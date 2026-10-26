"""Native desktop entry point: private seed, persistent data and a single instance."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import urllib.request
import webbrowser
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

from .backup import backup
from .server import create_app


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def verify_database(path):
    with closing(
        sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    ) as c:
        if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError(
                "Database integrity check failed; original files were kept"
            )
        if c.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError(
                "Database references are inconsistent; original files were kept"
            )


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def empty_connection(c):
    tables = [
        r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ]
    if not {"customers", "products", "invoices", "journal", "users"}.issubset(tables):
        return False
    for name in tables:
        if name.startswith("sqlite_") or name in (
            "users",
            "sessions",
            "login_attempts",
            "audit",
        ):
            continue
        if name == "warehouses":
            if c.execute("SELECT count(*) FROM warehouses WHERE id!=1").fetchone()[0]:
                return False
            continue
        if c.execute("SELECT count(*) FROM " + quoted(name)).fetchone()[0]:
            return False
    return True


def accounting_empty(path):
    with closing(sqlite3.connect(path)) as c:
        return empty_connection(c)


def fill_empty_install(seed, target):
    # Never replace a live database file or remove its WAL. Merge the trusted
    # seed under a writer transaction, retaining accounts and existing audit.
    create_app(target)
    with closing(sqlite3.connect(target, timeout=15)) as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("ATTACH DATABASE ? AS bundled", (str(seed),))
        c.execute("BEGIN IMMEDIATE")
        try:
            if not empty_connection(c):
                c.rollback()
                return False
            if c.execute("SELECT count(*) FROM bundled.users").fetchone()[0]:
                raise RuntimeError(
                    "The seed must not contain preconfigured user accounts"
                )
            c.execute("PRAGMA defer_foreign_keys=ON")
            tables = c.execute(
                "SELECT name,sql FROM bundled.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            for name, ddl in tables:
                if not c.execute(
                    "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name=?",
                    (name,),
                ).fetchone():
                    c.execute(ddl)
                target_cols = {
                    r[1]
                    for r in c.execute("PRAGMA main.table_info(" + quoted(name) + ")")
                }
                for col in c.execute(
                    "PRAGMA bundled.table_info(" + quoted(name) + ")"
                ).fetchall():
                    if col[1] not in target_cols:
                        if col[5]:
                            raise RuntimeError(
                                "Incompatible primary-key schema; original database was kept"
                            )
                        definition = (
                            quoted(col[1])
                            + " "
                            + col[2]
                            + (" NOT NULL" if col[3] else "")
                        )
                        if col[4] is not None:
                            definition += " DEFAULT " + str(col[4])
                        c.execute(
                            "ALTER TABLE " + quoted(name) + " ADD COLUMN " + definition
                        )
            for name, _ in tables:
                if name in ("users", "sessions", "login_attempts"):
                    continue
                cols = [
                    r[1]
                    for r in c.execute(
                        "PRAGMA bundled.table_info(" + quoted(name) + ")"
                    )
                ]
                if name == "audit":
                    cols.remove("id")
                fields = ",".join(quoted(col) for col in cols)
                insert = "INSERT OR IGNORE" if name == "warehouses" else "INSERT"
                c.execute(
                    insert
                    + " INTO main."
                    + quoted(name)
                    + "("
                    + fields
                    + ") SELECT "
                    + fields
                    + " FROM bundled."
                    + quoted(name)
                )
            if c.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("Seed import reference check failed")
            c.commit()
            return True
        except Exception:
            c.rollback()
            raise


def bootstrap_database(seed, target):
    seed = Path(seed)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    recovery = None
    if existed:
        verify_database(target)
        folder = target.parent / "backups"
        folder.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        recovery = backup(
            target, folder / f"before-start-{stamp}-{secrets.token_hex(4)}.sqlite3"
        )
    mode = "existing"
    if not existed or accounting_empty(target):
        if not seed.is_file():
            raise RuntimeError(
                "The private seed database is missing. Extract the complete ZIP first."
            )
        verify_database(seed)
        if existed:
            if fill_empty_install(seed, target):
                mode = "filled-empty"
        else:
            prepared = target.parent / f".seed-{secrets.token_hex(8)}.sqlite3"
            try:
                backup(seed, prepared)
                verify_database(prepared)
                if target.exists():
                    raise RuntimeError(
                        "Another process created the database; retry safely"
                    )
                os.replace(prepared, target)
                mode = "seeded"
            finally:
                prepared.unlink(missing_ok=True)
    # Application performs additive migrations only after the recovery backup.
    app = create_app(target)
    with closing(sqlite3.connect(target)) as c:
        if c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='legacy_settings'"
        ).fetchone():
            company = c.execute(
                "SELECT value FROM legacy_settings WHERE key='company'"
            ).fetchone()
            if company:
                os.environ["ERP_COMPANY"] = company[0]
    verify_database(target)
    return app, mode, recovery


def existing_instance(folder, opener):
    for _ in range(20):
        try:
            info = json.loads((folder / "running.json").read_text())
            port = int(info["port"])
            nonce = info["instance"]
            if not 1 <= port <= 65535:
                raise ValueError("Invalid port")
            address = f"http://127.0.0.1:{port}/"
            req = urllib.request.Request(
                address + "_desktop_ping", headers={"X-Desktop-Instance": nonce}
            )
            # Local requests must never be sent to an inherited network proxy.
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                req, timeout=1
            ) as response:
                result = json.load(response)
            if result.get("app") == "WIFI-HOME-ERP" and hmac.compare_digest(
                str(result.get("instance", "")), str(nonce)
            ):
                opener(address)
                print("The existing system window was opened.", flush=True)
                return True
        except (OSError, ValueError, KeyError):
            time.sleep(0.1)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seed",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "seed" / "DATABASE.sqlite3",
    )
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    os.umask(0o077)
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    folder = args.data_dir or base / "WIFI-HOME-ERP"
    folder.mkdir(parents=True, exist_ok=True)
    opener = (lambda address: None) if args.no_browser else webbrowser.open
    lock = sqlite3.connect(folder / ".running-lock.sqlite3", timeout=0)
    try:
        try:
            lock.execute("CREATE TABLE IF NOT EXISTS guard(id INTEGER)")
            lock.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError:
            if existing_instance(folder, opener):
                return 0
            raise RuntimeError(
                "Another system process is starting or busy. Keep its window open and retry."
            )
        app, mode, recovery = bootstrap_database(args.seed, folder / "data.sqlite3")
        nonce = secrets.token_urlsafe(24)
        current = {}

        def guarded(env, start):
            env["wsgi.multithread"] = True
            host = env.get("HTTP_HOST", "")
            origin = env.get("HTTP_ORIGIN")
            if host != current["host"] or (origin and origin != current["origin"]):
                start("403 Forbidden", [("Content-Type", "text/plain")])
                return [b"Local requests only"]
            if env.get("PATH_INFO") == "/_desktop_ping":
                if not hmac.compare_digest(
                    env.get("HTTP_X_DESKTOP_INSTANCE", ""), nonce
                ):
                    start("403 Forbidden", [("Content-Type", "text/plain")])
                    return [b"Forbidden"]
                start(
                    "200 OK",
                    [
                        ("Content-Type", "application/json"),
                        ("Cache-Control", "no-store"),
                    ],
                )
                return [
                    json.dumps({"app": "WIFI-HOME-ERP", "instance": nonce}).encode()
                ]
            return app(env, start)

        with make_server(
            "127.0.0.1",
            0,
            guarded,
            server_class=ThreadedServer,
            handler_class=QuietHandler,
        ) as server:
            current["host"] = f"127.0.0.1:{server.server_port}"
            current["origin"] = "http://" + current["host"]
            address = current["origin"] + "/"
            info = {"port": server.server_port, "instance": nonce, "pid": os.getpid()}
            temporary = folder / "running.json.tmp"
            temporary.write_text(json.dumps(info))
            os.replace(temporary, folder / "running.json")
            print("WIFI HOME ERP — desktop", flush=True)
            print("Address: " + address, flush=True)
            print("Data: " + str(folder / "data.sqlite3"), flush=True)
            print("Data mode: " + mode, flush=True)
            if recovery:
                print("Recovery backup: " + str(recovery), flush=True)
            print(
                "Keep this window open while using the system. Ctrl+C stops it.",
                flush=True,
            )
            timer = threading.Timer(0.3, opener, args=(address,))
            timer.daemon = True
            timer.start()
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        (folder / "running.json").unlink(missing_ok=True)
    finally:
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
