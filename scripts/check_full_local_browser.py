"""Check the same ERP in WASM, offline networking, private seed and portable backup."""

from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading, json, tempfile, sqlite3
from playwright.sync_api import sync_playwright

DIR = Path("/workspace/.cloud-setup/full-local")


class Quiet(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIR), **kwargs)

    def log_message(self, *args):
        pass


s = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
threading.Thread(target=s.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{s.server_port}"
try:
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        b = pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        ctx = b.new_context(
            viewport={"width": 390, "height": 844}, accept_downloads=True
        )
        ctx.add_init_script(
            "Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError')}});Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true})"
        )
        p = ctx.new_page()
        errors = []
        requests = []
        p.on("pageerror", lambda e: errors.append(str(e)))
        p.on("request", lambda r: requests.append(r.url))
        p.on("dialog", lambda d: d.accept())
        p.goto(base + "/private.html", wait_until="domcontentloaded")
        ctx.set_offline(True)
        p.locator("#login").wait_for(timeout=45000)
        p.locator("#login [name=name]").fill("local-review")
        p.locator("#login [name=password]").fill("Synthetic-Review-Password-123")
        p.locator("#login button").click()
        p.get_by_role("heading", name="فواتير المبيعات", exact=True).wait_for(
            timeout=30000
        )

        def api(path, data=None):
            return p.evaluate(
                """async ([path,data])=>{const r=await fetch(path,{method:data?'POST':'GET',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf},...(data?{body:JSON.stringify(data)}:{})});const v=await r.json();if(!r.ok)throw Error(v.error);return v;}""",
                [path, data],
            )

        state = api("/api/bootstrap")
        assert (
            len(state["customers"]) == 18
            and len(state["products"]) == 10
            and len(state["invoices"]) == 1
        )
        assert sum(x["balance"] for x in state["customers"]) == 0
        assert api("/api/position?asof=2026-10-22")["asset_total"] == 900000
        cid = state["customers"][0]["id"]
        supplier = api("/api/suppliers", {"name": "مورد اختبار محلي"})["id"]
        pid = api(
            "/api/products",
            {"name": "صنف اختبار محلي", "price": 100, "cost": 40, "qty": 0},
        )["id"]
        order = api(
            "/api/purchase-orders",
            {
                "supplier_id": supplier,
                "date": "2026-10-22",
                "lines": [{"product_id": pid, "qty": 10, "cost": 50}],
            },
        )
        api(f'/api/purchase-orders/{order["id"]}/approve', {})
        goods = api(
            f'/api/purchase-orders/{order["id"]}/receive',
            {
                "date": "2026-10-22",
                "warehouse_id": 1,
                "lines": [{"order_line_id": order["lines"][0]["id"], "qty": 5}],
            },
        )
        purchase = api(
            f'/api/goods-receipts/{goods["id"]}/invoice', {"date": "2026-10-22"}
        )
        purchase = api(f'/api/purchases/{purchase["id"]}/post', {})
        inv = api(
            "/api/invoices",
            {
                "customer_id": cid,
                "date": "2026-10-22",
                "due_date": "2026-10-22",
                "discount": 10,
                "paid": 50,
                "lines": [{"product_id": pid, "qty": 2, "price": 100}],
            },
        )
        inv = api(f'/api/invoices/{inv["id"]}/post', {})
        bank = api(
            "/api/banks",
            {"name": "بنك اختبار محلي", "date": "2026-01-01", "opening": 5000},
        )
        receipt = api(
            "/api/receipts",
            {
                "customer_id": cid,
                "date": "2026-10-22",
                "amount": 100,
                "bank_id": bank["id"],
            },
        )
        api(
            "/api/allocations",
            {
                "receipt_id": receipt["id"],
                "invoice_id": inv["id"],
                "date": "2026-10-22",
                "amount": 100,
            },
        )
        assert api(f'/api/invoices/{inv["id"]}')["settlement"]["outstanding"] == 4000
        api(
            "/api/returns",
            {
                "invoice_id": inv["id"],
                "date": "2026-10-22",
                "reason": "اختبار مرتجع محلي",
                "refund": 0,
                "lines": [{"sale_line_id": inv["lines"][0]["id"], "qty": 1}],
            },
        )
        api(
            "/api/supplier-returns",
            {
                "purchase_id": purchase["id"],
                "date": "2026-10-22",
                "reason": "اختبار رد للمورد",
                "lines": [{"purchase_line_id": purchase["lines"][0]["id"], "qty": 1}],
            },
        )
        position = api("/api/position?asof=2026-10-22")
        assert position["balanced"]
        # Use the original navigation and independent document without a server.
        p.locator('nav a[href="#procurement"]').click()
        p.get_by_role(
            "heading", name="دورة الشراء والاستلام والمرتجعات", exact=True
        ).wait_for()
        p.locator(f'a[href="#goods/{goods["id"]}"]').click()
        p.locator(f'a[href="/print/goods-receipts/{goods["id"]}"]').click()
        p.frame_locator("#local-document iframe").get_by_role(
            "heading", name="محضر استلام بضاعة", exact=True
        ).wait_for()
        p.locator("#local-doc-close").click()
        with p.expect_download() as dl:
            p.locator("#save-database").click()
        database = Path(tmp) / "export.sqlite3"
        dl.value.save_as(str(database))
        with sqlite3.connect(database) as c:
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("SELECT count(*) FROM customers").fetchone()[0] == 18
            assert c.execute("SELECT count(*) FROM products").fetchone()[0] == 11
            assert c.execute("SELECT sum(debit-credit) FROM journal").fetchone()[0] == 0
        with p.expect_download() as dl:
            p.locator("#save-system").click()
        snapshot = DIR / "restore-review.html"
        dl.value.save_as(str(snapshot))
        ctx.set_offline(False)
        p.goto(base + "/restore-review.html", wait_until="domcontentloaded")
        ctx.set_offline(True)
        p.locator("#login").wait_for(timeout=45000)
        p.locator("#login [name=name]").fill("local-review")
        p.locator("#login [name=password]").fill("Synthetic-Review-Password-123")
        p.locator("#login button").click()
        p.get_by_role("heading", name="فواتير المبيعات", exact=True).wait_for(
            timeout=30000
        )
        assert api("/api/position?asof=2026-10-22")["balanced"]
        assert len(api("/api/bootstrap")["products"]) == 11
        assert not errors, errors
        assert not [url for url in requests if not url.startswith(base)], requests
        snapshot.unlink()
        b.close()
    print(
        "Full WASM UI: private base data, same Python purchase/receipt/invoice/allocations/bank/customer and supplier returns, balanced position, original mobile navigation, document, SQLite export and HTML restore passed with storage blocked and network offline."
    )
finally:
    s.shutdown()
    s.server_close()
