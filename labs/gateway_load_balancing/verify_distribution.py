"""Verify that the isolated gateway distributes successful requests."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from urllib.request import urlopen


def fetch_replica(url: str) -> str:
    with urlopen(  # nosec B310 - this verifier targets an explicitly supplied lab endpoint
        url, timeout=2
    ) as response:
        payload = json.load(response)
    return str(payload["replica"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:18080/")
    parser.add_argument("--requests", type=int, default=30)
    args = parser.parse_args()
    counts = Counter(fetch_replica(args.url) for _ in range(args.requests))
    print(json.dumps(dict(sorted(counts.items())), indent=2))
    if len(counts) < 2:
        raise SystemExit("Expected at least two healthy replicas to receive requests.")


if __name__ == "__main__":
    main()
