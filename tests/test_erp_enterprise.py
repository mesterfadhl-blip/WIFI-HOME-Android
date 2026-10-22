import io
import json
import sqlite3
import unittest
from pathlib import Path
import tempfile
import test_erp_service as support
from erp.server import connect, create_app


class EnterpriseTests(unittest.TestCase):
    setUp = support.ERPTests.setUp
    tearDown = support.ERPTests.tearDown
    ok = support.ERPTests.ok
    state = support.ERPTests.state
    draft = support.ERPTests.draft
    balanced = support.ERPTests.balanced

    def order(self, qty=10, cost=50):
        sid = self.ok("/api/suppliers", "POST", {"name": "مورد جديد"})["id"]
        order = self.ok(
            "/api/purchase-orders",
            "POST",
            {
                "supplier_id": sid,
                "date": "2026-10-22",
                "lines": [{"product_id": self.pid, "qty": qty, "cost": cost}],
            },
        )
        self.ok(f'/api/purchase-orders/{order["id"]}/approve', "POST")
        return order

    def receive(self, order, qty=5):
        return self.ok(
            f'/api/purchase-orders/{order["id"]}/receive',
            "POST",
            {
                "date": "2026-10-22",
                "warehouse_id": 1,
                "lines": [{"order_line_id": order["lines"][0]["id"], "qty": qty}],
            },
        )

    def invoice(self, gr):
        p = self.ok(
            f'/api/goods-receipts/{gr["id"]}/invoice', "POST", {"date": "2026-10-22"}
        )
        return self.ok(f'/api/purchases/{p["id"]}/post', "POST")

    def return_supplier(self, p, qty=2):
        return self.ok(
            "/api/supplier-returns",
            "POST",
            {
                "purchase_id": p["id"],
                "date": "2026-10-22",
                "reason": "تالف عند المورد",
                "lines": [{"purchase_line_id": p["lines"][0]["id"], "qty": qty}],
            },
        )

    def legacy(self):
        return {
            "source": "old-device",
            "date": "2026-10-22",
            "include_balances": True,
            "backup": {
                "format": "WIFI-HOME-BACKUP",
                "data": {
                    "customers": [
                        {
                            "id": "C1",
                            "name": "عميل من النسخة",
                            "phone": "777",
                            "region": "المنطقة الأولى",
                            "limit": 500,
                        },
                        {"id": "C2", "name": "عميل دائن", "phone": "888"},
                    ],
                    "journal": [
                        {
                            "customerId": "C1",
                            "account": "العملاء",
                            "date": "2026-10-01",
                            "debit": 250,
                            "credit": 0,
                        },
                        {
                            "customerId": "C1",
                            "account": "العملاء",
                            "date": "2026-10-20",
                            "debit": 0,
                            "credit": 50,
                        },
                        {
                            "customerId": "C2",
                            "account": "العملاء",
                            "date": "2026-10-20",
                            "debit": 0,
                            "credit": 30,
                        },
                        {
                            "customerId": "C1",
                            "account": "العملاء",
                            "date": "2026-11-01",
                            "debit": 999,
                            "credit": 0,
                        },
                    ],
                },
            },
        }

    def test_legacy_review_balances_cutoff_and_idempotency(self):
        data = self.legacy()
        p = self.ok("/api/legacy/preview", "POST", data)
        self.assertEqual((p["new"], p["debit"], p["credit"]), (2, 20000, 3000))
        self.assertEqual(len(self.state()["customers"]), 1)
        r = self.ok("/api/legacy/import", "POST", {**data, "token": p["token"]})
        self.assertEqual(r["created"], 2)
        clients = {r["name"]: r for r in self.state()["customers"]}
        self.assertEqual(clients["عميل من النسخة"]["balance"], 20000)
        self.assertEqual(clients["عميل دائن"]["balance"], -3000)
        self.assertEqual(clients["عميل من النسخة"]["credit_limit"], 50000)
        again = self.ok("/api/legacy/preview", "POST", data)
        self.assertEqual(again["skipped"], 2)
        self.ok("/api/legacy/import", "POST", {**data, "token": again["token"]})
        self.assertEqual(len(self.state()["customers"]), 3)
        self.balanced()

    def test_legacy_conflicts_changed_content_and_unreviewed_refused(self):
        d = self.legacy()
        p = self.ok("/api/legacy/preview", "POST", d)
        d["backup"]["data"]["customers"][0]["phone"] = "changed"
        self.assertEqual(
            self.client.call("/api/legacy/import", "POST", {**d, "token": p["token"]})[
                0
            ],
            400,
        )
        p = self.ok("/api/legacy/preview", "POST", d)
        self.ok("/api/legacy/import", "POST", {**d, "token": p["token"]})
        d["backup"]["data"]["customers"][0]["phone"] = "changed-again"
        p = self.ok("/api/legacy/preview", "POST", d)
        self.assertEqual(p["conflicts"], 1)
        self.assertEqual(
            self.client.call("/api/legacy/import", "POST", {**d, "token": p["token"]})[
                0
            ],
            400,
        )

    def test_legacy_orphan_duplicate_and_unknown_layout_refused(self):
        d = self.legacy()
        d["backup"]["data"]["journal"][0]["customerId"] = "missing"
        self.assertEqual(self.client.call("/api/legacy/preview", "POST", d)[0], 400)
        d = self.legacy()
        d["backup"]["data"]["customers"][1]["id"] = "C1"
        self.assertEqual(self.client.call("/api/legacy/preview", "POST", d)[0], 400)
        self.assertEqual(
            self.client.call(
                "/api/legacy/preview", "POST", {"backup": {}, "date": "2026-10-22"}
            )[0],
            400,
        )

    def test_names_only_import_does_not_create_opening_journals(self):
        d = self.legacy()
        d["include_balances"] = False
        d["backup"] = {"database": d["backup"]["data"]}
        p = self.ok("/api/legacy/preview", "POST", d)
        self.ok("/api/legacy/import", "POST", {**d, "token": p["token"]})
        self.assertTrue(all(c["balance"] == 0 for c in self.state()["customers"]))
        self.assertEqual(
            self.ok("/api/position?asof=2026-10-22")["asset_total"], 400000
        )

    def test_partial_receiving_and_matching_never_double_stock(self):
        o = self.order()
        self.assertEqual(self.state()["products"][0]["qty"], 100)
        gr = self.receive(o, 5)
        self.assertEqual(self.state()["products"][0]["qty"], 105)
        self.assertEqual(self.state()["suppliers"][0]["balance"], 0)
        position = self.ok("/api/position?asof=2026-10-22")
        self.assertTrue(position["balanced"])
        self.assertEqual(
            next(
                r["amount"]
                for r in position["liabilities"]
                if r["name"] == "بضاعة مستلمة غير مفوترة"
            ),
            25000,
        )
        p = self.invoice(gr)
        self.assertEqual(self.state()["products"][0]["qty"], 105)
        self.assertEqual(self.state()["suppliers"][0]["balance"], 25000)
        current = self.ok(f'/api/purchase-orders/{o["id"]}')
        self.assertEqual(current["lines"][0]["remaining"], 5)
        self.assertEqual(
            self.client.call(
                f'/api/goods-receipts/{gr["id"]}/invoice',
                "POST",
                {"date": "2026-10-22"},
            )[0],
            400,
        )
        self.assertEqual(
            self.client.call(
                f'/api/purchase-orders/{o["id"]}/receive',
                "POST",
                {
                    "date": "2026-10-22",
                    "warehouse_id": 1,
                    "lines": [{"order_line_id": o["lines"][0]["id"], "qty": 6}],
                },
            )[0],
            400,
        )
        self.balanced()

    def test_matched_draft_cannot_change_price_or_supplier(self):
        o = self.order()
        gr = self.receive(o)
        p = self.ok(
            f'/api/goods-receipts/{gr["id"]}/invoice', "POST", {"date": "2026-10-22"}
        )
        data = {
            "supplier_id": p["supplier_id"],
            "date": p["date"],
            "version": p["version"],
            "warehouse_id": 1,
            "lines": [{"product_id": self.pid, "qty": 5, "cost": 99}],
        }
        self.assertEqual(
            self.client.call(f'/api/purchases/{p["id"]}', "PUT", data)[0], 400
        )
        self.assertEqual(self.ok(f'/api/purchases/{p["id"]}')["total"], 25000)

    def test_receipt_reversal_and_invoice_reversal_restore_grni(self):
        o = self.order()
        gr = self.receive(o)
        p = self.invoice(gr)
        self.assertEqual(
            self.client.call(
                f'/api/goods-receipts/{gr["id"]}/cancel', "POST", {"reason": "عكس"}
            )[0],
            400,
        )
        self.ok(
            f'/api/purchases/{p["id"]}/cancel', "POST", {"reason": "عكس فاتورة المورد"}
        )
        self.assertEqual(self.state()["products"][0]["qty"], 105)
        self.ok(
            f'/api/goods-receipts/{gr["id"]}/cancel', "POST", {"reason": "عكس الاستلام"}
        )
        self.assertEqual(self.state()["products"][0]["qty"], 100)
        self.assertEqual(
            self.ok(f'/api/purchase-orders/{o["id"]}')["lines"][0]["remaining"], 10
        )
        self.balanced()

    def test_supplier_return_uses_current_value_and_original_supplier_credit(self):
        p = self.invoice(self.receive(self.order()))
        r = self.return_supplier(p)
        self.assertEqual(r["total"], 10000)
        self.assertNotEqual(r["stock_cost"], r["total"])
        self.assertEqual(self.state()["products"][0]["qty"], 103)
        self.assertEqual(self.state()["suppliers"][0]["balance"], 15000)
        self.assertTrue(self.ok("/api/position?asof=2026-10-22")["balanced"])
        self.assertEqual(
            self.client.call(
                f'/api/purchases/{p["id"]}/cancel', "POST", {"reason": "عكس"}
            )[0],
            400,
        )
        self.ok(
            f'/api/supplier-returns/{r["id"]}/cancel', "POST", {"reason": "عكس المرتجع"}
        )
        self.assertEqual(self.state()["products"][0]["qty"], 105)
        self.balanced()

    def test_supplier_return_overage_and_later_stock_block_reversal(self):
        p = self.invoice(self.receive(self.order()))
        r = self.return_supplier(p, 3)
        self.assertEqual(
            self.client.call(
                "/api/supplier-returns",
                "POST",
                {
                    "purchase_id": p["id"],
                    "date": "2026-10-22",
                    "reason": "زيادة",
                    "lines": [{"purchase_line_id": p["lines"][0]["id"], "qty": 3}],
                },
            )[0],
            400,
        )
        inv = self.draft()
        self.ok(f'/api/invoices/{inv["id"]}/post', "POST")
        self.assertEqual(
            self.client.call(
                f'/api/supplier-returns/{r["id"]}/cancel', "POST", {"reason": "عكس"}
            )[0],
            400,
        )

    def test_position_splits_customer_credit_and_balances_historically(self):
        d = self.legacy()
        plan = self.ok("/api/legacy/preview", "POST", d)
        self.ok("/api/legacy/import", "POST", {**d, "token": plan["token"]})
        p = self.ok("/api/position?asof=2026-10-22")
        self.assertTrue(p["balanced"])
        self.assertEqual(p["liability_total"], 3000)
        before = self.ok("/api/position?asof=2025-12-31")
        self.assertEqual(before["asset_total"], 0)
        self.assertIn("قائمة المركز المالي", self.ok("/print/position?asof=2026-10-22"))

    def test_period_reopening_keeps_history_and_earlier_lock(self):
        self.ok(
            "/api/periods", "POST", {"through": "2026-02-01", "reason": "إقفال أول"}
        )
        self.ok(
            "/api/periods", "POST", {"through": "2026-03-01", "reason": "إقفال ثان"}
        )
        periods = self.ok("/api/controls")["periods"]
        old, new = periods[1]["id"], periods[0]["id"]
        self.assertEqual(
            self.client.call(
                f"/api/reopen/period/{old}", "POST", {"reason": "تصحيح فترة"}
            )[0],
            400,
        )
        self.ok(f"/api/reopen/period/{new}", "POST", {"reason": "تصحيح فترة لاحقة"})
        self.assertEqual(len(self.ok("/api/controls")["periods"]), 2)
        self.assertEqual(
            self.client.call(
                "/api/expenses",
                "POST",
                {
                    "date": "2026-01-31",
                    "amount": 1,
                    "category": "اختبار",
                    "note": "مصروف تجريبي",
                },
            )[0],
            400,
        )
        self.ok(
            "/api/expenses",
            "POST",
            {
                "date": "2026-02-15",
                "amount": 1,
                "category": "اختبار",
                "note": "مصروف تجريبي",
            },
        )
        self.assertEqual(len(self.ok("/api/controls")["reopens"]), 1)

    def test_sales_role_cannot_import_reopen_or_view_position(self):
        self.ok(
            "/api/users",
            "POST",
            {
                "name": "sales-role",
                "password": "Synthetic-Password-123",
                "role": "sales",
            },
        )
        self.ok(
            "/api/login",
            "POST",
            {"name": "sales-role", "password": "Synthetic-Password-123"},
        )
        for path, method, data in [
            ("/api/legacy/preview", "POST", self.legacy()),
            ("/api/position?asof=2026-10-22", "GET", None),
            ("/api/purchase-orders", "GET", None),
            ("/api/controls", "GET", None),
            ("/api/backup", "GET", None),
        ]:
            self.assertEqual(self.client.call(path, method, data)[0], 400, path)

    def test_backup_is_consistent_binary_and_import_replay_safe(self):
        env = {
            "PATH_INFO": "/api/backup",
            "REQUEST_METHOD": "GET",
            "wsgi.input": io.BytesIO(),
            "HTTP_COOKIE": self.client.cookie,
        }
        headers = {}

        def start(status, items):
            headers.update(dict(items))
            headers["status"] = status

        content = b"".join(self.app(env, start))
        self.assertTrue(headers["status"].startswith("200"))
        self.assertTrue(content.startswith(b"SQLite format 3"))
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "backup.sqlite3"
            p.write_bytes(content)
            with sqlite3.connect(p) as c:
                self.assertEqual(
                    c.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
        d = self.legacy()
        plan = self.ok("/api/legacy/preview", "POST", d)
        payload = {**d, "token": plan["token"], "request_id": "import-once"}
        first = self.ok("/api/legacy/import", "POST", payload)
        second = self.ok("/api/legacy/import", "POST", payload)
        self.assertEqual(first, second)
        self.assertEqual(len(self.state()["customers"]), 3)

    def test_credit_limit_is_enforced_at_post_and_master_changes_preserve_invoice(self):
        self.ok(
            f"/api/customers/{self.cid}",
            "PUT",
            {
                "name": "عميل محدث",
                "phone": "777",
                "region": "صنعاء",
                "credit_limit": 100,
            },
        )
        invoice = self.draft(paid=0)
        self.assertEqual(
            self.client.call(f'/api/invoices/{invoice["id"]}/post', "POST")[0], 400
        )
        self.assertEqual(self.state()["products"][0]["qty"], 100)
        self.ok(
            f"/api/customers/{self.cid}",
            "PUT",
            {"name": "عميل محدث", "credit_limit": 500},
        )
        self.ok(f'/api/invoices/{invoice["id"]}/post', "POST")
        self.ok(
            f"/api/products/{self.pid}",
            "PUT",
            {"name": "اسم الصنف الجديد", "price": 900, "active": False},
        )
        old = self.ok(f'/api/invoices/{invoice["id"]}')
        self.assertEqual(old["lines"][0]["name"], "كرت")
        self.assertEqual(old["lines"][0]["price"], 10000)
        self.assertEqual(
            self.client.call(
                "/api/invoices",
                "POST",
                {
                    "customer_id": self.cid,
                    "date": "2026-10-22",
                    "lines": [{"product_id": self.pid, "qty": 1, "price": 100}],
                },
            )[0],
            400,
        )
        self.balanced()

    def test_bank_reopen_only_latest_and_preserves_final_snapshot(self):
        b = self.ok(
            "/api/banks",
            "POST",
            {"name": "بنك إعادة الفتح", "date": "2026-01-01", "opening": 1000},
        )
        ids = []
        for month, last in [("10", "31"), ("11", "30")]:
            s = self.ok(
                "/api/banking/statements",
                "POST",
                {
                    "bank_id": b["id"],
                    "reference": month,
                    "from_date": f"2026-{month}-01",
                    "to_date": f"2026-{month}-{last}",
                    "opening": 1000,
                    "closing": 1000,
                    "lines": [],
                },
            )
            self.ok(f'/api/banking/statements/{s["id"]}/finalize', "POST")
            ids.append(s["id"])
        self.assertEqual(
            self.client.call(
                f"/api/reopen/bank/{ids[0]}", "POST", {"reason": "تصحيح كشف سابق"}
            )[0],
            400,
        )
        self.ok(f"/api/reopen/bank/{ids[1]}", "POST", {"reason": "تصحيح كشف أحدث"})
        with connect(self.path) as c:
            old = json.loads(
                c.execute(
                    "SELECT snapshot FROM control_reopens WHERE kind='bank'"
                ).fetchone()[0]
            )
            self.assertEqual(old["status"], "final")
            self.assertEqual(old["book_closing"], 100000)
        current = self.ok(f"/api/banking/statements/{ids[1]}")
        self.assertEqual(current["status"], "draft")
        self.ok(f"/api/banking/statements/{ids[1]}/finalize", "POST")

    def test_duplicate_purchase_lines_return_preserves_exact_pool_and_replay(self):
        sid = self.ok("/api/suppliers", "POST", {"name": "مورد بنود متعددة"})["id"]
        p = self.ok(
            "/api/purchases",
            "POST",
            {
                "supplier_id": sid,
                "date": "2026-10-22",
                "lines": [
                    {"product_id": self.pid, "qty": 3, "cost": 50},
                    {"product_id": self.pid, "qty": 3, "cost": 70},
                ],
            },
        )
        p = self.ok(f'/api/purchases/{p["id"]}/post', "POST")
        old = self.state()["products"][0]
        payload = {
            "purchase_id": p["id"],
            "date": "2026-10-22",
            "reason": "إرجاع بنود متعددة",
            "request_id": "return-once",
            "lines": [{"purchase_line_id": l["id"], "qty": 3} for l in p["lines"]],
        }
        first = self.ok("/api/supplier-returns", "POST", payload)
        again = self.ok("/api/supplier-returns", "POST", payload)
        self.assertEqual(first, again)
        after = self.state()["products"][0]
        self.assertEqual(old["qty"] - after["qty"], 6)
        self.assertEqual(old["stock_value"] - after["stock_value"], first["stock_cost"])
        self.balanced()

    def test_schema_upgrade_repeat_preserves_balances(self):
        self.invoice(self.receive(self.order()))
        before = self.state()
        create_app(self.path)
        create_app(self.path)
        after = self.state()
        self.assertEqual(before["products"], after["products"])
        self.assertEqual(before["customers"], after["customers"])
        self.assertEqual(before["suppliers"], after["suppliers"])
        with connect(self.path) as c:
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_legacy_explicit_demo_filter_and_optional_metadata(self):
        data = self.legacy()
        people = data["backup"]["data"]["customers"]
        people[0]["note"] = "ملاحظة نقل اصطناعية"
        people[0]["created"] = "2025-10-01T09:00:00"
        db = data["backup"]["data"]
        db["sales"] = [{"ref": "DEMO-1", "demo": True}]
        db["journal"][0]["ref"] = "DEMO-1"
        data["exclude_demo"] = True
        plan = self.ok("/api/legacy/preview", "POST", data)
        self.assertEqual(plan["demo_documents"], 1)
        self.assertEqual(plan["excluded_demo_documents"], 1)
        # The unmarked receipt remains; demo sales are never silently retained.
        self.assertEqual(plan["rows"][0]["opening"], -5000)
        self.ok("/api/legacy/import", "POST", {**data, "token": plan["token"]})
        customer = next(
            c for c in self.state()["customers"] if c["name"] == "عميل من النسخة"
        )
        self.assertEqual(customer["note"], "ملاحظة نقل اصطناعية")
        self.assertEqual(customer["legacy_created"], "2025-10-01T09:00:00")
        self.assertEqual(customer["balance"], -5000)
        self.balanced()
