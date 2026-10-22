"use strict";
const enterpriseLayout = layout;
layout = function (page, title, actions, body) {
  enterpriseLayout(page, title, actions, body);
  const links =
    session.role === "admin"
      ? [
          ["procurement", "دورة الشراء"],
          ["position", "المركز المالي"],
          ["migration", "نقل العملاء"],
          ["controls", "الإقفال والنسخ"],
        ]
      : session.role === "accountant"
        ? [
            ["procurement", "دورة الشراء"],
            ["position", "المركز المالي"],
          ]
        : [];
  const labels = Object.fromEntries(links);
  if (labels[page])
    document.querySelector(".breadcrumb").textContent =
      "مساحة العمل / " + labels[page];
  document
    .querySelector(".top nav")
    .insertAdjacentHTML(
      "beforeend",
      links
        .map(
          ([key, label]) =>
            `<a href="#${key}" class="${page === key ? "active" : ""}">${label}</a>`,
        )
        .join(""),
    );
};
const directoryLayout = layout;
layout = function (page, title, actions, body) {
  directoryLayout(page, title, actions, body);
  if (page === "customers" && session.role !== "sales") {
    document.querySelectorAll("[data-statement]").forEach((button) => {
      const c = cache.customers.find(
        (c) => String(c.id) === button.dataset.statement,
      );
      if (c) {
        button.insertAdjacentHTML(
          "afterend",
          `<button class="link" data-ent="customer-edit" data-id="${c.id}">تعديل البيانات والائتمان</button>`,
        );
        button
          .closest("tr")
          .children[0].insertAdjacentHTML(
            "beforeend",
            `<small>${esc(c.region || "")} · حد الائتمان: ${money(c.credit_limit)} ر.ي</small>`,
          );
      }
    });
  }
  if (page === "products" && session.role === "admin")
    document.querySelectorAll("tbody tr").forEach((tr, i) => {
      const p = cache.products[i];
      if (p)
        tr.lastElementChild.insertAdjacentHTML(
          "beforeend",
          `<br><button class="link" data-ent="product-edit" data-id="${p.id}">تعديل${p.active ? "" : " — موقوف"}</button>`,
        );
    });
};
function directoryDialog(kind, id) {
  const c = (kind === "customers" ? cache.customers : cache.products).find(
    (r) => r.id === Number(id),
  );
  if (!c) throw Error("السجل غير موجود");
  $("#modal").innerHTML =
    `<h2>${kind === "customers" ? "بيانات العميل وحد الائتمان" : "بيانات الصنف وسعر البيع"}</h2><form id="directory-form" data-kind="${kind}" data-id="${id}"><div class="fields">${field("الاسم", "name", "text", c.name, "required")}${kind === "customers" ? field("الهاتف", "phone", "text", c.phone) + field("العنوان", "address", "text", c.address) + field("المنطقة", "region", "text", c.region) + field("حد الائتمان (صفر = دون حد)", "credit_limit", "number", c.credit_limit / 100, 'min="0" step="0.01"') : field("سعر البيع", "price", "number", c.price / 100, 'min="0" step="0.01"') + `<div><label><input type="checkbox" name="active" ${c.active ? "checked" : ""}> صنف نشط للبيع</label></div>`}</div><p class="help">لا يغير هذا الإجراء تفاصيل المستندات المرحلة أو أرصدة المخزون.</p><button>حفظ البيانات</button><button class="secondary" type="button" data-action="close-modal">إلغاء</button></form>`;
  $("#modal").showModal();
}
const enterpriseNavigate = navigate;
let legacyInput = null,
  legacyPlan = null,
  procurementState = null,
  positionDate = today();
