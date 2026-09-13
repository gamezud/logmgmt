"""Logs in, then POSTs the JSON samples to POST /ingest (admin-only — see
docs/DECISIONS.md). Requires the backend running (`make up`) and a demo
admin account already created (see backend/create_user.py, and
samples/README.md for the exact command).

Never hardcodes a real password: reads it from --password (which defaults
to this repo's own documented demo password, not a real credential) or the
INGEST_PASSWORD env var, so overriding it never means editing this file.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent
JSON_SAMPLES = ["api.json", "crowdstrike.json", "aws.json", "m365.json", "ad.json"]

# Matches the account samples/README.md's setup command creates. Not a real
# secret — it's only ever meaningful against a demo account you create
# yourself locally via backend.create_user.
DEFAULT_USERNAME = "admin_a"
DEFAULT_PASSWORD = "demo-password"


def login(base_url: str, username: str, password: str) -> str:
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)["access_token"]
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print(
                f"post_logs: login failed: invalid username/password for {username!r}. "
                f"Check --username/--password (or INGEST_USERNAME/INGEST_PASSWORD), and "
                f"that the account exists: .venv/bin/python -m backend.create_user "
                f"--username {username} --role admin --tenant demoA",
                file=sys.stderr,
            )
        else:
            print(f"post_logs: login failed: HTTP {exc.code} {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(
            f"post_logs: cannot reach {base_url} ({exc.reason}) — is the backend running? "
            f"(`make up` starts it via docker-compose)",
            file=sys.stderr,
        )
        sys.exit(1)


def post_one(ingest_url: str, token: str, path: Path) -> None:
    with open(path, "rb") as f:
        body = f.read()
    request = urllib.request.Request(
        ingest_url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print(f"{path.name}: {response.status}")
    except urllib.error.HTTPError as exc:
        print(f"{path.name}: FAILED (HTTP {exc.code} {exc.reason})", file=sys.stderr)
    except urllib.error.URLError as exc:
        print(f"{path.name}: FAILED ({exc.reason}) — is the backend running?", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Log in, then POST the JSON samples to POST /ingest.")
    parser.add_argument("--url", default="http://localhost:8000", help="backend base URL, no trailing path")
    parser.add_argument("--username", default=os.environ.get("INGEST_USERNAME", DEFAULT_USERNAME))
    parser.add_argument(
        "--password",
        default=os.environ.get("INGEST_PASSWORD", DEFAULT_PASSWORD),
        help="or set INGEST_PASSWORD instead of passing this on the command line",
    )
    args = parser.parse_args()

    token = login(args.url, args.username, args.password)
    ingest_url = f"{args.url}/ingest"
    for name in JSON_SAMPLES:
        post_one(ingest_url, token, SAMPLES_DIR / name)


if __name__ == "__main__":
    main()
