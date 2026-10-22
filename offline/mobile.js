// This extension stays inside the standalone bundle's private lexical scope.
let offlineDirty = false;
const localExpense = expense;
expense = function (input, draft) {
  if (Number(draft.amount) > cash(input))
    throw Error("رصيد الصندوق غير كافٍ؛ سجل تمويلاً أو تحصيلاً صحيحاً أولاً");
  return localExpense(input, draft);
};
const localCommit = commit;
commit = function (next) {
  localCommit(next);
  offlineDirty = true;
  updateStorageStatus();
};
function updateStorageStatus() {
  let status = document.querySelector("[data-offline-status]");
  if (!status) {
    status = document.createElement("div");
    status.dataset.offlineStatus = "1";
    document.querySelector("header").after(status);
  }
  status.className = "offline-status" + (temporaryStorage ? " warn" : "");
  status.innerHTML = temporaryStorage
    ? "<b>العمليات تعمل، لكن المتصفح يمنع الحفظ التلقائي لهذا الملف.</b>بعد إنهاء العمل اضغط «حفظ نسخة الهاتف»، واحتفظ بالملف الجديد وافتحه في المرة القادمة. تصدير JSON متاح أيضاً."
    : "<b>نسخة تشغيل محلية — دون استضافة أو مزامنة.</b>يتم الحفظ في هذا المتصفح. احتفظ أيضاً بنسخة هاتف أو JSON، خصوصاً قبل حذف بيانات المتصفح أو نقل الملف.";
  if (offlineDirty)
    status.insertAdjacentHTML(
      "beforeend",
      "<br><strong>لديك تغييرات منذ آخر تصدير. احفظ نسخة خارج المتصفح.</strong>",
    );
}
function savePhoneFile() {
  const copy = document.documentElement.cloneNode(true);
  copy.querySelector("#offline-seed").textContent = JSON.stringify({
    format: "WIFI-HOME-OFFLINE",
    storageKey: "wifiHomeERP.offline." + recordID(),
    data: db,
  }).replace(/</g, "\\u003c");
  copy
    .querySelectorAll("[data-offline-status],#offline-document")
    .forEach((el) => el.remove());
  copy.querySelector("#view").innerHTML = "";
  copy.querySelector("#notice").textContent = "";
  copy.querySelector("#dialog-body").innerHTML = "";
  copy.querySelector("#modal").removeAttribute("open");
  download(
    "WIFI-HOME-PHONE-" + today() + "-" + Date.now() + ".html",
    "<!doctype html>\n" + copy.outerHTML,
    "text/html",
  );
  offlineDirty = false;
  updateStorageStatus();
  message(
    "تم طلب تنزيل نسخة الهاتف ببياناتك. تأكد من وجود الملف الجديد في التنزيلات؛ افتحه في المرة القادمة.",
  );
}
backup = function () {
  download(
    "WIFI-HOME-OFFLINE-" + today() + ".json",
    JSON.stringify(
      {
        format: "WIFI-HOME-OFFLINE",
        version: 2,
        createdAt: new Date().toISOString(),
        data: db,
      },
      null,
      2,
    ),
  );
  offlineDirty = false;
  updateStorageStatus();
  message("تم طلب تنزيل نسخة JSON. تحقق من حفظها في التنزيلات.");
};
importData = function (packageData) {
  const result = cleanOfflineImport(packageData),
    next = result.db;
  const balanceSum = next.customers.reduce(
    (n, c) => round(n + balance(next, c.id)),
    0,
  );
  const summary = `العملاء الأساسيون: ${next.customers.length}\nالأصناف: ${next.products.length}\nرصيد الصندوق: ${money(cash(next))} ريال\nصافي أرصدة العملاء: ${money(balanceSum)} ريال\nاستبعاد التجربة: ${result.removedCustomers} عميل، ${result.removedProducts} صنف، ${result.removedSales} فاتورة.\n\nاعتماد هذه البيانات واستبدال البيانات الحالية؟`;
  if (!confirm(summary)) return;
  if (db.customers.length || db.sales.length || db.products.length) backup();
  commit(next);
  render();
  message(
    "تم استيراد البيانات الأساسية واستبعاد التجربة. احفظ الآن نسخة الهاتف أو JSON.",
  );
};
const localSettings = settings;
settings = function () {
  return (
    `<div class="card stack offline-help"><h2>نسخة الهاتف التي تنفّذ العمليات</h2><p>البيع النقدي والآجل والسداد الجزئي، تعديل الفواتير بسبب موثق، القبض والمصروفات، استلام المخزون، العملاء والأصناف، والتقارير وكشف الحساب. هذه النسخة محلية مستقلة؛ وظائف البنوك والمستودعات المتعددة ودورة أوامر الشراء في نسخة الخادم ليست مفعلة هنا.</p><button data-offline="save">حفظ نسخة الهاتف ببياناتي</button><p>ملف HTML الجديد يحتوي بياناتك. احتفظ به بشكل خاص، ولا ترفعه إلى GitHub أو تشاركه كملف برنامج عام. لا يوجد تسجيل دخول أو صلاحيات مستخدمين مفروضة على الملف المحلي.</p><p>لا تمسح بيانات المتصفح قبل الاحتفاظ بنسخة خارجية. إذا منع المتصفح التخزين، افتح دائماً آخر ملف هاتف حفظته، أو استورد آخر JSON.</p></div>` +
    localSettings()
  );
};
const localRender = render;
render = function () {
  localRender();
  updateStorageStatus();
  const saveButton = document.querySelector('[data-offline="save-header"]');
  if (!saveButton) {
    const b = document.createElement("button");
    b.dataset.offline = "save-header";
    b.className = "secondary";
    b.textContent = "حفظ نسخة الهاتف";
    document.querySelector(".head-actions").prepend(b);
  }
  document.querySelector("#backup").textContent = "نسخة JSON";
  if (location.hash === "#customers")
    document
      .querySelectorAll("[data-ledger]")
      .forEach((b) =>
        b.insertAdjacentHTML(
          "afterend",
          `<button class="link" data-offline="customer-edit" data-id="${esc(b.dataset.ledger)}">تعديل</button>`,
        ),
      );
  if (location.hash === "#inventory")
    document.querySelectorAll("tbody tr").forEach((tr, i) => {
      const p = db.products[i];
      if (p)
        tr.lastElementChild.insertAdjacentHTML(
          "beforeend",
          `<button class="link" data-offline="product-edit" data-id="${esc(p.id)}">تعديل السعر</button>`,
        );
    });
  if (location.hash === "#cash")
    document
      .querySelector("#view")
      .insertAdjacentHTML(
        "afterbegin",
        '<div class="card actions"><button data-offline="capital">تمويل الصندوق</button></div>',
      );
};
function masterForm(kind, id) {
  const item = kind === "customer-edit" ? customer(id) : product(id);
  const content =
    field("الاسم", "name", "text", item.name, "required") +
    (kind === "customer-edit"
      ? field("الهاتف", "phone", "text", item.phone) +
        field("المنطقة", "region", "text", item.region) +
        field(
          "حد الائتمان",
          "limit",
          "number",
          item.limit || 0,
          'min="0" step="0.01"',
        )
      : field(
          "سعر البيع",
          "price",
          "number",
          item.price,
          'min="0" step="0.01"',
        ));
  modal(
    kind === "customer-edit" ? "تعديل بيانات العميل" : "تعديل بيانات الصنف",
    content,
    "offline-" + kind,
    id,
  );
}
function independentDocument() {
  const route = decodeURIComponent(location.hash.slice(1)),
    isInvoice = route.startsWith("invoice/");
  let title = "تقرير الحسابات",
    body = "";
  if (isInvoice) {
    title = "فاتورة بيع";
    const article = document.querySelector("article.invoice");
    if (!article) return;
    body = article.innerHTML;
  } else if (route === "reports") {
    const current = document
      .querySelector("#view .subnav")
      ?.closest(".card")
      ?.querySelector("table");
    if (!current) throw Error("اختر تقريراً يحتوي بيانات أولاً");
    const clone = current.cloneNode(true);
    if (reportTab === "sales")
      for (const tr of clone.rows) tr.lastElementChild?.remove();
    clone
      .querySelectorAll("button,a")
      .forEach((b) => b.replaceWith(document.createTextNode(b.textContent)));
    title =
      {
        sales: "تقرير المبيعات",
        customers: "المبيعات حسب العميل",
        products: "المبيعات حسب الصنف",
        daily: "المبيعات اليومية",
        ledger: "كشف حساب العميل",
      }[reportTab] || title;
    const r = report(db, filters);
    body = `<div class="invoice-meta"><div>الفترة: ${esc(filters.from || "البداية")} — ${esc(filters.to || "اليوم")}</div><div>العميل: ${esc(filters.customerId ? name(filters.customerId) : "الكل")}</div></div>`;
    if (reportTab === "ledger") {
      const l = ledger(db, filters.customerId, filters);
      body += `<p>رصيد أول الفترة: ${money(l.opening)} · رصيد آخر الفترة: ${money(l.closing)} ر.ي</p>`;
    } else
      body += `<p>صافي المبيعات: ${money(r.net)} · تكلفة المبيعات: ${money(r.cost)} · مجمل الربح: ${money(r.grossProfit)} ر.ي</p>`;
    body += clone.outerHTML;
  } else {
    window.print();
    return;
  }
  const doc = `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title><style>@page{size:A4;margin:15mm}body{font-family:Tahoma,Arial;color:#172a40;margin:20px;line-height:1.8}header{display:flex;justify-content:space-between;border-bottom:2px solid #176b63;margin-bottom:20px}table{border-collapse:collapse;width:100%;table-layout:fixed}th,td{padding:9px 6px;border-bottom:1px solid #dce3e8;overflow-wrap:anywhere;text-align:right;font-size:12px}th{background:#eef5f4}thead{display:table-header-group}tr{break-inside:avoid}.summary{width:55%;margin:20px auto 20px 0}.summary>div{display:flex;justify-content:space-between;border-bottom:1px solid #ddd}.invoice-top,.invoice-meta{display:flex;justify-content:space-between;gap:20px}.invoice-meta>div{flex:1}.invoice-meta b,.invoice-meta small{display:block}.total{font-size:18px;font-weight:bold}.note{margin-top:20px;font-size:12px;background:#f3f7f9;padding:12px}small{font-size:11px}a{color:inherit;text-decoration:none}footer{border-top:1px solid #ddd;margin-top:25px;font-size:11px}</style></head><body><header><b>${esc(db.settings.company)}</b><span>${esc(title)} · ريال يمني · دون ضريبة</span></header>${body}<footer>نسخة محلية · أُخرج المستند في ${esc(today())}</footer></body></html>`;
  let dialog = document.querySelector("#offline-document");
  if (dialog) dialog.remove();
  dialog = document.createElement("dialog");
  dialog.id = "offline-document";
  dialog.className = "offline-doc";
  dialog.innerHTML =
    '<div class="actions"><button data-offline="print-doc">طباعة المستند</button><button data-offline="save-doc">حفظ المستند HTML</button><button class="secondary" data-offline="close-doc">رجوع</button></div><iframe title="المستند المستقل" sandbox="allow-modals allow-same-origin"></iframe>';
  document.body.append(dialog);
  dialog.querySelector("iframe").srcdoc = doc;
  dialog.showModal();
  dialog.savedDocument = doc;
}
document.addEventListener(
  "click",
  (e) => {
    const b = e.target.closest('[data-offline],[data-action="print"]');
    if (!b) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    attempt(() => {
      const action = b.dataset.offline;
      if (action === "save" || action === "save-header") savePhoneFile();
      if (action === "customer-edit" || action === "product-edit")
        masterForm(action, b.dataset.id);
      if (action === "capital")
        modal(
          "تمويل الصندوق",
          field(
            "المبلغ",
            "amount",
            "number",
            "",
            'min="0.01" step="0.01" required',
          ) +
            field("التاريخ", "date", "date", today(), "required") +
            field("البيان", "note", "text", "", "required"),
          "offline-capital",
        );
      if (b.dataset.action === "print") independentDocument();
      if (action === "close-doc")
        document.querySelector("#offline-document").close();
      if (action === "save-doc")
        download(
          "WIFI-HOME-document-" + Date.now() + ".html",
          document.querySelector("#offline-document").savedDocument,
          "text/html",
        );
      if (action === "print-doc") {
        const frame = document.querySelector("#offline-document iframe");
        if (typeof frame.contentWindow.print !== "function")
          throw Error(
            "المتصفح لا يدعم الطباعة؛ احفظ المستند وافتحه في متصفح يدعمها",
          );
        frame.contentWindow.focus();
        frame.contentWindow.print();
      }
    });
  },
  true,
);
document.addEventListener(
  "submit",
  (e) => {
    const form = e.target;
    if (form.id !== "modal-form" || !form.dataset.kind?.startsWith("offline-"))
      return;
    e.preventDefault();
    e.stopImmediatePropagation();
    try {
      const f = Object.fromEntries(new FormData(form)),
        next = normalize(db),
        kind = form.dataset.kind,
        id = form.dataset.extra;
      if (kind === "offline-capital") {
        dateCheck(next, f.date);
        const amount = Number(f.amount);
        if (!Number.isFinite(amount) || amount <= 0 || !f.note.trim())
          throw Error("أدخل مبلغاً وبياناً صالحين");
        const ref = "CAP-" + recordID();
        entry(next, ref, f.date, f.note, [
          { account: "الصندوق", debit: round(amount), credit: 0 },
          {
            account: "رأس المال والأرصدة الافتتاحية",
            debit: 0,
            credit: round(amount),
          },
        ]);
        audit(next, "تمويل الصندوق", ref, null, f, "");
      } else {
        if (!f.name.trim()) throw Error("أدخل الاسم");
        const item = (
            kind === "offline-customer-edit" ? next.customers : next.products
          ).find((x) => x.id === id),
          before = structuredClone(item);
        if (kind === "offline-customer-edit") {
          const limit = Number(f.limit);
          if (!Number.isFinite(limit) || limit < 0)
            throw Error("حد الائتمان غير صالح");
          Object.assign(item, {
            name: f.name.trim(),
            phone: f.phone,
            region: f.region,
            limit,
          });
        } else {
          const price = Number(f.price);
          if (!Number.isFinite(price) || price < 0)
            throw Error("السعر غير صالح");
          Object.assign(item, { name: f.name.trim(), price: round(price) });
        }
        audit(next, "تعديل بيانات أساسية", id, before, item, "");
      }
      commit(next);
      document.querySelector("#modal").close();
      render();
      message("تم الحفظ محلياً.");
    } catch (error) {
      document.querySelector("#modal-error").textContent = error.message;
    }
  },
  true,
);
render();
