"""Validate operations, reload and portable persistence with storage disabled."""

from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading, tempfile, json, os
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path("/workspace/.cloud-setup/offline-mobile")


class Quiet(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kw):
        super().__init__(*args, directory=str(BUILD), **kw)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
fixture = {
    "customers": [{"id": "c1", "name": "عميل <اختبار>", "limit": 0, "phone": "000"}],
    "products": [
        {
            "id": "p1",
            "name": "كرت اختبار",
            "qty": 20,
            "cost": 40,
            "price": 100,
            "service": False,
        }
    ],
    "sales": [],
    "journal": [
        {
            "ref": "OPEN",
            "date": "2026-01-01",
            "account": "المخزون",
            "debit": 800,
            "credit": 0,
        },
        {
            "ref": "OPEN",
            "date": "2026-01-01",
            "account": "رأس المال والأرصدة الافتتاحية",
            "debit": 0,
            "credit": 800,
        },
    ],
    "stockMoves": [],
}
try:
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        b = pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        for blocked in (False, True):
            ctx = b.new_context(
                viewport={"width": 390, "height": 844}, accept_downloads=True
            )
            if blocked:
                ctx.add_init_script(
                    "Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError')}})"
                )
            p = ctx.new_page()
            errors = []
            requests = []
            p.on("pageerror", lambda e: errors.append(str(e)))
            p.on("request", lambda r: requests.append(r.url))
            p.on("dialog", lambda d: d.accept())
            p.goto(base + "/WIFI-HOME-OFFLINE.html#settings")
            p.locator("#import-file").set_input_files(
                {
                    "name": "synthetic.json",
                    "mimeType": "application/json",
                    "buffer": json.dumps({"data": fixture}).encode(),
                }
            )
            p.get_by_role("status").filter(has_text="تم استيراد").wait_for()
            p.locator("#new-sale").click()
            p.locator("#invoice-form [name=customerId]").select_option("c1")
            p.locator("#invoice-form [name=date]").fill("2026-10-22")
            p.locator('[data-line="0"][data-key="productId"]').select_option("p1")
            p.locator('[data-line="0"][data-key="qty"]').fill("2")
            p.locator("#invoice-form [name=payType]").select_option("mixed")
            p.locator("#invoice-form [name=paid]").fill("50")
            p.locator("#invoice-form [name=discount]").fill("10")
            p.locator("#invoice-form button[type=submit]").click()
            p.wait_for_url("**#invoice/INV-00001")
            p.locator('[data-edit="INV-00001"]').first.click()
            p.locator('[data-line="0"][data-key="qty"]').fill("3")
            p.locator("#invoice-form [name=reason]").fill("تصحيح كمية تجريبي")
            p.locator("#invoice-form button[type=submit]").click()
            p.wait_for_url("**#invoice/INV-00001")
            p.locator('nav a[href="#cash"]').click()
            p.locator("[data-action=receipt]").click()
            p.locator("#modal-form [name=customerId]").select_option("c1")
            p.locator("#modal-form [name=amount]").fill("100")
            p.locator("#modal-form [name=date]").fill("2026-10-22")
            p.locator("#modal-form [name=note]").fill("قبض اختبار")
            p.locator("#modal-form button:not([type])").click()
            p.locator("#modal").wait_for(state="hidden")
            with p.expect_download() as dl:
                p.locator("#backup").click()
            data = json.loads(Path(dl.value.path()).read_text())["data"]
            assert data["products"][0]["qty"] == 17
            assert data["sales"][0]["total"] == 290
            assert data["sales"][0]["revision"] == 2
            assert (
                sum(
                    j["debit"] - j["credit"]
                    for j in data["journal"]
                    if j["account"] == "الصندوق"
                )
                == 150
            )
            assert (
                sum(
                    j["debit"] - j["credit"]
                    for j in data["journal"]
                    if j["account"] == "العملاء"
                )
                == 140
            )
            assert round(sum(j["debit"] - j["credit"] for j in data["journal"]), 2) == 0
            with p.expect_download() as dl:
                p.locator("[data-offline=save-header]").click()
            snapshot = BUILD / (
                "saved-blocked.html" if blocked else "saved-normal.html"
            )
            dl.value.save_as(str(snapshot))
            p.goto(base + "/" + snapshot.name + "#customers")
            p.get_by_text("عميل <اختبار>", exact=True).wait_for()
            with p.expect_download() as dl:
                p.locator("#backup").click()
            restored = json.loads(Path(dl.value.path()).read_text())["data"]
            assert restored == data, "Portable snapshot changed data"
            if not blocked:
                p.reload()
                p.get_by_text("عميل <اختبار>", exact=True).wait_for()
            p.goto(base + "/" + snapshot.name + "#invoice/INV-00001")
            p.locator("[data-action=print]").click()
            p.frame_locator("#offline-document iframe").get_by_text(
                "INV-00001", exact=True
            ).wait_for()
            assert not errors, errors
            assert all(u.startswith(base) for u in requests), requests
            snapshot.unlink()
            ctx.close()
        b.close()
    print(
        "Offline browser: sale, amendment, receipt, exact balances, JSON, HTML snapshot, reload and independent invoice passed with storage available AND blocked."
    )
finally:
    server.shutdown()
    server.server_close()
