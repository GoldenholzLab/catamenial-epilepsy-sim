#!/usr/bin/env python3
"""Refresh hashes for completed run outputs whose status files finalize last."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from tempfile import NamedTemporaryFile


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = Path(item["path"])
        if not path.exists():
            raise FileNotFoundError(path)
        item["bytes"] = path.stat().st_size
        item["sha256"] = file_sha256(path)
    manifest["finalized_unix_time"] = time.time()

    with NamedTemporaryFile(
        prefix=f".{args.manifest.stem}-",
        suffix=".json",
        dir=args.manifest.parent,
        mode="w",
        encoding="utf-8",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temporary.replace(args.manifest)


if __name__ == "__main__":
    main()
