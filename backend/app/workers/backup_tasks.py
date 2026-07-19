"""Nightly database backups — pg_dump to /app/backups, keep the last N, and (best
effort) push to MinIO so a lost disk doesn't mean lost data."""
import logging
import os
import subprocess
from datetime import datetime
from urllib.parse import urlparse

from app.workers.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

BACKUP_DIR = os.environ.get("BACKUP_DIR", "/app/backups")
KEEP = int(os.environ.get("BACKUP_KEEP", "7"))


def _pg_env_and_target():
    """Turn the async SQLAlchemy URL into libpq connection parts for pg_dump."""
    url = settings.DATABASE_URL.replace("+asyncpg", "").replace("+psycopg2", "")
    p = urlparse(url)
    env = dict(os.environ)
    if p.password:
        env["PGPASSWORD"] = p.password
    return env, p


@celery_app.task(name="backups.run")
def run_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    env, p = _pg_env_and_target()
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    db = (p.path or "/qualifay").lstrip("/")
    out = os.path.join(BACKUP_DIR, f"{db}_{stamp}.sql.gz")

    cmd = ["pg_dump", "-h", p.hostname or "127.0.0.1", "-p", str(p.port or 5432),
           "-U", p.username or "qualifay", "-d", db, "--no-owner", "--no-privileges"]
    try:
        with open(out, "wb") as fh:
            dump = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            gz = subprocess.Popen(["gzip"], stdin=dump.stdout, stdout=fh)
            dump.stdout.close()
            gz.communicate()
            _, err = dump.communicate()
        if dump.returncode != 0:
            logger.error("pg_dump failed: %s", (err or b"").decode()[:500])
            if os.path.exists(out):
                os.remove(out)
            return {"ok": False, "error": "pg_dump failed"}
    except FileNotFoundError:
        logger.error("pg_dump not installed in this image")
        return {"ok": False, "error": "pg_dump missing"}

    size = os.path.getsize(out)
    _prune()
    remote = _upload_minio(out)
    offsite = _upload_offsite(out)
    logger.info("backup complete %s (%s bytes) minio=%s offsite=%s", out, size, remote, offsite)
    return {"ok": True, "file": os.path.basename(out), "size": size,
            "minio": remote, "offsite": offsite}


def _prune():
    try:
        files = sorted(
            [f for f in os.listdir(BACKUP_DIR) if f.endswith(".sql.gz")],
            key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), reverse=True,
        )
        for stale in files[KEEP:]:
            os.remove(os.path.join(BACKUP_DIR, stale))
    except Exception as e:
        logger.warning("prune failed: %s", e)


def _upload_minio(path: str):
    """Best-effort push to a 'backups' bucket. Never fail the backup over this."""
    try:
        from minio import Minio
        ep = settings.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
        secure = settings.MINIO_ENDPOINT.startswith("https")
        client = Minio(ep, access_key=settings.MINIO_USER, secret_key=settings.MINIO_PASSWORD, secure=secure)
        if not client.bucket_exists("backups"):
            client.make_bucket("backups")
        name = os.path.basename(path)
        client.fput_object("backups", name, path)
        return name
    except Exception as e:
        logger.warning("minio upload skipped: %s", e)
        return None


def _upload_offsite(path: str):
    """Push the dump to an off-box S3-compatible target (B2/S3/Wasabi), if configured.
    Best-effort: a remote failure must never fail the backup. Returns the remote key,
    'skipped' if unconfigured, or None on error."""
    if not (settings.BACKUP_S3_ENDPOINT and settings.BACKUP_S3_BUCKET
            and settings.BACKUP_S3_ACCESS_KEY and settings.BACKUP_S3_SECRET_KEY):
        return "skipped"
    try:
        from minio import Minio
        ep = settings.BACKUP_S3_ENDPOINT.replace("https://", "").replace("http://", "")
        client = Minio(
            ep,
            access_key=settings.BACKUP_S3_ACCESS_KEY,
            secret_key=settings.BACKUP_S3_SECRET_KEY,
            secure=settings.BACKUP_S3_SECURE,
        )
        if not client.bucket_exists(settings.BACKUP_S3_BUCKET):
            client.make_bucket(settings.BACKUP_S3_BUCKET)
        name = os.path.basename(path)
        client.fput_object(settings.BACKUP_S3_BUCKET, name, path)
        return name
    except Exception as e:
        logger.warning("offsite backup upload failed: %s", e)
        return None


def latest_backup_info():
    """Used by the monitoring endpoint to show when the last backup ran."""
    try:
        files = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".sql.gz")]
        if not files:
            return None
        newest = max(files, key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)))
        full = os.path.join(BACKUP_DIR, newest)
        return {"file": newest, "size": os.path.getsize(full),
                "at": datetime.utcfromtimestamp(os.path.getmtime(full)).isoformat(),
                "count": len(files)}
    except Exception:
        return None
