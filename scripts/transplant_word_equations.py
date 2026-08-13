#!/usr/bin/env python3
"""Transplant native equation blocks into a DOCX without rewriting other parts.

The equation skill deliberately uses python-docx to construct native OMML,
bookmarks, and SEQ fields. Loading and saving a document through python-docx
also normalizes unrelated package parts. This script uses that generated DOCX
only as a donor: it replaces the explicit equation-marker paragraphs in the
pre-equation DOCX with the donor's equation table and variable-definition
paragraph, while retaining every other ZIP member from the pre-equation file.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile

from lxml import etree


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
W_VAL = f"{{{W}}}val"
MARKER = re.compile(r"^\[\[EQUATION:([A-Za-z][A-Za-z0-9_-]*)\]\]$")


def validate_equation_references(document: etree._Element) -> None:
    """Fail the build if a REF field points past Word's 40-character bookmark."""

    bookmark_names = {
        value
        for value in document.xpath(
            './/w:bookmarkStart[starts-with(@w:name,"Eq_")]/@w:name',
            namespaces=NS,
        )
    }
    instructions = document.xpath(".//w:instrText/text()", namespaces=NS)
    referenced_names = {
        match.group(1)
        for instruction in instructions
        for match in [re.search(r"\bREF\s+(Eq_[A-Za-z0-9_]+)\b", instruction)]
        if match
    }
    missing = sorted(referenced_names - bookmark_names)
    if missing:
        raise ValueError(
            "Equation REF field(s) point to missing bookmark(s): "
            + ", ".join(missing)
        )


def paragraph_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS)).strip()


def paragraph_style(paragraph: etree._Element | None) -> str | None:
    if paragraph is None or paragraph.tag != f"{{{W}}}p":
        return None
    values = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
    return values[0] if values else None


def equation_caption(table: etree._Element) -> str | None:
    values = table.xpath("./w:tblPr/w:tblCaption/@w:val", namespaces=NS)
    if len(values) != 1 or not values[0].startswith("Equation:"):
        return None
    return values[0].split(":", 1)[1]


def enable_field_updates(payload: bytes) -> bytes:
    root = etree.fromstring(payload)
    nodes = root.findall(f"{{{W}}}updateFields")
    if len(nodes) == 1 and nodes[0].get(W_VAL, "true").lower() in {
        "true",
        "1",
        "on",
    }:
        return payload
    node = nodes[-1] if nodes else etree.SubElement(root, f"{{{W}}}updateFields")
    node.set(W_VAL, "true")
    for extra in nodes[:-1]:
        root.remove(extra)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )


def transplant(base: Path, donor: Path, manifest_path: Path, output: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("equations")
    if not isinstance(records, list) or not records:
        raise ValueError("Manifest must contain a nonempty equations array")

    with zipfile.ZipFile(base) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(donor) as archive:
        donor_document = etree.fromstring(archive.read("word/document.xml"))

    document = etree.fromstring(entries["word/document.xml"])
    body = document.find(f"{{{W}}}body")
    donor_body = donor_document.find(f"{{{W}}}body")
    if body is None or donor_body is None:
        raise ValueError("DOCX document.xml has no body")

    markers: dict[str, etree._Element] = {}
    for paragraph in body.findall(f"{{{W}}}p"):
        match = MARKER.fullmatch(paragraph_text(paragraph))
        if match:
            if match.group(1) in markers:
                raise ValueError(f"Duplicate base marker: {match.group(1)}")
            markers[match.group(1)] = paragraph

    donor_tables: dict[str, etree._Element] = {}
    for table in donor_body.findall(f"{{{W}}}tbl"):
        equation_id = equation_caption(table)
        if equation_id:
            if equation_id in donor_tables:
                raise ValueError(f"Duplicate donor equation: {equation_id}")
            donor_tables[equation_id] = table

    expected = [record["id"] for record in records]
    if set(markers) != set(expected):
        raise ValueError(
            "Base marker mismatch: "
            f"missing={sorted(set(expected) - set(markers))}, "
            f"extra={sorted(set(markers) - set(expected))}"
        )
    if set(donor_tables) != set(expected):
        raise ValueError(
            "Donor equation mismatch: "
            f"missing={sorted(set(expected) - set(donor_tables))}, "
            f"extra={sorted(set(donor_tables) - set(expected))}"
        )

    for record in records:
        equation_id = record["id"]
        marker = markers[equation_id]
        table = donor_tables[equation_id]
        position = record.get("definitions_position", "below")
        sibling = table.getprevious() if position == "above" else table.getnext()
        if record.get("variables") and paragraph_style(sibling) != "EquationVariables":
            raise ValueError(
                f"Donor equation {equation_id} has no immediate {position} "
                "EquationVariables paragraph"
            )
        replacements = [copy.deepcopy(table)]
        if record.get("variables"):
            definition = copy.deepcopy(sibling)
            replacements = (
                [definition, replacements[0]]
                if position == "above"
                else [replacements[0], definition]
            )
        index = body.index(marker)
        for offset, element in enumerate(replacements):
            body.insert(index + offset, element)
        body.remove(marker)

    unresolved = [
        paragraph_text(paragraph)
        for paragraph in body.findall(f"{{{W}}}p")
        if MARKER.fullmatch(paragraph_text(paragraph))
    ]
    if unresolved:
        raise ValueError(f"Unresolved equation markers: {unresolved}")
    validate_equation_references(document)

    entries["word/document.xml"] = etree.tostring(
        document,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )
    entries["word/settings.xml"] = enable_field_updates(entries["word/settings.xml"])

    if output.exists() and output.resolve() not in {base.resolve(), donor.resolve()}:
        output.unlink()
    with NamedTemporaryFile(
        prefix=f".{output.stem}-",
        suffix=output.suffix,
        dir=output.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    transplant(args.base, args.donor, args.manifest, args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
