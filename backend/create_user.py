"""CLI: create a backend login account (the `users` table). An operator
tool, never exposed over HTTP — there is no user-management endpoint in
this session (see docs/DECISIONS.md for why `users` has no RLS and is only
ever queried by the login code path).

Connects the same way every other write path in this project does: via
ingest.db.connect_sync, i.e. as APP_DB_USER, never POSTGRES_USER.

Run as a module (see docs/DECISIONS.md #22 for why running this file by
path instead breaks its package-relative imports):
    .venv/bin/python -m backend.create_user --username admin_a --role admin --tenant demoA
(omit --password to be prompted, so it never lands in shell history)
"""
import argparse
import getpass
import sys

import psycopg

from backend.security import hash_password
from ingest.db import connect_sync


def create_user(username: str, password: str, role: str, tenant: str) -> None:
    conn = connect_sync()
    password_hash = hash_password(password)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role, tenant) VALUES (%s, %s, %s, %s)",
                (username, password_hash, role, tenant),
            )
    except psycopg.errors.UniqueViolation:
        print(f"create_user: username {username!r} already exists", file=sys.stderr)
        sys.exit(1)
    print(f"create_user: created {username!r} (role={role}, tenant={tenant})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a backend login account.")
    parser.add_argument("--username", required=True)
    parser.add_argument(
        "--password",
        help="omit to be prompted instead (avoids the password landing in shell history)",
    )
    parser.add_argument("--role", required=True, choices=["admin", "viewer"])
    parser.add_argument("--tenant", required=True)
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    if not password:
        print("create_user: password must not be empty", file=sys.stderr)
        sys.exit(1)

    create_user(args.username, password, args.role, args.tenant)


if __name__ == "__main__":
    main()
