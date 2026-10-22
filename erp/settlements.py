"""Receipt allocation subledger: allocating money never posts a second cash entry."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from urllib.parse import parse_qs
from .domain import BusinessError, audit, date, money

SCHEMA = """
CREATE TABLE IF NOT EXISTS allocations(id INTEGER PRIMARY KEY,receipt_id INTEGER NOT NULL REFERENCES receipts(id),invoice_id INTEGER NOT NULL REFERENCES invoices(id),amount INTEGER NOT NULL,date TEXT NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id));
CREATE TABLE IF NOT EXISTS allocation_releases(id INTEGER PRIMARY KEY,allocation_id INTEGER NOT NULL REFERENCES allocations(id),amount INTEGER NOT NULL,date TEXT NOT NULL,reason TEXT NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id));
CREATE INDEX IF NOT EXISTS allocations_invoice ON allocations(invoice_id,date);
CREATE INDEX IF NOT EXISTS allocations_receipt ON allocations(receipt_id,date);
CREATE INDEX IF NOT EXISTS allocation_releases_source ON allocation_releases(allocation_id,date);
"""


def migrate(c):
    c.executescript(SCHEMA)
    if "due_date" not in {r["name"] for r in c.execute("PRAGMA table_info(invoices)")}:
        c.execute("ALTER TABLE invoices ADD COLUMN due_date TEXT")
    c.execute("UPDATE invoices SET due_date=date WHERE due_date IS NULL")


def allocation_amount(c, id, asof="9999-12-31"):
    row = c.execute("SELECT * FROM allocations WHERE id=?", (id,)).fetchone()
    if not row or row["date"] > asof:
        return 0
    released = c.execute(
        "SELECT coalesce(sum(amount),0) FROM allocation_releases WHERE allocation_id=? AND date<=?",
        (id, asof),
    ).fetchone()[0]
    return row["amount"] - released


def allocated(c, column, id, asof="9999-12-31"):
    if column not in ("receipt_id", "invoice_id"):
        raise ValueError("Invalid allocation scope")
    rows = c.execute(
        f"SELECT id FROM allocations WHERE {column}=? AND date<=?", (id, asof)
    ).fetchall()
    return sum(allocation_amount(c, r["id"], asof) for r in rows)


def invoice_balance(c, id, asof="9999-12-31"):
    s = c.execute("SELECT * FROM invoices WHERE id=?", (id,)).fetchone()
    if not s:
        raise BusinessError("الفاتورة غير موجودة")
    if s["date"] > asof or s["status"] != "posted":
        return {
            "issue_credit": s["total"] - s["paid"],
            "credits": 0,
            "refunds": 0,
            "allocated": 0,
            "outstanding": 0,
            "customer_credit": 0,
        }
    r = c.execute(
        "SELECT coalesce(sum(total),0) total,coalesce(sum(refund),0) refund FROM returns WHERE invoice_id=? AND status='posted' AND date<=?",
        (id, asof),
    ).fetchone()
    raw = s["total"] - s["paid"] - r["total"] + r["refund"]
    paid = allocated(c, "invoice_id", id, asof)
    return {
        "issue_credit": s["total"] - s["paid"],
        "credits": r["total"],
        "refunds": r["refund"],
        "allocated": paid,
        "outstanding": max(0, raw - paid),
        "customer_credit": max(0, -raw),
    }


def release(c, id, amount, day, reason, uid):
    from .operations import open_date

    day = open_date(c, day)
    reason = str(reason).strip()
    a = c.execute("SELECT * FROM allocations WHERE id=?", (id,)).fetchone()
    if not a or not reason or amount <= 0 or amount > allocation_amount(c, id):
        raise BusinessError("مبلغ فك التخصيص أو السبب غير صحيح")
    last = c.execute(
        "SELECT max(date) FROM allocation_releases WHERE allocation_id=?", (id,)
    ).fetchone()[0]
    if day < a["date"] or (last and day < last):
        raise BusinessError("تاريخ فك التخصيص يسبق حركة تخصيص لاحقة")
    c.execute(
        "INSERT INTO allocation_releases(allocation_id,amount,date,reason,user_id) VALUES(?,?,?,?,?)",
        (id, amount, day, reason, uid),
    )
    audit(c, uid, "فك تخصيص قبض", str(id), reason)


def trim_allocations(
    c, invoice_id, day, uid, all=False, reason="تعديل أو مرتجع الفاتورة"
):
    s = c.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    r = c.execute(
        "SELECT coalesce(sum(total-refund),0) FROM returns WHERE invoice_id=? AND status='posted'",
        (invoice_id,),
    ).fetchone()[0]
    capacity = 0 if all else max(0, s["total"] - s["paid"] - r)
    excess = max(0, allocated(c, "invoice_id", invoice_id) - capacity)
    for a in c.execute(
        "SELECT * FROM allocations WHERE invoice_id=? ORDER BY date DESC,id DESC",
        (invoice_id,),
    ).fetchall():
        if not excess:
            break
        if a["date"] > day:
            raise BusinessError("توجد تخصيصات بتاريخ لاحق؛ فك تخصيصها أولاً")
        amount = min(excess, allocation_amount(c, a["id"]))
        if amount:
            release(c, a["id"], amount, day, reason, uid)
            excess -= amount


def allocate(c, data, uid):
    from .operations import open_date

    day = open_date(c, data.get("date"))
    amount = money(data.get("amount", 0))
    r = c.execute(
        "SELECT * FROM receipts WHERE id=?", (data.get("receipt_id"),)
    ).fetchone()
    s = c.execute(
        "SELECT * FROM invoices WHERE id=?", (data.get("invoice_id"),)
    ).fetchone()
    if (
        not r
        or not s
        or s["status"] != "posted"
        or r["customer_id"] != s["customer_id"]
    ):
        raise BusinessError("القبض والفاتورة يجب أن يتبعا العميل نفسه، والفاتورة مرحلة")
    if day < max(r["date"], s["date"]):
        raise BusinessError("تاريخ التخصيص يسبق القبض أو الفاتورة")
    if (
        not amount
        or amount > r["amount"] - allocated(c, "receipt_id", r["id"])
        or amount > invoice_balance(c, s["id"])["outstanding"]
    ):
        raise BusinessError("التخصيص يتجاوز المتاح من القبض أو المتبقي من الفاتورة")
    id = c.execute(
        "INSERT INTO allocations(receipt_id,invoice_id,amount,date,user_id) VALUES(?,?,?,?,?)",
        (r["id"], s["id"], amount, day, uid),
    ).lastrowid
    audit(
        c,
        uid,
        "تخصيص سند قبض",
        s["number"],
        r["number"] + " — " + str(Decimal(amount) / 100),
    )
    return {"id": id, "balance": invoice_balance(c, s["id"])}


def data(c, asof="9999-12-31"):
    invoices = []
    for s in c.execute(
        "SELECT i.*,c.name customer FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.status='posted' AND i.date<=? ORDER BY i.date,i.id",
        (asof,),
    ).fetchall():
        invoices.append({**dict(s), **invoice_balance(c, s["id"], asof)})
    receipts = [
        {
            **dict(r),
            "available": r["amount"] - allocated(c, "receipt_id", r["id"], asof),
        }
        for r in c.execute(
            "SELECT r.*,c.name customer FROM receipts r JOIN customers c ON c.id=r.customer_id WHERE r.date<=? ORDER BY r.date DESC,r.id DESC",
            (asof,),
        )
    ]
    allocations = [
        {**dict(a), "remaining": allocation_amount(c, a["id"], asof)}
        for a in c.execute(
            "SELECT a.*,r.number receipt,i.number invoice,c.name customer FROM allocations a JOIN receipts r ON r.id=a.receipt_id JOIN invoices i ON i.id=a.invoice_id JOIN customers c ON c.id=i.customer_id WHERE a.date<=? ORDER BY a.date DESC,a.id DESC",
            (asof,),
        )
    ]
    return {"invoices": invoices, "receipts": receipts, "allocations": allocations}


def aging(c, asof):
    from datetime import date as Day

    asof = date(asof)
    state = data(c, asof)
    rows = []
    totals = {
        k: 0 for k in ("not_due", "days_1_30", "days_31_60", "days_61_90", "over_90")
    }
    for s in state["invoices"]:
        if not s["outstanding"]:
            continue
        days = (
            Day.fromisoformat(asof) - Day.fromisoformat(s["due_date"] or s["date"])
        ).days
        bucket = (
            "not_due"
            if days <= 0
            else (
                "days_1_30"
                if days <= 30
                else (
                    "days_31_60"
                    if days <= 60
                    else "days_61_90" if days <= 90 else "over_90"
                )
            )
        )
        totals[bucket] += s["outstanding"]
        rows.append({**s, "days_overdue": max(0, days), "bucket": bucket})
    unapplied = sum(r["available"] for r in state["receipts"])
    credits = sum(s["customer_credit"] for s in state["invoices"])
    gross = sum(totals.values())
    return {
        "asof": asof,
        "rows": rows,
        "buckets": totals,
        "gross_outstanding": gross,
        "unapplied_receipts": unapplied,
        "customer_credits": credits,
        "net_receivable": gross - unapplied - credits,
    }


def handle(c, path, method, payload, env, uid, role):
    query = {k: v[0] for k, v in parse_qs(env.get("QUERY_STRING", "")).items()}
    if path == "/api/settlements" and method == "GET":
        return data(c)
    if path == "/api/allocations" and method == "POST":
        return allocate(c, payload, uid)
    if (
        path.startswith("/api/allocations/")
        and path.endswith("/release")
        and method == "POST"
    ):
        if role not in ("admin", "accountant"):
            raise BusinessError("فك التخصيص للمدير أو المحاسب")
        id = int(path.split("/")[3])
        amount = money(payload.get("amount", 0))
        release(c, id, amount, payload.get("date"), payload.get("reason", ""), uid)
        return {"id": id, "remaining": allocation_amount(c, id)}
    if path in ("/api/aging", "/print/aging") and method == "GET":
        result = aging(
            c,
            query.get("asof")
            or datetime.now(timezone(timedelta(hours=3))).date().isoformat(),
        )
        if path.startswith("/print"):
            from .documents import aging_document

            return aging_document(result)
        return result
    return None