navigate = async function () {
  const route = location.hash.slice(1) || "sales";
  if (
    !["procurement", "position", "migration", "controls", "new-order"].includes(
      route,
    ) &&
    !route.startsWith("order/") &&
    !route.startsWith("goods/") &&
    !route.startsWith("supplier-return/") &&
    !route.startsWith("new-supplier-return/")
  )
    return enterpriseNavigate();
  if (!session) return;
  dirty = false;
  await load();
  if (session.role === "sales") throw Error("هذا القسم للمدير أو المحاسب");
  if (route === "migration") return migrationPage();
  if (route === "position") return positionPage();
  if (route === "controls") return controlsPage();
  if (route === "procurement") return procurementPage();
  if (route === "new-order") return orderEditor();
  if (route.startsWith("order/"))
    return orderPage(
      await api("/api/purchase-orders/" + Number(route.split("/")[1])),
    );
  if (route.startsWith("goods/"))
    return goodsPage(
      await api("/api/goods-receipts/" + Number(route.split("/")[1])),
    );
  if (route.startsWith("new-supplier-return/"))
    return supplierReturnEditor(
      await api("/api/purchases/" + Number(route.split("/")[1])),
    );
  if (route.startsWith("supplier-return/"))
    return supplierReturnPage(
      await api("/api/supplier-returns/" + Number(route.split("/")[1])),
    );
};
function migrationPage() {
  if (session.role !== "admin") throw Error("نقل البيانات للمدير فقط");
  layout(
    "migration",
    "نقل العملاء من النظام السابق",
    "",
    `<div class="help">من النظام السابق اختر الإعدادات والبيانات ← تصدير قاعدة البيانات. هنا تُنقل الأسماء والهواتف والمناطق وحدود الائتمان، واختيارياً صافي الأرصدة حتى تاريخ الانتقال كقيود افتتاحية. لا تُنقل الفواتير القديمة؛ لا تبدأ معاملات حقيقية حتى مراجعة الأرصدة. التكرار والتعارض يُفحصان قبل الاعتماد.</div><form id="legacy-form" class="panel padded"><div class="fields"><div><label>النسخة الاحتياطية JSON</label><input name="file" type="file" accept=".json,application/json" required></div>${field("رمز المصدر الثابت", "source", "text", "wifi-home-legacy", "required")}${field("تاريخ رصيد الانتقال شامل اليوم", "date", "date", today(), "required")}<div><label><input name="include_balances" type="checkbox"> نقل الأرصدة من قيود العملاء (بعد المراجعة)</label></div><div><label><input name="exclude_demo" type="checkbox" checked> استبعاد المستندات المعلّمة كتجربة من الأرصدة</label></div></div><button>قراءة الملف ومعاينة النقل</button></form><div id="legacy-plan"></div>`,
  );
  legacyPlan = null;
  legacyInput = null;
}
function showLegacyPlan(p) {
  $("#legacy-plan").innerHTML =
    `<div class="panel padded"><h2>مراجعة قبل الاعتماد</h2><p>عملاء جدد: ${p.new} · سبق نقلهم: ${p.skipped} · تعارضات: ${p.conflicts}</p><p>مستندات معلّمة كتجربة: ${p.demo_documents || 0} · مستبعد منها: ${p.excluded_demo_documents || 0}</p><p>أرصدة مدينة جديدة: ${money(p.debit)} · أرصدة دائنة جديدة: ${money(p.credit)} ر.ي</p>${table(
      ["الاسم", "الهاتف", "المنطقة", "الرصيد المنقول", "الإجراء"],
      p.rows.map(
        (r) =>
          `<tr><td>${esc(r.name)}</td><td>${esc(r.phone)}</td><td>${esc(r.region)}</td><td>${money(r.opening)}</td><td>${{ create: "إضافة", skip: "تجاوز — سبق نقله", conflict: "تعارض يحتاج مراجعة" }[r.action]}</td></tr>`,
      ),
    )}<p class="help">التعارضات لا تُدمج تلقائياً. الاحتفاظ بنفس رمز المصدر يمنع تكرار نقل الأرصدة. راجع الإجمالي مع كشف النظام السابق.</p><button data-ent="commit-legacy" ${p.conflicts || !p.new ? "disabled" : ""}>اعتماد نقل العملاء والأرصدة الموضحة</button></div>`;
}
async function positionPage() {
  const p = await api("/api/position?asof=" + positionDate);
  layout(
    "position",
    "قائمة المركز المالي",
    `<a class="btn secondary" target="_blank" href="/print/position?asof=${positionDate}">مستند مستقل / PDF</a>`,
    `<form id="position-form" class="panel padded filters">${field("حتى تاريخ", "asof", "date", positionDate, "required")}<button>عرض</button></form><div class="notice ${p.balanced ? "" : "error"}">${p.balanced ? "المعادلة متوازنة" : "تحتاج مراجعة"} · الأصول − الالتزامات − حقوق الملكية = ${money(p.difference)} ر.ي</div>${[
      ["الأصول", "assets", "asset_total"],
      ["الالتزامات", "liabilities", "liability_total"],
      ["حقوق الملكية", "equity", "equity_total"],
    ]
      .map(
        ([title, key, total]) =>
          `<div class="panel padded"><h2>${title}</h2>${table(
            ["الحساب", "القيمة بالريال اليمني"],
            p[key].map(
              (r) =>
                `<tr><td>${esc(r.name)}</td><td>${money(r.amount)}</td></tr>`,
            ),
          )}<b>الإجمالي: ${money(p[total])} ر.ي</b></div>`,
      )
      .join(
        "",
      )}${p.unclassified.length ? '<div class="notice error">حسابات غير مصنفة: ' + p.unclassified.map((r) => esc(r.account)).join("، ") + "</div>" : ""}<div class="help">الأرصدة تراكمية حتى التاريخ، والنتيجة المتراكمة ضمن حقوق الملكية. أرصدة العملاء والموردين المدينة والدائنة تُعرض منفصلة. هذه قائمة داخلية من القيود المسجلة وليست قوائم مدققة.</div>`,
  );
}
async function controlsPage() {
  const c = await api("/api/controls");
  layout(
    "controls",
    "الإقفال والنسخ الاحتياطي",
    `<a class="btn secondary" href="/api/backup" download>تنزيل نسخة قاعدة البيانات</a>`,
    `<div class="help">النسخة تحتوي بيانات مالية وحسابات المستخدمين؛ احتفظ بها في مكان خاص خارج الخادم. إعادة الفتح للمدير فقط وبسبب موثق، وتبدأ من آخر فترة أو آخر كشف لكل بنك. لا تُحذف قيود أو مستندات عند إعادة الفتح.</div><div class="panel padded"><h2>الفترات المحاسبية</h2>${table(
      ["حتى", "سبب الإقفال", "الحالة", "إجراء"],
      c.periods.map(
        (r) =>
          `<tr><td>${esc(r.through)}</td><td>${esc(r.reason)}</td><td>${r.reopened ? "أعيد فتحها" : "مقفلة"}</td><td>${r.reopened ? "" : `<button data-ent="reopen" data-kind="period" data-id="${r.id}">إعادة فتح</button>`}</td></tr>`,
      ),
    )}</div><div class="panel padded"><h2>كشوف البنك المعتمدة</h2>${table(
      ["البنك", "المرجع", "حتى", "إجراء"],
      c.statements.map(
        (r) =>
          `<tr><td>${esc(r.bank)}</td><td>${esc(r.reference)}</td><td>${esc(r.to_date)}</td><td><button data-ent="reopen" data-kind="bank" data-id="${r.id}">إعادة فتح</button></td></tr>`,
      ),
    )}</div><div class="panel padded"><h2>سجل إعادة الفتح</h2>${table(
      ["الوقت", "النوع", "المستند", "السبب"],
      c.reopens.map(
        (r) =>
          `<tr><td>${esc(r.at)}</td><td>${r.kind === "period" ? "فترة" : "كشف بنك"}</td><td>${r.document_id}</td><td>${esc(r.reason)}</td></tr>`,
      ),
    )}</div>`,
  );
}
async function procurementPage() {
  const [orders, goods, returns] = await Promise.all(
    [
      "/api/purchase-orders",
      "/api/goods-receipts",
      "/api/supplier-returns",
    ].map((p) => api(p)),
  );
  layout(
    "procurement",
    "دورة الشراء والاستلام والمرتجعات",
    '<a class="btn" href="#new-order">أمر شراء جديد</a>',
    `<div class="help">أمر الشراء لا يؤثر محاسبياً. الاستلام يزيد المخزون مقابل بضاعة مستلمة غير مفوترة. فاتورة المورد المطابقة تسجل الذمة دون إضافة المخزون مرة أخرى. يمكن الاستلام على دفعات ضمن الكمية المعتمدة.</div><div class="panel padded"><h2>أوامر الشراء</h2>${table(
      ["الأمر", "المورد", "التاريخ", "القيمة", "الحالة"],
      orders.map(
        (r) =>
          `<tr><td><a href="#order/${r.id}">${esc(r.number)}</a></td><td>${esc(r.supplier)}</td><td>${esc(r.date)}</td><td>${money(r.total)}</td><td>${{ draft: "مسودة", approved: "معتمد", cancelled: "ملغى" }[r.status]}</td></tr>`,
      ),
    )}</div><div class="panel padded"><h2>استلام البضاعة</h2>${table(
      ["الاستلام", "الأمر", "المورد", "القيمة", "الفاتورة"],
      goods.map(
        (r) =>
          `<tr><td><a href="#goods/${r.id}">${esc(r.number)}</a></td><td>${esc(r.order)}</td><td>${esc(r.supplier)}</td><td>${money(r.total)}</td><td>${r.invoice ? `<a href="#purchase/${r.invoice.id}">${esc(r.invoice.number)}</a>` : r.status === "posted" ? "غير مفوتر" : "ملغى"}</td></tr>`,
      ),
    )}</div><div class="panel padded"><h2>مرتجعات الموردين</h2>${table(
      ["الإشعار", "الشراء", "المورد", "القيمة", "الحالة"],
      returns.map(
        (r) =>
          `<tr><td><a href="#supplier-return/${r.id}">${esc(r.number)}</a></td><td>${esc(r.purchase)}</td><td>${esc(r.supplier)}</td><td>${money(r.total)}</td><td>${pill(r.status)}</td></tr>`,
      ),
    )}</div><div class="panel padded"><h2>إنشاء مرتجع من شراء مرحّل</h2><form id="choose-supplier-return"><select name="purchase_id" required>${options(
      cache.purchases
        .filter((p) => p.status === "posted")
        .map((p) => ({ id: p.id, name: p.number + " — " + p.supplier })),
      null,
      "اختر الشراء",
    )}</select><button>تحديد البنود المرتجعة</button></form></div>`,
  );
}
function orderEditor() {
  procurementState = { lines: [{ product_id: "", qty: 1, cost: 0 }] };
  layout(
    "procurement",
    "أمر شراء جديد",
    '<a class="btn secondary" href="#procurement">الرجوع</a>',
    `<form id="order-form" class="panel padded"><div class="fields"><div><label>المورد</label><select name="supplier_id" required>${options(cache.suppliers, null, "اختر المورد")}</select></div>${field("التاريخ", "date", "date", today(), "required")}${field("ملاحظات", "note")}</div><div id="order-lines"></div><button type="button" data-ent="order-line">إضافة بند</button><button>حفظ مسودة الأمر</button></form>`,
  );
  orderLines();
}
function orderLines() {
  $("#order-lines").innerHTML = table(
    ["الصنف", "الكمية", "تكلفة الوحدة"],
    procurementState.lines.map(
      (l, i) =>
        `<tr><td><select data-ol="${i}" data-key="product_id" required>${options(
          cache.products.filter((p) => !p.service),
          l.product_id,
          "اختر الصنف",
        )}</select></td><td><input type="number" min="1" step="1" value="${l.qty}" data-ol="${i}" data-key="qty" required></td><td><input type="number" min="0" step="0.01" value="${l.cost}" data-ol="${i}" data-key="cost" required></td></tr>`,
    ),
  );
}
function orderPage(p) {
  layout(
    "procurement",
    p.number,
    `<a class="btn secondary" href="#procurement">دورة الشراء</a><a class="btn secondary" target="_blank" href="/print/purchase-orders/${p.id}">مستند الأمر / PDF</a>${p.status === "draft" ? `<button data-ent="approve-order" data-id="${p.id}">اعتماد أمر الشراء</button>` : ""}${p.status !== "cancelled" ? `<button class="danger" data-ent="cancel-order" data-id="${p.id}">إلغاء الأمر</button>` : ""}`,
    `<div class="panel padded"><h2>${esc(p.supplier)}</h2><p>${esc(p.date)} · ${esc(p.note)}</p>${table(
      ["الصنف", "المطلوب", "المستلم", "المتبقي", "تكلفة الوحدة"],
      p.lines.map(
        (l) =>
          `<tr><td>${esc(l.name)}</td><td>${l.qty}</td><td>${l.received}</td><td>${l.remaining}</td><td>${money(l.cost)}</td></tr>`,
      ),
    )}</div>${
      p.status === "approved"
        ? `<form id="receive-order" data-id="${p.id}" class="panel padded"><h2>استلام جزئي أو كامل</h2><div class="fields">${field("تاريخ الاستلام", "date", "date", today(), "required")}<div><label>المستودع</label><select name="warehouse_id" required>${options(cache.warehouses, 1)}</select></div>${field("ملاحظات", "note")}</div>${table(
            ["الصنف", "الكمية المستلمة الآن"],
            p.lines
              .filter((l) => l.remaining > 0)
              .map(
                (l) =>
                  `<tr><td>${esc(l.name)}</td><td><input data-receive-line="${l.id}" type="number" min="0" max="${l.remaining}" step="1" value="0"></td></tr>`,
              ),
          )}<button>ترحيل استلام المخزون</button></form>`
        : ""
    }`,
  );
}
function goodsPage(g) {
  layout(
    "procurement",
    g.number,
    `<a class="btn secondary" href="#procurement">دورة الشراء</a><a class="btn secondary" target="_blank" href="/print/goods-receipts/${g.id}">محضر الاستلام / PDF</a>${g.status === "posted" && !g.invoice ? `<button class="danger" data-ent="cancel-goods" data-id="${g.id}">عكس الاستلام</button>` : ""}`,
    `<div class="panel padded"><h2>${esc(g.supplier)}</h2><p>الأمر ${esc(g.order)} · ${esc(g.date)} · ${pill(g.status)}</p>${table(
      ["الصنف", "الكمية", "تكلفة الوحدة", "القيمة"],
      g.lines.map(
        (l) =>
          `<tr><td>${esc(l.name)}</td><td>${l.qty}</td><td>${money(l.cost)}</td><td>${money(l.qty * l.cost)}</td></tr>`,
      ),
    )}</div>${g.invoice ? `<a class="btn" href="#purchase/${g.invoice.id}">فاتورة المورد ${esc(g.invoice.number)}</a>` : g.status === "posted" ? `<form id="invoice-goods" data-id="${g.id}" class="panel padded"><h2>إنشاء مسودة فاتورة المورد المطابقة</h2><p>بنود وتكلفة ومورد الفاتورة مرتبطة بهذا الاستلام ولا تضيف مخزوناً مرة ثانية.</p><div class="fields">${field("تاريخ الفاتورة", "date", "date", today(), "required")}${field("المسدد نقداً", "paid", "number", 0, 'min="0" step="0.01"')}</div><button>إنشاء فاتورة للمراجعة والترحيل</button></form>` : ""}`,
  );
}
function supplierReturnEditor(p) {
  layout(
    "procurement",
    "مرتجع من " + esc(p.number),
    "",
    `<form id="supplier-return-form" data-id="${p.id}" class="panel padded"><div class="fields">${field("التاريخ", "date", "date", today(), "required")}${field("سبب المرتجع", "reason", "text", "", "required")}<div><label>مستودع الرد</label><select name="warehouse_id" required>${options(cache.warehouses, p.warehouse_id)}</select></div></div>${table(
      ["الصنف", "الكمية المشتراة", "كمية الرد الآن"],
      p.lines.map(
        (l) =>
          `<tr><td>${esc(l.name)}</td><td>${l.qty}</td><td><input type="number" data-pr-line="${l.id}" min="0" max="${l.qty}" value="0" step="1"></td></tr>`,
      ),
    )}<p class="help">الخادم يتحقق من الكميات التي سبق ردها والمخزون الفعلي. قيمة المورد بالتكلفة الأصلية، وفرقها عن قيمة المخزون الحالية يسجل في حساب مستقل.</p><button>ترحيل مرتجع المورد</button></form>`,
  );
}
function supplierReturnPage(r) {
  layout(
    "procurement",
    r.number,
    `<a class="btn secondary" href="#procurement">دورة الشراء</a><a class="btn secondary" target="_blank" href="/print/supplier-returns/${r.id}">الإشعار / PDF</a>${r.status === "posted" ? `<button class="danger" data-ent="cancel-pr" data-id="${r.id}">عكس المرتجع</button>` : ""}`,
    `<div class="panel padded"><h2>${esc(r.supplier)}</h2><p>الفاتورة: ${esc(r.purchase)} · ${esc(r.date)} · ${esc(r.reason)}</p>${table(
      ["الصنف", "الكمية", "تخفيض ذمة المورد", "قيمة المخزون"],
      r.lines.map(
        (l) =>
          `<tr><td>${esc(l.name)}</td><td>${l.qty}</td><td>${money(l.amount)}</td><td>${money(l.stock_cost)}</td></tr>`,
      ),
    )}<p>إجمالي تخفيض المورد: ${money(r.total)} ر.ي · المخزون المردود: ${money(r.stock_cost)} ر.ي</p></div>`,
  );
}
document.addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.ol !== undefined) {
    const l = procurementState.lines[Number(el.dataset.ol)];
    l[el.dataset.key] = Number(el.value);
  }
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ent]");
  if (!b) return;
  run(async () => {
    const action = b.dataset.ent;
    if (action === "customer-edit" || action === "product-edit")
      return directoryDialog(
        action === "customer-edit" ? "customers" : "products",
        b.dataset.id,
      );
    if (action === "order-line") {
      procurementState.lines.push({ product_id: "", qty: 1, cost: 0 });
      return orderLines();
    }
    b.disabled = true;
    try {
      if (action === "commit-legacy") {
        if (!legacyInput || !legacyPlan) throw Error("أعد معاينة الملف");
        if (!confirm("اعتماد نقل الأسماء والأرصدة المعروضة؟")) return;
        const r = await api("/api/legacy/import", "POST", {
          ...legacyInput,
          token: legacyPlan.token,
          request_id: crypto.randomUUID(),
        });
        flash = `تم نقل ${r.created} عميل، وتجاوز ${r.skipped} سبق نقلهم.`;
        location.hash = "customers";
        return;
      }
      let path,
        payload = { request_id: crypto.randomUUID() };
      if (action === "approve-order")
        path = "/api/purchase-orders/" + b.dataset.id + "/approve";
      if (
        ["cancel-order", "cancel-goods", "cancel-pr", "reopen"].includes(action)
      ) {
        const reason = prompt("اكتب سبب الإجراء للمراجعة:");
        if (!reason) return;
        payload.reason = reason;
        path =
          action === "reopen"
            ? "/api/reopen/" + b.dataset.kind + "/" + b.dataset.id
            : {
                "cancel-order": "/api/purchase-orders/",
                "cancel-goods": "/api/goods-receipts/",
                "cancel-pr": "/api/supplier-returns/",
              }[action] +
              b.dataset.id +
              "/cancel";
      }
      if (path) {
        await api(path, "POST", payload);
        flash = "تم تنفيذ الإجراء وتسجيله في سجل التدقيق.";
        await navigate();
      }
    } finally {
      b.disabled = false;
    }
  });
});
document.addEventListener("submit", (e) => {
  const f = e.target;
  if (
    ![
      "directory-form",
      "legacy-form",
      "position-form",
      "order-form",
      "receive-order",
      "invoice-goods",
      "choose-supplier-return",
      "supplier-return-form",
    ].includes(f.id)
  )
    return;
  e.preventDefault();
  run(async () => {
    const b = f.querySelector('button:not([type="button"])');
    if (b) b.disabled = true;
    try {
      let d = Object.fromEntries(new FormData(f));
      d.request_id = crypto.randomUUID();
      if (f.id === "directory-form") {
        if (f.dataset.kind === "products")
          d.active = f.querySelector("[name=active]").checked;
        await api("/api/" + f.dataset.kind + "/" + f.dataset.id, "PUT", d);
        $("#modal").close();
        flash = "تم تحديث البيانات دون تغيير المستندات السابقة.";
        return navigate();
      }
      if (f.id === "legacy-form") {
        const file = f.querySelector("[type=file]").files[0];
        if (!file || file.size > 850000)
          throw Error(
            "اختر ملف JSON لا يتجاوز 850 كيلوبايت؛ الملفات الأكبر تحتاج ترحيلاً من الخادم.",
          );
        legacyInput = {
          source: d.source,
          date: d.date,
          include_balances: f.querySelector("[name=include_balances]").checked,
          exclude_demo: f.querySelector("[name=exclude_demo]").checked,
          backup: JSON.parse(await file.text()),
        };
        legacyPlan = await api("/api/legacy/preview", "POST", legacyInput);
        showLegacyPlan(legacyPlan);
        return;
      }
      if (f.id === "position-form") {
        positionDate = d.asof;
        return positionPage();
      }
      if (f.id === "choose-supplier-return") {
        location.hash = "new-supplier-return/" + Number(d.purchase_id);
        return;
      }
      if (f.id === "order-form") {
        d.supplier_id = Number(d.supplier_id);
        d.lines = procurementState.lines;
        const r = await api("/api/purchase-orders", "POST", d);
        location.hash = "order/" + r.id;
      }
      if (f.id === "receive-order") {
        d.warehouse_id = Number(d.warehouse_id);
        d.lines = [...f.querySelectorAll("[data-receive-line]")]
          .filter((i) => Number(i.value) > 0)
          .map((i) => ({
            order_line_id: Number(i.dataset.receiveLine),
            qty: Number(i.value),
          }));
        const r = await api(
          "/api/purchase-orders/" + f.dataset.id + "/receive",
          "POST",
          d,
        );
        location.hash = "goods/" + r.id;
      }
      if (f.id === "invoice-goods") {
        const r = await api(
          "/api/goods-receipts/" + f.dataset.id + "/invoice",
          "POST",
          d,
        );
        location.hash = "purchase/" + r.id;
      }
      if (f.id === "supplier-return-form") {
        d.purchase_id = Number(f.dataset.id);
        d.warehouse_id = Number(d.warehouse_id);
        d.lines = [...f.querySelectorAll("[data-pr-line]")]
          .filter((i) => Number(i.value) > 0)
          .map((i) => ({
            purchase_line_id: Number(i.dataset.prLine),
            qty: Number(i.value),
          }));
        const r = await api("/api/supplier-returns", "POST", d);
        location.hash = "supplier-return/" + r.id;
      }
    } finally {
      if (b) b.disabled = false;
    }
  });
});
