"""Bundle the SAME Python ERP and SQLite in a self-contained, optionally private HTML."""

from pathlib import Path
import argparse, base64, hashlib, io, json, re, secrets, zipfile

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("output", type=Path)
p.add_argument(
    "--runtime", type=Path, default=Path("/workspace/.cloud-setup/pyodide/package")
)
p.add_argument("--database", type=Path)
a = p.parse_args()
lock = json.loads((a.runtime / "pyodide-lock.json").read_text())
names = [
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
]
for name in ("sqlite3", "openssl", "hashlib"):
    info = lock["packages"][name]
    data = (a.runtime / info["file_name"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == info["sha256"]
    names.append(info["file_name"])
assets = {
    name: base64.b64encode((a.runtime / name).read_bytes()).decode() for name in names
}
stream = io.BytesIO()
with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
    for path in (ROOT / "erp").glob("*.py"):
        z.write(path, "erp/" + path.name)
    for path in (ROOT / "erp/static").iterdir():
        z.write(path, "erp/static/" + path.name)
assets["erp.zip"] = base64.b64encode(stream.getvalue()).decode()
assets["bridge.py"] = base64.b64encode(
    (ROOT / "local-engine/bridge.py").read_bytes()
).decode()
frontend = "\n".join(
    (ROOT / "erp/static" / name).read_text()
    for name in ("app.js", "operations.js", "workspace.js", "enterprise.js")
)
frontend = frontend.replace(
    "قاعدة بيانات مشتركة على الخادم", "قاعدة بيانات محلية في هذا الملف"
).replace("بياناتك محفوظة على خادم النظام.", "بياناتك محفوظة في النسخة المحلية.")
pack = {
    "version": 1,
    "storageKey": "wifi-home-full-" + secrets.token_hex(16),
    "assets": assets,
    "frontend": frontend,
    "database": (
        base64.b64encode(a.database.read_bytes()).decode() if a.database else ""
    ),
}
css = (
    ROOT / "erp/static/style.css"
).read_text() + """\n.local-shell{padding:10px 16px;background:#fff3cc;border-bottom:1px solid #d5b972;line-height:1.8}.local-tools{display:flex;gap:8px;flex-wrap:wrap;padding:10px}.loading{padding:60px;text-align:center}#local-document{position:fixed;inset:8px;width:calc(100% - 16px);height:calc(100% - 16px);max-width:none;max-height:none;padding:0}#local-document iframe{border:0;width:100%;height:calc(100% - 80px)}@media print{.local-shell{display:none}}"""
loader = (ROOT / "local-engine/loader.js").read_text()
# Every '<' in embedded JSON is escaped; user names cannot terminate scripts.
package = json.dumps(pack, ensure_ascii=False, separators=(",", ":")).replace(
    "<", "\\u003c"
)
loader = re.sub("</script", lambda m: "<\\/script", loader, flags=re.I)
html = (
    """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WIFI HOME ERP — نفس النظام محلياً</title><link rel="icon" href="data:,"><style>"""
    + css
    + """</style></head><body><div class="local-shell"><b>نفس النظام — تشغيل محلي دون استضافة</b><div id="local-status" role="status"></div><div class="local-tools"><button id="save-system" disabled>حفظ نسخة النظام ببياناتي</button><button id="save-database" disabled>تنزيل قاعدة البيانات</button></div><small>ملفك يحتوي بيانات خاصة. لا تشاركه أو ترفعه لموقع عام. لا توجد مزامنة بين الأجهزة.</small></div><div id="root"></div><script id="erp-package" type="application/json">"""
    + package
    + "</script><script>"
    + loader
    + "</script></body></html>"
)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(html)
print(
    f"Full local package: {a.output.stat().st_size} bytes; database included: {bool(a.database)}"
)
