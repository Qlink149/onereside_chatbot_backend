from typing import BinaryIO

from onereside_chatbot.database.storage.cloudflare_client import s3
from onereside_chatbot.utils.env_load import r2_bucket, r2_public_url
from onereside_chatbot.utils.logger_config import logger


def upload_media(file: BinaryIO, key: str, content_type: str = "image/jpeg") -> str:
    """Upload a file to R2. Returns the public URL."""
    try:
        s3.upload_fileobj(
            file,
            r2_bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        url = f"{r2_public_url.rstrip('/')}/{key}"
        logger.info("Media uploaded to R2.", extra={"key": key})
        return url
    except Exception as e:
        logger.exception("Failed to upload media to R2.", extra={"key": key})
        raise e


def get_media_url(key: str) -> str:
    """Return the public URL for an existing R2 object."""
    return f"{r2_public_url.rstrip('/')}/{key}"


def update_media(file: BinaryIO, key: str, content_type: str = "image/jpeg") -> str:
    """Replace an existing R2 object. Returns the new public URL."""
    try:
        url = upload_media(file, key, content_type)
        logger.info("Media updated in R2.", extra={"key": key})
        return url
    except Exception as e:
        logger.exception("Failed to update media in R2.", extra={"key": key})
        raise e


def delete_media(key: str) -> bool:
    """Delete an object from R2. Returns True on success."""
    try:
        s3.delete_object(Bucket=r2_bucket, Key=key)
        logger.info("Media deleted from R2.", extra={"key": key})
        return True
    except Exception as e:
        logger.exception("Failed to delete media from R2.", extra={"key": key})
        raise e
