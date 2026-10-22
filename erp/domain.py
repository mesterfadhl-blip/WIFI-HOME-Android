"""Shared validation and journal primitives."""

import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class BusinessError(Exception):
    pass


def money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:
            raise ValueError()
        return int((n * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (ValueError, InvalidOperation):
        raise BusinessError("المبلغ غير صحيح")


def date(value):
    try:
        return dt.date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise BusinessError("التاريخ غير صحيح")


def audit(c, user, action, document, detail=""):
    c.execute(
        "INSERT INTO audit(at,user_id,action,document,detail) VALUES(?,?,?,?,?)",
        (dt.datetime.now(dt.timezone.utc).isoformat(), user, action, document, detail),
    )


def journal(c, document, day, rows):
    closed = c.execute("SELECT max(through) FROM periods").fetchone()[0]
    if closed and day <= closed:
        raise BusinessError("الفترة مقفلة محاسبياً")
    if sum(r[2] - r[3] for r in rows) != 0:
        raise BusinessError("القيد غير متوازن")
    c.executemany(
        "INSERT INTO journal(document,date,account,customer_id,debit,credit) VALUES(?,?,?,?,?,?)",
        [(document, day, *r) for r in rows],
    )


def invoice_data(c, id):
    row = c.execute(
        "SELECT i.*,c.name customer,c.phone,c.address FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.id=?",
        (id,),
    ).fetchone()
    if not row:
        raise BusinessError("الفاتورة غير موجودة")
    data = dict(row)
    data["lines"] = [
        dict(r) for r in c.execute("SELECT * FROM lines WHERE invoice_id=?", (id,))
    ]
    for line in data["lines"]:
        returned = c.execute(
            "SELECT coalesce(sum(l.qty),0) FROM return_lines l JOIN returns r ON r.id=l.return_id WHERE r.status='posted' AND l.sale_line_id=?",
            (line["id"],),
        ).fetchone()[0]
        line["returned_qty"] = returned
        line["returnable_qty"] = line["qty"] - returned
    return data
