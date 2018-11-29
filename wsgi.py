import os
import logging
import io
import tarfile
import tempfile
import json
import requests

from flask import Flask, jsonify, request
from flask.logging import default_handler

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
        with tarfile.open(fileobj=tempfile.NamedTemporaryFile(delete=False), mode='w:gz') as f:   # noqa
            data = io.BytesIO(json.dumps(raw_data).encode())
            info = tarfile.TarInfo(name=f'{ai_service_id}_{data_id}.json')
            info.size = len(data.getvalue())
            temp_file_name = f.name
            f.addfile(info, data)

    except Exception as e:    # noqa
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
            'application/vnd.redhat.aiopspublisher.aiservice+tgz'
        )
    }

    headers = {'x-rh-insights-request-id': data_id}

    # send a POST request to upload service with files and headers info
    try:
        requests.post(
            f'http://{UPLOAD_SERVICE_ENDPOINT}',
            files=files,
            headers=headers
        )
        os.remove(temp_file_name)
    except Exception as e:   # noqa
        error_msg = "Error while posting data to Upload service" + str(e)
        ROOT_LOGGER.exception("Exception: %s", error_msg)
        return jsonify(
            status='Error',
            type=str(e.__class__.__name__),
            message=error_msg
        ), 500

    return jsonify(
        status='OK',
        message='Data published via Upload service'
    )


if __name__ == '__main__':
    application.run()
