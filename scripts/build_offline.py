"""Produce a generic operational offline HTML; never embed private customer data."""

from pathlib import Path
import re, sys

ROOT = Path(__file__).resolve().parents[1]
output = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/workspace/.cloud-setup/offline-mobile/WIFI-HOME-OFFLINE.html"
)
core = re.sub(
    r"^export (?=(?:const|function)\b)",
    "",
    (ROOT / "web/core.mjs").read_text(),
    flags=re.M,
)
app = re.sub(
    r'^import\s*\{.*?\}\s*from\s*"\./core.mjs";\s*',
    "",
    (ROOT / "web/app.mjs").read_text(),
    count=1,
    flags=re.S,
)
migration = re.sub(
    r"^import[^\n]+\n", "", (ROOT / "offline/migration.mjs").read_text(), flags=re.M
)
migration = re.sub(r"^export (?=function\b)", "", migration, flags=re.M)
app = app.replace('"wifiHomeERP.v1"', "OFFLINE_KEY").replace(
    "let db = emptyDB(),",
    "let db = offlineSeed.data ? normalize(offlineSeed.data) : emptyDB(),",
)
app = app.replace("localStorage.", "storage.").replace(
    "crypto.randomUUID()", "recordID()"
)
bootstrap = """
const offlineSeed=JSON.parse(document.getElementById('offline-seed').textContent);
const OFFLINE_KEY=offlineSeed.storageKey||'wifiHomeERP.offline.v2';
if(!globalThis.structuredClone)globalThis.structuredClone=value=>JSON.parse(JSON.stringify(value));
function recordID(){
 if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
 if(globalThis.crypto?.getRandomValues){const a=globalThis.crypto.getRandomValues(new Uint8Array(16));return [...a].map(x=>x.toString(16).padStart(2,'0')).join('');}
 return Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)+'-'+(++recordID.sequence);
}recordID.sequence=0;
let storage,temporaryStorage=false;
try{storage=window.localStorage;const probe='erp-probe-'+Date.now();storage.setItem(probe,'1');storage.removeItem(probe);}
catch(error){temporaryStorage=true;const memory=new Map();storage={getItem:key=>memory.get(key)??null,setItem:(key,value)=>memory.set(key,String(value)),removeItem:key=>memory.delete(key)};}
"""
script = (
    '(function(){"use strict";\n'
    + bootstrap
    + core
    + "\n"
    + migration
    + "\n"
    + app
    + "\n"
    + (ROOT / "offline/mobile.js").read_text()
    + "\n})();"
)
assert not re.search(r"^import\b|^export\b", script, re.M)
script = re.sub(r"</script", lambda m: "<\\/script", script, flags=re.I)
html = (ROOT / "web/index.html").read_text()
css = (
    (ROOT / "web/style.css").read_text()
    + "\n"
    + (ROOT / "offline/mobile.css").read_text()
)
html = html.replace(
    '<link rel="stylesheet" href="style.css" />', "<style>" + css + "</style>"
)
html = html.replace(
    '<script type="module" src="app.mjs"></script>',
    '<script id="offline-seed" type="application/json">{}</script><script>'
    + script
    + "</script>",
)
html = html.replace(
    "لا تُدخل بياناتك الفعلية قبل مراجعة\n        الأرصدة المستوردة",
    "نسخة تشغيل محلية على هذا الجهاز؛ احفظ نسخة احتياطية خارج المتصفح",
)
html = html.replace(
    "<title>WIFI HOME — إدارة المبيعات والحسابات</title>",
    "<title>WIFI HOME — نسخة الهاتف المحلية</title>",
)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(html)
print(f"{output} ({output.stat().st_size} bytes)")
