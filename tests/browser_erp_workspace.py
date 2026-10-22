from pathlib import Path
import secrets
import os
from datetime import datetime, timezone, timedelta
from calendar import monthrange
from playwright.sync_api import sync_playwright

out = Path(os.environ.get("ERP_REVIEW_DIR", "/workspace/erp-v3-review"))
out.mkdir(parents=True, exist_ok=True)
BASE = os.environ.get("ERP_TEST_URL", "http://127.0.0.1:8088").rstrip("/")
D = datetime.now(timezone(timedelta(hours=3))).date()
DAY = D.isoformat()
FIRST = D.replace(day=1).isoformat()
LAST = D.replace(day=monthrange(D.year, D.month)[1]).isoformat()
BEFORE = (D.replace(day=1) - timedelta(days=1)).isoformat()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    c = b.new_context(viewport={"width": 1440, "height": 1000})
    page = c.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    assert not c.request.get(BASE + "/api/status").json()[
        "configured"
    ], "Use a fresh dedicated test database, never live data"
    page.goto(BASE + "/")
    page.locator("#login [name=name]").fill("review-v3")
    page.locator("#login [name=password]").fill("Review-" + secrets.token_urlsafe(16))
    page.locator("#login button").click()
    page.get_by_role("heading", name="فواتير المبيعات", exact=True).wait_for()
    page.locator('nav a[href="#customers"]').click()
    page.locator("[data-action=customer]").click()
    page.locator("#modal [name=name]").fill("عميل المعاينة — بيانات اختبار")
    page.locator("#modal-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator('nav a[href="#products"]').click()
    page.locator("[data-action=product]").click()
    page.locator("#modal [name=name]").fill("كرت معاينة")
    page.locator("#modal [name=price]").fill("100")
    page.locator("#modal [name=cost]").fill("40")
    page.locator("#modal [name=qty]").fill("100")
    page.locator("#modal-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator('nav a[href="#warehouses"]').click()
    page.locator("[data-v3=warehouse]").click()
    page.locator("#v3-form [name=name]").fill("مستودع الفرع — معاينة")
    page.locator("#v3-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator("[data-v3=transfer-new]").click()
    page.locator("#transfer-form").wait_for()
    page.locator("[name=target_id]").select_option("2")
    page.locator("[data-tkey=product_id]").select_option("1")
    page.locator("[data-tkey=qty]").fill("20")
    page.get_by_role("button", name="حفظ المسودة", exact=True).click()
    page.wait_for_url("**/#transfer/1")
    page.locator("[data-v3=transfer-post]").wait_for()
    page.locator("[data-v3=transfer-post]").click()
    page.locator('a[href="/print/transfers/1"]').wait_for()
    page.screenshot(path=str(out / "transfer-workspace.png"), full_page=True)
    page.locator('nav a[href="#sales"]').click()
    page.locator("[data-action=new-invoice]").click()
    page.locator("#invoice-form").wait_for()
    page.locator("[name=customer_id]").select_option("1")
    page.locator("[name=warehouse_id]").select_option("2")
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
    assert (
        "المتبقي الفعلي" in page.locator("#view").inner_text()
        if page.locator("#view").count()
        else "المتبقي الفعلي" in page.locator(".workspace").inner_text()
    )
    page.locator('nav a[href="#banks"]').click()
    page.locator("[data-v3=bank]").click()
    page.locator("#v3-form [name=name]").fill("بنك المعاينة")
    page.locator("#v3-form [name=date]").fill(BEFORE)
    page.locator("#v3-form [name=opening]").fill("5000")
    page.locator("#v3-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator('nav a[href="#customers"]').click()
    page.locator("[data-action=receipt]").click()
    page.locator("#modal [name=customer_id]").select_option("1")
    page.locator("#modal [name=amount]").fill("100")
    page.locator("#modal [name=bank_id]").select_option("1")
    page.locator("#modal-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator('nav a[href="#settlements"]').click()
    page.locator("[data-v3=allocation]").click()
    page.locator("#allocation-receipt").select_option("1")
    page.locator("#allocation-invoice").select_option("1")
    page.locator("#v3-form [name=amount]").fill("100")
    page.locator("#v3-form button:not([type])").click()
    page.locator("#modal").wait_for(state="hidden")
    page.locator("[data-release]").wait_for()
    page.screenshot(path=str(out / "settlements-workspace.png"), full_page=True)
    page.locator('nav a[href="#banks"]').click()
    page.locator("[data-v3=statement-import]").click()
    page.locator("#v3-form [name=bank_id]").select_option("1")
    page.locator("#v3-form [name=reference]").fill("معاينة كشف البنك")
    page.locator("#v3-form [name=from_date]").fill(FIRST)
    page.locator("#v3-form [name=to_date]").fill(LAST)
    page.locator("#v3-form [name=opening]").fill("5000")
    page.locator("#v3-form [name=closing]").fill("5100")
    page.locator("#statement-csv").fill(
        "date,amount,reference,note\n" + DAY + ",100,DEPOSIT-1,إيداع اختبار"
    )
    page.locator("#v3-form button:not([type])").click()
    page.wait_for_url("**/#bank-statement/1")
    page.locator("[data-match-line]").wait_for()
    state = c.request.get(BASE + "/api/banking").json()
    mid = next(m["id"] for m in state["moves"] if m["document"] == "RC-000001")
    page.locator("[data-match-line]").select_option(str(mid))
    page.wait_for_timeout(150)
    page.locator("[data-finalize]").click()
    page.get_by_text("رصيد الدفاتر المعتمد", exact=True).wait_for()
    page.screenshot(path=str(out / "bank-reconciliation-workspace.png"), full_page=True)
    invoice = c.request.get(BASE + "/api/invoices/1").json()
    assert invoice["settlement"]["outstanding"] == 4000
    assert invoice["warehouse_id"] == 2
    stock = c.request.get(BASE + "/api/warehouse-stock").json()
    assert [s["qty"] for s in stock] == [80, 18]
    assert sum(s["value"] for s in stock) == 392000
    for route, name in [
        ("/print/invoices/1", "settled-invoice"),
        ("/print/transfers/1", "warehouse-transfer"),
        ("/print/aging?asof=" + DAY, "receivable-aging"),
        ("/print/bank-statements/1", "bank-reconciliation"),
    ]:
        page.goto(BASE + route)
        page.locator("article").wait_for()
        page.pdf(
            path=str(out / (name + ".pdf")),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
        )
    mobile = c.new_page()
    mobile.set_viewport_size({"width": 390, "height": 844})
    mobile.goto(BASE + "/#settlements")
    mobile.get_by_role(
        "heading", name="تخصيص التحصيل وأعمار الديون", exact=True
    ).wait_for()
    mobile.screenshot(path=str(out / "mobile-settlements.png"), full_page=True)
    assert not errors, errors
    print(
        "Browser: transfer, warehouse-specific sale, bank receipt, allocation, CSV import/match/finalize, four A4 outputs and mobile passed"
    )
    b.close()
