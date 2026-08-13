#!/usr/bin/env python3
"""Build a populated null catamenial-epilepsy analysis notebook from current output files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


CORE_DEFINITIONS = [
    "A_exact_any",
    "A_windowed_any",
    "A_windowed_excluding_C3",
    "A_windowed_C1_or_C2",
    "A_windowed_C1_only",
    "A_windowed_C2_only",
    "A_windowed_C3_only",
    "B_minimum_data_any",
    "B_minimum_data_excluding_C3",
    "B_minimum_data_C1_or_C2",
    "C_reproducibility_any",
    "C_reproducibility_C1_or_C2",
    "C_reproducibility_12cycle_any",
    "D_nb_regression_any",
    "D_nb_regression_C1_or_C2",
    "D_nb_regression_window_alpha_C1_or_C2",
]
HISTORICAL_DEFINITIONS = [
    "H1_newmark_penry_any",
    "H1_newmark_penry_66_7_any",
    "H2_duncan1993_any",
    "H3_herzog1997_twofold_any",
    "H4_reddy2007_any_phase2x_any",
]
FIGURES = [
    (
        "Figure 1. False-positive rate by window",
        "fig1_false_positive_by_window",
        "Calendar-month false-positive rate for practical monitoring durations, split by cohort.",
        "Apparent classification rates are shown as percentages among classifiable participant windows for random calendar windows. The dashed reference line marks 5%.",
    ),
    (
        "Figure 2. C-pattern decomposition",
        "fig2_pattern_decomposition",
        "Mutually exclusive C1/C2/C3 pattern categories for full-diary windows.",
        "Bars show the share of all attempted full-diary windows in each pattern category, including indeterminate windows, under strict Herzog phase labeling.",
    ),
    (
        "Figure 3. Study prevalence distribution",
        "fig3_study_prevalence_distribution_3month",
        "Study-level Monte Carlo distribution for 3-month null studies with n=30, n=50, and n=100.",
        "Each curve summarizes simulated studies using random 3-month windows and the windowed Herzog threshold definition. The y-axis is the proportion of simulated studies; vertical reference lines mark benchmark apparent CE prevalence values.",
    ),
    (
        "Figure 4. Indeterminate versus false-positive frontier",
        "fig4_indeterminate_vs_fpr_frontier",
        "Tradeoff between rejecting underspecified windows and the false-positive rate among classifiable windows.",
        "Each point is a definition-by-window-by-cohort result. Points farther right have more indeterminate windows; points higher on the plot have more false positives among windows that remained classifiable.",
    ),
    (
        "Appendix Figure. Historical versus core definitions",
        "fig4_historical_vs_core_definitions",
        "Assumption-based historical rules compared with core protocol definitions.",
        "The historical definitions are exploratory operationalizations and are plotted next to the core definitions only to show their null false-positive behavior under the same 3-month window setting.",
    ),
    (
        "Appendix QC Figure. Null cycle-day seizure profile",
        "fig5_qc_null_cycle_day_profile",
        "Quality-control cycle-day seizure profile in the daily audit sample.",
        "The audit sample contains 1% of participant daily rows. Lines show average daily seizure frequency by observed menstrual cycle day with approximate Poisson error bars.",
    ),
]

COHORT_DISPLAY = {
    "healthy_ovulatory": "healthy ovulatory",
    "population": "heterogeneous menstruating-age",
}
DEFINITION_DISPLAY = {
    "A_exact_any": "Exact Herzog 2004, any CE pattern",
    "A_windowed_any": "Windowed Herzog thresholds",
    "A_windowed_excluding_C3": "Windowed Herzog thresholds, excluding C3",
    "A_windowed_C1_or_C2": "Windowed Herzog C1/C2 union",
    "A_windowed_C1_only": "Windowed Herzog C1 only",
    "A_windowed_C2_only": "Windowed Herzog C2 only",
    "A_windowed_C3_only": "Windowed Herzog C3 only",
    "B_minimum_data_any": "Windowed Herzog with minimum data",
    "B_minimum_data_excluding_C3": "Windowed Herzog with minimum data, excluding C3",
    "B_minimum_data_C1_or_C2": "Windowed Herzog C1/C2 with minimum data",
    "C_reproducibility_any": "Cycle reproducibility, 6-cycle rule",
    "C_reproducibility_C1_or_C2": "Cycle reproducibility C1/C2, 6-cycle rule",
    "C_reproducibility_12cycle_any": "Cycle reproducibility, 12-cycle sensitivity",
    "D_nb_regression_any": "Negative-binomial regression C1/C2, stabilized dispersion",
    "D_nb_regression_C1_or_C2": "Negative-binomial regression C1/C2",
    "D_nb_regression_window_alpha_any": "Negative-binomial regression, window-only dispersion",
    "D_nb_regression_window_alpha_C1_or_C2": "Negative-binomial regression C1/C2, window-only dispersion",
    "H1_newmark_penry_any": "Newmark-Penry perimenstrual rule",
    "H1_newmark_penry_66_7_any": "Newmark-Penry two-thirds sensitivity",
    "H2_duncan1993_any": "Duncan 1993 ten-day rule",
    "H3_herzog1997_twofold_any": "Herzog 1997 twofold rule",
    "H4_reddy2007_any_phase2x_any": "Reddy 2007 any-phase twofold rule",
}
SUBSET_DISPLAY = {
    "all": "All windows",
    "ge_1_seizure_day_per_month": "At least 1 seizure day per month",
    "ge_2_seizures_per_month": "At least 2 seizures per month",
    "strict_23_35_day_cycles_only": "Strict 23-35 day cycles only",
    "common_classifiable_subset": "Common classifiable subset",
    "apparent_prevalence_all": "All participants",
    "apparent_prevalence_classifiable": "Classifiable participants only",
}
TEXT_DISPLAY = {
    "<1 seizure-day/month": "Less than 1 seizure day per month",
    "1 to <4 seizure-days/month": "1 to <4 seizure days per month",
    "4 to <10 seizure-days/month": "4 to <10 seizure days per month",
    ">=10 seizure-days/month": "At least 10 seizure days per month",
    "SD cycle length <2 days": "Cycle length SD < 2 days",
    "SD cycle length 2 to <4 days": "Cycle length SD 2 to <4 days",
    "SD cycle length >=4 days": "Cycle length SD at least 4 days",
    "strict_herzog": "Strict Herzog",
    "luteal_anchored_ovulatory": "Luteal-anchored ovulatory",
    "0 to 3": "0-3 seizure days",
    "4 to 7": "4-7 seizure days",
    "8 to 15": "8-15 seizure days",
    "ge 16": ">=16 seizure days",
    "seizure frequency": "Seizure-frequency stratum",
    "cycle regularity": "Cycle-regularity stratum",
    "window seizure days": "Window seizure-day stratum",
    "True": "Yes",
    "False": "No",
}
COLUMN_DISPLAY = {
    "cohort": "Cohort",
    "participants": "Participants",
    "age_mean": "Mean age, years",
    "age_sd": "Age SD, years",
    "mean_cycle_length": "Mean cycle length, days",
    "sd_cycle_length": "Mean cycle-length SD, days",
    "ovulatory_fraction": "Ovulatory cycles",
    "seizure_days_per_month": "Seizure days per month",
    "seizures_per_month": "Seizures per month",
    "definition": "CE definition",
    "phase_mode": "Phase labeling",
    "pattern_category": "Pattern category",
    "n_participants": "Participants per study",
    "n_windows": "Windows analyzed",
    "n_classifiable": "Classifiable windows",
    "positives": "False-positive windows",
    "false_positive_rate": "False-positive rate",
    "positive_rate_all_attempted": "Rate among all attempted",
    "FPR": "False-positive rate",
    "FPR (95% CI)": "False-positive rate (95% CI)",
    "wilson95_low": "95% CI lower",
    "wilson95_high": "95% CI upper",
    "indeterminate_rate": "Indeterminate windows",
    "window": "Observation window",
    "subset": "Analysis denominator",
    "stratum_type": "Stratum type",
    "stratum": "Stratum",
    "assumption_based_historical": "Assumption-based historical rule",
    "path": "Output file",
    "size_mb": "Size, MB",
    "sha256": "SHA-256 prefix",
    "Monte Carlo studies": "Monte Carlo studies",
    "Mean apparent CE prevalence": "Mean apparent CE prevalence",
    "2.5th percentile": "2.5th percentile",
    "97.5th percentile": "97.5th percentile",
    "Probability prevalence at least 39.1%": "Probability prevalence at least 39.1%",
    "Probability prevalence at least 44.2%": "Probability prevalence at least 44.2%",
}


def display_cohort(value: object) -> str:
    return COHORT_DISPLAY.get(str(value), str(value).replace("_", " "))


def display_text(value: object) -> str:
    text = str(value)
    if text in DEFINITION_DISPLAY:
        return DEFINITION_DISPLAY[text]
    if text in SUBSET_DISPLAY:
        return SUBSET_DISPLAY[text]
    if text in TEXT_DISPLAY:
        return TEXT_DISPLAY[text]
    # Longest/restricted replacements first so internal labels do not leak into
    # presentation text while stored output files keep their analysis keys.
    replacements = {
        "healthy_ovulatory": "healthy ovulatory",
        "healthy ovulatory and population": "healthy ovulatory and heterogeneous menstruating-age",
        "population": "heterogeneous menstruating-age",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def display_column(value: object) -> str:
    text = str(value)
    return COLUMN_DISPLAY.get(text, display_text(text).replace("_", " ").strip().title())


def display_cohort_sizes(sizes: dict[str, Any]) -> dict[str, Any]:
    return {display_cohort(k): v for k, v in sizes.items()}


def with_display_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "cohort" in out.columns:
        out["cohort"] = out["cohort"].map(display_cohort)
    for col in ["subset", "stratum", "stratum_type", "definition", "window"]:
        if col in out.columns:
            out[col] = out[col].map(lambda x: x if pd.isna(x) else display_text(x))
    out = out.rename(columns={col: display_column(col) for col in out.columns})
    return out


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    output_dir = (repo / args.output_dir).resolve()
    notebook_path = (repo / args.notebook).resolve()
    notebook_path.parent.mkdir(parents=True, exist_ok=True)

    data = load_outputs(output_dir)
    cells = build_cells(repo, output_dir, data)
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "pygments_lexer": "ipython3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_path.write_text(json.dumps(notebook, indent=2), encoding="utf-8")
    print(notebook_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root.")
    parser.add_argument("--output-dir", default="outputs", help="Directory containing analysis outputs.")
    parser.add_argument(
        "--notebook",
        default="notebooks/paper1_null_ce_analysis.ipynb",
        help="Notebook path to create.",
    )
    return parser.parse_args()


def load_outputs(output_dir: Path) -> dict[str, Any]:
    required = [
        "participant_summary.parquet",
        "window_results.parquet",
        "study_level_3month.parquet",
        "summary_tables.csv",
        "manifest.json",
    ]
    missing = [name for name in required if not (output_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing required output files in {output_dir}: {missing}")
    return {
        "participants": pd.read_parquet(output_dir / "participant_summary.parquet"),
        "windows": pd.read_parquet(output_dir / "window_results.parquet"),
        "study": pd.read_parquet(output_dir / "study_level_3month.parquet"),
        "summary": pd.read_csv(output_dir / "summary_tables.csv"),
        "manifest": json.loads((output_dir / "manifest.json").read_text(encoding="utf-8")),
    }


def build_cells(repo: Path, output_dir: Path, data: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = data["manifest"]
    summary = data["summary"]
    cells: list[dict[str, Any]] = []

    cells.append(markdown_cell(title_markdown(data)))
    cells.append(markdown_cell(cohort_definition_markdown()))
    cells.append(markdown_cell(hormone_validation_markdown(repo)))
    cells.append(markdown_cell(protocol_plan_markdown(manifest)))
    cells.append(markdown_cell("## Reproducible function calls\n\nThese cells are the exact calls used to regenerate the analysis outputs. Run the smoke call for a quick end-to-end check; run the full call for the defined 100,000-participant analysis."))
    cells.append(code_cell(reproduction_code(output_dir, repo)))
    cells.append(markdown_cell("## Load the current populated outputs\n\nThe remaining notebook cells read the existing output artifacts. This keeps figure and table rendering fast and reproducible after either a smoke run or a full run."))
    cells.append(code_cell(load_outputs_code(output_dir, repo)))

    cells.append(markdown_cell(table_intro("Table 1. Cohort and diary summary", "This table verifies that both defined cohorts are represented separately, that cycle summaries are available, and that seizure-burden metrics were carried through from the seizure simulator. It is the first QC table because every downstream apparent-classification estimate depends on the cohort construction and diary burden.")))
    cells.append(code_cell(table_1_code()))
    cells.append(markdown_cell(md_table(table_1(data["participants"]))))
    cells.append(markdown_cell(table_caption("Table 1", "Cohort-level participant and diary summaries for the full simulation. Percentages use a 0-100% scale; seizure rates are monthly averages over the 36-month diary.")))

    cells.append(markdown_cell(table_intro("Table 2. Primary full-window false-positive rates", "This table is the primary result summary for person-window false-positive rates under the null. It uses the full diary window and reports classifiable denominators, positives, Wilson 95% intervals, and indeterminate rates separately by cohort and definition.")))
    cells.append(code_cell(table_2_code()))
    cells.append(markdown_cell(md_table(table_2(summary))))
    cells.append(markdown_cell(table_caption("Table 2", "Primary full-diary false-positive rates under the null. The denominator for the false-positive rate is the number of classifiable participant windows, and the confidence interval is Wilson 95%.")))

    cells.append(markdown_cell(table_intro("Table 3. Window-length sensitivity for core definitions", "This table shows why diary length matters. Short calendar windows can be classifiable for simple windowed ratios but not for minimum-data, reproducibility, or exact three-cycle rules; the indeterminate column quantifies that tradeoff.")))
    cells.append(code_cell(table_3_code()))
    cells.append(markdown_cell(md_table(table_3(summary))))
    cells.append(markdown_cell(table_caption("Table 3", "False-positive and indeterminate rates for every prespecified observation window and core definition. Exact Herzog 2004 is expected to be classifiable only for 3-complete-cycle windows.")))

    cells.append(markdown_cell(table_intro("Table 4. Strict Herzog versus luteal-anchored ovulatory sensitivity", "This table addresses whether false-positive rates depend on the strict Herzog periovulatory window expanding with cycle length. Strict Herzog remains primary for historical comparability; the luteal-anchored mode fixes the ovulatory window at four pre-luteal days.")))
    cells.append(code_cell(table_phase_mode_code()))
    cells.append(markdown_cell(md_table(table_phase_mode(summary))))
    cells.append(markdown_cell(table_caption("Table 4", "Full-diary and 3-month windowed Herzog results under strict Herzog and luteal-anchored ovulatory phase labeling.")))

    cells.append(markdown_cell(table_intro("Table 5. Null study-level prevalence benchmarks", "This table maps person-level false positives into apparent prevalence in illustrative studies of 30, 50, and 100 participants. It reports prevalence among all participants, prevalence among classifiable participants only, and the probability of exceeding the 39.1% and 44.2% benchmark values.")))
    cells.append(code_cell(table_4_code()))
    cells.append(markdown_cell(md_table(table_4(summary))))
    cells.append(markdown_cell(table_caption("Table 5", "Study-level Monte Carlo summary from null studies using 3-month windows. The interval columns are the 2.5th and 97.5th percentiles of study-level apparent prevalence.")))

    cells.append(markdown_cell(table_intro("Table 6. Trial-like conditioned subsets", "These subsets answer whether common enrollment restrictions reduce false positives or mainly change the classifiable denominator. The common-classifiable subset supports head-to-head comparisons because every listed core definition is defined on the same windows.")))
    cells.append(code_cell(table_5_code()))
    cells.append(markdown_cell(md_table(table_5(summary))))
    cells.append(markdown_cell(table_caption("Table 6", "Full-diary false-positive rates after applying trial-like eligibility restrictions or a common classifiable denominator. This separates changes in apparent risk from changes in analyzability.")))

    cells.append(markdown_cell(table_intro("Table 7. C1/C2/C3 decomposition and C3 exclusion", "This table directly addresses whether the heterogeneous-cohort signal is driven by C3 logic. It reports mutually exclusive pattern categories and C1/C2 union comparisons for full-diary windows.")))
    cells.append(code_cell(table_6_code()))
    cells.append(markdown_cell(md_table(table_6(summary))))
    cells.append(markdown_cell(table_caption("Table 7", "Full-diary pattern decomposition and C3-exclusion sensitivity. C3 is evaluated only when ILP logic is applicable.")))

    cells.append(markdown_cell(table_intro("Table 8. Negative-binomial dispersion sensitivity", "This table separates the full-diary stabilized-dispersion regression comparator from a full-window, window-only dispersion sensitivity.")))
    cells.append(code_cell(table_7_code()))
    cells.append(markdown_cell(md_table(table_7(summary))))
    cells.append(markdown_cell(table_caption("Table 8", "Negative-binomial apparent classification rates in full-diary windows using full-diary stabilized alpha and window-only alpha. Both use the same M/O model and Holm family.")))

    cells.append(markdown_cell(table_intro("Table 9. Seizure-burden and cycle-regularity strata", "The requested strata diagnose where false positives concentrate. Seizure-frequency strata use observed full-diary seizure-days per month, and window-seizure-day strata use total seizure days within each analyzed window.")))
    cells.append(code_cell(table_8_code()))
    cells.append(markdown_cell(md_table(table_8(summary))))
    cells.append(markdown_cell(table_caption("Table 9", "Apparent classification rates by observed seizure burden and cycle regularity strata. These strata identify where null positives are concentrated.")))

    cells.append(markdown_cell(table_intro("Table 10. Assumption-based historical definitions", "Historical rules are exploratory operationalizations rather than literal replications, so they are flagged separately. This table keeps them out of the core endpoint table while still showing their null false-positive behavior.")))
    cells.append(code_cell(table_9_code()))
    cells.append(markdown_cell(md_table(table_9(summary))))
    cells.append(markdown_cell(table_caption("Table 10", "Apparent classification rates for exploratory historical definitions. These rows are deliberately labeled as assumption-based and should not be interpreted as literal historical replications.")))

    cells.append(markdown_cell(table_intro("Table 11. Output manifest", "The manifest is machine-readable provenance: it lists every analysis artifact, size, checksum, and the assumptions that were not directly derivable from simulator outputs.")))
    cells.append(code_cell(table_10_code()))
    cells.append(markdown_cell(md_table(table_10(manifest))))
    cells.append(markdown_cell(table_caption("Table 11", "Machine-readable output provenance. The checksum prefix is included to support reproducibility checks without making the table unnecessarily wide.")))

    cells.append(markdown_cell("## Publication-ready figures\n\nEach figure is written as PNG for notebook viewing and PDF/SVG for publication workflows. Fractional outcomes are displayed on a 0-100% percentage scale. The code cell below is the function call that regenerates the figure set from the populated output tables."))
    cells.append(code_cell(figures_code()))
    for title, stem, description, caption in FIGURES:
        png_rel = rel_path(output_dir / f"{stem}.png", repo / "notebooks")
        pdf_rel = rel_path(output_dir / f"{stem}.pdf", repo / "notebooks")
        cells.append(markdown_cell(f"### {title}\n\n{description}\n\nPDF companion: [PDF version]({pdf_rel})\n\n![{title}]({png_rel})\n\n**Figure caption.** {caption}"))

    cells.append(markdown_cell(limitations_markdown(manifest)))
    return cells


def title_markdown(data: dict[str, Any]) -> str:
    participants = data["participants"]
    windows = data["windows"]
    study = data["study"]
    manifest = data["manifest"]
    total_n = len(participants)
    cohorts = ", ".join(
        f"{display_cohort(k)}: {v}" for k, v in participants["cohort"].value_counts().sort_index().items()
    )
    mode = "smoke" if total_n < 100000 else "full"
    return (
        "# Null Catamenial Epilepsy Analysis Notebook\n\n"
        f"Populated from `{manifest['output_dir']}` outputs. Detected analysis mode: **{mode}**.\n\n"
        f"- Participants: **{total_n:,}** ({cohorts})\n"
        f"- Primary window rows: **{len(windows):,}**\n"
        f"- Study-level Monte Carlo rows: **{len(study):,}**\n"
        f"- Manifest files: **{len(manifest['files']):,}**"
    )


def cohort_definition_markdown() -> str:
    return (
        "## Cohort terminology\n\n"
        "This notebook uses **heterogeneous menstruating-age** as the presentation label for the broader cohort key "
        "stored in the analysis files. In this null-simulation study it means an assumption-driven broader menstruating-age "
        "simulated cohort, not a disease-positive, clinically diagnosed, or demographically representative population. This cohort allows "
        "the hormone-cycle simulator's natural ovulatory and anovulatory behavior and its configured "
        "rates of cycle modifiers such as PCOS, peri-menarche, perimenopause, dysmenorrhea, and cycle "
        "irregularity when available. It is contrasted with the **healthy ovulatory** cohort, which is "
        "restricted to adult ovulatory cycling with those medical modifiers disabled where the simulator "
        "exposes those controls. In both cohorts, seizure and menstrual diaries are generated from "
        "separate deterministic random streams. HORMONE-CYCLE selects diary day 1 uniformly from "
        "the first generated cycle and then proceeds forward without wrapping. The seizure and "
        "menstrual diaries are aligned directly by calendar day without reordering, so any apparent "
        "catamenial epilepsy classification is a false positive under the null."
    )


def hormone_validation_markdown(repo: Path) -> str:
    """Summarize the versioned hormone gate that authorized this paper rerun."""

    report_path = repo / "examples" / "reports" / "healthy_cycle_validation_v14.json"
    if not report_path.exists():
        return "## HORMONE-CYCLE validation provenance\n\nThe versioned validation report was not found."
    report = json.loads(report_path.read_text(encoding="utf-8"))
    calibration = report.get("calibration_metrics", [])
    external = report.get("external_crosscheck_metrics", [])
    subgroup_payloads = report.get("subgroup_analysis", {}).get("subgroups", {})
    subgroup_passed = sum(bool(payload.get("passed")) for payload in subgroup_payloads.values())
    ages = report.get("input", {}).get("age_range", [None, None])
    age_text = f"{ages[0]:g}–{ages[1] - 0.1:g}" if all(value is not None for value in ages) else "not recorded"
    return (
        "## HORMONE-CYCLE v0.4.0 validation provenance\n\n"
        f"The primary paper rerun was authorized only after the versioned 10,000-participant "
        f"adult validation cohort (ages {age_text}) passed **{sum(bool(m['passed']) for m in calibration)}/{len(calibration)}** "
        f"calibration/waveform checks and **{sum(bool(m['passed']) for m in external)}/{len(external)}** held-out "
        f"Cunningham/Flo checks; **{subgroup_passed}/{len(subgroup_payloads)}** secondary age-matched modifier software stress tests also passed. "
        "The v0.4.0 waveform gate maps every in-cycle Stricker serum observation, uses an independent "
        "Anckaert subphase amplitude/order check, and adds Roos-informed timing-dispersion, terminal-P4, "
        "anti-time-warp, and cycle-boundary guards. Long follicular phases preserve terminal "
        "maturation rather than stretching an ordinary curve. The pass is qualified rather than clinical: "
        "the waveform represents a latent daily envelope, not within-day pulsatility or "
        "participant-level clinical validation. Cycle-summary agreement is strongest at ages 18–45, and the retained "
        "post-50 discrepancy reflects differing variability estimates in AWHS and Flo. Modifier margins are "
        "investigator-selected regression guards rather than externally estimated clinical thresholds. The machine-readable "
        "report, citation audit, and executable validation notebook are "
        "`examples/reports/healthy_cycle_validation_v14.json`, "
        "`examples/reports/hormone_citation_audit_v14.json`, and `show_validation.ipynb`."
    )


def protocol_plan_markdown(manifest: dict[str, Any]) -> str:
    config = manifest["config"]
    full_sizes = config["analysis_modes"]["full"].get("cohort_sizes", {})
    return (
        "## Exact analysis plan followed\n\n"
        "1. Simulate two cohorts separately and never pool results: healthy ovulatory and heterogeneous menstruating-age.\n"
        f"2. Full defined cohort sizes are `{display_cohort_sizes(full_sizes)}`; smoke mode uses `{config['analysis_modes']['smoke']['n_total']}` total participants.\n"
        f"3. For each participant, simulate an independent CHOCOLATES seizure diary and an independent hormone-cycle diary for `{config['analysis_modes']['full']['diary_months']}` months in full mode.\n"
        "4. Select diary day 1 uniformly from the first generated HORMONE-CYCLE cycle, continue forward without wrapping, and align the independently generated seizure and menstrual diaries directly by calendar day.\n"
        "5. Label phases on the full diary before subsetting windows, using strict Herzog labels for primary analyses and a luteal-anchored fixed ovulatory window for sensitivity analyses.\n"
        "6. Sample calendar windows, full 36-month windows, and complete-cycle windows exactly as configured.\n"
        "7. Classify windows using exact Herzog 2004, windowed Herzog thresholds, C3-exclusion and pattern-only sensitivities, minimum-data rules, reproducibility rules, full-window stabilized/window-dispersion NB regression, and assumption-based historical definitions.\n"
        "8. Summarize false positives and indeterminacy by cohort, phase mode, window, definition, seizure-burden stratum, participant-level status, pattern category, and study-level Monte Carlo benchmarks.\n"
        "9. Save outputs as parquet/CSV, publication figures as PNG/PDF/SVG, a 1% daily audit sample, and a manifest.\n\n"
        "### Recorded assumptions\n\n"
        + "\n".join(f"- {display_text(item)}" for item in manifest.get("assumptions", []))
    )


def reproduction_code(output_dir: Path, repo: Path) -> str:
    config_path = (
        "config_random_start_full.yaml"
        if (repo / "config_random_start_full.yaml").exists()
        else "config.yaml"
    )
    progress_path = rel_path(output_dir / "progress.json", repo)
    return f"""from pathlib import Path
