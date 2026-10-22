"""Per-warehouse perpetual inventory and value-preserving internal transfers."""

from decimal import Decimal
from .domain import BusinessError, audit, date

SCHEMA = """
CREATE TABLE IF NOT EXISTS warehouses(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS warehouse_stock(warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),product_id INTEGER NOT NULL REFERENCES products(id),qty INTEGER NOT NULL,value INTEGER NOT NULL,PRIMARY KEY(warehouse_id,product_id));
CREATE TABLE IF NOT EXISTS transfers(id INTEGER PRIMARY KEY,number TEXT UNIQUE,date TEXT NOT NULL,source_id INTEGER NOT NULL REFERENCES warehouses(id),target_id INTEGER NOT NULL REFERENCES warehouses(id),status TEXT NOT NULL CHECK(status IN ('draft','posted','cancelled')),note TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS transfer_lines(id INTEGER PRIMARY KEY,transfer_id INTEGER NOT NULL REFERENCES transfers(id),product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,qty INTEGER NOT NULL,cost INTEGER NOT NULL DEFAULT 0);
"""


def migrate(c):
    c.executescript(SCHEMA)
    c.execute("INSERT OR IGNORE INTO warehouses(id,name) VALUES(1,'المستودع الرئيسي')")
    for table in ("movements", "invoices", "purchases", "returns"):
        cols = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
        if "warehouse_id" not in cols:
            c.execute(
                f"ALTER TABLE {table} ADD COLUMN warehouse_id INTEGER REFERENCES warehouses(id)"
            )
        c.execute(f"UPDATE {table} SET warehouse_id=1 WHERE warehouse_id IS NULL")
    c.execute(
        "INSERT INTO warehouse_stock(warehouse_id,product_id,qty,value) SELECT 1,p.id,p.qty,p.stock_value FROM products p WHERE p.service=0 AND NOT EXISTS(SELECT 1 FROM warehouse_stock s WHERE s.product_id=p.id)"
    )
    c.executescript(
        "CREATE INDEX IF NOT EXISTS movements_warehouse ON movements(product_id,warehouse_id,date,id);"
    )


def validate(c, id):
    r = c.execute("SELECT * FROM warehouses WHERE id=? AND active=1", (id,)).fetchone()
    if not r:
        raise BusinessError("المستودع غير موجود أو غير نشط")
    return r["id"]


def stock(c, pid, wid):
    validate(c, wid)
    r = c.execute(
        "SELECT * FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
        (wid, pid),
    ).fetchone()
    return (
        dict(r) if r else {"qty": 0, "value": 0, "warehouse_id": wid, "product_id": pid}
    )


def change(c, pid, q, v, ref, day, wid=1):
    from .operations import rounded

    s = stock(c, pid, wid)
    p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p or p["service"]:
        raise BusinessError("الصنف ليس مخزنياً")
    last = c.execute(
        "SELECT max(date) FROM movements WHERE product_id=? AND warehouse_id=?",
        (pid, wid),
    ).fetchone()[0]
    if last and day < last:
        raise BusinessError(
            "توجد حركة مستودع بتاريخ لاحق؛ لا يمكن تغيير التقييم بأثر رجعي"
        )
    qty = s["qty"] + q
    value = s["value"] + v
    if qty < 0 or value < 0 or (qty == 0 and value != 0):
        raise BusinessError("الرصيد أو قيمة المخزون غير كافية: " + p["name"])
    c.execute(
        "INSERT INTO warehouse_stock VALUES(?,?,?,?) ON CONFLICT(warehouse_id,product_id) DO UPDATE SET qty=excluded.qty,value=excluded.value",
        (wid, pid, qty, value),
    )
    totalqty = p["qty"] + q
    totalvalue = p["stock_value"] + v
    if totalqty < 0 or totalvalue < 0 or (not totalqty and totalvalue):
        raise BusinessError("إجمالي تقييم الصنف غير صحيح")
    cost = rounded(Decimal(totalvalue) / totalqty) if totalqty else p["cost"]
    c.execute(
        "UPDATE products SET qty=?,stock_value=?,cost=? WHERE id=?",
        (totalqty, totalvalue, cost, pid),
    )
    c.execute(
        "INSERT INTO movements(document,date,product_id,qty,warehouse_id) VALUES(?,?,?,?,?)",
        (ref, day, pid, q, wid),
    )


def cost(c, pid, q, wid=1):
    from .operations import rounded

    s = stock(c, pid, wid)
    if q <= 0 or q > s["qty"]:
        raise BusinessError("المخزون غير كافٍ في المستودع المحدد")
    return s["value"] if q == s["qty"] else rounded(Decimal(s["value"]) * q / s["qty"])


def transfer_data(c, id):
    s = c.execute(
        "SELECT t.*,a.name source,b.name target FROM transfers t JOIN warehouses a ON a.id=t.source_id JOIN warehouses b ON b.id=t.target_id WHERE t.id=?",
        (id,),
    ).fetchone()
    if not s:
        raise BusinessError("التحويل غير موجود")
    return {
        **dict(s),
        "lines": [
            dict(r)
            for r in c.execute(
                "SELECT * FROM transfer_lines WHERE transfer_id=?", (id,)
            )
        ],
    }


