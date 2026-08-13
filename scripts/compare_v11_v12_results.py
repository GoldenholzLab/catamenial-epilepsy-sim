#!/usr/bin/env python3
"""Quantify manuscript-result changes between two HORMONE-CYCLE paper runs."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


KEY_COLUMNS = [
    "table_type",
    "subset",
    "cohort",
    "window_type",
    "window_value",
    "definition",
    "phase_mode",
    "assumption_based_historical",
    "n_participants",
    "pattern_category",
    "indeterminate_reason",
]
NUMERIC_COLUMNS = [
    "n_windows",
    "n_classifiable",
    "positives",
    "false_positive_rate",
    "wilson95_low",
    "wilson95_high",
    "indeterminate_rate",
    "positive_rate_all_attempted",
    "n_indeterminate",
    "p_prevalence_ge_39_1",
    "p_prevalence_ge_44_2",
]


def finite_or_none(value: Any) -> float | int | None:
    """Return JSON-safe numeric values while preserving integer counts."""

    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    return float(value)


def cohort_summary(path: Path) -> list[dict[str, Any]]:
    """Summarize participant-level quantities most likely to move after recalibration."""

    frame = pd.read_parquet(path / "participant_summary.parquet")
    rows: list[dict[str, Any]] = []
    for cohort, group in frame.groupby("cohort", sort=True):
        row: dict[str, Any] = {
            "cohort": cohort,
            "n_participants": int(len(group)),
        }
        for column in [
            "age",
            "mean_cycle_length",
            "sd_cycle_length",
            "ovulatory_fraction",
            "seizure_days_per_month",
            "seizures_per_month",
        ]:
            row[f"mean_{column}"] = finite_or_none(group[column].mean())
        for column in ["pcos", "peri_menarche", "perimenopause"]:
            if column in group:
                row[f"prevalence_{column}"] = finite_or_none(group[column].mean())
        rows.append(row)
    return rows


def selected_result_rows(summary: pd.DataFrame) -> pd.DataFrame:
    """Return the endpoints used in the main manuscript narrative and tables."""

    strict = summary[
        (summary["table_type"] == "window_false_positive")
        & (summary["subset"] == "all")
        & (summary["phase_mode"] == "strict_herzog")
    ].copy()
    selections = pd.concat(
        [
            strict[
                (strict["window_type"] == "full")
                & strict["definition"].isin(
                    [
                        "A_windowed_any",
                        "A_windowed_C1_or_C2",
                        "A_windowed_C3_only",
                        "D_nb_regression_C1_or_C2",
                    ]
                )
            ],
            strict[
                (strict["window_type"] == "calendar")
                & (strict["window_value"].astype(str) == "3")
                & (strict["definition"] == "A_windowed_any")
            ],
            strict[
                (strict["window_type"] == "cycle")
                & (strict["window_value"].astype(str) == "3")
                & (strict["definition"] == "A_exact_any")
            ],
        ],
        ignore_index=True,
    )
    return selections.sort_values(
        ["window_type", "definition", "cohort"], kind="stable"
    )


def normalized_keys(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize mixed/blank summary keys so old/new rows align exactly."""

    result = frame.copy()
    for column in KEY_COLUMNS:
        if column not in result:
            result[column] = ""
        result[column] = result[column].fillna("<NA>").astype(str)
    return result


def aligned_summary_audit(old: pd.DataFrame, new: pd.DataFrame) -> dict[str, Any]:
    """Compare every aligned summary-table row and report numerical movement."""

    old_n = normalized_keys(old)
    new_n = normalized_keys(new)
    if old_n.duplicated(KEY_COLUMNS).any() or new_n.duplicated(KEY_COLUMNS).any():
        raise ValueError("Summary-table comparison keys are not unique")
    merged = old_n.merge(
        new_n,
        on=KEY_COLUMNS,
        how="outer",
        suffixes=("_old", "_new"),
        indicator=True,
        validate="one_to_one",
    )
    common = merged[merged["_merge"] == "both"].copy()
    numeric: dict[str, Any] = {}
    for column in NUMERIC_COLUMNS:
        old_col = f"{column}_old"
        new_col = f"{column}_new"
        if old_col not in common or new_col not in common:
            continue
        left = pd.to_numeric(common[old_col], errors="coerce")
        right = pd.to_numeric(common[new_col], errors="coerce")
        comparable = left.notna() & right.notna()
        delta = right[comparable] - left[comparable]
        numeric[column] = {
            "n_comparable": int(comparable.sum()),
            "n_changed": int((delta.abs() > 1e-12).sum()),
            "max_absolute_delta": finite_or_none(delta.abs().max()),
            "mean_absolute_delta": finite_or_none(delta.abs().mean()),
        }
    return {
        "old_rows": int(len(old)),
        "new_rows": int(len(new)),
        "aligned_rows": int((merged["_merge"] == "both").sum()),
        "old_only_rows": int((merged["_merge"] == "left_only").sum()),
        "new_only_rows": int((merged["_merge"] == "right_only").sum()),
        "numeric_columns": numeric,
    }


