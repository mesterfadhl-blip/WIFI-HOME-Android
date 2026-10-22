"""Purchase orders, physical receiving, invoice matching and supplier returns."""

from decimal import Decimal
from .domain import BusinessError, audit, journal, money
from .operations import (
    open_date,
    quantity,
    purchase_data,
    purchase_save,
    supplier_journal,
)
from . import warehouses

SCHEMA = """
CREATE TABLE IF NOT EXISTS purchase_orders(id INTEGER PRIMARY KEY,number TEXT UNIQUE,supplier_id INTEGER NOT NULL REFERENCES suppliers(id),date TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('draft','approved','cancelled')),note TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS order_lines(id INTEGER PRIMARY KEY,order_id INTEGER NOT NULL REFERENCES purchase_orders(id),product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,qty INTEGER NOT NULL,cost INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS goods_receipts(id INTEGER PRIMARY KEY,number TEXT UNIQUE,order_id INTEGER NOT NULL REFERENCES purchase_orders(id),date TEXT NOT NULL,warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),status TEXT NOT NULL CHECK(status IN ('posted','cancelled')),total INTEGER NOT NULL,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS goods_receipt_lines(id INTEGER PRIMARY KEY,receipt_id INTEGER NOT NULL REFERENCES goods_receipts(id),order_line_id INTEGER NOT NULL REFERENCES order_lines(id),product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,qty INTEGER NOT NULL,cost INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS supplier_returns(id INTEGER PRIMARY KEY,number TEXT UNIQUE,purchase_id INTEGER NOT NULL REFERENCES purchases(id),date TEXT NOT NULL,warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),status TEXT NOT NULL CHECK(status IN ('posted','cancelled')),total INTEGER NOT NULL,stock_cost INTEGER NOT NULL,reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS supplier_return_lines(id INTEGER PRIMARY KEY,return_id INTEGER NOT NULL REFERENCES supplier_returns(id),purchase_line_id INTEGER NOT NULL REFERENCES purchase_lines(id),product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,qty INTEGER NOT NULL,amount INTEGER NOT NULL,stock_cost INTEGER NOT NULL);
"""


def migrate(c):
    c.executescript(SCHEMA)
    if "receipt_id" not in {
        r["name"] for r in c.execute("PRAGMA table_info(purchases)")
    }:
        c.execute(
            "ALTER TABLE purchases ADD COLUMN receipt_id INTEGER REFERENCES goods_receipts(id)"
        )
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS purchase_receipt_unique ON purchases(receipt_id) WHERE receipt_id IS NOT NULL AND status!='cancelled'"
    )


def record(c, table, id):
    row = c.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
    if not row:
        raise BusinessError("المستند غير موجود")
    return dict(row)


def order(c, id):
    data = record(c, "purchase_orders", id)
    data["supplier"] = c.execute(
        "SELECT name FROM suppliers WHERE id=?", (data["supplier_id"],)
    ).fetchone()[0]
    data["lines"] = [
        dict(r) for r in c.execute("SELECT * FROM order_lines WHERE order_id=?", (id,))
    ]
    for line in data["lines"]:
        line["received"] = c.execute(
            "SELECT coalesce(sum(l.qty),0) FROM goods_receipt_lines l JOIN goods_receipts r ON r.id=l.receipt_id WHERE r.status='posted' AND l.order_line_id=?",
            (line["id"],),
        ).fetchone()[0]
        line["remaining"] = line["qty"] - line["received"]
    data["total"] = sum(l["qty"] * l["cost"] for l in data["lines"])
    return data


