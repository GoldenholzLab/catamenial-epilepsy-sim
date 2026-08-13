#!/usr/bin/env python3
"""Enable automatic Word field updates without changing other DOCX parts."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile

from lxml import etree


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W_VAL = f"{{{W}}}val"


def enable_updates(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    root = etree.fromstring(entries["word/settings.xml"])
    nodes = root.findall(f"{{{W}}}updateFields")
    node = nodes[-1] if nodes else etree.SubElement(root, f"{{{W}}}updateFields")
    node.set(W_VAL, "true")
    for extra in nodes[:-1]:
        root.remove(extra)
    entries["word/settings.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    with NamedTemporaryFile(
        prefix=f".{path.stem}-",
        suffix=path.suffix,
        dir=path.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    args = parser.parse_args()
    enable_updates(args.docx)


if __name__ == "__main__":
    main()
