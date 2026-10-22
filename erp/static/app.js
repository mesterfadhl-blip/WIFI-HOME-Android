"use strict";
const $ = (s) => document.querySelector(s),
  esc = (v) =>
    String(v ?? "").replace(
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
  money = (c) =>
    (Number(c || 0) / 100).toLocaleString("ar-YE", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }),
  today = () =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Aden",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());
let dirty = false;
let session = null,
  cache = { customers: [], products: [], invoices: [], audit: [] },
  editing = null,
  draft = null,
  filters = { from: today().slice(0, 7) + "-01", to: today(), customer: "" },
  flash = "";
const states = {
  draft: "مسودة",
  posted: "مرحلة",
  cancelled: "ملغاة",
  superseded: "مستبدلة بتعديل",
};
async function api(path, method = "GET", data) {
  const response = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { "X-CSRF-Token": session.csrf } : {}),
    },
    ...(data ? { body: JSON.stringify(data) } : {}),
  });
  const result = await response.json();
  if (!response.ok) throw Error(result.error || "تعذّر تنفيذ الطلب");
  return result;
}
const options = (items, value, label = "اختر") =>
  `<option value="">${label}</option>` +
  items
    .map(
      (i) =>
        `<option value="${i.id}" ${String(i.id) === String(value) ? "selected" : ""}>${esc(i.name)}</option>`,
    )
    .join("");
const field = (title, name, type = "text", value = "", attrs = "") =>
  `<div><label for="${name}">${title}</label><input id="${name}" name="${name}" type="${type}" value="${esc(value)}" ${attrs}></div>`;
const table = (heads, rows) =>
  `<div class="table"><table><thead><tr>${heads.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") || `<tr><td colspan="${heads.length}" class="empty">لا توجد مستندات. أنشئ أول مستند للبدء.</td></tr>`}</tbody></table></div>`;
