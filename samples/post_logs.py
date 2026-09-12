"""POSTs the JSON samples to an HTTP /ingest endpoint.

This targets a future FastAPI backend that does NOT exist in this session
(ingest+normalization only) -- running this now fails with
connection-refused, by design. It's included because the assignment's
deliverables (§6) ask for it alongside send_syslog.sh, as scaffolding for
whichever future session adds the HTTP ingest endpoint.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent
JSON_SAMPLES = ["api.json", "crowdstrike.json", "aws.json", "m365.json", "ad.json"]


def post_one(url: str, path: Path) -> None:
    with open(path, "rb") as f:
        body = f.read()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print(f"{path.name}: {response.status}")
    except urllib.error.URLError as exc:
        print(f"{path.name}: FAILED ({exc}) -- expected until a /ingest endpoint exists", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="POST the JSON samples to an /ingest endpoint.")
    parser.add_argument("--url", default="http://localhost:8000/ingest")
    args = parser.parse_args()

    for name in JSON_SAMPLES:
        post_one(args.url, SAMPLES_DIR / name)


if __name__ == "__main__":
    main()
