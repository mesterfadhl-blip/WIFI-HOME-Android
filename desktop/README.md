# Native Windows desktop package

This distribution preserves the Python ERP and `erp/static/` interface. It starts a local native Python server and opens the default browser, with no WebAssembly, HTML interpreter or dependency installation at the user's computer. It supports Windows 10/11 x64. Runtime binaries come from the official Python Software Foundation NuGet package; the build verifies its published SHA512 and AMD64 PE header and retains its license. The runtime includes the VC runtime, OpenSSL and SQLite libraries. No signature/TLS/security verification is disabled.

`START-WIFI-HOME.bat` runs the bundled Python with `-I -S`, then `desktop_start.py` explicitly selects the package's source directory. The application has no third-party requirements in desktop mode. Source `erp/production.py` and its optional S3 dependencies are not used. `BACKUP-DATA.bat` creates a consistent live SQLite backup beside the extracted application.

The private seed is in `seed/DATABASE.sqlite3`. On first run it is copied to `%LOCALAPPDATA%\WIFI-HOME-ERP\data.sqlite3`. Existing financial/master data always wins and is never replaced by the seed. A previous installation that is empty except for authentication/audit/default warehouse can receive the seed through one writer transaction after a consistent recovery backup, preserving its users/password hashes and audit. The merge rechecks emptiness under the write lock and defers/checks foreign keys. It does not swap a live database file or delete its WAL. Unknown existing records prevent automatic seeding. Additive migrations occur after backup.

A separate SQLite lock prevents duplicate desktop services. A subsequent start verifies the running local instance with an ephemeral nonce and reopens its browser address. The server binds only to `127.0.0.1`, rejects other Host/Origin headers, and keeps standard application session and CSRF checks. The data folder/backup files are private user files; no application data are uploaded to GitHub.

Close the console to stop the service. SQLite keeps committed data. Each subsequent launch creates a recovery snapshot, without deleting older backups. An error leaves details in `last-start-error.txt`; corruption/incompatible seeds stop startup instead of replacing financial data.

## Build privately

`scripts/build_windows_desktop.py` accepts a freshly verified runtime-info JSON, a private seed DB with no preconfigured users and a **new directory outside the repository**. The runtime-info holds the official NuGet URL, version, publisher and published SHA512 collected through NuGet's HTTPS metadata. Keep the `.nupkg` and the private output outside Git. The build includes stdlib/native DLLs but omits pip/site packages and unused Scripts; no pip is needed at runtime. Preserve `BUILD-INFO.json` and `runtime/LICENSE.txt`.

## Validation and limits

`tests/test_erp_desktop.py` covers initial seeding, owner edits across restart, prior empty installs with existing accounts/audit, corrupt seeds and custom records. The complete ERP suite contains 70 passing tests. `scripts/check_desktop_browser.py` runs the **packaged isolated entry script and bundled source** using the host interpreter against a disposable private data folder, not the user's work folder. It verifies original data, sale/amendment/receipt/expense, desktop navigation, restart persistence, consistent backup, same-instance reuse and rejecting foreign Host/Origin. The package's database remains unchanged during this test.

The development environment is Linux and cannot execute the Windows PE runtime; the official Windows executable itself has not been tested on a real Windows machine here. Runtime source/integrity, required DLLs and architecture were checked, and the exact packaged app/launcher were tested using native Python/Chromium at desktop size. Do not describe this as a completed real-Windows installation test or as remotely opening the user's own PC.
