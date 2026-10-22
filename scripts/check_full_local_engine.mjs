import fs from "node:fs";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const runtime =
  process.env.ERP_PYODIDE_RUNTIME || "/workspace/.cloud-setup/pyodide/package";
const { loadPyodide } = await import(
  pathToFileURL(path.join(runtime, "pyodide.mjs"))
);
const p = await loadPyodide({ indexURL: runtime + "/" });
await p.loadPackage(["sqlite3", "hashlib"]);
for (const dir of ["erp", "tests"]) {
  p.FS.mkdirTree("/app/" + dir);
  for (const name of fs.readdirSync(path.join(root, dir)))
    if (name.endsWith(".py"))
      p.FS.writeFile(
        "/app/" + dir + "/" + name,
        fs.readFileSync(path.join(root, dir, name)),
      );
}
p.FS.mkdirTree("/app/erp/static");
for (const name of fs.readdirSync(path.join(root, "erp/static")))
  p.FS.writeFile(
    "/app/erp/static/" + name,
    fs.readFileSync(path.join(root, "erp/static", name)),
  );
await p.runPythonAsync(`import sys,unittest
sys.path[:0]=['/app','/app/tests']
suite=unittest.defaultTestLoader.discover('/app/tests',pattern='test_erp*.py')
result=unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful():raise RuntimeError('WASM regression failures')
`);
