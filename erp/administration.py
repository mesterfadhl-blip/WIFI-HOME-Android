"""Financial position, audited reopening and consistent downloadable backups."""

import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs
from .domain import BusinessError, audit, date
from . import treasury


def migrate(c):
    if "reopened" not in {r["name"] for r in c.execute("PRAGMA table_info(periods)")}:
        c.execute("ALTER TABLE periods ADD COLUMN reopened INTEGER NOT NULL DEFAULT 0")
    c.executescript(
        "CREATE TABLE IF NOT EXISTS control_reopens(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,document_id INTEGER NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),reason TEXT NOT NULL,snapshot TEXT NOT NULL,at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
    )


def position(c, asof):
    asof = date(asof)
    rows = [
        dict(r)
        for r in c.execute(
            "SELECT account,sum(debit-credit) balance FROM journal WHERE date<=? GROUP BY account ORDER BY account",
            (asof,),
        )
    ]
    banks = {r["code"] for r in c.execute("SELECT code FROM banks")}
    assets = []
    liabilities = []
    equity = []
    unknown = []
    profit = 0
    income = {
        "المبيعات",
        "مردودات المبيعات",
        "تكلفة المبيعات",
        "مصروفات التشغيل",
        "فروق تكلفة مردودات المشتريات",
    }
    for row in rows:
        name = row["account"]
        n = row["balance"]
        if name in income:
            profit -= n
            continue
        if name == "رأس المال والأرصدة الافتتاحية":
            equity.append({"name": name, "amount": -n})
            continue
        if name in ("العملاء", "الموردون"):
            key = "customer_id" if name == "العملاء" else "supplier_id"
            values = [
                r[0]
                for r in c.execute(
                    f"SELECT sum(debit-credit) FROM journal WHERE account=? AND date<=? GROUP BY {key}",
                    (name, asof),
                )
            ]
            debit = sum(max(v, 0) for v in values)
            credit = sum(max(-v, 0) for v in values)
            if debit:
                assets.append(
                    {
                        "name": (
                            "ذمم العملاء"
                            if name == "العملاء"
                            else "دفعات وأرصدة مدينة لدى الموردين"
                        ),
                        "amount": debit,
                    }
                )
            if credit:
                liabilities.append(
                    {
                        "name": (
                            "دفعات وأرصدة دائنة للعملاء"
                            if name == "العملاء"
                            else "ذمم الموردين"
                        ),
                        "amount": credit,
                    }
                )
        elif name in ("المخزون", "الصندوق") or name in banks:
            if n >= 0:
                assets.append({"name": name, "amount": n})
            else:
                liabilities.append({"name": "رصيد دائن — " + name, "amount": -n})
        elif name in ("موردو خدمات", "بضاعة مستلمة غير مفوترة"):
            if n <= 0:
                liabilities.append({"name": name, "amount": -n})
            else:
                assets.append({"name": "رصيد مدين — " + name, "amount": n})
        elif n:
            unknown.append(row)
    equity.append({"name": "النتيجة المتراكمة حتى التاريخ", "amount": profit})
    a = sum(r["amount"] for r in assets)
    l = sum(r["amount"] for r in liabilities)
    e = sum(r["amount"] for r in equity)
    return {
        "asof": asof,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "asset_total": a,
        "liability_total": l,
        "equity_total": e,
        "difference": a - l - e,
        "unclassified": unknown,
        "balanced": a == l + e and not unknown,
    }


