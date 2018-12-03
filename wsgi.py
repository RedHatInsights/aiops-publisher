import os
import logging
import io
import tarfile
import tempfile
import json
import re

from flask import Flask, jsonify, request
from flask.logging import default_handler
import requests

application = Flask(__name__)  # noqa

# Set up logging
ROOT_LOGGER = logging.getLogger()
ROOT_LOGGER.setLevel(application.logger.level)
ROOT_LOGGER.addHandler(default_handler)

# Upload Service
UPLOAD_SERVICE_ENDPOINT = os.environ.get('UPLOAD_SERVICE_ENDPOINT')


@application.route("/", methods=['POST'])
def wake_up():
    """Endpoint for upload and publish requests."""
    input_data = request.get_json(force=True)
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

    ai_service_id = re.sub(r'[^a-z]', r'', ai_service_id.lower())
    files = {
        'upload': (
            temp_file_name, open(temp_file_name, 'rb'),
            f'application/vnd.redhat.{ai_service_id}.aiservice+tgz'
        )
    }

    headers = {'x-rh-insights-request-id': data_id}

    # send a POST request to upload service with files and headers info
    try:
        response = requests.post(
            f'http://{UPLOAD_SERVICE_ENDPOINT}',
            files=files,
            headers=headers
        )
        response.raise_for_status()

    except (ConnectionError, requests.HTTPError, requests.Timeout) as e:
        error_msg = "Error while posting data to Upload service: " + str(e)
        ROOT_LOGGER.exception("Exception: %s", error_msg)

        # TODO Implement Retry here # noqa
        # Retry needs to examine the status_code/exact Exception type
        # before it attempts to Retry
        # a 415 error (Unsupported Media Type) for example,
        # will continue to fail even in the next attempt
        # so there is no value in pursuing a Retry for error=415
        # A Timeout error, on the other hand, is worth Retrying

        return jsonify(
            status='Error',
            type=str(e.__class__.__name__),
            status_code=response.status_code,
            message=error_msg
        ), 500

    try:
        os.remove(temp_file_name)
    except IOError as e:
        # simply log the exception in this case
        # do not return an error since this is not a critical error
        error_msg = "Error while deleting the temporary file: " + str(e)
        ROOT_LOGGER.exception("Exception: %s", error_msg)

    return jsonify(
        status='OK',
        message='Data published via Upload service'
    )


if __name__ == '__main__':
    application.run()
