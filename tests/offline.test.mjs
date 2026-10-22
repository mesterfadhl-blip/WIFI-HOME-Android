import test from "node:test";
import assert from "node:assert/strict";
import { cleanOfflineImport } from "../offline/migration.mjs";
import { emptyDB, balance, cash } from "../web/core.mjs";
function fixture() {
  const d = emptyDB();
  d.customers = [
    { id: "c", name: "عميل أساسي" },
    { id: "V47-C1", name: "شركة الأمل - تجربة" },
  ];
  d.products = [
    { id: "p", name: "صنف أساسي", qty: 0, cost: 0, price: 100 },
    { id: "V47-P1", name: "كرت 100 - تجربة", qty: 100, cost: 70, price: 100 },
  ];
  d.sales = [
    {
      ref: "V47-INV-1",
      customerId: "V47-C1",
      demo: true,
      lines: [{ productId: "V47-P1" }],
    },
  ];
  d.journal = [
    {
      ref: "V47-INV-1",
      account: "العملاء",
      customerId: "V47-C1",
      debit: 6000,
      credit: 0,
    },
    { ref: "V47-INV-1", account: "المبيعات", debit: 0, credit: 6000 },
    { ref: "REAL", account: "الصندوق", debit: 9000, credit: 0 },
    {
      ref: "REAL",
      account: "رأس المال والأرصدة الافتتاحية",
      debit: 0,
      credit: 9000,
    },
  ];
  d.users = [{ password: "should-not-copy" }];
  return d;
}
test("local import removes verified demo, preserves cash and excludes accounts", () => {
  const r = cleanOfflineImport({ data: fixture() });
  assert.equal(r.db.customers.length, 1);
  assert.equal(r.db.products.length, 1);
  assert.equal(r.db.sales.length, 0);
  assert.equal(cash(r.db), 9000);
  assert.equal(balance(r.db, "c"), 0);
  assert.equal(r.db.users, undefined);
  assert.equal(r.removedCustomers, 1);
});
test("non-demo activity linked to trial identity is rejected", () => {
  const d = fixture();
  d.sales[0].demo = false;
  assert.throws(() => cleanOfflineImport({ data: d }), /غير تجريبية/);
});
test("unbalanced backup rejected without altering input", () => {
  const d = fixture();
  d.journal.at(-1).credit = 1;
  const before = JSON.stringify(d);
  assert.throws(() => cleanOfflineImport(d), /غير متوازنة/);
  assert.equal(JSON.stringify(d), before);
});
test("own portable backup keeps audit history", () => {
  const d = emptyDB();
  d.audit = [{ action: "تعديل بسبب موثق" }];
  assert.equal(
    cleanOfflineImport({ format: "WIFI-HOME-OFFLINE", data: d }).db.audit
      .length,
    1,
  );
});
