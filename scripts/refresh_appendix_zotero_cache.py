"""Refresh cached Zotero numbers and the NLM bibliography in a DOCX.

This does not flatten citations.  It updates the cached display inside the
existing live Zotero fields and leaves every ADDIN ZOTERO_ITEM and ADDIN
ZOTERO_BIBL instruction intact.  Bibliography strings are requested directly
from the running Zotero local API using the NLM citation-sequence style.  The
document's existing numeric citation presentation is retained: superscript in
the main manuscript and parenthetical in the appendix.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
import zipfile
from copy import deepcopy
from pathlib import Path

from lxml import etree
from lxml import html as lxml_html


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
NS = {"w": W_NS}

def fetch_nlm_bibliography(keys: list[str]) -> list[str]:
    # The local API sorts a multi-item bibliography according to library
    # metadata rather than the supplied itemKey order.  Request each item
    # separately so the bibliography exactly follows document citation order.
    entries = []
    for key in keys:
        query = urllib.parse.urlencode(
            {
                "format": "bib",
                "style": "nlm-citation-sequence",
                "locale": "en-US",
            }
        )
        with urllib.request.urlopen(
            f"http://localhost:23119/api/users/0/items/{key}?{query}", timeout=30
        ) as response:
            markup = response.read().decode("utf-8")
        tree = lxml_html.fromstring(markup)
        nodes = tree.xpath(
            './/div[contains(concat(" ", normalize-space(@class), " "), '
            '" csl-right-inline ")]'
        )
        if len(nodes) != 1:
            raise RuntimeError(
                f"Expected one NLM bibliography entry for {key}, found {len(nodes)}"
            )
        entry = " ".join(nodes[0].text_content().split())
        # Older CERES records stored the PubMed identifier in Zotero's
        # archive-location field.  NLM renders that as "Located at"; normalize
        # the cached bibliography label while retaining the live Zotero field.
        entry = re.sub(
            r"\bLocated at: (\d+)\.",
            r"PubMed PMID: \1.",
            entry,
        )
        entries.append(entry)
    if len(entries) != len(keys):
        raise RuntimeError(
            f"Expected {len(keys)} bibliography entries, received {len(entries)}"
        )
    return entries


def parse_citation_instruction(instruction: str) -> tuple[dict, str, str]:
    marker = "CSL_CITATION "
    start = instruction.index(marker) + len(marker)
    payload, offset = json.JSONDecoder().raw_decode(instruction[start:])
    prefix = instruction[:start]
    suffix = instruction[start + offset :]
    return payload, prefix, suffix


def citation_key(item: dict) -> str:
    uris = item.get("uris") or []
    if uris:
        return uris[0].rstrip("/").split("/")[-1]
    item_id = str(item.get("id", ""))
    return item_id.rstrip("/").split("/")[-1]


def ordered_citation_keys(root: etree._Element) -> list[str]:
    """Return unique Zotero item keys in first-citation document order."""

    instructions = root.xpath(
        './/w:fldSimple[contains(@w:instr,"ZOTERO_ITEM CSL_CITATION")]'
        ' | .//w:instrText[contains(.,"ZOTERO_ITEM CSL_CITATION")]',
        namespaces=NS,
    )
    keys: list[str] = []
    for node in instructions:
        instruction = (
            node.get(W + "instr") if node.tag == W + "fldSimple" else node.text
        )
        payload, _, _ = parse_citation_instruction(instruction or "")
        for item in payload.get("citationItems", []):
            key = citation_key(item)
            if key and key not in keys:
                keys.append(key)
    if not keys:
        raise RuntimeError("No live Zotero citation fields were found")
    return keys


def citation_presentation(root: etree._Element) -> str:
    """Infer the document's existing numeric-citation presentation."""

    instructions = root.xpath(
        './/w:fldSimple[contains(@w:instr,"ZOTERO_ITEM CSL_CITATION")]'
        ' | .//w:instrText[contains(.,"ZOTERO_ITEM CSL_CITATION")]',
        namespaces=NS,
    )
    for node in instructions:
        instruction = (
            node.get(W + "instr") if node.tag == W + "fldSimple" else node.text
        )
        payload, _, _ = parse_citation_instruction(instruction or "")
        formatted = payload.get("properties", {}).get("formattedCitation", "")
        if "\\super" in formatted:
            return "superscript"
        if formatted.startswith("("):
            return "parenthetical"
    raise RuntimeError("Could not infer numeric citation presentation")


