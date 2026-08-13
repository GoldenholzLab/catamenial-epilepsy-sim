#!/usr/bin/env python3
"""Remove temporary citation locator tokens without altering Word/Zotero fields."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


TOKEN_RE = re.compile(r"\[\[(?:CITE:[^\]]+|ZOTERO_BIBLIOGRAPHY)\]\]")


def _clone_info(info: ZipInfo) -> ZipInfo:
    cloned = ZipInfo(info.filename, date_time=info.date_time)
    cloned.compress_type = info.compress_type
    cloned.comment = info.comment
    cloned.extra = info.extra
    cloned.create_system = info.create_system
    cloned.create_version = info.create_version
    cloned.extract_version = info.extract_version
    cloned.flag_bits = info.flag_bits
    cloned.internal_attr = info.internal_attr
    cloned.external_attr = info.external_attr
    cloned.volume = info.volume
    return cloned


def strip_placeholders(path: Path) -> int:
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Expected a .docx file: {path}")
    if not path.is_file():
        raise FileNotFoundError(path)

    with ZipFile(path, "r") as source:
        document_xml = source.read("word/document.xml").decode("utf-8")
        updated_xml, count = TOKEN_RE.subn("", document_xml)
        if count == 0:
            return 0

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".docx",
            dir=path.parent,
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            with ZipFile(temp_path, "w", compression=ZIP_DEFLATED) as target:
                for info in source.infolist():
                    data = (
                        updated_xml.encode("utf-8")
                        if info.filename == "word/document.xml"
                        else source.read(info.filename)
                    )
                    target.writestr(_clone_info(info), data)
            shutil.copystat(path, temp_path)
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", type=Path, nargs="+")
    args = parser.parse_args()

    for path in args.docx:
        removed = strip_placeholders(path)
        print(f"{path}: removed {removed} placeholder(s)")


if __name__ == "__main__":
    main()
