#!/usr/bin/env python3
"""Audit v13 manuscript DOCX integrity after direct OOXML updates.

The audit is intentionally read-only.  It checks that every live Zotero field
and custom XML part present in the v11 source remains in the v13 output, that
the new validation citations were added at the expected multiplicities, and
that the appendix contains the expected figures and native Word equations
without unresolved build markers.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import zipfile
from pathlib import Path

from lxml import etree


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
CUNNINGHAM_KEY = "H25WKPM3"
HARLOW_KEY = "DEANI3HH"
MUMFORD_KEY = "3Y2YEUNZ"
ANCKAERT_KEY = "YLLLVBP5"


def read_part(docx: Path, name: str) -> bytes:
    with zipfile.ZipFile(docx) as archive:
        return archive.read(name)


def document_root(docx: Path) -> etree._Element:
    return etree.fromstring(read_part(docx, "word/document.xml"))


def field_instructions(root: etree._Element, token: str) -> list[str]:
    """Collect normalized simple and complex field instructions individually."""

    instructions = [
        value
        for value in root.xpath(".//w:fldSimple/@w:instr", namespaces=NS)
        if token in value
    ]
    fld_char = f"{{{NS['w']}}}fldChar"
    fld_char_type = f"{{{NS['w']}}}fldCharType"
    instr_text = f"{{{NS['w']}}}instrText"
    stack: list[list[str]] = []
    for element in root.iter():
        if element.tag == fld_char:
            kind = element.get(fld_char_type)
            if kind == "begin":
                stack.append([])
            elif kind == "end" and stack:
                combined = "".join(stack.pop())
                if token in combined:
                    instructions.append(combined)
        elif element.tag == instr_text and stack:
            stack[-1].append(element.text or "")
    return [re.sub(r"\s+", " ", value).strip() for value in instructions]


def assert_equation_references_resolve(
    root: etree._Element, *, expected_count: int, label: str
) -> int:
    """Require every equation REF field to name an extant equation bookmark."""

    bookmarks = set(
        root.xpath('.//w:bookmarkStart[starts-with(@w:name,"Eq_")]/@w:name', namespaces=NS)
    )
    references = []
    for instruction in field_instructions(root, "REF Eq_"):
        match = re.search(r"\bREF\s+(Eq_[A-Za-z0-9_]+)\b", instruction)
        if match:
            references.append(match.group(1))
    if len(references) != expected_count:
        raise AssertionError(
            f"{label}: expected {expected_count} equation REF fields, found {len(references)}"
        )
    missing = sorted(set(references) - bookmarks)
    if missing:
        raise AssertionError(
            f"{label}: equation REF fields name missing bookmarks: "
            + ", ".join(missing)
        )
    visible_text = " ".join(root.xpath(".//w:t/text()", namespaces=NS))
    if "Error! Reference source not found." in visible_text:
        raise AssertionError(f"{label}: unresolved equation cross-reference cache found")
    if "SD,Equations" in visible_text:
        raise AssertionError(
            f"{label}: missing space before live equation-reference field"
        )
    return len(references)


def canonical_xml_digest(payload: bytes) -> str:
    """Hash XML semantics while ignoring declaration serialization details."""

    root = etree.fromstring(payload)
    canonical = etree.tostring(root, method="c14n", with_comments=True)
    return hashlib.sha256(canonical).hexdigest()


def custom_xml_hashes(docx: Path) -> dict[str, str]:
    with zipfile.ZipFile(docx) as archive:
        return {
            name: canonical_xml_digest(archive.read(name))
            for name in archive.namelist()
            if name.startswith("customXml/")
        }


def citation_signature(instruction: str) -> tuple[str, ...]:
    """Return stable Zotero item keys, independent of display cache and IDs."""

    return tuple(
        re.findall(r"zotero\.org/users/[^/]+/items/([A-Z0-9]+)", instruction)
    )


def citation_properties(instruction: str) -> dict[str, object]:
    """Return the Zotero CSL citation properties stored in a field."""

    marker = "CSL_CITATION "
    start = instruction.index(marker) + len(marker)
    payload, _ = json.JSONDecoder().raw_decode(instruction[start:])
    return payload.get("properties", {})


def cached_citation_presentations(root: etree._Element) -> list[dict[str, object]]:
    """Inspect each live Zotero field's cached text and Word run formatting."""

    presentations: list[dict[str, object]] = []
    for field in root.xpath(
        './/w:fldSimple[contains(@w:instr,"ZOTERO_ITEM CSL_CITATION")]',
        namespaces=NS,
    ):
        text_runs = [
            run
            for run in field.xpath(".//w:r", namespaces=NS)
            if run.xpath(".//w:t[normalize-space(.) != '']", namespaces=NS)
        ]
        presentations.append(
            {
                "cached_text": "".join(
                    run.xpath("string(.//w:t)", namespaces=NS) for run in text_runs
                ),
                "all_superscript": bool(text_runs)
                and all(
                    run.xpath(
                        './w:rPr/w:vertAlign[@w:val="superscript"]',
                        namespaces=NS,
                    )
                    for run in text_runs
                ),
            }
        )

    for instruction_node in root.xpath(
        './/w:instrText[contains(.,"ZOTERO_ITEM CSL_CITATION")]',
        namespaces=NS,
    ):
        paragraph = instruction_node.xpath("ancestor::w:p[1]", namespaces=NS)[0]
        runs = paragraph.xpath(".//w:r", namespaces=NS)
        instruction_run = instruction_node.xpath(
            "ancestor::w:r[1]", namespaces=NS
        )[0]
        instruction_index = runs.index(instruction_run)
        separate_index = next(
            index
            for index in range(instruction_index + 1, len(runs))
            if runs[index].xpath(
                './/w:fldChar[@w:fldCharType="separate"]', namespaces=NS
            )
        )
        end_index = next(
            index
            for index in range(separate_index + 1, len(runs))
            if runs[index].xpath(
                './/w:fldChar[@w:fldCharType="end"]', namespaces=NS
            )
        )
        text_runs = [
            run
            for run in runs[separate_index : end_index + 1]
            if run.xpath(".//w:t[normalize-space(.) != '']", namespaces=NS)
        ]
        presentations.append(
            {
                "cached_text": "".join(
                    run.xpath("string(.//w:t)", namespaces=NS) for run in text_runs
                ),
                "all_superscript": bool(text_runs)
                and all(
                    run.xpath(
                        './w:rPr/w:vertAlign[@w:val="superscript"]',
                        namespaces=NS,
                    )
                    for run in text_runs
                ),
            }
        )
    return presentations


