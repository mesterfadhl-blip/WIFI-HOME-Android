# WIFI-HOME Web

Static browser version of WIFI-HOME, prepared from main commit 057aa890e118c4b484bdfc794c25e2b6eaa4e3a3.

Enable GitHub Pages under repository Settings > Pages, choose Deploy from a branch, branch gh-pages, folder / (root), then Save.
The site address after deployment is https://mesterfadhl-blip.github.io/WIFI-HOME-Android/.

Serve this directory over HTTPS for installation and offline use. For local development use `python -m http.server 8765` in this directory. No package installation is required.

Changes for web: added manifest, icon and service worker; guarded retired dashboard elements against missing DOM nodes; exposed the existing executive renderer used by later dashboard scripts; skipped old dashboard insertion when its container was replaced. Android/main source remains unchanged.

Validated at 390x844 and 1366x900: page load, navigation to sales/customers/inventory/cash/analysis/settings/home, and offline reload. This is a smoke check, not a complete accounting audit.

Data is stored locally per browser. Devices do not share data automatically. Use the application's backup/export and import features to transfer data. The original app includes demo entries on a fresh database and opens directly without server authentication. This deployment does not add a backend.

Future updates: update this branch's index.html and increment the service-worker cache version if its cached assets change.
