import { normalize, round } from "../web/core.mjs";

export function cleanOfflineImport(packageData) {
  const input = packageData.database || packageData.data || packageData;
  const source = normalize(input);
  const demoRefs = new Set(["V47-STK"]);
  for (const key of ["sales", "receipts", "expenses", "stockMoves"])
    for (const row of source[key] || [])
      if (row.demo === true && row.ref) demoRefs.add(row.ref);
  const reservedCustomers = {
    "V47-C1": "شركة الأمل - تجربة",
    "V47-C2": "مؤسسة النجاح - تجربة",
  };
  const reservedProducts = {
    "V47-P1": "كرت 100 - تجربة",
    "V47-P2": "كرت 200 - تجربة",
  };
  const customers = new Set(
    source.customers
      .filter((c) => c.demo === true || reservedCustomers[c.id] === c.name)
      .map((c) => c.id),
  );
  const products = new Set(
    source.products
      .filter((p) => p.demo === true || reservedProducts[p.id] === p.name)
      .map((p) => p.id),
  );
  // Do not silently discard actual activity that later used a demo identity.
  for (const s of source.sales)
    if (s.demo !== true && !demoRefs.has(s.ref)) {
      if (
        customers.has(s.customerId) ||
        s.lines.some((l) => products.has(l.productId))
      )
        throw Error(
          "توجد عملية غير تجريبية مرتبطة بسجل تجربة؛ تحتاج مراجعة قبل الاستيراد.",
        );
    }
  for (const j of source.journal)
    if (
      !demoRefs.has(j.ref) &&
      j.demo !== true &&
      j.account === "العملاء" &&
      customers.has(j.customerId)
    )
      throw Error("يوجد رصيد غير تجريبي لعميل تجربة؛ توقف الاستيراد للمراجعة.");
  const db = {
    customers: source.customers.filter((c) => !customers.has(c.id)),
    products: source.products.filter((p) => !products.has(p.id)),
    sales: source.sales.filter((s) => s.demo !== true && !demoRefs.has(s.ref)),
    receipts: source.receipts.filter(
      (r) => r.demo !== true && !demoRefs.has(r.ref),
    ),
    expenses: source.expenses.filter(
      (r) => r.demo !== true && !demoRefs.has(r.ref),
    ),
    journal: source.journal.filter(
      (r) => r.demo !== true && !demoRefs.has(r.ref),
    ),
    stockMoves: source.stockMoves.filter(
      (r) => r.demo !== true && !demoRefs.has(r.ref),
    ),
    audit: packageData.format === "WIFI-HOME-OFFLINE" ? source.audit : [],
    dailyClosings: source.dailyClosings.filter((c) => c.demo !== true),
    settings: source.settings,
    seq: source.seq,
  };
  for (const field of [
    "suppliers",
    "purchases",
    "supplierPayments",
    "purchaseReturns",
  ])
    if (Array.isArray(source[field])) db[field] = source[field];
  const ids = new Set();
  for (const c of db.customers) {
    if (!c.id || !c.name || ids.has(c.id))
      throw Error("اسم أو معرف عميل غير صالح أو مكرر");
    ids.add(c.id);
  }
  const pids = new Set();
  for (const p of db.products) {
    if (
      !p.id ||
      !p.name ||
      pids.has(p.id) ||
      !Number.isFinite(Number(p.qty)) ||
      Number(p.qty) < 0
    )
      throw Error("صنف غير صالح أو رصيد مخزون سالب");
    pids.add(p.id);
  }
  for (const s of db.sales)
    if (!ids.has(s.customerId) || s.lines.some((l) => !pids.has(l.productId)))
      throw Error("الفاتورة مرتبطة بعميل أو صنف مفقود");
  const refs = new Map();
  for (const j of db.journal) {
    for (const k of ["debit", "credit"])
      if (!Number.isFinite(Number(j[k] || 0)) || Number(j[k] || 0) < 0)
        throw Error("مبلغ قيد غير صالح");
    if (j.account === "العملاء" && !ids.has(j.customerId))
      throw Error("قيد مرتبط بعميل مفقود");
    refs.set(
      j.ref,
      round(
        (refs.get(j.ref) || 0) + Number(j.debit || 0) - Number(j.credit || 0),
      ),
    );
  }
  if ([...refs.values()].some((n) => n !== 0))
    throw Error("قيود النسخة غير متوازنة؛ لا يمكن اعتمادها");
  for (const s of db.sales) {
    s.postingRef = s.postingRef || s.ref;
    s.revision = s.revision || 1;
  }
  return {
    db: normalize(db),
    removedCustomers: customers.size,
    removedProducts: products.size,
    removedSales: source.sales.length - db.sales.length,
  };
}
