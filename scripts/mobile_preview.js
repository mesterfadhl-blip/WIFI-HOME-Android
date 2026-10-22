'use strict';
const root=document.getElementById('root');
function show(){
 const route=decodeURIComponent(location.hash.slice(1))||'sales';
 root.innerHTML=PAGES[route]||PAGES.sales;
 root.querySelectorAll('[data-action="logout"]').forEach(b=>b.remove());
 const footer=root.querySelector('.footer');if(footer)footer.textContent='معاينة محلية فقط · بيانات تجريبية · دون حفظ أو مزامنة';
 root.querySelectorAll('input[type="date"]').forEach(i=>{i.value=i.name==='from'?'2026-10-01':'2026-10-22';});
 if(route==='new') document.querySelector('#totals').textContent='معاينة نموذج الفاتورة فقط — دون حفظ أو احتساب معاملات';
 window.scrollTo(0,0);
}
function doc(path){
 const body=DOCS[path.split('?')[0]];
 if(!body){alert('هذا المستند غير مضاف إلى ملف المعاينة.');return;}
 root.innerHTML='<button class="preview-close" id="close-doc">← الرجوع للنظام</button><iframe id="preview-doc" title="مستند المعاينة" sandbox="allow-modals allow-same-origin"></iframe>';
 document.getElementById('preview-doc').srcdoc=body;
 document.getElementById('preview-doc').onload=()=>{
  const d=document.getElementById('preview-doc');
  const b=d.contentDocument.querySelector('#print-document');
  if(b)b.onclick=()=>d.contentWindow.print();
 };
 document.getElementById('close-doc').onclick=show;
 window.scrollTo(0,0);
}
document.addEventListener('click',e=>{
 const a=e.target.closest('a');
 if(a){
  const href=a.getAttribute('href')||'';
  if(href.startsWith('#'))return;
  e.preventDefault();
  if(href.startsWith('/print/'))return doc(href);
  alert('هذه معاينة للعرض؛ التصدير والحفظ متاحان في نسخة الخادم.');return;
 }
 const b=e.target.closest('button');
 if(!b||b.id==='close-doc')return;
 if(b.dataset.open){location.hash='invoice/'+b.dataset.open;return;}
 if(b.dataset.purchase){location.hash='purchase/'+b.dataset.purchase;return;}
 if(b.dataset.transfer){location.hash='transfer/'+b.dataset.transfer;return;}
 if(b.dataset.statement){doc('/print/statement');return;}
 if(b.dataset.supplierStatement){doc('/print/supplier');return;}
 if(b.dataset.action==='new-invoice'){location.hash='new';return;}
 if(b.dataset.action==='back'){location.hash='sales';return;}
 if(b.dataset.op==='new-purchase'){location.hash='new-purchase';return;}
 if(b.dataset.v3==='transfer-new'){location.hash='new-transfer';return;}
 e.preventDefault();alert('هذه معاينة للعرض فقط ببيانات تجريبية؛ لا يتم حفظ أو ترحيل معاملات.');
});
document.addEventListener('submit',e=>{e.preventDefault();alert('المعاينة تعرض بيانات ثابتة للفترة التجريبية؛ تغيير الفلاتر والحفظ يتطلبان نسخة الخادم.');});
window.addEventListener('hashchange',show);show();
