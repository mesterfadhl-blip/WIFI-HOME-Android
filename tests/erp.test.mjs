import test from "node:test";
import assert from "node:assert/strict";
import {
  emptyDB,
  saveInvoice,
  cancelInvoice,
  balance,
  cash,
  receipt,
  expense,
  report,
  ledger,
} from "../web/core.mjs";
function fixture() {
  const d = emptyDB();
  d.customers = [
    { id: "c1", name: "عميل أول", limit: 0 },
    { id: "c2", name: "عميل ثان", limit: 0 },
  ];
  d.products = [
    { id: "p1", name: "كرت", qty: 100, cost: 40, price: 100 },
    { id: "p2", name: "اشتراك", service: true, qty: 0, cost: 10, price: 50 },
  ];
  return d;
}
const draft = (more = {}) => ({
  date: "2026-10-22",
  customerId: "c1",
  payType: "mixed",
  paid: 50,
  discount: 10,
  lines: [{ productId: "p1", qty: 2, price: 100 }],
  ...more,
});
function balanced(db) {
  assert.equal(
    db.journal.reduce((a, j) => a + j.debit - j.credit, 0),
    0,
  );
}
test("new sale has exact discount, stock, receivable, cash and balanced ledger", () => {
  const original = fixture(),
    { db, sale } = saveInvoice(original, draft());
  assert.equal(sale.total, 190);
  assert.equal(sale.credit, 140);
  assert.equal(sale.cost, 80);
  assert.equal(db.products[0].qty, 98);
  assert.equal(balance(db, "c1"), 140);
  assert.equal(cash(db), 50);
  assert.equal(original.products[0].qty, 100);
  assert.equal(original.sales.length, 0);
  balanced(db);
});
test("editing retains reference, reverses old effects, preserves unrelated receipts and audit", () => {
  let { db, sale } = saveInvoice(fixture(), draft());
  db = receipt(db, { date: "2026-10-22", customerId: "c1", amount: 30 });
  const edited = saveInvoice(
    db,
    draft({
      paid: 100,
      discount: 0,
      lines: [{ productId: "p1", qty: 3, price: 100 }],
      reason: "تصحيح الكمية",
    }),
    sale.ref,
  );
  assert.equal(edited.sale.ref, sale.ref);
  assert.equal(edited.sale.revision, 2);
  assert.equal(edited.db.sales.length, 1);
  assert.equal(edited.db.products[0].qty, 97);
  assert.equal(balance(edited.db, "c1"), 170);
  assert.equal(cash(edited.db), 130);
  assert.equal(edited.db.audit.at(-1).before.total, 190);
  balanced(edited.db);
});
test("moving invoice to different customer removes old customer charge only", () => {
  let { db, sale } = saveInvoice(fixture(), draft());
  db = receipt(db, { date: "2026-10-22", customerId: "c1", amount: 20 });
  const r = saveInvoice(
    db,
    draft({ customerId: "c2", payType: "credit", reason: "تصحيح العميل" }),
    sale.ref,
  );
  assert.equal(balance(r.db, "c1"), -20);
  assert.equal(balance(r.db, "c2"), 190);
  assert.equal(cash(r.db), 20);
  balanced(r.db);
});
test("cancel latest revision restores stock and financial effects once", () => {
  let r = saveInvoice(fixture(), draft());
  r = saveInvoice(
    r.db,
    draft({
      lines: [{ productId: "p1", qty: 5, price: 100 }],
      reason: "تصحيح",
    }),
    r.sale.ref,
  );
  const db = cancelInvoice(r.db, r.sale.ref, "خطأ");
  assert.equal(db.products[0].qty, 100);
  assert.equal(balance(db, "c1"), 0);
  assert.equal(cash(db), 0);
  assert.equal(report(db).net, 0);
  assert.throws(() => cancelInvoice(db, r.sale.ref, "مرة ثانية"));
  balanced(db);
});
test("repeated product lines cannot oversell and rejected edits are atomic", () => {
  const original = fixture();
  assert.throws(
    () =>
      saveInvoice(
        original,
        draft({
          lines: [
            { productId: "p1", qty: 60, price: 100 },
            { productId: "p1", qty: 50, price: 100 },
          ],
        }),
      ),
    /المخزون/,
  );
  assert.equal(original.products[0].qty, 100);
  let r = saveInvoice(original, draft());
  const snapshot = JSON.stringify(r.db);
  assert.throws(() =>
    saveInvoice(r.db, draft({ discount: 9999, reason: "خطأ" }), r.sale.ref),
  );
  assert.equal(JSON.stringify(r.db), snapshot);
});
test("validation rejects overpayment, negative, NaN, empty lines and closed dates", () => {
  const db = fixture();
  for (const patch of [
    { paid: 1000 },
    { discount: -1 },
    { lines: [] },
    { date: "2026-02-30" },
    { lines: [{ productId: "p1", qty: "oops", price: 100 }] },
  ])
    assert.throws(() => saveInvoice(db, draft(patch)));
  db.dailyClosings = [{ date: "2026-10-22" }];
  assert.throws(() => saveInvoice(db, draft()), /مغلق/);
});
test("report distinguishes period receipts from original invoice payments", () => {
  let r = saveInvoice(
    fixture(),
    draft({ date: "2026-09-22", payType: "credit" }),
  );
  r.db = receipt(r.db, { date: "2026-10-22", customerId: "c1", amount: 100 });
  const reportNow = report(r.db, { from: "2026-10-01", to: "2026-10-31" });
  assert.equal(reportNow.net, 0);
  assert.equal(reportNow.instant, 0);
  assert.equal(reportNow.receipts, 100);
  assert.equal(reportNow.collections, 100);
  const l = ledger(r.db, "c1", { from: "2026-10-01", to: "2026-10-31" });
  assert.equal(l.opening, 190);
  assert.equal(l.closing, 90);
});
test("product filter apportions discounts and avoids attributing unallocated receipts", () => {
  const r = saveInvoice(
    fixture(),
    draft({
      discount: 20,
      paid: 80,
      lines: [
        { productId: "p1", qty: 1, price: 100 },
        { productId: "p2", qty: 2, price: 50 },
      ],
    }),
  );
  const p = report(r.db, { productId: "p2" });
  assert.equal(p.net, 90);
  assert.equal(p.cost, 20);
  assert.equal(p.grossProfit, 70);
  assert.equal(p.instant, 40);
  assert.equal(p.receipts, null);
  assert.equal(p.expenses, null);
  assert.equal(p.netProfit, null);
  assert.equal(r.db.products[1].qty, 0);
});
test("net profit deducts period expenses without changing gross margin", () => {
  let r = saveInvoice(fixture(), draft());
  r.db = expense(r.db, { date: "2026-10-22", note: "تشغيل", amount: 20 });
  const p = report(r.db);
  assert.equal(p.grossProfit, 110);
  assert.equal(p.netProfit, 90);
  assert.equal(p.expenses, 20);
  balanced(r.db);
});
test("credit limits check projected balance and edits restore availability first", () => {
  let db = fixture();
  db.customers[0].limit = 150;
  let r = saveInvoice(db, draft());
  assert.throws(() => saveInvoice(r.db, draft()), /حد ائتمان/);
  const revised = saveInvoice(r.db, draft({ reason: "تصحيح" }), r.sale.ref);
  assert.equal(balance(revised.db, "c1"), 140);
});
test("historical edit preserves value when stock unit cost changes later", () => {
  let r = saveInvoice(fixture(), draft());
  r.db.products[0].cost = 60;
  const originalStockValue = 98 * 60;
  const edited = saveInvoice(
    r.db,
    draft({
      lines: [{ productId: "p1", qty: 3, price: 100 }],
      reason: "تعديل تاريخي",
    }),
    r.sale.ref,
  );
  assert.equal(edited.sale.cost, 120);
  assert.equal(edited.db.products[0].qty, 97);
  assert.equal(
    roundValue(edited.db.products[0].qty * edited.db.products[0].cost),
    originalStockValue + 80 - 120,
  );
  function roundValue(n) {
    return Math.round(n * 100) / 100;
  }
});
