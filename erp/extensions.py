"""Version-three modules and replay-safe mutation dispatch."""

import hashlib
import json
from .domain import BusinessError
from . import (
    settlements,
    warehouses,
    treasury,
    legacy,
    procurement,
    administration,
    directory,
)


def migrate(c):
    settlements.migrate(c)
    warehouses.migrate(c)
    treasury.migrate(c)
    legacy.migrate(c)
    procurement.migrate(c)
    administration.migrate(c)
    directory.migrate(c)
    c.execute("PRAGMA user_version=4")


def handle(c, path, method, data, env, uid, role):
    token = data.get("request_id") if method == "POST" else None
    key = None
    if token:
        if not isinstance(token, str) or len(token) > 100:
            raise BusinessError("معرف الطلب غير صالح")
        key = f"v3:{uid}:{path}:{token}"
        fingerprint = hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        old = c.execute(
            "SELECT * FROM operation_requests WHERE key=?", (key,)
        ).fetchone()
        if old:
            if old["fingerprint"] != fingerprint:
                raise BusinessError("معرف الطلب مرتبط بمحتوى مختلف")
            return json.loads(old["result"])
    result = None
    for module in (
        directory,
        legacy,
        procurement,
        administration,
        settlements,
        warehouses,
        treasury,
    ):
        result = module.handle(c, path, method, data, env, uid, role)
        if result is not None:
            break
    if (
        result is None
        and method == "POST"
        and path in ("/api/payments", "/api/expenses", "/api/funding", "/api/returns")
    ):
        from .operations import handle as original_handle

        result = original_handle(c, path, method, data, env, uid, role)
    if result is not None and key:
        c.execute(
            "INSERT INTO operation_requests VALUES(?,?,?)",
            (key, fingerprint, json.dumps(result, ensure_ascii=False)),
        )
    return result