def assert_citation_presentation(
    root: etree._Element,
    instructions: list[str],
    *,
    expected: str,
    label: str,
) -> None:
    """Require both Zotero metadata and cached Word text to retain style."""

    metadata = [citation_properties(value) for value in instructions]
    cached = cached_citation_presentations(root)
    if len(cached) != len(instructions):
        raise AssertionError(
            f"{label}: found {len(instructions)} live Zotero fields but "
            f"{len(cached)} cached field results"
        )

    if expected == "superscript":
        metadata_ok = all(
            "\\super" in str(item.get("formattedCitation", ""))
            and not str(item.get("plainCitation", "")).startswith("(")
            for item in metadata
        )
        cached_ok = all(
            item["all_superscript"]
            and not str(item["cached_text"]).startswith("(")
            for item in cached
        )
    elif expected == "parenthetical":
        metadata_ok = all(
            str(item.get("formattedCitation", "")).startswith("(")
            and str(item.get("plainCitation", "")).startswith("(")
            and "\\super" not in str(item.get("formattedCitation", ""))
            for item in metadata
        )
        cached_ok = all(
            not item["all_superscript"]
            and str(item["cached_text"]).startswith("(")
            and str(item["cached_text"]).endswith(")")
            for item in cached
        )
    else:
        raise ValueError(f"Unsupported citation presentation: {expected}")

    if not metadata_ok or not cached_ok:
        raise AssertionError(
            f"{label}: live Zotero citation presentation is not uniformly {expected}"
        )


