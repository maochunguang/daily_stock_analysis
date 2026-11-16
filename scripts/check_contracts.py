#!/usr/bin/env python3
"""Verify that the upstream DB still exposes the contracts we depend on."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from personal.config import get_settings  # noqa: E402
from personal.contracts.upstream_db import UpstreamDB  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    db = UpstreamDB(settings.upstream_db)
    if not db.available:
        message = f"upstream database missing: {settings.upstream_db}"
        if args.allow_missing:
            print(f"WARN {message}")
            return 0
        print(f"ERROR {message}")
        return 1

    missing = db.missing_contracts()
    if missing:
        print("contract check failed:")
        for item in missing:
            print(f"  - {item}")
        return 1
    print(f"contract check passed: {settings.upstream_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
