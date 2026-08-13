#!/usr/bin/env python3
"""Update the user-edited draft_v5 DOCX files from direct-alignment outputs.

The source DOCX packages are treated as templates. Only the result-bearing
paragraphs, table cells, and embedded figure payloads identified below are
changed; Zotero fields and all unrelated package parts are preserved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import posixpath
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd
from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W_NS, "a": A_NS, "r": R_NS, "pr": PR_NS}
W = f"{{{W_NS}}}"

THRESHOLD_ORDER = {
    "C1": [0, 1, 1.69, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "C2": [0, 1, 1.83, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "C3": [0, 1, 1.62, 2, 3, 4, 5, 6, 7, 8, 9, 10],
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _numeric_window(series: pd.Series, value: int | float) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").eq(float(value))


def _window_row(
    summary: pd.DataFrame,
    cohort: str,
    window_type: str,
    window_value: int | None,
    definition: str,
) -> pd.Series:
    mask = (
        summary["table_type"].eq("window_false_positive")
        & summary["subset"].eq("all")
        & summary["cohort"].eq(cohort)
        & summary["phase_mode"].eq("strict_herzog")
        & summary["window_type"].eq(window_type)
        & summary["definition"].eq(definition)
    )
    if window_type != "full" and window_value is not None:
        mask &= _numeric_window(summary["window_value"], window_value)
    rows = summary.loc[mask]
    if len(rows) != 1:
        raise ValueError(
            f"Expected one summary row for {(cohort, window_type, window_value, definition)}, "
            f"found {len(rows)}"
        )
    return rows.iloc[0]


def _study_row(
    summary: pd.DataFrame,
    cohort: str,
    n_participants: int,
    definition: str,
) -> pd.Series:
    mask = (
        summary["table_type"].eq("study_level_3month")
        & summary["subset"].eq("apparent_prevalence_all")
        & summary["cohort"].eq(cohort)
        & summary["phase_mode"].eq("strict_herzog")
        & summary["definition"].eq(definition)
        & pd.to_numeric(summary["n_participants"], errors="coerce").eq(n_participants)
    )
    rows = summary.loc[mask]
    if len(rows) != 1:
        raise ValueError(
            f"Expected one study row for {(cohort, n_participants, definition)}, found {len(rows)}"
        )
    return rows.iloc[0]


def _pct(value: float, digits: int = 1) -> str:
    return f"{100 * float(value):.{digits}f}"


def _participant_subject(count: int) -> str:
    words = {
        0: "No",
        1: "One",
        2: "Two",
        3: "Three",
        4: "Four",
        5: "Five",
        6: "Six",
        7: "Seven",
        8: "Eight",
        9: "Nine",
        10: "Ten",
    }
    label = words.get(count, f"{count:,}")
    return f"{label} participant was" if count == 1 else f"{label} participants were"


def _window_result_cells(row: pd.Series) -> list[str]:
    return [
        f"{int(row.n_classifiable):,} / {int(row.n_windows):,}",
        f"{_pct(row.false_positive_rate)} "
        f"({_pct(row.wilson95_low)}–{_pct(row.wilson95_high)})",
        _pct(row.positive_rate_all_attempted),
        _pct(row.indeterminate_rate),
    ]


def main_table2_rows(summary: pd.DataFrame) -> tuple[list[list[str]], dict[str, pd.Series]]:
    rows: list[list[str]] = []
    selected: dict[str, pd.Series] = {}

    specifications = [
        ("h_full_any", "Healthy ovulatory", "healthy_ovulatory", "full", 36, "Windowed Herzog thresholds", "A_windowed_any"),
        ("h_full_c12", "", "healthy_ovulatory", "full", 36, "Windowed Herzog C1/C2 union", "A_windowed_C1_or_C2"),
        ("h_full_min", "", "healthy_ovulatory", "full", 36, "Herzog C1/C2 + ≥4 seizure-day minimum", "B_minimum_data_C1_or_C2"),
        ("h_full_nb", "", "healthy_ovulatory", "full", 36, "Negative-binomial C1/C2 calibration", "D_nb_regression_C1_or_C2"),
        ("h_3m_any", "", "healthy_ovulatory", "calendar", 3, "Windowed Herzog thresholds", "A_windowed_any"),
        ("h_3cy_exact", "", "healthy_ovulatory", "cycle", 3, "Exact Herzog 2004, any pattern", "A_exact_any"),
        ("p_full_any", "Heterogeneous menstruating-age", "population", "full", 36, "Windowed Herzog thresholds", "A_windowed_any"),
        ("p_full_c12", "", "population", "full", 36, "Windowed Herzog C1/C2 union", "A_windowed_C1_or_C2"),
        ("p_full_c3", "", "population", "full", 36, "Windowed Herzog C3 only", "A_windowed_C3_only"),
        ("p_full_min", "", "population", "full", 36, "Herzog C1/C2 + ≥4 seizure-day minimum", "B_minimum_data_C1_or_C2"),
        ("p_full_nb", "", "population", "full", 36, "Negative-binomial C1/C2 calibration", "D_nb_regression_C1_or_C2"),
        ("p_3m_any", "", "population", "calendar", 3, "Windowed Herzog thresholds", "A_windowed_any"),
        ("p_3cy_exact", "", "population", "cycle", 3, "Exact Herzog 2004, any pattern", "A_exact_any"),
    ]
    for key, display_cohort, cohort, window_type, value, definition_label, definition in specifications:
        result = _window_row(summary, cohort, window_type, value, definition)
        selected[key] = result
        if window_type == "full":
            display_window = "36-month full diary" if display_cohort else ""
        elif window_type == "calendar":
            display_window = "3-month calendar"
        else:
            display_window = "3 complete cycles"
        rows.append(
            [
                display_cohort,
                display_window,
                definition_label,
                *_window_result_cells(result),
            ]
        )
    return rows, selected


def main_table3_rows(summary: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    for cohort, cohort_label in [
        ("healthy_ovulatory", "Healthy ovulatory"),
        ("population", "Heterogeneous menstruating-age"),
    ]:
        first = True
        for n_participants in [30, 50, 100]:
            for definition, definition_label in [
                ("A_windowed_any", "Windowed Herzog thresholds"),
                ("A_windowed_C1_or_C2", "Windowed Herzog C1/C2 union"),
            ]:
                result = _study_row(summary, cohort, n_participants, definition)
                rows.append(
                    [
                        cohort_label if first else "",
                        str(n_participants),
                        definition_label,
                        f"{_pct(result.false_positive_rate)}%",
                        f"{_pct(result.wilson95_low)}%–{_pct(result.wilson95_high)}%",
                        f"{_pct(result.p_prevalence_ge_39_1)}%",
                        f"{_pct(result.p_prevalence_ge_44_2)}%",
                    ]
                )
                first = False
    return rows


def main_table1_rows(participants: pd.DataFrame) -> tuple[list[list[str]], dict[str, pd.Series]]:
    """Build the manuscript cohort-summary rows from participant-level outputs."""

    grouped = participants.groupby("cohort", sort=False).agg(
        n=("participant_id", "nunique"),
        age_mean=("age", "mean"),
        age_sd=("age", "std"),
        mean_cycle_length=("mean_cycle_length", "mean"),
        mean_cycle_length_sd=("sd_cycle_length", "mean"),
        ovulatory_fraction=("ovulatory_fraction", "mean"),
        seizure_days_per_month=("seizure_days_per_month", "mean"),
        seizures_per_month=("seizures_per_month", "mean"),
    )
    rows: list[list[str]] = []
    selected: dict[str, pd.Series] = {}
    for cohort, label in [
        ("healthy_ovulatory", "Healthy ovulatory"),
        ("population", "Heterogeneous menstruating-age"),
    ]:
        row = grouped.loc[cohort]
        selected[cohort] = row
        rows.append(
            [
                label,
                f"{int(row['n']):,}",
                f"{float(row['age_mean']):.1f}",
                f"{float(row['age_sd']):.1f}",
                f"{float(row['mean_cycle_length']):.2f}",
                f"{float(row['mean_cycle_length_sd']):.2f}",
                f"{100 * float(row['ovulatory_fraction']):.1f}%",
                f"{float(row['seizure_days_per_month']):.2f}",
                f"{float(row['seizures_per_month']):.2f}",
            ]
        )
    return rows, selected


def cumulative_rows(data: pd.DataFrame, pattern: str) -> tuple[list[list[str]], str]:
    panel = data[data["pattern"].eq(pattern)]
    if pattern in {"C1", "C2"}:
        healthy = panel[panel["cohort"].eq("healthy_ovulatory")].set_index("threshold")
        population = panel[panel["cohort"].eq("population")].set_index("threshold")
        rows = []
        for threshold in THRESHOLD_ORDER[pattern]:
            h = healthy.loc[float(threshold)]
            p = population.loc[float(threshold)]
            rows.append(
                [
                    _format_threshold(threshold),
                    f"{int(h.n_at_or_above):,}",
                    f"{h.pct_defined_at_or_above:.2f}",
                    f"{int(p.n_at_or_above):,}",
                    f"{p.pct_defined_at_or_above:.2f}",
                ]
            )
        h0, p0 = healthy.iloc[0], population.iloc[0]
        note = (
            f"Note. Healthy attempted={int(h0.n_attempted):,}, defined={int(h0.n_defined):,}, "
            f"undefined={int(h0.n_undefined):,}; heterogeneous attempted={int(p0.n_attempted):,}, "
            f"defined={int(p0.n_defined):,}, undefined={int(p0.n_undefined):,}. "
            "Percentages use the defined-ratio denominator."
        )
        return rows, note

    population = panel[panel["cohort"].eq("population")].set_index("threshold")
    rows = []
    for threshold in THRESHOLD_ORDER[pattern]:
        p = population.loc[float(threshold)]
        rows.append(
            [
                _format_threshold(threshold),
                f"{int(p.n_at_or_above):,}",
                f"{p.pct_defined_at_or_above:.2f}",
            ]
        )
    p0 = population.iloc[0]
    note = (
        f"Note. Attempted={int(p0.n_attempted):,}; applicable={int(p0.n_applicable):,}; "
        f"defined={int(p0.n_defined):,}; undefined={int(p0.n_undefined):,}. "
        "The healthy cohort is not applicable and is not shown."
    )
    return rows, note


def _format_threshold(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def c3_window_rows(data: pd.DataFrame) -> list[list[str]]:
    order = {"calendar": 0, "cycle": 1, "full": 2}
    selected = data.copy()
    selected["_order"] = selected["window_type"].map(order)
    selected["_value"] = pd.to_numeric(selected["window_value"], errors="coerce").fillna(999)
    selected = selected.sort_values(["_order", "_value"])
    rows: list[list[str]] = []
    for result in selected.itertuples(index=False):
        if result.window_type == "calendar":
            number = int(float(result.window_value))
            label = f"{number} month" + ("s" if number != 1 else "")
        elif result.window_type == "cycle":
            label = f"{int(float(result.window_value))} complete cycles"
        else:
            label = "36-month full diary"
        rows.append(
            [
                label,
                f"{int(result.n_applicable):,}",
                f"{int(result.n_classifiable):,}",
                f"{int(result.positives):,}",
                f"{_pct(result.false_positive_rate_classifiable)}% "
                f"({_pct(result.wilson95_low)}%–{_pct(result.wilson95_high)}%)",
                f"{_pct(result.positive_rate_all_attempted)}%",
            ]
        )
    return rows


def minimum_data_rows(data: pd.DataFrame) -> list[list[str]]:
    selected = data[
        (
            data["window_type"].eq("calendar")
            & pd.to_numeric(data["window_value"], errors="coerce").isin([4, 6, 12, 36])
        )
        | data["window_type"].eq("full")
    ].copy()
    selected["_value"] = pd.to_numeric(selected["window_value"], errors="coerce").fillna(36)
    selected = selected.sort_values(["cohort", "_value", "min_seizure_days"])
    rows: list[list[str]] = []
    for result in selected.itertuples(index=False):
        window = (
            "36-month full diary"
            if result.window_type == "full"
            else f"{int(float(result.window_value))} months"
        )
        classifiable_rate = (
            "—"
            if pd.isna(result.false_positive_rate_classifiable)
            else f"{_pct(result.false_positive_rate_classifiable)}%"
        )
        rows.append(
            [
                "Healthy" if result.cohort == "healthy_ovulatory" else "Heterogeneous",
                window,
                str(int(result.min_seizure_days)),
                f"{int(result.n_classifiable):,}",
                classifiable_rate,
                f"{_pct(result.positive_rate_all_attempted)}%",
            ]
        )
    return rows


def pattern_rows(summary: pd.DataFrame) -> list[list[str]]:
    rows: list[list[str]] = []
    for cohort, cohort_label in [
        ("healthy_ovulatory", "Healthy"),
        ("population", "Heterogeneous"),
    ]:
        for definition, definition_label in [
            ("A_windowed", "windowed Herzog"),
            ("B_minimum_data", "minimum-data"),
        ]:
            data = summary[
                summary["table_type"].eq("pattern_decomposition")
                & summary["cohort"].eq(cohort)
                & summary["window_type"].eq("full")
                & summary["phase_mode"].eq("strict_herzog")
                & summary["definition"].eq(definition)
            ].copy()
            if len(data) != 6:
                raise ValueError(f"Expected six pattern rows for {(cohort, definition)}, found {len(data)}")
            values = data.set_index("pattern_category")["positive_rate_all_attempted"]
            indeterminate = float(data["indeterminate_rate"].iloc[0])
            row = [
                f"{cohort_label} / {definition_label}",
                f"{_pct(values['none'])}%",
                f"{_pct(indeterminate)}%",
                f"{_pct(values['C1 only'])}%",
                f"{_pct(values['C2 only'])}%",
                f"{_pct(values['C1+C2'])}%",
            ]
            if cohort == "healthy_ovulatory":
                row.extend(["N/A", "N/A"])
            else:
                row.extend(
                    [
                        f"{_pct(values['C3 only'])}%",
                        f"{_pct(values['C3 plus C1/C2'])}%",
                    ]
                )
            rows.append(row)
    return rows


def parameter_rows(data: pd.DataFrame) -> list[list[str]]:
    columns = [
        "domain",
        "parameter",
        "cohort",
        "setting_or_sampling_distribution",
        "sampling_level",
        "source_or_rationale",
        "realized_validation_target",
    ]
    return [[str(value) for value in row] for row in data[columns].itertuples(index=False, name=None)]


def c3_nb_row(summary: pd.Series) -> list[str]:
    return [
        str(int(summary["n_attempted_audit_participants"])),
        str(int(summary["n_ratio_c3_applicable"])),
        str(int(summary["n_nb_classifiable"])),
        str(int(summary["positives"])),
        f"{_pct(summary['false_positive_rate_classifiable'])}% "
        f"({_pct(summary['wilson95_low'])}%–{_pct(summary['wilson95_high'])}%)",
        f"{_pct(summary['positive_rate_all_attempted'])}%",
    ]


def sparse_comparator_rows(window_results: pd.DataFrame) -> list[list[str]]:
    """Audit finite, positive-infinite, and undefined pooled ratio values."""

    base = window_results[
        (window_results["phase_mode"] == "strict_herzog")
        & (window_results["window_type"] == "cycle")
        & pd.to_numeric(window_results["window_value"], errors="coerce").eq(3)
    ].copy()
    rows: list[list[str]] = []
    specifications = [
        ("C1", "healthy_ovulatory", "Healthy ovulatory", 1.69),
        ("C1", "population", "Heterogeneous", 1.69),
        ("C2", "healthy_ovulatory", "Healthy ovulatory", 1.83),
        ("C2", "population", "Heterogeneous", 1.83),
        ("C3", "population", "Heterogeneous", 1.62),
    ]
    for pattern, cohort, cohort_label, threshold in specifications:
        group = base[base["cohort"] == cohort].copy()
        if pattern == "C3":
            group = group[group["c3_applicable_flag"].fillna(False).astype(bool)]
        values = pd.to_numeric(group[f"rr_{pattern}"], errors="coerce")
        finite = int(np.isfinite(values).sum())
        positive_infinite = int(np.isposinf(values).sum())
        undefined = int(values.isna().sum())
        at_or_above = int((values >= threshold).sum())
        share = (
            100.0 * positive_infinite / at_or_above if at_or_above else float("nan")
        )
        rows.append(
            [
                f"Type {pattern}",
                cohort_label,
                f"{finite:,}",
                f"{positive_infinite:,}",
                f"{undefined:,}",
                f"{at_or_above:,}",
                f"{positive_infinite:,} ({share:.1f}%)",
            ]
        )
    return rows


def paragraph_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def plain_text_nodes(paragraph: etree._Element) -> list[etree._Element]:
    nodes: list[etree._Element] = []
    field_depth = 0
    for element in paragraph.iter():
        if element.tag == f"{W}fldChar":
            field_type = element.get(f"{W}fldCharType")
            if field_type == "begin":
                field_depth += 1
            elif field_type == "end":
                field_depth = max(0, field_depth - 1)
        elif element.tag == f"{W}t" and field_depth == 0:
            nodes.append(element)
    return nodes


def find_paragraph(root: etree._Element, prefix: str) -> etree._Element:
    matches = [
        paragraph
        for paragraph in root.xpath(".//w:body/w:p", namespaces=NS)
        if paragraph_text(paragraph).startswith(prefix)
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one paragraph starting with {prefix!r}, found {len(matches)}")
    return matches[0]


def find_paragraph_after_heading(root: etree._Element, heading_text: str) -> etree._Element:
    """Return the first nonempty paragraph following an exact heading paragraph."""

    paragraphs = root.xpath(".//w:body/w:p", namespaces=NS)
    for index, paragraph in enumerate(paragraphs):
        if paragraph_text(paragraph).strip() != heading_text:
            continue
        for candidate in paragraphs[index + 1 :]:
            if paragraph_text(candidate).strip():
                return candidate
    raise ValueError(f"Could not find a paragraph after heading {heading_text!r}")


def image_member_before_caption(
    root: etree._Element,
    relationships_root: etree._Element,
    caption_prefix: str,
) -> str:
    """Resolve the package member for the last image before a caption paragraph."""

    body = root.find(f"{W}body")
    if body is None:
        raise ValueError("Word document body is missing")
    children = list(body)
    captions = [
        child
        for child in children
        if child.tag == f"{W}p" and paragraph_text(child).startswith(caption_prefix)
    ]
    if len(captions) != 1:
        raise ValueError(f"Expected one caption beginning {caption_prefix!r}, found {len(captions)}")
    caption_index = children.index(captions[0])
    figure_paragraph = next(
        (
            child
            for child in reversed(children[:caption_index])
            if child.tag == f"{W}p" and child.xpath(".//a:blip", namespaces=NS)
        ),
        None,
    )
    if figure_paragraph is None:
        raise ValueError(f"No figure found before caption {caption_prefix!r}")
    blip = figure_paragraph.xpath(".//a:blip", namespaces=NS)[0]
    relationship_id = blip.get(f"{{{R_NS}}}embed")
    relationships = relationships_root.xpath(
        f'./pr:Relationship[@Id="{relationship_id}"]',
        namespaces=NS,
    )
    if len(relationships) != 1:
        raise ValueError(f"Could not resolve image relationship {relationship_id!r}")
    target = relationships[0].get("Target")
    if not target:
        raise ValueError(f"Image relationship {relationship_id!r} has no target")
    return posixpath.normpath(posixpath.join("word", target))


def replace_plain_paragraph(paragraph: etree._Element, text: str) -> None:
    if paragraph.xpath(".//w:fldChar", namespaces=NS):
        raise ValueError("Refusing to replace a paragraph containing fields")
    nodes = plain_text_nodes(paragraph)
    if not nodes:
        raise ValueError("Paragraph contains no text nodes")
    nodes[0].text = text
    for node in nodes[1:]:
        node.text = ""


def replace_plain_prefix_before_fields(paragraph: etree._Element, text: str) -> None:
    nodes: list[etree._Element] = []
    for element in paragraph.iter():
        if element.tag == f"{W}fldChar" and element.get(f"{W}fldCharType") == "begin":
            break
        if element.tag == f"{W}t":
            nodes.append(element)
    if not nodes:
        raise ValueError("No plain prefix text before fields")
    nodes[0].text = text
    for node in nodes[1:]:
        node.text = ""


def replace_in_plain_nodes(
    paragraph: etree._Element,
    old: str,
    new: str,
    expected: int = 1,
) -> None:
    nodes = plain_text_nodes(paragraph)
    matches = sum((node.text or "").count(old) for node in nodes)
    if matches != expected:
        raise ValueError(
            f"Expected {expected} node-contained occurrence(s) of {old!r} in "
            f"{paragraph_text(paragraph)!r}, found {matches}"
        )
    for node in nodes:
        if node.text and old in node.text:
            node.text = node.text.replace(old, new)


def _cell_text(cell: etree._Element) -> str:
    return "".join(cell.xpath(".//w:t/text()", namespaces=NS))


def set_cell_text(cell: etree._Element, text: str) -> None:
    nodes = cell.xpath(".//w:t", namespaces=NS)
    if not nodes:
        if not text:
            return
        paragraphs = cell.xpath("./w:p", namespaces=NS)
        if not paragraphs:
            paragraph = etree.SubElement(cell, f"{W}p")
        else:
            paragraph = paragraphs[0]
        run = etree.SubElement(paragraph, f"{W}r")
        node = etree.SubElement(run, f"{W}t")
        node.text = str(text)
        return
    nodes[0].text = str(text)
    for node in nodes[1:]:
        node.text = ""


def set_table_rows(table: etree._Element, rows: Iterable[Iterable[str]]) -> None:
    table_rows = table.xpath("./w:tr", namespaces=NS)
    rows = [list(row) for row in rows]
    if len(table_rows) != len(rows) + 1:
        raise ValueError(
            f"Table row mismatch: document has {len(table_rows) - 1} data rows, update has {len(rows)}"
        )
    for table_row, values in zip(table_rows[1:], rows):
        cells = table_row.xpath("./w:tc", namespaces=NS)
        if len(cells) != len(values):
            raise ValueError(
                f"Table column mismatch: document has {len(cells)}, update has {len(values)}"
            )
        for cell, value in zip(cells, values):
            set_cell_text(cell, str(value))


def _paragraph_style(paragraph: etree._Element) -> str | None:
    values = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
    return values[0] if values else None


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w]+(?:[’'-][\w]+)*\b", text, flags=re.UNICODE))


def update_word_counts(root: etree._Element) -> dict[str, int]:
    paragraphs = root.xpath(".//w:body/w:p", namespaces=NS)
    texts = [paragraph_text(paragraph) for paragraph in paragraphs]

    abstract_start = texts.index("Abstract") + 1
    keywords_index = next(
        index for index in range(abstract_start, len(texts)) if texts[index].startswith("Keywords:")
    )
    abstract_parts = []
    for text in texts[abstract_start:keywords_index]:
        abstract_parts.append(re.sub(r"^[A-Za-z]+:\s*", "", text, count=1))
    abstract_words = _word_count(" ".join(abstract_parts))

    introduction_index = texts.index("Introduction") + 1
    acknowledgments_index = texts.index("Acknowledgments")
    main_parts = []
    for paragraph, text in zip(
        paragraphs[introduction_index:acknowledgments_index],
        texts[introduction_index:acknowledgments_index],
    ):
        if _paragraph_style(paragraph) == "Heading1":
            continue
        # Exclude cached Zotero citation result text from journal word counts.
        plain = "".join(node.text or "" for node in plain_text_nodes(paragraph))
        main_parts.append(plain)
    main_words = _word_count(" ".join(main_parts))

    abstract_count_paragraph = find_paragraph(root, "Abstract word count:")
    abstract_nodes = plain_text_nodes(abstract_count_paragraph)
    abstract_nodes[-1].text = str(abstract_words)
    main_count_paragraph = find_paragraph(root, "Main-text word count")
    main_nodes = plain_text_nodes(main_count_paragraph)
    main_nodes[-1].text = str(main_words)
    return {"abstract_words": abstract_words, "main_text_words": main_words}


def patch_manuscript(
    source: Path,
    target: Path,
    outputs: Path,
    supplement: Path,
    summary: pd.DataFrame,
    table1: list[list[str]],
    cohort_summary: dict[str, pd.Series],
    table2: list[list[str]],
    selected: dict[str, pd.Series],
    table3: list[list[str]],
    c3_summary: pd.Series,
) -> dict[str, Any]:
    with ZipFile(source) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))

        study_design = find_paragraph(root, "For each synthetic participant")
        replace_plain_paragraph(
            study_design,
            "For each synthetic participant, seizure and menstrual/hormone diaries were "
            "generated independently for 36 months and aligned directly by calendar-day index. "
            "HORMONE-CYCLE generated the first menstrual cycle in full and selected diary day 1 "
            "uniformly from that cycle’s realized days; generation then continued forward without "
            "wrapping. Analyses were stratified by cohort and phase-labeling mode.",
        )

        h_full_any = selected["h_full_any"]
        p_full_any = selected["p_full_any"]
        p_full_c12 = selected["p_full_c12"]
        p_full_c3 = selected["p_full_c3"]
        h_full_nb = selected["h_full_nb"]
        p_full_nb = selected["p_full_nb"]
        h_3m_any = selected["h_3m_any"]
        p_3m_any = selected["p_3m_any"]
        h_3cy_exact = selected["h_3cy_exact"]
        p_3cy_exact = selected["p_3cy_exact"]

        abstract_results = find_paragraph(root, "Results: In 36-month")
        replace_plain_paragraph(
            abstract_results,
            "Results: In 36-month strict-Herzog windows, CE was classified in "
            f"{_pct(h_full_any.false_positive_rate)}% of healthy ovulatory and "
            f"{_pct(p_full_any.false_positive_rate)}% of heterogeneous-cohort participants. "
            f"In the heterogeneous cohort, the C1/C2 union was {_pct(p_full_c12.false_positive_rate)}%, "
            f"whereas C3 positivity occurred in {_pct(p_full_c3.false_positive_rate)}% of applicable "
            "windows. C1/C2 negative-binomial false-positive rates were "
            f"{_pct(h_full_nb.false_positive_rate)}% and {_pct(p_full_nb.false_positive_rate)}%. "
            "The exploratory C3 model identified "
            f"{_pct(c3_summary['false_positive_rate_classifiable'])}% "
            f"(95% Wilson confidence interval, {_pct(c3_summary['wilson95_low'])}%–"
            f"{_pct(c3_summary['wilson95_high'])}%). Three-month windowed Herzog rates were "
            f"{_pct(h_3m_any.false_positive_rate)}% and {_pct(p_3m_any.false_positive_rate)}%.",
        )

        key_point = find_paragraph(root, "Windowed Herzog criteria misclassified")
        replace_plain_paragraph(
            key_point,
            "Windowed Herzog criteria misclassified "
            f"{_pct(h_full_any.false_positive_rate)}% of healthy and "
            f"{_pct(p_full_any.false_positive_rate)}% of heterogeneous simulated participants "
            "in 36-month diaries.",
        )

        healthy_summary = cohort_summary["healthy_ovulatory"]
        population_summary = cohort_summary["population"]
        simulation_cohort = find_paragraph_after_heading(root, "Simulation cohort")
        replace_plain_paragraph(
            simulation_cohort,
            "The completed run included 100,000 synthetic participants. The healthy ovulatory "
            f"cohort had {100 * float(healthy_summary['ovulatory_fraction']):.1f}% ovulatory cycles "
            "by design; the heterogeneous cohort had "
            f"{100 * float(population_summary['ovulatory_fraction']):.1f}% ovulatory cycles, greater "
            "within-participant cycle-length variability, and similar seizure burden (Table 1). "
            "Every diary began at a randomly selected menstrual-cycle phase.",
        )

        full_results = find_paragraph_after_heading(root, "Full-diary CE classification")
        replace_plain_paragraph(
            full_results,
            "In strict-Herzog 36-month windows, windowed Herzog thresholds classified "
            f"{_pct(h_full_any.false_positive_rate)}% of healthy ovulatory and "
            f"{_pct(p_full_any.false_positive_rate)}% of heterogeneous participants under independence "
            "(Table 2). In the heterogeneous cohort, the C1/C2 union was "
            f"{_pct(p_full_c12.false_positive_rate)}%, similar to the healthy cohort’s "
            f"{_pct(h_full_any.false_positive_rate)}%, whereas C3 positivity occurred in "
            f"{_pct(p_full_c3.false_positive_rate)}% of applicable windows. The excess was therefore "
            "primarily associated with the simulated inadequate-luteal-phase C3 mechanism "
            "(Figure 2 and Appendix S1).",
        )

        observation = find_paragraph_after_heading(root, "Observation windows")
        replace_plain_paragraph(
            observation,
            "Three-month windowed Herzog false-positive rates were "
            f"{_pct(h_3m_any.false_positive_rate)}% and {_pct(p_3m_any.false_positive_rate)}% in the "
            "healthy and heterogeneous cohorts, respectively. Rates declined with longer monitoring "
            "but remained definition-dependent (Figure 1). Exact Herzog 2004 applied to three complete "
            f"cycles yielded {_pct(h_3cy_exact.false_positive_rate)}% and "
            f"{_pct(p_3cy_exact.false_positive_rate)}% among classifiable windows, while many attempted "
            "windows were indeterminate. Appendix S1 reports C3 across every saved calendar and "
            "complete-cycle duration, minimum-data threshold sensitivities, and cumulative simulated "
            "C1, C2, and C3 ratio distributions.",
        )

        calibration = find_paragraph_after_heading(root, "Calibration checks")
        positive_count = int(c3_summary["positives"])
        positive_subject = _participant_subject(positive_count)
        replace_plain_paragraph(
            calibration,
            "The full-diary C1/C2 negative-binomial false-positive rate was "
            f"{_pct(h_full_nb.false_positive_rate)}% in the healthy cohort and "
            f"{_pct(p_full_nb.false_positive_rate)}% in the heterogeneous cohort, close to the "
            "prespecified 5% Type I error rate. In the 1% daily audit sample, "
            f"{int(c3_summary['n_ratio_c3_applicable'])} of "
            f"{int(c3_summary['n_attempted_audit_participants'])} heterogeneous participants had a "
            "C3-applicable ratio window, but only "
            f"{int(c3_summary['n_nb_classifiable'])} met the exploratory C3 model’s "
            "four-complete-inadequate luteal phase-cycle and four-seizure-day requirements. "
            f"{positive_subject} positive ({_pct(c3_summary['false_positive_rate_classifiable'])}%; "
            f"95% Wilson confidence interval, {_pct(c3_summary['wilson95_low'])}%–"
            f"{_pct(c3_summary['wilson95_high'])}%; "
            f"{_pct(c3_summary['positive_rate_all_attempted'])}% of all "
            f"{int(c3_summary['n_attempted_audit_participants'])} attempted participants).",
        )

        data_availability = find_paragraph(root, "Code, configuration, derived tabular outputs")
        replace_plain_paragraph(
            data_availability,
            "Code, configuration, derived tabular outputs, and the run manifest are available at "
            "https://github.com/GoldenholzLab/catamenial-epilepsy-sim. The completed "
            "primary simulation run used master seed 20260505; its manifest records configuration "
            "values, analysis-code and configuration fingerprints, file sizes, and SHA-256 "
            "checksums. The randomized-start analysis used config_random_start_full.yaml, and the "
            "Appendix S1 tables were derived from those primary outputs.",
        )

        tables = root.xpath(".//w:body/w:tbl", namespaces=NS)
        if len(tables) != 3:
            raise ValueError(f"Expected three manuscript tables, found {len(tables)}")
        set_table_rows(tables[0], table1)
        set_table_rows(tables[1], table2)
        set_table_rows(tables[2], table3)

        counts = update_word_counts(root)
        document_xml = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone="yes"
        )
        replacements_by_part = {
            "word/document.xml": document_xml,
            "word/media/image1.png": (outputs / "fig1_false_positive_by_window.png").read_bytes(),
            "word/media/image2.png": (outputs / "fig2_pattern_decomposition.png").read_bytes(),
            "word/media/image3.png": (outputs / "fig3_study_prevalence_distribution_3month.png").read_bytes(),
        }
        _write_patched_package(archive, target, replacements_by_part)
    return counts


def patch_appendix(
    source: Path,
    target: Path,
    outputs: Path,
    supplement: Path,
    summary: pd.DataFrame,
    parameter_table: list[list[str]],
    cumulative: dict[str, tuple[list[list[str]], str]],
    c3_windows: list[list[str]],
    minimum_rows: list[list[str]],
    c3_summary: pd.Series,
    patterns: list[list[str]],
) -> None:
    manifest = json.loads((outputs / "manifest.json").read_text(encoding="utf-8"))
    supplement_manifest = json.loads(
        (supplement / "manifest.json").read_text(encoding="utf-8")
    )
    with ZipFile(source) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        existing_tables = root.xpath(".//w:body/w:tbl", namespaces=NS)
        if len(existing_tables) == 19:
            patch_appendix_v7(
                archive=archive,
                root=root,
                target=target,
                outputs=outputs,
                supplement=supplement,
                manifest=manifest,
                summary=summary,
                parameter_table=parameter_table,
                cumulative=cumulative,
                c3_windows=c3_windows,
                c3_summary=c3_summary,
                patterns=patterns,
            )
            return

        provenance = find_paragraph(root, "The primary simulation run")
        provenance_prefix = (
            "The completed primary simulation run (100,000 participants; 50,000 per cohort; "
            "36 months) used master seed 20260505. Its manifest records output hashes "
            "plus the exact analysis-code and configuration SHA-256 fingerprints. Draft-v5 "
            "supplemental tables were derived from window_results.parquet, "
            "participant_summary.parquet, study_level_3month.parquet, and the deterministic 1% "
            "audit_daily_sample.parquet in that run directory. HORMONE-CYCLE version 0.1.0 was "
            "used. "
        )
        replace_plain_prefix_before_fields(provenance, provenance_prefix)

        limitation = find_paragraph(root, "The completed manifest does not store")
        code_fingerprint = manifest.get("analysis_code_sha256", "not recorded in legacy manifest")
        config_fingerprint = manifest.get(
            "analysis_config_sha256", "not recorded in legacy manifest"
        )
        supplement_fingerprint = supplement_manifest.get(
            "supplement_builder_sha256", "not recorded in legacy manifest"
        )
        replace_plain_paragraph(
            limitation,
            "The completed manifest stores the analysis-code fingerprint "
            f"{code_fingerprint} and configuration fingerprint "
            f"{config_fingerprint}, together with SHA-256 hashes for every "
            "primary output file. The supplemental manifest stores builder fingerprint "
            f"{supplement_fingerprint} and hashes for each derived artifact. These identifiers "
            "should accompany archived outputs.",
        )

        parameter_note = find_paragraph(root, "Note. The full machine-readable table")
        replace_in_plain_nodes(
            parameter_note,
            "the run version/commit",
            "the analysis-code and configuration SHA-256 fingerprints",
        )

        tables = root.xpath(".//w:body/w:tbl", namespaces=NS)
        if len(tables) != 9:
            raise ValueError(f"Expected nine appendix tables, found {len(tables)}")
        set_table_rows(tables[0], parameter_table)

        assumption_rows = tables[1].xpath("./w:tr", namespaces=NS)
        target_rows = [
            row
            for row in assumption_rows[1:]
            if _cell_text(row.xpath("./w:tc", namespaces=NS)[0]).startswith(
                "Circular seizure-diary shift"
            )
        ]
        if len(target_rows) != 1:
            raise ValueError(f"Expected one diary-alignment assumption row, found {len(target_rows)}")
        cells = target_rows[0].xpath("./w:tc", namespaces=NS)
        for cell, value in zip(
            cells,
            [
                "Direct calendar-day alignment",
                "Preserves the separately seeded seizure and hormone generator outputs without reordering.",
                "Independence follows from separate random streams; no artificial wraparound boundary is introduced.",
            ],
        ):
            set_cell_text(cell, value)

        for table_index, pattern in zip([2, 3, 4], ["C1", "C2", "C3"]):
            set_table_rows(tables[table_index], cumulative[pattern][0])
        set_table_rows(tables[5], c3_windows)
        set_table_rows(tables[6], minimum_rows)
        set_table_rows(tables[7], [c3_nb_row(c3_summary)])
        set_table_rows(tables[8], patterns)

        for prefix, note in [
            ("Note. Healthy attempted=", cumulative["C1"][1]),
            ("Note. Healthy attempted=", cumulative["C2"][1]),
        ]:
            matches = [
                paragraph
                for paragraph in root.xpath(".//w:body/w:p", namespaces=NS)
                if paragraph_text(paragraph).startswith(prefix)
            ]
            if len(matches) != 2:
                raise ValueError(f"Expected two healthy cumulative notes, found {len(matches)}")
            index = 0 if note == cumulative["C1"][1] else 1
            replace_plain_paragraph(matches[index], note)
        c3_note = find_paragraph(root, "Note. Attempted=")
        replace_plain_paragraph(c3_note, cumulative["C3"][1])

        reason_counts = json.loads(c3_summary["reason_counts"])
        reason_text = (
            "Reason counts: "
            + "; ".join(
                f"{key.replace('_', ' ')}={value}" for key, value in reason_counts.items()
            )
            + ". The narrower classifiable denominator reflects the model’s minimum four "
            "complete ILP cycles and four seizure days, not a discrepancy with pooled-ratio "
            "applicability."
        )
        reason_paragraph = find_paragraph(root, "Reason counts:")
        replace_plain_paragraph(reason_paragraph, reason_text)

        document_xml = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone="yes"
        )
        replacements_by_part = {
            "word/document.xml": document_xml,
            "word/media/image1.png": (supplement / "figS1_seizure_process_distributions.png").read_bytes(),
            "word/media/image2.png": (supplement / "figS2_seizure_rhythm_distributions.png").read_bytes(),
            "word/media/image3.png": (supplement / "figS3_menstrual_cycle_distributions.png").read_bytes(),
            "word/media/image4.png": (supplement / "figS4_age_and_modifier_distributions.png").read_bytes(),
            "word/media/image5.png": (supplement / "figS5_simulated_classification_associations.png").read_bytes(),
        }
        _write_patched_package(archive, target, replacements_by_part)


def patch_appendix_v7(
    *,
    archive: ZipFile,
    root: etree._Element,
    target: Path,
    outputs: Path,
    supplement: Path,
    manifest: dict[str, Any],
    summary: pd.DataFrame,
    parameter_table: list[list[str]],
    cumulative: dict[str, tuple[list[list[str]], str]],
    c3_windows: list[list[str]],
    c3_summary: pd.Series,
    patterns: list[list[str]],
) -> None:
    """Surgically update the chapter-organized appendix while preserving Zotero fields."""

    from build_draft_v7_appendix import (
        subgroup_check_rows,
        subgroup_rows,
        validation_rows,
    )

    validation_path = Path("examples/reports/notebook_validation_report.json")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    minimum_source = pd.read_csv(supplement / "tableS3_minimum_data_sensitivity.csv")
    minimum_rows_v7: list[list[str]] = []
    for row in minimum_source.itertuples(index=False):
        if row.window_type != "calendar" or int(float(row.window_value)) not in {4, 6, 12, 36}:
            continue
        rate = 100 * float(row.false_positive_rate_classifiable)
        low = 100 * float(row.wilson95_low)
        high = 100 * float(row.wilson95_high)
        minimum_rows_v7.append(
            [
                "Healthy ovulatory" if row.cohort == "healthy_ovulatory" else "Heterogeneous",
                f"{int(float(row.window_value))} months",
                str(int(row.min_seizure_days)),
                f"{int(row.n_classifiable):,}",
                f"{int(row.positives):,}",
                f"{rate:.1f}% ({low:.1f}%–{high:.1f}%)",
                f"{100 * float(row.positive_rate_all_attempted):.1f}%",
            ]
        )

    tables = root.xpath(".//w:body/w:tbl", namespaces=NS)
    if len(tables) != 19:
        raise ValueError(f"Expected 19 chapter-organized appendix tables, found {len(tables)}")
    set_table_rows(tables[5], validation_rows(validation))
    set_table_rows(tables[6], subgroup_rows(validation))
    set_table_rows(tables[7], subgroup_check_rows(validation))
    set_table_rows(tables[8], parameter_table)
    for table_index, pattern in zip([11, 12, 13], ["C1", "C2", "C3"]):
        set_table_rows(tables[table_index], cumulative[pattern][0])
    window_results = pd.read_parquet(outputs / "window_results.parquet")
    set_table_rows(tables[14], sparse_comparator_rows(window_results))
    set_table_rows(
        tables[15],
        [row for row in c3_windows if row[0] != "36-month full diary"],
    )
    set_table_rows(tables[16], minimum_rows_v7)
    set_table_rows(tables[17], [c3_nb_row(c3_summary)])
    set_table_rows(tables[18], patterns)

    for row in tables[3].xpath("./w:tr", namespaces=NS)[1:]:
        cells = row.xpath("./w:tc", namespaces=NS)
        if _cell_text(cells[0]) != "Diary completion":
            continue
        values = [
            "Diary start and completion",
            "Run",
            "Generate cycle 1 in full; select its first observed day uniformly; continue forward through subsequent cycles",
            "Optional cycle-day-1 start; no wrapping; truncate only the final retained cycle at the requested diary length",
            "Implementation rule",
        ]
        for cell, value in zip(cells, values):
            set_cell_text(cell, value)

    # Make the two study-design assumptions explicit without changing table structure.
    for row in tables[9].xpath("./w:tr", namespaces=NS)[1:]:
        cells = row.xpath("./w:tc", namespaces=NS)
        label = _cell_text(cells[0])
        if label == "Direct calendar-day alignment":
            values = [
                "Direct calendar-day alignment",
                "Preserves the separately seeded seizure and hormone outputs while HORMONE-CYCLE selects a uniformly random first-cycle start day.",
                "No end-to-start wraparound is introduced; boundary exposure is randomized across menstrual phases.",
            ]
        elif label == "Complete-diary observation":
            values = [
                "Randomized diary boundary",
                "Diary day 1 is selected uniformly from the realized days of the first generated menstrual cycle, after which generation proceeds forward.",
                "The first and final observed cycles may be partial; analyses requiring complete cycles exclude them.",
            ]
        else:
            continue
        for cell, value in zip(cells, values):
            set_cell_text(cell, value)

    evaluation_design = find_paragraph(root, "The quality-control design follows")
    replace_in_plain_nodes(
        evaluation_design,
        " validate --patients 10000 --days 365 --seed 7",
        " validate --patients 10000 --days 365 --seed 7 --start-mode random",
    )
    calibration_caption = find_paragraph(root, "Appendix Table A6.")
    replace_in_plain_nodes(
        calibration_caption,
        "10,000 synthetic participants, 365 days per participant, and seed 7.",
        "10,000 synthetic participants, 365 days per participant, seed 7, and a randomized "
        "menstrual starting phase.",
    )
    calibration_figure_caption = find_paragraph(root, "Appendix Figure A2.")
    replace_in_plain_nodes(
        calibration_figure_caption,
        "Panels A–C use the 10,000-participant run.",
        "Panels A–C use the 10,000-participant randomized-start run.",
    )

    study_provenance = find_paragraph(root, "The completed primary simulation included")
    replace_in_plain_nodes(
        study_provenance,
        "The generators were run independently and merged by calendar-day index. ",
        "The generators were run independently. HORMONE-CYCLE selected diary day 1 uniformly "
        "from the realized days of the first generated menstrual cycle and then continued "
        "forward without wrapping. The diaries were merged by calendar-day index. ",
    )

    manifest_paragraph = find_paragraph(root, "The completed manifest stores")
    replace_plain_paragraph(
        manifest_paragraph,
        "The completed manifest stores the analysis-code fingerprint "
        f"{manifest.get('analysis_code_sha256', 'not recorded')} and configuration fingerprint "
        f"{manifest.get('analysis_config_sha256', 'not recorded')}. These Secure Hash Algorithm "
        "256-bit fingerprints and all output-file hashes should accompany archived results. The "
        "study wrapper and HORMONE-CYCLE package declare version 0.1.0 and Python 3.11 or later. "
        "The full-run command was equivalent to “run_paper1_null_ce.py --config "
        "config_random_start_full.yaml --full,” and the archived machine-readable outputs are in "
        "outputs/random_start_full. The manifest records the complete configuration, assumptions, "
        "generated-file hashes, and dependency-facing analysis fingerprints.",
    )

    reasons = json.loads(c3_summary["reason_counts"])
    attempted = int(c3_summary["n_attempted_audit_participants"])
    applicable = int(c3_summary["n_ratio_c3_applicable"])
    classifiable = int(c3_summary["n_nb_classifiable"])
    positives = int(c3_summary["positives"])
    low_cycles = int(reasons.get("fewer_than_required_complete_ilp_cycles", 0))
    low_seizure_days = int(reasons.get("seizure_days_below_minimum", 0))
    audit_paragraph = find_paragraph(root, "The retained daily audit sample was selected")
    replace_plain_paragraph(
        audit_paragraph,
        "The retained daily audit sample was selected independently within each cohort without "
        "replacement at a 1% fraction. NumPy’s default random-number generator used a deterministic "
        "32-bit seed derived from master seed 20260505, the cohort name, and “audit_sample.” The "
        "heterogeneous-cohort seed was 529110050. The type C3 exploratory analysis attempted all "
        f"{attempted} retained heterogeneous participants: {applicable} had ratio-level type C3 "
        f"applicability, {classifiable} met regression data requirements, {low_cycles} had fewer "
        "than four complete inadequate-luteal-phase cycles, and "
        f"{low_seizure_days} had fewer than four seizure days. All {classifiable} classifiable "
        "participants used the negative-binomial fit; no robust-Poisson fallback or regression "
        f"failure occurred. {positives} were positive.",
    )
    caption = find_paragraph(root, "Appendix Table S7.")
    replace_plain_paragraph(
        caption,
        "Appendix Table S7. Exploratory type C3 negative-binomial calibration result in the "
        f"retained 1% daily audit sample. All {attempted} retained heterogeneous participants "
        f"were attempted; {applicable} were ratio-applicable, {classifiable} were "
        f"regression-classifiable, and {positives} were positive. “All-attempted rate” is "
        f"{positives}/{attempted}. The 95% Wilson interval describes Monte Carlo uncertainty "
        "under this configured simulation. No robust-Poisson fallback was used.",
    )

    relationships_root = etree.fromstring(
        archive.read("word/_rels/document.xml.rels")
    )
    image_replacements = {
        image_member_before_caption(root, relationships_root, "Appendix Figure A2."):
            Path(".codex_review/draft_v6_appendix_s1/generated_assets/hormone_cycle_validation.png").read_bytes(),
    }
    for number in range(1, 6):
        image_replacements[
            image_member_before_caption(
                root,
                relationships_root,
                f"Supplementary Figure S{number}.",
            )
        ] = (supplement / f"figS{number}_{[
            'seizure_process_distributions',
            'seizure_rhythm_distributions',
            'menstrual_cycle_distributions',
            'age_and_modifier_distributions',
            'simulated_classification_associations',
        ][number - 1]}.png").read_bytes()

    document_xml = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )
    _write_patched_package(
        archive,
        target,
        {"word/document.xml": document_xml, **image_replacements},
    )


def _write_patched_package(
    source_archive: ZipFile,
    target: Path,
    replacements: dict[str, bytes],
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        prefix=f".{target.stem}-",
        suffix=".docx",
        dir=target.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as output:
            names = set()
            for item in source_archive.infolist():
                names.add(item.filename)
                payload = replacements.get(item.filename, source_archive.read(item.filename))
                output.writestr(item, payload)
        missing = set(replacements) - names
        if missing:
            raise ValueError(f"Replacement package parts were not found: {sorted(missing)}")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manuscript-source", type=Path, required=True)
    parser.add_argument("--appendix-source", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--supplement", type=Path, required=True)
    parser.add_argument("--manuscript-out", type=Path, required=True)
    parser.add_argument("--appendix-out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = pd.read_csv(args.outputs / "summary_tables.csv")
    participants = pd.read_parquet(args.outputs / "participant_summary.parquet")
    table1, cohort_summary = main_table1_rows(participants)
    table2, selected = main_table2_rows(summary)
    table3 = main_table3_rows(summary)

    cumulative_data = pd.read_csv(
        args.supplement / "tableS1_cumulative_herzog_ratios.csv"
    )
    cumulative = {
        pattern: cumulative_rows(cumulative_data, pattern)
        for pattern in ["C1", "C2", "C3"]
    }
    c3_windows = c3_window_rows(
        pd.read_csv(args.supplement / "tableS2_c3_window_sensitivity.csv")
    )
    minimum_rows = minimum_data_rows(
        pd.read_csv(args.supplement / "tableS3_minimum_data_sensitivity.csv")
    )
    parameter_table = parameter_rows(
        pd.read_csv(args.supplement / "tableS5_simulator_parameters_and_assumptions.csv")
    )
    c3_summary = pd.read_csv(
        args.supplement / "tableS6_c3_nb_exploratory_summary.csv"
    ).iloc[0]
    patterns = pattern_rows(summary)

    counts = patch_manuscript(
        args.manuscript_source,
        args.manuscript_out,
        args.outputs,
        args.supplement,
        summary,
        table1,
        cohort_summary,
        table2,
        selected,
        table3,
        c3_summary,
    )
    patch_appendix(
        args.appendix_source,
        args.appendix_out,
        args.outputs,
        args.supplement,
        summary,
        parameter_table,
        cumulative,
        c3_windows,
        minimum_rows,
        c3_summary,
        patterns,
    )

    primary_manifest = json.loads(
        (args.outputs / "manifest.json").read_text(encoding="utf-8")
    )
    supplement_manifest = json.loads(
        (args.supplement / "manifest.json").read_text(encoding="utf-8")
    )
    report = {
        "outputs": str(args.outputs),
        "supplement": str(args.supplement),
        "inputs": {
            "manuscript_source": str(args.manuscript_source),
            "manuscript_source_sha256": file_sha256(args.manuscript_source),
            "appendix_source": str(args.appendix_source),
            "appendix_source_sha256": file_sha256(args.appendix_source),
            "primary_manifest_sha256": file_sha256(args.outputs / "manifest.json"),
            "supplement_manifest_sha256": file_sha256(args.supplement / "manifest.json"),
            "updater_sha256": file_sha256(Path(__file__)),
            "primary_analysis_code_sha256": primary_manifest.get(
                "analysis_code_sha256"
            ),
            "primary_analysis_config_sha256": primary_manifest.get(
                "analysis_config_sha256"
            ),
            "supplement_builder_sha256": supplement_manifest.get(
                "supplement_builder_sha256"
            ),
        },
        "manuscript_out": str(args.manuscript_out),
        "appendix_out": str(args.appendix_out),
        "manuscript_out_sha256": file_sha256(args.manuscript_out),
        "appendix_out_sha256": file_sha256(args.appendix_out),
        "word_counts": counts,
        "headline_percentages": {
            key: round(100 * float(value.false_positive_rate), 4)
            for key, value in selected.items()
        },
        "c3_nb": {
            key: (
                c3_summary[key].item()
                if hasattr(c3_summary[key], "item")
                else c3_summary[key]
            )
            for key in [
                "n_attempted_audit_participants",
                "n_ratio_c3_applicable",
                "n_nb_classifiable",
                "positives",
                "false_positive_rate_classifiable",
                "wilson95_low",
                "wilson95_high",
                "positive_rate_all_attempted",
            ]
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
