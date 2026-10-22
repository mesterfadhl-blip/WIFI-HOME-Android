from pathlib import Path
from playwright.sync_api import sync_playwright
import secrets
import os

BASE = os.environ.get("ERP_TEST_URL", "http://127.0.0.1:8085").rstrip("/")
out = Path(os.environ.get("ERP_REVIEW_DIR", "/workspace/erp-review"))
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    c = b.new_context(viewport={"width": 1440, "height": 1000})
    page = c.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    assert not c.request.get(BASE + "/api/status").json()[
        "configured"
    ], "Use a fresh dedicated test database; never run this scenario on live data"
    page.goto(BASE + "/")
    page.locator("#login [name=name]").fill("operations-review")
    page.locator("#login [name=password]").fill("Review-" + secrets.token_urlsafe(16))
    page.locator("#login button").click()
    page.get_by_role("heading", name="فواتير المبيعات", exact=True).wait_for()
    page.locator('nav a[href="#finance"]').click()
    page.locator("[data-op=funding]").click()
    page.locator("#modal [name=amount]").fill("10000")
    page.locator("#modal [name=note]").fill("رأس مال تجريبي — ليس إيراداً")
    page.locator("#operation-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator('nav a[href="#customers"]').click()
    page.locator("[data-action=customer]").click()
    page.locator("#modal [name=name]").fill("عميل دورة اختبار")
    page.locator("#modal-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator('nav a[href="#products"]').click()
    page.locator("[data-action=product]").click()
    page.locator("#modal [name=name]").fill("كرت — بيانات اختبار")
    page.locator("#modal [name=price]").fill("100")
    page.locator("#modal [name=cost]").fill("40")
    page.locator("#modal [name=qty]").fill("100")
    page.locator("#modal-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator('nav a[href="#suppliers"]').click()
    page.locator("[data-op=supplier]").click()
    page.locator("#modal [name=name]").fill("مورد دورة اختبار")
    page.locator("#operation-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator('nav a[href="#purchases"]').click()
    page.locator("[data-op=new-purchase]").click()
    page.locator("#purchase-form").wait_for()
    page.locator("[name=supplier_id]").select_option("1")
    page.locator("[data-pkey=product_id]").select_option("1")
    page.locator("[data-pkey=qty]").fill("100")
    page.locator("[data-pkey=cost]").fill("60")
    page.locator("[name=paid]").fill("1000")
    page.get_by_role("button", name="حفظ المسودة", exact=True).click()
    page.wait_for_url("**/#purchase/1")
    page.locator("[data-op=post-purchase]").wait_for()
    page.locator("[data-op=post-purchase]").click()
    page.locator('a[href="/print/purchases/1"]').wait_for()
    page.screenshot(path=str(out / "purchase-workspace.png"), full_page=True)
    page.locator('nav a[href="#sales"]').click()
    page.locator("[data-action=new-invoice]").click()
    page.locator("#invoice-form").wait_for()
    page.locator("[name=customer_id]").select_option("1")
    page.locator("[data-key=product_id]").select_option("1")
    page.locator("[data-key=qty]").fill("2")
    page.locator("[name=paid]").fill("50")
    page.locator("[name=discount]").fill("10")
    page.get_by_role("button", name="حفظ المسودة", exact=True).click()
    page.wait_for_url("**/#invoice/1")
    page.locator("[data-action=post]").wait_for()
    page.once("dialog", lambda d: d.accept())
    page.locator("[data-action=post]").click()
    page.locator("[data-action=amend]").wait_for()
    page.locator('nav a[href="#returns"]').click()
    page.locator("#choose-return [name=invoice_id]").select_option("1")
    page.get_by_role("button", name="فتح بنود الفاتورة").click()
    page.locator("#return-form").wait_for()
    page.locator("[data-return-line]").fill("1")
    page.locator("[name=refund]").fill("20")
    page.locator("[name=reason]").fill("إرجاع بند — بيانات اختبار")
    page.get_by_role("button", name="اعتماد إشعار المرتجع").click()
    page.wait_for_url("**/#return/1")
    page.locator('a[href="/print/returns/1"]').wait_for()
    page.locator('nav a[href="#finance"]').click()
    page.get_by_role("heading", name="المحاسبة والنتائج المالية", exact=True).wait_for()
    page.locator("[data-op=expense]").click()
    page.locator("#modal [name=category]").fill("تشغيل")
    page.locator("#modal [name=note]").fill("مصروف — اختبار")
    page.locator("#modal [name=amount]").fill("10")
    page.locator("#operation-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.get_by_role("heading", name="المحاسبة والنتائج المالية", exact=True).wait_for()
    page.screenshot(path=str(out / "finance-workspace.png"), full_page=True)
    response = c.request.get(BASE + "/api/finance")
    assert response.ok, response.text()
    f = response.json()
    assert f["net_sales"] == 9500
    assert f["cost"] == 5000
    assert f["expenses"] == 1000
    assert f["net_profit"] == 3500
    assert f["stock_value"] == 995000
    assert f["debits"] == f["credits"]
    assert c.request.get(BASE + "/api/reports").json()["totals"]["total"] == 9500
    for route, filename in [
        ("/print/purchases/1", "purchase"),
        ("/print/returns/1", "credit-note"),
        (
            "/print/supplier?supplier=1&from=2026-01-01&to=2026-12-31",
            "supplier-statement",
        ),
        ("/print/finance?from=2026-01-01&to=2026-12-31", "profit-trial-balance"),
    ]:
        page.goto(BASE + "" + route)
        page.locator("article").wait_for()
        assert page.locator("nav").count() == 0
        page.pdf(
            path=str(out / (filename + ".pdf")),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
        )
    mobile = c.new_page()
    mobile.set_viewport_size({"width": 390, "height": 844})
    mobile.goto(BASE + "/#finance")
    mobile.get_by_role(
        "heading", name="المحاسبة والنتائج المالية", exact=True
    ).wait_for()
    mobile.screenshot(path=str(out / "mobile-finance.png"), full_page=True)
    assert not errors, errors
    print(
        "Browser: purchase draft/post, weighted stock, sale, partial return, expense, financial totals, mobile and four independent PDFs passed"
    )
    b.close()
