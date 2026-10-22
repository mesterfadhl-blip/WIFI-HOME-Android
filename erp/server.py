"""WIFI HOME ERP: shared transactional sales service (Python standard library)."""
import csv
import io
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.cookies import SimpleCookie
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server
from .documents import invoice_document, statement_document, sales_document

ROOT = Path(__file__).parent
class BusinessError(Exception):
    pass

def money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0: raise ValueError()
        return int((n * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (ValueError, InvalidOperation):
        raise BusinessError('المبلغ غير صحيح')

def date(value):
    try: return dt.date.fromisoformat(value).isoformat()
    except (TypeError, ValueError): raise BusinessError('التاريخ غير صحيح')

def password_hash(value, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest

def connect(path):
    c=sqlite3.connect(path, timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

SCHEMA='''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','sales','accountant')));
CREATE TABLE IF NOT EXISTS login_attempts(key TEXT PRIMARY KEY,failures INTEGER NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),csrf TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT NOT NULL,price INTEGER NOT NULL,cost INTEGER NOT NULL,qty INTEGER NOT NULL,service INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,number TEXT UNIQUE,customer_id INTEGER NOT NULL REFERENCES customers(id),date TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('draft','posted','cancelled','superseded')),discount INTEGER NOT NULL DEFAULT 0,paid INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',total INTEGER NOT NULL DEFAULT 0,cost INTEGER NOT NULL DEFAULT 0,amends INTEGER REFERENCES invoices(id),version INTEGER NOT NULL DEFAULT 1,created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS lines(id INTEGER PRIMARY KEY,invoice_id INTEGER NOT NULL REFERENCES invoices(id),product_id INTEGER NOT NULL REFERENCES products(id),name TEXT NOT NULL,qty INTEGER NOT NULL,price INTEGER NOT NULL,cost INTEGER NOT NULL,service INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY,document TEXT NOT NULL,date TEXT NOT NULL,account TEXT NOT NULL,customer_id INTEGER REFERENCES customers(id),debit INTEGER NOT NULL DEFAULT 0,credit INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,document TEXT NOT NULL,date TEXT NOT NULL,product_id INTEGER NOT NULL REFERENCES products(id),qty INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY,number TEXT NOT NULL UNIQUE,date TEXT NOT NULL,customer_id INTEGER NOT NULL REFERENCES customers(id),amount INTEGER NOT NULL,note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT NOT NULL,user_id INTEGER REFERENCES users(id),action TEXT NOT NULL,document TEXT NOT NULL,detail TEXT NOT NULL);
'''

def audit(c,user,action,document,detail=''):
    c.execute('INSERT INTO audit(at,user_id,action,document,detail) VALUES(?,?,?,?,?)',(dt.datetime.now(dt.timezone.utc).isoformat(),user,action,document,detail))

def journal(c,document,day,rows):
    if sum(r[2]-r[3] for r in rows)!=0: raise BusinessError('القيد غير متوازن')
    c.executemany('INSERT INTO journal(document,date,account,customer_id,debit,credit) VALUES(?,?,?,?,?,?)',[(document,day,*r) for r in rows])

def invoice_data(c,id):
    row=c.execute('SELECT i.*,c.name customer,c.phone,c.address FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.id=?',(id,)).fetchone()
    if not row: raise BusinessError('الفاتورة غير موجودة')
    data=dict(row)
    data['lines']=[dict(r) for r in c.execute('SELECT * FROM lines WHERE invoice_id=?',(id,))]
    return data

def draft_save(c,data,user,id=None):
    old=invoice_data(c,id) if id else None
    if old and old['status']!='draft': raise BusinessError('الفاتورة المرحلة لا تعدل مباشرة؛ استخدم إصدار تعديل')
    if old and data.get('version')!=old['version']: raise BusinessError('تم تعديل المسودة من مستخدم آخر؛ حدّث الصفحة')
    if not c.execute('SELECT 1 FROM customers WHERE id=?',(data.get('customer_id'),)).fetchone(): raise BusinessError('اختر العميل')
    day=date(data.get('date')); discount=money(data.get('discount',0)); paid=money(data.get('paid',0))
    lines=[]
    for item in data.get('lines',[]):
        p=c.execute('SELECT * FROM products WHERE id=?',(item.get('product_id'),)).fetchone()
        try:
            q=int(item.get('qty',0))
            if str(q)!=str(item.get('qty')) or q<=0: raise ValueError()
        except (ValueError, TypeError, OverflowError): raise BusinessError('الكمية يجب أن تكون عدداً صحيحاً أكبر من صفر')
        if not p: raise BusinessError('الصنف غير موجود')
        lines.append((p['id'],p['name'],q,money(item.get('price',0)),p['cost'],p['service']))
    if not lines: raise BusinessError('أضف بنداً واحداً على الأقل')
    total=sum(q*price for _,_,q,price,_,_ in lines)-discount
    cost=sum(q*cost for _,_,q,_,cost,_ in lines)
    if total<0 or paid>total: raise BusinessError('الخصم أو السداد يتجاوز قيمة الفاتورة')
    values=(data['customer_id'],day,discount,paid,str(data.get('note',''))[:2000],total,cost)
    if id:
        c.execute('UPDATE invoices SET customer_id=?,date=?,discount=?,paid=?,note=?,total=?,cost=?,version=version+1 WHERE id=?',(*values,id))
        c.execute('DELETE FROM lines WHERE invoice_id=?',(id,))
    else:
        cur=c.execute("INSERT INTO invoices(customer_id,date,discount,paid,note,total,cost,status,created_by) VALUES(?,?,?,?,?,?,?,'draft',?)",(*values,user))
        id=cur.lastrowid
        c.execute('UPDATE invoices SET number=? WHERE id=?',(f'SI-{id:06}',id))
    c.executemany('INSERT INTO lines(invoice_id,product_id,name,qty,price,cost,service) VALUES(?,?,?,?,?,?,?)',[(id,*line) for line in lines])
    audit(c,user,'حفظ مسودة',str(id))
    return invoice_data(c,id)

def reverse(c,s,user,reason,status):
    rows=c.execute('SELECT account,customer_id,debit,credit FROM journal WHERE document=?',(s['number'],)).fetchall()
    if not rows: raise BusinessError('القيود الأصلية غير موجودة')
    ref=s['number']+'-REV'
    journal(c,ref,s['date'],[(r['account'],r['customer_id'],r['credit'],r['debit']) for r in rows])
    for line in s['lines']:
        if not line['service']:
            c.execute('UPDATE products SET qty=qty+? WHERE id=?',(line['qty'],line['product_id']))
            c.execute('INSERT INTO movements(document,date,product_id,qty) VALUES(?,?,?,?)',(ref,s['date'],line['product_id'],line['qty']))
    c.execute('UPDATE invoices SET status=? WHERE id=?',(status,s['id']))
    audit(c,user,'عكس فاتورة',s['number'],reason)

def post_invoice(c,id,user):
    s=invoice_data(c,id)
    if s['status']!='draft': raise BusinessError('تم ترحيل المستند بالفعل أو إلغاؤه')
    if s['amends']:
        prior=invoice_data(c,s['amends'])
        if prior['status']!='posted': raise BusinessError('تم تعديل أو إلغاء الفاتورة الأصلية مسبقاً')
        reverse(c,prior,user,'إصدار بديل '+s['number'],'superseded')
    used={}
    # Restore/re-cost from current stock; drafts reserve no stock or cost.
    cost=0
    stock_cost=0
    service_cost=0
    for line in s['lines']:
        p=c.execute('SELECT * FROM products WHERE id=?',(line['product_id'],)).fetchone()
        used[p['id']]=used.get(p['id'],0)+line['qty']
        if not p['service'] and used[p['id']]>p['qty']: raise BusinessError('مخزون غير كافٍ: '+p['name'])
        c.execute('UPDATE lines SET cost=? WHERE id=?',(p['cost'],line['id']))
        cost+=line['qty']*p['cost']
        if p['service']:service_cost+=line['qty']*p['cost']
        else:stock_cost+=line['qty']*p['cost']
    rows=[('العملاء',s['customer_id'],s['total'],0),('المبيعات',None,0,s['total'])]
    if s['paid']: rows += [('الصندوق',None,s['paid'],0),('العملاء',s['customer_id'],0,s['paid'])]
    if cost:rows.append(('تكلفة المبيعات',None,cost,0))
    if stock_cost:rows.append(('المخزون',None,0,stock_cost))
    if service_cost:rows.append(('موردو خدمات',None,0,service_cost))
    journal(c,s['number'],s['date'],rows)
    for line in s['lines']:
        if not line['service']:
            c.execute('UPDATE products SET qty=qty-? WHERE id=?',(line['qty'],line['product_id']))
            c.execute('INSERT INTO movements(document,date,product_id,qty) VALUES(?,?,?,?)',(s['number'],s['date'],line['product_id'],-line['qty']))
    c.execute("UPDATE invoices SET status='posted',cost=? WHERE id=?",(cost,id))
    audit(c,user,'ترحيل فاتورة',s['number'])
    return invoice_data(c,id)

class Application:
    def __init__(self,path):
        self.path=str(path)
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with connect(self.path) as c:c.executescript(SCHEMA)

    def __call__(self,env,start):
        status=200; headers=[('X-Content-Type-Options','nosniff'),('Cache-Control','no-store'),('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'")]
        method=env.get('REQUEST_METHOD','GET'); path=env.get('PATH_INFO','/');c=connect(self.path)
        try:
            if method=='GET' and path in ('/','/app.js','/style.css','/document.js'):
                file=ROOT/'static'/({'/':'index.html'}.get(path,path[1:]));body=file.read_bytes();kind='text/html' if path=='/' else 'text/javascript' if path.endswith('.js') else 'text/css'
            else:
                length=int(env.get('CONTENT_LENGTH') or 0)
                if length>1000000:raise BusinessError('الطلب أكبر من الحد المسموح')
                data=json.loads(env['wsgi.input'].read(length) or b'{}') if method!='GET' else {}
                if not isinstance(data,dict):raise BusinessError('الطلب غير صالح')
                cookie=SimpleCookie();cookie.load(env.get('HTTP_COOKIE',''))
                token=cookie.get('erp_session'); session=c.execute('SELECT s.*,u.name,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>unixepoch()', (hashlib.sha256(token.value.encode()).hexdigest() if token else '',)).fetchone()
                if path in ('/api/setup','/api/login') and method=='POST':
                    name=str(data.get('name','')).strip();password=str(data.get('password',''))
                    if not name or len(password)<8:raise BusinessError('أدخل اسم مستخدم وكلمة مرور من 8 أحرف على الأقل')
                    c.execute('BEGIN IMMEDIATE')
                    attempt_key=hashlib.sha256((str(env.get('REMOTE_ADDR','local'))+'|'+name).encode()).hexdigest()
                    attempt=c.execute('SELECT failures FROM login_attempts WHERE key=? AND expires>unixepoch()',(attempt_key,)).fetchone()
                    if attempt and attempt['failures']>=5:
                        status=429;raise BusinessError('محاولات دخول كثيرة؛ أعد المحاولة بعد 5 دقائق')
                    if path=='/api/setup':
                        if c.execute('SELECT 1 FROM users').fetchone():raise BusinessError('تم إعداد المستخدم الأول بالفعل')
                        c.execute('INSERT INTO users(name,password,role) VALUES(?,?,?)',(name,password_hash(password),'admin'))
                    user=c.execute('SELECT * FROM users WHERE name=?',(name,)).fetchone()
                    if not user or not hmac.compare_digest(password_hash(password,user['password'].split(':')[0]),user['password']):
                        c.execute('INSERT INTO login_attempts VALUES(?,1,unixepoch()+300) ON CONFLICT(key) DO UPDATE SET failures=CASE WHEN expires>unixepoch() THEN failures+1 ELSE 1 END,expires=unixepoch()+300',(attempt_key,));c.commit()
                        status=401;raise BusinessError('بيانات الدخول غير صحيحة')
                    c.execute('DELETE FROM login_attempts WHERE key=?',(attempt_key,))
                    raw=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
                    c.execute('INSERT INTO sessions VALUES(?,?,?,unixepoch()+28800)',(hashlib.sha256(raw.encode()).hexdigest(),user['id'],csrf))
                    c.commit();headers.append(('Set-Cookie','erp_session='+raw+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if os.environ.get('ERP_COOKIE_SECURE')=='1' else '')))
                    result={'name':user['name'],'role':user['role'],'csrf':csrf}
                elif path=='/api/status' and method=='GET':result={'configured':bool(c.execute('SELECT 1 FROM users').fetchone()),'user':({'name':session['name'],'role':session['role'],'csrf':session['csrf']} if session else None)}
                else:
                    if not session:status=401;raise BusinessError('سجّل الدخول أولاً')
                    if method!='GET':
                        if not hmac.compare_digest(env.get('HTTP_X_CSRF_TOKEN',''),session['csrf']):status=403;raise BusinessError('انتهت صلاحية الطلب؛ أعد تحميل الصفحة')
                        c.execute('BEGIN IMMEDIATE')
                    uid=session['user_id']; role=session['role']
                    result=self.dispatch(c,path,method,data,env,uid,role,session)
                    if method!='GET':c.commit()
                if isinstance(result,tuple):
                    content,kind,filename=result;body=content.encode('utf-8-sig');headers.append(('Content-Disposition','attachment; filename="'+filename+'"'))
                elif isinstance(result,str):body=result.encode();kind='text/html'
                else:body=json.dumps(result,ensure_ascii=False).encode();kind='application/json'
        except (BusinessError,ValueError,KeyError,TypeError,OverflowError,sqlite3.IntegrityError) as e:
            c.rollback();status=status if status!=200 else 400;body=json.dumps({'error':str(e)},ensure_ascii=False).encode();kind='application/json'
        except Exception:
            c.rollback();status=500;body=b'{"error":"Internal server error"}';kind='application/json'
        finally:c.close()
        start(str(status)+' '+{200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',429:'Too Many Requests',500:'Internal Server Error'}[status],headers+[('Content-Type',kind+'; charset=utf-8'),('Content-Length',str(len(body)))])
        return [body]

    def dispatch(self,c,path,method,data,env,uid,role,session):
        if path=='/api/logout' and method=='POST':c.execute('DELETE FROM sessions WHERE token=?',(session['token'],));return {'ok':True}
        if path=='/api/users' and method=='POST':
            if role!='admin':raise BusinessError('هذه العملية للمدير فقط')
            if data.get('role') not in ('sales','accountant') or len(str(data.get('password','')))<8:raise BusinessError('الدور أو كلمة المرور غير صحيحين')
            c.execute('INSERT INTO users(name,password,role) VALUES(?,?,?)',(str(data['name']).strip(),password_hash(data['password']),data['role']));audit(c,uid,'إضافة مستخدم',str(data['name']));return {'ok':True}
        if path=='/api/bootstrap' and method=='GET':
            return {key:[dict(r) for r in c.execute(sql)] for key,sql in {
                'customers':"SELECT c.*,coalesce((SELECT sum(debit-credit) FROM journal j WHERE j.account='العملاء' AND j.customer_id=c.id),0) balance FROM customers c",
                'products':'SELECT * FROM products',
                'invoices':'SELECT i.*,c.name customer FROM invoices i JOIN customers c ON c.id=i.customer_id ORDER BY i.id DESC',
                'audit':'SELECT a.*,u.name user FROM audit a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 100'}.items()}
        if path=='/api/customers' and method=='POST':
            name=str(data.get('name','')).strip()
            if not name:raise BusinessError('أدخل اسم العميل')
            id=c.execute('INSERT INTO customers(name,phone,address) VALUES(?,?,?)',(name,str(data.get('phone','')),str(data.get('address','')))).lastrowid
            audit(c,uid,'إضافة عميل',str(id));return {'id':id}
        if path=='/api/products' and method=='POST':
            if role!='admin':raise BusinessError('إضافة المخزون للمدير فقط')
            name=str(data.get('name','')).strip()
            if not name:raise BusinessError('أدخل اسم الصنف')
            q=int(data.get('qty',0));cost=money(data.get('cost',0));price=money(data.get('price',0));service=bool(data.get('service',False))
            if q<0 or (service and q):raise BusinessError('الكمية غير صحيحة')
            id=c.execute('INSERT INTO products(name,price,cost,qty,service) VALUES(?,?,?,?,?)',(name,price,cost,q,int(service))).lastrowid
            if q:
                ref=f'OPEN-STOCK-{id}';day=dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).date().isoformat()
                journal(c,ref,day,[('المخزون',None,q*cost,0),('رأس المال والأرصدة الافتتاحية',None,0,q*cost)])
                c.execute('INSERT INTO movements(document,date,product_id,qty) VALUES(?,?,?,?)',(ref,day,id,q))
            audit(c,uid,'رصيد صنف افتتاحي',str(id));return {'id':id}
        if path=='/api/invoices' and method=='POST':return draft_save(c,data,uid)
        if path.startswith('/api/invoices/'):
            parts=path.strip('/').split('/');id=int(parts[2]);s=invoice_data(c,id)
            if len(parts)==3:
                if method=='GET':return s
                if method=='PUT':return draft_save(c,data,uid,id)
            if method=='POST' and len(parts)==4:
                action=parts[3]
                if action=='post':
                    if data.get('version') is not None and data['version']!=s['version']:raise BusinessError('تغيّرت المسودة؛ حدّثها قبل الترحيل')
                    return post_invoice(c,id,uid)
                if action in ('cancel','amend'):
                    if role not in ('admin','accountant'):raise BusinessError('عكس المستندات للمدير أو المحاسب فقط')
                    reason=str(data.get('reason','')).strip()
                    if not reason:raise BusinessError('السبب إلزامي')
                    if s['status']!='posted':raise BusinessError('المستند غير قابل لهذه العملية')
                    if action=='cancel':reverse(c,s,uid,reason,'cancelled');return invoice_data(c,id)
                    draft={'customer_id':s['customer_id'],'date':s['date'],'discount':str(Decimal(s['discount'])/100),'paid':str(Decimal(s['paid'])/100),'note':s['note'],'lines':[{'product_id':l['product_id'],'qty':l['qty'],'price':str(Decimal(l['price'])/100)} for l in s['lines']]}
                    revised=draft_save(c,draft,uid);c.execute('UPDATE invoices SET amends=? WHERE id=?',(id,revised['id']));audit(c,uid,'طلب تعديل',revised['number'],reason);return invoice_data(c,revised['id'])
        if path=='/api/receipts' and method=='POST':
            amount=money(data.get('amount',0));day=date(data.get('date'))
            if not amount:raise BusinessError('المبلغ يجب أن يكون أكبر من صفر')
            id=c.execute("INSERT INTO receipts(number,date,customer_id,amount,note) VALUES(?,?,?,?,?)",('TMP-'+secrets.token_hex(8),day,data['customer_id'],amount,str(data.get('note','')))).lastrowid
            ref=f'RC-{id:06}';c.execute('UPDATE receipts SET number=? WHERE id=?',(ref,id));journal(c,ref,day,[('الصندوق',None,amount,0),('العملاء',data['customer_id'],0,amount)]);audit(c,uid,'سند قبض',ref);return {'number':ref}
        query={k:v[0] for k,v in parse_qs(env.get('QUERY_STRING','')).items()}
        if path.startswith('/print/invoices/') and method=='GET':return invoice_document(invoice_data(c,int(path.split('/')[-1])))
        if path in ('/api/reports','/print/sales','/print/statement','/export/sales.csv') and method=='GET':
            f=date(query.get('from','1900-01-01'));t=date(query.get('to','2999-12-31'))
            if f>t:raise BusinessError('بداية الفترة بعد نهايتها')
            cid=int(query['customer']) if query.get('customer') else None
            where="i.status='posted' AND i.date BETWEEN ? AND ?";args=[f,t]
            if cid:where+=' AND i.customer_id=?';args.append(cid)
            rows=[dict(r) for r in c.execute('SELECT i.*,c.name customer FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE '+where+' ORDER BY i.date,i.id',args)]
            receipts=c.execute('SELECT coalesce(sum(amount),0) FROM receipts WHERE date BETWEEN ? AND ?'+(' AND customer_id=?' if cid else ''),[f,t]+([cid] if cid else [])).fetchone()[0]
            totals={k:sum(r[k] for r in rows) for k in ('total','cost','paid')};totals['profit']=totals['total']-totals['cost'];totals['receipts']=receipts
            if path=='/export/sales.csv':
                stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['الفاتورة','التاريخ','العميل','صافي البيع','التكلفة','مجمل الربح'])
                for row in rows:
                    name=row['customer'];name="'"+name if name.startswith(('=','+','-','@')) else name
                    writer.writerow([row['number'],row['date'],name,str(Decimal(row['total'])/100),str(Decimal(row['cost'])/100),str(Decimal(row['total']-row['cost'])/100)])
                return stream.getvalue(),'text/csv','sales-report.csv'
            if path=='/api/reports':return {'rows':rows,'totals':totals,'from':f,'to':t}
            if path=='/print/sales':return sales_document(rows,totals,f,t)
            if not cid:raise BusinessError('اختر العميل لكشف الحساب')
            client=c.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone()
            if not client:raise BusinessError('العميل غير موجود')
            opening=c.execute("SELECT coalesce(sum(debit-credit),0) FROM journal WHERE account='العملاء' AND customer_id=? AND date<?",(cid,f)).fetchone()[0]
            movement=[dict(r) for r in c.execute("SELECT * FROM journal WHERE account='العملاء' AND customer_id=? AND date BETWEEN ? AND ? ORDER BY date,id",(cid,f,t))]
            return statement_document(dict(client),opening,movement,f,t)
        raise BusinessError('العملية غير متاحة')

def create_app(path=None):
    return Application(path or os.environ.get('ERP_DATABASE','/workspace/.cloud-setup/erp/data.sqlite3'))

if __name__=='__main__':
    os.umask(0o077)
    with make_server('127.0.0.1',int(os.environ.get('PORT','8081')),create_app()) as server:
        print('ERP development server: 127.0.0.1:'+str(server.server_port),flush=True)
        server.serve_forever()
