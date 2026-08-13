#!/usr/bin/env python3
"""Update v11 manuscript DOCX files from repaired hormone and analysis outputs.

The updater edits OOXML parts directly. It preserves all unrelated package parts,
including live Zotero fields, styles, numbering, relationships, and custom XML.
The appendix output contains equation markers; the native-equation workflow replaces
those markers in a separate audited step.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import struct
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from lxml import etree


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W, "m": M, "a": A, "wp": WP, "r": R, "pr": PR}

EQUATION_IDS = [
    "cycle_irregularity",
    "lognormal_sigma",
    "lognormal_mu",
    "pchip_basis",
    "pchip_interpolation",
    "bridged_hormone_noise",
    "herzog_c1",
    "herzog_c2",
    "herzog_c3",
    "nb_c1_c2_model",
    "nb_dispersion",
    "nb_c3_model",
]

WORD_PATTERN = re.compile(
    r"\b(?:[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:[’'\-–][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*)\b"
)

COHORT_LABELS = {
    "healthy_ovulatory": "Healthy ovulatory",
    "population": "Heterogeneous menstruating-age",
}
SCENARIO_LABELS = {
    "pcos": "Polycystic ovary syndrome",
    "cyclic_ocp": "Cyclic combined oral contraceptive",
    "continuous_ocp": "Continuous combined oral contraceptive",
    "hormonal_iud": "Levonorgestrel-releasing intrauterine device",
    "copper_iud": "Copper intrauterine device",
    "perimenopause": "Perimenopause",
    "peri_menarche": "Early postmenarche",
    "dysmenorrhea": "Primary dysmenorrhea",
}


def qn(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def text_of(element: etree._Element) -> str:
    return "".join(element.xpath(".//w:t/text()", namespaces=NS)).strip()


def body_paragraphs(root: etree._Element) -> list[etree._Element]:
    return root.xpath("./w:body/w:p", namespaces=NS)


def find_paragraph(root: etree._Element, prefix: str) -> etree._Element:
    matches = [p for p in body_paragraphs(root) if text_of(p).startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"Expected one paragraph beginning {prefix!r}, found {len(matches)}")
    return matches[0]


def find_exact_paragraph(root: etree._Element, text: str) -> etree._Element:
    matches = [p for p in body_paragraphs(root) if text_of(p) == text]
    if len(matches) != 1:
        raise ValueError(f"Expected one paragraph equal to {text!r}, found {len(matches)}")
    return matches[0]


def set_paragraph_text(paragraph: etree._Element, text: str) -> None:
    """Replace visible paragraph content while preserving paragraph properties."""

    for child in list(paragraph):
        if child.tag != qn(W, "pPr"):
            paragraph.remove(child)
    run = etree.SubElement(paragraph, qn(W, "r"))
    node = etree.SubElement(run, qn(W, "t"))
    if text.startswith(" ") or text.endswith(" "):
        node.set(qn(XML, "space"), "preserve")
    node.text = text


def insert_paragraph_after(paragraph: etree._Element, text: str) -> etree._Element:
    """Insert a paragraph using the reference paragraph's paragraph properties."""

    inserted = copy.deepcopy(paragraph)
    set_paragraph_text(inserted, text)
    parent = paragraph.getparent()
    parent.insert(parent.index(paragraph) + 1, inserted)
    return inserted


def final_text_of(element: etree._Element) -> str:
    """Return Word final-view text: tracked insertions included, deletions omitted."""

    return "".join(
        element.xpath(
            ".//w:t[not(ancestor::w:del) and not(ancestor::w:moveFrom)]/text()",
            namespaces=NS,
        )
    ).strip()


def word_count(text: str) -> int:
    """Count display words consistently for the title-page compliance metrics."""

    return len(WORD_PATTERN.findall(text))


def paragraphs_between(
    root: etree._Element,
    start_prefix: str,
    end_prefix: str,
    *,
    include_start: bool = False,
) -> list[etree._Element]:
    paragraphs = body_paragraphs(root)
    start = paragraphs.index(find_exact_paragraph(root, start_prefix))
    end = paragraphs.index(find_exact_paragraph(root, end_prefix))
    return paragraphs[start if include_start else start + 1 : end]


def refresh_main_title_page_counts(root: etree._Element) -> tuple[int, int]:
    """Recompute abstract and main-text counts from final-view manuscript text."""

    abstract = " ".join(
        final_text_of(paragraph)
        for paragraph in paragraphs_between(root, "Abstract", "Key Points")
    )
    main_text = " ".join(
        final_text_of(paragraph)
        for paragraph in paragraphs_between(
            root, "Introduction", "Acknowledgments", include_start=True
        )
    )
    abstract_words = word_count(abstract)
    main_text_words = word_count(main_text)
    set_paragraph_text(
        find_paragraph(root, "Abstract word count:"),
        f"Abstract word count: {abstract_words}",
    )
    set_paragraph_text(
        find_paragraph(root, "Main-text word count"),
        "Main-text word count (Introduction through Discussion, including headings): "
        f"{main_text_words}",
    )
    return abstract_words, main_text_words


def replace_literal(paragraph: etree._Element, old: str, new: str) -> None:
    for node in paragraph.xpath(".//w:t", namespaces=NS):
        if old in (node.text or ""):
            node.text = (node.text or "").replace(old, new)
            return
    raise ValueError(f"Could not replace {old!r} in paragraph {text_of(paragraph)!r}")


def make_text_run(text: str) -> etree._Element:
    run = etree.Element(qn(W, "r"))
    node = etree.SubElement(run, qn(W, "t"))
    if text.startswith(" ") or text.endswith(" "):
        node.set(qn(XML, "space"), "preserve")
    node.text = text
    return run


def make_ref_runs(bookmark: str, cached_number: int) -> list[etree._Element]:
    runs: list[etree._Element] = []
    begin = etree.Element(qn(W, "r"))
    etree.SubElement(begin, qn(W, "fldChar")).set(qn(W, "fldCharType"), "begin")
    runs.append(begin)
    instruction_run = etree.Element(qn(W, "r"))
    instruction = etree.SubElement(instruction_run, qn(W, "instrText"))
    instruction.set(qn(XML, "space"), "preserve")
    instruction.text = f" REF {bookmark} \\h "
    runs.append(instruction_run)
    separate = etree.Element(qn(W, "r"))
    etree.SubElement(separate, qn(W, "fldChar")).set(qn(W, "fldCharType"), "separate")
    runs.append(separate)
    runs.append(make_text_run(f"({cached_number})"))
    end = etree.Element(qn(W, "r"))
    etree.SubElement(end, qn(W, "fldChar")).set(qn(W, "fldCharType"), "end")
    runs.append(end)
    return runs


def replace_with_ref_sequence(
    paragraph: etree._Element,
    literal: str,
    segments: Sequence[str | tuple[str, int]],
) -> None:
    """Replace a literal inside one text run with text and live REF field segments."""

    for node in paragraph.xpath(".//w:t", namespaces=NS):
        current = node.text or ""
        if literal not in current:
            continue
        before, after = current.split(literal, 1)
        run = node.getparent()
        parent = run.getparent()
        insert_at = parent.index(run) + 1
        node.text = before
        if before.startswith(" ") or before.endswith(" "):
            node.set(qn(XML, "space"), "preserve")
        generated: list[etree._Element] = []
        for segment in segments:
            if isinstance(segment, str):
                generated.append(make_text_run(segment))
            else:
                bookmark, number = segment
                generated.extend(make_ref_runs(bookmark, number))
        generated.append(make_text_run(after))
        for element in generated:
            parent.insert(insert_at, element)
            insert_at += 1
        return
    raise ValueError(f"Could not replace reference literal {literal!r}")


