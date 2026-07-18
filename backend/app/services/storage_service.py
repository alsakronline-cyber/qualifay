"""Object storage for message attachments (email PDFs, images, etc.) in MinIO.
Files are stored under an 'attachments' bucket; the app streams them back through an
authenticated endpoint rather than exposing MinIO directly."""
import io
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

BUCKET = "attachments"


def _client():
    from minio import Minio
    ep = settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
    secure = settings.MINIO_ENDPOINT.startswith("https")
    return Minio(ep, access_key=settings.MINIO_USER, secret_key=settings.MINIO_PASSWORD, secure=secure)


def upload_attachment(key: str, data: bytes, content_type: str) -> bool:
    """Store bytes at `key`. Returns True on success (never raises)."""
    try:
        c = _client()
        if not c.bucket_exists(BUCKET):
            c.make_bucket(BUCKET)
        c.put_object(BUCKET, key, io.BytesIO(data), length=len(data),
                     content_type=content_type or "application/octet-stream")
        return True
    except Exception as e:
        logger.warning("attachment upload failed for %s: %s", key, e)
        return False


def get_attachment(key: str):
    """Return (bytes, content_type) for `key`, or (None, None) if unavailable."""
    try:
        c = _client()
        resp = c.get_object(BUCKET, key)
        data = resp.read()
        ct = resp.headers.get("Content-Type", "application/octet-stream")
        resp.close()
        resp.release_conn()
        return data, ct
    except Exception as e:
        logger.warning("attachment fetch failed for %s: %s", key, e)
        return None, None
