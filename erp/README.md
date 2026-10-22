# WIFI HOME ERP — transactional sales foundation

This is a new server-backed application under `erp/`. It does not load the Android HTML or the earlier localStorage workspace, and does not auto-import or overwrite either dataset. It uses one shared SQLite database, integer minor-unit money, server-authorized sessions, transactional posting, immutable posted documents and separate document templates. Currency: YER; no tax.

## Run locally

Python 3.11+; no third-party runtime dependencies.

```sh
cd /workspace/WIFI-HOME-Android
ERP_DATABASE=/workspace/.cloud-setup/erp/data.sqlite3 PORT=8081 python -m erp.server
```

The development server binds to 127.0.0.1. Open its HTTP address in a local development browser. First visit creates the administrator. There is no default password or demo data. Configure the first administrator before exposing a new deployment publicly. The login form requires at least eight characters. Subsequent users are created by the administrator with sales or accountant roles. Test database files used during development are outside the checkout and are never deployed.

The WSGI factory is `erp.server:create_app()`. For a production deployment, use a supported WSGI server behind an HTTPS reverse proxy, set `ERP_DATABASE` to a private path on a persistent volume and `ERP_COOKIE_SECURE=1`. Keep the same database volume across restarts. This is a single-company, single-server SQLite foundation. A production hosting configuration, ongoing operational backups and a security review are not established by the local checks. Do not run multiple independent copies with separate database files and expect synchronization.

**The static Netlify Drop site cannot run this server or share its database.** The existing Netlify site remains unchanged. A server hosting target and durable storage are needed for a public deployment. Do not upload the database or Python source as static website files.

## Workflow

1. Create customer and product records. Product starting stock is posted against opening equity. Service costs post against service payables, not stock.
2. Save a draft invoice. Drafts reserve no stock, create no journal entries and may be edited. A version check rejects stale saves.
3. Post the saved draft. A single immediate database transaction checks stock across duplicate product lines, snapshots costs, issues stock and posts balanced receivable/revenue/cash/cost entries. Repeated posting is rejected.
4. Posted invoices are immutable. Admin/accountant can request amendment with a reason; this creates a linked draft with a new document number. The original remains effective until replacement posting succeeds. Replacement atomically reverses original accounting/stock and posts the revised invoice. Failure leaves the original effective.
5. Accounting cancellation keeps the original invoice and adds reversal entries. It does not delete receipts or customer records. Repeated cancellation is rejected.
6. Receipts are standalone ledger movements. Current customer balance includes all posted debit/credit movements. Invoice payment labels refer to payment at issue; receipts are not allocated against individual invoices yet.

Sales roles cannot administer users/products or reverse posted documents. Session tokens are generated cryptographically, stored hashed server-side, and delivered in HttpOnly SameSite cookies; mutations also require a session CSRF token. Login attempts are throttled per user/address. The frontend stores neither credentials nor financial records in localStorage.

## Professional document outputs

Authenticated `/print/invoices/<id>`, `/print/statement?customer=...&from=...&to=...`, and `/print/sales?from=...&to=...` are independent document layouts. They do not print the dashboard or filters. A4 margins, fixed column widths, repeated table headings, numeric alignment, subtotals/totals, status, and page counters are specified in print CSS. The print action opens the browser's PDF/printer dialog; server-side automatic PDF generation is not part of this milestone. CSV export is available at `/export/sales.csv` with the same date/customer filters.

Sales reports include only effective posted invoices and separate net sales, recorded costs, gross profit and receipts during the period. Gross profit is not labelled net profit. Customer statements include opening balance, all movements including reversals, debit/credit totals and closing balance. Product quantities are whole units in this milestone.

## Backup and recovery

```sh
python -m erp.backup /path/to/data.sqlite3 /path/to/backups/new-backup.sqlite3
```

This uses SQLite's consistent online backup API and integrity-checks the new file. It refuses overwriting an existing destination. Store backups off the server, protected like the original database because they contain financial data, password hashes and sessions. To restore, stop application processes, restore the database to a separate verified path, set `ERP_DATABASE` to that path and start the service. Backup creation and restored balances were tested; no automatic scheduler/off-site destination has been configured.

## Verify

```sh
python -m unittest discover -s tests -p test_erp_service.py -v
```

Tests cover draft isolation, exact journal balances, posting idempotency, duplicate-line stock validation, amendments and rollback, cancellation with unrelated receipts, stale-save detection, dates/amount validation, session/CSRF/role enforcement, login throttling, backup consistency, service accounting, shared reads, period receipts and independent document rendering.

An actual Chromium browser test created an administrator/customer/product, saved and posted an invoice, viewed shared data in a second mobile tab, and generated invoice, statement and sales PDFs. A 70-line invoice produced a multi-page A4 PDF. This validates the initial sales slice, not a complete ERP.

## Remaining modules

Purchasing and supplier settlement, stock receipts/warehouse transfers and valuation policy for later receipts, returns/credit notes, invoice-level settlement allocation, operating expenses and full financial statements, fiscal-period locks, dedicated settings and backup administration, richer permission scopes and production hosting still need implementation. Do not treat this milestone as a finished ERP or an audited accounting package. The schema and transactional service are the foundation for those modules; the old system is not used as their design reference.
