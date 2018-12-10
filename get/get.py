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


def version():
    """Endpoint for API version."""
    return jsonify(
        status='OK',
        message='AIOPS Publisher API Version 1.0.0'
    )