def set_cell_text(cell: etree._Element, text: object) -> None:
    paragraphs = cell.xpath("./w:p", namespaces=NS)
    if not paragraphs:
        paragraph = etree.SubElement(cell, qn(W, "p"))
    else:
        paragraph = paragraphs[0]
    set_paragraph_text(paragraph, str(text))
    for extra in paragraphs[1:]:
        cell.remove(extra)


def set_table_rows(table: etree._Element, rows: Sequence[Sequence[object]]) -> None:
    current_rows = table.xpath("./w:tr", namespaces=NS)
    if len(current_rows) < 2:
        raise ValueError("Table requires a header and at least one data-row template")
    template = current_rows[1]
    for row in current_rows[1:]:
        table.remove(row)
    for values in rows:
        row = copy.deepcopy(template)
        cells = row.xpath("./w:tc", namespaces=NS)
        if len(cells) != len(values):
            raise ValueError(f"Expected {len(cells)} cells, received {len(values)} values")
        for cell, value in zip(cells, values):
            set_cell_text(cell, value)
        table.append(row)


def replace_table_cell(table: etree._Element, row_index: int, column_index: int, text: str) -> None:
    row = table.xpath("./w:tr", namespaces=NS)[row_index]
    cell = row.xpath("./w:tc", namespaces=NS)[column_index]
    set_cell_text(cell, text)


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


def update_drawing_aspect(root: etree._Element, relationship_id: str, image_path: Path) -> None:
    blips = root.xpath(f'.//a:blip[@r:embed="{relationship_id}"]', namespaces=NS)
    if len(blips) != 1:
        raise ValueError(f"Expected one drawing for {relationship_id}, found {len(blips)}")
    drawing = blips[0]
    while drawing is not None and etree.QName(drawing).localname not in {"inline", "anchor"}:
        drawing = drawing.getparent()
    if drawing is None:
        raise ValueError(f"No inline or anchor container for {relationship_id}")
    extent = drawing.find(qn(WP, "extent"))
    if extent is None:
        raise ValueError(f"No WordprocessingML extent for {relationship_id}")
    width_emu = int(extent.get("cx"))
    width_px, height_px = png_dimensions(image_path)
    height_emu = round(width_emu * height_px / width_px)
    extent.set("cy", str(height_emu))
    for graphic_extent in drawing.xpath(".//a:xfrm/a:ext", namespaces=NS):
        graphic_extent.set("cx", str(width_emu))
        graphic_extent.set("cy", str(height_emu))


def read_docx(path: Path) -> tuple[dict[str, bytes], etree._Element, etree._Element]:
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    return (
        entries,
        etree.fromstring(entries["word/document.xml"]),
        etree.fromstring(entries["word/_rels/document.xml.rels"]),
    )