def create_order(c, data, uid):
    day = open_date(c, data.get("date"))
    if not c.execute(
        "SELECT 1 FROM suppliers WHERE id=?", (data.get("supplier_id"),)
    ).fetchone():
        raise BusinessError("اختر المورد")
    rows = []
    for line in data.get("lines", []):
        p = c.execute(
            "SELECT * FROM products WHERE id=? AND service=0", (line.get("product_id"),)
        ).fetchone()
        if not p:
            raise BusinessError("اختر صنفاً مخزنياً")
        rows.append(
            (p["id"], p["name"], quantity(line.get("qty")), money(line.get("cost")))
        )
    if not rows:
        raise BusinessError("أضف بنود أمر الشراء")
    id = c.execute(
        "INSERT INTO purchase_orders(supplier_id,date,status,note) VALUES(?,?,'draft',?)",
        (data["supplier_id"], day, str(data.get("note", ""))[:2000]),
    ).lastrowid
    c.execute("UPDATE purchase_orders SET number=? WHERE id=?", (f"PO-{id:06}", id))
    c.executemany(
        "INSERT INTO order_lines(order_id,product_id,name,qty,cost) VALUES(?,?,?,?,?)",
        [(id, *r) for r in rows],
    )
    audit(c, uid, "إنشاء أمر شراء", str(id))
    return order(c, id)


def receive(c, id, data, uid):
    po = order(c, id)
    day = open_date(c, data.get("date"))
    if po["status"] != "approved" or day < po["date"]:
        raise BusinessError("الاستلام يتطلب أمر شراء معتمداً وتاريخاً لا يسبقه")
    wid = warehouses.validate(c, data.get("warehouse_id"))
    selected = []
    seen = set()
    byid = {l["id"]: l for l in po["lines"]}
    for item in data.get("lines", []):
        line = byid.get(item.get("order_line_id"))
        qty = quantity(item.get("qty"))
        if not line or line["id"] in seen or qty > line["remaining"]:
            raise BusinessError("بند مكرر أو كمية تتجاوز المتبقي في الأمر")
        seen.add(line["id"])
        selected.append((line, qty))
    if not selected:
        raise BusinessError("أدخل كميات الاستلام")
    total = sum(l["cost"] * q for l, q in selected)
    rid = c.execute(
        "INSERT INTO goods_receipts(order_id,date,warehouse_id,status,total,note) VALUES(?,?,?,'posted',?,?)",
        (id, day, wid, total, str(data.get("note", ""))[:2000]),
    ).lastrowid
    ref = f"GR-{rid:06}"
    c.execute("UPDATE goods_receipts SET number=? WHERE id=?", (ref, rid))
    for line, qty in selected:
        c.execute(
            "INSERT INTO goods_receipt_lines(receipt_id,order_line_id,product_id,name,qty,cost) VALUES(?,?,?,?,?,?)",
            (rid, line["id"], line["product_id"], line["name"], qty, line["cost"]),
        )
        warehouses.change(c, line["product_id"], qty, qty * line["cost"], ref, day, wid)
    journal(
        c,
        ref,
        day,
        [("المخزون", None, total, 0), ("بضاعة مستلمة غير مفوترة", None, 0, total)],
    )
    audit(c, uid, "استلام بضاعة من أمر شراء", ref)
    return receipt(c, rid)


def receipt(c, id):
    data = record(c, "goods_receipts", id)
    po = order(c, data["order_id"])
    data.update(
        supplier_id=po["supplier_id"], supplier=po["supplier"], order=po["number"]
    )
    data["lines"] = [
        dict(r)
        for r in c.execute(
            "SELECT * FROM goods_receipt_lines WHERE receipt_id=?", (id,)
        )
    ]
    inv = c.execute(
        "SELECT id,number,status FROM purchases WHERE receipt_id=? AND status!='cancelled'",
        (id,),
    ).fetchone()
    data["invoice"] = dict(inv) if inv else None
    return data


