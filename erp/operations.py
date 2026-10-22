"""Transactional purchasing, stock valuation, supplier settlement and credit notes."""

import json
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import parse_qs
from .domain import BusinessError, audit, date, journal, money, invoice_data

SCHEMA = """
CREATE TABLE IF NOT EXISTS operation_requests(key TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY,number TEXT UNIQUE,supplier_id INTEGER NOT NULL REFERENCES suppliers(id),date TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('draft','posted','cancelled')),total INTEGER NOT NULL,paid INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS purchase_lines(id INTEGER PRIMARY KEY,purchase_id INTEGER NOT NULL REFERENCES purchases(id),product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,qty INTEGER NOT NULL,cost INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,number TEXT UNIQUE,supplier_id INTEGER NOT NULL REFERENCES suppliers(id),date TEXT NOT NULL,amount INTEGER NOT NULL,note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS returns(id INTEGER PRIMARY KEY,number TEXT UNIQUE,invoice_id INTEGER NOT NULL REFERENCES invoices(id),date TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('posted','cancelled')),total INTEGER NOT NULL,cost INTEGER NOT NULL,refund INTEGER NOT NULL,reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS return_lines(id INTEGER PRIMARY KEY,return_id INTEGER NOT NULL REFERENCES returns(id),sale_line_id INTEGER NOT NULL REFERENCES lines(id),product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,qty INTEGER NOT NULL,net INTEGER NOT NULL,cost INTEGER NOT NULL,service INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY,number TEXT UNIQUE,date TEXT NOT NULL,amount INTEGER NOT NULL,category TEXT NOT NULL,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS funding(id INTEGER PRIMARY KEY,number TEXT UNIQUE,date TEXT NOT NULL,amount INTEGER NOT NULL,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS periods(id INTEGER PRIMARY KEY,through TEXT NOT NULL,reason TEXT NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id));
"""


