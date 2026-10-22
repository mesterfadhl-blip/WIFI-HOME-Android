"""Consistent online SQLite backup. Usage: python -m erp.backup SOURCE DESTINATION"""
import os
from pathlib import Path
import sqlite3
import sys

def backup(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or destination.exists():raise ValueError('Destination must be a new file, separate from the source')
    destination.parent.mkdir(parents=True,exist_ok=True)
    os.umask(0o077)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src:
        with sqlite3.connect(destination) as dest:
            src.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup integrity check failed')
    return destination

if __name__=='__main__':print(backup(*sys.argv[1:]))
