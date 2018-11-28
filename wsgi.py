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
UPLOAD_SERVICE = os.environ.get('UPLOAD_SERVICE')


@application.route("/", methods=['POST'])
def wake_up():
    """Endpoint for upload and publish requests."""
    input_data = request.get_json(force=True)
    data_id = input_data['id']
    raw_data = input_data['data']

    try:
        # create a tar.gz file using a temp file
        with tempfile.NamedTemporaryFile(dir='/tmp', delete=False) as tmp_file:
            temp_file_name = tmp_file.name
            with tarfile.open(temp_file_name, "w:gz") as tar:
                data = io.BytesIO()
                data_len = data.write(json.dumps(raw_data).encode())
                info = tar.tarinfo()
                info.name = 'aiservice_id_' + data_id
                info.size = data_len

                # add the tar.gz file to tar and close it
                data.seek(0)
                tar.addfile(info, data)
                tar.close()
    except IOError as e:
        return jsonify(
            status='Error',
            message='Error during TAR.GZ creation: ' + str(e)
        )

    files = {
        'upload': (
            temp_file_name, open(temp_file_name, 'rb'),
            'application/vnd.redhat.aiopspublisher.aiservice+tgz'
        )
    }

    headers = {'x-rh-insights-request-id': data_id}

    # send a POST request to upload service with files and headers info
    requests.post(f'http://{UPLOAD_SERVICE}', files=files, headers=headers)
    os.remove(temp_file_name)

    return jsonify(
        status='OK',
        message='Data published via Upload service'
    )


if __name__ == '__main__':
    application.run()
