"use strict";
const previousNavigate = navigate;
let settlementState = null,
  bankState = null,
  agingDate = today(),
  transferDraft = null;
navigate = async function () {
  if (!session) return;
  const route = location.hash.slice(1) || "sales";
  if (
    !["settlements", "banks", "warehouses", "new-transfer"].includes(route) &&
    !route.startsWith("bank-statement/") &&
    !route.startsWith("transfer/")
  )
    return previousNavigate();
  dirty = false;
  draft = null;
  await load();
  if (route === "settlements") return settlementsPage();
  if (session.role === "sales") throw Error("هذا القسم للمدير أو المحاسب");
  if (route === "banks") return banksPage();
  if (route === "warehouses") return warehousesPage();
  if (route.startsWith("bank-statement/"))
    return statementPage(
      await api("/api/banking/statements/" + Number(route.split("/")[1])),
    );
  if (route === "new-transfer") {
    transferDraft = {
      date: today(),
      source_id: 1,
      target_id: "",
      note: "",
      status: "draft",
      lines: [{ product_id: "", qty: 1 }],
    };
    return transferEditor();
  }
  if (route.startsWith("transfer/")) {
    transferDraft = await api("/api/transfers/" + Number(route.split("/")[1]));
    return transferEditor();
  }
};
const oldSalesEditor = drawEditor;
drawEditor = function () {
  oldSalesEditor();
  const form = $("#invoice-form .doc-meta");
  if (form) {
    form.insertAdjacentHTML(
      "beforeend",
      `<div><label>مستودع البيع</label><select name="warehouse_id" required>${options(cache.warehouses, draft.warehouse_id || 1, "اختر المستودع")}</select></div>${field("تاريخ الاستحقاق", "due_date", "date", draft.due_date || draft.date, "required")}`,
    );
  }
  if (draft.status === "posted" && draft.settlement) {
    const s = draft.settlement;
    $("#invoice-form").insertAdjacentHTML(
      "afterend",
      `<div class="help"><b>المتبقي الفعلي للفاتورة: ${money(s.outstanding)} ر.ي</b><br>قبض مخصص: ${money(s.allocated)} · إشعارات دائنة: ${money(s.credits)} · مردود نقدي: ${money(s.refunds)}<br><a href="#settlements">تفاصيل التحصيل والتخصيص</a></div>`,
    );
  }
};
const oldPurchaseEditor = purchaseEditor;
purchaseEditor = function () {
  oldPurchaseEditor();
  $("#purchase-form .doc-meta")?.insertAdjacentHTML(
    "beforeend",
    `<div><label>مستودع الاستلام</label><select name="warehouse_id" required>${options(cache.warehouses, purchasing.warehouse_id || 1, "اختر المستودع")}</select></div>`,
  );
};
function bankChoice() {
  return `<div><label>حساب الحركة</label><select name="bank_id"><option value="">الصندوق النقدي</option>${(cache.banks || []).map((b) => `<option value="${b.id}">${esc(b.name)} · ${esc(b.code)}</option>`).join("")}</select></div>`;
}
const oldDialog = dialog;
dialog = function (kind) {
  oldDialog(kind);
  if (kind === "receipt") {
    $("#modal-form .fields")?.insertAdjacentHTML("beforeend", bankChoice());
    $("#modal-form").dataset.request = crypto.randomUUID();
  }
  if (kind === "product")
    $("#modal-form .fields")?.insertAdjacentHTML(
      "beforeend",
      `<div><label>مستودع الرصيد الافتتاحي</label><select name="warehouse_id">${options(cache.warehouses, 1, "اختر المستودع")}</select></div>`,
    );
};
const oldOpDialog = opDialog;
opDialog = function (kind, extra = "") {
  oldOpDialog(kind, extra);
  if (["payment", "expense"].includes(kind))
    $("#operation-form .fields")?.insertAdjacentHTML("beforeend", bankChoice());
};
const oldReturnEditor = returnEditor;
returnEditor = function (s) {
  oldReturnEditor(s);
  $("#return-form .fields")?.insertAdjacentHTML(
    "beforeend",
    `<div><label>مستودع استلام المرتجع</label><select name="warehouse_id">${options(cache.warehouses, s.warehouse_id || 1, "اختر المستودع")}</select></div>`,
  );
};
function modalV3(title, body, kind, extra = "") {
  $("#modal").innerHTML =
    `<h2>${title}</h2><form id="v3-form" data-kind="${kind}" data-extra="${esc(extra)}" data-request="${crypto.randomUUID()}"><div class="fields">${body}</div><p id="v3-error" class="auth-error"></p><div class="actions" style="margin-top:20px"><button>حفظ</button><button type="button" class="secondary" data-action="close-modal">إلغاء</button></div></form>`;
  $("#modal").showModal();
}
async function settlementsPage() {
  settlementState = await api("/api/settlements");
  const a = await api("/api/aging?asof=" + agingDate);
  layout(
    "settlements",
    "تخصيص التحصيل وأعمار الديون",
    '<button data-v3="allocation">تخصيص سند قبض</button>',
    `<form id="aging-form" class="panel padded filters">${field("الأرصدة حتى تاريخ", "asof", "date", agingDate, "required")}<button>عرض الأعمار</button><a class="btn secondary" target="_blank" href="/print/aging?asof=${agingDate}">تقرير أعمار الديون / PDF</a></form><div class="grid">${[
      ["فواتير مفتوحة", a.gross_outstanding],
      ["قبض غير مخصص", a.unapplied_receipts],
      ["أرصدة دائنة من المرتجعات", a.customer_credits],
      ["صافي حسابات العملاء", a.net_receivable],
    ]
      .map(
        ([title, value]) =>
          `<div class="panel metric"><label>${title}</label><strong>${money(value)}</strong><small>حتى ${esc(a.asof)}</small></div>`,
      )
      .join(
        "",
      )}</div><div class="panel"><div class="panel-head"><h2>الفواتير المفتوحة</h2></div>${table(
      ["الفاتورة", "العميل", "الاستحقاق", "متأخر / يوم", "المخصص", "المتبقي"],
      a.rows.map(
        (s) =>
          `<tr><td><button class="link" data-open="${s.id}">${esc(s.number)}</button></td><td>${esc(s.customer)}</td><td>${esc(s.due_date)}</td><td>${s.days_overdue}</td><td class="num">${money(s.allocated)}</td><td class="num">${money(s.outstanding)}</td></tr>`,
      ),
    )}</div><div class="panel"><div class="panel-head"><h2>سندات القبض المتاحة للتخصيص</h2></div>${table(
      ["السند", "التاريخ", "العميل", "قيمة القبض", "غير مخصص"],
      settlementState.receipts.map(
        (r) =>
          `<tr><td>${esc(r.number)}</td><td>${esc(r.date)}</td><td>${esc(r.customer)}</td><td class="num">${money(r.amount)}</td><td class="num">${money(r.available)}</td></tr>`,
      ),
    )}</div><div class="panel"><div class="panel-head"><h2>سجل التخصيص</h2><span class="muted">لا يكرر قيد القبض</span></div>${table(
      ["التاريخ", "القبض", "الفاتورة", "التخصيص الأصلي", "المتبقي مخصصاً", ""],
      settlementState.allocations.map(
        (x) =>
          `<tr><td>${esc(x.date)}</td><td>${esc(x.receipt)}</td><td>${esc(x.invoice)}</td><td class="num">${money(x.amount)}</td><td class="num">${money(x.remaining)}</td><td>${x.remaining && session.role !== "sales" ? `<button class="link" data-release="${x.id}">فك تخصيص</button>` : ""}</td></tr>`,
      ),
    )}</div>`,
  );
}
function allocationOptions(rid) {
  const r = settlementState.receipts.find((r) => String(r.id) === String(rid));
  return options(
    settlementState.invoices
      .filter(
        (i) => i.outstanding > 0 && (!r || i.customer_id === r.customer_id),
      )
      .map((i) => ({
        id: i.id,
        name:
          i.number + " · " + i.customer + " · متبقي " + money(i.outstanding),
      })),
    "",
    "اختر الفاتورة",
  );
}
function allocationModal() {
  modalV3(
    "تخصيص قبض لفاتورة",
    `<div><label>سند القبض</label><select name="receipt_id" id="allocation-receipt" required>${options(
      settlementState.receipts
        .filter((r) => r.available > 0)
        .map((r) => ({
          id: r.id,
          name: r.number + " · " + r.customer + " · متاح " + money(r.available),
        })),
      "",
      "اختر سند القبض",
    )}</select></div><div><label>الفاتورة من نفس العميل</label><select name="invoice_id" id="allocation-invoice" required>${allocationOptions("")}</select></div>${field("المبلغ المخصص", "amount", "number", "", 'required min="0.01" step="0.01"')}${field("تاريخ التخصيص", "date", "date", today(), "required")}`,
    "allocation",
  );
}
async function warehousesPage() {
  const rows = await api("/api/warehouse-stock");
  layout(
    "warehouses",
    "المستودعات والتحويلات",
    '<button data-v3="warehouse">مستودع جديد</button><button class="secondary" data-v3="transfer-new">تحويل مخزني</button>',
    `<div class="panel padded"><h2>مستودعات المنشأة</h2><p>${cache.warehouses.map((w) => `<span class="tag">${esc(w.name)}</span>`).join(" ")}</p></div><div class="panel"><div class="panel-head"><h2>الأرصدة الفعلية حسب المستودع</h2></div>${table(
      ["المستودع", "الصنف", "الكمية", "القيمة الدقيقة"],
      rows.map(
        (s) =>
          `<tr><td>${esc(s.warehouse)}</td><td>${esc(s.product)}</td><td>${s.qty}</td><td class="num">${money(s.value)}</td></tr>`,
      ),
    )}</div><div class="panel"><div class="panel-head"><h2>سندات التحويل الداخلي</h2></div>${table(
      ["السند", "التاريخ", "من", "إلى", "الحالة"],
      cache.transfers.map(
        (t) =>
          `<tr><td><button class="link" data-transfer="${t.id}">${esc(t.number)}</button></td><td>${esc(t.date)}</td><td>${esc(t.source)}</td><td>${esc(t.target)}</td><td>${pill(t.status)}</td></tr>`,
      ),
    )}</div><div class="help">المخزون والتكلفة محفوظان لكل مستودع. التحويل يحافظ على إجمالي قيمة المخزون، ولا يولّد مبيعات أو مصروفاً.</div>`,
  );
}
function transferEditor() {
  const t = transferDraft,
    locked = t.status !== "draft";
  layout(
    "warehouses",
    t.number || "تحويل مخزني جديد",
    '<a class="btn secondary" href="#warehouses">المستودعات</a>',
    `<div class="panel"><div class="doc-toolbar"><div class="actions">${locked ? `<a class="btn secondary" target="_blank" href="/print/transfers/${t.id}">سند التحويل / PDF</a>${t.status === "posted" ? '<button class="danger" data-v3="transfer-cancel">عكس التحويل</button>' : ""}` : `<button form="transfer-form">حفظ المسودة</button>${t.id ? '<button class="secondary" data-v3="transfer-post">ترحيل التحويل</button>' : ""}`}</div>${pill(t.status)}</div><div class="document"><form id="transfer-form" data-request="${crypto.randomUUID()}"><fieldset ${locked ? "disabled" : ""} style="border:0;padding:0"><div class="fields"><div><label>من مستودع</label><select name="source_id" required>${options(cache.warehouses, t.source_id, "المصدر")}</select></div><div><label>إلى مستودع</label><select name="target_id" required>${options(cache.warehouses, t.target_id, "الوجهة")}</select></div>${field("التاريخ", "date", "date", t.date, "required")}${field("البيان", "note", "text", t.note)}</div><div class="table"><table class="lines"><thead><tr><th>الصنف</th><th>الكمية</th><th>القيمة المنقولة</th><th></th></tr></thead><tbody>${t.lines
      .map(
        (l, i) =>
          `<tr><td><select data-tl="${i}" data-tkey="product_id" required>${options(
            cache.products.filter((p) => !p.service),
            l.product_id,
            "الصنف",
          )}</select></td><td><input type="number" min="1" step="1" data-tl="${i}" data-tkey="qty" value="${esc(l.qty)}" required aria-label="كمية التحويل ${i + 1}"></td><td class="num">${locked ? money(l.cost) : "تُحسب عند الترحيل"}</td><td>${locked ? "" : `<button type="button" class="secondary" data-transfer-remove="${i}">×</button>`}</td></tr>`,
      )
      .join(
        "",
      )}</tbody></table></div>${locked ? "" : '<button type="button" class="link" data-v3="transfer-line">+ بند</button>'}</fieldset></form></div></div>`,
  );
}
async function banksPage() {
  bankState = await api("/api/banking");
  layout(
    "banks",
    "الخزينة والبنوك",
    `${session.role === "admin" ? '<button data-v3="bank">حساب بنكي</button>' : ""}<button class="secondary" data-v3="bank-transfer">تحويل نقدي / بنكي</button><button class="secondary" data-v3="statement-import">استيراد كشف بنك</button>`,
    `<div class="grid">${bankState.banks.map((b) => `<div class="panel metric"><label>${esc(b.name)} · ${esc(b.code)}</label><strong>${money(b.balance)}</strong><small>رصيد دفتر البنك · ريال يمني</small></div>`).join("")}</div><div class="panel"><div class="panel-head"><h2>كشوف البنك والتسويات</h2></div>${table(
      ["المرجع", "الحساب", "من", "إلى", "الرصيد الختامي", "الحالة"],
      bankState.statements.map(
        (s) =>
          `<tr><td><button class="link" data-statement-id="${s.id}">${esc(s.reference)}</button></td><td>${esc(s.bank)}</td><td>${esc(s.from_date)}</td><td>${esc(s.to_date)}</td><td class="num">${money(s.closing)}</td><td><span class="pill ${s.status === "final" ? "posted" : ""}">${s.status === "final" ? "معتمدة" : "مسودة مطابقة"}</span></td></tr>`,
      ),
    )}</div><div class="panel"><div class="panel-head"><h2>حركة دفاتر البنك</h2></div>${table(
      ["التاريخ", "الحساب", "المستند", "مرجع البنك", "المبلغ الموقّع"],
      bankState.moves.map(
        (m) =>
          `<tr><td>${esc(m.date)}</td><td>${esc(m.bank)}</td><td>${esc(m.document)}</td><td>${esc(m.reference)}</td><td class="num">${money(m.amount)}</td></tr>`,
      ),
    )}</div><div class="help">اختَر حساب البنك في سند القبض أو صرف المورد أو مصروف التشغيل لتُسجّل الحركة في دفاتر البنك. المطابقة مع كشف البنك لا تُنشئ قيداً ثانياً.</div>`,
  );
}
function statementPage(s) {
  const locked = s.status === "final";
  layout(
    "banks",
    "مطابقة كشف " + esc(s.reference),
    `<a class="btn secondary" href="#banks">البنوك</a><a class="btn secondary" target="_blank" href="/print/bank-statements/${s.id}">محضر التسوية / PDF</a>${locked ? "" : `<button data-finalize="${s.id}">اعتماد التسوية</button>`}`,
    `<div class="panel padded"><h2>${esc(s.bank)}</h2><p>${esc(s.from_date)} — ${esc(s.to_date)} · ${locked ? "تسوية معتمدة" : "مسودة مطابقة"}</p><div class="grid"><div class="metric"><label>رصيد أول الكشف</label><strong>${money(s.opening)}</strong></div><div class="metric"><label>رصيد نهاية الكشف</label><strong>${money(s.closing)}</strong></div>${locked ? `<div class="metric"><label>حركات دفترية معلقة عند الاعتماد</label><strong>${money(s.unmatched_book)}</strong></div><div class="metric"><label>رصيد الدفاتر المعتمد</label><strong>${money(s.book_closing)}</strong></div>` : ""}</div></div><div class="panel">${table(
      ["تاريخ البنك", "المرجع", "المبلغ", "الحركة الدفترية المطابقة"],
      s.lines.map(
        (l) =>
          `<tr><td>${esc(l.date)}</td><td>${esc(l.reference)}</td><td class="num">${money(l.amount)}</td><td>${
            locked
              ? esc(l.document)
              : `<select data-match-line="${l.id}" data-bank-statement="${s.id}" aria-label="مطابقة ${l.id}"><option value="">غير مطابق</option>${l.move_id ? `<option value="${l.move_id}" selected>${esc(l.document)}</option>` : ""}${s.candidates
                  .filter((m) => m.amount === l.amount)
                  .map(
                    (m) =>
                      `<option value="${m.id}">${esc(m.document)} · ${esc(m.date)} · ${esc(m.reference)}</option>`,
                  )
                  .join("")}</select>`
          }</td></tr>`,
      ),
    )}</div><div class="help">طابق كل حركة في كشف البنك مع مستند دفتري من الحساب نفسه وبالقيمة نفسها. سجّل رسوم البنك أو التحصيلات الناقصة أولاً. الحركات الدفترية التي لم تظهر في البنك تبقى معلقة وتدخل في الرصيد المعدل.</div>`,
  );
}
function bankOptions(value = "", cash = false) {
  return (
    (cash
      ? '<option value="">الصندوق النقدي</option>'
      : '<option value="">اختر الحساب</option>') +
    (cache.banks || [])
      .map(
        (b) =>
          `<option value="${b.id}" ${String(value) === String(b.id) ? "selected" : ""}>${esc(b.name)}</option>`,
      )
      .join("")
  );
}
function statementImport() {
  modalV3(
    "استيراد كشف بنك للمطابقة",
    `<div><label>الحساب البنكي</label><select name="bank_id" required>${bankOptions()}</select></div>${field("مرجع كشف البنك", "reference", "text", "", "required")}${field("من تاريخ", "from_date", "date", today().slice(0, 7) + "-01", "required")}${field("إلى تاريخ", "to_date", "date", today(), "required")}${field("رصيد أول الكشف", "opening", "number", 0, 'step="0.01" required')}${field("رصيد نهاية الكشف", "closing", "number", 0, 'step="0.01" required')}<div style="grid-column:1/-1"><label>ملف CSV (date, amount, reference, note)</label><input id="statement-csv-file" type="file" accept=".csv,text/csv"><textarea name="csv" id="statement-csv" placeholder="date,amount,reference,note" rows="6"></textarea><small>الموجب إيداع، والسالب سحب. استخدم تاريخ YYYY-MM-DD وأرقاماً دون فواصل آلاف.</small></div>`,
    "statement",
  );
}
function parseCSV(text) {
  const rows = [];
  let row = [],
    cell = "",
    quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else quoted = !quoted;
    } else if (c === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((c === "\n" || c === "\r") && !quoted) {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      if (row.some((x) => x.trim())) rows.push(row);
      row = [];
      cell = "";
    } else cell += c;
  }
  if (quoted) throw Error("ملف CSV يحتوي اقتباساً غير مغلق");
  row.push(cell);
  if (row.some((x) => x.trim())) rows.push(row);
  if (!rows.length) return [];
  const heads = rows.shift().map((h) => h.replace(/^\uFEFF/, "").trim());
  if (!["date", "amount"].every((h) => heads.includes(h)))
    throw Error("أعمدة CSV المطلوبة: date,amount,reference,note");
  return rows.map((r) =>
    Object.fromEntries(heads.map((h, i) => [h, r[i]?.trim() || ""])),
  );
}
document.addEventListener("click", (e) =>
  run(async () => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.transfer) {
      location.hash = "transfer/" + b.dataset.transfer;
      return;
    }
    if (b.dataset.statementId) {
      location.hash = "bank-statement/" + b.dataset.statementId;
      return;
    }
    if (b.dataset.release) {
      const a = settlementState.allocations.find(
        (a) => String(a.id) === b.dataset.release,
      );
      modalV3(
        "فك تخصيص قبض",
        field(
          "المبلغ",
          "amount",
          "number",
          a.remaining / 100,
          'required min="0.01" step="0.01"',
        ) +
          field("التاريخ", "date", "date", today(), "required") +
          field("السبب", "reason", "text", "", "required"),
        "release",
        a.id,
      );
      return;
    }
    if (b.dataset.transferRemove !== undefined) {
      transferDraft.lines.splice(Number(b.dataset.transferRemove), 1);
      dirty = true;
      transferEditor();
      return;
    }
    if (b.dataset.finalize) {
      await api(
        "/api/banking/statements/" + b.dataset.finalize + "/finalize",
        "POST",
        {},
      );
      flash = "اعتُمدت التسوية بعد فحص الرصيد المعدل والحركات المعلقة.";
      await navigate();
      return;
    }
    const a = b.dataset.v3;
    if (a === "allocation") allocationModal();
    if (a === "warehouse")
      modalV3(
        "مستودع جديد",
        field("اسم المستودع", "name", "text", "", "required"),
        "warehouse",
      );
    if (a === "transfer-new") location.hash = "new-transfer";
    if (a === "transfer-line") {
      transferDraft.lines.push({ product_id: "", qty: 1 });
      dirty = true;
      transferEditor();
    }
    if (a === "transfer-post") {
      if (dirty) throw Error("احفظ مسودة التحويل أولاً");
      await api("/api/transfers/" + transferDraft.id + "/post", "POST", {
        version: transferDraft.version,
      });
      await navigate();
    }
    if (a === "transfer-cancel") {
      const reason = prompt("سبب عكس التحويل:");
      if (reason) {
        await api("/api/transfers/" + transferDraft.id + "/cancel", "POST", {
          reason,
        });
        await navigate();
      }
    }
    if (a === "bank")
      modalV3(
        "حساب بنكي — ريال يمني",
        field("اسم الحساب", "name", "text", "", "required") +
          field("تاريخ الرصيد الافتتاحي", "date", "date", today(), "required") +
          field(
            "الرصيد الافتتاحي (رأس مال)",
            "opening",
            "number",
            0,
            'min="0" step="0.01"',
          ),
        "bank",
      );
    if (a === "bank-transfer")
      modalV3(
        "تحويل نقدي / بنكي",
        `<div><label>من</label><select name="source_bank">${bankOptions("", true)}</select></div><div><label>إلى</label><select name="target_bank">${bankOptions("", true)}</select></div>${field("التاريخ", "date", "date", today(), "required")}${field("المبلغ", "amount", "number", "", 'min="0.01" step="0.01" required')}${field("البيان", "note", "text", "", "required")}${field("مرجع البنك", "reference")}`,
        "bank-transfer",
      );
    if (a === "statement-import") statementImport();
  }),
);
document.addEventListener("input", (e) => {
  if (!e.target.closest("#transfer-form")) return;
  dirty = true;
  const el = e.target;
  if (el.dataset.tl !== undefined)
    transferDraft.lines[Number(el.dataset.tl)][el.dataset.tkey] = el.value;
  else if (el.name) transferDraft[el.name] = el.value;
});
document.addEventListener("change", (e) =>
  run(async () => {
    if (e.target.id === "allocation-receipt")
      $("#allocation-invoice").innerHTML = allocationOptions(e.target.value);
    if (e.target.id === "statement-csv-file" && e.target.files[0])
      $("#statement-csv").value = await e.target.files[0].text();
    if (e.target.dataset.matchLine) {
      const s = await api(
        "/api/banking/statements/" + e.target.dataset.bankStatement + "/match",
        "POST",
        {
          line_id: Number(e.target.dataset.matchLine),
          move_id: e.target.value ? Number(e.target.value) : null,
        },
      );
      statementPage(s);
    }
  }),
);
document.addEventListener("submit", (e) => {
  if (!["v3-form", "aging-form", "transfer-form"].includes(e.target.id)) return;
  e.preventDefault();
  const f = e.target;
  run(async () => {
    const b = e.submitter;
    if (b?.disabled) return;
    if (b) b.disabled = true;
    try {
      const data = Object.fromEntries(new FormData(f));
      if (f.id === "aging-form") {
        agingDate = data.asof;
        await settlementsPage();
        return;
      }
      if (f.id === "transfer-form") {
        const t = await api(
          "/api/transfers" + (transferDraft.id ? "/" + transferDraft.id : ""),
          transferDraft.id ? "PUT" : "POST",
          { ...transferDraft, request_id: f.dataset.request },
        );
        dirty = false;
        if (transferDraft.id) await navigate();
        else location.hash = "transfer/" + t.id;
        return;
      }
      data.request_id = f.dataset.request;
      const kind = f.dataset.kind;
      let path = {
        allocation: "/api/allocations",
        release: "/api/allocations/" + f.dataset.extra + "/release",
        warehouse: "/api/warehouses",
        bank: "/api/banks",
        "bank-transfer": "/api/banking/transfers",
        statement: "/api/banking/statements",
      }[kind];
      if (kind === "statement") {
        data.lines = parseCSV(data.csv || "");
        delete data.csv;
      }
      const result = await api(path, "POST", data);
      $("#modal").close();
      flash = "تم الحفظ مع ربط المستندات وتسجيل الأثر.";
      if (kind === "statement") location.hash = "bank-statement/" + result.id;
      else await navigate();
    } catch (err) {
      if (f.id === "v3-form") $("#v3-error").textContent = err.message;
      else throw err;
    } finally {
      if (b) b.disabled = false;
    }
  });
});