def invoice_receipt(c, id, data, uid):
    gr = receipt(c, id)
    day = open_date(c, data.get("date"))
    if gr["status"] != "posted" or gr["invoice"] or day < gr["date"]:
        raise BusinessError("الاستلام ملغى أو مرتبط بفاتورة أو تاريخ الفوترة يسبقه")
    inv = purchase_save(
        c,
        {
            "supplier_id": gr["supplier_id"],
            "date": day,
            "warehouse_id": gr["warehouse_id"],
            "paid": data.get("paid", 0),
            "note": "مطابقة استلام " + gr["number"],
            "lines": [
                {
                    "product_id": l["product_id"],
                    "qty": l["qty"],
                    "cost": str(Decimal(l["cost"]) / 100),
                }
                for l in gr["lines"]
            ],
        },
        uid,
    )
    c.execute("UPDATE purchases SET receipt_id=? WHERE id=?", (id, inv["id"]))
    audit(c, uid, "ربط استلام بفاتورة مورد", inv["number"], gr["number"])
    return purchase_data(c, inv["id"])


def cancel_receipt(c, id, data, uid):
    gr = receipt(c, id)
    reason = str(data.get("reason", "")).strip()
    open_date(c, gr["date"])
    if gr["status"] != "posted" or gr["invoice"] or not reason:
        raise BusinessError("الاستلام ملغى أو مفوتر أو سبب العكس مفقود")
    for l in gr["lines"]:
        last = c.execute(
            "SELECT document FROM movements WHERE product_id=? AND warehouse_id=? ORDER BY date DESC,id DESC LIMIT 1",
            (l["product_id"], gr["warehouse_id"]),
        ).fetchone()
        if not last or last[0] != gr["number"]:
            raise BusinessError("توجد حركة لاحقة؛ لا يمكن عكس الاستلام")
    for l in gr["lines"]:
        warehouses.change(
            c,
            l["product_id"],
            -l["qty"],
            -l["qty"] * l["cost"],
            gr["number"] + "-REV",
            gr["date"],
            gr["warehouse_id"],
        )
    journal(
        c,
        gr["number"] + "-REV",
        gr["date"],
        [
            ("بضاعة مستلمة غير مفوترة", None, gr["total"], 0),
            ("المخزون", None, 0, gr["total"]),
        ],
    )
    c.execute("UPDATE goods_receipts SET status='cancelled' WHERE id=?", (id,))
    audit(c, uid, "عكس استلام بضاعة", gr["number"], reason)
    return receipt(c, id)


def validate_matched(c, inv):
    if not inv.get("receipt_id"):
        return
    gr = receipt(c, inv["receipt_id"])
    expected = sorted((l["product_id"], l["qty"], l["cost"]) for l in gr["lines"])
    actual = sorted((l["product_id"], l["qty"], l["cost"]) for l in inv["lines"])
    if (
        gr["status"] != "posted"
        or actual != expected
        or gr["supplier_id"] != inv["supplier_id"]
        or gr["warehouse_id"] != inv["warehouse_id"]
        or inv["date"] < gr["date"]
    ):
        raise BusinessError(
            "فاتورة الاستلام يجب أن تطابق المورد والمستودع والبنود والتكلفة؛ لا يمكن احتساب المخزون مرتين"
        )


def supplier_return(c, id):
    data = record(c, "supplier_returns", id)
    p = purchase_data(c, data["purchase_id"])
    data.update(supplier=p["supplier"], purchase=p["number"])
    data["lines"] = [
        dict(r)
        for r in c.execute(
            "SELECT * FROM supplier_return_lines WHERE return_id=?", (id,)
        )
    ]
    return data


