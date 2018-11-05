import os
import logging

from flask import Flask, jsonify, request
from flask.logging import default_handler

import s3
import producer

application = Flask(__name__)  # noqa

# Set up logging
ROOT_LOGGER = logging.getLogger()
ROOT_LOGGER.setLevel(application.logger.level)
ROOT_LOGGER.addHandler(default_handler)

# Kafka message bus
SERVER = os.environ.get('KAFKA_SERVER')
TOPIC = os.environ.get('KAFKA_TOPIC')

# S3 credentials
AWS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_BUCKET = os.environ.get('AWS_S3_BUCKET_NAME')


@application.route("/", methods=['POST'])
def wake_up():
    """Endpoint for upload and publish requests."""
    input_data = request.get_json(force=True)
    data_id = input_data['id']
    ai_service_id = input_data.get('ai_service', 'generic_ai')
    raw_data = input_data['data']

    s3_destination = f'{AWS_BUCKET}/{data_id}/{ai_service_id}'

    application.logger.info(
        'Saving data to location:  s3://%s', s3_destination
    )

    filesystem = s3.connect(AWS_KEY, AWS_SECRET)
    s3.save_data(filesystem, s3_destination, raw_data)

    message = {
        'message': f'AI-Ops pipeline successfull for {data_id}',
        'url': s3_destination
    }

    application.logger.info('Publishing message on topic %s', TOPIC)
    producer.publish_message(SERVER, TOPIC, message)

    return jsonify(status='OK', message='Data published')


if __name__ == '__main__':
    application.run()
