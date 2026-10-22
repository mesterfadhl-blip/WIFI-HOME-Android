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
