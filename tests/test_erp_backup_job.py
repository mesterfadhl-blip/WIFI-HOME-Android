import hashlib, base64, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from erp.backup_job import upload_backup, start_scheduler


class BackupJobTests(unittest.TestCase):
    def test_offsite_snapshot_checks_integrity_checksum_and_encryption(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.sqlite3"
            with sqlite3.connect(source) as c:
                c.execute("CREATE TABLE example(value TEXT)")
                c.execute("INSERT INTO example VALUES('synthetic')")

            class S3:
                def put_object(self, **args):
                    self.args = args
                    self.content = args["Body"].read()

            client = S3()
            key = upload_backup(source, "synthetic-review-bucket", client=client)
            self.assertTrue(key.endswith(".sqlite3"))
            self.assertEqual(client.args["ServerSideEncryption"], "AES256")
            self.assertEqual(
                client.args["ChecksumSHA256"],
                base64.b64encode(hashlib.sha256(client.content).digest()).decode(),
            )
            restored = Path(folder) / "restored.sqlite3"
            restored.write_bytes(client.content)
            with sqlite3.connect(restored) as c:
                self.assertEqual(
                    c.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
                self.assertEqual(
                    c.execute("SELECT value FROM example").fetchone()[0], "synthetic"
                )

    def test_scheduler_requires_explicit_config_and_sane_interval(self):
        with patch.dict("os.environ", {"ERP_BACKUP_BUCKET": ""}):
            self.assertIsNone(start_scheduler("/not-used"))
        with patch.dict(
            "os.environ",
            {"ERP_BACKUP_BUCKET": "synthetic", "ERP_BACKUP_INTERVAL_SECONDS": "1"},
        ):
            with self.assertRaises(ValueError):
                start_scheduler("/not-used")
