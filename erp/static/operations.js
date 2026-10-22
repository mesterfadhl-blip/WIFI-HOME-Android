"use strict";
let purchasing = null;
const baseNavigate = navigate;
navigate = async function () {
  if (!session) return;
  const route = location.hash.slice(1) || "sales";
  if (
    !["purchases", "suppliers", "returns", "finance", "new-purchase"].includes(
      route,
    ) &&
    !route.startsWith("purchase/") &&
    !route.startsWith("return/") &&
    !route.startsWith("new-return/")
  )
    return baseNavigate();
  dirty = false;
  draft = null;
  await load();
  if (session.role === "sales" && !route.startsWith("return/"))
    throw Error("هذا القسم للمدير أو المحاسب");
  if (route === "purchases") return purchaseList();
  if (route === "suppliers") return suppliers();
  if (route === "returns") return returnList();
  if (route === "finance") return financePage();
  if (route === "new-purchase") {
    purchasing = {
      status: "draft",
      date: today(),
      supplier_id: "",
      paid: 0,
      note: "",
      lines: [{ product_id: "", qty: 1, cost: 0 }],
    };
    return purchaseEditor();
  }
  if (route.startsWith("purchase/")) {
    const p = await api("/api/purchases/" + Number(route.split("/")[1]));
    purchasing = {
      ...p,
      paid: p.paid / 100,
      lines: p.lines.map((l) => ({ ...l, cost: l.cost / 100 })),
    };
    return purchaseEditor();
  }
  if (route.startsWith("new-return/"))
    return returnEditor(
      await api("/api/invoices/" + Number(route.split("/")[1])),
    );
  if (route.startsWith("return/"))
    return returnView(await api("/api/returns/" + Number(route.split("/")[1])));
};
function purchaseList() {
  layout(
    "purchases",
    "فواتير المشتريات",
    '<button data-op="new-purchase">فاتورة شراء جديدة</button>',
    `<div class="panel">${table(
      ["المستند", "التاريخ", "المورد", "القيمة", "مسدد عند الإصدار", "الحالة"],
      cache.purchases.map(
        (p) =>
          `<tr><td><button class="link" data-purchase="${p.id}">${esc(p.number)}</button></td><td>${esc(p.date)}</td><td>${esc(p.supplier)}</td><td class="num">${money(p.total)}</td><td class="num">${money(p.paid)}</td><td>${pill(p.status)}</td></tr>`,
      ),
    )}</div><div class="help">حفظ المسودة لا يغيّر الكميات. الترحيل يستلم البضاعة ويُثبت قيمتها وحساب المورد والدفع في معاملة واحدة. الفواتير المرحلة لا تعدل مباشرة.</div>`,
  );
}
function purchaseEditor() {
  const p = purchasing,
    locked = p.status !== "draft";
  layout(
    "purchases",
    p.number || "فاتورة شراء جديدة",
    '<a class="btn secondary" href="#purchases">سجل المشتريات</a>',
    `<div class="panel"><div class="doc-toolbar"><div class="actions">${locked ? `<a class="btn secondary" target="_blank" href="/print/purchases/${p.id}">مستند الشراء / PDF</a>${p.status === "posted" ? '<button class="danger" data-op="cancel-purchase">إلغاء محاسبي</button>' : ""}` : `<button form="purchase-form">حفظ المسودة</button>${p.id ? '<button class="secondary" data-op="post-purchase">ترحيل واستلام</button>' : ""}`}</div>${pill(p.status)}</div><div class="document"><h2>${esc(p.number || "جديد")}</h2><form id="purchase-form"><fieldset ${locked ? "disabled" : ""} style="border:0;padding:0"><div class="fields doc-meta"><div><label>المورد</label><select name="supplier_id" required>${options(cache.suppliers, p.supplier_id, "اختر المورد")}</select></div>${field("تاريخ الاستلام", "date", "date", p.date, "required")}${field("المسدد عند الإصدار", "paid", "number", p.paid, 'min="0" step="0.01"')}${field("ملاحظات", "note", "text", p.note)}</div><div class="table"><table class="lines"><thead><tr><th>الصنف</th><th>الكمية</th><th>تكلفة الوحدة</th><th>القيمة</th><th></th></tr></thead><tbody>${p.lines
      .map(
        (l, i) =>
          `<tr><td><select data-pl="${i}" data-pkey="product_id" required>${options(
            cache.products.filter((p) => !p.service),
            l.product_id,
            "اختر الصنف",
          )}</select></td><td><input type="number" min="1" step="1" data-pl="${i}" data-pkey="qty" value="${esc(l.qty)}" required aria-label="كمية الشراء ${i + 1}"></td><td><input type="number" min="0" step="0.01" data-pl="${i}" data-pkey="cost" value="${esc(l.cost)}" required aria-label="تكلفة الشراء ${i + 1}"></td><td class="num" id="purchase-line-${i}">${money(Math.round(l.qty * l.cost * 100))}</td><td><button type="button" class="secondary" data-premove="${i}">×</button></td></tr>`,
      )
      .join(
        "",
      )}</tbody></table></div>${locked ? "" : '<button type="button" class="link" data-op="purchase-line">+ إضافة بند</button>'}<div class="totals" id="purchase-totals"></div></fieldset></form></div></div>`,
  );
  purchaseTotals();
}
function purchaseTotals() {
  const total = purchasing.lines.reduce(
      (n, l) => n + Math.round(Number(l.qty) * Number(l.cost) * 100),
      0,
    ),
    paid = Math.round(Number(purchasing.paid) * 100);
  $("#purchase-totals").innerHTML =
    `<div class="grand"><span>إجمالي الشراء</span><b>${money(total)}</b></div><div><span>المسدد عند الإصدار</span><b>${money(paid)}</b></div><div><span>المستحق عند الإصدار</span><b>${money(total - paid)}</b></div>`;
}
function suppliers() {
  layout(
    "suppliers",
    "الموردون وحساباتهم",
    '<button data-op="supplier">مورد جديد</button><button class="secondary" data-op="payment">سند صرف لمورد</button>',
    `<div class="panel">${table(
      ["المورد", "الهاتف", "المستحق الحالي", "المخرجات"],
      cache.suppliers.map(
        (s) =>
          `<tr><td>${esc(s.name)}</td><td>${esc(s.phone)}</td><td class="num">${money(s.balance)}</td><td><button class="link" data-supplier-ledger="${s.id}">كشف حساب المورد</button></td></tr>`,
      ),
    )}</div><div class="panel"><div class="panel-head"><h2>سندات الصرف للموردين</h2></div>${table(
      ["المستند", "التاريخ", "المورد", "المبلغ", "البيان"],
      cache.payments.map(
        (p) =>
          `<tr><td>${esc(p.number)}</td><td>${esc(p.date)}</td><td>${esc(p.supplier)}</td><td class="num">${money(p.amount)}</td><td>${esc(p.note)}</td></tr>`,
      ),
    )}</div>`,
  );
}
function returnList() {
  const eligible = cache.invoices.filter((i) => i.status === "posted");
  layout(
    "returns",
    "الإشعارات الدائنة ومرتجعات المبيعات",
    "",
    `<div class="panel padded"><h2>مرتجع من فاتورة أصلية</h2><form id="choose-return" class="filters"><div><label>الفاتورة الأصلية</label><select name="invoice_id" required>${options(
      eligible.map((i) => ({ id: i.id, name: i.number + " · " + i.customer })),
      null,
      "اختر الفاتورة",
    )}</select></div><button>فتح بنود الفاتورة</button></form></div><div class="panel">${table(
      [
        "الإشعار",
        "الفاتورة الأصلية",
        "التاريخ",
        "العميل",
        "قيمة المرتجع",
        "مردود نقدي",
        "الحالة",
      ],
      cache.returns.map(
        (r) =>
          `<tr><td><button class="link" data-credit="${r.id}">${esc(r.number)}</button></td><td>${esc(r.invoice)}</td><td>${esc(r.date)}</td><td>${esc(r.customer)}</td><td class="num">${money(r.total)}</td><td class="num">${money(r.refund)}</td><td>${pill(r.status)}</td></tr>`,
      ),
    )}</div>`,
  );
}
function returnEditor(s) {
  layout(
    "returns",
    "مرتجع من " + esc(s.number),
    '<a class="btn secondary" href="#returns">سجل المرتجعات</a>',
    `<div class="help">حدد الكمية المرتجعة. القيم والتكلفة ونصيب الخصم تُستخرج من الفاتورة الأصلية على الخادم، ولا يمكن إدخال سعر مرتجع مختلف. المبلغ غير المردود نقداً يخفض رصيد حساب العميل.</div><form id="return-form" data-invoice="${s.id}" data-request="${crypto.randomUUID()}"><div class="panel padded fields">${field("تاريخ المرتجع", "date", "date", today(), "required")}${field("السبب", "reason", "text", "", "required")}${field("مردود نقدي (صفر = تخفيض الحساب)", "refund", "number", 0, 'min="0" step="0.01"')}</div><div class="panel">${table(
      ["الصنف", "المباع", "المرتجع سابقاً", "متاح للرد", "الكمية المرتجعة"],
      s.lines.map(
        (l) =>
          `<tr><td>${esc(l.name)}</td><td>${l.qty}</td><td>${l.returned_qty}</td><td>${l.returnable_qty}</td><td><input type="number" data-return-line="${l.id}" min="0" max="${l.returnable_qty}" step="1" value="0" aria-label="مرتجع ${esc(l.name)}"></td></tr>`,
      ),
    )}</div><button>اعتماد إشعار المرتجع</button></form>`,
  );
}
function returnView(s) {
  layout(
    "returns",
    esc(s.number),
    `<a class="btn secondary" href="#returns">المرتجعات</a><a class="btn secondary" target="_blank" href="/print/returns/${s.id}">الإشعار الدائن / PDF</a>${s.status === "posted" && session.role !== "sales" ? `<button class="danger" data-cancel-credit="${s.id}">إلغاء المرتجع</button>` : ""}`,
    `<div class="panel padded"><div class="split"><h2>${esc(s.customer)}</h2>${pill(s.status)}</div><p>الفاتورة الأصلية: ${esc(s.invoice)} · التاريخ: ${esc(s.date)}</p><p>${esc(s.reason)}</p>${table(
      ["الصنف", "الكمية المرتجعة", "القيمة بعد الخصم"],
      s.lines.map(
        (l) =>
          `<tr><td>${esc(l.name)}</td><td>${l.qty}</td><td class="num">${money(l.net)}</td></tr>`,
      ),
    )}<div class="totals"><div class="grand"><span>الإشعار الدائن</span><b>${money(s.total)}</b></div><div><span>مردود نقدي</span><b>${money(s.refund)}</b></div><div><span>تخفيض حساب العميل</span><b>${money(s.total - s.refund)}</b></div></div></div>`,
  );
}
let financeFilter = { from: today().slice(0, 7) + "-01", to: today() };
async function financePage() {
  const q = new URLSearchParams(financeFilter),
    f = await api("/api/finance?" + q);
  layout(
    "finance",
    "المحاسبة والنتائج المالية",
    `<button data-op="expense">مصروف تشغيل</button><a class="btn secondary" target="_blank" href="/print/finance?${q}">المخرجات المالية / PDF</a>${session.role === "admin" ? '<button class="secondary" data-op="funding">تمويل الصندوق</button><button class="secondary" data-op="close-period">إقفال فترة</button>' : ""}`,
    `<form id="finance-filter" class="panel padded filters">${field("من تاريخ", "from", "date", financeFilter.from)}${field("إلى تاريخ", "to", "date", financeFilter.to)}<button>تحديث</button></form><div class="grid">${[
      ["صافي المبيعات بعد المرتجعات", f.net_sales],
      ["مجمل الربح", f.gross_profit],
      ["مصروفات التشغيل", f.expenses],
      ["فروق تكلفة مردودات الشراء", f.purchase_return_variance || 0],
      ["صافي نتيجة الفترة", f.net_profit],
    ]
      .map(
        ([t, v]) =>
          `<div class="panel metric"><label>${t}</label><strong>${money(v)}</strong><small>ريال يمني · من القيود المرحلة</small></div>`,
      )
      .join(
        "",
      )}</div><div class="panel"><div class="panel-head"><h2>ميزان المراجعة التراكمي حتى ${esc(f.to)}</h2><span class="tag">${f.debits === f.credits ? "متوازن" : "يوجد فرق"}</span></div>${table(
      ["الحساب", "حركة مدين", "حركة دائن", "صافي مدين", "صافي دائن"],
      f.trial.map(
        (r) =>
          `<tr><td>${esc(r.account)}</td><td class="num">${money(r.debit)}</td><td class="num">${money(r.credit)}</td><td class="num">${money(Math.max(0, r.debit - r.credit))}</td><td class="num">${money(Math.max(0, r.credit - r.debit))}</td></tr>`,
      ),
    )}<div class="padded split"><b>إجمالي المدين: ${money(f.debits)}</b><b>إجمالي الدائن: ${money(f.credits)}</b></div></div><div class="panel"><div class="panel-head"><h2>تقييم المخزون الحالي</h2><span class="muted">لقطة حالية — ليست رصيداً تاريخياً للفترة المحددة</span></div>${table(
      ["الصنف", "الكمية", "متوسط تكلفة الوحدة (مقرب)", "إجمالي القيمة الدقيق"],
      f.stock.map(
        (p) =>
          `<tr><td>${esc(p.name)}</td><td>${p.qty}</td><td class="num">${money(p.cost)}</td><td class="num">${money(p.stock_value)}</td></tr>`,
      ),
    )}<div class="padded"><b>إجمالي القيمة الحالية: ${money(f.stock_value)}</b></div></div><div class="panel"><div class="panel-head"><h2>المصروفات</h2></div>${table(
      ["المستند", "التاريخ", "التصنيف", "البيان", "المبلغ"],
      cache.expenses.map(
        (e) =>
          `<tr><td>${esc(e.number)}</td><td>${esc(e.date)}</td><td>${esc(e.category)}</td><td>${esc(e.note)}</td><td class="num">${money(e.amount)}</td></tr>`,
      ),
    )}</div><div class="panel padded"><h2>الفترات المقفلة</h2>${cache.periods.map((p) => `<p>حتى ${esc(p.through)} — ${esc(p.reason)}</p>`).join("") || '<p class="muted">لا توجد فترة مقفلة</p>'}<small>الإقفال يمنع الإضافة والتعديل والعكس ضمن الفترة. لا يوجد فتح فترة تلقائي.</small></div>`,
  );
}
function opModal(title, body, kind, extra = "") {
  $("#modal").innerHTML =
    `<h2>${title}</h2><form id="operation-form" data-request="${crypto.randomUUID()}" data-kind="${kind}" data-extra="${esc(extra)}"><div class="fields">${body}</div><p id="operation-error" class="auth-error"></p><div class="actions" style="margin-top:20px"><button>حفظ</button><button class="secondary" type="button" data-action="close-modal">إلغاء</button></div></form>`;
  $("#modal").showModal();
}
function opDialog(kind, extra = "") {
  if (kind === "funding")
    opModal(
      "تمويل رأسمالي للصندوق",
      field(
        "المبلغ",
        "amount",
        "number",
        "",
        'min="0.01" step="0.01" required',
      ) +
        field("التاريخ", "date", "date", today(), "required") +
        field("البيان", "note", "text", "", "required"),
      kind,
    );
  if (kind === "supplier")
    opModal(
      "مورد جديد",
      field("اسم المورد", "name", "text", "", "required") +
        field("الهاتف", "phone") +
        field("العنوان", "address"),
      kind,
    );
  if (kind === "payment")
    opModal(
      "سند صرف لمورد",
      '<div><label>المورد</label><select name="supplier_id" required>' +
        options(cache.suppliers, "") +
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
      kind,
    );
  if (kind === "expense")
    opModal(
      "مصروف تشغيل",
      field("التصنيف", "category", "text", "", "required") +
        field("البيان", "note", "text", "", "required") +
        field(
          "المبلغ",
          "amount",
          "number",
          "",
          'min="0.01" step="0.01" required',
        ) +
        field("التاريخ", "date", "date", today(), "required"),
      kind,
    );
  if (kind === "close-period")
    opModal(
      "إقفال فترة محاسبية",
      field("إقفال حتى نهاية يوم", "through", "date", today(), "required") +
        field("السبب", "reason", "text", "", "required"),
      kind,
    );
  if (kind === "supplier-ledger")
    opModal(
      "كشف حساب المورد",
      field("من تاريخ", "from", "date", financeFilter.from) +
        field("إلى تاريخ", "to", "date", financeFilter.to),
      kind,
      extra,
    );
}
document.addEventListener("click", (e) =>
  run(async () => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.purchase) {
      location.hash = "purchase/" + b.dataset.purchase;
      return;
    }
    if (b.dataset.credit) {
      location.hash = "return/" + b.dataset.credit;
      return;
    }
    if (b.dataset.supplierLedger) {
      opDialog("supplier-ledger", b.dataset.supplierLedger);
      return;
    }
    if (b.dataset.premove !== undefined) {
      purchasing.lines.splice(Number(b.dataset.premove), 1);
      dirty = true;
      purchaseEditor();
      return;
    }
    if (b.dataset.cancelCredit) {
      const reason = prompt("سبب إلغاء المرتجع:");
      if (reason) {
        await api(
          "/api/returns/" + b.dataset.cancelCredit + "/cancel",
          "POST",
          { reason },
        );
        await navigate();
      }
      return;
    }
    const a = b.dataset.op;
    if (a === "new-purchase") location.hash = "new-purchase";
    if (a === "purchase-line") {
      purchasing.lines.push({ product_id: "", qty: 1, cost: 0 });
      dirty = true;
      purchaseEditor();
    }
    if (
      ["supplier", "payment", "expense", "close-period", "funding"].includes(a)
    )
      opDialog(a);
    if (a === "post-purchase") {
      if (dirty) throw Error("احفظ مسودة الشراء قبل الترحيل");
      await api("/api/purchases/" + purchasing.id + "/post", "POST", {
        version: purchasing.version,
      });
      flash = "تم ترحيل الشراء واستلام الكمية وتحديث التقييم والمورد.";
      await navigate();
    }
    if (a === "cancel-purchase") {
      const reason = prompt("سبب إلغاء الشراء:");
      if (reason) {
        await api("/api/purchases/" + purchasing.id + "/cancel", "POST", {
          reason,
        });
        await navigate();
      }
    }
  }),
);
document.addEventListener("input", (e) => {
  if (!e.target.closest("#purchase-form")) return;
  dirty = true;
  const el = e.target;
  if (el.dataset.pl !== undefined) {
    const l = purchasing.lines[Number(el.dataset.pl)];
    l[el.dataset.pkey] = el.value;
    if (el.dataset.pkey === "product_id") {
      l.cost =
        (cache.products.find((p) => String(p.id) === el.value)?.cost || 0) /
        100;
      purchaseEditor();
    } else {
      $("#purchase-line-" + el.dataset.pl).textContent = money(
        Math.round(Number(l.qty) * Number(l.cost) * 100),
      );
      purchaseTotals();
    }
  } else if (el.name) {
    purchasing[el.name] = el.value;
    purchaseTotals();
  }
});
document.addEventListener("submit", (e) => {
  if (
    ![
      "purchase-form",
      "operation-form",
      "choose-return",
      "return-form",
      "finance-filter",
    ].includes(e.target.id)
  )
    return;
  e.preventDefault();
  const form = e.target;
  run(async () => {
    const data = Object.fromEntries(new FormData(form));
    const submit =
      e.submitter ||
      form.querySelector("button:not([type]),button[type=submit]");
    if (submit?.disabled) return;
    if (submit) submit.disabled = true;
    try {
      if (form.id === "purchase-form") {
        const p = await api(
          "/api/purchases" + (purchasing.id ? "/" + purchasing.id : ""),
          purchasing.id ? "PUT" : "POST",
          purchasing,
        );
        dirty = false;
        if (purchasing.id) await navigate();
        else location.hash = "purchase/" + p.id;
      }
      if (form.id === "choose-return")
        location.hash = "new-return/" + data.invoice_id;
      if (form.id === "return-form") {
        data.request_id = form.dataset.request;
        data.invoice_id = Number(form.dataset.invoice);
        data.lines = [...form.querySelectorAll("[data-return-line]")]
          .filter((el) => Number(el.value) > 0)
          .map((el) => ({
            sale_line_id: Number(el.dataset.returnLine),
            qty: Number(el.value),
          }));
        const r = await api("/api/returns", "POST", data);
        location.hash = "return/" + r.id;
      }
      if (form.id === "finance-filter") {
        financeFilter = data;
        await financePage();
      }
      if (form.id === "operation-form") {
        data.request_id = form.dataset.request;
        const kind = form.dataset.kind;
        if (kind === "supplier-ledger") {
          window.open(
            "/print/supplier?" +
              new URLSearchParams({ ...data, supplier: form.dataset.extra }),
            "_blank",
          );
          $("#modal").close();
          return;
        }
        if (
          kind === "close-period" &&
          !confirm("إقفال الفترة يمنع تعديل المستندات ضمنها. هل تعتمد الإقفال؟")
        )
          return;
        await api(
          "/api/" +
            {
              supplier: "suppliers",
              payment: "payments",
              expense: "expenses",
              "close-period": "periods",
              funding: "funding",
            }[kind],
          "POST",
          data,
        );
        $("#modal").close();
        flash = "تم الحفظ والترحيل.";
        await navigate();
      }
    } catch (err) {
      if (form.id === "operation-form")
        $("#operation-error").textContent = err.message;
      else throw err;
    } finally {
      if (submit) submit.disabled = false;
    }
  });
});
