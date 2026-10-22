import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from erp.production import production_app
from erp.server import connect, password_hash


class ProductionTests(unittest.TestCase):
    def test_bootstrap_is_private_and_preserved_across_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "data.sqlite3")
            settings = {
                "ERP_DATABASE": path,
                "ERP_COOKIE_SECURE": "1",
                "ERP_ADMIN_NAME": "owner",
                "ERP_ADMIN_PASSWORD": "Synthetic-Test-Password-123",
            }
            with patch.dict(os.environ, settings):
                app = production_app()
                with connect(path) as c:
                    original = dict(c.execute("SELECT * FROM users").fetchone())
                    self.assertEqual(original["role"], "admin")
                    self.assertEqual(
                        password_hash(
                            settings["ERP_ADMIN_PASSWORD"],
                            original["password"].split(":")[0],
                        ),
                        original["password"],
                    )
                with patch.dict(os.environ, {"ERP_ADMIN_PASSWORD": ""}):
                    production_app()
                with connect(path) as c:
                    self.assertEqual(
                        dict(c.execute("SELECT * FROM users").fetchone()), original
                    )
                headers = []
                body = b"".join(
                    app(
                        {"PATH_INFO": "/healthz", "REQUEST_METHOD": "GET"},
                        lambda status, items: headers.append(status),
                    )
                )
                self.assertEqual(headers, ["200 OK"])
                self.assertEqual(body, b"ok")

    def test_missing_bootstrap_or_insecure_configuration_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = {
                "ERP_DATABASE": str(Path(folder) / "data.sqlite3"),
                "ERP_COOKIE_SECURE": "1",
                "ERP_ADMIN_NAME": "",
                "ERP_ADMIN_PASSWORD": "",
            }
            with patch.dict(os.environ, settings):
                with self.assertRaises(RuntimeError):
                    production_app()
                with connect(settings["ERP_DATABASE"]) as c:
                    self.assertEqual(
                        c.execute("SELECT count(*) FROM users").fetchone()[0], 0
                    )
                with patch.dict(os.environ, {"ERP_COOKIE_SECURE": "0"}):
                    with self.assertRaises(RuntimeError):
                        production_app()
