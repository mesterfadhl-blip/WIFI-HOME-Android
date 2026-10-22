# WIFI HOME ERP — sales, purchasing, stock and accounting

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

Sales reports include effective posted invoices and negative posted credit notes, using each document date. They separate net sales after returns, recorded costs, gross profit and receipts during the period. Gross profit is not labelled net profit. Customer statements include opening balance, all movements including reversals, debit/credit totals and closing balance. Product quantities are whole units in this milestone.

## Backup and recovery

```sh
python -m erp.backup /path/to/data.sqlite3 /path/to/backups/new-backup.sqlite3
```

This uses SQLite's consistent online backup API and integrity-checks the new file. It refuses overwriting an existing destination. Store backups off the server, protected like the original database because they contain financial data, password hashes and sessions. To restore, stop application processes, restore the database to a separate verified path, set `ERP_DATABASE` to that path and start the service. Backup creation and restored balances were tested; no automatic scheduler/off-site destination has been configured.

## Verify

```sh
python -m unittest discover -s tests -p 'test_erp*.py' -v
```

Tests cover draft isolation, exact journal balances, posting idempotency, duplicate-line stock validation, amendments and rollback, cancellation with unrelated receipts, stale-save detection, dates/amount validation, session/CSRF/role enforcement, login throttling, backup consistency, service accounting, shared reads, period receipts and independent document rendering.

An actual Chromium browser test created an administrator/customer/product, saved and posted an invoice, viewed shared data in a second mobile tab, and generated invoice, statement and sales PDFs. A 70-line invoice produced a multi-page A4 PDF. This validates the initial sales slice, not a complete ERP.

## Purchasing, stock and supplier cycle

Create a supplier, then a purchase draft with stock items, quantities, unit costs and optional payment. Posting atomically receives stock at purchase cost and posts inventory against supplier payable plus the issue payment. Supplier payments are separate audited cash/payable movements. Purchase cancellation is allowed only before any later stock movement for the purchased items; it reverses the original entries and keeps unrelated payments. Purchase documents and supplier statements have independent A4 templates.

Inventory stores **exact total value in integer minor units**, independently of the displayed rounded average unit cost. Each issue removes an allocated portion of total value; issuing the last units removes the exact residual. Receipts and sale returns recalculate the displayed average. Backdated stock operations before a later movement are rejected rather than silently restating historical cost. Quantities are whole units; there is one stock pool, not multiple warehouses.

## Credit notes and returns

An accountant/admin selects lines from an effective posted invoice. The server checks the original line IDs and remaining returnable quantities. Credit amounts include the original allocated invoice discount, and returned cost is the original actual issue cost. Largest-remainder allocation and cumulative partial-return calculations preserve every minor unit across full returns. A return may credit the customer account and optionally refund part of its value in cash; it cannot refund more than the credit. Original invoices remain unchanged and link to separate credit notes.

A cancelled return reverses its own entries and stock; later stock movements block reversal when it would change valuations. An invoice with effective returns cannot be cancelled or amended until those returns are reversed. Retried requests from the UI carry a key; returns, expenses, supplier payments and capital funding reject reuse with a different payload and return the same result for an identical retry.

## Accounting and period close

Operating expenses post against cash. Admin-only capital funding posts cash against opening equity, never against sales revenue. The financial workspace separates sales, returns, net sales, recorded cost, gross profit, operating expense and net result. The cumulative trial review is explicitly labelled through its end date. Current inventory valuation is explicitly labelled current, not historical. The independent financial document prints profit/loss and the cumulative trial review.

Only an admin can close through a date with a reason. Journal posting, stock opening, draft saving/posting, reversals and settlement operations respect the close. Close records are audited. There is no automatic reopen or direct delete action.

## Upgrade and regression verification

Back up the database before upgrading. Startup adds supplier/purchase/return/expense/period/request tables and stock/line valuation columns. Legacy stock value is initialized from existing quantity and cost only once. Existing invoice discounts are allocated to original lines, and original recorded costs are preserved. User version 2 and query indexes are saved. Repeat startup and balance preservation are tested; startup does not import earlier localStorage datasets or delete existing documents.

The current suite contains 24 server tests. A browser cycle exercised supplier creation, purchase draft/post, weighted-average stock, sale, partial return and expense. Its checked values were: net sales 95.00 YER, cost 50.00, gross profit 45.00, expense 10.00 and net result 35.00. It also verified mobile financial reports and generated four additional A4 PDFs. Synthetic review records are kept in separate test databases outside the checkout.

## Remaining modules and deployment

Purchase orders and separate receiving, supplier purchase returns, warehouse transfers, invoice-level settlement allocation, bank reconciliation, balance sheet and statutory reporting, controlled period reopening, more granular permissions, automated off-site backups and production hosting still need implementation. This is not a completed or independently audited ERP. The static Netlify Drop deployment remains the old application; the Python service and durable database require server hosting.

The browser scenario is saved as `tests/browser_erp_operations.py`. It requires Playwright/Chromium in the test environment and an **empty dedicated** database server. It refuses to initialize a server that already has users. Set `ERP_TEST_URL` and `ERP_REVIEW_DIR` to select the test endpoint and artifact directory. It is not part of the application's runtime dependencies.
