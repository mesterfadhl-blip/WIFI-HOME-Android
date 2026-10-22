"""Production entry point; initialize the owner before accepting public traffic."""

import os
from pathlib import Path

from .server import connect, create_app, password_hash


def production_app():
    database = os.environ.get("ERP_DATABASE", "")
    if not database or not Path(database).is_absolute():
        raise RuntimeError(
            "ERP_DATABASE must name an absolute persistent database path"
        )
    if os.environ.get("ERP_COOKIE_SECURE") != "1":
        raise RuntimeError("Production requires ERP_COOKIE_SECURE=1 and HTTPS")
    os.umask(0o077)
    app = create_app(database)
    with connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if not connection.execute("SELECT 1 FROM users").fetchone():
            name = os.environ.get("ERP_ADMIN_NAME", "").strip()
            password = os.environ.get("ERP_ADMIN_PASSWORD", "")
            if not name or len(password) < 12:
                raise RuntimeError(
                    "Set ERP_ADMIN_NAME and an initial ERP_ADMIN_PASSWORD of at least 12 characters in hosting secrets"
                )
            connection.execute(
                "INSERT INTO users(name,password,role) VALUES(?,?,?)",
                (name, password_hash(password), "admin"),
            )

    def application(environ, start_response):
        if (
            environ.get("PATH_INFO") == "/healthz"
            and environ.get("REQUEST_METHOD") == "GET"
        ):
            with connect(database) as connection:
                connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            start_response(
                "200 OK",
                [("Content-Type", "text/plain"), ("Cache-Control", "no-store")],
            )
            return [b"ok"]
        return app(environ, start_response)

    return application


def main():
    from waitress import serve

    serve(
        production_app(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
        threads=4,
        max_request_body_size=1000000,
        expose_tracebacks=False,
    )


if __name__ == "__main__":
    main()
