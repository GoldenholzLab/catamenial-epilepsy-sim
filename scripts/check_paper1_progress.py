#!/usr/bin/env python3
"""Print the latest Paper 1 analysis progress/ETA from outputs/progress.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", default="outputs/progress.json", help="Path to progress.json.")
    args = parser.parse_args()
    path = Path(args.progress)
    if not path.exists():
        raise SystemExit(f"No progress file found at {path}. Start a run with progress.write_json enabled.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(f"mode: {payload.get('mode')}")
    print(f"stage: {payload.get('stage')}")
    if payload.get("message"):
        print(f"message: {payload['message']}")
    print(
        "participants: "
        f"{payload.get('participants_completed', 0):,}/"
        f"{payload.get('total_participants', 0):,} "
        f"({payload.get('percent_complete', 0.0):.1f}%)"
    )
    print(f"elapsed: {payload.get('elapsed')}")
    print(f"eta: {payload.get('eta') or 'not applicable for current stage'}")
    print(f"rate: {payload.get('participants_per_second', 0.0):.2f} participants/s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
