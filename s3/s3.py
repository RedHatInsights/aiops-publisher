from s3fs import S3FileSystem


def connect(key: str, secret: str) -> S3FileSystem:
    """Create a Boto3 client for S3 service."""
    filesystem = S3FileSystem(key=key, secret=secret)

    return filesystem


def save_data(filesystem: str, location: str, data: str) -> dict:
    """Save the data received from AI Service."""
    with filesystem.open(location, 'w') as s3_file:
        s3_file.write(data)
