import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from erp.desktop import bootstrap_database
from erp.server import create_app, connect, password_hash


class DesktopDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.seed = self.root / "seed.sqlite3"
        create_app(self.seed)
        with connect(self.seed) as c:
            c.execute("INSERT INTO customers(name,phone) VALUES('seed customer','000')")
            c.commit()
        self.target = self.root / "persistent" / "data.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_run_copies_seed_and_keeps_original_unchanged(self):
        before = hashlib.sha256(self.seed.read_bytes()).hexdigest()
        _, mode, recovery = bootstrap_database(self.seed, self.target)
        self.assertEqual(mode, "seeded")
        self.assertIsNone(recovery)
        with connect(self.target) as c:
            self.assertEqual(
                c.execute("SELECT name FROM customers").fetchone()[0], "seed customer"
            )
        self.assertEqual(hashlib.sha256(self.seed.read_bytes()).hexdigest(), before)

    def test_restart_preserves_entered_data_and_creates_recovery_backup(self):
        bootstrap_database(self.seed, self.target)
        with connect(self.target) as c:
            c.execute("UPDATE customers SET name='owner edit'")
            c.commit()
        _, mode, recovery = bootstrap_database(
            self.root / "missing-seed.sqlite3", self.target
        )
        self.assertEqual(mode, "existing")
        self.assertTrue(recovery.exists())
        for path in (self.target, recovery):
            with connect(path) as c:
                self.assertEqual(
                    c.execute("SELECT name FROM customers").fetchone()[0], "owner edit"
                )

    def test_empty_old_install_gets_seed_without_losing_owner_or_audit(self):
        create_app(self.target)
        hashed = password_hash("Synthetic-Password-123")
        with connect(self.target) as c:
            c.execute(
                "INSERT INTO users(id,name,password,role) VALUES(1,?,?,?)",
                ("existing-owner", hashed, "admin"),
            )
            c.execute(
                "INSERT INTO audit(at,user_id,action,document,detail) VALUES('2026-10-20',1,'old audit','setup','preserve')"
            )
            c.commit()
        _, mode, recovery = bootstrap_database(self.seed, self.target)
        self.assertEqual(mode, "filled-empty")
        self.assertTrue(recovery.exists())
        with connect(self.target) as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM customers").fetchone()[0], 1
            )
            self.assertEqual(
                c.execute("SELECT password FROM users").fetchone()[0], hashed
            )
            self.assertEqual(
                c.execute(
                    "SELECT count(*) FROM audit WHERE action='old audit'"
                ).fetchone()[0],
                1,
            )
            self.assertFalse(c.execute("PRAGMA foreign_key_check").fetchall())
        with connect(recovery) as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM customers").fetchone()[0], 0
            )

    def test_corrupt_seed_does_not_replace_existing_file(self):
        create_app(self.target)
        before = self.target.read_bytes()
        bad = self.root / "corrupt.sqlite3"
        bad.write_bytes(b"not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            bootstrap_database(bad, self.target)
        self.assertEqual(self.target.read_bytes(), before)

    def test_custom_records_in_old_install_are_not_replaced(self):
        create_app(self.target)
        with connect(self.target) as c:
            c.execute("CREATE TABLE owner_settings(value TEXT)")
            c.execute("INSERT INTO owner_settings VALUES('keep')")
            c.commit()
        _, mode, _ = bootstrap_database(self.seed, self.target)
        self.assertEqual(mode, "existing")
        with connect(self.target) as c:
            self.assertEqual(
                c.execute("SELECT value FROM owner_settings").fetchone()[0], "keep"
            )
