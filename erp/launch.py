"""Open a private desktop instance with data outside the extracted application."""

import os
from pathlib import Path
import threading
import webbrowser
from wsgiref.simple_server import make_server

from .server import create_app


def main():
    base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.local' / 'share'))
    database = base / 'WIFI-HOME-ERP' / 'data.sqlite3'
    database.parent.mkdir(parents=True, exist_ok=True)
    with make_server('127.0.0.1', 0, create_app(str(database))) as server:
        address = f'http://127.0.0.1:{server.server_port}/'
        print(f'WIFI HOME ERP: {address}', flush=True)
        print(f'Database: {database}', flush=True)
        print('Keep this window open. Press Ctrl+C to stop.', flush=True)
        timer = threading.Timer(1, webbrowser.open, args=(address,))
        timer.daemon = True
        timer.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
