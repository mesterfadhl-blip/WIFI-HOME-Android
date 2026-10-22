"""Bank subledger and explicit one-to-one statement reconciliation."""

from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs
from .domain import BusinessError, audit, date, journal, money

SCHEMA = """
CREATE TABLE IF NOT EXISTS banks(id INTEGER PRIMARY KEY,name TEXT NOT NULL,code TEXT UNIQUE,currency TEXT NOT NULL DEFAULT 'YER');
CREATE TABLE IF NOT EXISTS bank_moves(id INTEGER PRIMARY KEY,bank_id INTEGER NOT NULL REFERENCES banks(id),date TEXT NOT NULL,document TEXT NOT NULL,amount INTEGER NOT NULL,reference TEXT NOT NULL,note TEXT NOT NULL,UNIQUE(bank_id,document));
CREATE TABLE IF NOT EXISTS bank_statements(id INTEGER PRIMARY KEY,bank_id INTEGER NOT NULL REFERENCES banks(id),reference TEXT NOT NULL,from_date TEXT NOT NULL,to_date TEXT NOT NULL,opening INTEGER NOT NULL,closing INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('draft','final')),book_closing INTEGER,unmatched_book INTEGER,UNIQUE(bank_id,reference));
CREATE TABLE IF NOT EXISTS bank_statement_lines(id INTEGER PRIMARY KEY,statement_id INTEGER NOT NULL REFERENCES bank_statements(id),date TEXT NOT NULL,amount INTEGER NOT NULL,reference TEXT NOT NULL,note TEXT NOT NULL,move_id INTEGER UNIQUE REFERENCES bank_moves(id));
CREATE TABLE IF NOT EXISTS bank_transfers(id INTEGER PRIMARY KEY,number TEXT UNIQUE,date TEXT NOT NULL,source_bank INTEGER REFERENCES banks(id),target_bank INTEGER REFERENCES banks(id),amount INTEGER NOT NULL,note TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS bank_moves_date ON bank_moves(bank_id,date);
"""


def migrate(c):
    c.executescript(SCHEMA)
    for table in ("receipts", "payments", "expenses"):
        if "bank_id" not in {
            r["name"] for r in c.execute(f"PRAGMA table_info({table})")
        }:
            c.execute(
                f"ALTER TABLE {table} ADD COLUMN bank_id INTEGER REFERENCES banks(id)"
            )


def bank(c, id):
    r = c.execute("SELECT * FROM banks WHERE id=?", (id,)).fetchone()
    if not r:
        raise BusinessError("الحساب البنكي غير موجود")
    return dict(r)


def balance(c, id, asof="9999-12-31"):
    b = bank(c, id)
    return c.execute(
        "SELECT coalesce(sum(debit-credit),0) FROM journal WHERE account=? AND date<=?",
        (b["code"], asof),
    ).fetchone()[0]


def move(c, id, day, ref, amount, reference="", note=""):
    bank(c, id)
    closed = c.execute(
        "SELECT max(to_date) FROM bank_statements WHERE bank_id=? AND status='final'",
        (id,),
    ).fetchone()[0]
    if closed and day <= closed:
        raise BusinessError(
            "الحساب البنكي له تسوية معتمدة حتى "
            + closed
            + "؛ لا يمكن إضافة حركة بأثر رجعي"
        )
    c.execute(
        "INSERT INTO bank_moves(bank_id,date,document,amount,reference,note) VALUES(?,?,?,?,?,?)",
        (id, day, ref, amount, str(reference), str(note)),
    )