def collapse_numbers(numbers: list[int]) -> str:
    numbers = sorted(dict.fromkeys(numbers))
    groups: list[list[int]] = []
    for number in numbers:
        if not groups or number != groups[-1][-1] + 1:
            groups.append([number])
        else:
            groups[-1].append(number)
    rendered = []
    for group in groups:
        if len(group) >= 3:
            rendered.append(f"{group[0]}–{group[-1]}")
        else:
            rendered.extend(str(number) for number in group)
    return ",".join(rendered)


def zotero_rtf(text: str) -> str:
    """Encode the Unicode punctuation used here as Zotero-compatible RTF."""

    return text.replace("–", r"\uc0\u8211{}")


def render_citation(numbers: list[int], presentation: str) -> tuple[str, str, str]:
    collapsed = collapse_numbers(numbers)
    if presentation == "superscript":
        return (
            collapsed,
            rf"\super {zotero_rtf(collapsed)}\nosupersub{{}}",
            collapsed,
        )
    if presentation == "parenthetical":
        displayed = f"({collapsed})"
        return displayed, zotero_rtf(displayed), displayed
    raise ValueError(f"Unsupported citation presentation: {presentation}")


def updated_instruction(
    instruction: str,
    number_by_key: dict[str, int],
    presentation: str,
) -> tuple[str, str]:
    payload, prefix, suffix = parse_citation_instruction(instruction)
    numbers = [number_by_key[citation_key(item)] for item in payload["citationItems"]]
    display, formatted, plain = render_citation(numbers, presentation)
    payload.setdefault("properties", {})["formattedCitation"] = formatted
    payload["properties"]["plainCitation"] = plain
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return prefix + compact + suffix, display


def make_text_run(text: str) -> etree._Element:
    run = etree.Element(W + "r")
    node = etree.SubElement(run, W + "t")
    node.text = text
    return run


def set_run_presentation(run: etree._Element, presentation: str) -> None:
    run_properties = run.find("w:rPr", namespaces=NS)
    if presentation == "superscript":
        if run_properties is None:
            run_properties = etree.Element(W + "rPr")
            run.insert(0, run_properties)
        vertical = run_properties.find("w:vertAlign", namespaces=NS)
        if vertical is None:
            vertical = etree.SubElement(run_properties, W + "vertAlign")
        vertical.set(W + "val", "superscript")
    elif run_properties is not None:
        for vertical in run_properties.findall("w:vertAlign", namespaces=NS):
            run_properties.remove(vertical)


def refresh_simple_citations(
    root,
    number_by_key: dict[str, int],
    presentation: str,
) -> int:
    changed = 0
    for field in root.xpath(
        './/w:fldSimple[contains(@w:instr,"ZOTERO_ITEM CSL_CITATION")]',
        namespaces=NS,
    ):
        instruction = field.get(W + "instr")
        updated, display = updated_instruction(
            instruction, number_by_key, presentation
        )
        field.set(W + "instr", updated)
        for child in list(field):
            field.remove(child)
        result_run = make_text_run(display)
        set_run_presentation(result_run, presentation)
        field.append(result_run)
        changed += 1
    return changed


def contains_field_char(run, kind: str) -> bool:
    return bool(
        run.xpath(
            f'.//w:fldChar[@w:fldCharType="{kind}"]',
            namespaces=NS,
        )
    )


def refresh_complex_citations(
    root,
    number_by_key: dict[str, int],
    presentation: str,
) -> int:
    changed = 0
    instructions = root.xpath(
        './/w:instrText[contains(.,"ZOTERO_ITEM CSL_CITATION")]',
        namespaces=NS,
    )
    for instruction_node in instructions:
        updated, display = updated_instruction(
            instruction_node.text, number_by_key, presentation
        )
        instruction_node.text = updated
        paragraph = instruction_node.xpath("ancestor::w:p[1]", namespaces=NS)[0]
        runs = paragraph.xpath(".//w:r", namespaces=NS)
        instruction_run = instruction_node.xpath("ancestor::w:r[1]", namespaces=NS)[0]
        instruction_index = runs.index(instruction_run)
        separate_index = next(
            index
            for index in range(instruction_index + 1, len(runs))
            if contains_field_char(runs[index], "separate")
        )
        end_index = next(
            index
            for index in range(separate_index + 1, len(runs))
            if contains_field_char(runs[index], "end")
        )

        # Tracked insertions/deletions can split one live Zotero field across
        # several ``w:ins`` wrappers. Preserve those wrappers and the run
        # formatting; change only the cached result text between the field's
        # separator and end characters. Word/Zotero can still refresh the live
        # field because its begin/instruction/separate/end structure is intact.
        result_nodes = []
        for run in runs[separate_index : end_index + 1]:
            result_nodes.extend(run.xpath(".//w:t", namespaces=NS))
        if not result_nodes:
            raise RuntimeError(
                "A Zotero citation field has no cached text between its "
                "separator and end characters"
            )
        result_nodes[0].text = display
        for node in result_nodes[1:]:
            node.text = ""
        for node in result_nodes:
            set_run_presentation(
                node.xpath("ancestor::w:r[1]", namespaces=NS)[0],
                presentation,
            )
        changed += 1
    return changed


