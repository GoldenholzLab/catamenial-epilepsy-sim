#!/usr/bin/env python3
"""Insert Zotero-compatible Word fields from verified local Zotero records.

The input DOCX must already contain ZOTERO_PREF_1 document preferences and
placeholder markers of the form ``[[CITE:C001]]`` plus ``[[BIBLIOGRAPHY]]``.
The script uses item keys from the citation map, Zotero's local API for CSL
metadata, and Zotero's local SQLite database for internal item identifiers.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sqlite3
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS}
Q = lambda name: f"{{{W_NS}}}{name}"

CITE_RE = re.compile(r"\[\[CITE:C\d{3}\]\]")
BIB_MARKER = "[[BIBLIOGRAPHY]]"
ZOTERO_API = "http://127.0.0.1:23119/api/users/0/items"
ZOTERO_DB = "file:/Users/dgoldenh/Zotero/zotero.sqlite?immutable=1"
ZOTERO_USER_ID = "1538114"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", type=Path)
    parser.add_argument("citation_map", type=Path)
    return parser.parse_args()


def zotero_item_ids(keys: set[str]) -> dict[str, int]:
    conn = sqlite3.connect(ZOTERO_DB, uri=True)
    try:
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"SELECT key, itemID FROM items WHERE key IN ({placeholders})",
            sorted(keys),
        ).fetchall()
    finally:
        conn.close()
    result = {key: int(item_id) for key, item_id in rows}
    missing = sorted(keys - result.keys())
    if missing:
        raise RuntimeError(f"Zotero keys missing from local database: {missing}")
    return result


def zotero_csl(key: str, item_id: int) -> dict:
    url = f"{ZOTERO_API}/{key}?format=csljson"
    with urllib.request.urlopen(url, timeout=15) as response:
        payload = json.load(response)
    if not isinstance(payload, list) or len(payload) != 1:
        raise RuntimeError(f"Unexpected CSL response for Zotero key {key}")
    item_data = payload[0]
    item_data["id"] = item_id
    return item_data


def compress_numbers(numbers: list[int]) -> str:
    values = sorted(dict.fromkeys(numbers))
    groups: list[str] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        groups.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    groups.append(str(start) if start == previous else f"{start}-{previous}")
    return f"({','.join(groups)})"


def make_run(text: str | None = None, rpr: etree._Element | None = None) -> etree._Element:
    run = etree.Element(Q("r"))
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    if text is not None:
        node = etree.SubElement(run, Q("t"))
        if text.startswith(" ") or text.endswith(" "):
            node.set(f"{{{XML_NS}}}space", "preserve")
        node.text = text
    return run


def make_citation_runs(
    instruction: str,
    displayed: str,
    rpr: etree._Element | None,
) -> list[etree._Element]:
    begin = make_run()
    etree.SubElement(begin, Q("fldChar")).set(Q("fldCharType"), "begin")

    code = make_run()
    instr = etree.SubElement(code, Q("instrText"))
    instr.set(f"{{{XML_NS}}}space", "preserve")
    instr.text = instruction

    separate = make_run()
    etree.SubElement(separate, Q("fldChar")).set(Q("fldCharType"), "separate")

    result = make_run(displayed, rpr)
    result_rpr = result.find("w:rPr", NS)
    if result_rpr is None:
        result_rpr = etree.Element(Q("rPr"))
        result.insert(0, result_rpr)
    if result_rpr.find("w:noProof", NS) is None:
        etree.SubElement(result_rpr, Q("noProof"))

    end = make_run()
    etree.SubElement(end, Q("fldChar")).set(Q("fldCharType"), "end")
    return [begin, code, separate, result, end]


def citation_instruction(
    citation_id: str,
    displayed: str,
    specs: list[dict],
    item_ids: dict[str, int],
    csl_items: dict[str, dict],
) -> str:
    citation_items = []
    for spec in specs:
        key = spec["key"]
        item_id = item_ids[key]
        citation_items.append(
            {
                "id": item_id,
                "uris": [f"http://zotero.org/users/{ZOTERO_USER_ID}/items/{key}"],
                "itemData": csl_items[key],
            }
        )
    payload = {
        "citationID": citation_id,
        "properties": {
            "unsorted": False,
            "formattedCitation": displayed,
            "plainCitation": displayed,
            "noteIndex": 0,
        },
        "citationItems": citation_items,
        "schema": "https://github.com/citation-style-language/schema/raw/master/csl-citation.json",
    }
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f" ADDIN ZOTERO_ITEM CSL_CITATION {compact} "


def replace_marker_with_field(
    text_node: etree._Element,
    marker: str,
    runs: list[etree._Element],
) -> etree._Element | None:
    run = text_node.getparent()
    parent = run.getparent()
    full_text = text_node.text or ""
    before, separator, after = full_text.partition(marker)
    if not separator:
        return None

    text_node.text = before
    if before.startswith(" ") or before.endswith(" "):
        text_node.set(f"{{{XML_NS}}}space", "preserve")

    insert_at = parent.index(run) + 1
    for field_run in runs:
        parent.insert(insert_at, field_run)
        insert_at += 1

    if after:
        after_run = make_run(after, run.find("w:rPr", NS))
        parent.insert(insert_at, after_run)
        return after_run.find("w:t", NS)
    return None


def inject_fields(docx: Path, citation_map_path: Path) -> dict:
    citation_map = json.loads(citation_map_path.read_text())["citations"]
    all_specs = [spec for specs in citation_map.values() for spec in specs]
    keys = {spec["key"] for spec in all_specs}
    item_ids = zotero_item_ids(keys)
    csl_items = {key: zotero_csl(key, item_ids[key]) for key in sorted(keys)}

    with zipfile.ZipFile(docx, "r") as source:
        members = {name: source.read(name) for name in source.namelist()}

    root = etree.fromstring(members["word/document.xml"])
    reference_number: dict[str, int] = {}
    next_reference = 1
    occurrence = 0

    text_nodes = list(root.xpath(".//w:t", namespaces=NS))
    for initial_node in text_nodes:
        node = initial_node
        while node is not None:
            text = node.text or ""
            match = CITE_RE.search(text)
            if not match:
                break
            marker = match.group(0)
            specs = citation_map.get(marker)
            if not specs:
                raise RuntimeError(f"No citation-map entry for marker {marker}")

            numbers = []
            for spec in specs:
                key = spec["key"]
                if key not in reference_number:
                    reference_number[key] = next_reference
                    next_reference += 1
                numbers.append(reference_number[key])
            displayed = compress_numbers(numbers)

            occurrence += 1
            digest = hashlib.sha1(f"{marker}:{occurrence}".encode()).hexdigest()[:8]
            instruction = citation_instruction(
                f"id{digest}",
                displayed,
                specs,
                item_ids,
                csl_items,
            )
            source_run = node.getparent()
            field_runs = make_citation_runs(
                instruction,
                displayed,
                source_run.find("w:rPr", NS),
            )
            node = replace_marker_with_field(node, marker, field_runs)

    bibliography_count = 0
    for node in list(root.xpath(".//w:t", namespaces=NS)):
        if BIB_MARKER not in (node.text or ""):
            continue
        source_run = node.getparent()
        instruction = (
            ' ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} '
            "CSL_BIBLIOGRAPHY "
        )
        field_runs = make_citation_runs(
            instruction,
            "Zotero bibliography: refresh fields in Microsoft Word.",
            source_run.find("w:rPr", NS),
        )
        replace_marker_with_field(node, BIB_MARKER, field_runs)
        bibliography_count += 1

    if bibliography_count != 1:
        raise RuntimeError(f"Expected one bibliography marker, found {bibliography_count}")
    if root.xpath(".//w:t[contains(., '[[CITE:')]", namespaces=NS):
        raise RuntimeError("Citation markers remain after field injection")

    members["word/document.xml"] = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )

    with tempfile.NamedTemporaryFile(
        dir=docx.parent,
        prefix=f".{docx.stem}.",
        suffix=".docx",
        delete=False,
    ) as temp:
        temp_path = Path(temp.name)
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as target:
            for name, data in members.items():
                target.writestr(name, data)
        temp_path.replace(docx)
    finally:
        temp_path.unlink(missing_ok=True)

    return {
        "citation_fields": occurrence,
        "unique_references": len(reference_number),
        "bibliography_fields": bibliography_count,
    }


def main() -> None:
    args = parse_args()
    report = inject_fields(args.docx.resolve(), args.citation_map.resolve())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
