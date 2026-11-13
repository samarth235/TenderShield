"""Create a TenderShield user.

Usage (from backend/):
    python -m scripts.create_user --email officer@dept.gov.in --role officer
The password is read from the TS_NEW_USER_PASSWORD environment variable, or prompted for.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from app.auth import RANK, create_user
from app.db import init_db, session


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True)
    ap.add_argument("--role", choices=sorted(RANK), default="viewer")
    ap.add_argument("--name", default="")
    args = ap.parse_args()
    password = os.environ.get("TS_NEW_USER_PASSWORD") or getpass.getpass("Password (min 10 characters): ")
    init_db()
    with session() as conn:
        try:
            user = create_user(conn, args.email, password, args.role, args.name)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    print(f"Created {user['role']} {user['email']} (id {user['user_id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
