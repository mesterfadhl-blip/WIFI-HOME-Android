"""Reviewed, idempotent customer migration from the two previous browser apps."""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from .domain import BusinessError, audit, journal, money, date
from .operations import open_date


def migrate(c):
    c.executescript(
        """CREATE TABLE IF NOT EXISTS legacy_customers(source TEXT NOT NULL,legacy_id TEXT NOT NULL,customer_id INTEGER NOT NULL REFERENCES customers(id),fingerprint TEXT NOT NULL,PRIMARY KEY(source,legacy_id));"""
    )
    cols = {r["name"] for r in c.execute("PRAGMA table_info(customers)")}
    for col, kind in [
        ("region", "TEXT NOT NULL DEFAULT ''"),
        ("credit_limit", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in cols:
            c.execute(f"ALTER TABLE customers ADD COLUMN {col} {kind}")


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def text(value, limit=300):
    if not isinstance(value, (str, int)) or len(str(value)) > limit:
        raise BusinessError("قيمة نصية غير صالحة في ملف العملاء")
    return str(value).strip()


def preview(c, data):
    package = data.get("backup")
    if not isinstance(package, dict):
        raise BusinessError("اختر ملف نسخة احتياطية بصيغة JSON")
    db = package.get("database", package.get("data", package))
    if not isinstance(db, dict) or not isinstance(db.get("customers"), list):
        raise BusinessError("النسخة لا تحتوي قائمة عملاء")
    source = text(data.get("source", "wifi-home-legacy"), 100)
    if not source:
        raise BusinessError("أدخل رمز مصدر ثابت لهذه النسخة")
    day = date(data.get("date"))
    balances = data.get("include_balances", False)
    if not isinstance(balances, bool):
        raise BusinessError("خيار نقل الأرصدة غير صالح")
    people = db["customers"]
    if not people or len(people) > 5000:
        raise BusinessError("عدد العملاء يجب أن يكون من 1 إلى 5000")
    entries = db.get("journal", [])
    if balances and not isinstance(entries, list):
        raise BusinessError("دفتر القيود غير صالح")
    totals = {}
    ids = set()
    for person in people:
        if not isinstance(person, dict):
            raise BusinessError("سجل عميل غير صالح")
        ident = text(person.get("id", ""), 100)
        if not ident or ident in ids:
            raise BusinessError("معرفات العملاء مفقودة أو متكررة")
        ids.add(ident)
    if balances:
        if not entries:
            raise BusinessError(
                "لا توجد قيود للتحقق من الأرصدة؛ استورد الأسماء فقط أو أرفق نسخة كاملة"
            )
        for entry in entries:
            if not isinstance(entry, dict):
                raise BusinessError("قيد قديم غير صالح")
            if entry.get("account") != "العملاء":
                continue
            cid = text(entry.get("customerId", ""), 100)
            if cid not in ids:
                raise BusinessError("يوجد قيد لعميل غير موجود بالنسخة؛ راجع الملف أولاً")
            when = date(str(entry.get("date", ""))[:10])
            if when <= day:
                totals[cid] = (
                    totals.get(cid, 0)
                    + money(entry.get("debit", 0))
                    - money(entry.get("credit", 0))
                )
    rows = []
    seen = set()
    for person in people:
        ident = text(person["id"], 100)
        name = text(person.get("name", ""))
        phone = text(person.get("phone", ""), 100)
        if not name:
            raise BusinessError("يوجد عميل بدون اسم")
        row = {
            "legacy_id": ident,
            "name": name,
            "phone": phone,
            "address": text(person.get("address", ""), 1000),
            "region": text(person.get("region", "")),
            "credit_limit": money(person.get("limit", 0)),
            "opening": totals.get(ident, 0),
        }
        fingerprint = digest(row)
        linked = c.execute(
            "SELECT * FROM legacy_customers WHERE source=? AND legacy_id=?",
            (source, ident),
        ).fetchone()
        if linked:
            action = "skip" if linked["fingerprint"] == fingerprint else "conflict"
        else:
            key = (name.casefold(), phone)
            same = c.execute(
                "SELECT 1 FROM customers WHERE lower(trim(name))=? AND trim(phone)=?",
                key,
            ).fetchone()
            action = "conflict" if same or key in seen else "create"
            seen.add(key)
        rows.append({**row, "action": action, "fingerprint": fingerprint})
    plan = {"source": source, "date": day, "include_balances": balances, "rows": rows}
    return {
        **plan,
        "token": digest(plan),
        "count": len(rows),
        "new": sum(r["action"] == "create" for r in rows),
        "skipped": sum(r["action"] == "skip" for r in rows),
        "conflicts": sum(r["action"] == "conflict" for r in rows),
        "debit": sum(max(r["opening"], 0) for r in rows if r["action"] == "create"),
        "credit": sum(max(-r["opening"], 0) for r in rows if r["action"] == "create"),
    }


def commit(c, data, uid):
    plan = preview(c, data)
    if data.get("token") != plan["token"]:
        raise BusinessError("تغير الملف أو العملاء بعد المعاينة؛ أعد المراجعة")
    if plan["conflicts"]:
        raise BusinessError(
            "يوجد تعارض في أسماء أو معرفات العملاء؛ لا يمكن اعتماد النقل"
        )
    if plan["include_balances"]:
        open_date(c, plan["date"])
    for row in plan["rows"]:
        if row["action"] == "skip":
            continue
        cid = c.execute(
            "INSERT INTO customers(name,phone,address,region,credit_limit) VALUES(?,?,?,?,?)",
            (
                row["name"],
                row["phone"],
                row["address"],
                row["region"],
                row["credit_limit"],
            ),
        ).lastrowid
        c.execute(
            "INSERT INTO legacy_customers VALUES(?,?,?,?)",
            (plan["source"], row["legacy_id"], cid, row["fingerprint"]),
        )
        amount = row["opening"]
        if amount:
            journal(
                c,
                f"LEGACY-CUSTOMER-{cid}",
                plan["date"],
                [
                    ("العملاء", cid, max(amount, 0), max(-amount, 0)),
                    (
                        "رأس المال والأرصدة الافتتاحية",
                        None,
                        max(-amount, 0),
                        max(amount, 0),
                    ),
                ],
            )
    audit(
        c,
        uid,
        "استيراد عملاء بعد المراجعة",
        plan["source"],
        json.dumps(
            {
                "created": plan["new"],
                "skipped": plan["skipped"],
                "balances": plan["include_balances"],
                "date": plan["date"],
            }
        ),
    )
    return {"created": plan["new"], "skipped": plan["skipped"]}


def handle(c, path, method, data, env, uid, role):
    if path not in ("/api/legacy/preview", "/api/legacy/import"):
        return None
    if role != "admin":
        raise BusinessError("استيراد البيانات للمدير فقط")
    if method != "POST":
        raise BusinessError("الطلب غير صالح")
    return preview(c, data) if path.endswith("/preview") else commit(c, data, uid)
