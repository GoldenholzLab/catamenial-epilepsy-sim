"""Update the v15 exact Herzog results with tracked OOXML replacements."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def accepted_text(element):
    return "".join(
        node.text or "" for node in element.findall(".//w:t", NS)
        if not node.xpath("ancestor::w:del", namespaces=NS)
    )


def update(document: Path, summary: Path, audit_dir: Path):
    with summary.open() as stream:
        results = {row["cohort"]: row for row in csv.DictReader(stream)}
    with ZipFile(document) as package:
        entries = [(info, package.read(info.filename)) for info in package.infolist()]
    parts = dict((info.filename, data) for info, data in entries)
    root = ET.fromstring(parts["word/document.xml"])
    settings = ET.fromstring(parts["word/settings.xml"])
    original_revisions = [ET.tostring(n) for n in root.xpath("//w:ins | //w:del", namespaces=NS)]
    original_fields = root.xpath("//w:instrText/text()", namespaces=NS)
    revision_id = max([int(v) for v in root.xpath("//@w:id", namespaces=NS)] + [0]) + 1
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changes = []

    def run_with_text(run, value, deleted=False):
        result = copy.deepcopy(run)
        for child in list(result):
            if child.tag != f"{{{W}}}rPr":
                result.remove(child)
        text = ET.SubElement(result, f"{{{W}}}{'delText' if deleted else 't'}")
        text.set(XML_SPACE, "preserve")
        text.text = value
        return result

    def replace(paragraph, old, new):
        nonlocal revision_id
        assert accepted_text(paragraph).count(old) == 1, (old, accepted_text(paragraph))
        matches = [n for n in paragraph.findall("w:r/w:t", NS) if old in (n.text or "")]
        assert len(matches) == 1, f"Replacement must be in one ordinary text run: {old}"
        node = matches[0]
        run = node.getparent()
        assert len(run.findall("w:t", NS)) == 1
        assert all(child.tag in {f"{{{W}}}rPr", f"{{{W}}}t"} for child in run)
        before, after = node.text.split(old, 1)
        position = paragraph.index(run)
        replacement = []
        if before:
            replacement.append(run_with_text(run, before))
        for tag, value, deleted in [("del", old, True), ("ins", new, False)]:
            revision = ET.Element(f"{{{W}}}{tag}")
            revision.set(f"{{{W}}}id", str(revision_id))
            revision_id += 1
            revision.set(f"{{{W}}}author", "Codex")
            revision.set(f"{{{W}}}date", timestamp)
            revision.append(run_with_text(run, value, deleted))
            replacement.append(revision)
        if after:
            replacement.append(run_with_text(run, after))
        paragraph.remove(run)
        for offset, element in enumerate(replacement):
            paragraph.insert(position + offset, element)
        changes.append({"old": old, "new": new})

    body_paragraphs = root.findall("w:body/w:p", NS)
    result_paragraphs = [p for p in body_paragraphs if "50.5% and 52.2%" in accepted_text(p)]
    assert len(result_paragraphs) == 2
    for paragraph in result_paragraphs:
        replace(paragraph, "50.5%", f"{100 * float(results['healthy_ovulatory']['false_positive_rate']):.1f}%")
        replace(paragraph, "52.2%", f"{100 * float(results['population']['false_positive_rate']):.1f}%")
    table = root.findall(".//w:tbl", NS)[1]
    rows = table.findall("w:tr", NS)
    for row_index, cohort, expected in [
        (8, "healthy_ovulatory", ["22,113 / 50,000", "50.5 (49.9–51.2)", "22.3", "55.8"]),
        (17, "population", ["18,153 / 50,000", "52.2 (51.5–53.0)", "19.0", "63.7"]),
    ]:
        cells = rows[row_index].findall("w:tc", NS)
        assert accepted_text(cells[1]) == "3 complete cycles"
        assert accepted_text(cells[2]) == "Exact Herzog 2004, any pattern"
        result = results[cohort]
        replacements = [
            f"{int(float(result['n_classifiable'])):,} / {int(float(result['n_windows'])):,}",
            f"{100 * float(result['false_positive_rate']):.1f} ({100 * float(result['wilson95_low']):.1f}–{100 * float(result['wilson95_high']):.1f})",
            f"{100 * float(result['positive_rate_all_attempted']):.1f}",
            f"{100 * float(result['indeterminate_rate']):.1f}",
        ]
        for cell, old, new in zip(cells[3:], expected, replacements):
            assert accepted_text(cell) == old
            replace(cell.find("w:p", NS), old, new)
    assert len(changes) == 12
    assert not any("50.5% and 52.2%" in accepted_text(p) for p in body_paragraphs)
    assert root.xpath("//w:instrText/text()", namespaces=NS) == original_fields
    current_revisions = [ET.tostring(n) for n in root.xpath("//w:ins | //w:del", namespaces=NS)]
    assert all(revision in current_revisions for revision in original_revisions)
    if settings.find("w:trackRevisions", NS) is None:
        ET.SubElement(settings, f"{{{W}}}trackRevisions")
    assert settings.find("w:trackRevisions", NS).get(f"{{{W}}}val", "true") not in {"0", "false", "off"}
    audit_dir.mkdir(parents=True, exist_ok=True)
    backup = audit_dir / "draft_v15_manuscript_before_exact_correction.docx"
    assert not backup.exists(), "Refusing to replace the original backup"
    shutil.copy2(document, backup)
    updated_xml = ET.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    with ZipFile(document, "w") as package:
        for info, data in entries:
            if info.filename == "word/document.xml":
                data = updated_xml
            elif info.filename == "word/settings.xml":
                data = ET.tostring(settings, xml_declaration=True, encoding="UTF-8", standalone=True)
            package.writestr(info, data)
    with ZipFile(document) as package:
        for name, original in parts.items():
            if name not in {"word/document.xml", "word/settings.xml"}:
                assert package.read(name) == original, f"Unexpected change to {name}"
    payload = {"document": str(document.resolve()), "backup": str(backup.resolve()), "changes": changes,
               "existing_revision_count": len(original_revisions), "added_revision_count": 2 * len(changes),
               "field_instruction_count": len(original_fields), "track_revisions": True}
    (audit_dir / "manuscript_change_audit.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    args = parser.parse_args()
    update(args.document, args.summary, args.audit_dir)