const pill = (s) => `<span class="pill ${s}">${states[s]}</span>`;
function notice(error) {
  const n = $("#notice");
  if (n) {
    n.textContent = error;
    n.className = "notice error";
  } else alert(error);
}
function layout(page, title, actions, body) {
  const modules = {
    sales: "المبيعات",
    customers: "العملاء",
    products: "الأصناف",
    purchases: "المشتريات",
    suppliers: "الموردون",
    returns: "المرتجعات",
    finance: "المحاسبة",
    settlements: "التحصيل",
    banks: "البنوك",
    warehouses: "المستودعات",
    reports: "التقارير",
    audit: "سجل التدقيق",
    users: "المستخدمون",
  };
  $("#root").innerHTML =
    `<div class="top"><a class="brand" href="#sales">WIFI HOME <small>ERP</small></a><nav>${Object.entries(
      modules,
    )
      .filter(
        ([key]) =>
          (key !== "users" || session.role === "admin") &&
          (![
            "purchases",
            "suppliers",
            "returns",
            "finance",
            "banks",
            "warehouses",
          ].includes(key) ||
            session.role !== "sales"),
      )
      .map(
        ([key, label]) =>
          `<a href="#${key}" class="${key === page ? "active" : ""}">${label}</a>`,
      )
      .join(
        "",
      )}</nav><div class="user">${esc(session.name)} <button data-action="logout">خروج</button></div></div><main class="workspace"><div class="heading"><div><div class="breadcrumb">مساحة العمل / ${modules[page] || "المبيعات"}</div><h1>${title}</h1></div><div class="actions">${actions || ""}</div></div><div id="notice" class="${flash ? "notice" : ""}">${esc(flash)}</div>${body}<div class="footer">العملة: ريال يمني · دون ضريبة · قاعدة بيانات مشتركة على الخادم · المستندات المرحلة لا تُعدّل مباشرة</div></main><dialog id="modal"></dialog>`;
  flash = "";
}
function invoices(rows) {
  return table(
    [
      "رقم المستند",
      "تاريخ الفاتورة",
      "العميل",
      "صافي القيمة",
      "دفع / مردود عند الإصدار",
      "الحالة",
    ],
    rows.map(
      (s) =>
        `<tr><td><button class="link" ${s.kind === "credit" ? `data-credit="${s.credit_id}"` : `data-open="${s.id}"`}>${esc(s.number)}</button>${s.amends ? "<small> · إصدار تعديل</small>" : ""}</td><td>${esc(s.date)}</td><td>${esc(s.customer)}</td><td class="num">${money(s.total)}</td><td class="num">${money(s.paid)}</td><td>${pill(s.status)}</td></tr>`,
    ),
  );
}
function sales() {
  layout(
    "sales",
    "فواتير المبيعات",
    '<button data-action="new-invoice">إنشاء فاتورة</button>',
    `<div class="panel"><div class="panel-head"><span>كل المستندات <span class="tag">${cache.invoices.length}</span></span><input id="search" aria-label="بحث" placeholder="بحث برقم المستند أو العميل" style="max-width:300px"></div>${invoices(cache.invoices)}</div><div class="help">احفظ الفاتورة كمسودة للمراجعة. الترحيل فقط هو الذي يؤثر على المخزون وحساب العميل والصندوق. إصدار التعديل يحتفظ بالأصل وسجل العكس.</div>`,
  );
}
function editor(s) {
  dirty = false;
  draft = {
    ...s,
    discount: s.id ? s.discount / 100 : 0,
    paid: s.id ? s.paid / 100 : 0,
    lines: s.lines.map((l) => ({
      ...l,
      price: s.id ? l.price / 100 : l.price,
    })),
  };
  editing = s.id || null;
  drawEditor();
}
function drawEditor() {
  const s = draft,
    locked = s.status !== "draft";
  layout(
    "sales",
    s.number || "فاتورة بيع جديدة",
    `<button class="secondary" data-action="back">الفواتير</button>`,
    `<div class="panel"><div class="doc-toolbar"><div class="actions">${locked ? `<a class="btn secondary" target="_blank" href="/print/invoices/${s.id}">مستند الفاتورة / PDF</a>${s.status === "posted" && session.role !== "sales" ? '<button data-action="amend">إصدار تعديل</button><button class="danger" data-action="cancel">إلغاء محاسبي</button>' : ""}` : `<button type="submit" form="invoice-form">حفظ المسودة</button>${s.id ? '<button class="secondary" data-action="post">ترحيل المستند</button>' : ""}`}</div><div class="steps"><span class="${s.status === "draft" ? "on" : ""}">مسودة</span><span class="${s.status === "posted" ? "on" : ""}">مرحلة</span><span class="${["cancelled", "superseded"].includes(s.status) ? "on" : ""}">عكس / استبدال</span></div></div><div class="document"><h2>${esc(s.number || "جديد")}</h2>${s.amends ? `<p class="help">هذا مستند تعديل مرتبط بالفاتورة الأصلية رقم المعرف ${s.amends}. عند الترحيل سيُعكس الأصل وتُرحّل هذه النسخة داخل معاملة واحدة.</p>` : ""}<form id="invoice-form"><fieldset ${locked ? "disabled" : ""} style="border:0;padding:0;margin:0"><div class="fields doc-meta"><div><label>العميل</label><select name="customer_id" required>${options(cache.customers, s.customer_id, "اختر العميل")}</select></div>${field("تاريخ الفاتورة", "date", "date", s.date, "required")}${field("المسدد عند الإصدار", "paid", "number", s.paid, 'min="0" step="0.01"')}${field("خصم الفاتورة", "discount", "number", s.discount, 'min="0" step="0.01"')}</div><div class="table"><table class="lines"><thead><tr><th>الصنف</th><th>الكمية</th><th>سعر الوحدة</th><th>قيمة البند</th><th></th></tr></thead><tbody>${s.lines.map((l, i) => `<tr><td><select data-line="${i}" data-key="product_id" required>${options(cache.products, l.product_id, "اختر الصنف")}</select></td><td><input data-line="${i}" data-key="qty" type="number" min="1" step="1" value="${esc(l.qty)}" required aria-label="الكمية ${i + 1}"></td><td><input data-line="${i}" data-key="price" type="number" min="0" step="0.01" value="${esc(l.price)}" required aria-label="السعر ${i + 1}"></td><td class="num" id="line-${i}">${money(Math.round(Number(l.qty) * Number(l.price) * 100))}</td><td><button class="secondary" type="button" data-remove="${i}" aria-label="حذف البند">×</button></td></tr>`).join("")}</tbody></table></div>${locked ? "" : '<button class="link" type="button" data-action="add-line">+ إضافة بند</button>'}<div class="fields" style="margin-top:25px"><div><label>ملاحظات المستند</label><textarea name="note">${esc(s.note)}</textarea></div><div id="totals" class="totals" style="width:100%"></div></div></fieldset></form><p class="muted">رصيد العميل الكامل يظهر في كشف الحساب المستقل. المسدد هنا هو الدفعة المسجلة عند إصدار الفاتورة.</p></div></div>`,
  );
  totals();
}
function totals() {
  if (!draft || !$("#totals")) return;
  const gross = draft.lines.reduce(
      (n, l) => n + Math.round(Number(l.qty) * Number(l.price) * 100),
      0,
    ),
    discount = Math.round(Number(draft.discount) * 100),
    paid = Math.round(Number(draft.paid) * 100);
  $("#totals").innerHTML =
    `<div><span>مجموع البنود</span><b>${money(gross)}</b></div><div><span>الخصم</span><b>${money(discount)}</b></div><div class="grand"><span>صافي الفاتورة</span><b>${money(gross - discount)}</b></div><div><span>مسدد عند الإصدار</span><b>${money(paid)}</b></div><div><span>آجل عند الإصدار</span><b>${money(gross - discount - paid)}</b></div>`;
}
function customers() {
  layout(
    "customers",
    "العملاء",
    '<button data-action="customer">عميل جديد</button><button class="secondary" data-action="receipt">سند قبض</button>',
    `<div class="panel">${table(
      ["العميل", "الهاتف", "العنوان", "رصيد الحساب", "المخرجات"],
      cache.customers.map(
        (c) =>
          `<tr><td>${esc(c.name)}</td><td>${esc(c.phone)}</td><td>${esc(c.address)}</td><td class="num">${money(c.balance)}</td><td><button class="link" data-statement="${c.id}">كشف حساب مستقل</button></td></tr>`,
      ),
    )}</div>`,
  );
}
function products() {
  layout(
    "products",
    "دليل الأصناف",
    session.role === "admin"
      ? '<button data-action="product">صنف / رصيد افتتاحي</button>'
      : "",
    `<div class="help">الرصيد الافتتاحي يُثبت محاسبياً. استخدم فاتورة الشراء لترحيل الاستلام وتحديث متوسط التكلفة. القيمة المخزنية محفوظة بدقة ولا تعتمد على تقريب تكلفة الوحدة.</div><div class="panel">${table(
      ["الصنف", "النوع", "المتوفر", "تكلفة الوحدة", "سعر البيع"],
      cache.products.map(
        (p) =>
          `<tr><td>${esc(p.name)}</td><td>${p.service ? "خدمة" : "مخزني"}</td><td class="num">${p.service ? "—" : p.qty}</td><td class="num">${money(p.cost)}</td><td class="num">${money(p.price)}</td></tr>`,
      ),
    )}</div>`,
  );
}
function query() {
  return new URLSearchParams(filters).toString();
}
async function reports() {
  const r = await api("/api/reports?" + query());
  layout(
    "reports",
    "تقارير المبيعات والحسابات",
    `<a class="btn secondary" href="/export/sales.csv?${query()}">تصدير CSV</a><a class="btn secondary" target="_blank" href="/print/sales?${query()}">مستند تقرير المبيعات / PDF</a>`,
    `<form id="filters" class="panel padded filters">${field("من تاريخ", "from", "date", filters.from)}${field("إلى تاريخ", "to", "date", filters.to)}<div><label>العميل</label><select name="customer">${options(cache.customers, filters.customer, "كل العملاء")}</select></div><button>تحديث التقرير</button></form><div class="grid">${[
      ["صافي المبيعات", "total", "بعد الخصومات"],
      ["تكلفة المبيعات", "cost", "التكلفة عند الترحيل"],
      ["مجمل الربح", "profit", "قبل مصروفات التشغيل"],
      ["سندات قبض الفترة", "receipts", "قد تخص ديون فترات سابقة"],
    ]
      .map(
        ([title, key, note]) =>
          `<div class="panel metric"><label>${title}</label><strong>${money(r.totals[key])}</strong><small>${note}</small></div>`,
      )
      .join(
        "",
      )}</div><div class="panel"><div class="panel-head"><h2>المستندات المكوّنة للأرقام</h2><span class="muted">الفواتير والإشعارات الدائنة المرحلة</span></div>${invoices(r.rows)}</div><div class="help">التقرير المطبوع مستند مستقل بترويسة وفترة وجدول ومجاميع، ولا يحتوي فلاتر أو أزرار التطبيق. لا نخلط التحصيل بمبيعات الفترة لحساب نسبة سداد مضللة.</div>`,
  );
}
function auditPage() {
  layout(
    "audit",
    "سجل تدقيق المستندات",
    "",
    `<div class="panel padded">${cache.audit.map((a) => `<div class="audit"><b>${esc(a.action)} <span class="tag">${esc(a.document)}</span></b><p>${esc(a.user)} · ${esc(a.at)}</p><p>${esc(a.detail)}</p></div>`).join("") || '<div class="empty">لا توجد عمليات.</div>'}</div>`,
  );
}
function users() {
  layout(
    "users",
    "المستخدمون والصلاحيات",
    '<button data-action="user">إضافة مستخدم</button>',
    `<div class="panel padded"><h2>أدوار العمل</h2>${table(["الدور", "الصلاحيات"], ["<tr><td>المدير</td><td>إدارة المستخدمين والأصناف والعملاء والمستندات وإصدار التعديلات</td></tr>", "<tr><td>المحاسب</td><td>المستندات وسندات القبض والتقارير والعكس المحاسبي</td></tr>", "<tr><td>المبيعات</td><td>مسودات وفواتير البيع والعملاء والقبض، دون عكس المستندات أو إدارة المستخدمين</td></tr>"])}</div>`,
  );
}
async function load() {
  cache = await api("/api/bootstrap");
}
async function navigate() {
  if (!session) return;
  await load();
  const route = location.hash.slice(1) || "sales";
  draft = null;
  if (route.startsWith("invoice/"))
    editor(await api("/api/invoices/" + Number(route.split("/")[1])));
  else if (route === "new")
    editor({
      status: "draft",
      date: today(),
      customer_id: "",
      discount: 0,
      paid: 0,
      note: "",
      lines: [{ product_id: "", qty: 1, price: 0 }],
    });
  else if (route === "reports") await reports();
  else
    (
      ({ sales, customers, products, audit: auditPage, users })[route] || sales
    )();
}
async function loginUI() {
  const status = await api("/api/status");
  session = status.user;
  if (session) {
    await navigate();
    return;
  }
  $("#root").innerHTML =
    `<div class="panel login"><div class="brand">WIFI HOME ERP</div><h1>${status.configured ? "تسجيل الدخول" : "تهيئة مدير النظام"}</h1><p class="muted">${status.configured ? "بياناتك محفوظة على خادم النظام." : "لا توجد كلمة مرور افتراضية. أنشئ حساب المدير الأول قبل بدء العمل."}</p><form id="login" data-mode="${status.configured ? "login" : "setup"}"><div class="fields">${field("اسم المستخدم", "name", "text", "", 'required autocomplete="username"')}${field("كلمة المرور", "password", "password", "", 'required minlength="8" autocomplete="current-password"')}</div><button>${status.configured ? "دخول" : "إنشاء حساب المدير"}</button><p class="auth-error" id="auth-error"></p></form></div>`;
}
function modal(title, body, kind) {
  $("#modal").innerHTML =
    `<h2>${title}</h2><form id="modal-form" data-kind="${kind}"><div class="fields">${body}</div><p class="auth-error" id="modal-error"></p><div class="actions" style="margin-top:20px"><button>حفظ</button><button type="button" class="secondary" data-action="close-modal">إلغاء</button></div></form>`;
  $("#modal").showModal();
}
function dialog(kind) {
  if (kind === "customer")
    modal(
      "عميل جديد",
      field("اسم العميل", "name", "text", "", "required") +
        field("الهاتف", "phone") +
        field("العنوان", "address"),
      "customer",
    );
  if (kind === "product")
    modal(
      "تعريف صنف ورصيد افتتاحي",
      field("اسم الصنف", "name", "text", "", "required") +
        field("سعر البيع", "price", "number", 0, 'min="0" step="0.01"') +
        field("تكلفة الوحدة", "cost", "number", 0, 'min="0" step="0.01"') +
        field("رصيد افتتاحي (كمية)", "qty", "number", 0, 'min="0" step="1"') +
        '<div><label>النوع</label><select name="service"><option value="false">مخزني</option><option value="true">خدمة</option></select></div>',
      "product",
    );
  if (kind === "receipt")
    modal(
      "سند قبض",
      '<div><label>العميل</label><select name="customer_id" required>' +
        options(cache.customers, "") +
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
  if (kind === "user")
    modal(
      "مستخدم جديد",
      field("اسم المستخدم", "name", "text", "", "required") +
        field(
          "كلمة مرور أولية",
          "password",
          "password",
          "",
          'minlength="8" required',
        ) +
        '<div><label>الدور</label><select name="role"><option value="sales">مبيعات</option><option value="accountant">محاسب</option></select></div>',
      "user",
    );
  if (kind === "statement")
    modal(
      "كشف حساب العميل",
      field("من تاريخ", "from", "date", filters.from) +
        field("إلى تاريخ", "to", "date", filters.to),
      kind,
    );
}
async function run(fn) {
  try {
    await fn();
  } catch (e) {
    notice(e.message);
  }
}
document.addEventListener("click", (e) =>
  run(async () => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.open) {
      location.hash = "invoice/" + b.dataset.open;
      return;
    }
    if (b.dataset.remove !== undefined) {
      draft.lines.splice(Number(b.dataset.remove), 1);
      dirty = true;
      drawEditor();
      return;
    }
    if (b.dataset.statement) {
      dialog("statement");
      $("#modal-form").dataset.customer = b.dataset.statement;
      return;
    }
    const a = b.dataset.action;
    if (a === "new-invoice") location.hash = "new";
    if (a === "back") location.hash = "sales";
    if (a === "add-line") {
      draft.lines.push({ product_id: "", qty: 1, price: 0 });
      dirty = true;
      drawEditor();
    }
    if (a === "close-modal") $("#modal").close();
    if (["customer", "product", "receipt", "user"].includes(a)) dialog(a);
    if (a === "logout") {
      await api("/api/logout", "POST", {});
      session = null;
      await loginUI();
    }
    if (a === "post") {
      if (dirty) throw Error("احفظ التعديلات في المسودة أولاً قبل الترحيل");
      if (
        confirm("ترحيل النسخة المحفوظة؟ إذا عدّلت حقولاً، احفظ المسودة أولاً.")
      ) {
        await api("/api/invoices/" + editing + "/post", "POST", {
          version: draft.version,
        });
        flash = "تم الترحيل وربط المستند بالحسابات والمخزون.";
        await navigate();
      }
    }
    if (["cancel", "amend"].includes(a)) {
      const reason = prompt(
        a === "cancel" ? "سبب الإلغاء المحاسبي:" : "سبب إصدار التعديل:",
      );
      if (reason?.trim()) {
        const s = await api("/api/invoices/" + editing + "/" + a, "POST", {
          reason,
        });
        flash =
          a === "amend"
            ? "أُنشئت مسودة تعديل. لن تُعكس الفاتورة الأصلية حتى ترحيل البديل."
            : "تم عكس الفاتورة مع حفظ أصلها وسجلها.";
        if (a === "amend") location.hash = "invoice/" + s.id;
        else await navigate();
      }
    }
  }),
);
document.addEventListener("input", (e) => {
  if (!draft || !e.target.closest("#invoice-form")) return;
  dirty = true;
  const el = e.target;
  if (el.dataset.line !== undefined) {
    const l = draft.lines[Number(el.dataset.line)];
    l[el.dataset.key] = el.value;
    if (el.dataset.key === "product_id") {
      l.price =
        (cache.products.find((p) => String(p.id) === el.value)?.price || 0) /
        100;
      drawEditor();
    } else {
      $("#line-" + el.dataset.line).textContent = money(
        Math.round(Number(l.qty) * Number(l.price) * 100),
      );
      totals();
    }
  } else if (el.name) {
    draft[el.name] = el.value;
    totals();
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "search") {
    const q = e.target.value.toLowerCase();
    document
      .querySelectorAll("tbody tr")
      .forEach((tr) => (tr.hidden = !tr.textContent.toLowerCase().includes(q)));
  }
});
document.addEventListener("submit", (e) => {
  e.preventDefault();
  run(async () => {
    const form = e.target,
      data = Object.fromEntries(new FormData(form));
    if (form.id === "login") {
      try {
        session = await api("/api/" + form.dataset.mode, "POST", data);
        await navigate();
      } catch (err) {
        $("#auth-error").textContent = err.message;
      }
    }
    if (form.id === "invoice-form") {
      const s = await api(
        "/api/invoices" + (editing ? "/" + editing : ""),
        editing ? "PUT" : "POST",
        draft,
      );
      flash = "حُفظت المسودة دون أثر محاسبي. راجعها ثم رحّلها.";
      if (editing) await navigate();
      else location.hash = "invoice/" + s.id;
    }
    if (form.id === "filters") {
      filters = data;
      await reports();
    }
    if (form.id === "modal-form") {
      try {
        const kind = form.dataset.kind;
        if (form.dataset.request) data.request_id = form.dataset.request;
        if (kind === "statement") {
          window.open(
            "/print/statement?" +
              new URLSearchParams({ ...data, customer: form.dataset.customer }),
            "_blank",
          );
          $("#modal").close();
          return;
        }
        if (kind === "product") data.service = data.service === "true";
        await api(
          "/api/" +
            {
              customer: "customers",
              product: "products",
              receipt: "receipts",
              user: "users",
            }[kind],
          "POST",
          data,
        );
        $("#modal").close();
        flash = "تم الحفظ في قاعدة البيانات المشتركة.";
        await navigate();
      } catch (err) {
        $("#modal-error").textContent = err.message;
      }
    }
  });
});
document.addEventListener(
  "click",
  (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (a && dirty) {
      if (!confirm("ترك تعديلات المسودة غير المحفوظة؟")) {
        e.preventDefault();
        e.stopImmediatePropagation();
      } else dirty = false;
    }
  },
  true,
);
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
window.addEventListener("hashchange", () => run(navigate));
run(loginUI);