def bibliography_paragraph(text: str, *, first: bool, last: bool) -> etree._Element:
    paragraph = etree.Element(W + "p")
    p_pr = etree.SubElement(paragraph, W + "pPr")
    style = etree.SubElement(p_pr, W + "pStyle")
    style.set(W + "val", "Bibliography")
    if first:
        begin_run = etree.SubElement(paragraph, W + "r")
        begin = etree.SubElement(begin_run, W + "fldChar")
        begin.set(W + "fldCharType", "begin")
        instr_run = etree.SubElement(paragraph, W + "r")
        instr = etree.SubElement(instr_run, W + "instrText")
        instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        instr.text = (
            ' ADDIN ZOTERO_BIBL {"uncited":[],"omitted":[],"custom":[]} '
            "CSL_BIBLIOGRAPHY "
        )
        separate_run = etree.SubElement(paragraph, W + "r")
        separate = etree.SubElement(separate_run, W + "fldChar")
        separate.set(W + "fldCharType", "separate")
    paragraph.append(make_text_run(text))
    if last:
        end_run = etree.SubElement(paragraph, W + "r")
        end = etree.SubElement(end_run, W + "fldChar")
        end.set(W + "fldCharType", "end")
    return paragraph


def rebuild_bibliography(root, entries: list[str]) -> None:
    body = root.find(".//" + W + "body")
    paragraphs = list(body)
    start_index = next(
        index
        for index, node in enumerate(paragraphs)
        if node.tag == W + "p"
        and node.xpath(
            './/w:instrText[contains(.,"ZOTERO_BIBL")]',
            namespaces=NS,
        )
    )
    end_index = next(
        index
        for index in range(start_index, len(paragraphs))
        if paragraphs[index].tag == W + "p"
        and paragraphs[index].xpath(
            './/w:fldChar[@w:fldCharType="end"]',
            namespaces=NS,
        )
    )
    for node in paragraphs[start_index : end_index + 1]:
        body.remove(node)
    for offset, entry in enumerate(entries):
        paragraph = bibliography_paragraph(
            f"{offset + 1}. {html.unescape(entry)}",
            first=offset == 0,
            last=offset == len(entries) - 1,
        )
        body.insert(start_index + offset, paragraph)


def refresh_docx(path: Path, output: Path) -> dict:
    with zipfile.ZipFile(path, "r") as source:
        parser = etree.XMLParser(remove_blank_text=False)
        source_root = etree.fromstring(source.read("word/document.xml"), parser)
    ordered_keys = ordered_citation_keys(source_root)
    presentation = citation_presentation(source_root)
    entries = fetch_nlm_bibliography(ordered_keys)
    number_by_key = {key: index + 1 for index, key in enumerate(ordered_keys)}
    temp = output.with_suffix(".refresh-tmp.docx")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
        temp, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                parser = etree.XMLParser(remove_blank_text=False)
                root = etree.fromstring(data, parser)
                simple = refresh_simple_citations(
                    root, number_by_key, presentation
                )
                complex_count = refresh_complex_citations(
                    root, number_by_key, presentation
                )
                rebuild_bibliography(root, entries)
                data = etree.tostring(
                    root,
                    xml_declaration=True,
                    encoding="UTF-8",
                    standalone=True,
                )
            target.writestr(item, data)
    temp.replace(output)
    return {
        "simple_citation_fields": simple,
        "complex_citation_fields": complex_count,
        "bibliography_entries": len(entries),
        "ordered_keys": ordered_keys,
        "citation_presentation": presentation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.docx
    result = refresh_docx(args.docx, output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
