import os
import logging

from flask import Flask, jsonify, request
from flask.logging import default_handler

application = Flask(__name__)  # noqa

# Set up logging
ROOT_LOGGER = logging.getLogger()
ROOT_LOGGER.setLevel(application.logger.level)
ROOT_LOGGER.addHandler(default_handler)

@application.route("/", methods=['POST'])
def wake_up():
    """Endpoint for upload and publish requests."""
    input_data = request.get_json(force=True)
    data_id = input_data['id']
    ai_service_id = input_data.get('ai_service', 'generic_ai')
    raw_data = input_data['data']

    return jsonify(status='OK', message='Data published')


if __name__ == '__main__':
    application.run()
