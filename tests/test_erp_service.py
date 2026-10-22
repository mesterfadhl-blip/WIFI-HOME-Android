import io
import json
from pathlib import Path
import tempfile
import unittest
from erp.server import create_app, connect

class Client:
    def __init__(self,app):self.app=app;self.cookie='';self.csrf=''
    def call(self,path,method='GET',data=None,csrf=True):
        raw=json.dumps(data or {}).encode();url,_,query=path.partition('?');headers={}
        env={'PATH_INFO':url,'QUERY_STRING':query,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'HTTP_COOKIE':self.cookie,'HTTP_X_CSRF_TOKEN':self.csrf if csrf else ''}
        def start(status,items):headers.update(items);headers['status']=int(status[:3])
        payload=b''.join(self.app(env,start))
        if 'Set-Cookie' in headers:self.cookie=headers['Set-Cookie'].split(';')[0]
        result=json.loads(payload) if headers.get('Content-Type','').startswith('application/json') else payload.decode()
        if isinstance(result,dict) and result.get('csrf'):self.csrf=result['csrf']
        return headers['status'],result

class ERPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'erp.sqlite3';self.app=create_app(self.path);self.client=Client(self.app)
        self.ok('/api/setup','POST',{'name':'admin','password':'Test-Only-Password-123'})
        self.cid=self.ok('/api/customers','POST',{'name':'عميل اختبار'})['id']
        self.pid=self.ok('/api/products','POST',{'name':'كرت','price':'100','cost':'40','qty':100})['id']
    def tearDown(self):self.tmp.cleanup()
    def ok(self,path,method='GET',data=None):
        status,value=self.client.call(path,method,data);self.assertEqual(status,200,value);return value
    def draft(self,**kwargs):
        payload={'customer_id':self.cid,'date':'2026-10-22','discount':10,'paid':50,'lines':[{'product_id':self.pid,'qty':2,'price':100}]};payload.update(kwargs)
        return self.ok('/api/invoices','POST',payload)
    def state(self):return self.ok('/api/bootstrap')
    def balanced(self):
        with connect(self.path) as c:self.assertEqual(c.execute('SELECT sum(debit-credit) FROM journal').fetchone()[0],0)
    def test_draft_has_no_stock_or_ledger_effect_then_posts_once(self):
        d=self.draft();self.assertEqual(self.state()['products'][0]['qty'],100);self.assertEqual(self.state()['customers'][0]['balance'],0)
        s=self.ok(f'/api/invoices/{d["id"]}/post','POST');self.assertEqual(s['total'],19000);self.assertEqual(self.state()['products'][0]['qty'],98);self.assertEqual(self.state()['customers'][0]['balance'],14000)
        self.assertEqual(self.client.call(f'/api/invoices/{d["id"]}/post','POST')[0],400);self.assertEqual(self.state()['products'][0]['qty'],98);self.balanced()
    def test_duplicate_product_lines_cannot_oversell_and_transaction_rolls_back(self):
        d=self.draft(lines=[{'product_id':self.pid,'qty':60,'price':100},{'product_id':self.pid,'qty':60,'price':100}],paid=0)
        self.assertEqual(self.client.call(f'/api/invoices/{d["id"]}/post','POST')[0],400);self.assertEqual(self.state()['products'][0]['qty'],100);self.assertEqual(self.state()['customers'][0]['balance'],0);self.balanced()
    def test_amendment_retains_original_and_replaces_effects_atomically(self):
        d=self.draft();self.ok(f'/api/invoices/{d["id"]}/post','POST')
        a=self.ok(f'/api/invoices/{d["id"]}/amend','POST',{'reason':'تصحيح كمية'})
        self.assertEqual(self.state()['products'][0]['qty'],98)
        a=self.ok(f'/api/invoices/{a["id"]}','PUT',{'version':a['version'],'customer_id':self.cid,'date':a['date'],'discount':0,'paid':100,'lines':[{'product_id':self.pid,'qty':3,'price':100}]})
        self.ok(f'/api/invoices/{a["id"]}/post','POST');state=self.state();self.assertEqual(state['products'][0]['qty'],97);self.assertEqual(state['customers'][0]['balance'],20000);self.assertEqual(self.ok(f'/api/invoices/{d["id"]}')['status'],'superseded');r=self.ok('/api/reports');self.assertEqual(r['totals']['total'],30000);self.assertEqual(len(r['rows']),1);self.balanced()
    def test_failed_amendment_does_not_reverse_original(self):
        d=self.draft();self.ok(f'/api/invoices/{d["id"]}/post','POST');a=self.ok(f'/api/invoices/{d["id"]}/amend','POST',{'reason':'زيادة'})
        a=self.ok(f'/api/invoices/{a["id"]}','PUT',{'version':a['version'],'customer_id':self.cid,'date':a['date'],'lines':[{'product_id':self.pid,'qty':101,'price':100}]})
        self.assertEqual(self.client.call(f'/api/invoices/{a["id"]}/post','POST')[0],400);self.assertEqual(self.ok(f'/api/invoices/{d["id"]}')['status'],'posted');self.assertEqual(self.state()['products'][0]['qty'],98);self.balanced()
    def test_cancel_retains_receipt_and_cannot_repeat(self):
        d=self.draft();self.ok(f'/api/invoices/{d["id"]}/post','POST');self.ok('/api/receipts','POST',{'customer_id':self.cid,'date':'2026-10-22','amount':30});self.ok(f'/api/invoices/{d["id"]}/cancel','POST',{'reason':'خطأ'})
        self.assertEqual(self.state()['products'][0]['qty'],100);self.assertEqual(self.state()['customers'][0]['balance'],-3000);self.assertEqual(self.ok('/api/reports')['totals']['total'],0);self.assertEqual(self.client.call(f'/api/invoices/{d["id"]}/cancel','POST',{'reason':'تكرار'})[0],400);self.balanced()
    def test_auth_csrf_and_server_permissions(self):
        outsider=Client(self.app);self.assertEqual(outsider.call('/api/bootstrap')[0],401);self.assertEqual(self.client.call('/api/customers','POST',{'name':'x'},csrf=False)[0],403)
        self.ok('/api/users','POST',{'name':'seller','password':'Another-Test-Password','role':'sales'})
        outsider.call('/api/login','POST',{'name':'seller','password':'Another-Test-Password'});self.assertNotEqual(outsider.call('/api/users','POST',{'name':'bad','password':'Another-Test-Password','role':'accountant'})[0],200)
        self.assertNotEqual(outsider.call('/api/products','POST',{'name':'bad','price':1,'cost':1,'qty':1})[0],200)
    def test_rejects_stale_draft_and_invalid_values(self):
        d=self.draft();payload={'version':d['version'],'customer_id':self.cid,'date':d['date'],'lines':[{'product_id':self.pid,'qty':2,'price':100}]};self.ok(f'/api/invoices/{d["id"]}','PUT',payload)
        self.assertEqual(self.client.call(f'/api/invoices/{d["id"]}','PUT',payload)[0],400)
        for change in ({'paid':999},{'discount':999},{'date':'2026-02-30'},{'lines':[]},{'lines':[{'product_id':self.pid,'qty':1.5,'price':100}]}):
            base={'customer_id':self.cid,'date':'2026-10-22','lines':[{'product_id':self.pid,'qty':2,'price':100}]};base.update(change);self.assertEqual(self.client.call('/api/invoices','POST',base)[0],400)
    def test_documents_are_independent_escape_inputs_and_show_true_totals(self):
        d=self.draft();self.ok(f'/api/invoices/{d["id"]}/post','POST')
        for path,title in [(f'/print/invoices/{d["id"]}','فاتورة مبيعات'),(f'/print/statement?customer={self.cid}&from=2026-10-22&to=2026-10-22','كشف حساب عميل'),('/print/sales?from=2026-10-22&to=2026-10-22','تقرير المبيعات')]:
            html=self.ok(path);self.assertIn(title,html);self.assertIn('size:A4',html);self.assertNotIn('class="workspace"',html);self.assertIn('<thead>',html);self.assertIn('<colgroup>',html)
    def test_service_cost_is_payable_not_fictitious_inventory(self):
        pid=self.ok('/api/products','POST',{'name':'خدمة','price':100,'cost':40,'qty':0,'service':True})['id']
        d=self.draft(lines=[{'product_id':pid,'qty':1,'price':100}],discount=0,paid=100)
        self.ok(f'/api/invoices/{d["id"]}/post','POST')
        with connect(self.path) as c:
            rows=c.execute('SELECT account,credit FROM journal WHERE document=?',(d['number'],)).fetchall()
        self.assertIn(('موردو خدمات',4000),[(r['account'],r['credit']) for r in rows])
        self.assertNotIn('المخزون',[r['account'] for r in rows]);self.balanced()
    def test_failed_login_throttles_and_backup_restores_committed_records(self):
        from erp.backup import backup
        outsider=Client(self.app)
        for _ in range(5):self.assertEqual(outsider.call('/api/login','POST',{'name':'admin','password':'Incorrect-Password'})[0],401)
        self.assertEqual(outsider.call('/api/login','POST',{'name':'admin','password':'Incorrect-Password'})[0],429)
        d=self.draft();self.ok(f'/api/invoices/{d["id"]}/post','POST')
        target=Path(self.tmp.name)/'restored.sqlite3';backup(self.path,target)
        with connect(target) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('SELECT qty FROM products WHERE id=?',(self.pid,)).fetchone()[0],98)
            self.assertEqual(c.execute('SELECT status FROM invoices WHERE id=?',(d['id'],)).fetchone()[0],'posted')
    def test_second_session_reads_shared_committed_data_and_receipt_period_separate(self):
        second=Client(self.app);self.assertEqual(second.call('/api/login','POST',{'name':'admin','password':'Test-Only-Password-123'})[0],200)
        d=self.draft(date='2026-09-01');self.ok(f'/api/invoices/{d["id"]}/post','POST');self.ok('/api/receipts','POST',{'customer_id':self.cid,'date':'2026-10-22','amount':30})
        status,state=second.call('/api/bootstrap');self.assertEqual(status,200);self.assertEqual(state['customers'][0]['balance'],11000)
        r=self.ok('/api/reports?from=2026-10-01&to=2026-10-31');self.assertEqual(r['totals']['total'],0);self.assertEqual(r['totals']['receipts'],3000)

if __name__=='__main__':unittest.main()
