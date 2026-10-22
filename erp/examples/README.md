# Review samples

These are demonstration outputs rendered from the new server-backed ERP, using synthetic test records marked as review/test data. They are not customer invoices or live accounting records.

- invoice.pdf: posted sale, gross 200.00 YER, discount 10.00, net 190.00, issue payment 50.00, issue credit 140.00.
- statement.pdf: matching customer ledger with debit/credit movements and final balance 140.00 YER.
- sales-report.pdf: net sale 190.00 YER, recorded cost 80.00 and gross profit 110.00; no operating-expense/net-profit claim.
- invoice-preview.png: first page rasterized from the actual invoice PDF.
- workspace-preview.png: server-backed invoice form and workflow toolbar in Chromium.

Print CSS uses an independent A4 template rather than dashboard screenshots. A separate 70-line invoice was also rendered and checked as a multi-page PDF in development. These sample PDFs were generated via Chromium's print renderer; the application exposes independent HTML documents and a browser print action.

## Purchasing, return and accounting cycle

Additional samples use a fresh, dedicated test database, not the original invoice sample database above. Test capital cash funding is 10,000.00 YER. Opening stock is 100 units at 40.00 YER; purchase is 100 units at 60.00, paid 1,000.00, giving 200 units at 50.00 weighted cost. A sale of two units at 100.00 has a 10.00 invoice discount and 50.00 issue payment. One unit is returned for a 95.00 credit note, with 20.00 refunded. An operating expense of 10.00 is posted.

- purchase.pdf: 6,000.00 purchase and stock receipt; 1,000.00 paid at issue.
- credit-note.pdf: 95.00 credit, 20.00 cash refund, 75.00 customer balance reduction.
- supplier-statement.pdf: 5,000.00 payable after the purchase issue payment.
- profit-trial-balance.pdf: net sales 95.00, net recorded cost 50.00, gross profit 45.00, expense 10.00, net result 35.00; cumulative debit/credit totals balance.
- finance-workspace.png: actual browser financial workspace for this cycle.

The remaining inventory is 199 units with an exact value of 9,950.00 YER. Sample data is explicitly synthetic; none of these outputs is a live invoice or assertion that the public Netlify site has been updated.

## Version 3 review cycle

These samples use another fresh synthetic database, not the previous cycles. Opening inventory is 100 units at 40.00 YER in the main warehouse. A transfer sends 20 units (800.00 YER) to a branch warehouse without changing the global stock asset. A sale issues two units from that branch, totals 190.00 after discount and records 50.00 cash at issue. A bank customer receipt of 100.00 is allocated to that invoice, leaving an actual invoice balance of 40.00. The test bank has a 5,000.00 opening balance and its 100.00 receipt is matched to an imported statement ending at 5,100.00.

- settled-invoice.pdf: original issue amounts plus a separate current-settlement section with 100.00 allocated and 40.00 remaining.
- receivable-aging.pdf: one invoice due for 40.00; unapplied receipts 0.00; net receivable 40.00.
- warehouse-transfer.pdf: 20 units valued at 800.00 between named warehouses; no change of ownership.
- bank-reconciliation.pdf: matched deposit, statement closing and book closing 5,100.00; pending amount 0.00.
- settlements-workspace.png: real browser capture of the allocation/aging workspace.

After the sale, warehouse quantities are 80 and 18 units, total value 3,920.00 YER. These documents demonstrate test output only; the public static website remains unchanged.

Version-four review documents: `financial-position.pdf`, `goods-receipt.pdf`, and `supplier-return.pdf`. All records and balances are synthetic, generated in a separate temporary database by `scripts/check_enterprise_browser.py`; they are not the user's imported customers or live accounts.