def create_return(c, data, uid):
    p = purchase_data(c, data.get("purchase_id"))
    day = open_date(c, data.get("date"))
    reason = str(data.get("reason", "")).strip()
    if p["status"] != "posted" or day < p["date"] or not reason:
        raise BusinessError("اختر شراء مرحلاً وتاريخاً مناسباً وسبب المرتجع")
    wid = warehouses.validate(c, data.get("warehouse_id") or p["warehouse_id"])
    byid = {l["id"]: l for l in p["lines"]}
    seen = set()
    rows = []
    total = 0
    cost = 0
    for item in data.get("lines", []):
        l = byid.get(item.get("purchase_line_id"))
        q = quantity(item.get("qty"))
        if not l or l["id"] in seen:
            raise BusinessError("بند المرتجع غير صحيح أو مكرر")
        seen.add(l["id"])
        returned = c.execute(
            "SELECT coalesce(sum(l.qty),0) FROM supplier_return_lines l JOIN supplier_returns r ON r.id=l.return_id WHERE l.purchase_line_id=? AND r.status='posted'",
            (l["id"],),
        ).fetchone()[0]
        if q > l["qty"] - returned:
            raise BusinessError("المرتجع يتجاوز الكمية المشتراة المتبقية")
        # Issue each selected product once, so duplicated purchase lines cannot
        # independently consume the same value pool.
        rows.append({"line": l, "qty": q})
        total += q * l["cost"]
    if not rows:
        raise BusinessError("أضف بنود المرتجع")
    groups = {}
    for r in rows:
        groups[r["line"]["product_id"]] = (
            groups.get(r["line"]["product_id"], 0) + r["qty"]
        )
    costs = {pid: warehouses.cost(c, pid, q, wid) for pid, q in groups.items()}
    from .operations import split_amount

    for pid, amount in costs.items():
        group = [r for r in rows if r["line"]["product_id"] == pid]
        for r, v in zip(group, split_amount(amount, [r["qty"] for r in group])):
            r["stock_cost"] = v
    cost = sum(costs.values())
    id = c.execute(
        "INSERT INTO supplier_returns(purchase_id,date,warehouse_id,status,total,stock_cost,reason) VALUES(?,?,?,'posted',?,?,?)",
        (p["id"], day, wid, total, cost, reason),
    ).lastrowid
    ref = f"PR-{id:06}"
    c.execute("UPDATE supplier_returns SET number=? WHERE id=?", (ref, id))
    for r in rows:
        l = r["line"]
        c.execute(
            "INSERT INTO supplier_return_lines(return_id,purchase_line_id,product_id,name,qty,amount,stock_cost) VALUES(?,?,?,?,?,?,?)",
            (
                id,
                l["id"],
                l["product_id"],
                l["name"],
                r["qty"],
                r["qty"] * l["cost"],
                r["stock_cost"],
            ),
        )
    for pid, q in groups.items():
        warehouses.change(c, pid, -q, -costs[pid], ref, day, wid)
    variance = cost - total
    entries = [("الموردون", total, 0), ("المخزون", 0, cost)]
    if variance:
        entries.append(
            ("فروق تكلفة مردودات المشتريات", max(variance, 0), max(-variance, 0))
        )
    supplier_journal(c, ref, day, p["supplier_id"], entries)
    audit(c, uid, "مرتجع مشتريات إلى المورد", ref, reason)
    return supplier_return(c, id)


def cancel_supplier_return(c, id, data, uid):
    r = supplier_return(c, id)
    reason = str(data.get("reason", "")).strip()
    open_date(c, r["date"])
    if r["status"] != "posted" or not reason:
        raise BusinessError("اختر مرتجعاً مرحلاً وأدخل سبب العكس")
    for l in r["lines"]:
        last = c.execute(
            "SELECT document FROM movements WHERE product_id=? AND warehouse_id=? ORDER BY date DESC,id DESC LIMIT 1",
            (l["product_id"], r["warehouse_id"]),
        ).fetchone()
        if not last or last[0] != r["number"]:
            raise BusinessError("توجد حركة لاحقة؛ لا يمكن عكس المرتجع")
    for l in r["lines"]:
        warehouses.change(
            c,
            l["product_id"],
            l["qty"],
            l["stock_cost"],
            r["number"] + "-REV",
            r["date"],
            r["warehouse_id"],
        )
    entries = c.execute(
        "SELECT * FROM journal WHERE document=?", (r["number"],)
    ).fetchall()
    p = purchase_data(c, r["purchase_id"])
    supplier_journal(
        c,
        r["number"] + "-REV",
        r["date"],
        p["supplier_id"],
        [(l["account"], l["credit"], l["debit"]) for l in entries],
    )
    c.execute("UPDATE supplier_returns SET status='cancelled' WHERE id=?", (id,))
    audit(c, uid, "عكس مرتجع مشتريات", r["number"], reason)
    return supplier_return(c, id)


