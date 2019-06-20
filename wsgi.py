import os
import logging
import io
import tarfile
import tempfile
import json
import sys
from contextlib import suppress

from flask import Flask, jsonify, request
from flask.logging import default_handler
import requests
from gunicorn.arbiter import Arbiter
from urllib3.exceptions import NewConnectionError

from publish_json_schema import PublishJSONSchema

# Set up logging
ROOT_LOGGER = logging.getLogger()
ROOT_LOGGER.addHandler(default_handler)

# all gunicorn processes in a given instance need to access a common
# folder in /tmp where the metrics can be recorded
PROMETHEUS_MULTIPROC_DIR = '/tmp/aiops_publisher'

try:
    os.makedirs(PROMETHEUS_MULTIPROC_DIR, exist_ok=True)
    os.environ['prometheus_multiproc_dir'] = PROMETHEUS_MULTIPROC_DIR
    import prometheus_metrics
except IOError as e:
    # this is a non-starter for scraping metrics in the
    # Multiprocess Mode (Gunicorn)
    # terminate if there is an exception here
    ROOT_LOGGER.error(
        "Error while creating prometheus_multiproc_dir: %s", e
    )
    sys.exit(Arbiter.APP_LOAD_ERROR)


application = Flask(__name__)  # noqa

# Set up logging level
ROOT_LOGGER.setLevel(application.logger.level)

VERSION = "0.0.1"

# Upload Service
UPLOAD_SERVICE = os.environ.get('UPLOAD_SERVICE')
UPLOAD_SERVICE_PATH = os.environ.get('UPLOAD_SERVICE_PATH')

# Schema for the Publish API
SCHEMA = PublishJSONSchema()

MAX_RETRIES = 3


def _retryable(method: str, *args, **kwargs) -> requests.Response:
    """Retryable HTTP request.

    Invoke a "method" on "requests.session" with retry logic.
    :param method: "get", "post" etc.
    :param *args: Args for requests (first should be an URL, etc.)
    :param **kwargs: Kwargs for requests
    :return: Response object
    :raises: HTTPError when all requests fail
    """
    with requests.Session() as session:
        for attempt in range(MAX_RETRIES):
            try:
                resp = getattr(session, method)(*args, **kwargs)

                resp.raise_for_status()
            except (requests.HTTPError, requests.ConnectionError) as e:
                ROOT_LOGGER.warning(
                    'Request failed (attempt #%d), retrying: %s',
                    attempt, str(e)
                )
                continue
            else:
                return resp

    raise requests.HTTPError('All attempts failed')


@application.route('/', methods=['GET'])
def get_root():
    """Root Endpoint for Liveness/Readiness check."""
    try:
        _retryable('get', f'{UPLOAD_SERVICE}')
        status = 'OK'
        message = 'Up and Running'
        status_code = 200
    except (requests.HTTPError, NewConnectionError):
        status = 'Error'
        message = 'upload-service not operational'
        status_code = 500

    return jsonify(
        status=status,
        version=VERSION,
        message=message
    ), status_code


@application.route('/api/v0/version', methods=['GET'])
def get_version():
    """Endpoint for getting the current version."""
    return jsonify(
        status='OK',
        version=VERSION,
        message='AIOPS Publisher Version 0.0.1'
    )


@application.route("/api/v0/publish", methods=['GET'])
def get_publish():
    """Endpoint for get route for publish."""
    return jsonify(
        status='OK',
        version=VERSION,
        message='Requires a POST call to publish recommendations'
    )


@application.route("/api/v0/publish", methods=['POST'])
def post_publish():
    """Endpoint for upload and publish requests."""
    input_data = request.get_json(force=True)
    validation = SCHEMA.load(input_data)
    if validation.errors:
        return jsonify(
            status='Error',
            errors=validation.errors,
            message='Input payload validation failed'
        ), 400

    data_id = input_data['id']
    ai_service_id = input_data.get('ai_service', 'generic_ai')
    raw_data = input_data['data']

    try:
        temp_file_name = tempfile.NamedTemporaryFile(delete=False).name
        with tarfile.open(temp_file_name, "w:gz") as tar:
            data = io.BytesIO(json.dumps(raw_data).encode())
            info = tarfile.TarInfo(name=f'{ai_service_id}_{data_id}.json')
            info.size = len(data.getvalue())
            temp_file_name = tar.name
            tar.addfile(info, data)

    except (IOError, tarfile.TarError) as e:
        error_msg = 'Error during TAR.GZ creation: ' + str(e)
        ROOT_LOGGER.exception("Exception: %s", error_msg)
        return jsonify(
            status='Error',
            type=str(e.__class__.__name__),
            message=error_msg
        ), 500

    files = {
        'upload': (
            temp_file_name, open(temp_file_name, 'rb'),
            f'application/vnd.redhat.{ai_service_id}.aiservice+tgz'
        )
    }

    b64_identity = request.headers.get('x-rh-identity')

    headers = {'x-rh-insights-request-id': data_id,
               'x-rh-identity': b64_identity}

    # send a POST request to upload service with files and headers info
    try:
        prometheus_metrics.METRICS['posts'].inc()
        _retryable(
            'post',
            f'{UPLOAD_SERVICE}/{UPLOAD_SERVICE_PATH}/upload',
            files=files,
            headers=headers
        )
        prometheus_metrics.METRICS['post_successes'].inc()
    except requests.HTTPError as e:
        ROOT_LOGGER.error("Unable to access upload-service: %s", e)
        prometheus_metrics.METRICS['post_errors'].inc()
        return jsonify(
            status='Error',
            type=str(e.__class__.__name__),
            status_code=500,
            message="Unable to access upload-service"
        ), 500
    finally:
        with suppress(IOError):
            os.remove(temp_file_name)

    return jsonify(
        status='OK',
        message='Data published via Upload service'
    )


@application.route("/metrics", methods=['GET'])
def get_metrics():
    """Metrics Endpoint."""
    return prometheus_metrics.generate_aggregated_metrics()


if __name__ == '__main__':
    # pylama:ignore=C0103
    port = os.environ.get("PORT", 8003)
    application.run(port=int(port))
