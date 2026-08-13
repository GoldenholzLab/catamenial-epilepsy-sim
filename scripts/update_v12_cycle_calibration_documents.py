#!/usr/bin/env python3
"""Build v13 manuscript DOCX files from the v11 repaired documents.

The script edits OOXML directly so existing live Zotero fields, styles, comments,
relationships, and custom XML remain intact.  It deliberately leaves native
equation insertion and the final Microsoft Word/Zotero refresh to separate,
auditable steps.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from lxml import etree

import update_v11_hormone_documents as base
from hormone_cycler.literature import STRICKER_DAILY_SERUM_REFERENCE
from inject_live_zotero_fields import (
    citation_instruction,
    make_citation_runs,
    replace_marker_with_field,
    zotero_csl,
    zotero_item_ids,
)


CUNNINGHAM_KEY = "H25WKPM3"
CUNNINGHAM_MARKER = "[[CITE_CUNNINGHAM]]"
WAVEFORM_MARKER = "[[CITE_WAVEFORM_SOURCES]]"
HARLOW_MARKER = "[[CITE_HARLOW]]"
MUMFORD_MARKER = "[[CITE_MUMFORD]]"
ANCKAERT_MARKER = "[[CITE_ANCKAERT]]"
STRICKER_MARKER = "[[CITE_STRICKER]]"
STRICKER_KEY = "RQGUHW73"
HARLOW_KEY = "DEANI3HH"
MUMFORD_KEY = "3Y2YEUNZ"
ANCKAERT_KEY = "YLLLVBP5"
EXPECTED_VALIDATION_AGE_RANGE = [18.0, 55.0]
REQUIRED_CITATION_KEYS = {
    "li_2023_awhs",
    "bull_2019_natural_cycles",
    "cunningham_2024_flo",
    "stricker_2006_reference",
    "harlow_2000_long_follicular",
    "mumford_2012_cycle_hormones",
    "anckaert_2021_hormones",
    "fraser_2011_bleeding",
    "mortimer_2026_pcos",
    "doi_2005_pcos_hormones",
    "who_1986_adolescent_cycles",
    "venturoli_1986_menarche",
    "santoro_2011_perimenopause",
    "edelman_2014_ocp",
    "xiao_1995_lng_iud",
    "faundes_1980_copper_iud",
    "malmqvist_1974_copper_bleeding",
    "dawood_2006_dysmenorrhea",
}
OLD_EQUATION_IDS = [
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
NEW_WAVEFORM_EQUATION_IDS = [
    "lh_reference_mapping",
    "long_follicular_terminal_start",
]


def data_tables(root: etree._Element) -> list[etree._Element]:
    """Return the 19 non-equation tables in their document order."""

    tables = [
        table
        for table in root.xpath("./w:body/w:tbl", namespaces=base.NS)
        if not table.xpath(".//m:oMath", namespaces=base.NS)
    ]
    if len(tables) != 19:
        raise ValueError(f"Expected 19 non-equation appendix tables, found {len(tables)}")
    return tables


def make_paragraph_like(reference: etree._Element, text: str) -> etree._Element:
    paragraph = copy.deepcopy(reference)
    base.set_paragraph_text(paragraph, text)
    return paragraph


def insert_after(reference: etree._Element, element: etree._Element) -> etree._Element:
    parent = reference.getparent()
    parent.insert(parent.index(reference) + 1, element)
    return element


def replace_regex_in_text_nodes(
    element: etree._Element,
    pattern: str,
    replacement: str,
) -> None:
    """Replace the first regex match while preserving fields and run structure."""

    for node in element.xpath(".//w:t", namespaces=base.NS):
        current = node.text or ""
        updated, count = re.subn(pattern, replacement, current, count=1)
        if count:
            node.text = updated
            return
    raise ValueError(f"Could not replace regex {pattern!r} in {base.text_of(element)!r}")


def set_single_citation_paragraph(
    paragraph: etree._Element,
    before: str,
    after: str,
) -> None:
    """Rewrite prose around one complex Zotero field without flattening it."""

    children = list(paragraph)
    begin_index = next(
        index
        for index, child in enumerate(children)
        if child.xpath('.//w:fldChar[@w:fldCharType="begin"]', namespaces=base.NS)
    )
    end_index = next(
        index
        for index in range(begin_index + 1, len(children))
        if children[index].xpath('.//w:fldChar[@w:fldCharType="end"]', namespaces=base.NS)
    )
    properties = paragraph.find(base.qn(base.W, "pPr"))
    field_children = [copy.deepcopy(child) for child in children[begin_index : end_index + 1]]
    for child in list(paragraph):
        if child is not properties:
            paragraph.remove(child)
    if before:
        paragraph.append(base.make_text_run(before))
    for child in field_children:
        paragraph.append(child)
    if after:
        paragraph.append(base.make_text_run(after))


def inject_cunningham_fields(root: etree._Element, displayed: str) -> int:
    """Replace all Cunningham markers with live Zotero citation fields."""

    item_ids = zotero_item_ids({CUNNINGHAM_KEY})
    csl_items = {
        CUNNINGHAM_KEY: zotero_csl(CUNNINGHAM_KEY, item_ids[CUNNINGHAM_KEY])
    }
    count = 0
    for initial_node in list(root.xpath(".//w:t", namespaces=base.NS)):
        node = initial_node
        while node is not None and CUNNINGHAM_MARKER in (node.text or ""):
            count += 1
            digest = hashlib.sha1(f"v13-cunningham-{count}".encode()).hexdigest()[:8]
            instruction = citation_instruction(
                f"id{digest}",
                displayed,
                [{"key": CUNNINGHAM_KEY}],
                item_ids,
                csl_items,
            )
            source_run = node.getparent()
            runs = make_citation_runs(
                instruction,
                displayed,
                source_run.find("w:rPr", base.NS),
            )
            node = replace_marker_with_field(node, CUNNINGHAM_MARKER, runs)
    return count


def inject_waveform_fields(root: etree._Element, displayed: str) -> int:
    """Replace waveform-source markers with one live multi-item Zotero field."""

    keys = {STRICKER_KEY, HARLOW_KEY, MUMFORD_KEY, ANCKAERT_KEY}
    item_ids = zotero_item_ids(keys)
    csl_items = {key: zotero_csl(key, item_ids[key]) for key in sorted(keys)}
    specs = [
        {"key": STRICKER_KEY},
        {"key": HARLOW_KEY},
        {"key": MUMFORD_KEY},
        {"key": ANCKAERT_KEY},
    ]
    count = 0
    for initial_node in list(root.xpath(".//w:t", namespaces=base.NS)):
        node = initial_node
        while node is not None and WAVEFORM_MARKER in (node.text or ""):
            count += 1
            digest = hashlib.sha1(f"v13-waveform-{count}".encode()).hexdigest()[:8]
            instruction = citation_instruction(
                f"id{digest}",
                displayed,
                specs,
                item_ids,
                csl_items,
            )
            source_run = node.getparent()
            runs = make_citation_runs(
                instruction,
                displayed,
                source_run.find("w:rPr", base.NS),
            )
            node = replace_marker_with_field(node, WAVEFORM_MARKER, runs)
    return count


def inject_single_source_fields(
    root: etree._Element,
    marker: str,
    key: str,
    displayed: str,
    slug: str,
) -> int:
    """Replace all occurrences of one source marker with live Zotero fields."""

    item_ids = zotero_item_ids({key})
    csl_items = {key: zotero_csl(key, item_ids[key])}
    count = 0
    for initial_node in list(root.xpath(".//w:t", namespaces=base.NS)):
        node = initial_node
        while node is not None and marker in (node.text or ""):
            count += 1
            digest = hashlib.sha1(f"v13-{slug}-{count}".encode()).hexdigest()[:8]
            instruction = citation_instruction(
                f"id{digest}",
                displayed,
                [{"key": key}],
                item_ids,
                csl_items,
            )
            source_run = node.getparent()
            runs = make_citation_runs(
                instruction,
                displayed,
                source_run.find("w:rPr", base.NS),
            )
            node = replace_marker_with_field(node, marker, runs)
    return count


def update_main(
    source: Path,
    output: Path,
    outputs: Path,
    supplement: Path,
) -> None:
    entries, root, relationships = base.read_docx(source)
    tables = root.xpath("./w:body/w:tbl", namespaces=base.NS)
    if len(tables) != 3:
        raise ValueError(f"Expected 3 main-manuscript tables, found {len(tables)}")

    participants = pd.read_parquet(outputs / "participant_summary.parquet")
    summary = pd.read_csv(outputs / "summary_tables.csv")
    exploratory = pd.read_csv(
        supplement / "tableS6_c3_nb_exploratory_summary.csv"
    ).iloc[0]
    base.set_table_rows(tables[0], base.main_table_1(participants))
    base.set_table_rows(tables[1], base.main_table_2(summary))
    base.set_table_rows(tables[2], base.main_table_3(summary))

    healthy_any = base.full_window_row(summary, "healthy_ovulatory", "A_windowed_any")
    population_any = base.full_window_row(summary, "population", "A_windowed_any")
    population_c12 = base.full_window_row(summary, "population", "A_windowed_C1_or_C2")
    population_c3 = base.full_window_row(summary, "population", "A_windowed_C3_only")
    healthy_3m = base.result_row(summary, "healthy_ovulatory", "calendar", 3, "A_windowed_any")
    population_3m = base.result_row(summary, "population", "calendar", 3, "A_windowed_any")
    healthy_exact = base.result_row(summary, "healthy_ovulatory", "cycle", 3, "A_exact_any")
    population_exact = base.result_row(summary, "population", "cycle", 3, "A_exact_any")
    healthy_nb = base.full_window_row(summary, "healthy_ovulatory", "D_nb_regression_C1_or_C2")
    population_nb = base.full_window_row(summary, "population", "D_nb_regression_C1_or_C2")

    base.set_paragraph_text(
        base.find_paragraph(root, "Results: Three-month false-positive rates"),
        f"Results: Three-month false-positive rates were {base.format_main_percent(healthy_3m['false_positive_rate'])}% in the healthy ovulatory cohort and "
        f"{base.format_main_percent(population_3m['false_positive_rate'])}% in the heterogeneous cohort. In 36-month windows, CE was classified in "
        f"{base.format_main_percent(healthy_any['false_positive_rate'])}% and {base.format_main_percent(population_any['false_positive_rate'])}%, respectively. "
        f"In the heterogeneous cohort, the C1/C2 rate was {base.format_main_percent(population_c12['false_positive_rate'])}%, whereas C3 occurred in "
        f"{base.format_main_percent(population_c3['false_positive_rate'])}% of applicable windows. C1/C2 negative-binomial rates were "
        f"{base.format_main_percent(healthy_nb['false_positive_rate'])}% and {base.format_main_percent(population_nb['false_positive_rate'])}%; the exploratory C3 model was positive in "
        f"{base.format_percent(exploratory['false_positive_rate_classifiable'])} of classifiable audit participants (95% confidence interval, "
        f"{base.format_percent(exploratory['wilson95_low'])}–{base.format_percent(exploratory['wilson95_high'])}).",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Despite independence"),
        "Despite independence, 36-month Herzog false-positive rates were "
        f"{base.format_main_percent(healthy_any['false_positive_rate'])}% in healthy-ovulatory and "
        f"{base.format_main_percent(population_any['false_positive_rate'])}% in heterogeneous cohorts.",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "The completed run included 100,000"),
        "The completed run included 100,000 synthetic participants. The healthy ovulatory cohort had "
        f"{base.format_percent(participants.loc[participants.cohort == 'healthy_ovulatory', 'ovulatory_fraction'].mean())} ovulatory cycles by design; "
        f"the heterogeneous cohort had {base.format_percent(participants.loc[participants.cohort == 'population', 'ovulatory_fraction'].mean())} ovulatory cycles, "
        "greater within-participant cycle-length variability, and similar seizure burden (Table 1). Every diary began at a randomly selected menstrual-cycle phase.",
    )
    audit_features = pd.read_csv(supplement / "audit_realized_features.csv")
    ilp_fraction = audit_features.loc[
        audit_features.cohort == "population", "audit_ilp_fraction"
    ].mean()
    base.set_paragraph_text(
        base.find_paragraph(root, "We used strict Herzog phase labeling"),
        "We used strict Herzog phase labeling and the prespecified windowed Herzog pattern-specific ratio thresholds across each participant’s full 36-month diary. CE was classified in "
        f"{base.format_main_percent(healthy_any['false_positive_rate'])}% of classifiable healthy-ovulatory participant-windows and in "
        f"{base.format_main_percent(population_any['false_positive_rate'])}% of classifiable heterogeneous-cohort participant-windows under independence (Table 2). "
        f"In the heterogeneous cohort, the C1/C2 union was {base.format_main_percent(population_c12['false_positive_rate'])}%, whereas C3 was positive in "
        f"{base.format_main_percent(population_c3['false_positive_rate'])}% of C3-applicable windows. Thus, the between-cohort difference in the composite endpoint was primarily driven by the simulator-generated inadequate-luteal-phase designation. Because version 0.3.0 changes the progesterone envelope used to assign inadequate-luteal-phase status, all C3-dependent results were regenerated; in the retained 1% audit sample, the heterogeneous cohort’s mean inadequate-luteal-phase cycle fraction was {base.format_percent(ilp_fraction)}.",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Three-month false-positive rates were"),
        f"Three-month false-positive rates were {base.format_main_percent(healthy_3m['false_positive_rate'])}% and "
        f"{base.format_main_percent(population_3m['false_positive_rate'])}% in the healthy and heterogeneous cohorts, respectively. Rates declined with longer monitoring but remained definition-dependent (Figure 1). "
        f"Exact Herzog applied to three complete cycles yielded {base.format_main_percent(healthy_exact['false_positive_rate'])}% and "
        f"{base.format_main_percent(population_exact['false_positive_rate'])}% among classifiable windows, while many attempted windows were indeterminate. Appendix S1 reports C3 across every saved calendar and complete-cycle duration, minimum-data threshold sensitivities, and cumulative simulated C1, C2, and C3 ratio distributions.",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "The full-diary C1/C2 negative-binomial"),
        f"The full-diary C1/C2 negative-binomial false-positive rate was {base.format_main_percent(healthy_nb['false_positive_rate'])}% in the healthy cohort and "
        f"{base.format_main_percent(population_nb['false_positive_rate'])}% in the heterogeneous cohort, close to the prespecified 5% Type I error rate. "
        f"In the 1% daily audit sample, {int(exploratory['n_ratio_c3_applicable'])} of {int(exploratory['n_attempted_audit_participants'])} heterogeneous participants had a C3-applicable ratio window, but only "
        f"{int(exploratory['n_nb_classifiable'])} met the exploratory C3 model’s four-complete-inadequate-luteal-phase-cycle and four-seizure-day requirements. "
        f"{int(exploratory['positives'])} participants were positive ({base.format_percent(exploratory['false_positive_rate_classifiable'])}; 95% Wilson confidence interval, "
        f"{base.format_percent(exploratory['wilson95_low'])}–{base.format_percent(exploratory['wilson95_high'])}; {base.format_percent(exploratory['positive_rate_all_attempted'])} of all "
        f"{int(exploratory['n_attempted_audit_participants'])} attempted participants).",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "The analysis most closely aligned with the original Herzog 2004 procedure"),
        "The analysis most closely aligned with the original Herzog 2004 procedure applied the same-pattern-in-two-of-three rule to exactly three complete 23–35-day cycles. "
        f"Under that definition, false-positive classification occurred in {base.format_main_percent(healthy_exact['false_positive_rate'])}% and "
        f"{base.format_main_percent(population_exact['false_positive_rate'])}% of classifiable windows in the healthy and heterogeneous cohorts, respectively, although many attempted windows were indeterminate. "
        "Even this comparison should be interpreted cautiously because the simulation represents complete independence and does not reproduce the mixture of true hormone-associated and unrelated seizure patterns present in clinical cohorts.",
    )
    discussion = base.find_paragraph(root, "This study quantified the false positive classification")
    replace_regex_in_text_nodes(
        discussion,
        r"false-positive classification occurred in [0-9.]+% of healthy-ovulatory and [0-9.]+% of heterogeneous-cohort",
        f"false-positive classification occurred in {base.format_main_percent(healthy_3m['false_positive_rate'])}% of healthy-ovulatory and {base.format_main_percent(population_3m['false_positive_rate'])}% of heterogeneous-cohort",
    )

    reasons = json.loads(exploratory["reason_counts"])
    base.set_paragraph_text(
        base.find_paragraph(root, "The largest heterogeneous-cohort"),
        "The largest heterogeneous-cohort excess was C3-driven, whereas C1/C2 behavior was similar between cohorts.",
    )

    # Refresh the abstract as a complete paragraph.  The repaired v11 file
    # contains a malformed legacy phrase around the two simulator names; field
    # updates in Word can make that run-level corruption even more visible.
    base.set_paragraph_text(
        base.find_paragraph(root, "Methods: We simulated"),
        "Methods: We simulated 100,000 synthetic participants for 36 months in healthy ovulatory and heterogeneously ovulatory menstruating-age cohorts. "
        "CHOCOLATES generated seizure diaries, and HORMONE-CYCLE version 0.3.0 independently generated menstrual and hormone diaries using separate deterministic random streams; diaries were aligned directly by calendar day without reordering. "
        "We applied Herzog phase definitions and pattern-specific seizure-frequency ratio thresholds across calendar, complete-cycle, and full-diary windows. A negative-binomial analysis was used as a model-concordant statistical calibration check.",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Significance: False-positive classification"),
        "Significance: False-positive CE classification is common when independent seizure and menstrual-cycle simulations are overlaid, particularly for heterogeneous cycles when C3 logic is used. Population, observation duration, phase definitions, and minimum-data rules materially affect results and should be reported explicitly.",
    )

    methods = base.find_paragraph(root, "CHOCOLATES generated")
    methods_text = base.text_of(methods)
    if "HORMONE-CYCLE version 0.2.0 is a custom simulator" in methods_text:
        base.replace_literal(
            methods,
            "HORMONE-CYCLE version 0.2.0 is a custom simulator",
            "HORMONE-CYCLE version 0.3.0 is a custom simulator",
        )
    else:
        base.replace_literal(
            methods,
            "HORMONE-CYCLE is a new custom, simulator",
            "HORMONE-CYCLE version 0.3.0 is a custom simulator",
        )
    base.replace_literal(
        methods,
        "It samples participant traits and cycle realizations, then generates daily bleeding, ovulation, estradiol, and progesterone trajectories.",
        "It assigns age-specific participant variability components, samples right-skewed cycle realizations, and generates daily bleeding, ovulation, estradiol, and progesterone trajectories. Full hormone trajectories were retained for validation and the prespecified 1% daily audit sample; other paper-simulation participants used an RNG-equivalent compact renderer that retained identical cycle structure and inadequate-luteal-phase status without materializing unused concentration rows.",
    )
    next_heading = base.find_exact_paragraph(root, "Phase labeling and Herzog criteria")
    external_paragraph = make_paragraph_like(
        methods,
        "As a separate aggregate cross-check not used for fitting, simulated 12-month age-stratified cycle means and participant-specific standard deviations were compared with a global period-tracking cohort. "
        + CUNNINGHAM_MARKER
        + " The comparison was prespecified as an external summary-level check rather than individual-level validation; Appendix S1 reports targets, margins, and the older-age discrepancy.",
    )
    next_heading.getparent().insert(next_heading.getparent().index(next_heading), external_paragraph)

    waveform_paragraph = make_paragraph_like(
        methods,
        "For ovulatory cycles, version 0.3.0 maps the complete daily LH-aligned serum estradiol and progesterone medians to the simulated ovulation event, uses PCHIP between those daily values, and preserves a broad luteal progesterone summit. Long follicular phases retain a terminal 14-day estradiol-maturation interval and use delayed-emergence or failed-wave geometry rather than stretching an ordinary-cycle template. "
        + WAVEFORM_MARKER
        + " An independent assay-specific serum cohort supplies subphase amplitude and ordering checks; Appendix S1 reports the numerical and visual validation criteria. These checks concern population-level daily envelopes and do not establish individual clinical validity or reproduce within-day progesterone pulsatility.",
    )
    next_heading.getparent().insert(next_heading.getparent().index(next_heading), waveform_paragraph)

    limitations = base.find_paragraph(root, "The study is limited by simulator and adapter assumptions")
    limitation_text = base.text_of(limitations)
    limitation_text = limitation_text.replace(
        "summary-level calibration does not substitute for external validation using paired real diaries.",
        "summary-level calibration and the held-out aggregate cycle cross-check do not substitute for external validation using paired real diaries. Agreement was strongest at ages 18–45 and was more qualified after age 50 because the two large app cohorts reported different variability magnitudes.",
    )
    limitation_text = limitation_text.replace(
        "Monte Carlo intervals do not include model-form uncertainty.",
        "The hormone waveform is a daily population-median envelope rather than an individual endocrine time series; it omits within-day pulsatility, and the long-follicular failed-wave share is an investigator-set heterogeneity parameter rather than a published prevalence. Monte Carlo intervals do not include model-form uncertainty.",
    )
    base.set_paragraph_text(limitations, limitation_text)

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
    cumulative_paragraph = base.find_paragraph(root, "Across cumulative C1 ratio thresholds")
    # Preserve the live Herzog Zotero field while refreshing the surrounding
    # numerical prose from the definitive supplement.
    set_single_citation_paragraph(
        cumulative_paragraph,
        "Across cumulative C1 ratio thresholds from 1.69 to 10, the proportions reported by Herzog (2015)",
        f" exceeded the corresponding simulated heterogeneous-cohort proportions by "
        f"{point_differences.min():.2f}–{point_differences.max():.2f} percentage points, "
        f"equivalent to relative differences of {relative_differences.min():.0f}%–"
        f"{relative_differences.max():.0f}% (Appendix Table S4).",
    )

    base.set_paragraph_text(
        base.find_paragraph(root, "Supporting information:"),
        "Supporting information: Appendix S1; Appendix Tables A1–A8 and Figures A1–A4; Tables S1–S8 and Figures S1–S5",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Appendix S1 contains the simulator"),
        "Appendix S1 contains the simulator source-to-parameter map, healthy-cycle calibration and held-out aggregate validation, hormone-waveform numerical and visual checks, representative hormone traces, assumption review, C3 algorithm, cumulative simulated Herzog-ratio panels, window and minimum-data sensitivities, exploratory C3 negative-binomial calibration check, pattern decomposition, feature associations, Appendix Tables A1–A8, Appendix Figures A1–A4, Tables S1–S8, and Figures S1–S5.",
    )
    base.set_paragraph_text(base.find_paragraph(root, "References:"), "References: 20")

    citation_fields = inject_cunningham_fields(root, "(13)")
    if citation_fields != 1:
        raise ValueError(f"Expected one new main citation, inserted {citation_fields}")
    waveform_fields = inject_waveform_fields(root, "(9,14–16)")
    if waveform_fields != 1:
        raise ValueError(f"Expected one new main waveform citation, inserted {waveform_fields}")
    rels = base.relationship_map(relationships)
    media = {
        rels["rId8"]: outputs / "fig1_false_positive_by_window.png",
        rels["rId9"]: outputs / "fig2_pattern_decomposition.png",
        rels["rId10"]: outputs / "fig3_study_prevalence_distribution_3month.png",
    }
    for rid, path in [("rId8", media[rels["rId8"]]), ("rId9", media[rels["rId9"]]), ("rId10", media[rels["rId10"]])]:
        base.update_drawing_aspect(root, rid, path)
    base.refresh_main_title_page_counts(root)
    base.write_docx(output, entries, root, media, relationships)


def metric_label(name: str) -> str:
    age_names = {
        "cycle_mean_": "Mean cycle length, age ",
        "cycle_within_person_sd_": "Pooled within-person cycle-length SD, age ",
        "cycle_irregularity_": "Participants with mean absolute adjacent difference ≥7 days, age ",
        "cycle_short_lt24_": "Cycles shorter than 24 days, age ",
        "cycle_long_gt38_": "Cycles longer than 38 days, age ",
        "external_cunningham_mean_personal_sd_": "Held-out mean participant-specific SD, age ",
        "external_cunningham_mean_": "Held-out mean cycle length, age ",
    }
    for prefix, label in age_names.items():
        if name.startswith(prefix):
            return label + name.removeprefix(prefix).replace("50+", "≥50").replace("-", "–")
    labels = {
        "follicular_mean_days": "Mean follicular interval",
        "luteal_mean_days": "Mean luteal interval",
        "bleeding_mean_days": "Mean bleeding duration",
        "luteal_sd_days": "Luteal-interval SD",
        "bleeding_sd_days": "Bleeding-duration SD",
        "estradiol_preovulatory_peak_width_days": "Estradiol preovulatory peak width at ≥80% maximum",
        "estradiol_luteal_secondary_peak_ratio": "Luteal estradiol peak / preovulatory maximum",
        "progesterone_plateau_width_days": "Progesterone plateau width at ≥75% maximum",
        "progesterone_peak_offset_from_ovulation_days": "Progesterone peak offset from ovulation",
        "progesterone_rise_to_5ng_offset_days": "Progesterone ≥5 ng/mL rise offset from ovulation",
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


def metric_value(metric: dict, field: str) -> str:
    value = float(metric[field])
    name = metric["name"]
    if any(token in name for token in ["cycle_irregularity_", "cycle_short_lt24_", "cycle_long_gt38_"]):
        return base.format_percent(value)
    if name in {
        "progesterone_terminal_to_peak_ratio",
        "estradiol_luteal_secondary_peak_ratio",
    }:
        return f"{value:.4f}"
    if name.startswith("progesterone_"):
        return f"{value:.2f}"
    return f"{value:.2f}"


def v13_validation_rows(validation: dict) -> list[list[str]]:
    source_names = {
        "li_2023_awhs": "Li et al. (2023), Tables 4–5 and Supplementary Table 2",
        "bull_2019_natural_cycles": "Bull et al. (2019), Table 1",
        "cunningham_2024_flo": "Cunningham et al. (2024), held-out aggregate cross-check",
        "stricker_2006_reference": "Stricker et al. (2006), Table 1B and Figure 1",
        "anckaert_2021_hormones": "Anckaert et al. (2021), independent assay-specific subphase reference intervals",
    }
    kinetic_names = {
        "estradiol_preovulatory_peak_width_days",
        "estradiol_luteal_secondary_peak_ratio",
        "progesterone_plateau_width_days",
        "progesterone_peak_offset_from_ovulation_days",
        "progesterone_rise_to_5ng_offset_days",
        "progesterone_premenstrual_withdrawal_days",
        "progesterone_terminal_to_peak_ratio",
        "progesterone_cross_cycle_jump_ng_ml",
    }
    rows: list[list[str]] = []
    for metric in validation["baseline_metrics"]:
        name = metric["name"]
        source = source_names[metric["citation_key"]]
        if name in kinetic_names:
            source = "Stricker daily series; prespecified morphology software-check bound"
        if name.startswith(("estradiol_", "progesterone_")):
            sample = "16 retained diaries, two per AWHS age band"
        elif name.startswith("external_cunningham_"):
            sample = "10,000 adults aged 18–54.9; first 11 cycles per participant"
        else:
            sample = "10,000 adults aged 18–54.9"
        rows.append(
            [
                metric_label(name),
                metric_value(metric, "observed"),
                metric_value(metric, "expected"),
                f"{metric_value(metric, 'lower_bound')} to {metric_value(metric, 'upper_bound')}",
                "Pass" if metric["passed"] else "Fail",
                source,
                sample,
            ]
        )
    return rows


def v13_subgroup_summary_rows(validation: dict) -> list[list[str]]:
    """Render age-matched secondary modifier stress-test summaries."""

    rows: list[list[str]] = []
    for key, item in validation["subgroup_analysis"]["subgroups"].items():
        summary = item["summary"]
        age_range = item["age_range"]
        rows.append(
            [
                f"{base.SCENARIO_LABELS[key]} (ages {age_range[0]:g}–{age_range[1] - 0.1:g})",
                f"{summary['mean_cycle_days']:.2f}",
                base.format_percent(summary["ovulation_rate"]),
                f"{summary['mean_bleeding_days']:.2f}",
                base.format_percent(summary["irregularity_rate"]),
                base.format_percent(summary["amenorrhea_rate"]),
                f"{sum(check['passed'] for check in item['checks'])}/{len(item['checks'])} passed",
            ]
        )
    return rows


def replace_equations_with_markers(root: etree._Element) -> None:
    body = root.find("./w:body", namespaces=base.NS)
    equation_tables = [
        table
        for table in body.findall(base.qn(base.W, "tbl"))
        if table.xpath(".//m:oMath", namespaces=base.NS)
        and len(table.xpath("./w:tr[1]/w:tc", namespaces=base.NS)) == 3
    ]
    if len(equation_tables) != len(OLD_EQUATION_IDS):
        raise ValueError(
            f"Expected {len(OLD_EQUATION_IDS)} existing equation tables, found {len(equation_tables)}"
        )
    for table, equation_id in zip(equation_tables, OLD_EQUATION_IDS):
        marker = etree.Element(base.qn(base.W, "p"))
        base.set_paragraph_text(marker, f"[[EQUATION:{equation_id}]]")
        body.replace(table, marker)
    for paragraph in list(body.xpath("./w:p", namespaces=base.NS)):
        style = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=base.NS)
        if style == ["EquationVariables"]:
            body.remove(paragraph)

    pchip_marker = base.find_exact_paragraph(
        root, "[[EQUATION:pchip_interpolation]]"
    )
    long_paragraph = base.find_paragraph(root, "Long follicular phases are not created")
    marker_mapping = make_paragraph_like(
        long_paragraph, f"[[EQUATION:{NEW_WAVEFORM_EQUATION_IDS[0]}]]"
    )
    marker_terminal = make_paragraph_like(
        long_paragraph, f"[[EQUATION:{NEW_WAVEFORM_EQUATION_IDS[1]}]]"
    )
    insert_after(pchip_marker, marker_mapping)
    insert_after(long_paragraph, marker_terminal)


def add_example_figure(
    root: etree._Element,
    relationships: etree._Element,
    image_path: Path,
) -> tuple[str, str]:
    """Clone the Appendix Figure A2 drawing as a new Figure A3 drawing."""

    source_blip = root.xpath('.//a:blip[@r:embed="rId11"]', namespaces=base.NS)
    if len(source_blip) != 1:
        raise ValueError(f"Expected one Appendix Figure A2 drawing, found {len(source_blip)}")
    source_paragraph = source_blip[0].xpath("ancestor::w:p[1]", namespaces=base.NS)[0]
    caption_a2 = base.find_paragraph(root, "Appendix Figure A2.")
    caption_a3 = make_paragraph_like(
        caption_a2,
        "Appendix Figure A3. Prespecified illustrative healthy-cycle traces after the version 0.3.0 waveform update. Panel A shows a 31-year-old participant assigned to the low-variability component; panel B shows a 31-year-old participant assigned to the high-variability component; panel C shows a 52-year-old participant with a later-life long-cycle episode. Estradiol and progesterone use separate axes; red shading denotes bleeding and green triangles denote ovulation. The updated P4 envelope has a postovulatory rise, broad summit, and late-luteal withdrawal. In the long cycle, extra follicular days precede a terminal E2-maturation interval rather than stretching the ordinary template. The displayed seeds were selected by prespecified component and episode criteria; these examples illustrate model behavior and are not independent validation observations.",
    )
    drawing_a3 = copy.deepcopy(source_paragraph)

    existing_ids = []
    for relationship in relationships.xpath("./pr:Relationship", namespaces=base.NS):
        match = re.fullmatch(r"rId(\d+)", relationship.get("Id", ""))
        if match:
            existing_ids.append(int(match.group(1)))
    # Reserve the relationship before the equation-insertion pass.  That pass
    # loads the package through python-docx, whose part allocator otherwise can
    # reuse a low-numbered relationship ID that is only present in the raw
    # relationship XML.  A high, explicit ID keeps the new drawing stable
    # through the OOXML -> python-docx -> OOXML round trip.
    new_rid_number = max(max(existing_ids, default=0) + 1, 1000)
    while f"rId{new_rid_number}" in {
        relationship.get("Id", "")
        for relationship in relationships.xpath("./pr:Relationship", namespaces=base.NS)
    }:
        new_rid_number += 1
    new_rid = f"rId{new_rid_number}"
    target = "media/healthy_cycle_example_traces_v13.png"
    relation = etree.SubElement(relationships, base.qn(base.PR, "Relationship"))
    relation.set("Id", new_rid)
    relation.set(
        "Type",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
    )
    relation.set("Target", target)
    for blip in drawing_a3.xpath(".//a:blip", namespaces=base.NS):
        blip.set(base.qn(base.R, "embed"), new_rid)
    max_doc_pr = max(
        [int(value) for value in root.xpath(".//wp:docPr/@id", namespaces=base.NS)]
        or [0]
    )
    for node in drawing_a3.xpath(".//wp:docPr", namespaces=base.NS):
        node.set("id", str(max_doc_pr + 1))
        node.set("name", "Appendix Figure A3")
    for node in drawing_a3.xpath('.//*[local-name()="cNvPr"]'):
        node.set("id", str(max_doc_pr + 1))
        node.set("name", "Appendix Figure A3")

    # The source appendix places each drawing immediately before its caption.
    # Keep A2 together, then append the cloned A3 drawing and its own caption.
    parent = caption_a2.getparent()
    insert_index = parent.index(caption_a2) + 1
    parent.insert(insert_index, drawing_a3)
    parent.insert(insert_index + 1, caption_a3)
    base.update_drawing_aspect(root, new_rid, image_path)
    return new_rid, target


def add_waveform_figure(
    root: etree._Element,
    relationships: etree._Element,
    image_path: Path,
) -> tuple[str, str]:
    """Clone the Appendix Figure A3 drawing as a new Figure A4 drawing."""

    caption_a3 = base.find_paragraph(root, "Appendix Figure A3.")
    source_paragraph = caption_a3.getprevious()
    if source_paragraph is None or len(
        source_paragraph.xpath(".//a:blip", namespaces=base.NS)
    ) != 1:
        raise ValueError("Appendix Figure A3 drawing is not immediately before its caption")
    drawing_a4 = copy.deepcopy(source_paragraph)
    caption_a4 = make_paragraph_like(
        caption_a3,
        "Appendix Figure A4. HORMONE-CYCLE version 0.3.0 waveform construction and visual validation. Panels A and B overlay the ordinary-cycle estradiol and progesterone envelopes on the complete mapped daily Stricker serum medians. " + STRICKER_MARKER + " The vertical dashed line is the simulated ovulation day, 0.75 day after the synchronized LH peak. Panel C compares an ordinary follicular E2 segment with two Harlow-informed 53-day-cycle geometries. " + HARLOW_MARKER + " Excess follicular time precedes a fixed 14-day terminal maturation interval; the failed-wave curve is a deterministic heterogeneity option. The 25% failed-wave share is an investigator-selected sensitivity parameter, not an estimated prevalence. The figure checks construction and morphology and is not participant-level clinical validation.",
    )

    existing_ids = []
    for relationship in relationships.xpath("./pr:Relationship", namespaces=base.NS):
        match = re.fullmatch(r"rId(\d+)", relationship.get("Id", ""))
        if match:
            existing_ids.append(int(match.group(1)))
    new_rid_number = max(max(existing_ids, default=0) + 1, 1001)
    existing_rids = {
        relationship.get("Id", "")
        for relationship in relationships.xpath("./pr:Relationship", namespaces=base.NS)
    }
    while f"rId{new_rid_number}" in existing_rids:
        new_rid_number += 1
    new_rid = f"rId{new_rid_number}"
    target = "media/hormone_waveform_validation_v13.png"
    relation = etree.SubElement(relationships, base.qn(base.PR, "Relationship"))
    relation.set("Id", new_rid)
    relation.set(
        "Type",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
    )
    relation.set("Target", target)
    for blip in drawing_a4.xpath(".//a:blip", namespaces=base.NS):
        blip.set(base.qn(base.R, "embed"), new_rid)
    max_doc_pr = max(
        [int(value) for value in root.xpath(".//wp:docPr/@id", namespaces=base.NS)]
        or [0]
    )
    for node in drawing_a4.xpath(".//wp:docPr", namespaces=base.NS):
        node.set("id", str(max_doc_pr + 1))
        node.set("name", "Appendix Figure A4")
    for node in drawing_a4.xpath('.//*[local-name()="cNvPr"]'):
        node.set("id", str(max_doc_pr + 1))
        node.set("name", "Appendix Figure A4")

    parent = caption_a3.getparent()
    insert_index = parent.index(caption_a3) + 1
    parent.insert(insert_index, drawing_a4)
    parent.insert(insert_index + 1, caption_a4)
    base.update_drawing_aspect(root, new_rid, image_path)
    return new_rid, target


def update_appendix(
    source: Path,
    output: Path,
    outputs: Path,
    supplement: Path,
    validation_path: Path,
    validation_figure: Path,
    examples_figure: Path,
    workflow_figure: Path,
    waveform_figure: Path,
) -> None:
    entries, root, relationships = base.read_docx(source)
    tables = data_tables(root)
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if not all(
        validation.get(key)
        for key in ("baseline_passed", "calibration_passed", "external_crosscheck_passed")
    ):
        raise ValueError(
            "Refusing to build v13 documents unless calibration, waveform validation, and the held-out "
            "aggregate cross-check pass"
        )
    if not validation.get("waveform_validation_passed"):
        raise ValueError("Refusing to build v13 documents after failed waveform validation")
    if validation.get("input", {}).get("age_range") != EXPECTED_VALIDATION_AGE_RANGE:
        raise ValueError(
            "Refusing to build v13 documents from a validation report that does not "
            "match the declared 18.0--54.9-year adult source cohort"
        )
    citation_keys = set(validation.get("citations", {}))
    if not REQUIRED_CITATION_KEYS.issubset(citation_keys):
        missing = sorted(REQUIRED_CITATION_KEYS - citation_keys)
        raise ValueError(
            "Refusing to build v13 documents from an obsolete or incomplete citation registry: "
            + ", ".join(missing)
        )
    incomplete_citations = [
        key
        for key, payload in validation.get("citations", {}).items()
        if not payload.get("title") or not payload.get("pmid") or not payload.get("evidence_role")
    ]
    if incomplete_citations:
        raise ValueError(
            "Refusing to build v13 documents from unauditable citation records: "
            + ", ".join(sorted(incomplete_citations))
        )
    subgroup_analysis = validation.get("subgroup_analysis", {})
    if subgroup_analysis.get("evaluation_type") != "secondary direction/range software stress tests":
        raise ValueError("Refusing to build v13 documents from obsolete modifier validation semantics")
    failed_subgroups = [
        name
        for name, payload in validation.get("subgroup_analysis", {}).get("subgroups", {}).items()
        if not payload.get("passed")
    ]
    if failed_subgroups:
        raise ValueError(
            "Refusing to build v13 documents after failed modifier scenarios: "
            + ", ".join(failed_subgroups)
        )
    run_manifest = json.loads((outputs / "manifest.json").read_text(encoding="utf-8"))
    summary = pd.read_csv(outputs / "summary_tables.csv")
    windows = pd.read_parquet(outputs / "window_results.parquet")

    # Table A1: preserve all existing citation fields and add the held-out source.
    a1_rows = tables[0].xpath("./w:tr", namespaces=base.NS)
    li_cells = a1_rows[1].xpath("./w:tc", namespaces=base.NS)
    base.set_cell_text(li_cells[2], "Age-specific mean cycle length, pooled within-person SD, participant-level irregularity, and short/long cycle tails")
    base.set_cell_text(li_cells[3], "Direct or derived age-band outcome targets; surrogate initialization followed by full-simulator refinement of latent two-component variability parameters")
    base.set_cell_text(li_cells[4], "Prespecified age-stratified calibration checks")
    bull_cells = a1_rows[2].xpath("./w:tc", namespaces=base.NS)
    base.set_cell_text(bull_cells[3], "Direct phase-timing and bleeding targets; stable-luteal structure")
    base.set_cell_text(bull_cells[4], "Phase and bleeding mean/SD checks")
    stricker_row = a1_rows[3]
    stricker_cells = stricker_row.xpath("./w:tc", namespaces=base.NS)
    for cell, value in zip(
        stricker_cells[2:],
        [
            "Complete daily serum estradiol and progesterone medians synchronized to the LH peak",
            "Primary ovulatory daily-envelope construction after unit conversion and event alignment",
            "Daily-envelope and prespecified morphology software checks",
            "Development source reused for internal construction checks",
        ],
    ):
        base.set_cell_text(cell, value)

    source_rows = [
        [
            "Cunningham et al. (2024) " + CUNNINGHAM_MARKER,
            ">19 million global Flo users aged 18–55; 12-month analysis cohort",
            "Age-specific participant cycle mean and mean participant-specific cycle-length SD",
            "Not used for fitting",
            "Held-out aggregate cross-check with prespecified practical-equivalence margins",
            "Independent aggregate source; no participant-level linkage",
        ],
        [
            "Harlow et al. (2000) " + HARLOW_MARKER,
            "416 conception and non-conception cycles; 28 follicular phases lasting ≥24 days",
            "Five heterogeneous long-follicular urinary-oestrogen patterns; delayed dominant-follicle emergence was most common",
            "Qualitative geometry for delayed-emergence and failed-wave E2 variants; no class-frequency fit",
            "Visual long-follicular morphology check",
            "Development morphology source; 25% failed-wave share remains investigator selected",
        ],
        [
            "Mumford et al. (2012) " + MUMFORD_MARKER,
            "259 healthy regularly menstruating women aged 18–44; up to two cycles and eight serum samples per cycle",
            "In cycles >35 days, E2 and LH peaks occurred about three days later than in normal-length cycles",
            "Independent timing context supporting delayed rather than proportional stretching",
            "Qualitative long-cycle timing cross-check",
            "Independent context source; not used to estimate waveform values",
        ],
        [
            "Anckaert et al. (2021) " + ANCKAERT_MARKER,
            "85 apparently healthy women aged 18–37 monitored across one natural cycle",
            "Assay-specific E2 and P4 follicular, ovulatory, luteal, and subphase reference intervals",
            "Not used to construct the waveform",
            "Independent amplitude and phase-order cross-check with broad assay-aware bounds",
            "Independent aggregate hormone source; not participant-level trajectory validation",
        ],
    ]
    insert_at = tables[0].index(stricker_row) + 1
    for values in source_rows:
        new_row = copy.deepcopy(stricker_row)
        for cell, value in zip(
            new_row.xpath("./w:tc", namespaces=base.NS), values
        ):
            base.set_cell_text(cell, value)
        tables[0].insert(insert_at, new_row)
        insert_at += 1

    # Table A2: correct AWHS targets and estimand.
    a2 = tables[1]
    base.replace_table_cell(a2, 0, 2, "Participants irregular: mean absolute adjacent-cycle difference ≥7 days")
    target_rows = [
        ["<15", "29.82", "20.4%", "0.62"],
        ["15–19", "29.82", "20.4%", "0.90"],
        ["20–24", "29.62", "20.9%", "0.97"],
        ["25–29", "29.31", "15.9%", "0.97"],
        ["30–34", "28.75", "11.6%", "0.97"],
        ["35–39", "28.19", "10.6%", "0.97"],
        ["40–44", "27.70", "12.8%", "0.95"],
        ["45–49", "27.86", "28.2%", "0.88"],
        ["≥50", "30.21", "60.2%", "0.70"],
    ]
    base.set_table_rows(a2, target_rows)

    # Table A3: complete daily LH-aligned reference values used by v0.3.0.
    base.set_table_rows(
        tables[2],
        [
            [
                f"{row.lh_offset_days:+d}",
                f"{row.estradiol_pg_ml:.2f}",
                f"{row.progesterone_ng_ml:.2f}",
            ]
            for row in STRICKER_DAILY_SERUM_REFERENCE
        ],
    )
    base.replace_table_cell(tables[2], 0, 0, "Day relative to serum LH peak")
    base.replace_table_cell(tables[2], 0, 1, "Estradiol median (pg/mL)")
    base.replace_table_cell(tables[2], 0, 2, "Progesterone median (ng/mL)")

    # Table A4: implemented v0.3.0 rules.
    a4 = tables[3]
    base.replace_table_cell(a4, 1, 2, "HORMONE-CYCLE version 0.3.0; Python ≥3.11")
    base.replace_table_cell(a4, 2, 2, "SHA-256 domain-separated Python random.Random streams for participant profile, cycle generation, and diary-start selection")
    base.replace_table_cell(a4, 2, 4, "Implementation choice preventing observation-boundary selection from perturbing latent profile or cycle draws")
    base.replace_table_cell(a4, 4, 2, "Truncated Gaussian around the age-band target after compensation for expected anovulatory and ≥50 long-cycle shifts")
    base.replace_table_cell(a4, 4, 3, "Between-person standard deviation 0.8 day (<20), 0.6 day (20–44), or 0.8 day (≥45); range 20–90 days")
    base.replace_table_cell(a4, 5, 2, "Age-specific Bernoulli assignment to a low- or high-variability participant component; component standard deviation is stable within person")
    base.replace_table_cell(a4, 5, 3, "Deterministic shifted-lognormal surrogate initialization followed by full-simulator refinement against AWHS SD, irregularity, and short/long tails")
    base.replace_table_cell(a4, 6, 2, "17-day-shifted lognormal draw around the resolved person/cycle mean and variability; rounded to nearest day")
    base.replace_table_cell(a4, 6, 3, "18–120 days; age ≥50 adds a 25.4912-day episode with probability 0.109 after compensating the latent mean")
    base.replace_table_cell(a4, 9, 2, "Truncated Gaussian centered on 12.4 days with latent standard deviation 3.0 days; rounded to nearest day")
    base.replace_table_cell(a4, 11, 2, "Truncated Gaussian centered on 4.0 days with standard deviation 1.5 days; rounded to nearest day")
    base.replace_table_cell(a4, 11, 4, "Direct Bull et al. Table 1 target; Fraser terminology")
    base.replace_table_cell(a4, 14, 2, "Daily Stricker medians indexed to the LH peak; simulated ovulation is 0.75 day later. Nonpositive offsets retain one-day spacing; positive offsets are scaled to the realized post-LH interval")
    base.replace_table_cell(a4, 14, 3, "The published +14-day tail reaches the final simulated cycle day without moving the progesterone rise before ovulation")
    base.replace_table_cell(a4, 14, 4, "Stricker daily series plus event-alignment rule")
    base.replace_table_cell(a4, 15, 2, "All 30 daily E2/P4 values in Table A3; ordinary-cycle E2 uses the −1 through +14 segment after a follicular ramp, and P4 uses −15 through +14")
    base.replace_table_cell(a4, 15, 3, "Converted from pmol/L and nmol/L; rounded to two decimals for reporting")
    base.replace_table_cell(a4, 15, 4, "Direct Stricker medians after unit conversion")
    base.replace_table_cell(a4, 18, 2, "Shape-preserving piecewise cubic Hermite interpolation (PCHIP) using the basis and piecewise interpolation defined below")
    long_e2_row = copy.deepcopy(a4.xpath("./w:tr", namespaces=base.NS)[15])
    for cell, value in zip(
        long_e2_row.xpath("./w:tc", namespaces=base.NS),
        [
            "Long-follicular estradiol geometry",
            "Cycle/day",
            "For follicular phases ≥24 days, excess time precedes a fixed 14-day terminal maturation interval; deterministic profile hashing selects delayed dominant-follicle emergence or a failed-wave/replacement geometry",
            "Failed-wave share 0.25 and failed-wave peak 0.52 × ordinary preovulatory target",
            "Harlow qualitative morphology; Mumford independent timing context; share and amplitude are investigator-selected sensitivity settings",
        ],
    ):
        base.set_cell_text(cell, value)
    a4.insert(a4.index(a4.xpath("./w:tr", namespaces=base.NS)[15]) + 1, long_e2_row)

    # Validation and modifier tables.
    base.set_table_rows(tables[5], v13_validation_rows(validation))
    base.set_table_rows(tables[6], v13_subgroup_summary_rows(validation))
    base.set_table_rows(tables[7], base.subgroup_check_rows(validation))
    parameter_data = pd.read_csv(supplement / "tableS5_simulator_parameters_and_assumptions.csv")
    base.set_table_rows(
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
    base.set_table_rows(tables[11], base.cumulative_rows(cumulative, "C1", include_herzog=True))
    base.set_table_rows(tables[12], base.cumulative_rows(cumulative, "C2"))
    base.set_table_rows(tables[13], base.cumulative_rows(cumulative, "C3"))
    base.set_table_rows(tables[14], base.ratio_audit_rows(windows))
    base.set_table_rows(tables[15], base.c3_sensitivity_rows(pd.read_csv(supplement / "tableS2_c3_window_sensitivity.csv")))
    base.set_table_rows(tables[16], base.minimum_data_rows(pd.read_csv(supplement / "tableS3_minimum_data_sensitivity.csv")))
    exploratory = pd.read_csv(supplement / "tableS6_c3_nb_exploratory_summary.csv")
    base.set_table_rows(tables[17], base.exploratory_row(exploratory))
    base.set_table_rows(tables[18], base.pattern_rows(summary))

    # Chapter 1 prose; citation-bearing fields are retained where present.
    p = base.find_paragraph(root, "Three primary data sources")
    set_single_citation_paragraph(
        p,
        "Three primary data sources supplied baseline calibration targets: the Apple Women’s Health Study for age-specific cycle summaries, the Natural Cycles cohort for phase and bleeding timing, and daily laboratory measurements for estradiol and progesterone subphase values. ",
        " Cunningham et al. supplied a fourth, independent aggregate cohort that was held out from parameter fitting and used only for a 12-month age-stratified cross-check. " + CUNNINGHAM_MARKER + " Condition-specific sources informed modifier directions or broad ranges; exact modifier margins are investigator-selected regression guards. Table A1 states exactly how each source entered development and evaluation. Development used aggregate quantities reported in the articles; participant-level source data were unavailable and were not used.",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Appendix Table A1."),
        "Appendix Table A1. Evidence provenance for HORMONE-CYCLE. “Calibration” means that a published result informed parameter fitting, waveform construction, or an acceptance target. “Held out” means that the published summary was not used to fit or construct the relevant model component. Cunningham is an independent aggregate cycle source; Anckaert is an independent aggregate hormone source. Neither provides participant-level linked validation for the simulated joint trajectories.",
    )
    p = base.find_paragraph(root, "Age selects one of eight calibration bands")
    set_single_citation_paragraph(
        p,
        "Age selects one of eight calibration bands. Li et al. reported 165,668 cycles from 12,608 participants and defined an irregular participant using a mean adjacent-cycle difference of at least 7 days. Their table footnote omits ‘absolute,’ but their methods define adjacent-cycle differences as absolute values; version 0.3.0 follows that convention. The model uses their age-specific pooled within-person SD, participant irregularity prevalence, and short- and long-cycle tails; age-band means are derived from the published adjusted contrasts anchored to the reported overall mean. ",
        " Participant irregularity is therefore evaluated with Equation 1 rather than as the probability that any single adjacent pair crosses the threshold.",
    )
    explanation = base.find_paragraph(root, "The latent within-person standard deviation")
    base.set_paragraph_text(
        explanation,
        "Each participant is assigned once to an age-specific low- or high-variability component. A deterministic shifted-lognormal surrogate supplied initial component probabilities and standard deviations against four AWHS outcomes per age band: pooled within-person SD, participant irregularity prevalence, and short- and long-cycle tails, using 11 cycles per participant to match the source cohort’s median follow-up. Production values were then refined and accepted against the complete simulator, which additionally represents between-person means, rounding and truncation, random observation boundaries, and variable realized follow-up. Given the resolved cycle-specific latent mean and SD, Equations 2 and 3 parameterize and sample a shifted lognormal cycle length. The 17-day shift supplies realistic right skew while the 18–120-day limits remain broad software safeguards. The ≥50-year band also includes an occasional long-cycle episode fitted to its joint targets.",
    )
    marker_two = make_paragraph_like(explanation, "[[EQUATION:cycle_shifted_lognormal_parameters]]")
    marker_three = make_paragraph_like(explanation, "[[EQUATION:cycle_length_generation]]")
    insert_after(explanation, marker_two)
    insert_after(marker_two, marker_three)
    p = base.find_paragraph(root, "For each cycle, ovulation is drawn")
    set_single_citation_paragraph(
        p,
        "For each cycle, ovulation is drawn from a Bernoulli distribution using the resolved person-level probability. Natural cycle length is drawn from the shifted lognormal process in Equations 2 and 3, rather than the former symmetric Gaussian. Ovulatory cycles use a luteal distribution centered on 12.4 days; the follicular interval absorbs most remaining cycle-length variation. Natural Cycles data reported a 29.3-day mean cycle, 16.9-day mean follicular phase, and 12.4-day mean luteal phase across 612,613 ovulatory cycles from 124,648 users. ",
        " The implemented latent luteal standard deviation is 3.0 days before truncation and rounding; the validation target is the published 2.4-day realized SD.",
    )
    bleeding = base.find_paragraph(root, "Bleeding duration is sampled")
    base.replace_literal(bleeding, "4.7 days with a standard deviation of 1.0 day", "4.0 days with a standard deviation of 1.5 days")
    base.replace_literal(
        bleeding,
        "The 4.7-day value is an investigator-selected calibration setting. Bull et al. reported a 4.0 ± 1.5-day mean bleeding duration in Table 1; the calibration assessment therefore compares the realized simulation with that ",
        "Bull et al. reported the same 4.0 ± 1.5-day distribution in Table 1; both its mean and standard deviation are direct validation targets. ",
    )
    base.replace_literal(bleeding, "published distribution. ", "")
    table_a4_caption = base.find_paragraph(root, "Appendix Table A4.")
    table_a4_caption_text = base.text_of(table_a4_caption)
    if "version 0.2.0" in table_a4_caption_text:
        base.replace_literal(table_a4_caption, "version 0.2.0", "version 0.3.0")
    else:
        base.replace_literal(table_a4_caption, "version 0.1.0", "version 0.3.0")
    base.set_paragraph_text(
        base.find_paragraph(root, "Ovulatory trajectories use seven control points"),
        "Ovulatory trajectories in version 0.3.0 use the complete daily serum estradiol and progesterone medians measured in 20 healthy volunteers and synchronized to the serum LH peak. "
        + STRICKER_MARKER
        + " The simulator places ovulation 0.75 day after that event. For nonpositive LH-relative days, published one-day spacing is retained; positive offsets are multiplied by the realized post-LH interval divided by 14, so the published +14-day tail reaches the final cycle day. Progesterone uses the complete −15 to +14 series, producing a postovulatory rise, a broad midluteal summit, and late-luteal withdrawal. Estradiol uses the −1 to +14 segment after an ordinary follicular ramp and retains the published secondary luteal elevation. PCHIP interpolation, defined in Equations 6 and 7, connects these daily values without spline overshoot; Equation 8 defines the LH-relative event mapping.",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Appendix Table A3."),
        "Appendix Table A3. Complete daily ovulatory serum-hormone reference series used by HORMONE-CYCLE version 0.3.0, derived from Stricker et al. (2006) Table 1B and Figure 1. "
        + STRICKER_MARKER
        + " Day 0 is the synchronized serum LH peak; the simulator ovulation marker is 0.75 day later. Estradiol was converted from picomoles per liter to picograms per milliliter and progesterone from nanomoles per liter to nanograms per milliliter.",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Appendix Figure A1."),
        "Appendix Figure A1. HORMONE-CYCLE diary-generation workflow. Each generated cycle samples structure and bleeding, maps the LH-aligned daily serum envelope to the realized ovulation and luteal interval, applies the long-follicular E2 branch when applicable, and adds endpoint-bridged serial noise after PCHIP interpolation. Cycle 1 is generated in full and diary day 1 is selected uniformly from its realized cycle days. Output proceeds forward through the remainder of cycle 1 and successive complete cycles until the requested diary length is reached; there is no wrapping.",
    )
    anovulatory_paragraph = base.find_paragraph(root, "Anovulatory cycles use four lower-amplitude control points")
    long_cycle_paragraph = make_paragraph_like(
        anovulatory_paragraph,
        "Long follicular phases are not created by horizontally stretching the ordinary estradiol curve. When the realized follicular interval is at least 24 days, the model keeps a 14-day terminal maturation segment aligned to ovulation and assigns extra time to a low early interval. A deterministic patient-and-cycle hash selects delayed dominant-follicle emergence by default or a failed-wave/replacement geometry in 25% of such cycles. Harlow et al. reported five heterogeneous urinary-oestrogen patterns in 28 long follicular phases, with delayed emergence most common; the implementation represents only two of those patterns. "
        + HARLOW_MARKER
        + " Mumford et al. independently found that in cycles longer than 35 days, E2 and LH peaks occurred about three days later than in normal-length cycles, supporting delayed timing rather than proportional stretching. "
        + MUMFORD_MARKER
        + " The 25% share and failed-wave amplitude are investigator-selected heterogeneity settings, not published prevalence estimates. Equation 9 defines the start of the terminal maturation interval.",
    )
    anovulatory_paragraph.getparent().insert(
        anovulatory_paragraph.getparent().index(anovulatory_paragraph),
        long_cycle_paragraph,
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Fixed inputs and a fixed seed produce identical diaries"),
        "Fixed inputs and a fixed seed produce identical diaries. SHA-256 domain separation creates independent profile, cycle, and observation-start streams, so changing the diary start rule does not perturb the latent person or generated cycles. For computational efficiency, non-audit participants in the large paper simulation use a compact renderer that consumes the same random draws as the full renderer, retains cycle timing, ovulation, midluteal progesterone and inadequate-luteal-phase status, and omits unused daily concentration objects. Validation and the retained 1% audit sample use full daily hormone curves; automated equivalence tests compare both paths, including partial first and final cycles. Reproducibility records should preserve the repository commit, configuration, seed, requested diary length, age and modifier inputs, and validation-report hash. The implementation omits pregnancy, postpartum physiology, medication changes, secular drift in an individual’s latent mean or variability component, missing diary entries, bleeding intensity, laboratory-assay error, and mechanistic endocrine feedback. Modifier combinations are coarse profile transformations for synthetic stress testing; causal treatment effects and individual clinical prediction remain outside scope.",
    )

    # Replace the old 12 native equations by markers; the audited equation skill
    # will insert the expanded 16-equation manifest after this script completes.
    replace_equations_with_markers(root)

    # Chapter 2 is rewritten as an explicit calibration/validation assessment.
    base.set_paragraph_text(base.find_exact_paragraph(root, "Chapter 2. Internal calibration and validation status of HORMONE-CYCLE"), "Chapter 2. Calibration and validation status of HORMONE-CYCLE")
    base.set_paragraph_text(base.find_exact_paragraph(root, "2.1 Evaluation terminology and design"), "2.1 Evaluation terminology, source separation, and design")
    base.set_paragraph_text(
        base.find_paragraph(root, "This chapter reports internal target reproduction"),
        "This chapter distinguishes calibration-target reproduction, held-out aggregate cross-checks, waveform construction checks, visual checks, and modifier stress tests. AWHS and Bull informed cycle calibration, and the complete Stricker daily series constructs the ovulatory waveform. Cunningham was withheld from cycle fitting, while Anckaert was withheld from hormone-waveform construction; both are independent at the aggregate-source level rather than participant-level validation. Harlow informed long-follicular E2 geometry, and Mumford supplied independent long-cycle timing context.",
    )
    design = base.find_paragraph(root, "The quality-control design follows established")
    set_single_citation_paragraph(
        design,
        "The quality-control design follows established simulation-study reporting principles. ",
        f" The baseline command was equivalent to “hormone_cycler validate --patients 10000 --days 365 --seed 7 --start-mode random.” The validation workflow restricted this baseline cohort to ages 18–54.9 to match AWHS adult eligibility. Secondary modifier scenarios used 1,200 age-matched participants and paired unmodified cohorts generated from the same seed: ages 18–44.9 for PCOS, contraception, IUD, and dysmenorrhea; ages 45–54.9 for perimenopause; and ages 13–17.9 for peri-menarche. Acceptance rules were encoded in src/hormone_cycler/hormone_constants.py before the reported execution. The run evaluated {len(validation['calibration_metrics'])} calibration and waveform metrics, {len(validation['external_crosscheck_metrics'])} held-out Cunningham metrics, and eight modifier scenarios. The primary gate required every calibration, waveform, and held-out metric to pass; modifier results were secondary stress tests.",
    )
    estimand_paragraph = base.find_paragraph(root, "The primary sources used for parameter development")
    base.set_paragraph_text(
        estimand_paragraph,
        "The AWHS age-band comparisons use equal participant weighting and at most the first 11 cycles, matching the source cohort’s median follow-up. The Cunningham cross-check uses the same simulated 12-month-equivalent summaries but retains the source study’s different age bands and estimator. AWHS’s table footnote says mean adjacent-cycle difference without specifying absolute values; because its methods define adjacent-cycle differences as absolute values, that convention was prespecified here. These design choices prevent the previous error of treating pairwise threshold exceedances as the participant-level irregularity estimand.",
    )
    provenance_audit = make_paragraph_like(
        estimand_paragraph,
        "Before the definitive validation and paper rerun, a registry-wide provenance audit "
        "checked the title, PubMed identifier, DOI, source URL, and declared evidence role for "
        "all 20 scientific-source records against PubMed. Five legacy identifiers that resolved "
        "to unrelated articles and one citation-label mismatch were corrected. The fitted AWHS, "
        "Bull, and Stricker quantities and the held-out Cunningham results were unaffected; the "
        "corrections prevent secondary context and modifier sources from being misidentified. "
        "The machine-readable audit report is archived with the validation artifacts.",
    )
    insert_after(estimand_paragraph, provenance_audit)
    base.set_paragraph_text(base.find_exact_paragraph(root, "2.2 Baseline calibration targets and tolerances"), "2.2 Healthy-cycle calibration targets and acceptance criteria")
    base.set_paragraph_text(
        base.find_paragraph(root, "The 19 distributional checks comprise"),
        "The AWHS calibration includes five outcomes in each of eight age bands: mean cycle length, pooled within-person SD, participant prevalence with mean absolute adjacent-cycle difference ≥7 days, cycles <24 days, and cycles >38 days. Practical margins are ±0.55 day for means; ±0.35 day for within-person SD below age 50 and ±1.0 day at age ≥50; ±3.5 percentage points for participant irregularity; and ±3 percentage points for cycle tails below age 50 and ±5 points at age ≥50. Bull checks add follicular, luteal, and bleeding means plus luteal and bleeding SDs. These margins assess aggregate similarity, not sampling confidence intervals or individual prediction.",
    )
    hormone_paragraph = base.find_paragraph(root, "Fourteen hormone-anchor checks compare")
    heading_template = base.find_exact_paragraph(root, "2.2 Healthy-cycle calibration targets and acceptance criteria")
    normal_template = hormone_paragraph
    held_heading = make_paragraph_like(heading_template, "2.3 Held-out aggregate validation and critical interpretation")
    held_one = make_paragraph_like(
        normal_template,
        "Cunningham et al. reported age-specific 12-month participant means and mean participant-specific cycle-length SDs from a global Flo cohort. " + CUNNINGHAM_MARKER + " The source was not used for fitting. Prespecified practical-equivalence margins were ±1.5 days for mean cycle length and ±1.25 days for mean personal SD, widened to ±2.5 and ±3.5 days, respectively, at ages 51–55 because the menopause-transition cohorts and estimators differ substantially.",
    )
    held_two = make_paragraph_like(
        normal_template,
        "The external summary check passed, but the interpretation is qualified. Agreement was strongest from ages 18–45. At ages 51–55, the simulator’s variability was higher than Flo but close to the much larger AWHS ≥50 residual SD. The two published cohorts therefore disagree in the region with sparse, selective, and rapidly changing cycles. The simulator retains an intermediate high-variability behavior rather than fitting the held-out source. This is a model-form uncertainty, not evidence that one cohort is correct.",
    )
    hormone_heading = make_paragraph_like(heading_template, "2.4 Hormone waveform and phase-duration checks")
    parent = hormone_paragraph.getparent()
    idx = parent.index(hormone_paragraph)
    for element in [held_heading, held_one, held_two, hormone_heading]:
        parent.insert(idx, element)
        idx += 1
    base.set_paragraph_text(
        hormone_paragraph,
        "Fourteen hormone-amplitude checks compare seven estradiol and seven progesterone subphases with the independently measured Anckaert reference intervals; broad assay-aware windows account for platform and cohort differences. Eight daily morphology checks evaluate preovulatory E2 width, the secondary luteal E2 peak, progesterone plateau width, P4 rise and peak timing relative to ovulation, consecutive premenstrual withdrawal, terminal-to-peak ratio, and cross-cycle continuity. The validation implementation retains two diaries from each of eight age bands (16 total). The ordinary-cycle envelope is also overlaid directly on mapped Stricker medians, while 53-day delayed-emergence and failed-wave examples test the no-stretch rule. These are aggregate amplitude, construction, and software morphology checks—not validation of joint person-level endocrine trajectories or intraday progesterone pulses.",
    )
    set_single_citation_paragraph(
        base.find_paragraph(root, "Appendix Table A6."),
        f"Appendix Table A6. Complete healthy-cycle calibration, held-out aggregate cross-check, and hormone waveform results. The {len(validation['calibration_metrics'])} calibration and waveform metrics comprise 40 AWHS age-band metrics, five Bull phase/bleeding metrics, 14 independent Anckaert amplitude/order checks, and eight Stricker-derived daily morphology checks. Calibration and construction sources are ",
        " Fourteen Cunningham metrics are held out from cycle fitting. " + CUNNINGHAM_MARKER + " Anckaert was held out from waveform construction. Cycle and phase metrics use 10,000 adults aged 18–54.9, 365 days per participant, seed 7, randomized starting phase, equal participant weighting, and at most 11 cycles per participant. Hormone metrics use 16 retained diaries balanced across eight age bands. Every row met its prespecified acceptance band. This qualified pass does not constitute individual-level external validation. Durations are in days; estradiol is in picograms per milliliter; progesterone is in nanograms per milliliter.",
    )
    base.set_paragraph_text(base.find_exact_paragraph(root, "2.3 Modifier-scenario checks"), "2.5 Age-matched modifier software stress tests")
    base.set_paragraph_text(
        base.find_paragraph(root, "Each modifier was simulated separately"),
        "Each modifier was simulated separately with 1,200 participants and compared with an unmodified cohort generated from the same seed and age range. PCOS, oral-contraceptive, intrauterine-device, and dysmenorrhea scenarios used ages 18–44.9; perimenopause used ages 45–54.9; and peri-menarche used ages 13–17.9. The checks assess cycle length, irregularity, ovulation, bleeding, or amenorrhea according to the feature addressed by the cited literature. The papers generally support effect direction or broad ranges; exact numerical margins are investigator-selected regression guards. Accordingly, these are age-matched software stress tests, not held-out clinical validation.",
    )
    modifier_caption = base.find_paragraph(root, "Appendix Table A7.")
    modifier_caption_text_nodes = modifier_caption.xpath(".//w:t", namespaces=base.NS)
    if not modifier_caption_text_nodes:
        raise ValueError("Appendix Table A7 caption has no text nodes")
    modifier_caption_text_nodes[0].text = (
        "Appendix Table A7. Secondary age-matched modifier stress-test summary. "
        "Each scenario uses 1,200 participants and an unmodified cohort generated with the "
        "same seed and age range. “Code-defined checks” counts the criteria listed individually "
        "in Table A8. Exact margins are investigator-selected regression guards; passing "
        "indicates behavior in the declared direction/range, not clinical validity. Supporting "
        "sources are attached directly to each scenario: polycystic ovary syndrome is compared "
        "with Mortimer et al. (2026) and Jarrett et al. (2020) "
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Appendix Table A8."),
        "Appendix Table A8. Auditable secondary modifier stress-test criteria. Each scenario uses 1,200 participants and a seed- and age-matched unmodified cohort. Acceptance bounds were defined in the validation code and are investigator-selected unless the criterion names a direct published quantity. The supporting papers are named in the source column; they generally support directions or broad ranges rather than the exact numerical bounds.",
    )
    base.set_paragraph_text(base.find_exact_paragraph(root, "2.4 Graphical calibration summary"), "2.6 Graphical calibration summary and representative traces")
    set_single_citation_paragraph(
        base.find_paragraph(root, "Appendix Figure A2."),
        "Appendix Figure A2. Healthy-cycle calibration and held-out aggregate validation. Panels A–D compare simulated age-specific mean cycle length, pooled within-person SD, participant irregularity, and short/long tails with AWHS. Panel F compares follicular, luteal, and bleeding means and SDs with Bull et al. Calibration sources are ",
        " Panel E compares mean participant-specific SD with the held-out Cunningham Flo cohort. " + CUNNINGHAM_MARKER + " Published and simulated lines are aggregate summaries; the older-age discrepancy in panel E is retained as model-form uncertainty.",
    )
    base.set_paragraph_text(base.find_exact_paragraph(root, "2.5 Interpretation and remaining validation needs"), "2.7 Validation conclusion and remaining needs")
    base.set_paragraph_text(
        base.find_paragraph(root, "The current checks show that the implementation reproduces"),
        "The primary gate is a qualified pass: version 0.3.0 reproduces all prespecified fitted aggregate targets, passes every held-out Cunningham cycle margin and independent Anckaert hormone bound, and passes all daily morphology checks. The P4 envelope is now sustained across several midluteal days rather than concentrated in a single triangular peak; its ≥5-ng/mL rise occurs after ovulation and withdrawal approaches the next menses. Ordinary-cycle E2 retains its recognizable follicular peak and secondary luteal elevation. Long-cycle E2 no longer reflects simple horizontal stretching, but only two of Harlow’s five reported long-follicular patterns are implemented, and their mixture is not prevalence-calibrated. The daily population-median envelope also omits intraday hormone pulsatility and does not reproduce individual longitudinal endocrine trajectories. Independent participant-level validation should use held-out daily bleeding, ovulation, and hormone records; align estimands prospectively; and examine joint distributions, serial correlation, between-person heterogeneity, assay effects, and missingness.",
    )

    base.set_paragraph_text(
        base.find_paragraph(root, "The completed manifest stores the analysis-code fingerprint"),
        "The completed manifest stores the analysis-code fingerprint "
        f"{run_manifest['analysis_code_sha256']} and configuration fingerprint "
        f"{run_manifest['analysis_config_sha256']}. These Secure Hash Algorithm 256-bit fingerprints identify the exact v13 analysis code and configuration used for the completed run.",
    )

    # Refresh C3 exploratory prose and caption from the rerun.
    exploratory_row = exploratory.iloc[0]
    reasons = json.loads(exploratory_row["reason_counts"])
    base.set_paragraph_text(
        base.find_paragraph(root, "The retained daily audit sample was selected"),
        "The retained daily audit sample was selected independently within each cohort without replacement at a 1% fraction. NumPy’s default random-number generator used a deterministic 32-bit seed derived from master seed 20260505, the cohort name, and “audit_sample.” The heterogeneous-cohort seed was 529110050. The type C3 exploratory analysis attempted all "
        f"{int(exploratory_row['n_attempted_audit_participants'])} retained heterogeneous participants: {int(exploratory_row['n_ratio_c3_applicable'])} had ratio-level type C3 applicability, "
        f"{int(exploratory_row['n_nb_classifiable'])} met regression data requirements, {int(reasons.get('fewer_than_required_complete_ilp_cycles', 0))} had fewer than four complete inadequate-luteal-phase cycles, and "
        f"{int(reasons.get('seizure_days_below_minimum', 0))} had fewer than four seizure days. All {int(exploratory_row['n_nb_classifiable'])} classifiable participants used the negative-binomial fit; no robust-Poisson fallback or regression failure occurred. "
        f"{int(exploratory_row['positives'])} were positive.",
    )
    base.set_paragraph_text(
        base.find_paragraph(root, "Appendix Table S7."),
        "Appendix Table S7. Exploratory type C3 negative-binomial calibration result in the retained 1% daily audit sample. All "
        f"{int(exploratory_row['n_attempted_audit_participants'])} retained heterogeneous participants were attempted; {int(exploratory_row['n_ratio_c3_applicable'])} were ratio-applicable, "
        f"{int(exploratory_row['n_nb_classifiable'])} were regression-classifiable, and {int(exploratory_row['positives'])} were positive. “All-attempted rate” is "
        f"{int(exploratory_row['positives'])}/{int(exploratory_row['n_attempted_audit_participants'])}. The 95% Wilson interval describes Monte Carlo uncertainty under this configured simulation. No robust-Poisson fallback was used.",
    )

    # Live REF fields keep their bookmarks; Microsoft Word updates cached equation
    # numbers after the two cycle equations and two waveform equations are inserted.
    base.replace_with_ref_sequence(
        base.find_paragraph(root, "Age selects one of eight calibration bands"),
        "Equation 1",
        ["Equation ", ("Eq_cycle_irregularity", 1)],
    )
    base.replace_with_ref_sequence(
        base.find_paragraph(root, "Each participant is assigned once"),
        "Equations 2 and 3",
        [
            "Equations ",
            ("Eq_cycle_shifted_lognormal_parameter", 2),
            " and ",
            ("Eq_cycle_length_generation", 3),
        ],
    )
    base.replace_with_ref_sequence(
        base.find_paragraph(root, "For each cycle, ovulation is drawn"),
        "Equations 2 and 3",
        [
            "Equations ",
            ("Eq_cycle_shifted_lognormal_parameter", 2),
            " and ",
            ("Eq_cycle_length_generation", 3),
        ],
    )

    # Replace Appendix A1/A2 and append the representative-trace and waveform figures.
    rels = base.relationship_map(relationships)
    media: dict[str, Path] = {
        rels["rId10"]: workflow_figure,
        rels["rId11"]: validation_figure,
        rels["rId12"]: supplement / "figS1_seizure_process_distributions.png",
        rels["rId13"]: supplement / "figS2_seizure_rhythm_distributions.png",
        rels["rId14"]: supplement / "figS3_menstrual_cycle_distributions.png",
        rels["rId15"]: supplement / "figS4_age_and_modifier_distributions.png",
        rels["rId16"]: supplement / "figS5_simulated_classification_associations.png",
    }
    for rid in ["rId10", "rId11", "rId12", "rId13", "rId14", "rId15", "rId16"]:
        base.update_drawing_aspect(root, rid, media[rels[rid]])
    new_rid, new_target = add_example_figure(root, relationships, examples_figure)
    media[new_target] = examples_figure
    waveform_rid, waveform_target = add_waveform_figure(
        root, relationships, waveform_figure
    )
    media[waveform_target] = waveform_figure

    citation_count = inject_cunningham_fields(root, "(8)")
    if citation_count != 5:
        raise ValueError(f"Expected five new appendix Cunningham citations, inserted {citation_count}")
    expected_single_fields = [
        (STRICKER_MARKER, STRICKER_KEY, "(7)", "stricker", 3),
        (HARLOW_MARKER, HARLOW_KEY, "(9)", "harlow", 3),
        (MUMFORD_MARKER, MUMFORD_KEY, "(10)", "mumford", 2),
        (ANCKAERT_MARKER, ANCKAERT_KEY, "(11)", "anckaert", 1),
    ]
    for marker, key, displayed, slug, expected in expected_single_fields:
        inserted = inject_single_source_fields(
            root, marker, key, displayed, slug
        )
        if inserted != expected:
            raise ValueError(
                f"Expected {expected} new appendix {slug} citations, inserted {inserted}"
            )
    base.write_docx(output, entries, root, media, relationships)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-source", type=Path, default=Path("outputs/epilepsia_submission/draft_v11_hormone_repaired.docx"))
    parser.add_argument("--appendix-source", type=Path, default=Path("outputs/epilepsia_submission/draft_v11_appendix_hormone_repaired.docx"))
    parser.add_argument("--main-output", type=Path, default=Path("outputs/epilepsia_submission/draft_v13_waveform_recalibrated.docx"))
    parser.add_argument("--appendix-output", type=Path, default=Path("outputs/epilepsia_submission/draft_v13_appendix_waveform_recalibrated_pre_equations.docx"))
    parser.add_argument("--outputs", type=Path, default=Path("outputs/random_start_full_v13_waveform_recalibration"))
    parser.add_argument("--supplement", type=Path, default=Path("outputs/random_start_supplement_v13_waveform_recalibration"))
    parser.add_argument("--validation", type=Path, default=Path("examples/reports/healthy_cycle_validation_v13.json"))
    parser.add_argument("--validation-figure", type=Path, default=Path("examples/reports/hormone_cycle_validation_v13.png"))
    parser.add_argument("--examples-figure", type=Path, default=Path("examples/reports/healthy_cycle_example_traces_v13.png"))
    parser.add_argument("--workflow-figure", type=Path, default=Path("examples/reports/hormone_cycle_workflow_v13.png"))
    parser.add_argument("--waveform-figure", type=Path, default=Path("examples/reports/hormone_waveform_validation_v13.png"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    update_main(args.main_source, args.main_output, args.outputs, args.supplement)
    update_appendix(
        args.appendix_source,
        args.appendix_output,
        args.outputs,
        args.supplement,
        args.validation,
        args.validation_figure,
        args.examples_figure,
        args.workflow_figure,
        args.waveform_figure,
    )
    print(args.main_output.resolve())
    print(args.appendix_output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