import sys

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.core.utils import load_config
from paper1_null_ce.core.simulate import run_pipeline

config = load_config(ROOT / "{config_path}")

# Quick validation run used while developing and reviewing the pipeline. It is
# intentionally opt-in so executing this results notebook does not overwrite
# the already-populated definitive artifacts:
# smoke_result = run_pipeline(config, mode="smoke")

# Prespecified full analysis. This is intentionally separate because it is large:
# full_result = run_pipeline(config, mode="full")

# During a long run, check ETA from another terminal:
# python3.11 scripts/check_paper1_progress.py --progress {progress_path}
"""


def load_outputs_code(output_dir: Path, repo: Path) -> str:
    output_path = rel_path(output_dir, repo)
    return f"""from pathlib import Path
import json
import pandas as pd

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
OUTPUT_DIR = ROOT / "{output_path}"

participant_summary = pd.read_parquet(OUTPUT_DIR / "participant_summary.parquet")
window_results = pd.read_parquet(OUTPUT_DIR / "window_results.parquet")
study_path = OUTPUT_DIR / "study_level_3month.parquet"
if not study_path.exists():
    study_path = OUTPUT_DIR / "study_level_3month_n30.parquet"
study_level = pd.read_parquet(study_path)
summary_tables = pd.read_csv(OUTPUT_DIR / "summary_tables.csv")
manifest = json.loads((OUTPUT_DIR / "manifest.json").read_text())

