# Review samples

These are demonstration outputs rendered from the new server-backed ERP, using synthetic test records marked as review/test data. They are not customer invoices or live accounting records.

- invoice.pdf: posted sale, gross 200.00 YER, discount 10.00, net 190.00, issue payment 50.00, issue credit 140.00.
- statement.pdf: matching customer ledger with debit/credit movements and final balance 140.00 YER.
- sales-report.pdf: net sale 190.00 YER, recorded cost 80.00 and gross profit 110.00; no operating-expense/net-profit claim.
- invoice-preview.png: first page rasterized from the actual invoice PDF.
- workspace-preview.png: server-backed invoice form and workflow toolbar in Chromium.

Print CSS uses an independent A4 template rather than dashboard screenshots. A separate 70-line invoice was also rendered and checked as a multi-page PDF in development. These sample PDFs were generated via Chromium's print renderer; the application exposes independent HTML documents and a browser print action.
