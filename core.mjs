export const round = (n) =>
  Math.round((Number(n) + Number.EPSILON) * 100) / 100;
const number = (v, label) => {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0) throw Error("قيمة غير صحيحة: " + label);
  return n;
};
const active = (s) => s.status !== "ملغاة";
export const day = (value) => String(value || "").slice(0, 10);
export function emptyDB() {
  return {
    customers: [],
    products: [],
    sales: [],
    receipts: [],
    expenses: [],
    journal: [],
    stockMoves: [],
    audit: [],
    dailyClosings: [],
    seq: { sale: 1, customer: 1, product: 1, receipt: 1, expense: 1 },
    settings: { company: "واي فاي هوم" },
  };
}
export function normalize(input) {
  if (
    !input ||
    !Array.isArray(input.customers) ||
    !Array.isArray(input.products) ||
    !Array.isArray(input.sales)
  )
    throw Error("الملف لا يحتوي قاعدة بيانات عملاء وأصناف وفواتير صالحة");
  const db = structuredClone(input);
  for (const key of [
    "customers",
    "products",
    "sales",
    "receipts",
    "expenses",
    "journal",
    "stockMoves",
    "audit",
    "dailyClosings",
  ]) {
    if (db[key] === undefined) db[key] = [];
    if (!Array.isArray(db[key])) throw Error("بيانات غير صالحة: " + key);
  }
  db.seq = { ...emptyDB().seq, ...db.seq };
  db.settings = { ...emptyDB().settings, ...db.settings };
  return db;
}
export function balance(db, cid) {
  return round(
    db.journal
      .filter((j) => j.account === "العملاء" && j.customerId === cid)
      .reduce((n, j) => n + Number(j.debit || 0) - Number(j.credit || 0), 0),
  );
}
export function cash(db) {
  return round(
    db.journal
      .filter((j) => j.account === "الصندوق")
      .reduce((n, j) => n + Number(j.debit || 0) - Number(j.credit || 0), 0),
  );
}
function dateCheck(db, date) {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
    !Number.isFinite(Date.parse(date + "T12:00:00Z")) ||
    new Date(date + "T12:00:00Z").toISOString().slice(0, 10) !== date
  )
    throw Error("التاريخ غير صحيح");
  if (
    db.dailyClosings.some((c) => day(c.date) === date && c.status !== "ملغاة")
  )
    throw Error("اليوم مغلق محاسبياً؛ لا يمكن تعديله");
}
function next(db, key, prefix) {
  let ref;
  do {
    ref = prefix + String(db.seq[key]++).padStart(5, "0");
  } while (
    [...db.sales, ...db.receipts, ...db.expenses].some((x) => x.ref === ref)
  );
  return ref;
}
function entry(db, ref, date, desc, rows) {
  const delta = round(
    rows.reduce((n, r) => n + Number(r.debit || 0) - Number(r.credit || 0), 0),
  );
  if (delta !== 0) throw Error("القيد غير متوازن");
  db.journal.push(
    ...rows.map((r) => ({ ref, date: date + "T12:00:00", desc, ...r })),
  );
}
function audit(db, action, ref, before, after, reason) {
  db.audit.push({
    at: new Date().toISOString(),
    user: "المستخدم المحلي",
    action,
    ref,
    reason,
    before: structuredClone(before || null),
    after: structuredClone(after || null),
  });
}
function reverse(db, s, tag) {
  const posting = s.postingRef || s.ref,
    rows = db.journal.filter((j) => j.ref === posting);
  if (!rows.length)
    throw Error("لا توجد قيود أصلية لهذه الفاتورة؛ يلزم مراجعتها قبل التعديل");
  entry(
    db,
    tag,
    day(s.date),
    "عكس " + posting,
    rows.map((j) => ({
      account: j.account,
      ...(j.customerId ? { customerId: j.customerId } : {}),
      debit: Number(j.credit || 0),
      credit: Number(j.debit || 0),
    })),
  );
  for (const l of s.lines) {
    if (l.service) continue;
    const p = db.products.find((p) => p.id === l.productId);
    if (!p) throw Error("صنف الفاتورة القديم غير موجود");
    const restoredQty = round(Number(p.qty) + Number(l.qty));
    p.cost =
      (Number(p.qty) * Number(p.cost || 0) +
        Number(l.qty) * Number(l.cost || 0)) /
      restoredQty;
    p.qty = restoredQty;
    db.stockMoves.push({
      ref: tag,
      date: s.date,
      productId: p.id,
      qty: Number(l.qty),
      cost: Number(l.cost || 0),
      type: "عكس بيع",
    });
  }
}
export function saveInvoice(input, draft, editRef = null) {
  const db = normalize(input),
    old = editRef ? db.sales.find((s) => s.ref === editRef) : null;
  if (editRef && !old) throw Error("الفاتورة غير موجودة");
  if (old && !active(old)) throw Error("لا يمكن تعديل فاتورة ملغاة");
  dateCheck(db, draft.date);
  if (old) {
    dateCheck(db, day(old.date));
    if (!draft.reason?.trim()) throw Error("اكتب سبب تعديل الفاتورة");
  }
  const customer = db.customers.find(
    (c) => c.id === draft.customerId && !c.inactive,
  );
  if (!customer) throw Error("اختر العميل");
  if (!Array.isArray(draft.lines) || !draft.lines.length)
    throw Error("أضف بنداً واحداً على الأقل");
  const revision = old ? Number(old.revision || 1) + 1 : 1;
  if (old) reverse(db, old, `${old.ref}-REV-${revision}`);
  const used = {};
  const lines = draft.lines.map((l) => {
    const p = db.products.find((p) => p.id === l.productId && !p.inactive);
    if (!p) throw Error("اختر صنفاً صالحاً");
    const qty = number(l.qty, "الكمية"),
      price = number(l.price, "السعر");
    if (qty <= 0) throw Error("الكمية يجب أن تكون أكبر من صفر");
    used[p.id] = (used[p.id] || 0) + qty;
    if (!p.service && used[p.id] > Number(p.qty))
      throw Error("المخزون غير كافٍ: " + p.name);
    const prior = old?.lines.find((x) => x.productId === p.id);
    return {
      productId: p.id,
      name: p.name,
      qty,
      price,
      cost: number(prior?.cost ?? p.cost ?? 0, "التكلفة"),
      service: !!p.service,
      total: round(qty * price),
    };
  });
  const subtotal = round(lines.reduce((n, l) => n + l.total, 0)),
    discount = number(draft.discount || 0, "الخصم");
  if (discount > subtotal) throw Error("الخصم أكبر من قيمة الفاتورة");
  const total = round(subtotal - discount);
  if (!["cash", "credit", "mixed"].includes(draft.payType))
    throw Error("طريقة الدفع غير صحيحة");
  const paid =
    draft.payType === "cash"
      ? total
      : draft.payType === "credit"
        ? 0
        : number(draft.paid || 0, "المسدد");
  if (paid > total) throw Error("المسدد أكبر من الفاتورة");
  const credit = round(total - paid),
    cost = round(lines.reduce((n, l) => n + l.qty * l.cost, 0)),
    ref = old?.ref || next(db, "sale", "INV-"),
    postingRef = old ? `${ref}-V${revision}` : ref;
  const beforeBalance = balance(db, customer.id);
  if (
    Number(customer.limit) > 0 &&
    round(beforeBalance + credit) > Number(customer.limit)
  )
    throw Error("الفاتورة تتجاوز حد ائتمان العميل");
  const rows = [
    { account: "العملاء", customerId: customer.id, debit: total, credit: 0 },
    { account: "المبيعات", debit: 0, credit: total },
  ];
  if (paid)
    rows.push(
      { account: "الصندوق", debit: paid, credit: 0 },
      { account: "العملاء", customerId: customer.id, debit: 0, credit: paid },
    );
  if (cost)
    rows.push(
      { account: "تكلفة المبيعات", debit: cost, credit: 0 },
      { account: "المخزون", debit: 0, credit: cost },
    );
  entry(db, postingRef, draft.date, "فاتورة بيع " + ref, rows);
  for (const l of lines)
    if (!l.service) {
      const p = db.products.find((p) => p.id === l.productId),
        remaining = round(Number(p.qty) - l.qty),
        remainingValue = Number(p.qty) * Number(p.cost || 0) - l.qty * l.cost;
      if (
        remainingValue < -0.01 ||
        (remaining === 0 && Math.abs(remainingValue) > 0.01)
      )
        throw Error(
          "التعديل لا يتوافق مع تكلفة المخزون الحالية؛ يلزم مراجعة حركة الصنف: " +
            p.name,
        );
      if (remaining > 0) p.cost = Math.max(0, remainingValue) / remaining;
      p.qty = remaining;
      db.stockMoves.push({
        ref: postingRef,
        date: draft.date + "T12:00:00",
        productId: l.productId,
        qty: -l.qty,
        cost: l.cost,
        type: "بيع",
      });
    }
  const sale = {
    ref,
    postingRef,
    revision,
    date: draft.date + "T12:00:00",
    customerId: customer.id,
    lines,
    subtotal,
    discount,
    total,
    paid: round(paid),
    credit,
    cost,
    payType: draft.payType,
    note: String(draft.note || ""),
    status: "معتمدة",
    updatedAt: new Date().toISOString(),
  };
  if (old) db.sales[db.sales.indexOf(old)] = sale;
  else db.sales.push(sale);
  audit(
    db,
    old ? "تعديل فاتورة" : "إنشاء فاتورة",
    ref,
    old,
    sale,
    draft.reason || "",
  );
  return { db, sale };
}
export function cancelInvoice(input, ref, reason) {
  const db = normalize(input),
    s = db.sales.find((x) => x.ref === ref);
  if (!s || !active(s)) throw Error("الفاتورة غير قابلة للإلغاء");
  if (!reason?.trim()) throw Error("اكتب سبب الإلغاء");
  dateCheck(db, day(s.date));
  const before = structuredClone(s);
  reverse(db, s, ref + "-CANCEL-" + Number(s.revision || 1));
  s.status = "ملغاة";
  audit(db, "إلغاء فاتورة", ref, before, s, reason);
  return db;
}
export function receipt(input, draft) {
  const db = normalize(input);
  dateCheck(db, draft.date);
  if (!db.customers.some((c) => c.id === draft.customerId && !c.inactive))
    throw Error("اختر العميل");
  const amount = number(draft.amount, "المبلغ");
  if (amount <= 0) throw Error("أدخل مبلغاً أكبر من صفر");
  const ref = next(db, "receipt", "REC-");
  entry(db, ref, draft.date, "سند قبض", [
    { account: "الصندوق", debit: amount, credit: 0 },
    {
      account: "العملاء",
      customerId: draft.customerId,
      debit: 0,
      credit: amount,
    },
  ]);
  db.receipts.push({ ...draft, ref, date: draft.date + "T12:00:00", amount });
  audit(db, "سند قبض", ref, null, draft, "");
  return db;
}
export function expense(input, draft) {
  const db = normalize(input);
  dateCheck(db, draft.date);
  const amount = number(draft.amount, "المبلغ");
  if (!draft.note?.trim() || amount <= 0)
    throw Error("أدخل وصفاً ومبلغاً صحيحاً");
  const ref = next(db, "expense", "EXP-");
  entry(db, ref, draft.date, draft.note, [
    { account: "المصروفات", debit: amount, credit: 0 },
    { account: "الصندوق", debit: 0, credit: amount },
  ]);
  db.expenses.push({ ...draft, amount, ref, date: draft.date + "T12:00:00" });
  audit(db, "مصروف", ref, null, draft, "");
  return db;
}
export function report(
  db,
  { from = "", to = "", customerId = "", productId = "" } = {},
) {
  const inside = (x) =>
    (!from || day(x.date) >= from) && (!to || day(x.date) <= to);
  const invoices = db.sales.filter(
    (s) =>
      active(s) &&
      inside(s) &&
      (!customerId || s.customerId === customerId) &&
      (!productId || s.lines.some((l) => l.productId === productId)),
  );
  const rows = invoices.map((s) => {
    const selected = s.lines.filter(
        (l) => !productId || l.productId === productId,
      ),
      gross = selected.reduce(
        (n, l) => n + Number(l.total ?? l.qty * l.price),
        0,
      ),
      share = Number(s.subtotal) ? gross / Number(s.subtotal) : 1,
      net = round(Number(s.total) * share),
      cost = round(
        selected.reduce((n, l) => n + Number(l.qty) * Number(l.cost || 0), 0),
      );
    return {
      ...s,
      net,
      selectedCost: cost,
      units: selected.reduce((n, l) => n + Number(l.qty), 0),
      selectedPaid: round(Number(s.paid) * share),
    };
  });
  const sum = (f) => round(rows.reduce((n, r) => n + f(r), 0)),
    net = sum((r) => r.net),
    cost = sum((r) => r.selectedCost),
    instant = sum((r) => r.selectedPaid),
    receipts = productId
      ? null
      : round(
          db.receipts
            .filter(
              (r) => inside(r) && (!customerId || r.customerId === customerId),
            )
            .reduce((n, r) => n + Number(r.amount), 0),
        );
  const costs =
    customerId || productId
      ? null
      : round(
          db.expenses.filter(inside).reduce((n, r) => n + Number(r.amount), 0),
        );
  return {
    rows,
    net,
    cost,
    grossProfit: round(net - cost),
    margin: net ? round(((net - cost) / net) * 100) : 0,
    instant,
    receipts,
    collections: receipts === null ? null : round(instant + receipts),
    expenses: costs,
    netProfit: costs === null ? null : round(net - cost - costs),
    creditSales: round(net - instant),
    units: sum((r) => r.units),
  };
}
export function ledger(db, cid, { from = "", to = "" } = {}) {
  const all = db.journal
    .filter((j) => j.account === "العملاء" && j.customerId === cid)
    .map((j, i) => ({ ...j, order: i }))
    .sort(
      (a, b) =>
        String(a.date).localeCompare(String(b.date)) || a.order - b.order,
    );
  const opening = round(
    all
      .filter((j) => from && day(j.date) < from)
      .reduce((n, j) => n + Number(j.debit || 0) - Number(j.credit || 0), 0),
  );
  let running = opening;
  const rows = all
    .filter((j) => (!from || day(j.date) >= from) && (!to || day(j.date) <= to))
    .map((j) => {
      running = round(running + Number(j.debit || 0) - Number(j.credit || 0));
      return { ...j, balance: running };
    });
  return { opening, rows, closing: running };
}
