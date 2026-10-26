"""Exercise the packaged desktop entry point against a disposable private data folder."""

from contextlib import closing
import hashlib, json, os
from pathlib import Path
import sqlite3, subprocess, sys, tempfile, urllib.request, urllib.error
from playwright.sync_api import sync_playwright

PACKAGE = Path("/workspace/.cloud-setup/deliveries/windows-private-20261026")
SEED = PACKAGE / "seed/DATABASE.sqlite3"
original_hash = hashlib.sha256(SEED.read_bytes()).hexdigest()
process = None
with tempfile.TemporaryDirectory(prefix="erp-desktop-review-") as work:
    local = Path(work) / "مساحة حفظ الكمبيوتر"
    data = local / "WIFI-HOME-ERP"
    env = dict(os.environ, LOCALAPPDATA=str(local))

    def start():
        proc = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                str(PACKAGE / "desktop_start.py"),
                "--data-dir",
                str(data),
                "--no-browser",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        while True:
            line = proc.stdout.readline()
            if line.startswith("Address: "):
                return proc, line.split(": ", 1)[1].strip()
            if not line:
                raise RuntimeError("Desktop failed: " + proc.stderr.read())

    try:
        process, base = start()
        # Re-opening the desktop command reuses this exact server and data.
        second = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                str(PACKAGE / "desktop_start.py"),
                "--data-dir",
                str(data),
                "--no-browser",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert second.returncode == 0, second.stderr
        assert "existing system window" in second.stdout
        for headers in (
            {"Origin": "https://external.invalid"},
            {"Host": "external.invalid"},
        ):
            try:
                urllib.request.urlopen(
                    urllib.request.Request(base + "api/status", headers=headers)
                )
            except urllib.error.HTTPError as e:
                assert e.code == 403
            else:
                raise AssertionError("Foreign origin/host was accepted")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path="/usr/bin/chromium", args=["--no-sandbox"]
            )
            context = browser.new_context(viewport={"width": 1440, "height": 960})
            p = context.new_page()
            errors = []
            p.on("pageerror", lambda e: errors.append(str(e)))
            p.on("dialog", lambda d: d.accept("تصحيح كمية للاختبار"))
            p.goto(base)
            p.locator("#login [name=name]").fill("desktop-review")
            p.locator("#login [name=password]").fill("Synthetic-Desktop-Password-123")
            p.locator("#login button").click()
            p.get_by_role("heading", name="فواتير المبيعات", exact=True).wait_for()

            def api(path, data=None):
                return p.evaluate(
                    """async ([path,data])=>{const r=await fetch(path,{method:data?'POST':'GET',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf},...(data?{body:JSON.stringify(data)}:{})});const result=await r.json();if(!r.ok)throw Error(result.error);return result;}""",
                    [path, data],
                )

            state = api("/api/bootstrap")
            assert (
                len(state["customers"]) == 18
                and len(state["products"]) == 10
                and len(state["invoices"]) == 1
            )
            cid = state["customers"][0]["id"]
            pid = api(
                "/api/products",
                {
                    "name": "صنف اختبار كمبيوتر",
                    "price": 100,
                    "cost": 40,
                    "qty": 10,
                    "opening_date": "2026-10-26",
                },
            )["id"]
            p.locator("[data-action=new-invoice]").click()
            p.locator("#invoice-form [name=customer_id]").select_option(str(cid))
            p.locator("#invoice-form [name=date]").fill("2026-10-26")
            p.locator("#invoice-form [name=due_date]").fill("2026-10-26")
            p.locator('[data-line="0"][data-key=product_id]').select_option(str(pid))
            p.locator('[data-line="0"][data-key=qty]').fill("2")
            p.locator("#invoice-form [name=discount]").fill("10")
            p.locator("#invoice-form [name=paid]").fill("50")
            p.get_by_role("button", name="حفظ المسودة", exact=True).click()
            p.wait_for_url("**/#invoice/2")
            p.locator("[data-action=post]").click()
            p.locator('a[href="/print/invoices/2"]').wait_for()
            p.locator("[data-action=amend]").click()
            p.wait_for_url("**/#invoice/3")
            p.locator('[data-line="0"][data-key=qty]').fill("3")
            p.get_by_role("button", name="حفظ المسودة", exact=True).click()
            p.locator("[data-action=post]").click()
            p.locator('a[href="/print/invoices/3"]').wait_for()
            api(
                "/api/receipts",
                {
                    "customer_id": cid,
                    "date": "2026-10-26",
                    "amount": 100,
                    "note": "قبض اختبار",
                },
            )
            api(
                "/api/expenses",
                {
                    "date": "2026-10-26",
                    "amount": 10,
                    "category": "تشغيل",
                    "note": "مصروف اختبار",
                },
            )
            assert api("/api/position?asof=2026-10-26")["balanced"]
            p.locator('nav a[href="#finance"]').click()
            p.get_by_role(
                "heading", name="المحاسبة والنتائج المالية", exact=True
            ).wait_for()
            assert not errors, errors
            context.close()
            process.terminate()
            process.wait(timeout=10)
            process, base = start()
            context = browser.new_context(viewport={"width": 1440, "height": 960})
            p = context.new_page()
            p.goto(base)
            p.locator("#login [name=name]").fill("desktop-review")
            p.locator("#login [name=password]").fill("Synthetic-Desktop-Password-123")
            p.locator("#login button").click()
            p.get_by_role("heading", name="فواتير المبيعات", exact=True).wait_for()
            state = api("/api/bootstrap")
            assert next(x for x in state["products"] if x["id"] == pid)["qty"] == 7
            assert (
                next(x for x in state["customers"] if x["id"] == cid)["balance"]
                == 14000
            )
            assert len(state["products"]) == 11
            browser.close()
        # The exact isolated backup entry point creates a consistent snapshot.
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(PACKAGE / "desktop_backup.py")],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        copies = list((PACKAGE / "MY-BACKUPS").glob("*.sqlite3"))
        assert len(copies) == 1
        with closing(sqlite3.connect(copies[0])) as c:
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        copies[0].unlink()
        (PACKAGE / "MY-BACKUPS").rmdir()
        assert list((data / "backups").glob("*.sqlite3"))
        assert hashlib.sha256(SEED.read_bytes()).hexdigest() == original_hash
        print(
            "Desktop package: isolated entry, private seed, origin/host guards, single instance, sale -> amendment -> receipt -> expense, restart persistence and live backup passed at desktop viewport."
        )
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
