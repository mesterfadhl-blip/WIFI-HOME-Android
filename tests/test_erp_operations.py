import unittest
from pathlib import Path
import test_erp_service as support
from erp.server import connect, create_app


class OperationTests(unittest.TestCase):
    setUp = support.ERPTests.setUp
    tearDown = support.ERPTests.tearDown
    ok = support.ERPTests.ok
    draft = support.ERPTests.draft
    state = support.ERPTests.state
    balanced = support.ERPTests.balanced

    def supplier(self):
        return self.ok("/api/suppliers", "POST", {"name": "مورد اختبار"})["id"]

    def purchase(self, sid=None, **kwargs):
        sid = sid or self.supplier()
        data = {
            "supplier_id": sid,
            "date": "2026-10-22",
            "paid": 1000,
            "lines": [{"product_id": self.pid, "qty": 100, "cost": 60}],
        }
        data.update(kwargs)
        return self.ok("/api/purchases", "POST", data)

    def post_purchase(self, p):
        return self.ok(
            f'/api/purchases/{p["id"]}/post', "POST", {"version": p["version"]}
        )

    def post_sale(self, **kwargs):
        s = self.draft(**kwargs)
        return self.ok(f'/api/invoices/{s["id"]}/post', "POST")

    def credit(self, s, qty=1, **kwargs):
        data = {
            "invoice_id": s["id"],
            "date": "2026-10-22",
            "reason": "مرتجع اختبار",
            "refund": 0,
            "lines": [{"sale_line_id": s["lines"][0]["id"], "qty": qty}],
        }
        data.update(kwargs)
        return self.ok("/api/returns", "POST", data)

    def test_purchase_posts_once_with_weighted_value_and_supplier_payment(self):
        p = self.purchase()
        self.assertEqual(self.state()["products"][0]["qty"], 100)
        self.post_purchase(p)
        st = self.state()
        self.assertEqual(st["products"][0]["qty"], 200)
        self.assertEqual(st["products"][0]["cost"], 5000)
        self.assertEqual(st["products"][0]["stock_value"], 1000000)
        self.assertEqual(st["suppliers"][0]["balance"], 500000)
        self.assertEqual(
            self.client.call(f'/api/purchases/{p["id"]}/post', "POST")[0], 400
        )
        self.ok(
            "/api/payments",
            "POST",
            {"supplier_id": p["supplier_id"], "date": "2026-10-22", "amount": 300},
        )
        self.assertEqual(self.state()["suppliers"][0]["balance"], 470000)
        self.balanced()

    def test_full_purchase_sale_return_expense_cycle_agrees_with_profit_and_stock(self):
        p = self.purchase()
        self.post_purchase(p)
        s = self.post_sale()
        r = self.credit(s, refund=20)
        self.assertEqual(r["total"], 9500)
        self.assertEqual(r["cost"], 5000)
        self.ok(
            "/api/expenses",
            "POST",
            {"date": "2026-10-22", "amount": 10, "category": "تشغيل", "note": "إنترنت"},
        )
        st = self.state()
        self.assertEqual(st["products"][0]["qty"], 199)
        self.assertEqual(st["products"][0]["stock_value"], 995000)
        self.assertEqual(st["customers"][0]["balance"], 6500)
        f = self.ok("/api/finance?from=2026-10-22&to=2026-10-22")
        self.assertEqual(f["net_sales"], 9500)
        self.assertEqual(f["cost"], 5000)
        self.assertEqual(f["gross_profit"], 4500)
        self.assertEqual(f["net_profit"], 3500)
        self.assertEqual(f["debits"], f["credits"])
        self.assertEqual(self.ok("/api/reports")["totals"]["total"], 9500)
        self.balanced()

    def test_partial_returns_exactly_allocate_discount_and_cost_cents(self):
        s = self.post_sale(
            lines=[{"product_id": self.pid, "qty": 3, "price": "3.34"}],
            discount=".02",
            paid=0,
        )
        credits = [self.credit(s) for _ in range(3)]
        self.assertEqual(sum(r["total"] for r in credits), s["total"])
        self.assertEqual(sum(r["cost"] for r in credits), s["cost"])
        self.assertEqual(self.state()["products"][0]["stock_value"], 400000)
        self.assertEqual(self.state()["customers"][0]["balance"], 0)
        self.assertEqual(
            self.client.call(
                "/api/returns",
                "POST",
                {
                    "invoice_id": s["id"],
                    "date": "2026-10-22",
                    "reason": "زيادة",
                    "lines": [{"sale_line_id": s["lines"][0]["id"], "qty": 1}],
                },
            )[0],
            400,
        )
        self.balanced()

    def test_return_cannot_reference_other_invoice_or_repeat_same_line(self):
        a = self.post_sale()
        b = self.post_sale()
        for lines in [
            [{"sale_line_id": b["lines"][0]["id"], "qty": 1}],
            [{"sale_line_id": a["lines"][0]["id"], "qty": 1}] * 2,
        ]:
            self.assertEqual(
                self.client.call(
                    "/api/returns",
                    "POST",
                    {
                        "invoice_id": a["id"],
                        "date": "2026-10-22",
                        "reason": "خطأ",
                        "lines": lines,
                    },
                )[0],
                400,
            )
        self.assertEqual(len(self.state()["returns"]), 0)
        self.assertEqual(self.state()["products"][0]["qty"], 96)

    def test_cancel_return_then_invoice_restores_original_values(self):
        s = self.post_sale()
        r = self.credit(s, refund=10)
        self.assertEqual(
            self.client.call(
                f'/api/invoices/{s["id"]}/cancel', "POST", {"reason": "تعديل"}
            )[0],
            400,
        )
        self.ok(f'/api/returns/{r["id"]}/cancel', "POST", {"reason": "خطأ المرتجع"})
        self.assertEqual(
            self.client.call(
                f'/api/returns/{r["id"]}/cancel', "POST", {"reason": "تكرار"}
            )[0],
            400,
        )
        self.ok(f'/api/invoices/{s["id"]}/cancel', "POST", {"reason": "خطأ الفاتورة"})
        st = self.state()
        self.assertEqual(st["products"][0]["qty"], 100)
        self.assertEqual(st["products"][0]["stock_value"], 400000)
        self.assertEqual(st["customers"][0]["balance"], 0)
        self.balanced()

    def test_purchase_cancellation_blocked_after_consumption_and_backdated_stock_rejected(
        self,
    ):
        p = self.purchase()
        self.post_purchase(p)
        self.post_sale()
        self.assertEqual(
            self.client.call(
                f'/api/purchases/{p["id"]}/cancel', "POST", {"reason": "إلغاء"}
            )[0],
            400,
        )
        q = self.purchase(date="2026-10-21")
        self.assertEqual(
            self.client.call(f'/api/purchases/{q["id"]}/post', "POST")[0], 400
        )
        self.assertEqual(self.state()["products"][0]["qty"], 198)
        self.balanced()

    def test_clean_purchase_cancellation_preserves_unrelated_supplier_payment(self):
        p = self.purchase()
        self.post_purchase(p)
        self.ok(
            "/api/payments",
            "POST",
            {"supplier_id": p["supplier_id"], "date": "2026-10-22", "amount": 100},
        )
        self.ok(f'/api/purchases/{p["id"]}/cancel', "POST", {"reason": "خطأ"})
        self.assertEqual(self.state()["products"][0]["stock_value"], 400000)
        self.assertEqual(self.state()["products"][0]["qty"], 100)
        self.assertEqual(self.state()["suppliers"][0]["balance"], -10000)
        self.balanced()

    def test_period_close_blocks_all_financial_mutations_including_old_drafts(self):
        p = self.purchase()
        s = self.draft()
        self.ok(
            "/api/periods", "POST", {"through": "2026-10-22", "reason": "إقفال الشهر"}
        )
        for path, payload in [
            (f'/api/purchases/{p["id"]}/post', {}),
            (f'/api/invoices/{s["id"]}/post', {}),
            (
                "/api/receipts",
                {"customer_id": self.cid, "date": "2026-10-22", "amount": 10},
            ),
            (
                "/api/payments",
                {"supplier_id": p["supplier_id"], "date": "2026-10-22", "amount": 10},
            ),
            (
                "/api/expenses",
                {
                    "date": "2026-10-22",
                    "amount": 10,
                    "category": "تشغيل",
                    "note": "اختبار",
                },
            ),
        ]:
            status, r = self.client.call(path, "POST", payload)
            self.assertEqual(status, 400, r)
            self.assertIn("مقفل", r["error"])
        self.assertEqual(self.state()["products"][0]["qty"], 100)
        self.balanced()

    def test_integer_value_retained_when_average_rounding_would_lose_cents(self):
        pid = self.ok(
            "/api/products",
            "POST",
            {
                "name": "دقة تكلفة",
                "price": 1,
                "cost": ".01",
                "qty": 1,
                "opening_date": "2026-01-01",
            },
        )["id"]
        p = self.purchase(paid=0, lines=[{"product_id": pid, "qty": 2, "cost": ".02"}])
        self.post_purchase(p)
        s = self.post_sale(
            discount=0, paid=0, lines=[{"product_id": pid, "qty": 3, "price": 1}]
        )
        self.assertEqual(s["cost"], 5)
        stock = next(p for p in self.state()["products"] if p["id"] == pid)
        self.assertEqual(stock["qty"], 0)
        self.assertEqual(stock["stock_value"], 0)
        self.balanced()

    def test_documents_and_supplier_opening_balance_and_sales_role_denial(self):
        p = self.purchase()
        self.post_purchase(p)
        s = self.post_sale()
        r = self.credit(s)
        for path, title in [
            (f'/print/purchases/{p["id"]}', "فاتورة شراء"),
            (f'/print/returns/{r["id"]}', "إشعار دائن"),
            (
                f'/print/supplier?supplier={p["supplier_id"]}&from=2026-10-22&to=2026-10-22',
                "كشف حساب مورد",
            ),
            ("/print/finance?from=2026-10-22&to=2026-10-22", "ميزان المراجعة"),
        ]:
            html = self.ok(path)
            self.assertIn(title, html)
            self.assertIn("size:A4", html)
            self.assertNotIn('class="workspace"', html)
        self.ok(
            "/api/users",
            "POST",
            {"name": "seller2", "password": "Test-Password-123", "role": "sales"},
        )
        other = support.Client(self.app)
        other.call(
            "/api/login", "POST", {"name": "seller2", "password": "Test-Password-123"}
        )
        self.assertEqual(other.call(f"/api/returns/{r['id']}")[0], 200)
        self.assertEqual(other.call(f"/print/returns/{r['id']}")[0], 200)
        for path in [
            "/api/purchases",
            "/api/returns",
            "/api/payments",
            "/api/expenses",
            "/api/periods",
        ]:
            self.assertNotEqual(other.call(path, "POST", {})[0], 200)

    def test_retry_keys_prevent_duplicate_credit_payment_and_expense(self):
        s = self.post_sale()
        payload = {
            "request_id": "credit-request-1",
            "invoice_id": s["id"],
            "date": "2026-10-22",
            "reason": "إعادة محاولة",
            "lines": [{"sale_line_id": s["lines"][0]["id"], "qty": 1}],
        }
        a = self.ok("/api/returns", "POST", payload)
        b = self.ok("/api/returns", "POST", payload)
        self.assertEqual(a["id"], b["id"])
        self.assertEqual(len(self.state()["returns"]), 1)
        payload["refund"] = 1
        self.assertEqual(self.client.call("/api/returns", "POST", payload)[0], 400)
        for path, payload in [
            (
                "/api/expenses",
                {
                    "request_id": "expense-1",
                    "date": "2026-10-22",
                    "amount": 10,
                    "category": "تشغيل",
                    "note": "اختبار",
                },
            ),
            (
                "/api/payments",
                {
                    "request_id": "payment-1",
                    "date": "2026-10-22",
                    "amount": 10,
                    "supplier_id": self.supplier(),
                },
            ),
        ]:
            self.assertEqual(
                self.ok(path, "POST", payload), self.ok(path, "POST", payload)
            )
        self.assertEqual(len(self.state()["expenses"]), 1)
        self.assertEqual(len(self.state()["payments"]), 1)
        self.balanced()

    def test_legacy_database_upgrade_preserves_original_invoice_and_stock(self):
        from erp.server import SCHEMA

        legacy = Path(self.tmp.name) / "legacy.sqlite3"
        with connect(legacy) as c:
            c.executescript(SCHEMA)
            c.execute("INSERT INTO customers(id,name) VALUES(1,'عميل قديم')")
            c.execute(
                "INSERT INTO products(id,name,price,cost,qty,service) VALUES(1,'صنف قديم',10000,4000,98,0)"
            )
            c.execute(
                "INSERT INTO invoices(id,number,customer_id,date,status,discount,paid,total,cost) VALUES(1,'SI-000001',1,'2026-10-22','posted',1000,5000,19000,8000)"
            )
            c.execute(
                "INSERT INTO lines(invoice_id,product_id,name,qty,price,cost,service) VALUES(1,1,'صنف قديم',2,10000,4000,0)"
            )
            entries = [
                ("المخزون", None, 400000, 0),
                ("رأس المال والأرصدة الافتتاحية", None, 0, 400000),
                ("العملاء", 1, 19000, 0),
                ("المبيعات", None, 0, 19000),
                ("الصندوق", None, 5000, 0),
                ("العملاء", 1, 0, 5000),
                ("تكلفة المبيعات", None, 8000, 0),
                ("المخزون", None, 0, 8000),
            ]
            c.executemany(
                "INSERT INTO journal(document,date,account,customer_id,debit,credit) VALUES('LEGACY','2026-10-22',?,?,?,?)",
                entries,
            )
        create_app(legacy)
        create_app(legacy)
        with connect(legacy) as c:
            line = c.execute("SELECT * FROM lines").fetchone()
            stock = c.execute("SELECT * FROM products").fetchone()
            self.assertEqual(line["cost_total"], 8000)
            self.assertEqual(line["net_total"], 19000)
            self.assertEqual(stock["stock_value"], 392000)
            self.assertEqual(stock["qty"], 98)
            self.assertEqual(
                c.execute("SELECT sum(debit-credit) FROM journal").fetchone()[0], 0
            )
            self.assertEqual(
                c.execute("SELECT total FROM invoices").fetchone()[0], 19000
            )
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_migration_is_repeatable_and_retains_balances(self):
        self.post_purchase(self.purchase())
        self.post_sale()
        before = self.state()
        create_app(self.path)
        create_app(self.path)
        after = self.state()
        self.assertEqual(before["products"], after["products"])
        self.assertEqual(before["customers"], after["customers"])
        self.balanced()


if __name__ == "__main__":
    unittest.main()