def write_docx(
    output: Path,
    entries: dict[str, bytes],
    root: etree._Element,
    media_updates: dict[str, Path],
    relationships: etree._Element | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = dict(entries)
    entries["word/document.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone="yes"
    )
    if relationships is not None:
        entries["word/_rels/document.xml.rels"] = etree.tostring(
            relationships,
            xml_declaration=True,
            encoding="UTF-8",
            standalone="yes",
        )
    for target, path in media_updates.items():
        entries[f"word/{target}"] = path.read_bytes()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


def relationship_map(relationships: etree._Element) -> dict[str, str]:
    return {node.get("Id"): node.get("Target") for node in relationships}


def format_percent(value: float, digits: int = 1) -> str:
    return f"{100 * float(value):.{digits}f}%"


def format_main_percent(value: float, digits: int = 1) -> str:
    return f"{100 * float(value):.{digits}f}"


def full_window_row(summary: pd.DataFrame, cohort: str, definition: str) -> pd.Series:
    query = summary[
        (summary["table_type"] == "window_false_positive")
        & (summary["subset"] == "all")
        & (summary["cohort"] == cohort)
        & (summary["phase_mode"] == "strict_herzog")
        & (summary["window_type"] == "full")
        & (summary["definition"] == definition)
    ]
    if len(query) != 1:
        raise ValueError(f"Expected one full-window row for {cohort}/{definition}, found {len(query)}")
    return query.iloc[0]


def result_row(
    summary: pd.DataFrame,
    cohort: str,
    window_type: str,
    window_value: object,
    definition: str,
) -> pd.Series:
    query = summary[
        (summary["table_type"] == "window_false_positive")
        & (summary["subset"] == "all")
        & (summary["cohort"] == cohort)
        & (summary["phase_mode"] == "strict_herzog")
        & (summary["window_type"] == window_type)
        & (summary["window_value"].astype(str) == str(window_value))
        & (summary["definition"] == definition)
    ]
    if len(query) != 1:
        raise ValueError(
            f"Expected one result row for {cohort}/{window_type}/{window_value}/{definition}, found {len(query)}"
        )
    return query.iloc[0]


def main_table_1(participants: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    for cohort in ["healthy_ovulatory", "population"]:
        group = participants[participants["cohort"] == cohort]
        rows.append(
            [
                COHORT_LABELS[cohort],
                f"{group['participant_id'].nunique():,}",
                f"{group['age'].mean():.1f}",
                f"{group['age'].std():.1f}",
                f"{group['mean_cycle_length'].mean():.2f}",
                f"{group['sd_cycle_length'].mean():.2f}",
                format_percent(group["ovulatory_fraction"].mean()),
                f"{group['seizure_days_per_month'].mean():.2f}",
                f"{group['seizures_per_month'].mean():.2f}",
            ]
        )
    return rows


def main_table_2(summary: pd.DataFrame) -> list[list[str]]:
    specs = [
        ("healthy_ovulatory", "36-month full diary", "full", "full_diary", "A_windowed_any", "Windowed Herzog thresholds"),
        ("healthy_ovulatory", "", "full", "full_diary", "A_windowed_C1_or_C2", "Windowed Herzog C1/C2 union"),
        ("healthy_ovulatory", "", "full", "full_diary", "B_minimum_data_C1_or_C2", "Herzog C1/C2 + ≥4 seizure-day minimum"),
        ("healthy_ovulatory", "", "full", "full_diary", "D_nb_regression_C1_or_C2", "Negative-binomial C1/C2 calibration"),
        ("healthy_ovulatory", "3-month calendar", "calendar", 3, "A_windowed_any", "Windowed Herzog thresholds"),
        ("healthy_ovulatory", "3 complete cycles", "cycle", 3, "A_exact_any", "Exact Herzog 2004, any pattern"),
        ("population", "36-month full diary", "full", "full_diary", "A_windowed_any", "Windowed Herzog thresholds"),
        ("population", "", "full", "full_diary", "A_windowed_C1_or_C2", "Windowed Herzog C1/C2 union"),
        ("population", "", "full", "full_diary", "A_windowed_C3_only", "Windowed Herzog C3 only"),
        ("population", "", "full", "full_diary", "B_minimum_data_C1_or_C2", "Herzog C1/C2 + ≥4 seizure-day minimum"),
        ("population", "", "full", "full_diary", "D_nb_regression_C1_or_C2", "Negative-binomial C1/C2 calibration"),
        ("population", "3-month calendar", "calendar", 3, "A_windowed_any", "Windowed Herzog thresholds"),
        ("population", "3 complete cycles", "cycle", 3, "A_exact_any", "Exact Herzog 2004, any pattern"),
    ]
    rows: list[list[str]] = []
    last_cohort = None
    for cohort, window_label, window_type, window_value, definition, definition_label in specs:
        row = result_row(summary, cohort, window_type, window_value, definition)
        cohort_label = COHORT_LABELS[cohort] if cohort != last_cohort else ""
        last_cohort = cohort
        rows.append(
            [
                cohort_label,
                window_label,
                definition_label,
                f"{int(row['n_classifiable']):,} / {int(row['n_windows']):,}",
                f"{format_main_percent(row['false_positive_rate'])} ({format_main_percent(row['wilson95_low'])}–{format_main_percent(row['wilson95_high'])})",
                format_main_percent(row["positive_rate_all_attempted"]),
                format_main_percent(row["indeterminate_rate"]),
            ]
        )
    return rows


def main_table_3(summary: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    last_cohort = None
    for cohort in ["healthy_ovulatory", "population"]:
        for n_participants in [30, 50, 100]:
            for definition, definition_label in [
                ("A_windowed_any", "Windowed Herzog thresholds"),
                ("A_windowed_C1_or_C2", "Windowed Herzog C1/C2 union"),
            ]:
                query = summary[
                    (summary["table_type"] == "study_level_3month")
                    & (summary["subset"] == "apparent_prevalence_all")
                    & (summary["cohort"] == cohort)
                    & (summary["phase_mode"] == "strict_herzog")
                    & (summary["definition"] == definition)
                    & (summary["n_participants"] == n_participants)
                ]
                if len(query) != 1:
                    raise ValueError(f"Expected one study-level row, found {len(query)}")
                row = query.iloc[0]
                cohort_label = COHORT_LABELS[cohort] if cohort != last_cohort else ""
                last_cohort = cohort
                rows.append(
                    [
                        cohort_label,
                        str(n_participants),
                        definition_label,
                        format_percent(row["false_positive_rate"]),
                        f"{format_percent(row['wilson95_low'])}–{format_percent(row['wilson95_high'])}",
                        format_percent(row["p_prevalence_ge_39_1"]),
                        format_percent(row["p_prevalence_ge_44_2"]),
                    ]
                )
    return rows


def validation_metric_label(name: str) -> str:
    if name.startswith("cycle_mean_"):
        return "Mean cycle length, age " + name.removeprefix("cycle_mean_")
    if name.startswith("cycle_irregularity_"):
        return "Adjacent-cycle difference of at least 7 days, age " + name.removeprefix("cycle_irregularity_")
    labels = {
        "follicular_mean_days": "Mean follicular interval",
        "luteal_mean_days": "Mean luteal interval",
        "bleeding_mean_days": "Mean bleeding duration",
        "estradiol_preovulatory_peak_width_days": "Estradiol preovulatory peak width at ≥80% maximum",
        "progesterone_premenstrual_withdrawal_days": "Consecutive progesterone-decline transitions before bleeding",
        "progesterone_terminal_to_peak_ratio": "Final-cycle progesterone / cycle maximum",
        "progesterone_cross_cycle_jump_ng_ml": "Progesterone jump across cycle boundary",
    }
    if name in labels:
        return labels[name]
    if name.startswith("estradiol_"):
        return "Estradiol, " + name.removeprefix("estradiol_").replace("_", " ")
    if name.startswith("progesterone_"):
        return "Progesterone, " + name.removeprefix("progesterone_").replace("_", " ")
    return name.replace("_", " ")


def validation_value(metric: dict, field: str) -> str:
    value = float(metric[field])
    name = metric["name"]
    if name.startswith("cycle_irregularity_"):
        return format_percent(value)
    if name == "progesterone_terminal_to_peak_ratio":
        return f"{value:.4f}"
    if name.startswith("progesterone_"):
        return f"{value:.2f}"
    return f"{value:.2f}"


def validation_rows(validation: dict) -> list[list[str]]:
    source_names = {
        "li_2023_awhs": "Li et al. (2023), age-stratified article tables",
        "bull_2019_natural_cycles": "Bull et al. (2019), Table 1",
        "stricker_2006_reference": "Stricker et al. (2006), Table 1B and Figure 1",
    }
    kinetic_names = {
        "estradiol_preovulatory_peak_width_days",
        "progesterone_premenstrual_withdrawal_days",
        "progesterone_terminal_to_peak_ratio",
        "progesterone_cross_cycle_jump_ng_ml",
    }
    rows: list[list[str]] = []
    for metric in validation["baseline_metrics"]:
        expected = validation_value(metric, "expected")
        lower = validation_value(metric, "lower_bound")
        upper = validation_value(metric, "upper_bound")
        if metric["name"] == "bleeding_mean_days":
            expected, lower, upper = "4.00", "2.50", "5.50"
        source = source_names[metric["citation_key"]]
        if metric["name"] in kinetic_names:
            source = "Stricker et al. (2006), daily series; prespecified kinetic smoke-check bound"
        sample = (
            "16 retained diaries balanced across eight age bands (two per band)"
            if metric["name"].startswith(("estradiol_", "progesterone_"))
            else "10,000 synthetic participants"
        )
        label = (
            validation_metric_label(metric["name"])
            .replace("20-24", "20–24")
            .replace("25-29", "25–29")
            .replace("30-34", "30–34")
            .replace("35-39", "35–39")
            .replace("40-44", "40–44")
            .replace("45-49", "45–49")
            .replace("50+", "≥50")
        )
        rows.append(
            [
                label,
                validation_value(metric, "observed"),
                expected,
                f"{lower} to {upper}",
                "Pass" if metric["passed"] else "Fail",
                source,
                sample,
            ]
        )
    return rows


def subgroup_summary_rows(validation: dict) -> list[list[str]]:
    rows: list[list[str]] = []
    baseline = validation["subgroup_analysis"]["baseline_reference"]
    payloads: list[tuple[str, dict, str]] = [("Baseline reference", baseline, "Reference")]
    for key, item in validation["subgroup_analysis"]["subgroups"].items():
        payloads.append((SCENARIO_LABELS[key], item["summary"], f"{sum(check['passed'] for check in item['checks'])}/{len(item['checks'])} passed"))
    for label, summary, checks in payloads:
        rows.append(
            [
                label,
                f"{summary['mean_cycle_days']:.2f}",
                format_percent(summary["ovulation_rate"]),
                f"{summary['mean_bleeding_days']:.2f}",
                format_percent(summary["irregularity_rate"]),
                format_percent(summary["amenorrhea_rate"]),
                checks,
            ]
        )
    return rows


def subgroup_check_rows(validation: dict) -> list[list[str]]:
    rows: list[list[str]] = []
    for key, payload in validation["subgroup_analysis"]["subgroups"].items():
        for check in payload["checks"]:
            is_fraction = any(token in check["name"] for token in ["ovulation", "irregularity", "amenorrhea"])
            is_days = any(token in check["name"] for token in ["cycle", "bleeding"])

            def value(number: float) -> str:
                if is_fraction:
                    return format_percent(number)
                if is_days:
                    return f"{number:.2f} days"
                return f"{number:.3f}"

            rows.append(
                [
                    SCENARIO_LABELS[key],
                    check["notes"],
                    value(check["observed"]),
                    f"{value(check['lower_bound'])} to {value(check['upper_bound'])}",
                    check["citation"]["short_name"],
                    "Pass" if check["passed"] else "Fail",
                ]
            )
    return rows


def cumulative_rows(data: pd.DataFrame, pattern: str, include_herzog: bool = False) -> list[list[str]]:
    thresholds = data[data["pattern"] == pattern]["threshold"].drop_duplicates().tolist()
    herzog = [100.00, 66.67, 38.10, 34.35, 21.43, 17.35, 14.97, 12.24, 10.54, 8.16, 7.48, 6.46]
    rows: list[list[str]] = []
    for index, threshold in enumerate(thresholds):
        if pattern == "C3":
            row = data[(data["pattern"] == pattern) & (data["cohort"] == "population") & (data["threshold"] == threshold)].iloc[0]
            rows.append([f"{threshold:g}", f"{int(row['n_at_or_above']):,}", f"{row['pct_defined_at_or_above']:.2f}"])
        else:
            healthy = data[(data["pattern"] == pattern) & (data["cohort"] == "healthy_ovulatory") & (data["threshold"] == threshold)].iloc[0]
            population = data[(data["pattern"] == pattern) & (data["cohort"] == "population") & (data["threshold"] == threshold)].iloc[0]
            values = [
                f"{threshold:g}",
                f"{int(healthy['n_at_or_above']):,}",
                f"{healthy['pct_defined_at_or_above']:.2f}",
                f"{int(population['n_at_or_above']):,}",
                f"{population['pct_defined_at_or_above']:.2f}",
            ]
            if include_herzog:
                values.append(f"{herzog[index]:.2f}")
            rows.append(values)
    return rows


def ratio_audit_rows(windows: pd.DataFrame) -> list[list[str]]:
    base = windows[
        (windows["phase_mode"] == "strict_herzog")
        & (windows["window_type"] == "cycle")
        & (windows["window_value"].astype(str) == "3")
    ]
    specs = [
        ("Type C1", "healthy_ovulatory", "rr_C1", None, 1.69),
        ("Type C1", "population", "rr_C1", None, 1.69),
        ("Type C2", "healthy_ovulatory", "rr_C2", None, 1.83),
        ("Type C2", "population", "rr_C2", None, 1.83),
        ("Type C3", "population", "rr_C3", "c3_applicable_flag", 1.62),
    ]
    rows: list[list[str]] = []
    for label, cohort, ratio, applicable, threshold in specs:
        group = base[base["cohort"] == cohort]
        if applicable:
            group = group[group[applicable].fillna(False).astype(bool)]
        values = group[ratio]
        finite = int(np.isfinite(values).sum())
        positive_infinity = int(np.isposinf(values).sum())
        undefined = int(values.isna().sum())
        at_or_above = int((values >= threshold).sum())
        share = 100 * positive_infinity / at_or_above if at_or_above else math.nan
        rows.append(
            [
                label,
                "Healthy ovulatory" if cohort == "healthy_ovulatory" else "Heterogeneous",
                f"{finite:,}",
                f"{positive_infinity:,}",
                f"{undefined:,}",
                f"{at_or_above:,}",
                f"{positive_infinity:,} ({share:.1f}%)",
            ]
        )
    return rows


def c3_sensitivity_rows(data: pd.DataFrame) -> list[list[str]]:
    order = {"calendar": 0, "cycle": 1, "full": 2}
    data = data.assign(_order=data["window_type"].map(order)).sort_values(["_order", "window_value"], key=lambda s: pd.to_numeric(s, errors="coerce") if s.name == "window_value" else s)
    rows: list[list[str]] = []
    for _, row in data.iterrows():
        if row["window_type"] == "calendar":
            window = f"{int(float(row['window_value']))} month" + ("s" if int(float(row["window_value"])) != 1 else "")
        elif row["window_type"] == "cycle":
            window = f"{int(float(row['window_value']))} complete cycles"
        else:
            window = "36 months"
        rows.append(
            [
                window,
                f"{int(row['n_applicable']):,}",
                f"{int(row['n_classifiable']):,}",
                f"{int(row['positives']):,}",
                f"{format_percent(row['false_positive_rate_classifiable'])} ({format_percent(row['wilson95_low'])}–{format_percent(row['wilson95_high'])})",
                format_percent(row["positive_rate_all_attempted"]),
            ]
        )
    return rows


def minimum_data_rows(data: pd.DataFrame) -> list[list[str]]:
    keep = data[
        (data["window_type"].isin(["calendar", "full"]))
        & (
            ((data["window_type"] == "calendar") & (pd.to_numeric(data["window_value"], errors="coerce").isin([4, 6, 12])))
            | (data["window_type"] == "full")
        )
    ].copy()
    keep["months"] = np.where(keep["window_type"] == "full", 36, pd.to_numeric(keep["window_value"], errors="coerce"))
    keep["cohort_order"] = keep["cohort"].map({"healthy_ovulatory": 0, "population": 1})
    keep = keep.sort_values(["min_seizure_days", "cohort_order", "months"])
    rows: list[list[str]] = []
    for _, row in keep.iterrows():
        rows.append(
            [
                "Healthy ovulatory" if row["cohort"] == "healthy_ovulatory" else "Heterogeneous",
                f"{int(row['months'])} months",
                str(int(row["min_seizure_days"])),
                f"{int(row['n_classifiable']):,}",
                f"{int(row['positives']):,}",
                f"{format_percent(row['false_positive_rate_classifiable'])} ({format_percent(row['wilson95_low'])}–{format_percent(row['wilson95_high'])})",
                format_percent(row["positive_rate_all_attempted"]),
            ]
        )
    return rows


def exploratory_row(data: pd.DataFrame) -> list[list[str]]:
    row = data.iloc[0]
    return [[
        f"{int(row['n_attempted_audit_participants']):,}",
        f"{int(row['n_ratio_c3_applicable']):,}",
        f"{int(row['n_nb_classifiable']):,}",
        f"{int(row['positives']):,}",
        f"{format_percent(row['false_positive_rate_classifiable'])} ({format_percent(row['wilson95_low'])}–{format_percent(row['wilson95_high'])})",
        format_percent(row["positive_rate_all_attempted"]),
    ]]


def pattern_rows(summary: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    categories = ["none", "C1 only", "C2 only", "C1+C2", "C3 only", "C3 plus C1/C2"]
    for cohort, definition, label in [
        ("healthy_ovulatory", "A_windowed", "Healthy / windowed Herzog"),
        ("healthy_ovulatory", "B_minimum_data", "Healthy / minimum-data"),
        ("population", "A_windowed", "Heterogeneous / windowed Herzog"),
        ("population", "B_minimum_data", "Heterogeneous / minimum-data"),
    ]:
        group = summary[
            (summary["table_type"] == "pattern_decomposition")
            & (summary["phase_mode"] == "strict_herzog")
            & (summary["window_type"] == "full")
            & (summary["cohort"] == cohort)
            & (summary["definition"] == definition)
        ]
        lookup = group.set_index("pattern_category")
        indeterminate = float(group["indeterminate_rate"].iloc[0])
        values = [format_percent(float(lookup.loc[category, "positive_rate_all_attempted"])) for category in categories]
        if cohort == "healthy_ovulatory":
            values[-2:] = ["N/A", "N/A"]
        rows.append([label, values[0], format_percent(indeterminate), *values[1:]])
    return rows


def update_main_document(source: Path, output: Path, outputs: Path, supplement: Path) -> None:
    entries, root, relationships = read_docx(source)
    tables = root.xpath("./w:body/w:tbl", namespaces=NS)
    if len(tables) != 3:
        raise ValueError(f"Expected 3 main-manuscript tables, found {len(tables)}")
    participants = pd.read_parquet(outputs / "participant_summary.parquet")
    summary = pd.read_csv(outputs / "summary_tables.csv")
    supplement_summary = pd.read_csv(supplement / "tableS6_c3_nb_exploratory_summary.csv")
    exploratory = supplement_summary.iloc[0]

    set_table_rows(tables[0], main_table_1(participants))
    set_table_rows(tables[1], main_table_2(summary))
    set_table_rows(tables[2], main_table_3(summary))

    insert_paragraph_after(
        find_paragraph(root, "Daniel M. Goldenholz, MD, PhD¹"),
        "Author emails and ORCID iDs: Daniel M. Goldenholz, daniel.goldenholz@bidmc.harvard.edu, 0000-0002-8370-2758; Wesley T. Kerr, kerrw@pitt.edu, 0000-0002-5546-5951; Sharon Chiang, sharon.chiang@ucsf.edu, 0000-0002-4548-4550; M. Brandon Westover, mbwest@stanford.edu, 0000-0003-4803-312X; Rachael L. Sumner, rachael.sumner@aut.ac.nz, 0000-0002-2652-4617.",
    )
    set_paragraph_text(
        find_paragraph(root, "Supporting information:"),
        "Supporting information: Appendix S1; Appendix Tables A1–A8 and Figures A1–A2; Tables S1–S8 and Figures S1–S5",
    )

    healthy_any = full_window_row(summary, "healthy_ovulatory", "A_windowed_any")
    population_any = full_window_row(summary, "population", "A_windowed_any")
    population_c12 = full_window_row(summary, "population", "A_windowed_C1_or_C2")
    population_c3 = full_window_row(summary, "population", "A_windowed_C3_only")
    healthy_3m = result_row(summary, "healthy_ovulatory", "calendar", 3, "A_windowed_any")
    population_3m = result_row(summary, "population", "calendar", 3, "A_windowed_any")
    healthy_exact = result_row(summary, "healthy_ovulatory", "cycle", 3, "A_exact_any")
    population_exact = result_row(summary, "population", "cycle", 3, "A_exact_any")
    healthy_nb = full_window_row(summary, "healthy_ovulatory", "D_nb_regression_C1_or_C2")
    population_nb = full_window_row(summary, "population", "D_nb_regression_C1_or_C2")

    set_paragraph_text(
        find_paragraph(root, "Results: Three-month false-positive rates"),
        f"Results: Three-month false-positive rates were {format_main_percent(healthy_3m['false_positive_rate'])}% in the healthy ovulatory cohort and "
        f"{format_main_percent(population_3m['false_positive_rate'])}% in the heterogeneous cohort. In 36-month windows, CE was classified in "
        f"{format_main_percent(healthy_any['false_positive_rate'])}% and {format_main_percent(population_any['false_positive_rate'])}%, respectively. "
        f"In the heterogeneous cohort, the C1/C2 rate was {format_main_percent(population_c12['false_positive_rate'])}%, "
        f"whereas C3 occurred in {format_main_percent(population_c3['false_positive_rate'])}% of applicable windows. C1/C2 negative-binomial rates were "
        f"{format_main_percent(healthy_nb['false_positive_rate'])}% and {format_main_percent(population_nb['false_positive_rate'])}%; the exploratory C3 model was positive in "
        f"{format_percent(exploratory['false_positive_rate_classifiable'])} of classifiable audit participants (95% confidence interval, {format_percent(exploratory['wilson95_low'])}–{format_percent(exploratory['wilson95_high'])}).",
    )
    set_paragraph_text(
        find_paragraph(root, "The higher misclassification in the heterogeneous-cohort"),
        "The heterogeneous-cohort excess was primarily C3/inadequate-luteal-phase driven; full-diary C1/C2 rates were similar between cohorts.",
    )
    set_paragraph_text(
        find_paragraph(root, "Herzog criteria misclassified"),
        "Despite independence, 36-month Herzog false-positive rates were "
        f"{format_main_percent(healthy_any['false_positive_rate'])}% in healthy-ovulatory and "
        f"{format_main_percent(population_any['false_positive_rate'])}% in heterogeneous cohorts.",
    )
    set_paragraph_text(
        find_paragraph(root, "Reporting the exact cycle phase"),
        "Report the phase, its temporal definition, the comparison method, and prespecified minimum-data requirements.",
    )
    set_paragraph_text(
        find_paragraph(root, "The completed run included 100,000"),
        "The completed run included 100,000 synthetic participants. The healthy ovulatory cohort had "
        f"{format_percent(participants.loc[participants.cohort == 'healthy_ovulatory', 'ovulatory_fraction'].mean())} ovulatory cycles by design; "
        f"the heterogeneous cohort had {format_percent(participants.loc[participants.cohort == 'population', 'ovulatory_fraction'].mean())} ovulatory cycles, "
        "greater within-participant cycle-length variability, and similar seizure burden (Table 1). Every diary began at a randomly selected menstrual-cycle phase.",
    )
    set_paragraph_text(
        find_paragraph(root, "Three-month false-positive rates for"),
        f"Three-month false-positive rates were {format_main_percent(healthy_3m['false_positive_rate'])}% and "
        f"{format_main_percent(population_3m['false_positive_rate'])}% in the healthy and heterogeneous cohorts, respectively. "
        "Rates declined with longer monitoring but remained definition-dependent (Figure 1). Exact Herzog applied to three complete cycles yielded "
        f"{format_main_percent(healthy_exact['false_positive_rate'])}% and {format_main_percent(population_exact['false_positive_rate'])}% among classifiable windows, "
        "while many attempted windows were indeterminate. Appendix S1 reports C3 across every saved calendar and complete-cycle duration, minimum-data threshold sensitivities, and cumulative simulated C1, C2, and C3 ratio distributions.",
    )
    set_paragraph_text(
        find_paragraph(root, "The analysis most closely aligned with the original Herzog 2004 procedure"),
        "The analysis most closely aligned with the original Herzog 2004 procedure applied the same-pattern-in-two-of-three rule to exactly three complete 23–35-day cycles. "
        f"Under that definition, false-positive classification occurred in {format_main_percent(healthy_exact['false_positive_rate'])}% and "
        f"{format_main_percent(population_exact['false_positive_rate'])}% of classifiable windows in the healthy and heterogeneous cohorts, respectively, although many attempted windows were indeterminate. "
        "Even this comparison should be interpreted cautiously because the simulation represents complete independence and does not reproduce the mixture of true hormone-associated and unrelated seizure patterns present in clinical cohorts.",
    )

    reasons = json.loads(exploratory["reason_counts"])
    set_paragraph_text(
        find_paragraph(root, "As a test of simulation calibration"),
        f"The full-diary C1/C2 negative-binomial false-positive rate was {format_main_percent(healthy_nb['false_positive_rate'])}% in the healthy cohort and "
        f"{format_main_percent(population_nb['false_positive_rate'])}% in the heterogeneous cohort, close to the prespecified 5% Type I error rate. "
        f"In the 1% daily audit sample, {int(exploratory['n_ratio_c3_applicable'])} of {int(exploratory['n_attempted_audit_participants'])} heterogeneous participants had a C3-applicable ratio window, "
        f"but only {int(exploratory['n_nb_classifiable'])} met the exploratory C3 model’s four-complete-inadequate-luteal-phase-cycle and four-seizure-day requirements. "
        f"{int(exploratory['positives'])} participants were positive ({format_percent(exploratory['false_positive_rate_classifiable'])}; 95% Wilson confidence interval, "
        f"{format_percent(exploratory['wilson95_low'])}–{format_percent(exploratory['wilson95_high'])}; {format_percent(exploratory['positive_rate_all_attempted'])} of all "
        f"{int(exploratory['n_attempted_audit_participants'])} attempted participants).",
    )
    set_paragraph_text(
        find_paragraph(root, "The largest heterogeneous-cohort"),
        "The largest heterogeneous-cohort excess was C3-driven, whereas C1/C2 behavior was similar between cohorts.",
    )

    set_paragraph_text(
        find_paragraph(root, "As this was a simulation study"),
        "This study used only synthetic data. Institutional review board approval, patient consent, and clinical-trial registration were not applicable. All figures and tables are original; permission to reproduce third-party material was not applicable.",
    )
    acknowledgments_text = find_paragraph(root, "The authors thank the people")
    ai_heading = insert_paragraph_after(acknowledgments_text, "Artificial Intelligence Use Disclosure")
    insert_paragraph_after(
        ai_heading,
        "OpenAI Codex, a generative artificial intelligence coding and writing assistant, was used to assist with code review, software and notebook updates, consistency checking, and language editing. The authors retain responsibility for the accuracy, originality, and integrity of the work.",
    )
    conflict_heading = find_paragraph(root, "Conflict of Interest")
    conflict_paragraphs = body_paragraphs(root)
    conflict_index = conflict_paragraphs.index(conflict_heading) + 1
    set_paragraph_text(
        conflict_paragraphs[conflict_index],
        "DMG reports funding from NIH K23NS124656, NIH R21NS142800, and the American Board of Psychiatry and Neurology. MBW is a co-founder of, serves as a scientific advisor and consultant to, and has a personal equity interest in Beacon Biosignals. The remaining authors have no conflicts of interest to disclose.",
    )
    author_paragraphs = body_paragraphs(root)
    author_index = author_paragraphs.index(find_paragraph(root, "Daniel M. Goldenholz: Conceptualization"))
    set_paragraph_text(
        author_paragraphs[author_index],
        "Daniel M. Goldenholz: Conceptualization, methodology, software, formal analysis, visualization, writing—original draft, writing—review and editing, funding acquisition. Wesley T. Kerr: Conceptualization, methodology, validation, writing—review and editing. Sharon Chiang: Methodology, validation, writing—review and editing. M. Brandon Westover: Methodology, software, validation, writing—review and editing. Rachael L. Sumner: Methodology, validation, writing—review and editing.",
    )
    set_paragraph_text(
        find_paragraph(root, "Appendix S1 contains the simulator"),
        "Appendix S1 contains the simulator source-to-parameter map, assumption review, C3 algorithm, cumulative simulated Herzog-ratio panels, window and minimum-data sensitivities, exploratory C3 negative-binomial calibration check, pattern decomposition, feature associations, Appendix Tables A1–A8, Appendix Figures A1–A2, Tables S1–S8, and Figures S1–S5.",
    )
    set_paragraph_text(
        find_paragraph(root, "We used strict Herzog phase labeling"),
        "We used strict Herzog phase labeling and the prespecified windowed Herzog pattern-specific ratio thresholds across each participant’s full 36-month diary. CE was classified in "
        f"{format_main_percent(healthy_any['false_positive_rate'])}% of classifiable healthy-ovulatory participant-windows and in {format_main_percent(population_any['false_positive_rate'])}% of classifiable heterogeneous-cohort participant-windows under independence (Table 2). "
        f"In the heterogeneous cohort, the C1/C2 union was {format_main_percent(population_c12['false_positive_rate'])}%, whereas C3 was positive in {format_main_percent(population_c3['false_positive_rate'])}% of C3-applicable windows. "
        "Thus, the between-cohort difference in the composite endpoint was primarily driven by the simulator-generated inadequate-luteal-phase designation.",
    )
    discussion_opening = find_paragraph(root, "This study quantified the false positive classification")
    replace_literal(
        discussion_opening,
        "41.4%",
        f"{format_main_percent(healthy_3m['false_positive_rate'])}%",
    )
    replace_literal(
        discussion_opening,
        "50.5%",
        f"{format_main_percent(population_3m['false_positive_rate'])}%",
    )

    cumulative = pd.read_csv(supplement / "tableS1_cumulative_herzog_ratios.csv")
    c1_population = cumulative[
        (cumulative["pattern"] == "C1")
        & (cumulative["cohort"] == "population")
        & (cumulative["threshold"] >= 1.69)
    ].sort_values("threshold")
    herzog = np.array([38.10, 34.35, 21.43, 17.35, 14.97, 12.24, 10.54, 8.16, 7.48, 6.46])
    simulated = c1_population["pct_defined_at_or_above"].to_numpy()
    point_differences = herzog - simulated
    relative_differences = point_differences / simulated * 100
    cumulative_paragraph = find_paragraph(root, "Across cumulative C1 ratio thresholds")
    replace_literal(
        cumulative_paragraph,
        "1.16–10.72",
        f"{point_differences.min():.2f}–{point_differences.max():.2f}",
    )
    replace_literal(
        cumulative_paragraph,
        "22%–92%",
        f"{relative_differences.min():.0f}%–{relative_differences.max():.0f}%",
    )

    rels = relationship_map(relationships)
    media = {
        rels["rId8"]: outputs / "fig1_false_positive_by_window.png",
        rels["rId9"]: outputs / "fig2_pattern_decomposition.png",
        rels["rId10"]: outputs / "fig3_study_prevalence_distribution_3month.png",
    }
    for rid, path in [("rId8", media[rels["rId8"]]), ("rId9", media[rels["rId9"]]), ("rId10", media[rels["rId10"]])]:
        update_drawing_aspect(root, rid, path)
    refresh_main_title_page_counts(root)
    write_docx(output, entries, root, media, relationships)


def update_appendix_document(
    source: Path,
    output: Path,
    outputs: Path,
    supplement: Path,
    validation_path: Path,
    validation_figure: Path,
) -> None:
    entries, root, relationships = read_docx(source)
    tables = root.xpath("./w:body/w:tbl", namespaces=NS)
    if len(tables) != 19:
        raise ValueError(f"Expected 19 appendix tables, found {len(tables)}")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    run_manifest = json.loads((outputs / "manifest.json").read_text(encoding="utf-8"))
    summary = pd.read_csv(outputs / "summary_tables.csv")
    windows = pd.read_parquet(outputs / "window_results.parquet")

    # Evidence and implementation tables.
    replace_table_cell(tables[0], 3, 4, "Fourteen anchor and four kinetic smoke checks in 16 retained diaries balanced across eight age bands")
    replace_table_cell(tables[3], 9, 3, "Standard deviation 1.7 days; lower bound 9; upper bound min(17, cycle length −8)")
    replace_table_cell(
        tables[3],
        14,
        2,
        "Early follicular day 1; midfollicular 0.45 × follicular length; preovulatory centered 2 days before ovulation; ovulation at follicular length",
    )
    replace_table_cell(
        tables[3],
        14,
        3,
        "Early luteal max(2 days, 0.22 × luteal length); midluteal max(3 days, 0.55 × luteal length); late luteal cycle end −4 days; cycle end returns to the early-follicular baseline",
    )
    replace_table_cell(tables[3], 14, 4, "Derived placement plus kinetic face-validity constraints")
    replace_table_cell(tables[3], 18, 2, "Shape-preserving piecewise cubic Hermite interpolation (PCHIP) in Equations 4 and 5")
    replace_table_cell(tables[3], 18, 3, "Applied separately to estradiol and progesterone without spline overshoot")
    replace_table_cell(tables[3], 19, 2, "Stationary first-order autoregressive state with coefficient 0.92; realized paths linearly bridged to zero at both cycle endpoints")
    replace_table_cell(tables[3], 19, 3, "Estradiol stationary standard deviation equals participant noise scale; progesterone uses 0.9 × that scale")

    set_table_rows(tables[5], validation_rows(validation))
    set_table_rows(tables[6], subgroup_summary_rows(validation))
    set_table_rows(tables[7], subgroup_check_rows(validation))

    parameter_data = pd.read_csv(supplement / "tableS5_simulator_parameters_and_assumptions.csv")
    set_table_rows(
        tables[8],
        [
            [
                row["domain"],
                row["parameter"],
                row["cohort"],
                row["setting_or_sampling_distribution"],
                row["sampling_level"],
                row["source_or_rationale"],
                row["realized_validation_target"],
            ]
            for _, row in parameter_data.iterrows()
        ],
    )

    cumulative = pd.read_csv(supplement / "tableS1_cumulative_herzog_ratios.csv")
    set_table_rows(tables[11], cumulative_rows(cumulative, "C1", include_herzog=True))
    set_table_rows(tables[12], cumulative_rows(cumulative, "C2"))
    set_table_rows(tables[13], cumulative_rows(cumulative, "C3"))
    set_table_rows(tables[14], ratio_audit_rows(windows))
    c3_data = pd.read_csv(supplement / "tableS2_c3_window_sensitivity.csv")
    set_table_rows(tables[15], c3_sensitivity_rows(c3_data))
    minimum_data = pd.read_csv(supplement / "tableS3_minimum_data_sensitivity.csv")
    set_table_rows(tables[16], minimum_data_rows(minimum_data))
    exploratory = pd.read_csv(supplement / "tableS6_c3_nb_exploratory_summary.csv")
    set_table_rows(tables[17], exploratory_row(exploratory))
    set_table_rows(tables[18], pattern_rows(summary))

    set_paragraph_text(
        find_paragraph(root, "The completed manifest stores the analysis-code fingerprint"),
        "The completed manifest stores the analysis-code fingerprint "
        f"{run_manifest['analysis_code_sha256']} and configuration fingerprint "
        f"{run_manifest['analysis_config_sha256']}. These Secure Hash Algorithm 256-bit fingerprints identify the exact repaired analysis code and configuration used for the completed run.",
    )

    # Hormone-method and validation prose. Citation-bearing runs are edited in place.
    p = find_paragraph(root, "Ovulatory trajectories use seven control points")
    replace_literal(p, "smoothstep", "shape-preserving PCHIP")
    replace_literal(
        p,
        " function in Equation 4 and the interpolation in Equation 5.",
        " basis in Equation 4 and the piecewise interpolation in Equation 5. The preovulatory anchor is centered two days before ovulation, and the final four cycle days withdraw toward the early-follicular baseline before the next bleeding onset.",
    )
    set_paragraph_text(
        find_paragraph(root, "Anovulatory cycles use four lower-amplitude control points"),
        "Anovulatory cycles use four lower-amplitude control points. Person-level hormone scales are multiplied by cycle-level lognormal scales with coefficients of variation 0.08 for estradiol and 0.10 for progesterone. Day-to-day continuity is produced by a stationary first-order autoregressive process with coefficient 0.92. Each realized noise path is linearly bridged to zero at both cycle endpoints so stochastic noise cannot recreate a vertical reset.",
    )
    quality_control = find_paragraph(root, "The quality-control design follows established")
    replace_literal(
        quality_control,
        "Fourteen hormone smoke checks used 16 retained diaries.",
        "Fourteen hormone-anchor and four kinetic smoke checks used 16 retained diaries balanced across eight age bands.",
    )
    set_paragraph_text(
        find_paragraph(root, "The 14 hormone checks compare"),
        "Fourteen hormone-anchor checks compare seven estradiol and seven progesterone subphase summaries with Stricker-derived anchors. Four additional kinetic checks evaluate estradiol peak width, consecutive premenstrual progesterone withdrawal, the terminal-to-peak progesterone ratio, and cross-cycle progesterone continuity. The validation implementation retains two diaries from each of eight age bands (16 total). These checks confirm software output and approximate anchor reproduction in a small age-balanced sample. They do not establish population-level hormone validation.",
    )
    caption = find_paragraph(root, "Appendix Table A6.")
    replace_literal(caption, "The 14 hormone checks use 16 retained diaries, all from the younger-than-20 age band.", "The 18 hormone anchor and kinetic checks use 16 retained diaries balanced across eight age bands (two per band).")
    figure_caption = find_paragraph(root, "Appendix Figure A2.")
    replace_literal(figure_caption, "Internal observed-versus-target calibration.", "Internal target reproduction and kinetic checks.")
    replace_literal(
        figure_caption,
        "panel D compares estradiol and progesterone subphase summaries with Stricker et al. (2006) ",
        "panel D compares estradiol and progesterone subphase summaries with Stricker et al. (2006), and panels E and F show a complete ovulatory cycle plus the first day of the next cycle on separate estradiol and progesterone scales ",
    )
    replace_literal(
        figure_caption,
        "Panel D uses 16 retained diaries, all from the younger-than-20 age band.",
        "Panel D uses 16 retained diaries balanced across eight age bands; panels E and F use a fixed-seed representative ovulatory cycle and mark the next bleeding onset.",
    )

    # Replace equation paragraphs with stable markers and remove redundant prose definitions.
    equation_paragraphs = [p for p in body_paragraphs(root) if p.xpath(".//m:oMath", namespaces=NS)]
    if len(equation_paragraphs) != len(EQUATION_IDS):
        raise ValueError(f"Expected {len(EQUATION_IDS)} native display equations, found {len(equation_paragraphs)}")
    for paragraph, equation_id in zip(equation_paragraphs, EQUATION_IDS):
        set_paragraph_text(paragraph, f"[[EQUATION:{equation_id}]]")

    replacements = {
        "In Equation 1,": "The latent within-person standard deviation is solved numerically by bisection under the Gaussian cycle-length model. A person-specific mean is sampled around the age-band target, and a person-specific within-person standard deviation is sampled around the value obtained from Equation 1.",
        "In Equations 2 and 3,": "These parameter choices give the lognormal multiplier an arithmetic mean of one.",
        "In Equation 6,": "The stationary innovation scale preserves the requested marginal variance, and the linear bridge forces the fractional noise contribution to zero on the first and final cycle days. Each interpolated hormone value is multiplied by 1 + εd before the estradiol floor of 5 picograms per milliliter or progesterone floor of 0.05 nanograms per milliliter is applied.",
        "In Equation 10,": "Follicular and luteal days form the reference category because both phase indicators equal 0 on those days.",
        "In Equation 11,": "The implemented fallback sets dispersion to 1 when the mean is nonpositive or the sample variance does not exceed the mean. Otherwise, the method-of-moments estimate is bounded below by 10−6 and above by 50 for numerical stability.",
    }
    remove_prefixes = ["In Equations 4 and 5,", "In Equations 7–9,", "In Equation 12,"]
    for prefix, replacement in replacements.items():
        set_paragraph_text(find_paragraph(root, prefix), replacement)
    for prefix in remove_prefixes:
        paragraph = find_paragraph(root, prefix)
        paragraph.getparent().remove(paragraph)

    # Live equation references point to bookmarks created by the equation workflow.
    replace_with_ref_sequence(
        find_paragraph(root, "The latent within-person standard deviation"),
        "Equation 1",
        ["Equation ", ("Eq_cycle_irregularity", 1)],
    )
    p = find_paragraph(root, "Ovulatory trajectories use seven control points")
    replace_with_ref_sequence(p, "Equation 4", ["Equation ", ("Eq_pchip_basis", 4)])
    replace_with_ref_sequence(p, "Equation 5", ["Equation ", ("Eq_pchip_interpolation", 5)])
    p = find_paragraph(root, "Average daily seizure frequency")
    replace_with_ref_sequence(
        p,
        "Equations 7–9",
        ["Equations ", ("Eq_herzog_c1", 7), "–", ("Eq_herzog_c3", 9)],
    )
    p = find_paragraph(root, "The exploratory type C3 model restricts")
    replace_with_ref_sequence(p, "Equation 11", ["Equation ", ("Eq_nb_dispersion", 11)])
    p = find_paragraph(root, "Equation 12 gives")
    replace_with_ref_sequence(p, "Equation 12", ["Equation ", ("Eq_nb_c3_model", 12)])

    exploratory_row_data = exploratory.iloc[0]
    reasons = json.loads(exploratory_row_data["reason_counts"])
    set_paragraph_text(
        find_paragraph(root, "The retained daily audit sample was selected"),
        "The retained daily audit sample was selected independently within each cohort without replacement at a 1% fraction. NumPy’s default random-number generator used a deterministic 32-bit seed derived from master seed 20260505, the cohort name, and “audit_sample.” The heterogeneous-cohort seed was 529110050. The type C3 exploratory analysis attempted all "
        f"{int(exploratory_row_data['n_attempted_audit_participants'])} retained heterogeneous participants: {int(exploratory_row_data['n_ratio_c3_applicable'])} had ratio-level type C3 applicability, "
        f"{int(exploratory_row_data['n_nb_classifiable'])} met regression data requirements, {int(reasons.get('fewer_than_required_complete_ilp_cycles', 0))} had fewer than four complete inadequate-luteal-phase cycles, and "
        f"{int(reasons.get('seizure_days_below_minimum', 0))} had fewer than four seizure days. All {int(exploratory_row_data['n_nb_classifiable'])} classifiable participants used the negative-binomial fit; no robust-Poisson fallback or regression failure occurred. "
        f"{int(exploratory_row_data['positives'])} were positive.",
    )
    caption = find_paragraph(root, "Appendix Table S7.")
    set_paragraph_text(
        caption,
        "Appendix Table S7. Exploratory type C3 negative-binomial calibration result in the retained 1% daily audit sample. All "
        f"{int(exploratory_row_data['n_attempted_audit_participants'])} retained heterogeneous participants were attempted; {int(exploratory_row_data['n_ratio_c3_applicable'])} were ratio-applicable, "
        f"{int(exploratory_row_data['n_nb_classifiable'])} were regression-classifiable, and {int(exploratory_row_data['positives'])} were positive. “All-attempted rate” is "
        f"{int(exploratory_row_data['positives'])}/{int(exploratory_row_data['n_attempted_audit_participants'])}. The 95% Wilson interval describes Monte Carlo uncertainty under this configured simulation. No robust-Poisson fallback was used.",
    )

    rels = relationship_map(relationships)
    media: dict[str, Path] = {
        rels["rId11"]: validation_figure,
        rels["rId12"]: supplement / "figS1_seizure_process_distributions.png",
        rels["rId13"]: supplement / "figS2_seizure_rhythm_distributions.png",
        rels["rId14"]: supplement / "figS3_menstrual_cycle_distributions.png",
        rels["rId15"]: supplement / "figS4_age_and_modifier_distributions.png",
        rels["rId16"]: supplement / "figS5_simulated_classification_associations.png",
    }
    for rid in ["rId11", "rId12", "rId13", "rId14", "rId15", "rId16"]:
        update_drawing_aspect(root, rid, media[rels[rid]])
    write_docx(output, entries, root, media, relationships)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-source", type=Path, default=Path("outputs/epilepsia_submission/draft_v11.docx"))
    parser.add_argument("--appendix-source", type=Path, default=Path("outputs/epilepsia_submission/draft_v11_appendix.docx"))
    parser.add_argument("--main-output", type=Path, default=Path("outputs/epilepsia_submission/draft_v11_hormone_repaired.docx"))
    parser.add_argument("--appendix-output", type=Path, default=Path("outputs/epilepsia_submission/draft_v11_appendix_hormone_repaired_pre_equations.docx"))
    parser.add_argument("--outputs", type=Path, default=Path("outputs/random_start_full_v11_hormone_fix"))
    parser.add_argument("--supplement", type=Path, default=Path("outputs/random_start_supplement_v11_hormone_fix"))
    parser.add_argument("--validation", type=Path, default=Path("examples/reports/notebook_validation_report.json"))
    parser.add_argument("--validation-figure", type=Path, default=Path(".codex_review/v11_hormone_fix/hormone_cycle_validation_v11.png"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    update_main_document(args.main_source, args.main_output, args.outputs, args.supplement)
    update_appendix_document(
        args.appendix_source,
        args.appendix_output,
        args.outputs,
        args.supplement,
        args.validation,
        args.validation_figure,
    )
    print(args.main_output.resolve())
    print(args.appendix_output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
