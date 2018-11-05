"""S3 Data storage interface."""

from .s3 import connect, save_data

__all__ = ["connect", "save_data"]
