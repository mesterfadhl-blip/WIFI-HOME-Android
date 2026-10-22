"""Consistent encrypted S3 backups; activated only with an explicit private bucket."""

import base64
import hashlib
import logging
import os
from pathlib import Path
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from .backup import backup


def upload_backup(database, bucket, prefix="wifi-home-erp", client=None):
    if not bucket or "/" in bucket or len(bucket) > 63:
        raise ValueError("Set ERP_BACKUP_BUCKET to a valid private S3 bucket name")
    prefix = prefix.strip("/")
    if client is None:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            config=Config(
                connect_timeout=10, read_timeout=60, retries={"max_attempts": 2}
            ),
        )
    stamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%Y%m%dT%H%M%SZ")
    key = (
        (prefix + "/" if prefix else "")
        + stamp
        + "-"
        + secrets.token_hex(8)
        + ".sqlite3"
    )
    with tempfile.TemporaryDirectory(prefix="erp-backup-") as folder:
        path = backup(database, Path(folder) / "snapshot.sqlite3")
        checksum = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(chunk)
        with path.open("rb") as stream:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=stream,
                ContentType="application/vnd.sqlite3",
                ServerSideEncryption="AES256",
                ChecksumSHA256=base64.b64encode(checksum.digest()).decode(),
            )
    return key


def start_scheduler(database):
    bucket = os.environ.get("ERP_BACKUP_BUCKET", "").strip()
    if not bucket:
        return None
    interval = int(os.environ.get("ERP_BACKUP_INTERVAL_SECONDS", "86400"))
    if interval < 3600:
        raise ValueError("Backup interval must be at least one hour")
    prefix = os.environ.get("ERP_BACKUP_PREFIX", "wifi-home-erp")
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                upload_backup(database, bucket, prefix)
                logging.info("ERP off-site backup completed")
            except Exception as error:
                logging.error(
                    "ERP off-site backup failed (%s); check bucket and hosting credentials",
                    type(error).__name__,
                )
            stop.wait(interval)

    threading.Thread(target=worker, name="erp-backup", daemon=True).start()
    return stop


if __name__ == "__main__":
    upload_backup(
        os.environ["ERP_DATABASE"],
        os.environ["ERP_BACKUP_BUCKET"],
        os.environ.get("ERP_BACKUP_PREFIX", "wifi-home-erp"),
    )
    print("Off-site backup completed")