participant_summary.shape, window_results.shape, study_level.shape, summary_tables.shape
"""


def table_1_code() -> str:
    return """cohort_summary = (
    participant_summary
    .groupby("cohort")
    .agg(
        participants=("participant_id", "nunique"),
        age_mean=("age", "mean"),
        age_sd=("age", "std"),
        mean_cycle_length=("mean_cycle_length", "mean"),
        sd_cycle_length=("sd_cycle_length", "mean"),
        ovulatory_fraction=("ovulatory_fraction", "mean"),
        seizure_days_per_month=("seizure_days_per_month", "mean"),
        seizures_per_month=("seizures_per_month", "mean"),
    )
    .reset_index()
)
cohort_summary
"""


def table_2_code() -> str:
    return """primary_full = summary_tables[
    (summary_tables.table_type == "window_false_positive")
    & (summary_tables.phase_mode == "strict_herzog")
    & (summary_tables.subset == "all")
    & (summary_tables.window_type == "full")
    & (summary_tables.definition.isin([
        "A_windowed_any", "A_windowed_C1_or_C2",
        "B_minimum_data_any", "B_minimum_data_C1_or_C2",
        "C_reproducibility_any", "D_nb_regression_C1_or_C2"
    ]))
].copy()
primary_full
"""


def table_3_code() -> str:
    return """window_sensitivity = summary_tables[
    (summary_tables.table_type == "window_false_positive")
    & (summary_tables.phase_mode == "strict_herzog")
    & (summary_tables.subset == "all")
    & (summary_tables.definition.isin([
        "A_exact_any", "A_windowed_any", "A_windowed_C1_or_C2",
        "B_minimum_data_C1_or_C2", "C_reproducibility_C1_or_C2",
        "D_nb_regression_C1_or_C2"
    ]))
].copy()
window_sensitivity
"""


def table_4_code() -> str:
    return """study_benchmarks = summary_tables[
    (summary_tables.table_type == "study_level_3month")
    & (summary_tables.phase_mode == "strict_herzog")
    & (summary_tables.definition.isin([
        "A_windowed_any", "B_minimum_data_C1_or_C2",
        "C_reproducibility_C1_or_C2", "D_nb_regression_C1_or_C2"
    ]))
].copy()
study_benchmarks
"""


def table_phase_mode_code() -> str:
    return """phase_mode_sensitivity = summary_tables[
    (summary_tables.table_type == "window_false_positive")
    & (summary_tables.subset == "all")
    & (
        (summary_tables.window_type == "full")
        | ((summary_tables.window_type == "calendar") & (summary_tables.window_value.astype(str) == "3"))
    )
    & (summary_tables.definition.isin(["A_windowed_any", "A_windowed_C1_or_C2", "A_windowed_C3_only"]))
].copy()
phase_mode_sensitivity
"""


def table_5_code() -> str:
    return """trial_like_subsets = summary_tables[
    (summary_tables.table_type == "window_false_positive")
    & (summary_tables.phase_mode == "strict_herzog")
    & (summary_tables.window_type == "full")
    & (summary_tables.subset.isin([
        "ge_1_seizure_day_per_month",
        "ge_2_seizures_per_month",
        "strict_23_35_day_cycles_only",
        "common_classifiable_subset",
    ]))
    & (summary_tables.definition.isin([
        "A_windowed_any", "A_windowed_C1_or_C2",
        "B_minimum_data_C1_or_C2",
        "C_reproducibility_C1_or_C2", "D_nb_regression_C1_or_C2"
    ]))
].copy()
trial_like_subsets
"""


def table_6_code() -> str:
    return """pattern_decomposition = summary_tables[
    (summary_tables.table_type == "pattern_decomposition")
    & (summary_tables.phase_mode == "strict_herzog")
    & (summary_tables.window_type == "full")
    & (summary_tables.definition.isin(["A_windowed", "B_minimum_data", "D_nb_regression"]))
].copy()
pattern_decomposition
"""


def table_7_code() -> str:
    return """nb_dispersion_sensitivity = summary_tables[
    (summary_tables.table_type == "window_false_positive")
    & (summary_tables.phase_mode == "strict_herzog")
    & (summary_tables.subset == "all")
    & (summary_tables.window_type == "full")
    & (summary_tables.definition.isin([
        "D_nb_regression_C1_or_C2", "D_nb_regression_window_alpha_C1_or_C2"
    ]))
].copy()
nb_dispersion_sensitivity
"""


def table_8_code() -> str:
    return """strata_rows = summary_tables[
    (summary_tables.table_type == "window_false_positive")
    & (summary_tables.phase_mode == "strict_herzog")
    & (summary_tables.definition.isin(["A_windowed_any", "A_windowed_C1_or_C2", "B_minimum_data_C1_or_C2", "D_nb_regression_C1_or_C2"]))
    & (
        summary_tables.subset.astype(str).str.startswith("seizure_frequency:")
        | summary_tables.subset.astype(str).str.startswith("cycle_regularity:")
        | summary_tables.subset.astype(str).str.startswith("window_seizure_days_")
    )
].copy()
strata_rows
"""


def table_9_code() -> str:
    return """historical_rows = summary_tables[
    (summary_tables.table_type == "window_false_positive")
    & (summary_tables.phase_mode == "strict_herzog")
    & (summary_tables.subset == "all")
    & (summary_tables.window_type.isin(["calendar", "full"]))
    & (summary_tables.definition.isin([
        "H1_newmark_penry_any", "H1_newmark_penry_66_7_any",
        "H2_duncan1993_any", "H3_herzog1997_twofold_any",
        "H4_reddy2007_any_phase2x_any"
    ]))
].copy()
historical_rows
"""


def table_10_code() -> str:
    return """manifest_files = pd.DataFrame(manifest["files"])
