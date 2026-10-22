"""Independent A4 document layouts; never print the application dashboard."""

import os
from html import escape as esc
from decimal import Decimal
from datetime import datetime, timezone


def money(cents):
    return f"{Decimal(cents)/100:,.2f}"


def text(value):
    return esc(str(value or ""))


def document(title, ref, body, subtitle=""):
    company = text(os.environ.get("ERP_COMPANY", "واي فاي هوم"))
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{text(title)} {text(ref)}</title><style>
@page{{size:A4;margin:18mm 14mm 20mm;@bottom-center{{content:"صفحة " counter(page) " / " counter(pages);font:10px Arial;color:#657181}}}}
*{{box-sizing:border-box}}body{{font:13px Tahoma,Arial,sans-serif;color:#192a3b;margin:0;background:#eef1f5}}.toolbar{{background:#142d43;padding:12px;text-align:center;color:#fff}}button{{font:inherit;padding:9px 20px;border:0;background:#fff;border-radius:4px;cursor:pointer}}article{{background:white;max-width:210mm;margin:24px auto;padding:18mm 14mm;min-height:297mm}}header{{display:flex;justify-content:space-between;border-bottom:3px solid #203d57;padding-bottom:18px;margin-bottom:20px}}.company{{font-size:23px;font-weight:bold}}.en{{font-size:12px;letter-spacing:3px;color:#62758a;direction:ltr;text-align:right;margin-top:6px}}h1{{font-size:22px;margin:0 0 10px}}.ref{{font-size:15px;direction:ltr;text-align:left;color:#40566c}}.meta{{display:grid;grid-template-columns:1fr 1fr;gap:20px;border-bottom:1px solid #d5dee6;margin-bottom:20px;padding-bottom:16px;line-height:2}}.muted{{color:#647489;font-size:11px}}table{{width:100%;border-collapse:collapse;table-layout:fixed;font-size:12px}}th{{background:#eaf0f5;color:#29425b;font-size:11px}}td,th{{border-bottom:1px solid #d8e0e8;padding:10px 6px;text-align:right;vertical-align:top;overflow-wrap:anywhere}}.num{{direction:ltr;text-align:left;font-variant-numeric:tabular-nums;white-space:nowrap}}thead{{display:table-header-group}}tfoot{{display:table-row-group;font-weight:bold}}tr{{break-inside:avoid}}.summary{{margin:20px 0 20px auto;width:80mm;break-inside:avoid}}.summary td{{padding:9px}}.grand{{background:#203d57;color:white;font-size:15px}}.note{{line-height:1.9;border-top:1px solid #d8e0e8;padding-top:13px;font-size:11px;margin-top:20px}}.signatures{{display:flex;justify-content:space-around;margin-top:40px;color:#60758a;font-size:11px;break-inside:avoid}}.signatures div{{border-top:1px solid #aab9c6;padding:12px 18px}}.status{{border:1px solid #8d9ead;padding:4px 10px;font-size:11px;display:inline-block;margin-top:8px}}.stamp{{font-size:11px;color:#687a8c;margin-top:24px}}.empty{{text-align:center;padding:35px}}@media(max-width:650px){{article{{margin:0;padding:18px;min-height:100vh}}table{{font-size:10px}}td,th{{padding:8px 3px}}.company{{font-size:17px}}h1{{font-size:18px}}.summary{{max-width:100%}}.meta{{gap:8px}}}}@media print{{body{{background:white}}.toolbar{{display:none}}article{{padding:0;margin:0;max-width:none;min-height:0}}header{{break-after:avoid}}.meta{{break-after:avoid}}}}
</style><script src="/document.js" defer></script></head><body><div class="toolbar"><button id="print-document">طباعة المستند / حفظ PDF</button><span> · قالب A4 مستقل</span></div><article><header><div><div class="company">{company}</div><div class="en">WIFI HOME · ERP</div><div class="muted">العملة: الريال اليمني · دون ضريبة</div></div><div><h1>{text(title)}</h1><div class="ref">{text(ref)}</div><div class="muted">{text(subtitle)}</div></div></header>{body}<div class="stamp">تاريخ استخراج المستند: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC</div></article></body></html>"""


def invoice_document(s):
    statuses = {
        "draft": "مسودة — غير مرحلة محاسبياً",
        "posted": "فاتورة مرحلة",
        "cancelled": "ملغاة",
        "superseded": "استُبدلت بإصدار تعديل",
    }
    rows = "".join(
        f'<tr><td>{i}</td><td>{text(l["name"])}</td><td class="num">{l["qty"]}</td><td class="num">{money(l["price"])}</td><td class="num">{money(l["price"]*l["qty"])}</td></tr>'
        for i, l in enumerate(s["lines"], 1)
    )
    body = f"""<div class="meta"><div><span class="muted">فاتورة إلى</span><br><b>{text(s['customer'])}</b><br>{text(s['address'])}<br>{text(s['phone'])}</div><div>تاريخ الفاتورة: <b>{text(s['date'])}</b><br>تاريخ الاستحقاق: <b>{text(s.get('due_date') or s['date'])}</b><br>الحالة: <span class="status">{statuses[s['status']]}</span><br>السداد: {'نقدي' if s['paid']==s['total'] else 'آجل' if not s['paid'] else 'جزئي'}{('<br>بديل الفاتورة ذات المعرف: '+str(s['amends'])) if s['amends'] else ''}</div></div><table><colgroup><col style="width:6%"><col style="width:40%"><col style="width:12%"><col style="width:21%"><col style="width:21%"></colgroup><thead><tr><th>#</th><th>البيان</th><th class="num">الكمية</th><th class="num">سعر الوحدة</th><th class="num">قيمة البند</th></tr></thead><tbody>{rows}</tbody></table><table class="summary"><tbody><tr><td>مجموع البنود</td><td class="num">{money(s['total']+s['discount'])}</td></tr><tr><td>الخصم</td><td class="num">{money(s['discount'])}</td></tr><tr class="grand"><td>صافي الفاتورة</td><td class="num">{money(s['total'])}</td></tr><tr><td>المسدد عند الإصدار</td><td class="num">{money(s['paid'])}</td></tr><tr><td>آجل عند الإصدار</td><td class="num">{money(s['total']-s['paid'])}</td></tr></tbody></table><div class="note">{text(s['note'])}<br>القيم أعلاه تخص هذه الفاتورة وقت إصدارها. رصيد حساب العميل وسندات القبض اللاحقة يظهران في كشف الحساب المستقل.</div><div class="signatures"><div>إعداد / اعتماد</div><div>توقيع المستلم</div></div>"""
    if s["status"] == "posted" and s.get("settlement"):
        payment = s["settlement"]
        block = f'<div class="note"><b>حالة التحصيل عند استخراج المستند</b><br>قبض مخصص لهذه الفاتورة: {money(payment["allocated"])} ر.ي · إشعارات دائنة: {money(payment["credits"])} ر.ي · مردود نقدي: {money(payment["refunds"])} ر.ي<br><b>المتبقي الفعلي للفـاتورة: {money(payment["outstanding"])} ر.ي</b></div>'
        body = body.replace('<div class="note">', block + '<div class="note">', 1)
    return document("فاتورة مبيعات", s["number"], body)


def statement_document(client, opening, rows, f, t):
    running = opening
    bodyrows = []
    for r in rows:
        running += r["debit"] - r["credit"]
        bodyrows.append(
            f'<tr><td>{text(r["date"])}</td><td>{text(r["document"])}</td><td>{text(r["account"])}</td><td class="num">{money(r["debit"])}</td><td class="num">{money(r["credit"])}</td><td class="num">{money(running)}</td></tr>'
        )
    debit = sum(r["debit"] for r in rows)
    credit = sum(r["credit"] for r in rows)
    body = f"""<div class="meta"><div><span class="muted">اسم العميل</span><br><b>{text(client['name'])}</b><br>{text(client['phone'])}</div><div>من: <b>{text(f)}</b><br>إلى: <b>{text(t)}</b><br>رصيد أول الفترة: <b>{money(opening)}</b> ر.ي</div></div><table><colgroup><col style="width:17%"><col style="width:21%"><col style="width:14%"><col style="width:16%"><col style="width:16%"><col style="width:16%"></colgroup><thead><tr><th>التاريخ</th><th>المستند</th><th>الحساب</th><th class="num">مدين</th><th class="num">دائن</th><th class="num">الرصيد</th></tr></thead><tbody>{''.join(bodyrows) or '<tr><td colspan="6" class="empty">لا توجد حركة خلال الفترة</td></tr>'}</tbody><tfoot><tr><td colspan="3">مجموع حركة الفترة</td><td class="num">{money(debit)}</td><td class="num">{money(credit)}</td><td class="num">{money(running)}</td></tr></tfoot></table><table class="summary"><tr><td>رصيد أول الفترة</td><td class="num">{money(opening)}</td></tr><tr><td>إجمالي المدين</td><td class="num">{money(debit)}</td></tr><tr><td>إجمالي الدائن</td><td class="num">{money(credit)}</td></tr><tr class="grand"><td>رصيد آخر الفترة</td><td class="num">{money(running)}</td></tr></table><div class="note">الرصيد المدين موجب: مستحق على العميل. الرصيد السالب: رصيد دائن للعميل. يشمل الكشف قيود العكس والتعديلات لضمان تتبع الحركات.</div>"""
    return document("كشف حساب عميل", f'C-{client["id"]:06}', body, "حركة حساب تفصيلية")


def sales_document(rows, totals, f, t):
    bodyrows = "".join(
        f'<tr><td>{text(r["number"])}</td><td>{text(r["date"])}</td><td>{text(r["customer"])}</td><td class="num">{money(r["total"])}</td><td class="num">{money(r["cost"])}</td><td class="num">{money(r["total"]-r["cost"])}</td></tr>'
        for r in rows
    )
    body = f"""<div class="meta"><div>الفترة: <b>{text(f)} — {text(t)}</b><br>المستندات: <b>{len(rows)}</b></div><div>أساس التقرير: الفواتير والإشعارات الدائنة المرحلة<br>المسودات والملغى والمستبدل: مستبعدة</div></div><table><colgroup><col style="width:17%"><col style="width:17%"><col style="width:21%"><col style="width:15%"><col style="width:15%"><col style="width:15%"></colgroup><thead><tr><th>الفاتورة</th><th>التاريخ</th><th>العميل</th><th class="num">صافي البيع</th><th class="num">التكلفة</th><th class="num">مجمل الربح</th></tr></thead><tbody>{bodyrows or '<tr><td colspan="6" class="empty">لا توجد فواتير مرحلة</td></tr>'}</tbody><tfoot><tr><td colspan="3">الإجمالي</td><td class="num">{money(totals['total'])}</td><td class="num">{money(totals['cost'])}</td><td class="num">{money(totals['profit'])}</td></tr></tfoot></table><div class="note">صافي البيع = مجموع البنود − الخصم. مجمل الربح = صافي البيع − تكلفة المبيعات المسجلة عند الترحيل. لا يمثل مجمل الربح صافي الربح بعد مصروفات التشغيل.<br>صافي الدفع والمردود عند الإصدار: {money(totals['paid'])} ر.ي · سندات قبض خلال الفترة: {money(totals['receipts'])} ر.ي. سندات القبض قد تخص فواتير سابقة، ولا تُحتسب كنسبة سداد لفواتير هذه الفترة.</div>"""
    return document("تقرير المبيعات", "SALES", body)


def purchase_document(s):
    rows = "".join(
        f'<tr><td>{i}</td><td>{text(l["name"])}</td><td class="num">{l["qty"]}</td><td class="num">{money(l["cost"])}</td><td class="num">{money(l["qty"]*l["cost"])}</td></tr>'
        for i, l in enumerate(s["lines"], 1)
    )
    body = f"""<div class="meta"><div>المورد: <b>{text(s['supplier'])}</b><br>{text(s['phone'])}<br>{text(s['address'])}</div><div>التاريخ: {text(s['date'])}<br>الحالة: {text({'draft':'مسودة غير مرحلة','posted':'مرحلة ومستلمة','cancelled':'ملغاة'}[s['status']])}</div></div><table><colgroup><col style="width:7%"><col style="width:36%"><col style="width:13%"><col style="width:22%"><col style="width:22%"></colgroup><thead><tr><th>#</th><th>الصنف</th><th class="num">الكمية</th><th class="num">تكلفة الوحدة</th><th class="num">القيمة</th></tr></thead><tbody>{rows}</tbody></table><table class="summary"><tr class="grand"><td>إجمالي الشراء</td><td class="num">{money(s['total'])}</td></tr><tr><td>المسدد عند الإصدار</td><td class="num">{money(s['paid'])}</td></tr><tr><td>الآجل عند الإصدار</td><td class="num">{money(s['total']-s['paid'])}</td></tr></table><div class="note">{text(s['note'])}<br>هذا المستند يثبت الشراء والاستلام عند ترحيله. سندات الصرف اللاحقة تظهر في كشف حساب المورد.</div><div class="signatures"><div>استلام المخزون</div><div>اعتماد المحاسب</div></div>"""
    return document("فاتورة شراء واستلام", s["number"], body)


def return_document(s):
    rows = "".join(
        f'<tr><td>{text(l["name"])}</td><td class="num">{l["qty"]}</td><td class="num">{money(l["net"])}</td></tr>'
        for l in s["lines"]
    )
    body = f"""<div class="meta"><div>العميل: <b>{text(s['customer'])}</b><br>مرجع الفاتورة: {text(s['invoice'])}</div><div>تاريخ المرتجع: {text(s['date'])}<br>الحالة: {'مرحل' if s['status']=='posted' else 'ملغى'}</div></div><table><colgroup><col style="width:55%"><col style="width:15%"><col style="width:30%"></colgroup><thead><tr><th>البند المرتجع</th><th class="num">الكمية</th><th class="num">القيمة بعد نصيب الخصم</th></tr></thead><tbody>{rows}</tbody></table><table class="summary"><tr class="grand"><td>قيمة الإشعار الدائن</td><td class="num">{money(s['total'])}</td></tr><tr><td>مردود نقدي</td><td class="num">{money(s['refund'])}</td></tr><tr><td>تخفيض رصيد العميل</td><td class="num">{money(s['total']-s['refund'])}</td></tr></table><div class="note">السبب: {text(s['reason'])}<br>القيمة مأخوذة من الفاتورة الأصلية بعد توزيع الخصم. تُعاد تكلفة المخزون الأصلية للمبيعات، ولا يُستخدم سعر بيع جديد للمرتجع.</div>"""
    return document("إشعار دائن — مرتجع مبيعات", s["number"], body)


def supplier_document(supplier, opening, rows, f, t):
    running = opening
    details = []
    for r in rows:
        running += r["credit"] - r["debit"]
        details.append(
            f'<tr><td>{text(r["date"])}</td><td>{text(r["document"])}</td><td class="num">{money(r["debit"])}</td><td class="num">{money(r["credit"])}</td><td class="num">{money(running)}</td></tr>'
        )
    body = f"""<div class="meta"><div>المورد: <b>{text(supplier['name'])}</b><br>{text(supplier['phone'])}</div><div>الفترة: {text(f)} — {text(t)}<br>رصيد أول الفترة: {money(opening)}</div></div><table><colgroup><col style="width:20%"><col style="width:26%"><col style="width:18%"><col style="width:18%"><col style="width:18%"></colgroup><thead><tr><th>التاريخ</th><th>المستند</th><th class="num">مدين / سداد</th><th class="num">دائن / شراء</th><th class="num">المستحق</th></tr></thead><tbody>{''.join(details) or '<tr><td colspan="5">لا توجد حركة</td></tr>'}</tbody><tfoot><tr><td colspan="2">إجمالي حركة الفترة</td><td class="num">{money(sum(r['debit'] for r in rows))}</td><td class="num">{money(sum(r['credit'] for r in rows))}</td><td class="num">{money(running)}</td></tr></tfoot></table><table class="summary"><tr><td>رصيد أول الفترة</td><td class="num">{money(opening)}</td></tr><tr class="grand"><td>رصيد آخر الفترة</td><td class="num">{money(running)}</td></tr></table><div class="note">الرصيد الموجب يمثل مبلغاً مستحقاً للمورد. يشمل الكشف فواتير الشراء والسداد وقيود الإلغاء.</div>"""
    return document("كشف حساب مورد", f'SUP-{supplier["id"]:06}', body)


def finance_document(s):
    lines = [
        ("المبيعات قبل المرتجعات", s["sales"]),
        ("مردودات المبيعات", -s["returns"]),
        ("صافي المبيعات", s["net_sales"]),
        ("تكلفة المبيعات بعد المرتجعات", -s["cost"]),
        ("مجمل الربح", s["gross_profit"]),
        ("مصروفات التشغيل", -s["expenses"]),
        ("أثر فروق تكلفة مردودات المشتريات", -s.get("purchase_return_variance", 0)),
        ("صافي نتيجة الفترة", s["net_profit"]),
    ]
    body = f"""<div class="meta"><div>الفترة: <b>{text(s['from'])} — {text(s['to'])}</b></div><div>أساس التقرير: القيود المرحلة<br>دون ضريبة</div></div><table><colgroup><col style="width:70%"><col style="width:30%"></colgroup><thead><tr><th>البيان</th><th class="num">ريال يمني</th></tr></thead><tbody>{''.join(f'<tr class="{ "grand" if i==len(lines)-1 else ""}"><td>{text(label)}</td><td class="num">{money(value)}</td></tr>' for i,(label,value) in enumerate(lines))}</tbody></table><h2 style="margin-top:30px">ميزان المراجعة التراكمي حتى {text(s['to'])}</h2><table><colgroup><col style="width:50%"><col style="width:25%"><col style="width:25%"></colgroup><thead><tr><th>الحساب</th><th class="num">حركة مدين</th><th class="num">حركة دائن</th></tr></thead><tbody>{''.join(f'<tr><td>{text(r["account"])}</td><td class="num">{money(r["debit"])}</td><td class="num">{money(r["credit"])}</td></tr>' for r in s['trial'])}</tbody><tfoot><tr><td>الإجمالي</td><td class="num">{money(s['debits'])}</td><td class="num">{money(s['credits'])}</td></tr></tfoot></table><div class="note">قائمة الربح والخسارة تخص الفترة المحددة. ميزان المراجعة تراكمي حتى نهاية الفترة. تقييم المخزون الحالي يُعرض في شاشة المخزون ولا يُنسب تلقائياً إلى تاريخ قديم.</div>"""
    return document("قائمة الربح والخسارة وميزان المراجعة", "FINANCIAL", body)


def aging_document(s):
    labels = {
        "not_due": "غير متأخر",
        "days_1_30": "1–30 يوماً",
        "days_31_60": "31–60 يوماً",
        "days_61_90": "61–90 يوماً",
        "over_90": "أكثر من 90 يوماً",
    }
    rows = "".join(
        f'<tr><td>{text(r["number"])}</td><td>{text(r["customer"])}</td><td>{text(r["due_date"])}</td><td class="num">{r["days_overdue"]}</td><td class="num">{money(r["outstanding"])}</td></tr>'
        for r in s["rows"]
    )
    body = f"""<div class="meta"><div>الرصيد حتى: <b>{text(s['asof'])}</b></div><div>الأساس: فواتير مرحلة بعد تخصيص القبض والمرتجعات</div></div><table><colgroup><col style="width:20%"><col style="width:30%"><col style="width:20%"><col style="width:10%"><col style="width:20%"></colgroup><thead><tr><th>الفاتورة</th><th>العميل</th><th>تاريخ الاستحقاق</th><th class="num">تأخير / يوم</th><th class="num">المتبقي الفعلي</th></tr></thead><tbody>{rows or '<tr><td colspan="5">لا توجد فواتير مستحقة</td></tr>'}</tbody></table><h2 style="margin-top:25px">تحليل أعمار المستحقات</h2><table><thead><tr><th>الشريحة</th><th class="num">الرصيد</th></tr></thead><tbody>{''.join(f'<tr><td>{label}</td><td class="num">{money(s["buckets"][key])}</td></tr>' for key,label in labels.items())}</tbody></table><table class="summary"><tr><td>إجمالي الفواتير المفتوحة</td><td class="num">{money(s['gross_outstanding'])}</td></tr><tr><td>قبض غير مخصص</td><td class="num">{money(s['unapplied_receipts'])}</td></tr><tr><td>أرصدة دائنة من المرتجعات</td><td class="num">{money(s['customer_credits'])}</td></tr><tr class="grand"><td>صافي حسابات العملاء</td><td class="num">{money(s['net_receivable'])}</td></tr></table><div class="note">لا يوزع النظام الأرصدة غير المخصصة على الفواتير تلقائياً. التخصيص يحدد علاقة السداد بالمستند ولا يكرر قيد القبض. لا تُحتسب أعمار الدين من تاريخ استخراج التقرير وإنما من تاريخ استحقاق كل فاتورة.</div>"""
    return document("أعمار الذمم المدينة", "AR-AGING", body)


def transfer_document(s):
    total = sum(l["cost"] for l in s["lines"])
    body = f"""<div class="meta"><div>من: <b>{text(s['source'])}</b><br>إلى: <b>{text(s['target'])}</b></div><div>التاريخ: {text(s['date'])}<br>الحالة: {text({'draft':'مسودة','posted':'مرحل','cancelled':'ملغى'}[s['status']])}</div></div><table><colgroup><col style="width:55%"><col style="width:15%"><col style="width:30%"></colgroup><thead><tr><th>الصنف</th><th class="num">الكمية</th><th class="num">القيمة المنقولة</th></tr></thead><tbody>{''.join(f'<tr><td>{text(l["name"])}</td><td class="num">{l["qty"]}</td><td class="num">{money(l["cost"])}</td></tr>' for l in s['lines'])}</tbody><tfoot><tr><td colspan="2">إجمالي القيمة</td><td class="num">{money(total)}</td></tr></tfoot></table><div class="note">{text(s['note'])}<br>تحويل داخلي بين مستودعات المنشأة دون تغيير الملكية. لا يغيّر إجمالي قيمة المخزون ولا يولّد إيراداً أو مصروفاً.</div><div class="signatures"><div>أمين المستودع المرسل</div><div>أمين المستودع المستلم</div></div>"""
    return document("سند تحويل مخزني", s["number"], body)


def reconciliation_document(s):
    rows = "".join(
        f'<tr><td>{text(l["date"])}</td><td>{text(l["reference"])}</td><td class="num">{money(l["amount"])}</td><td>{text(l["document"] or "غير مطابق")}</td></tr>'
        for l in s["lines"]
    )
    final = s["status"] == "final"
    summary = (
        f'<tr><td>حركات دفترية معلقة</td><td class="num">{money(s["unmatched_book"])}</td></tr><tr class="grand"><td>رصيد الدفاتر عند الاعتماد</td><td class="num">{money(s["book_closing"])}</td></tr>'
        if final
        else ""
    )
    body = f"""<div class="meta"><div>الحساب: <b>{text(s['bank'])}</b><br>الكود: {text(s['code'])}</div><div>الفترة: {text(s['from_date'])} — {text(s['to_date'])}<br>الحالة: {'تسوية معتمدة' if final else 'مسودة مطابقة — غير معتمدة'}</div></div><table><colgroup><col style="width:20%"><col style="width:25%"><col style="width:22%"><col style="width:33%"></colgroup><thead><tr><th>تاريخ البنك</th><th>مرجع البنك</th><th class="num">المبلغ الموقّع</th><th>المستند الدفتري المطابق</th></tr></thead><tbody>{rows or '<tr><td colspan="4">لا توجد حركات في الكشف</td></tr>'}</tbody></table><table class="summary"><tr><td>رصيد أول الكشف</td><td class="num">{money(s['opening'])}</td></tr><tr><td>رصيد نهاية الكشف</td><td class="num">{money(s['closing'])}</td></tr>{summary}</table><div class="note">المبالغ الموجبة إيداعات، والسالبة سحوبات. الرصيد الدفتري المعدل = رصيد كشف البنك + الحركات الدفترية التي لم تظهر بعد في البنك. المطابقة لا تُنشئ قيوداً مالية جديدة، ولا تُرحّل رسوم البنك تلقائياً.</div>"""
    return document("محضر تسوية بنكية", s["reference"], body)
