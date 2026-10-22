"""Bundle the local ERP into one HTML file, with no external assets."""
import pathlib
import re
import sys
root = pathlib.Path(__file__).resolve().parent.parent
source = root / 'web'
output = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '/workspace/.cloud-setup/erp-standalone/index.html')
core = re.sub(r'^export (?=(?:const|function)\b)', '', (source / 'core.mjs').read_text(), flags=re.M)
app = re.sub(r'^import\s*\{.*?\}\s*from\s*"\./core\.mjs";\s*', '', (source / 'app.mjs').read_text(), count=1, flags=re.S)
assert not re.search(r'^import\b|^export\b', core + app, re.M)
# Only local record IDs use this fallback; it is not an authentication token.
app = app.replace('crypto.randomUUID()', 'recordID()').replace('localStorage.', 'storage.')
bootstrap = '''
function recordID() {
 if(globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
 if(!globalThis.crypto?.getRandomValues) throw Error('المتصفح لا يدعم إنشاء معرفات السجلات؛ افتح النسخة المنشورة عبر HTTPS');
 const bytes=globalThis.crypto.getRandomValues(new Uint8Array(16));
 return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
}
let storage, temporaryStorage=false;
try {
 const probe='wifiERP.probe.'+Date.now();
 storage=window.localStorage; storage.setItem(probe,'1'); storage.removeItem(probe);
} catch(error) {
 temporaryStorage=true;
 const memory=new Map();
 storage={getItem:key=>memory.get(key)??null,setItem:(key,value)=>memory.set(key,String(value)),removeItem:key=>memory.delete(key)};
}
'''
ending = '''
if(temporaryStorage){
 const warning=document.createElement('div');warning.className='note warn';warning.setAttribute('role','alert');
 warning.textContent='وضع المعاينة فقط: المتصفح يمنع الحفظ الدائم لهذا الملف. ستفقد المدخلات عند إغلاقه. افتح النسخة المنشورة من رابط HTTPS لحفظ بيانات العمل، أو صدّر نسخة احتياطية قبل الإغلاق.';
 document.querySelector('main').prepend(warning);
}
'''
script = '(function(){"use strict";\n' + bootstrap + core + '\n' + app + '\n' + ending + '\n})();'
script = re.sub(r'</script', r'<\\/script', script, flags=re.I)
html=(source / 'index.html').read_text()
html=html.replace('<link rel="stylesheet" href="style.css" />','<style>\n'+(source/'style.css').read_text()+'\n</style>')
html=html.replace('<script type="module" src="app.mjs"></script>', '<script>\n'+script+'\n</script>')
assert '<script type="module"' not in html and 'href="style.css"' not in html
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(html)
print(output)