def signed(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite():
            raise ValueError()
        return (-1 if n < 0 else 1) * money(abs(n))
    except (ValueError, InvalidOperation):
        raise BusinessError("مبلغ كشف البنك غير صالح")


def receive(c, data, uid):
    from .operations import open_date
    import secrets

    day = open_date(c, data.get("date"))
    amount = money(data.get("amount", 0))
    cid = data.get("customer_id")
    bid = data.get("bank_id") or None
    if (
        not amount
        or not c.execute("SELECT 1 FROM customers WHERE id=?", (cid,)).fetchone()
    ):
        raise BusinessError("اختر العميل وأدخل مبلغاً صحيحاً")
    account = bank(c, bid)["code"] if bid else "الصندوق"
    id = c.execute(
        "INSERT INTO receipts(number,date,customer_id,amount,note,bank_id) VALUES(?,?,?,?,?,?)",
        (
            "TMP-" + secrets.token_hex(8),
            day,
            cid,
            amount,
            str(data.get("note", "")),
            bid,
        ),
    ).lastrowid
    ref = f"RC-{id:06}"
    c.execute("UPDATE receipts SET number=? WHERE id=?", (ref, id))
    journal(c, ref, day, [(account, None, amount, 0), ("العملاء", cid, 0, amount)])
    if bid:
        move(c, bid, day, ref, amount, data.get("reference", ""), data.get("note", ""))
    audit(c, uid, "سند قبض بنكي" if bid else "سند قبض نقدي", ref)
    return {"id": id, "number": ref}


def pay(c, data, uid, expense=False):
    from .operations import open_date, supplier_journal

    day = open_date(c, data.get("date"))
    amount = money(data.get("amount", 0))
    b = bank(c, data.get("bank_id"))
    if not amount or amount > balance(c, b["id"], day):
        raise BusinessError("المبلغ غير صحيح أو يتجاوز الرصيد البنكي")
    note = str(data.get("note", "")).strip()
    if expense:
        category = str(data.get("category", "")).strip()
        if not category or not note:
            raise BusinessError("التصنيف والبيان إلزاميان")
        id = c.execute(
            "INSERT INTO expenses(date,amount,category,note,bank_id) VALUES(?,?,?,?,?)",
            (day, amount, category, note, b["id"]),
        ).lastrowid
        ref = f"EX-{id:06}"
        c.execute("UPDATE expenses SET number=? WHERE id=?", (ref, id))
        journal(
            c,
            ref,
            day,
            [("مصروفات التشغيل", None, amount, 0), (b["code"], None, 0, amount)],
        )
    else:
        sid = data.get("supplier_id")
        if not c.execute("SELECT 1 FROM suppliers WHERE id=?", (sid,)).fetchone():
            raise BusinessError("اختر المورد")
        id = c.execute(
            "INSERT INTO payments(supplier_id,date,amount,note,bank_id) VALUES(?,?,?,?,?)",
            (sid, day, amount, note, b["id"]),
        ).lastrowid
        ref = f"PV-{id:06}"
        c.execute("UPDATE payments SET number=? WHERE id=?", (ref, id))
        supplier_journal(
            c, ref, day, sid, [("الموردون", amount, 0), (b["code"], 0, amount)]
        )
    move(c, b["id"], day, ref, -amount, data.get("reference", ""), note)
    audit(c, uid, "مصروف بنكي" if expense else "صرف بنكي لمورد", ref, note)
    return {"number": ref}


def create_bank(c, data, uid):
    from .operations import open_date

    name = str(data.get("name", "")).strip()
    day = open_date(c, data.get("date"))
    opening = money(data.get("opening", 0))
    if not name:
        raise BusinessError("أدخل اسم الحساب البنكي")
    id = c.execute("INSERT INTO banks(name) VALUES(?)", (name,)).lastrowid
    code = f"BANK-{id:04}"
    c.execute("UPDATE banks SET code=? WHERE id=?", (code, id))
    if opening:
        ref = f"BO-{id:06}"
        journal(
            c,
            ref,
            day,
            [
                (code, None, opening, 0),
                ("رأس المال والأرصدة الافتتاحية", None, 0, opening),
            ],
        )
        move(c, id, day, ref, opening, "رصيد افتتاحي", "رصيد بنكي افتتاحي")
    audit(c, uid, "تعريف حساب بنكي", code, name)
    return {"id": id, "code": code}


def transfer(c, data, uid):
    from .operations import open_date

    day = open_date(c, data.get("date"))
    source = data.get("source_bank") or None
    target = data.get("target_bank") or None
    amount = money(data.get("amount", 0))
    note = str(data.get("note", "")).strip()
    if source is None and target is None:
        raise BusinessError("حدد حساباً بنكياً واحداً على الأقل")
    if source and target and int(source) == int(target):
        raise BusinessError("المصدر والوجهة متطابقان")
    a = bank(c, source)["code"] if source else "الصندوق"
    b = bank(c, target)["code"] if target else "الصندوق"
    available = (
        balance(c, source, day)
        if source
        else c.execute(
            "SELECT coalesce(sum(debit-credit),0) FROM journal WHERE account='الصندوق' AND date<=?",
            (day,),
        ).fetchone()[0]
    )
    if not amount or amount > available or not note:
        raise BusinessError("المبلغ يتجاوز الرصيد المتاح أو البيان مفقود")
    id = c.execute(
        "INSERT INTO bank_transfers(date,source_bank,target_bank,amount,note) VALUES(?,?,?,?,?)",
        (day, source, target, amount, note),
    ).lastrowid
    ref = f"BT-{id:06}"
    c.execute("UPDATE bank_transfers SET number=? WHERE id=?", (ref, id))
    journal(c, ref, day, [(b, None, amount, 0), (a, None, 0, amount)])
    if source:
        move(c, source, day, ref, -amount, data.get("reference", ""), note)
    if target:
        move(c, target, day, ref, amount, data.get("reference", ""), note)
    audit(c, uid, "تحويل نقدي / بنكي", ref, note)
    return {"number": ref}


def statement_data(c, id):
    s = c.execute(
        "SELECT s.*,b.name bank,b.code FROM bank_statements s JOIN banks b ON b.id=s.bank_id WHERE s.id=?",
        (id,),
    ).fetchone()
    if not s:
        raise BusinessError("كشف البنك غير موجود")
    lines = [
        dict(r)
        for r in c.execute(
            "SELECT l.*,m.document FROM bank_statement_lines l LEFT JOIN bank_moves m ON m.id=l.move_id WHERE l.statement_id=? ORDER BY l.id",
            (id,),
        )
    ]
    first = (
        c.execute(
            "SELECT min(from_date) FROM bank_statements WHERE bank_id=? AND status='final'",
            (s["bank_id"],),
        ).fetchone()[0]
        or s["from_date"]
    )
    candidates = [
        dict(r)
        for r in c.execute(
            "SELECT m.* FROM bank_moves m WHERE bank_id=? AND date BETWEEN ? AND ? AND NOT EXISTS(SELECT 1 FROM bank_statement_lines l WHERE l.move_id=m.id) ORDER BY date,id",
            (s["bank_id"], first, s["to_date"]),
        )
    ]
    return {**dict(s), "lines": lines, "candidates": candidates}


def create_statement(c, data, uid):
    b = bank(c, data.get("bank_id"))
    f = date(data.get("from_date"))
    t = date(data.get("to_date"))
    ref = str(data.get("reference", "")).strip()
    opening = signed(data.get("opening", 0))
    closing = signed(data.get("closing", 0))
    if f > t or not ref:
        raise BusinessError("الفترة أو مرجع الكشف غير صحيح")
    lines = []
    for l in data.get("lines", []):
        day = date(l.get("date"))
        amount = signed(l.get("amount", 0))
        if not f <= day <= t or not amount:
            raise BusinessError("تاريخ أو مبلغ حركة كشف البنك غير صحيح")
        lines.append((day, amount, str(l.get("reference", "")), str(l.get("note", ""))))
    if opening + sum(l[1] for l in lines) != closing:
        raise BusinessError("رصيد أول الكشف مع الحركات لا يساوي الرصيد الختامي")
    id = c.execute(
        "INSERT INTO bank_statements(bank_id,reference,from_date,to_date,opening,closing,status) VALUES(?,?,?,?,?,?,'draft')",
        (b["id"], ref, f, t, opening, closing),
    ).lastrowid
    c.executemany(
        "INSERT INTO bank_statement_lines(statement_id,date,amount,reference,note) VALUES(?,?,?,?,?)",
        [(id, *l) for l in lines],
    )
    audit(c, uid, "استيراد كشف بنك للمطابقة", str(id), ref)
    return statement_data(c, id)


def match(c, id, data, uid):
    s = statement_data(c, id)
    if s["status"] != "draft":
        raise BusinessError("التسوية معتمدة ولا تقبل التغيير")
    l = c.execute(
        "SELECT * FROM bank_statement_lines WHERE id=? AND statement_id=?",
        (data.get("line_id"), id),
    ).fetchone()
    if not l:
        raise BusinessError("الحركة لا تتبع الكشف")
    mid = data.get("move_id") or None
    if mid:
        m = c.execute(
            "SELECT * FROM bank_moves WHERE id=? AND bank_id=?", (mid, s["bank_id"])
        ).fetchone()
        first = (
            c.execute(
                "SELECT min(from_date) FROM bank_statements WHERE bank_id=? AND status='final'",
                (s["bank_id"],),
            ).fetchone()[0]
            or s["from_date"]
        )
        if (
            not m
            or m["amount"] != l["amount"]
            or m["date"] > s["to_date"]
            or m["date"] < first
        ):
            raise BusinessError(
                "المبلغ أو الحساب أو تاريخ الحركة الدفترية لا يطابق الكشف"
            )
    c.execute("UPDATE bank_statement_lines SET move_id=? WHERE id=?", (mid, l["id"]))
    audit(
        c, uid, "مطابقة حركة بنكية" if mid else "فك مطابقة بنكية", str(id), str(l["id"])
    )
    return statement_data(c, id)


def finalize(c, id, uid):
    from datetime import date as Date, timedelta

    s = statement_data(c, id)
    if s["status"] != "draft":
        raise BusinessError("التسوية معتمدة بالفعل")
    if any(l["move_id"] is None for l in s["lines"]):
        raise BusinessError(
            "توجد حركات بنك غير مطابقة؛ سجل الرسوم أو التحصيلات الناقصة ثم طابقها"
        )
    final = c.execute(
        "SELECT * FROM bank_statements WHERE bank_id=? AND status='final' ORDER BY to_date DESC LIMIT 1",
        (s["bank_id"],),
    ).fetchone()
    if final:
        if (
            s["from_date"]
            != (Date.fromisoformat(final["to_date"]) + timedelta(days=1)).isoformat()
            or s["opening"] != final["closing"]
        ):
            raise BusinessError("الكشف يجب أن يتصل بآخر كشف معتمد وبنفس رصيده الختامي")
        first = c.execute(
            "SELECT min(from_date) FROM bank_statements WHERE bank_id=? AND status='final'",
            (s["bank_id"],),
        ).fetchone()[0]
    else:
        first = s["from_date"]
        before = c.execute(
            "SELECT coalesce(sum(debit-credit),0) FROM journal WHERE account=? AND date<?",
            (s["code"], first),
        ).fetchone()[0]
        if before != s["opening"]:
            raise BusinessError(
                "الرصيد الافتتاحي لأول كشف لا يطابق الرصيد الدفتري قبل الفترة"
            )
    # Other draft matches cannot silently remove a pending book item from this reconciliation.
    pending = c.execute(
        "SELECT coalesce(sum(m.amount),0) FROM bank_moves m WHERE m.bank_id=? AND m.date BETWEEN ? AND ? AND NOT EXISTS(SELECT 1 FROM bank_statement_lines l JOIN bank_statements st ON st.id=l.statement_id WHERE l.move_id=m.id AND (st.status='final' OR st.id=?))",
        (s["bank_id"], first, s["to_date"], id),
    ).fetchone()[0]
    book = balance(c, s["bank_id"], s["to_date"])
    if s["closing"] + pending != book:
        raise BusinessError("الرصيد المعدل لا يطابق رصيد البنك الدفتري")
    c.execute(
        "UPDATE bank_statements SET status='final',book_closing=?,unmatched_book=? WHERE id=?",
        (book, pending, id),
    )
    audit(c, uid, "اعتماد تسوية بنكية", str(id), s["reference"])
    return statement_data(c, id)


def state(c):
    return {
        "banks": [
            {**dict(b), "balance": balance(c, b["id"])}
            for b in c.execute("SELECT * FROM banks ORDER BY id")
        ],
        "moves": [
            dict(r)
            for r in c.execute(
                "SELECT m.*,b.name bank FROM bank_moves m JOIN banks b ON b.id=m.bank_id ORDER BY m.date DESC,m.id DESC"
            )
        ],
        "statements": [
            dict(r)
            for r in c.execute(
                "SELECT s.*,b.name bank FROM bank_statements s JOIN banks b ON b.id=s.bank_id ORDER BY s.to_date DESC,s.id DESC"
            )
        ],
    }


def handle(c, path, method, data, env, uid, role):
    if path == "/api/receipts" and method == "POST":
        return receive(c, data, uid)
    if (
        path in ("/api/payments", "/api/expenses")
        and method == "POST"
        and data.get("bank_id")
    ):
        if role not in ("admin", "accountant"):
            raise BusinessError("الصرف البنكي للمدير أو المحاسب")
        return pay(c, data, uid, path == "/api/expenses")
    if not path.startswith(("/api/banks", "/api/banking", "/print/bank-statements/")):
        return None
    if role not in ("admin", "accountant"):
        raise BusinessError("إدارة البنوك للمدير أو المحاسب")
    if path == "/api/banking" and method == "GET":
        return state(c)
    if path == "/api/banks" and method == "POST":
        if role != "admin":
            raise BusinessError("تعريف الحسابات البنكية للمدير")
        return create_bank(c, data, uid)
    if path == "/api/banking/transfers" and method == "POST":
        return transfer(c, data, uid)
    if path == "/api/banking/statements" and method == "POST":
        return create_statement(c, data, uid)
    if path.startswith("/api/banking/statements/"):
        bits = path.strip("/").split("/")
        id = int(bits[3])
        if len(bits) == 4 and method == "GET":
            return statement_data(c, id)
        if method == "POST" and bits[-1] == "match":
            return match(c, id, data, uid)
        if method == "POST" and bits[-1] == "finalize":
            return finalize(c, id, uid)
    if path.startswith("/print/bank-statements/") and method == "GET":
        from .documents import reconciliation_document

        return reconciliation_document(statement_data(c, int(path.split("/")[-1])))
    raise BusinessError("العملية غير متاحة")