def handle(c, path, method, data, env, uid, role):
    prefixes = (
        "/api/purchase-orders",
        "/api/goods-receipts",
        "/api/supplier-returns",
        "/print/purchase-orders/",
        "/print/goods-receipts/",
        "/print/supplier-returns/",
    )
    if not path.startswith(prefixes):
        return None
    if role not in ("admin", "accountant"):
        raise BusinessError("هذه العملية للمدير أو المحاسب")
    parts = path.strip("/").split("/")
    resource = parts[1]
    if parts[0] == "print":
        return document(c, resource, int(parts[2]))
    table = {
        "purchase-orders": "purchase_orders",
        "goods-receipts": "goods_receipts",
        "supplier-returns": "supplier_returns",
    }[resource]
    getter = {
        "purchase-orders": order,
        "goods-receipts": receipt,
        "supplier-returns": supplier_return,
    }[resource]
    if len(parts) == 2:
        if method == "GET":
            return [
                getter(c, r[0])
                for r in c.execute(
                    f"SELECT id FROM {table} ORDER BY id DESC"
                ).fetchall()
            ]
        if method == "POST" and resource == "purchase-orders":
            return create_order(c, data, uid)
        if method == "POST" and resource == "supplier-returns":
            return create_return(c, data, uid)
    if len(parts) == 3 and method == "GET":
        return getter(c, int(parts[2]))
    if len(parts) == 4 and method == "POST":
        id = int(parts[2])
        action = parts[3]
        if resource == "purchase-orders":
            po = order(c, id)
            if action == "approve":
                open_date(c, po["date"])
                if po["status"] != "draft":
                    raise BusinessError("الأمر ليس مسودة")
                c.execute(
                    "UPDATE purchase_orders SET status='approved',version=version+1 WHERE id=?",
                    (id,),
                )
                audit(c, uid, "اعتماد أمر شراء", po["number"])
                return order(c, id)
            if action == "receive":
                return receive(c, id, data, uid)
            if action == "cancel":
                if (
                    po["status"] == "cancelled"
                    or any(l["received"] for l in po["lines"])
                    or not str(data.get("reason", "")).strip()
                ):
                    raise BusinessError("لا يمكن إلغاء أمر مستلم أو دون سبب")
                c.execute(
                    "UPDATE purchase_orders SET status='cancelled',version=version+1 WHERE id=?",
                    (id,),
                )
                audit(c, uid, "إلغاء أمر شراء", po["number"], data["reason"])
                return order(c, id)
        if resource == "goods-receipts" and action == "invoice":
            return invoice_receipt(c, id, data, uid)
        if resource == "goods-receipts" and action == "cancel":
            return cancel_receipt(c, id, data, uid)
        if resource == "supplier-returns" and action == "cancel":
            return cancel_supplier_return(c, id, data, uid)
    raise BusinessError("طلب دورة المشتريات غير صالح")


def document(c, resource, id):
    from .documents import document as page, text, money as fmt

    title, getter, column = {
        "purchase-orders": ("أمر شراء", order, "cost"),
        "goods-receipts": ("محضر استلام بضاعة", receipt, "cost"),
        "supplier-returns": ("إشعار مدين للمورد", supplier_return, "amount"),
    }[resource]
    s = getter(c, id)
    rows = "".join(
        f'<tr><td>{text(l["name"])}</td><td>{l["qty"]}</td><td class="num">{fmt(l[column]*l["qty"] if column=="cost" else l[column])}</td></tr>'
        for l in s["lines"]
    )
    return page(
        title,
        s["number"],
        f'<div class="meta">المورد: {text(s["supplier"])} · التاريخ: {text(s["date"])} · الحالة: {text(s["status"])}</div><table><thead><tr><th>الصنف</th><th>الكمية</th><th>القيمة بالريال اليمني</th></tr></thead><tbody>{rows}</tbody><tfoot><tr><td colspan="2">الإجمالي</td><td>{fmt(s["total"])}</td></tr></tfoot></table>',
    )
