"""Replace Appendix Figure A1 and clarify its diary-generation semantics.

The patch operates directly on OOXML so existing Zotero fields, the live table
of contents, section geometry, and other Word-specific structures are preserved.
"""

from __future__ import annotations

import argparse
import posixpath
import zipfile
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NS = {"w": W_NS, "a": A_NS, "r": R_NS, "pr": PR_NS}

CAPTION_LABEL = "Appendix Figure A1. "
CAPTION_TEXT = (
    "HORMONE-CYCLE diary-generation workflow. By default, cycle 1 is generated in "
    "full and diary day 1 is selected uniformly from its realized cycle days. Output "
    "then proceeds forward from that selected day through the remainder of cycle 1. "
    "If more diary days are required, the simulator generates the next complete cycle "
    "and appends its records from cycle day 1 in their original order. This cycle-level "
    "workflow repeats until the requested diary length is filled; only the final "
    "generated cycle may be partly retained. The initial phase is selected once, and "
    "no end-to-start wraparound or circular shift is used. An explicit cycle-day-1 "
    "option is available for applications that require diary day 1 to coincide with "
    "menstrual cycle day 1. A domain-separated random stream selects the initial "
    "cycle day so that this observation-boundary choice does not consume values from "
    "the patient-profile or cycle-generation random streams."
)

INPUTS_PARAGRAPH_START = "The public simulation call accepts age in years"
INPUTS_PARAGRAPH_TEXT = (
    "The public simulation call accepts age in years, diary length in days, a random "
    "seed, and optional reproductive or medical modifiers. Input validation rejects "
    "nonfinite ages, nonpositive diary lengths, and incompatible modifier combinations. "
    "The default start mode generates cycle 1 in full, selects one of its realized cycle "
    "days with equal probability, and assigns that day to diary day 1. The optional "
    "cycle-day-1 mode retains the original observation boundary. After the initial "
    "selection, records are retained in chronological order without wrapping. Another "
    "cycle is generated only when the retained diary remains shorter than the requested "
    "length. Records from the final generated cycle are retained only until the exact "
    "requested number of days is reached. Each daily row contains "
    "the calendar-day index, cycle index, day within cycle, realized cycle length, "
    "estradiol in picograms per milliliter, progesterone in nanograms per milliliter, "
    "ovulation, and bleeding. Cycle summaries report phase lengths, ovulation day, "
    "ovulatory status, bleeding days, reproductive stage, and active modifiers."
)


def paragraph_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def replace_paragraph_text(
    paragraph: etree._Element,
    *,
    label: str | None,
    text: str,
) -> None:
    paragraph_properties = paragraph.find(f"{{{W_NS}}}pPr")
    for child in list(paragraph):
        if child is not paragraph_properties:
            paragraph.remove(child)

    if label:
        label_run = etree.SubElement(paragraph, f"{{{W_NS}}}r")
        run_properties = etree.SubElement(label_run, f"{{{W_NS}}}rPr")
        etree.SubElement(run_properties, f"{{{W_NS}}}b")
        label_text = etree.SubElement(label_run, f"{{{W_NS}}}t")
        label_text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        label_text.text = label

    text_run = etree.SubElement(paragraph, f"{{{W_NS}}}r")
    text_run_properties = etree.SubElement(text_run, f"{{{W_NS}}}rPr")
    not_bold = etree.SubElement(text_run_properties, f"{{{W_NS}}}b")
    not_bold.set(f"{{{W_NS}}}val", "0")
    text_node = etree.SubElement(text_run, f"{{{W_NS}}}t")
    text_node.text = text


def patch_document(
    docx_path: Path,
    figure_path: Path,
) -> tuple[str, int]:
    with zipfile.ZipFile(docx_path, "r") as source_zip:
        document_root = etree.fromstring(source_zip.read("word/document.xml"))
        relationships_root = etree.fromstring(
            source_zip.read("word/_rels/document.xml.rels")
        )

        body = document_root.find(f"{{{W_NS}}}body")
        if body is None:
            raise RuntimeError("Word document body is missing")

        body_children = list(body)
        caption_paragraph = next(
            (
                child
                for child in body_children
                if child.tag == f"{{{W_NS}}}p"
                and paragraph_text(child).startswith(CAPTION_LABEL)
            ),
            None,
        )
        if caption_paragraph is None:
            raise RuntimeError("Could not locate Appendix Figure A1 caption")

        caption_index = body_children.index(caption_paragraph)
        figure_paragraph = None
        for child in reversed(body_children[:caption_index]):
            if child.tag == f"{{{W_NS}}}p" and child.xpath(
                ".//a:blip", namespaces=NS
            ):
                figure_paragraph = child
                break
        if figure_paragraph is None:
            raise RuntimeError("Could not locate the image preceding Figure A1 caption")

        blip = figure_paragraph.xpath(".//a:blip", namespaces=NS)[0]
        relationship_id = blip.get(f"{{{R_NS}}}embed")
        if not relationship_id:
            raise RuntimeError("Figure A1 image has no embedded relationship")

        relationship = relationships_root.xpath(
            f'./pr:Relationship[@Id="{relationship_id}"]',
            namespaces=NS,
        )
        if len(relationship) != 1:
            raise RuntimeError("Could not resolve Figure A1 image relationship")
        relationship_target = relationship[0].get("Target")
        if not relationship_target:
            raise RuntimeError("Figure A1 image relationship has no target")
        image_member = posixpath.normpath(
            posixpath.join("word", relationship_target)
        )

        replace_paragraph_text(
            caption_paragraph,
            label=CAPTION_LABEL,
            text=CAPTION_TEXT,
        )

        inputs_paragraphs = [
            child
            for child in body_children
            if child.tag == f"{{{W_NS}}}p"
            and paragraph_text(child).startswith(INPUTS_PARAGRAPH_START)
        ]
        if len(inputs_paragraphs) != 1:
            raise RuntimeError(
                f"Expected one inputs paragraph, found {len(inputs_paragraphs)}"
            )
        replace_paragraph_text(
            inputs_paragraphs[0],
            label=None,
            text=INPUTS_PARAGRAPH_TEXT,
        )

        updated_document_xml = etree.tostring(
            document_root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone="yes",
        )
        figure_bytes = figure_path.read_bytes()

        temp_path = docx_path.with_suffix(".figure-a1.tmp.docx")
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as target_zip:
            for item in source_zip.infolist():
                if item.filename == "word/document.xml":
                    target_zip.writestr(item, updated_document_xml)
                elif item.filename == image_member:
                    target_zip.writestr(item, figure_bytes)
                else:
                    target_zip.writestr(item, source_zip.read(item.filename))

    temp_path.replace(docx_path)
    return image_member, len(CAPTION_TEXT.split())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", type=Path)
    parser.add_argument("figure", type=Path)
    args = parser.parse_args()
    image_member, caption_words = patch_document(args.docx, args.figure)
    print(
        f"Updated {args.docx}: replaced {image_member}; "
        f"Figure A1 caption now contains {caption_words} words."
    )


if __name__ == "__main__":
    main()
