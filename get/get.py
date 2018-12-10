import logging

from flask import jsonify

# Logger
ROOT_LOGGER = logging.getLogger()


def root_path():
    """Endpoint for default root path."""
    return jsonify(
        status='OK',
        message='AIOPS Publisher up and running!'
    )
