"""Build a private Windows distribution; never publish seed data in Git."""

from pathlib import Path, PurePosixPath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse, base64, hashlib, json, shutil, sqlite3, struct, zipfile
from erp.backup import backup

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--database", type=Path, required=True)
p.add_argument("--runtime-info", type=Path, required=True)
args = p.parse_args()
if args.output.exists():
    raise SystemExit(
        "Output must be a new directory; existing files are never overwritten"
    )
if args.output.resolve().is_relative_to(ROOT):
    raise SystemExit("Private database output must be outside the repository")
info = json.loads(args.runtime_info.read_text())
runtime = Path(info["path"])
raw = runtime.read_bytes()
if base64.b64encode(hashlib.sha512(raw).digest()).decode() != info["sha512"]:
    raise SystemExit("Runtime SHA512 verification failed")
if "Python Software Foundation" not in info["authors"]:
    raise SystemExit("Unexpected runtime publisher")
with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as c:
    if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("Invalid seed database")
    if c.execute("SELECT count(*) FROM users").fetchone()[0]:
        raise SystemExit("Distribution seed must not contain existing login accounts")
    counts = {
        t: c.execute("SELECT count(*) FROM " + t).fetchone()[0]
        for t in ("customers", "products", "invoices")
    }
args.output.mkdir(parents=True, mode=0o700)
out = args.output
with zipfile.ZipFile(runtime) as z:
    exe = z.read("tools/python.exe")
    offset = struct.unpack_from("<I", exe, 0x3C)[0]
    if (
        exe[offset : offset + 4] != b"PE\0\0"
        or struct.unpack_from("<H", exe, offset + 4)[0] != 0x8664
    ):
        raise SystemExit("Expected an official AMD64 Python executable")
    for name in z.namelist():
        if not name.startswith("tools/") or name.endswith("/"):
            continue
        relative = PurePosixPath(name[len("tools/") :])
        if ".." in relative.parts or relative.is_absolute():
            raise SystemExit("Unsafe archive entry")
        if str(relative).startswith(("Lib/site-packages/", "Scripts/")):
            continue
        target = out / "runtime" / Path(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(name))
for name in (
    "desktop_start.py",
    "desktop_backup.py",
    "START-WIFI-HOME.bat",
    "BACKUP-DATA.bat",
):
    source = ROOT / "desktop" / name
    if name.endswith(".bat"):
        (out / name).write_bytes(
            source.read_text()
            .replace("\r\n", "\n")
            .replace("\n", "\r\n")
            .encode("ascii")
        )
    else:
        shutil.copyfile(source, out / name)
(out / "erp").mkdir()
for source in (ROOT / "erp").glob("*.py"):
    shutil.copyfile(source, out / "erp" / source.name)
shutil.copytree(ROOT / "erp/static", out / "erp/static")
(out / "seed").mkdir()
backup(args.database, out / "seed/DATABASE.sqlite3")
shutil.copyfile(ROOT / "desktop/START-AR.txt", out / "START-AR.txt")
manifest = {
    "platform": "Windows x64",
    "python_version": info["version"],
    "runtime_source": info["url"],
    "runtime_sha512": info["sha512"],
    "base_counts": counts,
    "files": {},
}
for f in out.rglob("*"):
    if f.is_file():
        manifest["files"][str(f.relative_to(out))] = hashlib.sha256(
            f.read_bytes()
        ).hexdigest()
(out / "BUILD-INFO.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
print(
    "Private Windows folder built; runtime hash/PE, database integrity and source counts verified:",
    counts,
)
