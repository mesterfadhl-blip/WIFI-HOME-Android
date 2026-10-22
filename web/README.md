# WIFI-HOME: new sales and reporting workspace

This is a new local browser application, not a visual patch over the legacy dashboard. Currency: YER; no tax. No package installation or build is required.

## Run

From the repository: `python -m http.server 8766 --directory web`, then open http://127.0.0.1:8766. For hosting, upload the contents of `web/` so `index.html`, `app.mjs`, `core.mjs` and `style.css` are at the site root. Netlify serves `.mjs` as JavaScript. Use HTTPS for `crypto.randomUUID` and production hosting.

## Data and migration

The new application uses localStorage key `wifiHomeERP.v1`. It does not write to the legacy `cardFinanceV2` key and does not create demonstration transactions. On the same origin, Settings can copy legacy data. Between origins, export a JSON backup from the old application and import it in Settings. Supported wrappers: `data`, `database`, and a direct database object. Existing legacy demonstration entries are not silently deleted during import. Review imported opening balances and records.

Import replaces the new application's data after confirmation and triggers a downloadable backup first. Keep this backup outside the browser. Browsers control whether downloads are retained; do not assume automatic durable recovery. Storage write failures leave in-memory committed data unchanged. Conflicting writes from another tab are rejected until reload.

## Implemented

- Separate sales register, invoice editor, printable invoice, customer list and ledger, inventory, cash, reporting and data settings.
- Cash, credit and partial settlement; quantities and price overrides; invoice discount; date and customer.
- Invoice revision with required reason, unchanged invoice number, audit before/after, reversal of old journals and stock, posting of replacement, and accounting cancellation.
- Validation of stock across repeated product lines, finite/nonnegative amounts, overpayments, closed dates and customer credit limits.
- Receipt and expense posting; stock receipts against suppliers with average cost; customer opening balances.
- Period/customer/product filters; gross and net profit separated; customer/product/day aggregates; opening/closing customer ledger; CSV for the displayed report and printable views.
- Historical stock edits preserve the recorded cost and remaining inventory value; incompatible valuation changes are rejected for review rather than silently creating value differences.

## Calculations and boundaries

Net sales = line values minus invoice discount, excluding cancelled invoices. Gross profit = net sales minus recorded cost of the selected lines. Net period result additionally deducts period operating expenses. Shared expenses and unallocated receipts are not attributed to individual products/customers. Invoice upfront payment is distinct from later receipts and from current customer account balance. No misleading collection percentage is calculated. Product filtering apportions invoice discount and upfront payment by pre-discount line value; this is disclosed on screen. Receipts are not allocated to invoices yet, so an invoice's credit amount is labelled "credit at sale", not "current invoice balance".

This is an initial functional ERP workspace, not a complete ERP or a deployment with server security. No shared database, server authentication, enforced user permissions, automatic off-device backups, invoice-level receipt allocations, purchase cycle, returns cycle, or period close/reopen UI has been added. Imported daily closes are respected. Do not treat this as an audited accounting package or assume data synchronization across devices.

## Validation

`node --test tests/erp.test.mjs` from repository root covers sales/discounts, inventory, balanced journals, editing, customer reassignment, unrelated receipts, cancellation, insufficient stock and duplicate lines, invalid dates/amounts, closed days, credit limits, period receipts, product allocation, profit and historical cost changes.

Browser validation at 390x844 and 1366x900 covers invoice creation/editing, persisted totals and stock, navigation, and report rendering. This does not establish every business rule or replace review with the owner's real examples.
