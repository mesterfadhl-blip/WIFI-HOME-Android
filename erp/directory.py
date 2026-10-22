"""Maintain master data without rewriting posted document snapshots or stock."""

from .domain import BusinessError, audit, money


def migrate(c):
    if "active" not in {r["name"] for r in c.execute("PRAGMA table_info(products)")}:
        c.execute("ALTER TABLE products ADD COLUMN active INTEGER NOT NULL DEFAULT 1")


def handle(c, path, method, data, env, uid, role):
    parts = path.strip("/").split("/")
    if (
        len(parts) != 3
        or parts[0] != "api"
        or parts[1] not in ("customers", "products")
        or method != "PUT"
    ):
        return None
    kind = parts[1]
    id = int(parts[2])
    if (kind == "products" and role != "admin") or (
        kind == "customers" and role not in ("admin", "accountant")
    ):
        raise BusinessError("تعديل الدليل يحتاج صلاحية المدير أو المحاسب")
    old = c.execute(f"SELECT * FROM {kind} WHERE id=?", (id,)).fetchone()
    if not old:
        raise BusinessError("السجل غير موجود")
    name = str(data.get("name", "")).strip()
    if not name or len(name) > 300:
        raise BusinessError("أدخل اسماً صالحاً")
    if kind == "customers":
        c.execute(
            "UPDATE customers SET name=?,phone=?,address=?,region=?,credit_limit=? WHERE id=?",
            (
                name,
                str(data.get("phone", ""))[:100],
                str(data.get("address", ""))[:1000],
                str(data.get("region", ""))[:300],
                money(data.get("credit_limit", 0)),
                id,
            ),
        )
    else:
        active = data.get("active", True)
        if not isinstance(active, bool):
            raise BusinessError("حالة الصنف غير صالحة")
        c.execute(
            "UPDATE products SET name=?,price=?,active=? WHERE id=?",
            (name, money(data.get("price", 0)), int(active), id),
        )
    audit(
        c,
        uid,
        "تعديل بيانات عميل" if kind == "customers" else "تعديل بيانات صنف",
        str(id),
    )
    return {"ok": True}
