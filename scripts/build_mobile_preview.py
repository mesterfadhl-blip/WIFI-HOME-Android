"""Build a read-only, standalone preview from a fresh synthetic ERP database."""
import json
from pathlib import Path
import sys
import threading
from wsgiref.simple_server import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_erp_workspace import WorkspaceTests
from playwright.sync_api import sync_playwright

class Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass

t = WorkspaceTests()
t.setUp()
server = None
try:
    # Only newly generated test records; never read any existing database.
    sid = t.ok('/api/suppliers', 'POST', {'name': 'مورد المعاينة — بيانات تجريبية'})['id']
    p = t.ok('/api/purchases', 'POST', {'supplier_id': sid, 'date':'2026-10-22','paid':0,'lines':[{'product_id':t.pid,'qty':50,'cost':50}]})
    t.ok(f'/api/purchases/{p["id"]}/post','POST',{'version':p['version']})
    wid = t.warehouse()
    transfer = t.transfer(wid,20)
    s = t.sale(warehouse_id=wid)
    bank = t.bank()
    receipt = t.receipt(100, bank_id=bank['id'], reference='إيداع تجريبي')
    t.allocate(receipt,s,100)
    t.draft(paid=0)
    server = make_server('127.0.0.1',0,t.app,handler_class=Quiet)
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    routes=['sales','customers','products','purchases','suppliers','returns','finance','settlements','banks','warehouses','reports','audit','users','invoice/1','invoice/2','purchase/1','transfer/1','new','new-purchase','new-transfer']
    snapshots={}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':844})
        context.add_cookies([{'name':'erp_session','value':t.client.cookie.split('=',1)[1],'url':base}])
        page=context.new_page();page.goto(base)
        page.locator('h1').wait_for()
        page.evaluate("filters={from:'2026-10-01',to:'2026-10-31',customer:''};financeFilter={from:'2026-10-01',to:'2026-10-31'};agingDate='2026-10-22'")
        for route in routes:
            snapshots[route]=page.evaluate("""async route => {history.replaceState(null,'','#'+route);await navigate();return document.querySelector('#root').innerHTML;}""",route)
        browser.close()
    documents={}
    for path in ['/print/invoices/1','/print/purchases/1','/print/transfers/1','/print/sales?from=2026-10-01&to=2026-10-31','/print/finance?from=2026-10-01&to=2026-10-31','/print/aging?asof=2026-10-22','/print/statement?customer=1&from=2026-10-01&to=2026-10-31','/print/supplier?supplier=1&from=2026-10-01&to=2026-10-31']:
        status,body=t.client.call(path)
        assert status==200,(path,body)
        body=body.replace('<script src="/document.js" defer></script>','')
        body=body.replace('<body>','<body><p style="text-align:center;color:#805600">معاينة فقط · جميع الأرقام تجريبية</p>')
        documents[path.split('?')[0]]=body
    def encoded(v):
        return json.dumps(v,ensure_ascii=False).replace('<','\\u003c')
    css=(ROOT/'erp/static/style.css').read_text()
    script='const PAGES='+encoded(snapshots)+';const DOCS='+encoded(documents)+';\n'+(ROOT/'scripts/mobile_preview.js').read_text()
    html='''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WIFI HOME ERP — معاينة الهاتف</title><style>'''+css+'''\n.preview-banner{padding:14px;background:#fff1c2;color:#513800;text-align:center;line-height:1.8}.preview-banner b{display:block}.preview-banner a{color:inherit;text-decoration:underline}#preview-doc{width:100%;height:85vh;border:0;background:white}.preview-close{padding:12px;margin:10px}.top nav{overflow-x:auto}@media(max-width:600px){.top{display:block!important}.top nav{display:flex!important;white-space:nowrap;padding:12px 0}.top .brand{display:block}.top{position:static}.document{padding:12px!important}}@media print{.preview-banner{display:none}}</style></head><body><div class="preview-banner"><b>معاينة النظام — بيانات تجريبية فقط</b>تنقّل بين الأقسام وافتح الفواتير والتقارير. الحفظ والترحيل غير متاحين، ولا توجد مزامنة.<br>اسحب شريط الأقسام أفقياً لعرض البنوك والمستودعات والتقارير.</div><div id="root"></div><script>'''+script+'</script></body></html>'
    target=ROOT/'preview/WIFI-HOME-PREVIEW.html';target.write_text(html)
    print(f'Created {target.name}: {len(snapshots)} screens, {len(documents)} documents, {target.stat().st_size} bytes')
finally:
    if server:server.shutdown();server.server_close()
    t.tearDown()