def save(c, data, uid, id=None):
    from .operations import open_date, quantity

    day = open_date(c, data.get("date"))
    a = validate(c, data.get("source_id"))
    b = validate(c, data.get("target_id"))
    if a == b:
        raise BusinessError("المصدر والوجهة يجب أن يختلفا")
    old = transfer_data(c, id) if id else None
    if old and (old["status"] != "draft" or data.get("version") != old["version"]):
        raise BusinessError("المستند مرحل أو تغيرت المسودة")
    lines = []
    for l in data.get("lines", []):
        p = c.execute(
            "SELECT * FROM products WHERE id=? AND service=0", (l.get("product_id"),)
        ).fetchone()
        if not p:
            raise BusinessError("اختر صنفاً مخزنياً")
        lines.append((p["id"], p["name"], quantity(l.get("qty"))))
    if not lines:
        raise BusinessError("أضف بند تحويل")
    values = (day, a, b, str(data.get("note", ""))[:2000])
    if id:
        c.execute(
            "UPDATE transfers SET date=?,source_id=?,target_id=?,note=?,version=version+1 WHERE id=?",
            (*values, id),
        )
        c.execute("DELETE FROM transfer_lines WHERE transfer_id=?", (id,))
    else:
        id = c.execute(
            "INSERT INTO transfers(date,source_id,target_id,note,status) VALUES(?,?,?,?,'draft')",
            values,
        ).lastrowid
        c.execute("UPDATE transfers SET number=? WHERE id=?", (f"TR-{id:06}", id))
    c.executemany(
        "INSERT INTO transfer_lines(transfer_id,product_id,name,qty) VALUES(?,?,?,?)",
        [(id, *l) for l in lines],
    )
    audit(c, uid, "حفظ مسودة تحويل مخزني", str(id))
    return transfer_data(c, id)


def post(c, id, uid):
    from .operations import open_date

    t = transfer_data(c, id)
    open_date(c, t["date"])
    if t["status"] != "draft":
        raise BusinessError("التحويل ليس مسودة")
    for l in t["lines"]:
        value = cost(c, l["product_id"], l["qty"], t["source_id"])
        change(
            c,
            l["product_id"],
            -l["qty"],
            -value,
            t["number"],
            t["date"],
            t["source_id"],
        )
        change(
            c, l["product_id"], l["qty"], value, t["number"], t["date"], t["target_id"]
        )
        c.execute("UPDATE transfer_lines SET cost=? WHERE id=?", (value, l["id"]))
    c.execute("UPDATE transfers SET status='posted' WHERE id=?", (id,))
    audit(c, uid, "ترحيل تحويل داخلي دون تغيير الملكية", t["number"])
    return transfer_data(c, id)


def cancel(c, id, uid, reason):
    from .operations import open_date

    t = transfer_data(c, id)
    open_date(c, t["date"])
    if t["status"] != "posted" or not str(reason).strip():
        raise BusinessError("اختر تحويلًا مرحلاً واكتب السبب")
    for l in t["lines"]:
        for wid in (t["source_id"], t["target_id"]):
            last = c.execute(
                "SELECT document FROM movements WHERE product_id=? AND warehouse_id=? ORDER BY date DESC,id DESC LIMIT 1",
                (l["product_id"], wid),
            ).fetchone()
            if not last or last["document"] != t["number"]:
                raise BusinessError("توجد حركة لاحقة؛ لا يمكن عكس التحويل")
    for l in t["lines"]:
        change(
            c,
            l["product_id"],
            -l["qty"],
            -l["cost"],
            t["number"] + "-REV",
            t["date"],
            t["target_id"],
        )
        change(
            c,
            l["product_id"],
            l["qty"],
            l["cost"],
            t["number"] + "-REV",
            t["date"],
            t["source_id"],
        )
    c.execute("UPDATE transfers SET status='cancelled' WHERE id=?", (id,))
    audit(c, uid, "عكس تحويل داخلي", t["number"], reason)
    return transfer_data(c, id)


def inventory(c):
    return [
        dict(r)
        for r in c.execute(
            "SELECT s.*,w.name warehouse,p.name product FROM warehouse_stock s JOIN warehouses w ON w.id=s.warehouse_id JOIN products p ON p.id=s.product_id ORDER BY w.id,p.name"
        )
    ]


def handle(c, path, method, data, env, uid, role):
    if path == "/api/warehouse-stock" and method == "GET":
        return inventory(c)
    if not path.startswith(("/api/warehouses", "/api/transfers", "/print/transfers/")):
        return None
    if role not in ("admin", "accountant"):
        raise BusinessError("إدارة المستودعات والتحويلات للمدير أو المحاسب")
    if path == "/api/warehouses" and method == "POST":
        name = str(data.get("name", "")).strip()
        if not name:
            raise BusinessError("أدخل اسم المستودع")
        id = c.execute("INSERT INTO warehouses(name) VALUES(?)", (name,)).lastrowid
        audit(c, uid, "إنشاء مستودع", str(id), name)
        return {"id": id}
    if path == "/api/transfers" and method == "POST":
        return save(c, data, uid)
    if path.startswith("/api/transfers/"):
        bits = path.strip("/").split("/")
        id = int(bits[2])
        if len(bits) == 3:
            if method == "GET":
                return transfer_data(c, id)
            if method == "PUT":
                return save(c, data, uid, id)
        if method == "POST" and bits[-1] == "post":
            t = transfer_data(c, id)
            if data.get("version") is not None and data["version"] != t["version"]:
                raise BusinessError("تغيرت المسودة")
            return post(c, id, uid)
        if method == "POST" and bits[-1] == "cancel":
            return cancel(c, id, uid, data.get("reason", ""))
    if path.startswith("/print/transfers/") and method == "GET":
        from .documents import transfer_document

        return transfer_document(transfer_data(c, int(path.split("/")[-1])))
    raise BusinessError("العملية غير متاحة")