def reopen(c, kind, id, data, uid):
    reason = str(data.get("reason", "")).strip()
    if len(reason) < 5:
        raise BusinessError("اكتب سبب إعادة الفتح بوضوح (5 أحرف على الأقل)")
    if kind == "period":
        row = c.execute(
            "SELECT * FROM periods WHERE id=? AND reopened=0", (id,)
        ).fetchone()
        latest = c.execute(
            "SELECT id FROM periods WHERE reopened=0 ORDER BY through DESC,id DESC LIMIT 1"
        ).fetchone()
        if not row or not latest or latest[0] != id:
            raise BusinessError("يمكن إعادة فتح آخر فترة مقفلة فقط")
        snapshot = dict(row)
        c.execute("UPDATE periods SET reopened=1 WHERE id=?", (id,))
    else:
        snapshot = treasury.statement_data(c, id)
        latest = c.execute(
            "SELECT id FROM bank_statements WHERE bank_id=? AND status='final' ORDER BY to_date DESC,id DESC LIMIT 1",
            (snapshot["bank_id"],),
        ).fetchone()
        if snapshot["status"] != "final" or not latest or latest[0] != id:
            raise BusinessError("يمكن إعادة فتح آخر كشف معتمد لهذا البنك فقط")
        c.execute(
            "UPDATE bank_statements SET status='draft',book_closing=NULL,unmatched_book=NULL WHERE id=?",
            (id,),
        )
    c.execute(
        "INSERT INTO control_reopens(kind,document_id,user_id,reason,snapshot) VALUES(?,?,?,?,?)",
        (kind, id, uid, reason, json.dumps(snapshot, ensure_ascii=False)),
    )
    audit(
        c,
        uid,
        "إعادة فتح فترة" if kind == "period" else "إعادة فتح تسوية بنك",
        str(id),
        reason,
    )
    return {"ok": True}


def handle(c, path, method, data, env, uid, role):
    if path in ("/api/position", "/print/position"):
        if role not in ("admin", "accountant"):
            raise BusinessError("القائمة للمدير أو المحاسب")
        if method != "GET":
            raise BusinessError("طلب غير صالح")
        q = parse_qs(env.get("QUERY_STRING", ""))
        value = position(c, q.get("asof", ["2999-12-31"])[0])
        if path.startswith("/api/"):
            return value
        from .documents import document, text, money

        body = ""
        for title, key, total in [
            ("الأصول", "assets", "asset_total"),
            ("الالتزامات", "liabilities", "liability_total"),
            ("حقوق الملكية", "equity", "equity_total"),
        ]:
            rows = "".join(
                f'<tr><td>{text(r["name"])}</td><td class="num">{money(r["amount"])}</td></tr>'
                for r in value[key]
            )
            body += f"<h2>{title}</h2><table><thead><tr><th>الحساب</th><th>القيمة بالريال اليمني</th></tr></thead><tbody>{rows}</tbody><tfoot><tr><td>الإجمالي</td><td>{money(value[total])}</td></tr></tfoot></table>"
        body += f'<p>فرق المعادلة: {money(value["difference"])} · الحسابات غير المصنفة: {len(value["unclassified"])}</p>'
        return document("قائمة المركز المالي", value["asof"], body)
    if path == "/api/controls" and method == "GET":
        if role != "admin":
            raise BusinessError("إدارة الإقفال للمدير فقط")
        return {
            "periods": [
                dict(r) for r in c.execute("SELECT * FROM periods ORDER BY id DESC")
            ],
            "statements": [
                dict(r)
                for r in c.execute(
                    "SELECT s.*,b.name bank FROM bank_statements s JOIN banks b ON b.id=s.bank_id WHERE s.status='final' ORDER BY s.to_date DESC"
                )
            ],
            "reopens": [
                dict(r)
                for r in c.execute(
                    "SELECT id,kind,document_id,user_id,reason,at FROM control_reopens ORDER BY id DESC"
                )
            ],
        }
    if path.startswith("/api/reopen/") and method == "POST":
        if role != "admin":
            raise BusinessError("إعادة الفتح للمدير فقط")
        parts = path.strip("/").split("/")
        if len(parts) != 4 or parts[2] not in ("period", "bank"):
            raise BusinessError("طلب غير صالح")
        return reopen(c, parts[2], int(parts[3]), data, uid)
    if path == "/api/backup" and method == "GET":
        if role != "admin":
            raise BusinessError("تنزيل النسخة الاحتياطية للمدير فقط")
        from .backup import backup

        source = c.execute("PRAGMA database_list").fetchone()[2]
        with tempfile.TemporaryDirectory() as folder:
            target = backup(source, Path(folder) / "backup.sqlite3")
            content = target.read_bytes()
        return content, "application/vnd.sqlite3", "WIFI-HOME-ERP-backup.sqlite3"
    return None