def rounded(value):
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def split_amount(total, weights):
    """Largest-remainder allocation: result always sums to the document amount."""
    denominator = sum(weights)
    if not denominator:
        return [0] * len(weights)
    result = [total * w // denominator for w in weights]
    ranked = sorted(
        range(len(weights)), key=lambda i: -(total * weights[i] % denominator)
    )
    for i in ranked[: total - sum(result)]:
        result[i] += 1
    return result


def migrate(c):
    c.executescript(SCHEMA)
    cols = {r["name"] for r in c.execute("PRAGMA table_info(products)")}
    if "stock_value" not in cols:
        c.execute(
            "ALTER TABLE products ADD COLUMN stock_value INTEGER NOT NULL DEFAULT 0"
        )
        c.execute("UPDATE products SET stock_value=qty*cost WHERE service=0")
    cols = {r["name"] for r in c.execute("PRAGMA table_info(lines)")}
    if "cost_total" not in cols:
        c.execute("ALTER TABLE lines ADD COLUMN cost_total INTEGER NOT NULL DEFAULT 0")
        c.execute("ALTER TABLE lines ADD COLUMN net_total INTEGER NOT NULL DEFAULT 0")
        for inv in c.execute("SELECT id,total FROM invoices").fetchall():
            rows = c.execute(
                "SELECT * FROM lines WHERE invoice_id=? ORDER BY id", (inv["id"],)
            ).fetchall()
            shares = split_amount(inv["total"], [r["qty"] * r["price"] for r in rows])
            for r, net in zip(rows, shares):
                c.execute(
                    "UPDATE lines SET cost_total=?,net_total=? WHERE id=?",
                    (r["qty"] * r["cost"], net, r["id"]),
                )
    cols = {r["name"] for r in c.execute("PRAGMA table_info(journal)")}
    if "supplier_id" not in cols:
        c.execute(
            "ALTER TABLE journal ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id)"
        )
    c.executescript(
        """
    CREATE INDEX IF NOT EXISTS journal_customer_date ON journal(customer_id,date,account);
    CREATE INDEX IF NOT EXISTS journal_supplier_date ON journal(supplier_id,date,account);
    CREATE INDEX IF NOT EXISTS journal_document ON journal(document);
    CREATE INDEX IF NOT EXISTS movements_product_date ON movements(product_id,date,id);
    CREATE INDEX IF NOT EXISTS lines_invoice ON lines(invoice_id);
    CREATE INDEX IF NOT EXISTS invoices_customer_status ON invoices(customer_id,status,date);
    CREATE INDEX IF NOT EXISTS returns_invoice_status ON returns(invoice_id,status);
    CREATE INDEX IF NOT EXISTS return_lines_original ON return_lines(sale_line_id);
    PRAGMA user_version=2;
    """
    )


def quantity(value):
    try:
        q = int(value)
        if q <= 0 or Decimal(str(value)) != Decimal(q):
            raise ValueError()
        return q
    except (ValueError, TypeError, ArithmeticError):
        raise BusinessError("الكمية يجب أن تكون عدداً صحيحاً موجباً")


def open_date(c, value):
    day = date(value)
    closed = c.execute("SELECT max(through) FROM periods").fetchone()[0]
    if closed and day <= closed:
        raise BusinessError("الفترة مقفلة محاسبياً حتى " + closed)
    return day


def chronology(c, pid, day):
    last = c.execute(
        "SELECT max(date) FROM movements WHERE product_id=?", (pid,)
    ).fetchone()[0]
    if last and day < last:
        raise BusinessError(
            "تاريخ حركة المخزون يسبق حركة لاحقة للصنف؛ لا يمكن تغيير تقييم المخزون بأثر رجعي"
        )


def change_stock(c, pid, qty, value, ref, day, warehouse_id=1):
    from .warehouses import change

    return change(c, pid, qty, value, ref, day, warehouse_id)


def issue_cost(c, pid, qty, warehouse_id=1):
    from .warehouses import cost

    return cost(c, pid, qty, warehouse_id)


def purchase_data(c, id):
    r = c.execute(
        "SELECT p.*,s.name supplier,s.phone,s.address FROM purchases p JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?",
        (id,),
    ).fetchone()
    if not r:
        raise BusinessError("فاتورة الشراء غير موجودة")
    d = dict(r)
    d["lines"] = [
        dict(r)
        for r in c.execute("SELECT * FROM purchase_lines WHERE purchase_id=?", (id,))
    ]
    return d


def purchase_save(c, data, uid, id=None):
    old = purchase_data(c, id) if id else None
    if old and (old["status"] != "draft" or data.get("version") != old["version"]):
        raise BusinessError("المستند مرحل أو تغيّر؛ حدّث الصفحة")
    if not c.execute(
        "SELECT 1 FROM suppliers WHERE id=?", (data.get("supplier_id"),)
    ).fetchone():
        raise BusinessError("اختر المورد")
    day = open_date(c, data.get("date"))
    from .warehouses import validate

    warehouse_id = validate(
        c, data.get("warehouse_id") or (old["warehouse_id"] if old else 1)
    )
    paid = money(data.get("paid", 0))
    lines = []
    for l in data.get("lines", []):
        p = c.execute(
            "SELECT * FROM products WHERE id=?", (l.get("product_id"),)
        ).fetchone()
        if not p or p["service"]:
            raise BusinessError("اختر صنفاً مخزنياً صالحاً")
        lines.append(
            (p["id"], p["name"], quantity(l.get("qty")), money(l.get("cost", 0)))
        )
    if not lines:
        raise BusinessError("أضف بند شراء")
    total = sum(q * cost for _, _, q, cost in lines)
    if paid > total:
        raise BusinessError("المسدد يتجاوز قيمة الشراء")
    values = (data["supplier_id"], day, total, paid, str(data.get("note", ""))[:2000])
    if id:
        c.execute(
            "UPDATE purchases SET supplier_id=?,date=?,total=?,paid=?,note=?,version=version+1 WHERE id=?",
            (*values, id),
        )
        c.execute("DELETE FROM purchase_lines WHERE purchase_id=?", (id,))
    else:
        id = c.execute(
            "INSERT INTO purchases(supplier_id,date,total,paid,note,status) VALUES(?,?,?,?,?,'draft')",
            values,
        ).lastrowid
        c.execute("UPDATE purchases SET number=? WHERE id=?", (f"PI-{id:06}", id))
    c.executemany(
        "INSERT INTO purchase_lines(purchase_id,product_id,name,qty,cost) VALUES(?,?,?,?,?)",
        [(id, *l) for l in lines],
    )
    c.execute("UPDATE purchases SET warehouse_id=? WHERE id=?", (warehouse_id, id))
    audit(c, uid, "حفظ مسودة شراء", str(id))
    return purchase_data(c, id)


def supplier_journal(c, ref, day, sid, rows):
    journal(c, ref, day, [(a, None, d, cr) for a, d, cr in rows])
    c.execute(
        "UPDATE journal SET supplier_id=? WHERE document=? AND account='الموردون'",
        (sid, ref),
    )


def post_purchase(c, id, uid):
    s = purchase_data(c, id)
    open_date(c, s["date"])
    if s["status"] != "draft":
        raise BusinessError("المستند ليس مسودة")
    for l in s["lines"]:
        change_stock(
            c,
            l["product_id"],
            l["qty"],
            l["qty"] * l["cost"],
            s["number"],
            s["date"],
            s["warehouse_id"],
        )
    rows = [("المخزون", s["total"], 0), ("الموردون", 0, s["total"])]
    if s["paid"]:
        rows += [("الموردون", s["paid"], 0), ("الصندوق", 0, s["paid"])]
    supplier_journal(c, s["number"], s["date"], s["supplier_id"], rows)
    c.execute("UPDATE purchases SET status='posted' WHERE id=?", (id,))
    audit(c, uid, "ترحيل شراء واستلام مخزون", s["number"])
    return purchase_data(c, id)


def cancel_purchase(c, id, uid, reason):
    s = purchase_data(c, id)
    open_date(c, s["date"])
    if s["status"] != "posted" or not str(reason).strip():
        raise BusinessError("اختر فاتورة مرحلة واكتب سبب الإلغاء")
    for l in s["lines"]:
        last = c.execute(
            "SELECT document FROM movements WHERE product_id=? AND warehouse_id=? ORDER BY date DESC,id DESC LIMIT 1",
            (l["product_id"], s["warehouse_id"]),
        ).fetchone()
        if not last or last["document"] != s["number"]:
            raise BusinessError(
                "تحرك الصنف بعد الاستلام؛ إلغاء الشراء يتطلب معالجة الحركات اللاحقة أولاً"
            )
    ref = s["number"] + "-REV"
    for l in s["lines"]:
        change_stock(
            c,
            l["product_id"],
            -l["qty"],
            -l["qty"] * l["cost"],
            ref,
            s["date"],
            s["warehouse_id"],
        )
    rows = c.execute(
        "SELECT * FROM journal WHERE document=?", (s["number"],)
    ).fetchall()
    supplier_journal(
        c,
        ref,
        s["date"],
        s["supplier_id"],
        [(r["account"], r["credit"], r["debit"]) for r in rows],
    )
    c.execute("UPDATE purchases SET status='cancelled' WHERE id=?", (id,))
    audit(c, uid, "إلغاء شراء", s["number"], reason)
    return purchase_data(c, id)


def return_data(c, id):
    r = c.execute(
        "SELECT r.*,i.number invoice,c.name customer,c.id customer_id,c.phone,c.address FROM returns r JOIN invoices i ON i.id=r.invoice_id JOIN customers c ON c.id=i.customer_id WHERE r.id=?",
        (id,),
    ).fetchone()
    if not r:
        raise BusinessError("إشعار المرتجع غير موجود")
    d = dict(r)
    d["lines"] = [
        dict(x)
        for x in c.execute("SELECT * FROM return_lines WHERE return_id=?", (id,))
    ]
    return d


def create_return(c, data, uid):
    s = invoice_data(c, data.get("invoice_id"))
    day = open_date(c, data.get("date"))
    reason = str(data.get("reason", "")).strip()
    if s["status"] != "posted" or not reason:
        raise BusinessError("اختر فاتورة مرحلة واكتب سبب المرتجع")
    if day < s["date"]:
        raise BusinessError("تاريخ المرتجع يسبق الفاتورة")
    selected = set()
    rows = []
    for item in data.get("lines", []):
        lid = int(item.get("sale_line_id", 0))
        q = quantity(item.get("qty"))
        if lid in selected:
            raise BusinessError("البند مكرر في المرتجع")
        selected.add(lid)
        l = next((x for x in s["lines"] if x["id"] == lid), None)
        if not l:
            raise BusinessError("بند المرتجع لا يتبع الفاتورة")
        prior = c.execute(
            "SELECT coalesce(sum(l.qty),0) qty,coalesce(sum(l.net),0) net,coalesce(sum(l.cost),0) cost FROM return_lines l JOIN returns r ON r.id=l.return_id WHERE r.status='posted' AND l.sale_line_id=?",
            (lid,),
        ).fetchone()
        if q + prior["qty"] > l["qty"]:
            raise BusinessError("المرتجع يتجاوز الكمية المباعة بعد المرتجعات السابقة")
        net = (
            rounded(Decimal(l["net_total"]) * (q + prior["qty"]) / l["qty"])
            - prior["net"]
        )
        cost = (
            rounded(Decimal(l["cost_total"]) * (q + prior["qty"]) / l["qty"])
            - prior["cost"]
        )
        rows.append((lid, l["product_id"], l["name"], q, net, cost, l["service"]))
    if not rows:
        raise BusinessError("حدد كمية مرتجعة واحدة على الأقل")
    total = sum(r[4] for r in rows)
    cost = sum(r[5] for r in rows)
    refund = money(data.get("refund", 0))
    if refund > total:
        raise BusinessError("المردود النقدي يتجاوز قيمة المرتجع")
    id = c.execute(
        "INSERT INTO returns(invoice_id,date,status,total,cost,refund,reason) VALUES(?,?,'posted',?,?,?,?)",
        (s["id"], day, total, cost, refund, reason),
    ).lastrowid
    from .warehouses import validate

    wid = validate(c, data.get("warehouse_id") or s["warehouse_id"])
    c.execute("UPDATE returns SET warehouse_id=? WHERE id=?", (wid, id))
    ref = f"CN-{id:06}"
    c.execute("UPDATE returns SET number=? WHERE id=?", (ref, id))
    c.executemany(
        "INSERT INTO return_lines(return_id,sale_line_id,product_id,name,qty,net,cost,service) VALUES(?,?,?,?,?,?,?,?)",
        [(id, *r) for r in rows],
    )
    entries = [
        ("مردودات المبيعات", None, total, 0),
        ("العملاء", s["customer_id"], 0, total),
    ]
    physical = 0
    service = 0
    for _, pid, _, q, _, v, is_service in rows:
        if is_service:
            service += v
        else:
            change_stock(c, pid, q, v, ref, day, wid)
            physical += v
    if physical:
        entries.append(("المخزون", None, physical, 0))
    if service:
        entries.append(("موردو خدمات", None, service, 0))
    if cost:
        entries.append(("تكلفة المبيعات", None, 0, cost))
    if refund:
        entries += [
            ("العملاء", s["customer_id"], refund, 0),
            ("الصندوق", None, 0, refund),
        ]
    journal(c, ref, day, entries)
    from .settlements import trim_allocations

    trim_allocations(c, s["id"], day, uid, reason="تخفيض المتبقي بسبب " + ref)
    audit(c, uid, "إشعار دائن / مرتجع مبيعات", ref, reason)
    return return_data(c, id)


def cancel_return(c, id, uid, reason):
    s = return_data(c, id)
    open_date(c, s["date"])
    if s["status"] != "posted" or not str(reason).strip():
        raise BusinessError("المستند ملغى أو السبب غير موجود")
    # Reversing a return after later stock movement changes valuations: reject it.
    for l in s["lines"]:
        if not l["service"]:
            last = c.execute(
                "SELECT document FROM movements WHERE product_id=? AND warehouse_id=? ORDER BY date DESC,id DESC LIMIT 1",
                (l["product_id"], s["warehouse_id"]),
            ).fetchone()
            if not last or last["document"] != s["number"]:
                raise BusinessError("توجد حركات مخزون لاحقة؛ راجعها قبل عكس المرتجع")
    ref = s["number"] + "-REV"
    for l in s["lines"]:
        if not l["service"]:
            change_stock(
                c,
                l["product_id"],
                -l["qty"],
                -l["cost"],
                ref,
                s["date"],
                s["warehouse_id"],
            )
    rows = c.execute(
        "SELECT * FROM journal WHERE document=?", (s["number"],)
    ).fetchall()
    journal(
        c,
        ref,
        s["date"],
        [(r["account"], r["customer_id"], r["credit"], r["debit"]) for r in rows],
    )
    c.execute("UPDATE returns SET status='cancelled' WHERE id=?", (id,))
    audit(c, uid, "إلغاء مرتجع", s["number"], reason)
    return return_data(c, id)


def supplier_statement(c, sid, f, t):
    supplier = c.execute("SELECT * FROM suppliers WHERE id=?", (sid,)).fetchone()
    if not supplier:
        raise BusinessError("المورد غير موجود")
    opening = c.execute(
        "SELECT coalesce(sum(credit-debit),0) FROM journal WHERE account='الموردون' AND supplier_id=? AND date<?",
        (sid, f),
    ).fetchone()[0]
    rows = [
        dict(r)
        for r in c.execute(
            "SELECT * FROM journal WHERE account='الموردون' AND supplier_id=? AND date BETWEEN ? AND ? ORDER BY date,id",
            (sid, f, t),
        )
    ]
    return dict(supplier), opening, rows


def _handle(c, path, method, data, env, uid, role):
    if not (
        path.startswith(
            (
                "/api/purchases",
                "/api/suppliers",
                "/api/payments",
                "/api/returns",
                "/api/expenses",
                "/api/finance",
                "/api/periods",
                "/api/funding",
                "/print/purchases/",
                "/print/returns/",
                "/print/supplier",
                "/print/finance",
            )
        )
    ):
        return None
    read_credit = method == "GET" and (
        path.startswith("/api/returns/") or path.startswith("/print/returns/")
    )
    if role not in ("admin", "accountant") and not read_credit:
        raise BusinessError("هذه العملية للمدير أو المحاسب فقط")
    query = {k: v[0] for k, v in parse_qs(env.get("QUERY_STRING", "")).items()}
    if path == "/api/suppliers" and method == "POST":
        name = str(data.get("name", "")).strip()
        if not name:
            raise BusinessError("أدخل اسم المورد")
        id = c.execute(
            "INSERT INTO suppliers(name,phone,address) VALUES(?,?,?)",
            (name, str(data.get("phone", "")), str(data.get("address", ""))),
        ).lastrowid
        audit(c, uid, "إضافة مورد", str(id))
        return {"id": id}
    if path == "/api/purchases" and method == "POST":
        return purchase_save(c, data, uid)
    if path.startswith("/api/purchases/"):
        parts = path.strip("/").split("/")
        id = int(parts[2])
        if len(parts) == 3:
            if method == "GET":
                return purchase_data(c, id)
            if method == "PUT":
                return purchase_save(c, data, uid, id)
        if method == "POST" and parts[-1] == "post":
            current = purchase_data(c, id)
            if (
                data.get("version") is not None
                and data["version"] != current["version"]
            ):
                raise BusinessError("تغيّرت مسودة الشراء؛ حدّثها قبل الترحيل")
            return post_purchase(c, id, uid)
        if method == "POST" and parts[-1] == "cancel":
            return cancel_purchase(c, id, uid, data.get("reason", ""))
    if path == "/api/payments" and method == "POST":
        day = open_date(c, data.get("date"))
        amount = money(data.get("amount", 0))
        sid = data.get("supplier_id")
        if (
            not amount
            or not c.execute("SELECT 1 FROM suppliers WHERE id=?", (sid,)).fetchone()
        ):
            raise BusinessError("المبلغ أو المورد غير صحيح")
        id = c.execute(
            "INSERT INTO payments(supplier_id,date,amount,note) VALUES(?,?,?,?)",
            (sid, day, amount, str(data.get("note", ""))),
        ).lastrowid
        ref = f"PV-{id:06}"
        c.execute("UPDATE payments SET number=? WHERE id=?", (ref, id))
        supplier_journal(
            c, ref, day, sid, [("الموردون", amount, 0), ("الصندوق", 0, amount)]
        )
        audit(c, uid, "سند صرف لمورد", ref)
        return {"number": ref}
    if path == "/api/returns" and method == "POST":
        return create_return(c, data, uid)
    if path.startswith("/api/returns/"):
        parts = path.strip("/").split("/")
        id = int(parts[2])
        if method == "GET" and len(parts) == 3:
            return return_data(c, id)
        if method == "POST" and parts[-1] == "cancel":
            return cancel_return(c, id, uid, data.get("reason", ""))
    if path == "/api/expenses" and method == "POST":
        day = open_date(c, data.get("date"))
        amount = money(data.get("amount", 0))
        category = str(data.get("category", "")).strip()
        note = str(data.get("note", "")).strip()
        if not amount or not category or not note:
            raise BusinessError("أدخل مبلغاً وتصنيفاً وبياناً صحيحاً")
        id = c.execute(
            "INSERT INTO expenses(date,amount,category,note) VALUES(?,?,?,?)",
            (day, amount, category, note),
        ).lastrowid
        ref = f"EX-{id:06}"
        c.execute("UPDATE expenses SET number=? WHERE id=?", (ref, id))
        journal(
            c,
            ref,
            day,
            [("مصروفات التشغيل", None, amount, 0), ("الصندوق", None, 0, amount)],
        )
        audit(c, uid, "مصروف تشغيل", ref, note)
        return {"number": ref}
    if path == "/api/funding" and method == "POST":
        if role != "admin":
            raise BusinessError("التمويل الرأسمالي للمدير فقط")
        day = open_date(c, data.get("date"))
        amount = money(data.get("amount", 0))
        note = str(data.get("note", "")).strip()
        if not amount or not note:
            raise BusinessError("أدخل المبلغ والبيان")
        id = c.execute(
            "INSERT INTO funding(date,amount,note) VALUES(?,?,?)", (day, amount, note)
        ).lastrowid
        ref = f"CF-{id:06}"
        c.execute("UPDATE funding SET number=? WHERE id=?", (ref, id))
        journal(
            c,
            ref,
            day,
            [
                ("الصندوق", None, amount, 0),
                ("رأس المال والأرصدة الافتتاحية", None, 0, amount),
            ],
        )
        audit(c, uid, "تمويل رأس مال الصندوق", ref, note)
        return {"number": ref}
    if path == "/api/periods" and method == "POST":
        if role != "admin":
            raise BusinessError("إقفال الفترات للمدير فقط")
        through = date(data.get("through"))
        reason = str(data.get("reason", "")).strip()
        last = c.execute("SELECT max(through) FROM periods").fetchone()[0]
        if not reason or (last and through <= last):
            raise BusinessError("أدخل سبباً وتاريخ إقفال أحدث من السابق")
        c.execute(
            "INSERT INTO periods(through,reason,user_id) VALUES(?,?,?)",
            (through, reason, uid),
        )
        audit(c, uid, "إقفال فترة", through, reason)
        return {"through": through}
    if path == "/api/finance" and method == "GET":
        return finance(c, query)
    from . import documents

    if path.startswith("/print/purchases/") and method == "GET":
        return documents.purchase_document(purchase_data(c, int(path.split("/")[-1])))
    if path.startswith("/print/returns/") and method == "GET":
        return documents.return_document(return_data(c, int(path.split("/")[-1])))
    if path == "/print/supplier" and method == "GET":
        f = date(query.get("from", "1900-01-01"))
        t = date(query.get("to", "2999-12-31"))
        if f > t:
            raise BusinessError("بداية الفترة بعد نهايتها")
        supplier, opening, rows = supplier_statement(
            c, int(query.get("supplier", 0)), f, t
        )
        return documents.supplier_document(supplier, opening, rows, f, t)
    if path == "/print/finance" and method == "GET":
        return documents.finance_document(finance(c, query))
    raise BusinessError("العملية غير متاحة")


def finance(c, query):
    f = date(query.get("from", "1900-01-01"))
    t = date(query.get("to", "2999-12-31"))
    if f > t:
        raise BusinessError("بداية الفترة بعد نهايتها")
    rows = [
        dict(r)
        for r in c.execute(
            "SELECT account,sum(debit) debit,sum(credit) credit FROM journal WHERE date BETWEEN ? AND ? GROUP BY account ORDER BY account",
            (f, t),
        )
    ]
    accounts = {r["account"]: r for r in rows}

    def net(account):
        r = accounts.get(account, {})
        return r.get("debit", 0) - r.get("credit", 0)

    sales = -net("المبيعات")
    returns = net("مردودات المبيعات")
    cost = net("تكلفة المبيعات")
    expenses = net("مصروفات التشغيل")
    stock = [
        dict(r)
        for r in c.execute(
            "SELECT id,name,qty,cost,stock_value FROM products WHERE service=0 ORDER BY name"
        )
    ]
    trial = [
        dict(r)
        for r in c.execute(
            "SELECT account,sum(debit) debit,sum(credit) credit FROM journal WHERE date<=? GROUP BY account ORDER BY account",
            (t,),
        )
    ]
    return {
        "from": f,
        "to": t,
        "accounts": rows,
        "trial": trial,
        "sales": sales,
        "returns": returns,
        "net_sales": sales - returns,
        "cost": cost,
        "gross_profit": sales - returns - cost,
        "expenses": expenses,
        "net_profit": sales - returns - cost - expenses,
        "stock": stock,
        "stock_value": sum(r["stock_value"] for r in stock),
        "stock_date": "current",
        "debits": sum(r["debit"] for r in trial),
        "credits": sum(r["credit"] for r in trial),
    }


def handle(c, path, method, data, env, uid, role):
    token = data.get("request_id") if method == "POST" else None
    key = None
    if token and path in (
        "/api/returns",
        "/api/payments",
        "/api/expenses",
        "/api/funding",
    ):
        if role not in ("admin", "accountant"):
            raise BusinessError("هذه العملية للمدير أو المحاسب فقط")
        if not isinstance(token, str) or len(token) > 100:
            raise BusinessError("معرف الطلب غير صالح")
        key = f"{uid}:{path}:{token}"
        fingerprint = hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        prior = c.execute(
            "SELECT * FROM operation_requests WHERE key=?", (key,)
        ).fetchone()
        if prior:
            if prior["fingerprint"] != fingerprint:
                raise BusinessError("معرف الطلب استُخدم لمحتوى مختلف")
            return json.loads(prior["result"])
    result = _handle(c, path, method, data, env, uid, role)
    if key and result is not None:
        c.execute(
            "INSERT INTO operation_requests VALUES(?,?,?)",
            (key, fingerprint, json.dumps(result, ensure_ascii=False)),
        )
    return result
