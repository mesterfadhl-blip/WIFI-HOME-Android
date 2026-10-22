"""Run the unchanged ERP WSGI application in the browser's private filesystem."""

import base64
import hashlib
import io
import json
import sqlite3
import os
from urllib.parse import urlsplit
from erp.server import create_app

DATABASE = "/data/erp.sqlite3"
application = create_app(DATABASE)
with sqlite3.connect(DATABASE) as _metadata:
    if _metadata.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='legacy_settings'"
    ).fetchone():
        _company = _metadata.execute(
            "SELECT value FROM legacy_settings WHERE key='company'"
        ).fetchone()
        if _company:
            os.environ["ERP_COMPANY"] = _company[0]
_cookie = ""


def call(request_json):
    global _cookie
    request = json.loads(request_json)
    url = urlsplit(request["path"])
    raw = request.get("body", "").encode()
    supplied = {k.lower(): v for k, v in request.get("headers", {}).items()}
    env = {
        "REQUEST_METHOD": request.get("method", "GET"),
        "PATH_INFO": url.path,
        "QUERY_STRING": url.query,
        "CONTENT_LENGTH": str(len(raw)),
        "CONTENT_TYPE": supplied.get("content-type", "application/json"),
        "wsgi.input": io.BytesIO(raw),
        "wsgi.errors": io.StringIO(),
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "https",
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "SERVER_NAME": "local-device",
        "SERVER_PORT": "443",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "REMOTE_ADDR": "local-device",
        "HTTP_COOKIE": _cookie,
        "HTTP_X_CSRF_TOKEN": supplied.get("x-csrf-token", ""),
    }
    response = {}

    def start(status, headers):
        global _cookie
        response["status"] = int(status.split()[0])
        response["headers"] = dict(headers)
        if "Set-Cookie" in response["headers"]:
            _cookie = response["headers"]["Set-Cookie"].split(";")[0]

    body = b"".join(application(env, start))
    response["body"] = base64.b64encode(body).decode()
    return json.dumps(response)


def snapshot():
    # Consistent SQLite backup, including data still in the WAL.
    target = "/data/export.sqlite3"
    import os

    if os.path.exists(target):
        os.unlink(target)
    with sqlite3.connect(DATABASE) as source:
        with sqlite3.connect(target) as dest:
            source.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Database integrity check failed")
    with open(target, "rb") as file:
        return base64.b64encode(file.read()).decode()