def selected_comparison(old: pd.DataFrame, new: pd.DataFrame) -> list[dict[str, Any]]:
    """Build a compact before/after table for manuscript headline endpoints."""

    keys = ["cohort", "window_type", "window_value", "definition", "phase_mode"]
    old_selected = selected_result_rows(old)
    new_selected = selected_result_rows(new)
    merged = old_selected.merge(
        new_selected,
        on=keys,
        how="outer",
        suffixes=("_old", "_new"),
        indicator=True,
        validate="one_to_one",
    )
    rows: list[dict[str, Any]] = []
    for _, source in merged.iterrows():
        row = {key: source[key] for key in keys}
        row["alignment"] = source["_merge"]
        for metric in [
            "n_classifiable",
            "positives",
            "false_positive_rate",
            "indeterminate_rate",
        ]:
            old_value = finite_or_none(source.get(f"{metric}_old"))
            new_value = finite_or_none(source.get(f"{metric}_new"))
            row[f"{metric}_old"] = old_value
            row[f"{metric}_new"] = new_value
            row[f"{metric}_delta"] = (
                None if old_value is None or new_value is None else new_value - old_value
            )
        rows.append(row)
    return rows


def cohort_comparison(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Align participant summaries and calculate new-minus-old deltas."""

    old_map = {row["cohort"]: row for row in old}
    new_map = {row["cohort"]: row for row in new}
    result: list[dict[str, Any]] = []
    for cohort in sorted(set(old_map) | set(new_map)):
        row: dict[str, Any] = {"cohort": cohort}
        for key in sorted(set(old_map.get(cohort, {})) | set(new_map.get(cohort, {}))):
            if key == "cohort":
                continue
            left = old_map.get(cohort, {}).get(key)
            right = new_map.get(cohort, {}).get(key)
            row[f"{key}_old"] = left
            row[f"{key}_new"] = right
            row[f"{key}_delta"] = (
                None
                if left is None or right is None
                else finite_or_none(float(right) - float(left))
            )
        result.append(row)
    return result


def markdown_report(report: dict[str, Any], old_label: str, new_label: str) -> str:
    """Render the comparison as a concise, reviewable Markdown handoff."""

    lines = [
        f"# Paper-result change audit: HORMONE-CYCLE {old_label} to {new_label}",
        "",
        f"This report compares the two specified full-study runs. Deltas are {new_label} minus {old_label}.",
        "",
        "## Headline endpoints",
        "",
        f"| Cohort | Window | Definition | {old_label} rate | {new_label} rate | Change (percentage points) |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in report["headline_endpoints"]:
        old = row["false_positive_rate_old"]
        new = row["false_positive_rate_new"]
        delta = row["false_positive_rate_delta"]
        window = f"{row['window_type']} {row['window_value']}"
        lines.append(
            "| {cohort} | {window} | {definition} | {old} | {new} | {delta} |".format(
                cohort=row["cohort"],
                window=window,
                definition=row["definition"],
                old="—" if old is None else f"{100 * old:.2f}%",
                new="—" if new is None else f"{100 * new:.2f}%",
                delta="—" if delta is None else f"{100 * delta:+.2f}",
            )
        )
    lines.extend(
        [
            "",
            "## Complete summary-table alignment",
            "",
            f"- {old_label} rows: {report['all_summary_rows']['old_rows']:,}",
            f"- {new_label} rows: {report['all_summary_rows']['new_rows']:,}",
            f"- Aligned rows: {report['all_summary_rows']['aligned_rows']:,}",
            f"- {old_label}-only rows: {report['all_summary_rows']['old_only_rows']:,}",
            f"- {new_label}-only rows: {report['all_summary_rows']['new_only_rows']:,}",
            "",
            "The JSON companion contains cohort-level changes and maximum/mean absolute movement for every aligned numeric summary column.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--old",
        type=Path,
        default=Path("outputs/random_start_full_v12_cycle_calibration"),
    )
    parser.add_argument(
        "--new",
        type=Path,
        default=Path("outputs/random_start_full_v13_waveform_recalibration"),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("examples/reports/paper_results_change_v12_to_v13.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("docs/paper_results_change_v12_to_v13.md"),
    )
    parser.add_argument("--old-label", default="v0.2.0")
    parser.add_argument("--new-label", default="v0.3.0")
    args = parser.parse_args()

    old_summary = pd.read_csv(args.old / "summary_tables.csv")
    new_summary = pd.read_csv(args.new / "summary_tables.csv")
    old_cohorts = cohort_summary(args.old)
    new_cohorts = cohort_summary(args.new)
    report = {
        "old_label": args.old_label,
        "new_label": args.new_label,
        "old_output_directory": str(args.old),
        "new_output_directory": str(args.new),
        "cohort_summaries": cohort_comparison(old_cohorts, new_cohorts),
        "headline_endpoints": selected_comparison(old_summary, new_summary),
        "all_summary_rows": aligned_summary_audit(old_summary, new_summary),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(
        markdown_report(report, args.old_label, args.new_label),
        encoding="utf-8",
    )
    print(args.json_output.resolve())
    print(args.markdown_output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
