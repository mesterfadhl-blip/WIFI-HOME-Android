import {
  emptyDB,
  normalize,
  round,
  balance,
  cash,
  saveInvoice,
  cancelInvoice,
  receipt,
  expense,
  report,
  ledger,
  day,
} from "./core.mjs";
const KEY = "wifiHomeERP.v1",
  LEGACY = "cardFinanceV2",
  money = (n) =>
    Number(n || 0).toLocaleString("ar-YE", { maximumFractionDigits: 2 }),
  today = () =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Aden",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    ),
  $ = (s) => document.querySelector(s),
  customer = (id) => db.customers.find((c) => c.id === id),
  product = (id) => db.products.find((p) => p.id === id),
  name = (id) => customer(id)?.name || "عميل غير موجود";
let db = emptyDB(),
  stored = null,
  readFailed = false,
  filters = {
    from: today().slice(0, 7) + "-01",
    to: today(),
    customerId: "",
    productId: "",
  },
  reportTab = "sales",
  draft = null,
  editing = null;
try {
  stored = localStorage.getItem(KEY);
  if (stored) db = normalize(JSON.parse(stored));
} catch (e) {
  readFailed = true;
  $("#notice").textContent = "تعذر قراءة البيانات: " + e.message;
  $("#notice").className = "error";
}
const pages = {
  home: "نظرة عامة",
  sales: "فواتير المبيعات",
  customers: "العملاء",
  inventory: "الأصناف والمخزون",
  cash: "الصندوق",
  reports: "التقارير والتحليل",
  settings: "الإعدادات والبيانات",
};
function message(text, error = false) {
  $("#notice").className = error ? "error" : "success";
  $("#notice").textContent = text;
}
function commit(next) {
  if (readFailed)
    throw Error("تعذر قراءة البيانات المخزنة؛ صدّرها للمراجعة قبل أي تعديل.");
  const actual = localStorage.getItem(KEY);
  if (actual !== stored)
    throw Error(
      "تغيّرت البيانات في تبويب آخر. أعد تحميل الصفحة قبل الحفظ لتجنب فقد التغييرات.",
    );
  const text = JSON.stringify(next);
  localStorage.setItem(KEY, text);
  stored = text;
  db = next;
}
function attempt(fn) {
  try {
    fn();
  } catch (e) {
    message(e.message, true);
  }
}
function table(head, rows) {
  return `<div class="table-wrap"><table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") || `<tr><td colspan="${head.length}" class="empty">لا توجد بيانات مطابقة</td></tr>`}</tbody></table></div>`;
}
function kpis(items) {
  return `<div class="kpis">${items.map(([t, v, n]) => `<div class="kpi"><span>${t}</span><strong>${v === null ? "—" : money(v)}</strong><small>${n || "ريال يمني"}</small></div>`).join("")}</div>`;
}
function options(list, value, all) {
  return (
    (all !== undefined ? `<option value="">${all}</option>` : "") +
    list
      .map(
        (x) =>
          `<option value="${esc(x.id)}" ${x.id === value ? "selected" : ""}>${esc(x.name)}</option>`,
      )
      .join("")
  );
}
function field(label, name, type = "text", value = "", extra = "") {
  return `<div><label for="${name}">${label}</label><input id="${name}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`;
}
function filtersUI(withProduct = true) {
  return `<form id="filters" class="card filters">${field("من تاريخ", "from", "date", filters.from)}${field("إلى تاريخ", "to", "date", filters.to)}<div><label>العميل</label><select name="customerId">${options(db.customers, filters.customerId, "كل العملاء")}</select></div>${withProduct ? `<div><label>الصنف</label><select name="productId">${options(db.products, filters.productId, "كل الأصناف")}</select></div>` : ""}<div class="actions"><button>تطبيق</button><button type="button" class="secondary" data-action="clear-filters">كل الفترات</button></div></form>`;
}
function invoiceRows(rows) {
  return rows.map(
    (s) =>
      `<tr><td><button class="link" data-view="${esc(s.ref)}">${esc(s.ref)}</button><small>مراجعة ${s.revision || 1}</small></td><td>${esc(day(s.date))}</td><td>${esc(name(s.customerId))}</td><td>${money(s.total)}</td><td>${money(s.paid)}</td><td>${money(s.credit)}</td><td><span class="pill ${s.status === "ملغاة" ? "bad" : ""}">${esc(s.status || "معتمدة")}</span></td><td><div class="actions"><button class="link" data-view="${esc(s.ref)}">عرض</button>${s.status !== "ملغاة" ? `<button class="link" data-edit="${esc(s.ref)}">تعديل</button>` : ""}</div></td></tr>`,
  );
}
function invoicesTable(rows) {
  return table(
    [
      "الفاتورة",
      "التاريخ",
      "العميل",
      "صافي الفاتورة",
      "المسدد عند البيع",
      "الآجل عند البيع",
      "الحالة",
      "الإجراءات",
    ],
    invoiceRows(rows),
  );
}
function home() {
  const r = report(db, { from: today(), to: today() });
  return `<div class="note">مساحة عمل فعلية دون أرقام تجريبية. ابدأ بالعملاء والأصناف، ثم أنشئ فاتورة بيع. الأرقام أدناه مشتقة من المستندات المعتمدة.</div>${kpis(
    [
      ["صافي مبيعات اليوم", r.net, "بعد الخصم، دون الملغى"],
      ["تحصيل اليوم", r.collections, "مسدد الفواتير + سندات قبض اليوم"],
      ["مجمل ربح اليوم", r.grossProfit, "صافي البيع − تكلفة المبيعات"],
      ["رصيد الصندوق", cash(db), "رصيد تراكمي من القيود"],
    ],
  )}<div class="two"><div class="card"><div class="split"><h2>آخر الفواتير</h2><a href="#sales">كل الفواتير</a></div>${invoicesTable(db.sales.slice(-6).reverse())}</div><div class="card"><h2>ما يحتاج انتباهك</h2><p>مديونية العملاء: <b>${money(db.customers.reduce((n, c) => n + Math.max(0, balance(db, c.id)), 0))}</b> ر.ي</p><p>أصناف عند حد الطلب: <b>${db.products.filter((p) => !p.service && Number(p.qty) <= Number(p.min || 0)).length}</b></p><p>عدد الفواتير الملغاة: <b>${db.sales.filter((s) => s.status === "ملغاة").length}</b></p><div class="formula">صافي المبيعات = مجموع البنود − الخصم<br>مجمل الربح = صافي المبيعات − تكلفة البنود<br>صافي نتيجة الفترة = مجمل الربح − المصروفات</div></div></div>`;
}
function sales() {
  const rows = db.sales
    .filter(
      (s) =>
        (!filters.from || day(s.date) >= filters.from) &&
        (!filters.to || day(s.date) <= filters.to) &&
        (!filters.customerId || s.customerId === filters.customerId),
    )
    .slice()
    .reverse();
  return `${filtersUI(false)}<div class="card"><div class="split"><h2>سجل فواتير البيع</h2><button data-action="new-sale">+ فاتورة جديدة</button></div><p class="muted">الآجل هنا هو المتبقي وقت إصدار الفاتورة، وليس الرصيد الحالي للعميل. سندات القبض منفصلة ولا تُنسب إلى فاتورة دون تخصيص.</p><input id="search-invoice" placeholder="بحث برقم الفاتورة أو اسم العميل" aria-label="بحث الفواتير"><div id="invoice-list">${invoicesTable(rows)}</div></div>`;
}
function startInvoice(ref = null) {
  if (draft && !confirm("ترك الفاتورة غير المحفوظة؟")) return;
  editing = ref;
  const s = db.sales.find((s) => s.ref === ref);
  draft = s
    ? structuredClone(s)
    : {
        date: today(),
        customerId: "",
        payType: "cash",
        discount: 0,
        paid: 0,
        note: "",
        lines: [],
      };
  draft.date = day(draft.date);
  draft.reason = "";
  if (!draft.lines.length)
    draft.lines.push({ productId: "", qty: 1, price: 0 });
  location.hash = ref ? "edit/" + encodeURIComponent(ref) : "new";
  render();
}
function lineRow(l, i) {
  return `<tr><td><select data-line="${i}" data-key="productId" aria-label="الصنف ${i + 1}">${options(
    db.products.filter((p) => !p.inactive),
    l.productId,
    "اختر الصنف",
  )}</select></td><td><input type="number" min="0.001" step="any" value="${esc(l.qty)}" data-line="${i}" data-key="qty" aria-label="الكمية ${i + 1}"></td><td><input type="number" min="0" step="0.01" value="${esc(l.price)}" data-line="${i}" data-key="price" aria-label="السعر ${i + 1}"></td><td id="line-total-${i}">${money(Number(l.qty) * Number(l.price))}</td><td><button type="button" class="danger" data-remove="${i}" aria-label="حذف البند ${i + 1}">×</button></td></tr>`;
}
function editor() {
  if (!draft) return '<div class="card">افتح الفاتورة من سجل المبيعات.</div>';
  return `<form id="invoice-form"><div class="note ${editing ? "warn" : ""}">${editing ? "تعديل " + esc(editing) + " · سيُحفظ رقم الفاتورة وتُنشأ مراجعة جديدة. تُعكس القيود وحركة المخزون السابقة قبل ترحيل الجديدة." : "فاتورة جديدة · لن تُحفظ أو تؤثر على المخزون والحسابات قبل الاعتماد."}</div><div class="card form-grid"><div><label>العميل</label><select name="customerId" required>${options(
    db.customers.filter((c) => !c.inactive),
    draft.customerId,
    "اختر العميل",
  )}</select><small id="customer-balance"></small></div>${field("تاريخ الفاتورة", "date", "date", draft.date, "required")}<div><label>طريقة الدفع</label><select name="payType"><option value="cash" ${draft.payType === "cash" ? "selected" : ""}>نقدي</option><option value="credit" ${draft.payType === "credit" ? "selected" : ""}>آجل</option><option value="mixed" ${draft.payType === "mixed" ? "selected" : ""}>سداد جزئي</option></select></div>${field("المسدد عند البيع", "paid", "number", draft.paid, 'min="0" step="0.01"')}</div><div class="card"><h2>بنود الفاتورة</h2><div class="table-wrap"><table class="items"><thead><tr><th>الصنف</th><th>الكمية</th><th>سعر الوحدة</th><th>الإجمالي</th><th></th></tr></thead><tbody>${draft.lines.map(lineRow).join("")}</tbody></table></div><button type="button" class="secondary" data-action="add-line">+ إضافة بند</button></div><div class="two"><div class="card stack">${field("ملاحظات الفاتورة", "note", "text", draft.note)}${editing ? field("سبب التعديل (إلزامي)", "reason", "text", draft.reason, "required") : ""}<p class="muted">لا ضريبة على هذه الفاتورة. تكلفة المبيعات تُقرأ من تكلفة الصنف وتُحفظ وقت البيع؛ لا تتغير أسعار التكلفة القديمة بتغيير قائمة الأسعار.</p></div><div class="card">${field("خصم إجمالي الفاتورة", "discount", "number", draft.discount, 'min="0" step="0.01"')}<div id="totals" class="summary"></div></div></div><div class="actions"><button type="submit">${editing ? "حفظ وترحيل التعديل" : "اعتماد الفاتورة"}</button><button type="button" class="secondary" data-action="discard">إلغاء والرجوع</button></div></form>`;
}
function calc() {
  if (!draft || !$("#invoice-form")) return;
  const subtotal = round(
      draft.lines.reduce((n, l) => n + Number(l.qty) * Number(l.price), 0),
    ),
    total = round(subtotal - Number(draft.discount)),
    paid =
      draft.payType === "cash"
        ? total
        : draft.payType === "credit"
          ? 0
          : Number(draft.paid || 0);
  $("#invoice-form [name=paid]").disabled = draft.payType !== "mixed";
  if (draft.payType !== "mixed") $("#invoice-form [name=paid]").value = paid;
  $("#totals").innerHTML =
    `<div><span>مجموع البنود</span><b>${money(subtotal)}</b></div><div><span>الخصم</span><b>${money(draft.discount)}</b></div><div class="total"><span>صافي الفاتورة</span><b>${money(total)}</b></div><div><span>المسدد</span><b>${money(paid)}</b></div><div><span>آجل عند البيع</span><b>${money(total - paid)}</b></div>`;
  const c = customer(draft.customerId);
  $("#customer-balance").textContent = c
    ? "رصيد العميل الحالي: " +
      money(balance(db, c.id)) +
      " ر.ي (يشمل الفاتورة القديمة عند التعديل)"
    : "";
}
function invoiceView(ref) {
  const s = db.sales.find((s) => s.ref === ref);
  if (!s) return '<div class="card">الفاتورة غير موجودة.</div>';
  const c = customer(s.customerId),
    revisions = db.audit.filter((a) => a.ref === ref);
  return `<div class="screen-actions actions"><button data-action="print">طباعة / حفظ PDF</button>${s.status !== "ملغاة" ? `<button data-edit="${esc(ref)}">تعديل الفاتورة</button><button class="danger" data-cancel="${esc(ref)}">إلغاء الفاتورة</button>` : ""}<a class="button secondary" href="#sales">رجوع إلى الفواتير</a></div><article class="card invoice"><div class="invoice-top"><div><h2>${esc(db.settings.company)}</h2><small>فاتورة بيع · ريال يمني · دون ضريبة</small></div><div><b>${esc(ref)}</b><p><span class="pill ${s.status === "ملغاة" ? "bad" : ""}">${esc(s.status)}</span> · مراجعة ${s.revision || 1}</p></div></div><div class="invoice-meta"><div><small>العميل</small><b>${esc(c?.name || "—")}</b>${esc(c?.phone || "")}<br>${esc(c?.region || "")}</div><div><small>تاريخ الفاتورة</small><b>${esc(day(s.date))}</b>الدفع: ${{ cash: "نقدي", credit: "آجل", mixed: "سداد جزئي" }[s.payType] || "—"}</div></div>${table(
    ["الصنف", "الكمية", "سعر الوحدة", "الإجمالي"],
    s.lines.map(
      (l) =>
        `<tr><td>${esc(l.name)}</td><td>${money(l.qty)}</td><td>${money(l.price)}</td><td>${money(l.total)}</td></tr>`,
    ),
  )}<div class="summary"><div><span>مجموع البنود</span><b>${money(s.subtotal)}</b></div><div><span>الخصم</span><b>${money(s.discount)}</b></div><div class="total"><span>صافي الفاتورة</span><b>${money(s.total)}</b></div><div><span>المسدد عند البيع</span><b>${money(s.paid)}</b></div><div><span>آجل عند البيع</span><b>${money(s.credit)}</b></div></div><p>${esc(s.note || "")}</p><div class="note">رصيد حساب العميل الحالي: <b>${money(balance(db, s.customerId))} ر.ي</b><br><small>هذا رصيد الحساب الكامل، وليس المتبقي من هذه الفاتورة. سندات القبض اللاحقة غير مخصصة للفواتير.</small></div></article><div class="card no-print"><h2>سجل مراجعات المستند</h2>${table(
    ["التاريخ والوقت", "الإجراء", "السبب", "القيمة قبل", "القيمة بعد"],
    revisions.map(
      (a) =>
        `<tr><td>${esc(a.at)}</td><td>${esc(a.action)}</td><td>${esc(a.reason || "—")}</td><td>${a.before ? money(a.before.total) : "—"}</td><td>${a.after ? money(a.after.total) : "—"}</td></tr>`,
    ),
  )}</div>`;
}
function customers() {
  return `<div class="card"><div class="split"><h2>العملاء وأرصدة الحسابات</h2><button data-action="add-customer">+ عميل</button></div>${table(
    ["العميل", "الهاتف", "المنطقة", "حد الائتمان", "الرصيد الحالي", ""],
    db.customers.map(
      (c) =>
        `<tr><td>${esc(c.name)}</td><td>${esc(c.phone)}</td><td>${esc(c.region)}</td><td>${money(c.limit)}</td><td class="${balance(db, c.id) > 0 ? "bad" : "good"}">${money(balance(db, c.id))}</td><td><button class="link" data-ledger="${esc(c.id)}">كشف الحساب</button></td></tr>`,
    ),
  )}</div>`;
}
function inventory() {
  return `<div class="note">الإضافة هنا للأصناف. استلام الكميات يُرحّل للمخزون مقابل حساب الموردين، ويعيد احتساب متوسط التكلفة.</div><div class="card"><div class="split"><h2>الأصناف والمخزون</h2><button data-action="add-product">+ صنف</button></div>${table(
    [
      "الصنف",
      "النوع",
      "المتوفر",
      "متوسط التكلفة",
      "سعر البيع",
      "قيمة المخزون",
      "",
    ],
    db.products.map(
      (p) =>
        `<tr><td>${esc(p.name)}</td><td>${p.service ? "خدمة" : "مخزني"}</td><td>${p.service ? "—" : money(p.qty)}</td><td>${money(p.cost)}</td><td>${money(p.price)}</td><td>${p.service ? "—" : money(Number(p.qty) * Number(p.cost))}</td><td>${p.service ? "" : `<button class="link" data-stock="${esc(p.id)}">استلام مخزون</button>`}</td></tr>`,
    ),
  )}</div>`;
}
function cashPage() {
  return `${kpis([
    ["رصيد الصندوق", cash(db), "تراكمي من القيود"],
    [
      "سندات القبض",
      db.receipts.reduce((n, r) => n + Number(r.amount), 0),
      "إجمالي كل الفترات",
    ],
    [
      "المصروفات",
      db.expenses.reduce((n, r) => n + Number(r.amount), 0),
      "إجمالي كل الفترات",
    ],
    [
      "مسدد عند البيع",
      db.sales
        .filter((s) => s.status !== "ملغاة")
        .reduce((n, s) => n + Number(s.paid), 0),
      "الفواتير المعتمدة فقط",
    ],
  ])}<div class="card"><div class="split"><h2>حركة الصندوق</h2><div class="actions"><button data-action="receipt">+ سند قبض</button><button class="secondary" data-action="expense">+ مصروف</button></div></div>${table(
    ["التاريخ", "المستند", "البيان", "داخل", "خارج"],
    db.journal
      .filter((j) => j.account === "الصندوق")
      .slice()
      .reverse()
      .map(
        (j) =>
          `<tr><td>${esc(day(j.date))}</td><td>${esc(j.ref)}</td><td>${esc(j.desc)}</td><td>${money(j.debit)}</td><td>${money(j.credit)}</td></tr>`,
      ),
  )}</div>`;
}
function groups(rows, key) {
  const map = new Map();
  for (const s of rows) {
    const k = key(s);
    const x = map.get(k) || { label: k, net: 0, cost: 0, count: 0 };
    x.net = round(x.net + s.net);
    x.cost = round(x.cost + s.selectedCost);
    x.count++;
    map.set(k, x);
  }
  return [...map.values()].sort((a, b) => b.net - a.net);
}
function reports() {
  const r = report(db, filters);
  let content = "";
  if (reportTab === "sales") content = invoicesTable(r.rows);
  if (reportTab === "customers")
    content = table(
      ["العميل", "عدد الفواتير", "صافي المبيعات", "التكلفة", "مجمل الربح"],
      groups(r.rows, (s) => name(s.customerId)).map(
        (x) =>
          `<tr><td>${esc(x.label)}</td><td>${x.count}</td><td>${money(x.net)}</td><td>${money(x.cost)}</td><td>${money(x.net - x.cost)}</td></tr>`,
      ),
    );
  if (reportTab === "daily")
    content = table(
      ["اليوم", "عدد الفواتير", "صافي المبيعات", "التكلفة", "مجمل الربح"],
      groups(r.rows, (s) => day(s.date))
        .sort((a, b) => a.label.localeCompare(b.label))
        .map(
          (x) =>
            `<tr><td>${esc(x.label)}</td><td>${x.count}</td><td>${money(x.net)}</td><td>${money(x.cost)}</td><td>${money(x.net - x.cost)}</td></tr>`,
        ),
    );
  if (reportTab === "products") {
    const data = new Map();
    for (const sale of r.rows) {
      for (const line of sale.lines) {
        if (filters.productId && line.productId !== filters.productId) continue;
        const row = data.get(line.productId) || {
          name: line.name,
          qty: 0,
          net: 0,
          cost: 0,
        };
        const share = Number(sale.subtotal)
          ? Number(line.total) / Number(sale.subtotal)
          : 0;
        row.qty += Number(line.qty);
        row.net = round(row.net + Number(sale.total) * share);
        row.cost = round(row.cost + Number(line.qty) * Number(line.cost || 0));
        data.set(line.productId, row);
      }
    }
    content = table(
      [
        "الصنف",
        "الكمية",
        "صافي المبيعات بعد توزيع الخصم",
        "التكلفة",
        "مجمل الربح",
      ],
      [...data.values()].map(
        (x) =>
          `<tr><td>${esc(x.name)}</td><td>${money(x.qty)}</td><td>${money(x.net)}</td><td>${money(x.cost)}</td><td>${money(x.net - x.cost)}</td></tr>`,
      ),
    );
  }
  if (reportTab === "ledger") {
    if (!filters.customerId)
      content =
        '<div class="empty">اختر عميلاً لعرض كشف الحساب مع الرصيد الافتتاحي.</div>';
    else {
      const l = ledger(db, filters.customerId, filters);
      content = `${kpis([
        ["رصيد أول الفترة", l.opening],
        ["رصيد آخر الفترة", l.closing],
      ])}${table(
        ["التاريخ", "المستند", "البيان", "عليه / مدين", "له / دائن", "الرصيد"],
        l.rows.map(
          (j) =>
            `<tr><td>${esc(day(j.date))}</td><td>${esc(j.ref)}</td><td>${esc(j.desc)}</td><td>${money(j.debit)}</td><td>${money(j.credit)}</td><td>${money(j.balance)}</td></tr>`,
        ),
      )}`;
    }
  }
  const bars = groups(r.rows, (s) => name(s.customerId)).slice(0, 5),
    max = Math.max(1, ...bars.map((x) => x.net));
  return `${filtersUI()}${kpis([
    ["صافي المبيعات", r.net, "بعد الخصم، دون الملغى"],
    ["تكلفة المبيعات", r.cost, "تكلفة البنود وقت البيع"],
    ["مجمل الربح", r.grossProfit, "صافي المبيعات − التكلفة"],
    ["هامش مجمل الربح", r.margin, "% = مجمل الربح ÷ صافي المبيعات"],
  ])}${kpis([
    ["مسدد فواتير الفترة", r.instant, "المسدد عند البيع فقط"],
    [
      "سندات قبض الفترة",
      r.receipts,
      r.receipts === null ? "غير مخصصة للأصناف" : "قد تشمل ديون فترات سابقة",
    ],
    [
      "مصروفات الفترة",
      r.expenses,
      r.expenses === null ? "غير مخصصة للعميل أو الصنف" : "جميع مصروفات الفترة",
    ],
    [
      "صافي نتيجة الفترة",
      r.netProfit,
      r.netProfit === null
        ? "غير متاح مع تصفية عميل أو صنف"
        : "مجمل الربح − المصروفات",
    ],
  ])}<div class="note">التحصيل لا يُعرض كنسبة سداد لفواتير الفترة؛ سندات القبض قد تخص ديوناً سابقة. ${filters.productId ? "عند تصفية صنف، يُوزع خصم الفاتورة والمسدد عليها بنسبة قيمة بنود الصنف قبل الخصم." : ""}</div><div class="card no-print"><h2>أعلى العملاء في الفترة</h2>${bars.map((x) => `<div class="chart-row"><b>${esc(x.label)}</b><span>${money(x.net)} ر.ي</span></div><div class="bar"><i style="width:${Math.max(0, (x.net / max) * 100)}%"></i></div>`).join("") || '<p class="muted">لا توجد مبيعات</p>'}</div><div class="card"><div class="split"><h2>تفاصيل التقرير</h2><div class="actions"><button class="secondary" data-action="export-csv">تصدير CSV</button><button class="secondary" data-action="print">طباعة</button></div></div><div class="subnav no-print">${[
    ["sales", "الفواتير"],
    ["customers", "حسب العميل"],
    ["products", "حسب الصنف"],
    ["daily", "حسب اليوم"],
    ["ledger", "كشف الحساب"],
  ]
    .map(
      ([k, l]) =>
        `<button class="${reportTab === k ? "active" : ""}" data-report="${k}">${l}</button>`,
    )
    .join(
      "",
    )}</div>${reportTab !== "ledger" && filters.productId ? '<p class="muted">جدول الفواتير يعرض المستند كاملاً؛ المؤشرات والتجميعات تخص الصنف المحدد.</p>' : ""}${content}</div>`;
}
function settings() {
  const hasLegacy = !!localStorage.getItem(LEGACY);
  return `<div class="card stack"><h2>حفظ البيانات واستيرادها</h2><div class="note warn">هذه نسخة جديدة مستقلة في هذا المتصفح. لا تحتوي على بيانات تجريبية، ولا تنقل البيانات بين الأجهزة تلقائياً. بيانات النظام السابق لم تُعدّل.</div><button data-action="backup">تنزيل نسخة احتياطية</button><h3>استيراد نسخة احتياطية</h3><p class="muted">سيستبدل بيانات هذه النسخة بعد أخذ نسخة احتياطية تلقائية للبيانات الحالية.</p><input id="import-file" type="file" accept=".json" aria-label="استيراد نسخة احتياطية">${hasLegacy ? '<button class="secondary" data-action="import-legacy">استيراد بيانات النظام السابق من هذا المتصفح</button>' : '<p class="muted">للانتقال من رابط آخر: صدّر نسخة JSON من النظام السابق ثم استوردها هنا.</p>'}</div><div class="card"><h2>سجل العمليات</h2>${table(
    ["التاريخ", "الإجراء", "المستند", "السبب"],
    db.audit
      .slice(-50)
      .reverse()
      .map(
        (a) =>
          `<tr><td>${esc(a.at)}</td><td>${esc(a.action)}</td><td>${esc(a.ref || "—")}</td><td>${esc(a.reason || a.details || "—")}</td></tr>`,
      ),
  )}</div>`;
}
function render() {
  const route = decodeURIComponent(location.hash.slice(1) || "home"),
    [page, ref] = route.split("/");
  if (page === "edit" && (!draft || editing !== ref)) {
    editing = ref;
    const sale = db.sales.find((s) => s.ref === ref);
    draft = sale
      ? { ...structuredClone(sale), date: day(sale.date), reason: "" }
      : null;
  }
  $("#title").textContent =
    page === "new"
      ? "فاتورة بيع جديدة"
      : page === "edit"
        ? "تعديل فاتورة"
        : page === "invoice"
          ? "عرض الفاتورة"
          : pages[page] || pages.home;
  $("#nav").innerHTML = Object.entries(pages)
    .map(
      ([k, v]) =>
        `<a href="#${k}" class="${k === page || (k === "sales" && ["new", "edit", "invoice"].includes(page)) ? "active" : ""}">${v}</a>`,
    )
    .join("");
  $("#view").innerHTML = (
    { home, sales, customers, inventory, cash: cashPage, reports, settings }[
      page
    ] ||
    (["new", "edit"].includes(page)
      ? editor
      : page === "invoice"
        ? () => invoiceView(ref)
        : home)
  )();
  calc();
}
function download(filename, text, type = "application/json") {
  const url = URL.createObjectURL(new Blob([text], { type })),
    a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function backup() {
  download(
    "WIFI-HOME-ERP-" + today() + ".json",
    JSON.stringify(
      {
        format: "WIFI-HOME-ERP",
        version: 1,
        createdAt: new Date().toISOString(),
        data: db,
      },
      null,
      2,
    ),
  );
}
function importData(data) {
  const next = normalize(data.database || data.data || data);
  if (
    !confirm(
      "استبدال بيانات النسخة الجديدة بالملف المحدد؟ احتفظ بنسخة احتياطية خارج المتصفح.",
    )
  )
    return;
  backup();
  commit(next);
  render();
  message("تم الاستيراد. راجع الأرصدة وكشف الحساب قبل اعتماد فواتير جديدة.");
}
function modal(title, body, kind, extra = "") {
  $("#dialog-body").innerHTML =
    `<h2>${title}</h2><form id="modal-form" data-kind="${kind}" data-extra="${esc(extra)}"><div class="form-grid">${body}</div><div class="actions"><button>حفظ</button><button type="button" class="secondary" data-action="close-modal">إلغاء</button></div><p id="modal-error" class="bad" role="alert"></p></form>`;
  $("#modal").showModal();
}
function forms(kind, id = "") {
  if (kind === "add-customer")
    modal(
      "عميل جديد",
      field("اسم العميل", "name", "text", "", "required") +
        field("الهاتف", "phone") +
        field("المنطقة", "region") +
        field("حد الائتمان (صفر = دون حد)", "limit", "number", 0, 'min="0"') +
        field(
          "رصيد افتتاحي مستحق",
          "opening",
          "number",
          0,
          'min="0" step="0.01"',
        ),
      "customer",
    );
  if (kind === "add-product")
    modal(
      "صنف جديد",
      field("اسم الصنف", "name", "text", "", "required") +
        field("سعر البيع", "price", "number", 0, 'min="0" step="0.01"') +
        field("حد إعادة الطلب", "min", "number", 0, 'min="0"') +
        '<div><label>نوع الصنف</label><select name="service"><option value="false">مخزني</option><option value="true">خدمة</option></select></div>',
      "product",
    );
  if (kind === "stock")
    modal(
      "استلام مخزون: " + esc(product(id)?.name),
      field("الكمية", "qty", "number", "", 'min="0.001" step="any" required') +
        field(
          "تكلفة الوحدة",
          "cost",
          "number",
          "",
          'min="0" step="0.01" required',
        ) +
        field("التاريخ", "date", "date", today(), "required"),
      "stock",
      id,
    );
  if (kind === "receipt")
    modal(
      "سند قبض",
      '<div><label>العميل</label><select name="customerId" required>' +
        options(db.customers, "", "اختر العميل") +
        "</select></div>" +
        field(
          "المبلغ",
          "amount",
          "number",
          "",
          'min="0.01" step="0.01" required',
        ) +
        field("التاريخ", "date", "date", today(), "required") +
        field("البيان", "note"),
      "receipt",
    );
  if (kind === "expense")
    modal(
      "مصروف",
      field("البيان", "note", "text", "", "required") +
        field(
          "المبلغ",
          "amount",
          "number",
          "",
          'min="0.01" step="0.01" required',
        ) +
        field("التاريخ", "date", "date", today(), "required"),
      "expense",
    );
}
document.addEventListener("click", (e) =>
  attempt(() => {
    const b = e.target.closest("button,a");
    if (!b) return;
    if (b.dataset.edit) {
      startInvoice(b.dataset.edit);
      return;
    }
    if (b.dataset.view) {
      location.hash = "invoice/" + encodeURIComponent(b.dataset.view);
      return;
    }
    if (b.dataset.cancel) {
      const reason = prompt("سبب إلغاء الفاتورة (إلزامي):");
      if (reason) {
        commit(cancelInvoice(db, b.dataset.cancel, reason));
        render();
        message("أُلغيت الفاتورة وعُكس أثرها على المخزون والحسابات.");
      }
      return;
    }
    if (b.dataset.ledger) {
      filters = { ...filters, customerId: b.dataset.ledger, productId: "" };
      reportTab = "ledger";
      location.hash = "reports";
      render();
      return;
    }
    if (b.dataset.stock) {
      forms("stock", b.dataset.stock);
      return;
    }
    if (b.dataset.report) {
      reportTab = b.dataset.report;
      render();
      return;
    }
    if (b.dataset.remove !== undefined) {
      draft.lines.splice(Number(b.dataset.remove), 1);
      render();
      return;
    }
    const action = b.dataset.action;
    if (action === "new-sale" || b.id === "new-sale") startInvoice();
    if (action === "add-line") {
      draft.lines.push({ productId: "", qty: 1, price: 0 });
      render();
    }
    if (action === "discard") {
      if (confirm("ترك الفاتورة دون حفظ؟")) {
        draft = null;
        location.hash = "sales";
      }
    }
    if (action === "print") window.print();
    if (action === "backup" || b.id === "backup") backup();
    if (action === "clear-filters") {
      filters = { from: "", to: "", customerId: "", productId: "" };
      render();
    }
    if (action === "import-legacy")
      importData(JSON.parse(localStorage.getItem(LEGACY)));
    if (action === "close-modal") $("#modal").close();
    if (["add-customer", "add-product", "receipt", "expense"].includes(action))
      forms(action);
    if (action === "export-csv") {
      const current = $("#view .subnav")
        ?.closest(".card")
        ?.querySelector("table");
      if (current) {
        const rows = [...current.rows].map((tr) =>
          [...tr.cells].map((td) => td.innerText),
        );
        download(
          "report-" + today() + ".csv",
          "\ufeff" +
            rows
              .map((row) =>
                row
                  .map(
                    (value) =>
                      '"' +
                      String(value)
                        .replaceAll('"', '""')
                        .replace(/^[=+@-]/, "'$&") +
                      '"',
                  )
                  .join(","),
              )
              .join("\r\n"),
          "text/csv;charset=utf-8",
        );
        return;
      }
      const r = report(db, filters),
        rows =
          reportTab === "ledger" && filters.customerId
            ? [
                ["التاريخ", "المستند", "مدين", "دائن", "الرصيد"],
                ...ledger(db, filters.customerId, filters).rows.map((j) => [
                  day(j.date),
                  j.ref,
                  j.debit,
                  j.credit,
                  j.balance,
                ]),
              ]
            : [
                [
                  "الفاتورة",
                  "التاريخ",
                  "العميل",
                  "صافي البيع المحدد",
                  "تكلفة البيع المحدد",
                  "مجمل الربح",
                ],
                ...r.rows.map((s) => [
                  s.ref,
                  day(s.date),
                  name(s.customerId),
                  s.net,
                  s.selectedCost,
                  round(s.net - s.selectedCost),
                ]),
              ];
      download(
        "report-" + today() + ".csv",
        "\ufeff" +
          rows
            .map((r) =>
              r
                .map(
                  (x) =>
                    '"' +
                    String(x ?? "")
                      .replaceAll('"', '""')
                      .replace(/^[=+@-]/, "'$&") +
                    '"',
                )
                .join(","),
            )
            .join("\r\n"),
        "text/csv;charset=utf-8",
      );
    }
  }),
);
document.addEventListener("input", (e) => {
  if (e.target.closest("#invoice-form")) {
    const el = e.target;
    if (el.dataset.line !== undefined) {
      const line = draft.lines[Number(el.dataset.line)];
      line[el.dataset.key] = el.value;
      if (el.dataset.key === "productId") {
        line.price = Number(product(el.value)?.price || 0);
        render();
      } else {
        $("#line-total-" + el.dataset.line).textContent = money(
          Number(line.qty) * Number(line.price),
        );
        calc();
      }
    } else if (el.name) {
      draft[el.name] = el.value;
      calc();
    }
  }
  if (e.target.id === "search-invoice") {
    const q = e.target.value.toLowerCase();
    $("#invoice-list tbody")
      .querySelectorAll("tr")
      .forEach(
        (row) => (row.hidden = !row.textContent.toLowerCase().includes(q)),
      );
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "import-file") {
    const f = e.target.files[0];
    if (f)
      f.text()
        .then((text) => attempt(() => importData(JSON.parse(text))))
        .catch((err) => message(err.message, true));
  }
});
document.addEventListener("submit", (e) => {
  e.preventDefault();
  attempt(() => {
    if (e.target.id === "filters") {
      const f = Object.fromEntries(new FormData(e.target));
      if (f.from && f.to && f.from > f.to)
        throw Error("تاريخ البداية بعد النهاية");
      filters = { ...filters, ...f };
      render();
    }
    if (e.target.id === "invoice-form") {
      const result = saveInvoice(db, draft, editing);
      commit(result.db);
      draft = null;
      location.hash = "invoice/" + encodeURIComponent(result.sale.ref);
      render();
      message("تم حفظ الفاتورة وترحيلها: " + result.sale.ref);
    }
    if (e.target.id === "modal-form") {
      const f = Object.fromEntries(new FormData(e.target)),
        kind = e.target.dataset.kind;
      try {
        let next = normalize(db);
        if (kind === "customer") {
          const id = crypto.randomUUID();
          next.customers.push({ id, ...f, limit: Number(f.limit) });
          if (Number(f.opening))
            next.journal.push(
              {
                ref: "OPEN-" + id,
                date: today() + "T00:00:00",
                desc: "رصيد افتتاحي",
                account: "العملاء",
                customerId: id,
                debit: Number(f.opening),
                credit: 0,
              },
              {
                ref: "OPEN-" + id,
                date: today() + "T00:00:00",
                desc: "رصيد افتتاحي",
                account: "رأس المال والأرصدة الافتتاحية",
                debit: 0,
                credit: Number(f.opening),
              },
            );
        }
        if (kind === "product")
          next.products.push({
            id: crypto.randomUUID(),
            name: f.name,
            price: Number(f.price),
            min: Number(f.min),
            service: f.service === "true",
            qty: 0,
            cost: 0,
          });
        if (kind === "stock") {
          const p = next.products.find((p) => p.id === e.target.dataset.extra),
            q = Number(f.qty),
            cost = Number(f.cost);
          if (
            !Number.isFinite(q) ||
            q <= 0 ||
            !Number.isFinite(cost) ||
            cost < 0
          )
            throw Error("أدخل كمية وتكلفة صحيحتين");
          if (
            next.dailyClosings.some(
              (c) => day(c.date) === f.date && c.status !== "ملغاة",
            )
          )
            throw Error("اليوم مغلق محاسبياً");
          const ref = "STK-" + crypto.randomUUID();
          p.cost = round(
            (Number(p.qty) * Number(p.cost) + q * cost) / (Number(p.qty) + q),
          );
          p.qty = round(Number(p.qty) + q);
          next.stockMoves.push({
            ref,
            date: f.date,
            productId: p.id,
            qty: q,
            cost,
            type: "توريد",
          });
          const amount = round(q * cost);
          next.journal.push(
            {
              ref,
              date: f.date + "T12:00:00",
              desc: "استلام مخزون " + p.name,
              account: "المخزون",
              debit: amount,
              credit: 0,
            },
            {
              ref,
              date: f.date + "T12:00:00",
              desc: "استلام مخزون " + p.name,
              account: "الموردون",
              debit: 0,
              credit: amount,
            },
          );
        }
        if (kind === "receipt") next = receipt(db, f);
        if (kind === "expense") next = expense(db, f);
        commit(next);
        $("#modal").close();
        render();
        message("تم الحفظ.");
      } catch (err) {
        $("#modal-error").textContent = err.message;
      }
    }
  });
});
document.addEventListener(
  "click",
  (e) => {
    const link = e.target.closest('a[href^="#"]');
    if (link && draft && link.getAttribute("href") !== location.hash) {
      if (!confirm("ترك الفاتورة دون حفظ؟")) {
        e.preventDefault();
        e.stopImmediatePropagation();
      } else {
        draft = null;
        editing = null;
      }
    }
  },
  true,
);
window.addEventListener("hashchange", () => {
  const route = decodeURIComponent(location.hash.slice(1));
  if (route.startsWith("edit/") && editing !== route.slice(5)) {
    editing = route.slice(5);
    const s = db.sales.find((s) => s.ref === editing);
    draft = s ? { ...structuredClone(s), date: day(s.date), reason: "" } : null;
  }
  render();
  window.scrollTo(0, 0);
});
window.addEventListener("beforeunload", (e) => {
  if (draft) {
    e.preventDefault();
    e.returnValue = "";
  }
});
if (localStorage.getItem(LEGACY) && !stored)
  message(
    "بيانات النسخة السابقة موجودة ولم تتغير. يمكنك استيرادها من الإعدادات.",
  );
render();
