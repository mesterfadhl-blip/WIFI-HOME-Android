"""Exercise the new modules in a fresh synthetic database, never live data."""

from pathlib import Path
import sys, threading, json
from wsgiref.simple_server import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from test_erp_enterprise import EnterpriseTests
from playwright.sync_api import sync_playwright


class Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


t = EnterpriseTests()
t.setUp()
server = None
out = Path("/workspace/.cloud-setup/enterprise-review")
out.mkdir(exist_ok=True, parents=True)
try:
    t.ok("/api/suppliers", "POST", {"name": "مورد معاينة"})
    server = make_server("127.0.0.1", 0, t.app, handler_class=Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    with sync_playwright() as pw:
        b = pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        c = b.new_context(viewport={"width": 1440, "height": 1000})
        c.add_cookies(
            [
                {
                    "name": "erp_session",
                    "value": t.client.cookie.split("=", 1)[1],
                    "url": base,
                }
            ]
        )
        page = c.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())
        page.goto(base + "/#procurement")
        page.get_by_role(
            "heading", name="دورة الشراء والاستلام والمرتجعات", exact=True
        ).wait_for()
        page.get_by_role("link", name="أمر شراء جديد", exact=True).click()
        page.locator("#order-form [name=supplier_id]").select_option("1")
        page.locator("#order-form [name=date]").fill("2026-10-22")
        page.locator('[data-ol="0"][data-key=product_id]').select_option("1")
        page.locator('[data-ol="0"][data-key=qty]').fill("10")
        page.locator('[data-ol="0"][data-key=cost]').fill("50")
        page.get_by_role("button", name="حفظ مسودة الأمر", exact=True).click()
        page.wait_for_url("**/#order/1")
        page.locator("[data-ent=approve-order]").click()
        page.locator("#receive-order").wait_for()
        page.locator("#receive-order [name=date]").fill("2026-10-22")
        page.locator("[data-receive-line]").fill("5")
        page.get_by_role("button", name="ترحيل استلام المخزون", exact=True).click()
        page.wait_for_url("**/#goods/1")
        page.locator("#invoice-goods").wait_for()
        page.locator("#invoice-goods [name=date]").fill("2026-10-22")
        page.get_by_role(
            "button", name="إنشاء فاتورة للمراجعة والترحيل", exact=True
        ).click()
        page.wait_for_url("**/#purchase/1")
        page.get_by_role("button", name="ترحيل واستلام", exact=True).click()
        page.locator('a[href="/print/purchases/1"]').wait_for()
        assert t.state()["products"][0]["qty"] == 105
        page.locator('nav a[href="#procurement"]').click()
        page.locator("#choose-supplier-return [name=purchase_id]").select_option("1")
        page.get_by_role("button", name="تحديد البنود المرتجعة", exact=True).click()
        page.locator("#supplier-return-form [name=date]").fill("2026-10-22")
        page.locator("#supplier-return-form [name=reason]").fill("مرتجع معاينة")
        page.locator("[data-pr-line]").fill("2")
        page.get_by_role("button", name="ترحيل مرتجع المورد", exact=True).click()
        page.wait_for_url("**/#supplier-return/1")
        assert t.state()["products"][0]["qty"] == 103
        page.locator('nav a[href="#migration"]').click()
        fixture = out / "synthetic-old-backup.json"
        fixture.write_text(json.dumps(t.legacy()["backup"], ensure_ascii=False))
        page.locator("#legacy-form [name=file]").set_input_files(str(fixture))
        page.locator("#legacy-form [name=date]").fill("2026-10-22")
        page.locator("#legacy-form [name=include_balances]").check()
        page.get_by_role("button", name="قراءة الملف ومعاينة النقل", exact=True).click()
        page.locator("[data-ent=commit-legacy]").wait_for()
        page.screenshot(path=str(out / "customer-import-review.png"), full_page=True)
        page.locator("[data-ent=commit-legacy]").click()
        page.wait_for_url("**/#customers")
        page.locator("tbody tr").filter(has_text="عميل من النسخة").wait_for()
        page.locator("tbody tr").filter(has_text="عميل من النسخة").locator(
            '[data-ent="customer-edit"]'
        ).click()
        page.locator("#directory-form [name=phone]").fill("999777")
        page.locator("#directory-form [name=credit_limit]").fill("500")
        page.locator("#directory-form button:not([type])").click()
        page.locator("#modal").wait_for(state="hidden")
        page.get_by_text("999777", exact=True).wait_for()
        page.locator('nav a[href="#position"]').click()
        page.locator("#position-form [name=asof]").fill("2026-10-22")
        page.locator("#position-form button").click()
        page.get_by_text("المعادلة متوازنة", exact=False).wait_for()
        page.screenshot(path=str(out / "financial-position.png"), full_page=True)
        mobile = c.new_page()
        mobile.set_viewport_size({"width": 390, "height": 844})
        mobile.goto(base + "/#procurement")
        mobile.get_by_role(
            "heading", name="دورة الشراء والاستلام والمرتجعات", exact=True
        ).wait_for()
        mobile.screenshot(path=str(out / "procurement-mobile.png"), full_page=True)
        for path, name in [
            ("/print/position?asof=2026-10-22", "financial-position"),
            ("/print/goods-receipts/1", "goods-receipt"),
            ("/print/supplier-returns/1", "supplier-return"),
        ]:
            doc = c.new_page()
            doc.goto(base + path)
            doc.pdf(path=str(out / (name + ".pdf")), format="A4", print_background=True)
            doc.close()
        assert not errors, errors
        print(
            "Browser: order -> partial receipt -> matched invoice -> supplier return -> reviewed customer import -> balanced position passed, desktop and mobile."
        )
        b.close()
finally:
    if server:
        server.shutdown()
        server.server_close()
    t.tearDown()