manifest_files.assign(size_mb=manifest_files["bytes"] / 1_000_000)[["path", "size_mb", "sha256"]]
"""


def figures_code() -> str:
    return """from paper1_null_ce.core.plots import write_all_figures
from tempfile import TemporaryDirectory

# Exercise the exact publication-figure renderer without mutating the immutable
# completed-run bundle or invalidating its recorded checksums.
with TemporaryDirectory(prefix="paper1-notebook-figures-") as figure_dir:
    regenerated = write_all_figures(
        figure_dir,
        summary_tables,
        study_level,
        pd.read_parquet(OUTPUT_DIR / "audit_daily_sample.parquet"),
    )
    regenerated_figure_names = [path.name for path in regenerated]
regenerated_figure_names
"""


def table_intro(title: str, reason: str) -> str:
    return f"## {title}\n\n**Why this table is included.** {reason}\n\n**Code to call.**"


def table_caption(label: str, caption: str) -> str:
    return f"**{label} caption.** {caption}"


def table_1(participants: pd.DataFrame) -> pd.DataFrame:
    out = (
        participants.groupby("cohort")
        .agg(
            participants=("participant_id", "nunique"),
            age_mean=("age", "mean"),
            age_sd=("age", "std"),
            mean_cycle_length=("mean_cycle_length", "mean"),
            sd_cycle_length=("sd_cycle_length", "mean"),
            ovulatory_fraction=("ovulatory_fraction", "mean"),
            seizure_days_per_month=("seizure_days_per_month", "mean"),
            seizures_per_month=("seizures_per_month", "mean"),
        )
        .reset_index()
    )
    return format_table(
        out,
        {
            "participants": "int",
            "age_mean": 1,
            "age_sd": 1,
            "mean_cycle_length": 2,
            "sd_cycle_length": 2,
            "ovulatory_fraction": "pct",
            "seizure_days_per_month": 2,
            "seizures_per_month": 2,
        },
    )


def table_2(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "window_false_positive")
        & (summary.phase_mode == "strict_herzog")
        & (summary.subset == "all")
        & (summary.window_type == "full")
        & (summary.definition.isin([
            "A_windowed_any", "A_windowed_C1_or_C2",
            "B_minimum_data_any", "B_minimum_data_C1_or_C2",
            "C_reproducibility_any", "D_nb_regression_C1_or_C2",
        ]))
    ].copy()
    data["FPR (95% CI)"] = data.apply(rate_ci, axis=1)
    out = data[
        [
            "cohort",
            "definition",
            "n_windows",
            "n_classifiable",
            "positives",
            "FPR (95% CI)",
            "indeterminate_rate",
        ]
    ].sort_values(["cohort", "definition"])
    return format_table(out, {"n_windows": "int", "n_classifiable": "int", "positives": "int", "indeterminate_rate": "pct"})


def table_3(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "window_false_positive")
        & (summary.phase_mode == "strict_herzog")
        & (summary.subset == "all")
        & (summary.definition.isin([
            "A_exact_any", "A_windowed_any", "A_windowed_C1_or_C2",
            "B_minimum_data_C1_or_C2", "C_reproducibility_C1_or_C2",
            "D_nb_regression_C1_or_C2",
        ]))
    ].copy()
    data["window"] = data.apply(window_label, axis=1)
    data["FPR"] = data["false_positive_rate"]
    out = data[
        [
            "cohort",
            "window",
            "definition",
            "n_classifiable",
            "positives",
            "FPR",
            "indeterminate_rate",
        ]
    ].sort_values(["cohort", "window", "definition"])
    return format_table(
        out,
        {"n_classifiable": "int", "positives": "int", "FPR": "pct", "indeterminate_rate": "pct"},
    )


def table_phase_mode(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "window_false_positive")
        & (summary.subset == "all")
        & (
            (summary.window_type == "full")
            | ((summary.window_type == "calendar") & (summary.window_value.astype(str) == "3"))
        )
        & (summary.definition.isin(["A_windowed_any", "A_windowed_C1_or_C2", "A_windowed_C3_only"]))
    ].copy()
    data["window"] = data.apply(window_label, axis=1)
    data["FPR (95% CI)"] = data.apply(rate_ci, axis=1)
    out = data[
        [
            "cohort",
            "phase_mode",
            "window",
            "definition",
            "n_classifiable",
            "positives",
            "FPR (95% CI)",
            "indeterminate_rate",
        ]
    ].sort_values(["cohort", "window", "definition", "phase_mode"])
    return format_table(out, {"n_classifiable": "int", "positives": "int", "indeterminate_rate": "pct"})


def table_4(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "study_level_3month")
        & (summary.phase_mode == "strict_herzog")
        & (summary.definition.isin([
            "A_windowed_any", "B_minimum_data_C1_or_C2",
            "C_reproducibility_C1_or_C2", "D_nb_regression_C1_or_C2",
        ]))
    ].copy()
    out = data[
        [
            "cohort",
            "definition",
            "n_participants",
            "subset",
            "n_windows",
            "false_positive_rate",
            "wilson95_low",
            "wilson95_high",
            "p_prevalence_ge_39_1",
            "p_prevalence_ge_44_2",
        ]
    ].sort_values(["cohort", "definition", "n_participants", "subset"])
    out = out.rename(
        columns={
            "n_windows": "Monte Carlo studies",
            "false_positive_rate": "Mean apparent CE prevalence",
            "wilson95_low": "2.5th percentile",
            "wilson95_high": "97.5th percentile",
            "p_prevalence_ge_39_1": "Probability prevalence at least 39.1%",
            "p_prevalence_ge_44_2": "Probability prevalence at least 44.2%",
        }
    )
    return format_table(
        out,
        {
            "Monte Carlo studies": "int",
            "Mean apparent CE prevalence": "pct",
            "2.5th percentile": "pct",
            "97.5th percentile": "pct",
            "Probability prevalence at least 39.1%": "pct",
            "Probability prevalence at least 44.2%": "pct",
        },
    )


def table_5(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "window_false_positive")
        & (summary.phase_mode == "strict_herzog")
        & (summary.window_type == "full")
        & (summary.subset.isin([
            "ge_1_seizure_day_per_month",
            "ge_2_seizures_per_month",
            "strict_23_35_day_cycles_only",
            "common_classifiable_subset",
        ]))
        & (summary.definition.isin([
            "A_windowed_any", "A_windowed_C1_or_C2",
            "B_minimum_data_C1_or_C2",
            "C_reproducibility_C1_or_C2", "D_nb_regression_C1_or_C2",
        ]))
    ].copy()
    data["FPR (95% CI)"] = data.apply(rate_ci, axis=1)
    out = data[
        [
            "cohort",
            "subset",
            "definition",
            "n_classifiable",
            "positives",
            "FPR (95% CI)",
            "indeterminate_rate",
        ]
    ].sort_values(["cohort", "subset", "definition"])
    return format_table(out, {"n_classifiable": "int", "positives": "int", "indeterminate_rate": "pct"})


def table_6(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "pattern_decomposition")
        & (summary.phase_mode == "strict_herzog")
        & (summary.window_type == "full")
        & (summary.definition.isin(["A_windowed", "B_minimum_data", "D_nb_regression"]))
    ].copy()
    out = data[
        [
            "cohort",
            "definition",
            "pattern_category",
            "n_classifiable",
            "positives",
            "false_positive_rate",
            "positive_rate_all_attempted",
            "indeterminate_rate",
        ]
    ].sort_values(["cohort", "definition", "pattern_category"])
    return format_table(out, {"n_classifiable": "int", "positives": "int", "false_positive_rate": "pct", "positive_rate_all_attempted": "pct", "indeterminate_rate": "pct"})


def table_7(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "window_false_positive")
        & (summary.phase_mode == "strict_herzog")
        & (summary.subset == "all")
        & (summary.window_type == "full")
        & (summary.definition.isin(["D_nb_regression_C1_or_C2", "D_nb_regression_window_alpha_C1_or_C2"]))
    ].copy()
    data["window"] = data.apply(window_label, axis=1)
    data["FPR (95% CI)"] = data.apply(rate_ci, axis=1)
    out = data[
        [
            "cohort",
            "window",
            "definition",
            "n_classifiable",
            "positives",
            "FPR (95% CI)",
            "indeterminate_rate",
        ]
    ].sort_values(["cohort", "window", "definition"])
    return format_table(out, {"n_classifiable": "int", "positives": "int", "indeterminate_rate": "pct"})


def table_8(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "window_false_positive")
        & (summary.phase_mode == "strict_herzog")
        & (summary.definition.isin(["A_windowed_any", "A_windowed_C1_or_C2", "B_minimum_data_C1_or_C2", "D_nb_regression_C1_or_C2"]))
        & (
            summary.subset.astype(str).str.startswith("seizure_frequency:")
            | summary.subset.astype(str).str.startswith("cycle_regularity:")
            | summary.subset.astype(str).str.startswith("window_seizure_days_")
        )
    ].copy()
    data["stratum_type"] = np.select(
        [
            data["subset"].str.startswith("seizure_frequency:"),
            data["subset"].str.startswith("cycle_regularity:"),
            data["subset"].str.startswith("window_seizure_days_"),
        ],
        ["seizure frequency", "cycle regularity", "window seizure days"],
        default="other",
    )
    data["stratum"] = np.where(
        data["subset"].str.contains(":"),
        data["subset"].str.split(":", n=1).str[1],
        data["subset"].str.replace("window_seizure_days_", "", regex=False).str.replace("_", " ", regex=False),
    )
    data["FPR"] = data["false_positive_rate"]
    out = data[
        [
            "cohort",
            "stratum_type",
            "stratum",
            "definition",
            "n_classifiable",
            "positives",
            "FPR",
            "indeterminate_rate",
        ]
    ].sort_values(["cohort", "stratum_type", "stratum", "definition"])
    return format_table(
        out,
        {"n_classifiable": "int", "positives": "int", "FPR": "pct", "indeterminate_rate": "pct"},
    )


def table_9(summary: pd.DataFrame) -> pd.DataFrame:
    data = summary[
        (summary.table_type == "window_false_positive")
        & (summary.phase_mode == "strict_herzog")
        & (summary.subset == "all")
        & (summary.window_type.isin(["calendar", "full"]))
        & (summary.definition.isin(HISTORICAL_DEFINITIONS))
    ].copy()
    data = data[(data.window_type == "full") | (data.window_value.astype(str) == "3")]
    data["window"] = data.apply(window_label, axis=1)
    data["FPR (95% CI)"] = data.apply(rate_ci, axis=1)
    out = data[
        [
            "cohort",
            "window",
            "definition",
            "n_classifiable",
            "positives",
            "FPR (95% CI)",
            "indeterminate_rate",
            "assumption_based_historical",
        ]
    ].sort_values(["cohort", "window", "definition"])
    return format_table(
        out,
        {
            "n_classifiable": "int",
            "positives": "int",
            "indeterminate_rate": "pct",
            "assumption_based_historical": "bool",
        },
    )


def table_10(manifest: dict[str, Any]) -> pd.DataFrame:
    files = pd.DataFrame(manifest["files"]).copy()
    files["size_mb"] = files["bytes"] / 1_000_000
    files["sha256"] = files["sha256"].str.slice(0, 16) + "..."
    return format_table(files[["path", "size_mb", "sha256"]], {"size_mb": 3})


def rate_ci(row: pd.Series) -> str:
    if pd.isna(row["false_positive_rate"]):
        return "NA"
    return f"{100 * row['false_positive_rate']:.1f}% ({100 * row['wilson95_low']:.1f}, {100 * row['wilson95_high']:.1f})"


def window_label(row: pd.Series) -> str:
    if row["window_type"] == "calendar":
        value = int(float(row["window_value"]))
        return f"{value} month" if value == 1 else f"{value} months"
    if row["window_type"] == "cycle":
        value = int(float(row["window_value"]))
        return f"{value} cycle" if value == 1 else f"{value} cycles"
    if row["window_type"] == "full":
        return "36-month full diary"
    return f"{row['window_type']} {row['window_value']}"


def format_table(df: pd.DataFrame, formats: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    for col, fmt in formats.items():
        if col not in out:
            continue
        if fmt == "pct":
            out[col] = out[col].map(lambda x: "NA" if pd.isna(x) else f"{100 * float(x):.1f}%")
        elif fmt == "int":
            out[col] = out[col].map(lambda x: "NA" if pd.isna(x) else f"{int(float(x)):,}")
        elif fmt == "bool":
            out[col] = out[col].map(lambda x: "Yes" if bool(x) else "No")
        else:
            out[col] = out[col].map(lambda x: "NA" if pd.isna(x) else f"{float(x):.{int(fmt)}f}")
    return with_display_labels(out)


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows populated for this table._"
    safe = df.copy()
    safe.columns = [str(c) for c in safe.columns]
    rows = [safe.columns.tolist()] + safe.astype(str).replace({"nan": "NA"}).map(display_text).values.tolist()
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
    header = "| " + " | ".join(str(rows[0][i]).ljust(widths[i]) for i in range(len(widths))) + " |"
    sep = "| " + " | ".join("-" * widths[i] for i in range(len(widths))) + " |"
    body = [
        "| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(len(widths))) + " |"
        for row in rows[1:]
    ]
    return "\n".join([header, sep, *body])


def markdown_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "id": hashlib.sha256(f"markdown\0{source}".encode("utf-8")).hexdigest()[:12],
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def code_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "id": hashlib.sha256(f"code\0{source}".encode("utf-8")).hexdigest()[:12],
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def rel_path(path: Path, base: Path) -> str:
    import os

    return os.path.relpath(path.resolve(), start=base.resolve())


def limitations_markdown(manifest: dict[str, Any]) -> str:
    output_dir = manifest.get("output_dir", "the recorded output directory")
    return (
        "## Interpretation notes\n\n"
        f"- The notebook is populated from the current files in `{output_dir}`. If those files were produced by smoke mode, the numerical values are smoke-test values, not the final 100,000-participant estimates.\n"
        "- Full-study values are produced by running `run_paper1_null_ce.py --config config_random_start_full.yaml --full`, then rebuilding this notebook.\n"
        "- Exact Herzog 2004 results are intentionally present only for 3-complete-cycle windows.\n"
        "- Historical definitions are assumption-based operationalizations and should be kept separate from core endpoints.\n"
        "- The manifest assumptions are part of the analysis record:\n\n"
        + "\n".join(f"  - {display_text(item)}" for item in manifest.get("assumptions", []))
    )


if __name__ == "__main__":
    raise SystemExit(main())
