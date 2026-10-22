import unittest
import test_erp_service as support
from erp.server import connect, create_app


class WorkspaceTests(unittest.TestCase):
    setUp = support.ERPTests.setUp
    tearDown = support.ERPTests.tearDown
    ok = support.ERPTests.ok
    state = support.ERPTests.state
    draft = support.ERPTests.draft
    balanced = support.ERPTests.balanced

    def sale(self, **kw):
        s = self.draft(**kw)
        return self.ok(f'/api/invoices/{s["id"]}/post', "POST")

    def receipt(self, amount=100, **kw):
        p = {"customer_id": self.cid, "date": "2026-10-22", "amount": amount}
        p.update(kw)
        return self.ok("/api/receipts", "POST", p)

    def allocate(self, r, s, amount=100, **kw):
        p = {
            "receipt_id": r["id"],
            "invoice_id": s["id"],
            "amount": amount,
            "date": "2026-10-22",
        }
        p.update(kw)
        return self.ok("/api/allocations", "POST", p)

    def bank(self, opening=5000, **kw):
        p = {"name": "بنك اختبار", "date": "2026-01-01", "opening": opening}
        p.update(kw)
        return self.ok("/api/banks", "POST", p)

    def warehouse(self):
        return self.ok("/api/warehouses", "POST", {"name": "المستودع الثاني"})["id"]

    def transfer(self, wid, qty=30):
        t = self.ok(
            "/api/transfers",
            "POST",
            {
                "date": "2026-10-22",
                "source_id": 1,
                "target_id": wid,
                "lines": [{"product_id": self.pid, "qty": qty}],
            },
        )
        return self.ok(f'/api/transfers/{t["id"]}/post', "POST")

    def test_receipt_allocation_reduces_invoice_not_cash_twice(self):
        s = self.sale()
        r = self.receipt(100)
        with connect(self.path) as c:
            before = c.execute("SELECT count(*) FROM journal").fetchone()[0]
        a = self.allocate(r, s, 100)
        self.assertEqual(a["balance"]["outstanding"], 4000)
        self.assertEqual(
            self.ok(f'/api/invoices/{s["id"]}')["settlement"]["allocated"], 10000
        )
        with connect(self.path) as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM journal").fetchone()[0], before
            )
        self.assertEqual(self.state()["customers"][0]["balance"], 4000)
        self.balanced()

    def test_overallocation_wrong_customer_and_dates_rejected(self):
        s = self.sale()
        r = self.receipt(100)
        base = {
            "receipt_id": r["id"],
            "invoice_id": s["id"],
            "date": "2026-10-22",
            "amount": 101,
        }
        self.assertEqual(self.client.call("/api/allocations", "POST", base)[0], 400)
        cid = self.ok("/api/customers", "POST", {"name": "عميل ثان"})["id"]
        r2 = self.receipt(100, customer_id=cid)
        base.update(receipt_id=r2["id"], amount=10)
        self.assertEqual(self.client.call("/api/allocations", "POST", base)[0], 400)
        base.update(receipt_id=r["id"], date="2026-10-21")
        self.assertEqual(self.client.call("/api/allocations", "POST", base)[0], 400)

    def test_return_releases_excess_allocation_preserves_audit_and_credit(self):
        s = self.sale(paid=0)
        r = self.receipt(190)
        self.allocate(r, s, 190)
        self.ok(
            "/api/returns",
            "POST",
            {
                "invoice_id": s["id"],
                "date": "2026-10-22",
                "reason": "مرتجع جزئي",
                "lines": [{"sale_line_id": s["lines"][0]["id"], "qty": 1}],
            },
        )
        state = self.ok("/api/settlements")
        self.assertEqual(state["allocations"][0]["remaining"], 9500)
        self.assertEqual(state["receipts"][0]["available"], 9500)
        self.assertEqual(state["invoices"][0]["outstanding"], 0)
        self.balanced()

    def test_cancellation_frees_allocations_without_deleting_receipt(self):
        s = self.sale()
        r = self.receipt(100)
        self.allocate(r, s, 100)
        self.ok(f'/api/invoices/{s["id"]}/cancel', "POST", {"reason": "خطأ"})
        st = self.ok("/api/settlements")
        self.assertEqual(st["receipts"][0]["available"], 10000)
        self.assertEqual(st["allocations"][0]["remaining"], 0)
        self.assertEqual(self.state()["customers"][0]["balance"], -10000)

    def test_aging_tracks_due_dates_and_release_history_as_of_date(self):
        s = self.sale(date="2026-08-01", due_date="2026-08-15", paid=0)
        r = self.receipt(50, date="2026-09-01")
        a = self.allocate(r, s, 50, date="2026-09-01")
        self.ok(
            f'/api/allocations/{a["id"]}/release',
            "POST",
            {"date": "2026-10-22", "amount": 20, "reason": "إعادة توزيع"},
        )
        earlier = self.ok("/api/aging?asof=2026-09-15")
        later = self.ok("/api/aging?asof=2026-10-22")
        self.assertEqual(earlier["rows"][0]["outstanding"], 14000)
        self.assertEqual(earlier["buckets"]["days_31_60"], 14000)
        self.assertEqual(later["rows"][0]["outstanding"], 16000)
        self.assertEqual(later["unapplied_receipts"], 2000)
        self.assertEqual(later["net_receivable"], 14000)

    def test_allocation_retry_key_and_closed_period_guard(self):
        s = self.sale(paid=0)
        r = self.receipt(190)
        p = {
            "receipt_id": r["id"],
            "invoice_id": s["id"],
            "date": "2026-10-22",
            "amount": 50,
            "request_id": "once",
        }
        self.assertEqual(
            self.ok("/api/allocations", "POST", p),
            self.ok("/api/allocations", "POST", p),
        )
        self.assertEqual(len(self.ok("/api/settlements")["allocations"]), 1)
        self.ok("/api/periods", "POST", {"through": "2026-10-22", "reason": "إقفال"})
        self.assertEqual(
            self.client.call("/api/allocations", "POST", {**p, "request_id": "new"})[0],
            400,
        )

    def test_bank_receipt_posts_bank_and_allocation_agrees_with_ledger(self):
        b = self.bank()
        s = self.sale()
        r = self.receipt(100, bank_id=b["id"], reference="إيداع-1")
        self.allocate(r, s, 100)
        state = self.ok("/api/banking")
        self.assertEqual(state["banks"][0]["balance"], 510000)
        with connect(self.path) as c:
            self.assertEqual(
                c.execute(
                    "SELECT sum(debit-credit) FROM journal WHERE account='الصندوق'"
                ).fetchone()[0],
                5000,
            )
        self.assertEqual(self.state()["customers"][0]["balance"], 4000)
        self.balanced()

    def test_bank_transfer_conserves_cash_and_bank_balance_and_rejects_future_funding(
        self,
    ):
        b = self.bank()
        second = self.bank(opening=0, name="بنك ثان")
        self.ok(
            "/api/banking/transfers",
            "POST",
            {
                "date": "2026-10-22",
                "source_bank": b["id"],
                "target_bank": second["id"],
                "amount": 250,
                "note": "تحويل",
            },
        )
        st = self.ok("/api/banking")
        self.assertEqual([x["balance"] for x in st["banks"]], [475000, 25000])
        self.balanced()
        future = self.bank(opening=1000, name="رصيد مستقبلي", date="2026-12-01")
        self.assertEqual(
            self.client.call(
                "/api/banking/transfers",
                "POST",
                {
                    "date": "2026-10-22",
                    "source_bank": future["id"],
                    "amount": 10,
                    "note": "سحب",
                },
            )[0],
            400,
        )

    def test_bank_statement_reconciliation_carries_pending_into_next_period(self):
        b = self.bank()
        r = self.receipt(1000, bank_id=b["id"], date="2026-10-10")
        self.ok(
            "/api/banking/transfers",
            "POST",
            {
                "date": "2026-10-20",
                "source_bank": b["id"],
                "amount": 500,
                "note": "تحويل للصندوق",
            },
        )
        s = self.ok(
            "/api/banking/statements",
            "POST",
            {
                "bank_id": b["id"],
                "reference": "OCT",
                "from_date": "2026-10-01",
                "to_date": "2026-10-31",
                "opening": 5000,
                "closing": 6000,
                "lines": [{"date": "2026-10-11", "amount": 1000, "reference": "إيداع"}],
            },
        )
        move = next(
            x for x in self.ok("/api/banking")["moves"] if x["document"] == r["number"]
        )
        self.ok(
            f'/api/banking/statements/{s["id"]}/match',
            "POST",
            {"line_id": s["lines"][0]["id"], "move_id": move["id"]},
        )
        final = self.ok(f'/api/banking/statements/{s["id"]}/finalize', "POST")
        self.assertEqual(final["book_closing"], 550000)
        self.assertEqual(final["unmatched_book"], -50000)
        second = self.ok(
            "/api/banking/statements",
            "POST",
            {
                "bank_id": b["id"],
                "reference": "NOV",
                "from_date": "2026-11-01",
                "to_date": "2026-11-30",
                "opening": 6000,
                "closing": 5500,
                "lines": [{"date": "2026-11-03", "amount": -500}],
            },
        )
        pending = next(
            x for x in self.ok("/api/banking")["moves"] if x["amount"] == -50000
        )
        self.ok(
            f'/api/banking/statements/{second["id"]}/match',
            "POST",
            {"line_id": second["lines"][0]["id"], "move_id": pending["id"]},
        )
        final = self.ok(f'/api/banking/statements/{second["id"]}/finalize', "POST")
        self.assertEqual(final["unmatched_book"], 0)
        self.balanced()

    def test_bank_match_cannot_use_wrong_account_amount_or_duplicate_move(self):
        b = self.bank()
        other = self.bank(name="بنك آخر")
        r = self.receipt(100, bank_id=b["id"])
        moves = self.ok("/api/banking")["moves"]
        m = next(x for x in moves if x["document"] == r["number"])
        s = self.ok(
            "/api/banking/statements",
            "POST",
            {
                "bank_id": other["id"],
                "reference": "WRONG",
                "from_date": "2026-10-01",
                "to_date": "2026-10-31",
                "opening": 5000,
                "closing": 5100,
                "lines": [{"date": "2026-10-22", "amount": 100}],
            },
        )
        self.assertEqual(
            self.client.call(
                f'/api/banking/statements/{s["id"]}/match',
                "POST",
                {"line_id": s["lines"][0]["id"], "move_id": m["id"]},
            )[0],
            400,
        )
        self.assertEqual(
            self.client.call(f'/api/banking/statements/{s["id"]}/finalize', "POST")[0],
            400,
        )
        self.assertEqual(
            self.client.call(
                "/api/banking/statements",
                "POST",
                {
                    "bank_id": b["id"],
                    "reference": "BAD",
                    "from_date": "2026-10-01",
                    "to_date": "2026-10-31",
                    "opening": 5000,
                    "closing": 5100,
                    "lines": [],
                },
            )[0],
            400,
        )

    def test_bank_fee_must_be_posted_before_matching_and_final_cannot_change(self):
        b = self.bank()
        self.ok(
            "/api/expenses",
            "POST",
            {
                "date": "2026-10-22",
                "bank_id": b["id"],
                "amount": 10,
                "category": "رسوم بنكية",
                "note": "رسوم",
            },
        )
        s = self.ok(
            "/api/banking/statements",
            "POST",
            {
                "bank_id": b["id"],
                "reference": "FEE",
                "from_date": "2026-10-01",
                "to_date": "2026-10-31",
                "opening": 5000,
                "closing": 4990,
                "lines": [{"date": "2026-10-22", "amount": -10}],
            },
        )
        m = next(x for x in self.ok("/api/banking")["moves"] if x["amount"] == -1000)
        self.ok(
            f'/api/banking/statements/{s["id"]}/match',
            "POST",
            {"line_id": s["lines"][0]["id"], "move_id": m["id"]},
        )
        self.ok(f'/api/banking/statements/{s["id"]}/finalize', "POST")
        self.assertEqual(
            self.client.call(
                f'/api/banking/statements/{s["id"]}/match',
                "POST",
                {"line_id": s["lines"][0]["id"], "move_id": None},
            )[0],
            400,
        )
        self.assertEqual(
            self.client.call(
                "/api/receipts",
                "POST",
                {
                    "customer_id": self.cid,
                    "bank_id": b["id"],
                    "date": "2026-10-22",
                    "amount": 20,
                },
            )[0],
            400,
        )
        self.assertEqual(self.ok("/api/banking")["banks"][0]["balance"], 499000)
        self.balanced()

    def test_warehouse_transfer_preserves_total_value_without_fictional_journal(self):
        wid = self.warehouse()
        with connect(self.path) as c:
            n = c.execute("SELECT count(*) FROM journal").fetchone()[0]
        t = self.transfer(wid, 30)
        st = self.ok("/api/warehouse-stock")
        self.assertEqual([r["qty"] for r in st], [70, 30])
        self.assertEqual(sum(r["value"] for r in st), 400000)
        with connect(self.path) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM journal").fetchone()[0], n)
        self.assertEqual(
            self.client.call(f'/api/transfers/{t["id"]}/post', "POST")[0], 400
        )
        self.ok(f'/api/transfers/{t["id"]}/cancel', "POST", {"reason": "عكس"})
        self.assertEqual(self.state()["products"][0]["qty"], 100)
        self.balanced()

    def test_sale_consumes_only_selected_warehouse_and_return_restores_it(self):
        wid = self.warehouse()
        self.transfer(wid, 2)
        s = self.sale(warehouse_id=wid)
        st = self.ok("/api/warehouse-stock")
        self.assertEqual([x["qty"] for x in st], [98, 0])
        d = self.draft(warehouse_id=wid)
        self.assertEqual(
            self.client.call(f'/api/invoices/{d["id"]}/post', "POST")[0], 400
        )
        self.ok(
            "/api/returns",
            "POST",
            {
                "invoice_id": s["id"],
                "date": "2026-10-22",
                "reason": "مرتجع",
                "lines": [{"sale_line_id": s["lines"][0]["id"], "qty": 1}],
            },
        )
        self.assertEqual([x["qty"] for x in self.ok("/api/warehouse-stock")], [98, 1])
        self.balanced()

    def test_warehouse_purchase_and_cross_warehouse_return_values(self):
        wid = self.warehouse()
        sid = self.ok("/api/suppliers", "POST", {"name": "مورد"})["id"]
        p = self.ok(
            "/api/purchases",
            "POST",
            {
                "supplier_id": sid,
                "warehouse_id": wid,
                "date": "2026-10-22",
                "lines": [{"product_id": self.pid, "qty": 2, "cost": 60}],
            },
        )
        self.ok(f'/api/purchases/{p["id"]}/post', "POST")
        s = self.sale(warehouse_id=wid)
        self.assertEqual(s["cost"], 12000)
        self.assertEqual(s["lines"][0]["cost"], 6000)
        self.ok(
            "/api/returns",
            "POST",
            {
                "invoice_id": s["id"],
                "warehouse_id": 1,
                "date": "2026-10-22",
                "reason": "إلى الرئيسي",
                "lines": [{"sale_line_id": s["lines"][0]["id"], "qty": 1}],
            },
        )
        stocks = self.ok("/api/warehouse-stock")
        self.assertEqual(stocks[0]["qty"], 101)
        self.assertEqual(stocks[0]["value"], 406000)
        self.balanced()

    def test_transfer_duplicate_lines_rollback_and_later_movements_block_reversal(self):
        wid = self.warehouse()
        t = self.ok(
            "/api/transfers",
            "POST",
            {
                "date": "2026-10-22",
                "source_id": 1,
                "target_id": wid,
                "lines": [{"product_id": self.pid, "qty": 60}] * 2,
            },
        )
        self.assertEqual(
            self.client.call(f'/api/transfers/{t["id"]}/post', "POST")[0], 400
        )
        self.assertEqual(self.state()["products"][0]["qty"], 100)
        t = self.transfer(wid, 10)
        self.sale(warehouse_id=wid)
        self.assertEqual(
            self.client.call(
                f'/api/transfers/{t["id"]}/cancel', "POST", {"reason": "عكس"}
            )[0],
            400,
        )

    def test_fractional_average_value_conserved_across_warehouses_and_sales(self):
        pid = self.ok(
            "/api/products",
            "POST",
            {
                "name": "صنف كسور",
                "price": 1,
                "cost": ".01",
                "qty": 1,
                "opening_date": "2026-01-01",
            },
        )["id"]
        supplier = self.ok("/api/suppliers", "POST", {"name": "مورد الكسور"})["id"]
        p = self.ok(
            "/api/purchases",
            "POST",
            {
                "supplier_id": supplier,
                "date": "2026-10-22",
                "lines": [{"product_id": pid, "qty": 2, "cost": ".02"}],
            },
        )
        self.ok(f'/api/purchases/{p["id"]}/post', "POST")
        wid = self.warehouse()
        t = self.ok(
            "/api/transfers",
            "POST",
            {
                "date": "2026-10-22",
                "source_id": 1,
                "target_id": wid,
                "lines": [{"product_id": pid, "qty": 1}],
            },
        )
        self.ok(f'/api/transfers/{t["id"]}/post', "POST")
        a = self.sale(
            warehouse_id=1,
            discount=0,
            paid=0,
            lines=[{"product_id": pid, "qty": 2, "price": 1}],
        )
        b = self.sale(
            warehouse_id=wid,
            discount=0,
            paid=0,
            lines=[{"product_id": pid, "qty": 1, "price": 1}],
        )
        self.assertEqual(a["cost"] + b["cost"], 5)
        rows = [r for r in self.ok("/api/warehouse-stock") if r["product_id"] == pid]
        self.assertEqual(sum(r["qty"] for r in rows), 0)
        self.assertEqual(sum(r["value"] for r in rows), 0)
        self.balanced()

    def test_upgrade_is_repeatable_and_role_permissions_hold(self):
        wid = self.warehouse()
        self.transfer(wid)
        before = self.ok("/api/warehouse-stock")
        create_app(self.path)
        create_app(self.path)
        self.assertEqual(before, self.ok("/api/warehouse-stock"))
        self.ok(
            "/api/users",
            "POST",
            {"name": "seller-v3", "password": "Test-Password-123", "role": "sales"},
        )
        other = support.Client(self.app)
        other.call(
            "/api/login", "POST", {"name": "seller-v3", "password": "Test-Password-123"}
        )
        for path in (
            "/api/banks",
            "/api/transfers",
            "/api/warehouses",
            "/api/banking/transfers",
        ):
            self.assertNotEqual(other.call(path, "POST", {})[0], 200)


if __name__ == "__main__":
    unittest.main()