def assert_counter_subset(
    source: collections.Counter[object],
    output: collections.Counter[object],
    label: str,
) -> None:
    missing = source - output
    if missing:
        sample = repr(next(iter(missing)))[:160]
        raise AssertionError(
            f"{label}: {sum(missing.values())} source field(s) were lost; "
            f"first missing signature begins {sample}"
        )


def audit_pair(source: Path, output: Path, *, appendix: bool) -> dict[str, object]:
    with zipfile.ZipFile(output) as archive:
        corrupt_member = archive.testzip()
        if corrupt_member:
            raise AssertionError(f"{output}: corrupt ZIP member {corrupt_member}")

    source_root = document_root(source)
    output_root = document_root(output)
    source_citation_instructions = field_instructions(
        source_root, "ZOTERO_ITEM CSL_CITATION"
    )
    output_citation_instructions = field_instructions(
        output_root, "ZOTERO_ITEM CSL_CITATION"
    )
    citation_presentation = "parenthetical" if appendix else "superscript"
    assert_citation_presentation(
        output_root,
        output_citation_instructions,
        expected=citation_presentation,
        label=output.name,
    )
    source_signatures = [
        citation_signature(value) for value in source_citation_instructions
    ]
    output_signatures = [
        citation_signature(value) for value in output_citation_instructions
    ]
    if any(not signature for signature in source_signatures + output_signatures):
        raise AssertionError(f"{output.name}: could not parse a Zotero citation item key")
    source_citations = collections.Counter(
        key for signature in source_signatures for key in signature
    )
    output_citations = collections.Counter(
        key for signature in output_signatures for key in signature
    )
    assert_counter_subset(source_citations, output_citations, output.name)

    source_bibliographies = collections.Counter(
        field_instructions(source_root, "ZOTERO_BIBL")
    )
    output_bibliographies = collections.Counter(
        field_instructions(output_root, "ZOTERO_BIBL")
    )
    assert_counter_subset(source_bibliographies, output_bibliographies, output.name)

    source_custom = custom_xml_hashes(source)
    output_custom = custom_xml_hashes(output)
    changed_custom = {
        name
        for name, digest in source_custom.items()
        if output_custom.get(name) != digest
    }
    if changed_custom:
        raise AssertionError(
            f"{output.name}: source custom XML parts changed or disappeared: "
            + ", ".join(sorted(changed_custom))
        )

    xml_text = etree.tostring(output_root, encoding="unicode")
    unresolved = sorted(set(re.findall(r"\[\[(?:EQUATION|CITE)[^\]]*\]\]", xml_text)))
    if unresolved:
        raise AssertionError(
            f"{output.name}: unresolved build markers: {', '.join(unresolved)}"
        )

    cunningham_fields = sum(
        count
        for key, count in output_citations.items()
        if key == CUNNINGHAM_KEY
    )
    expected_cunningham = 5 if appendix else 1
    if cunningham_fields != expected_cunningham:
        raise AssertionError(
            f"{output.name}: expected {expected_cunningham} Cunningham fields, "
            f"found {cunningham_fields}"
        )

    expected_new_source_counts = (
        {
            HARLOW_KEY: 3,
            MUMFORD_KEY: 2,
            ANCKAERT_KEY: 1,
        }
        if appendix
        else {
            HARLOW_KEY: 1,
            MUMFORD_KEY: 1,
            ANCKAERT_KEY: 1,
        }
    )
    for key, expected in expected_new_source_counts.items():
        observed = output_citations[key]
        if observed != expected:
            raise AssertionError(
                f"{output.name}: expected {expected} citation item(s) for {key}, "
                f"found {observed}"
            )

    native_math = int(output_root.xpath("count(.//m:oMath)", namespaces=NS))
    seq_equations = sum(
        1
        for instruction in field_instructions(output_root, "SEQ Equation")
        if "SEQ Equation" in instruction
    )
    if appendix and (native_math < 16 or seq_equations != 16):
        raise AssertionError(
            f"{output.name}: expected at least 16 native math objects and exactly "
            f"16 equation SEQ fields; found {native_math} and {seq_equations}"
        )
    equation_ref_fields = assert_equation_references_resolve(
        output_root,
        expected_count=9 if appendix else 0,
        label=output.name,
    )

    if appendix:
        relationships = etree.fromstring(
            read_part(output, "word/_rels/document.xml.rels")
        )
        relationship_targets = {
            node.get("Id"): node.get("Target") for node in relationships
        }
        with zipfile.ZipFile(output) as archive:
            for figure in ("A3", "A4"):
                captions = output_root.xpath(
                    f'.//w:p[contains(string(.), "Appendix Figure {figure}.")]',
                    namespaces=NS,
                )
                if len(captions) != 1:
                    raise AssertionError(
                        f"{output.name}: expected one Appendix Figure {figure} caption, "
                        f"found {len(captions)}"
                    )
                previous = captions[0].getprevious()
                embeds = (
                    previous.xpath('.//a:blip/@r:embed', namespaces=NS)
                    if previous is not None
                    else []
                )
                if len(embeds) != 1 or not relationship_targets.get(
                    embeds[0], ""
                ).startswith("media/"):
                    raise AssertionError(
                        f"{output.name}: Appendix Figure {figure} is not linked to one "
                        "embedded image"
                    )
                embedded_target = "word/" + relationship_targets[embeds[0]]
                if embedded_target not in archive.namelist():
                    raise AssertionError(
                        f"{output.name}: missing embedded Appendix Figure {figure} media "
                        f"{embedded_target}"
                    )

    required_phrases = ["HORMONE-CYCLE version 0.3.0"]
    if appendix:
        required_phrases.extend(
            [
                "Chapter 2. Calibration and validation status of HORMONE-CYCLE",
                "held-out aggregate cross-check",
                "The primary gate is a qualified pass",
                "Appendix Figure A3.",
                "Appendix Figure A4.",
                "Long follicular phases are not created by horizontally stretching",
                "broad midluteal summit",
            ]
        )
    else:
        required_phrases.append("aggregate cross-check not used for fitting")
    visible_text = " ".join(output_root.xpath(".//w:t/text()", namespaces=NS))
    absent = [phrase for phrase in required_phrases if phrase not in visible_text]
    if absent:
        raise AssertionError(
            f"{output.name}: required text absent: {', '.join(absent)}"
        )

    return {
        "source": str(source),
        "output": str(output),
        "source_citation_fields": len(source_citation_instructions),
        "output_citation_fields": len(output_citation_instructions),
        "source_citation_items": sum(source_citations.values()),
        "output_citation_items": sum(output_citations.values()),
        "citation_presentation": citation_presentation,
        "cunningham_fields": cunningham_fields,
        "source_bibliography_fields": sum(source_bibliographies.values()),
        "output_bibliography_fields": sum(output_bibliographies.values()),
        "preserved_custom_xml_parts": len(source_custom),
        "native_math_objects": native_math,
        "equation_seq_fields": seq_equations,
        "equation_ref_fields": equation_ref_fields,
        "status": "pass",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--main-source",
        type=Path,
        default=Path("outputs/epilepsia_submission/draft_v11_hormone_repaired.docx"),
    )
    parser.add_argument("--main-output", type=Path, required=True)
    parser.add_argument(
        "--appendix-source",
        type=Path,
        default=Path(
            "outputs/epilepsia_submission/draft_v11_appendix_hormone_repaired.docx"
        ),
    )
    parser.add_argument("--appendix-output", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    report = {
        "main": audit_pair(args.main_source, args.main_output, appendix=False),
        "appendix": audit_pair(
            args.appendix_source, args.appendix_output, appendix=True
        ),
        "status": "pass",
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
