"""Summary tables for the Paper 1 null CE analysis."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from paper1_null_ce.core.utils import wilson_ci


DEFINITION_COLUMNS: dict[str, str] = {
    "A_exact_any": "label_A_exact_any",
    "A_windowed_any": "label_A_windowed_any",
    "A_windowed_excluding_C3": "label_A_windowed_excluding_C3",
    "A_windowed_C1_or_C2": "label_A_windowed_C1_or_C2",
    "A_windowed_C1_only": "label_A_windowed_C1",
    "A_windowed_C2_only": "label_A_windowed_C2",
    "A_windowed_C3_only": "label_A_windowed_C3",
    "B_minimum_data_any": "label_B_any",
    "B_minimum_data_excluding_C3": "label_B_excluding_C3",
    "B_minimum_data_C1_or_C2": "label_B_C1_or_C2",
    "C_reproducibility_any": "label_C_any",
    "C_reproducibility_C1_or_C2": "label_C_C1_or_C2",
    "C_reproducibility_12cycle_any": "label_C12_any",
    "C_reproducibility_12cycle_C1_or_C2": "label_C12_C1_or_C2",
    "D_nb_regression_any": "label_D_any",
    "D_nb_regression_C1_or_C2": "label_D_C1_or_C2",
    "D_nb_regression_window_alpha_any": "label_D_window_alpha_any",
    "D_nb_regression_window_alpha_C1_or_C2": "label_D_window_alpha_C1_or_C2",
    "H1_newmark_penry_any": "label_H1_any",
    "H1_newmark_penry_66_7_any": "label_H1_sensitivity_any",
    "H2_duncan1993_any": "label_H2_any",
    "H3_herzog1997_twofold_any": "label_H3_any",
    "H4_reddy2007_any_phase2x_any": "label_H4_any",
}

HISTORICAL_DEFINITIONS = {
    "H1_newmark_penry_any",
    "H1_newmark_penry_66_7_any",
    "H2_duncan1993_any",
    "H3_herzog1997_twofold_any",
    "H4_reddy2007_any_phase2x_any",
}

PATTERN_CATEGORY_COLUMNS = {
    "A_windowed": "label_A_windowed_pattern_category",
    "B_minimum_data": "label_B_pattern_category",
    "C_reproducibility": "label_C_pattern_category",
    "D_nb_regression": "label_D_pattern_category",
}

PATTERN_CATEGORIES = [
    "C1 only",
    "C2 only",
    "C1+C2",
    "C3 only",
    "C3 plus C1/C2",
    "none",
]

MIN_INTERPRETABLE_CLASSIFIABLE = 1000


def _bool_series(series: pd.Series) -> pd.Series:
    return series.map(lambda value: True if value is True else (False if value is False else pd.NA)).astype("boolean")


def _subset_mask(df: pd.DataFrame, subset: str) -> pd.Series:
    if subset == "all":
        return pd.Series(True, index=df.index)
    if subset == "ge_1_seizure_day_per_month":
        return df["seizure_days_per_month"] >= 1.0
    if subset == "ge_2_seizures_per_month":
        return df["seizures_per_month"] >= 2.0
    if subset == "strict_23_35_day_cycles_only":
        return df["strict_herzog_eligible_flag"].astype(bool)
    if subset == "common_classifiable_subset":
        cols = [c for c in ["label_A_windowed_any", "label_B_any", "label_C_any", "label_D_any"] if c in df]
        if not cols:
            return pd.Series(False, index=df.index)
        mask = pd.Series(True, index=df.index)
        for col in cols:
            mask &= _bool_series(df[col]).notna()
        return mask
    if subset == "window_seizure_days_0_to_3":
        return df["seizure_days_total"] <= 3
    if subset == "window_seizure_days_4_to_7":
        return (df["seizure_days_total"] >= 4) & (df["seizure_days_total"] <= 7)
    if subset == "window_seizure_days_8_to_15":
        return (df["seizure_days_total"] >= 8) & (df["seizure_days_total"] <= 15)
    if subset == "window_seizure_days_ge_16":
        return df["seizure_days_total"] >= 16
    raise ValueError(f"Unknown subset: {subset}")


def summarize_window_results(window_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    group_cols = ["cohort", "phase_mode", "window_type", "window_value"] if "phase_mode" in window_results else ["cohort", "window_type", "window_value"]
    subset_items: list[tuple[str, pd.Series]] = [
        (subset, _subset_mask(window_results, subset))
        for subset in [
            "all",
            "ge_1_seizure_day_per_month",
            "ge_2_seizures_per_month",
            "strict_23_35_day_cycles_only",
            "common_classifiable_subset",
            "window_seizure_days_0_to_3",
            "window_seizure_days_4_to_7",
            "window_seizure_days_8_to_15",
            "window_seizure_days_ge_16",
        ]
    ]
    for col, prefix in [
        ("seizure_frequency_stratum", "seizure_frequency"),
        ("cycle_regularity_stratum", "cycle_regularity"),
    ]:
        if col in window_results:
            for value in sorted(str(v) for v in window_results[col].dropna().unique()):
                subset_items.append((f"{prefix}:{value}", window_results[col].astype(str) == value))

    for subset, mask in subset_items:
        subset_df = window_results[mask].copy()
        if subset_df.empty:
            continue
        for definition, col in DEFINITION_COLUMNS.items():
            if col not in subset_df:
                continue
            tmp = subset_df.copy()
            tmp["_label"] = _bool_series(tmp[col])
            for keys, g in tmp.groupby(group_cols, dropna=False, sort=True):
                key_map = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
                n_windows = int(len(g))
                n_classifiable = int(g["_label"].notna().sum())
                positives = int((g["_label"] == True).sum())  # noqa: E712
                fpr = positives / n_classifiable if n_classifiable else np.nan
                lo, hi = wilson_ci(positives, n_classifiable) if n_classifiable else (np.nan, np.nan)
                rows.append(
                    {
                        "table_type": "window_false_positive",
                        "subset": subset,
                        "cohort": key_map["cohort"],
                        "window_type": key_map["window_type"],
                        "window_value": key_map["window_value"],
                        "definition": definition,
                        "phase_mode": key_map.get("phase_mode", "strict_herzog"),
                        "assumption_based_historical": definition in HISTORICAL_DEFINITIONS,
                        "n_windows": n_windows,
                        "n_classifiable": n_classifiable,
                        "positives": positives,
                        "false_positive_rate": fpr,
                        "wilson95_low": lo,
                        "wilson95_high": hi,
                        "indeterminate_rate": 1.0 - (n_classifiable / n_windows) if n_windows else np.nan,
                        "positive_rate_all_attempted": positives / n_windows if n_windows else np.nan,
                        "unstable_denominator": bool(0 < n_classifiable < MIN_INTERPRETABLE_CLASSIFIABLE),
                        "interpretation_note": "unstable; not interpreted" if 0 < n_classifiable < MIN_INTERPRETABLE_CLASSIFIABLE else "",
                    }
                )
    return pd.DataFrame(rows)


def summarize_study_level(study_level: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if study_level.empty:
        return pd.DataFrame(rows)
    group_cols = ["cohort", "phase_mode", "definition", "n_participants"] if "phase_mode" in study_level else ["cohort", "definition", "n_participants"]
    for keys, g in study_level.groupby(group_cols, sort=True):
        key_map = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
        for prevalence_col in ["apparent_prevalence_all", "apparent_prevalence_classifiable"]:
            values = g[prevalence_col].dropna()
            rows.append(
                {
                    "table_type": "study_level_3month",
                    "subset": prevalence_col,
                    "cohort": key_map["cohort"],
                    "window_type": "study_mc_calendar",
                    "window_value": 3,
                    "definition": key_map["definition"],
                    "phase_mode": key_map.get("phase_mode", "strict_herzog"),
                    "n_participants": int(key_map["n_participants"]),
                    "assumption_based_historical": key_map["definition"] in HISTORICAL_DEFINITIONS,
                    "n_windows": int(len(values)),
                    "n_classifiable": int(len(values)),
                    "positives": np.nan,
                    "false_positive_rate": float(values.mean()) if len(values) else np.nan,
                    "wilson95_low": float(values.quantile(0.025)) if len(values) else np.nan,
                    "wilson95_high": float(values.quantile(0.975)) if len(values) else np.nan,
                    "indeterminate_rate": np.nan,
                    "positive_rate_all_attempted": float(values.mean()) if len(values) else np.nan,
                    "unstable_denominator": False,
                    "interpretation_note": "",
                    "p_prevalence_ge_39_1": float((values >= 0.391).mean()) if len(values) else np.nan,
                    "p_prevalence_ge_44_2": float((values >= 0.442).mean()) if len(values) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def summarize_participant_results(window_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if window_results.empty:
        return pd.DataFrame(rows)
    group_cols = ["cohort", "phase_mode", "window_type", "window_value"] if "phase_mode" in window_results else ["cohort", "window_type", "window_value"]
    for definition, col in DEFINITION_COLUMNS.items():
        if col not in window_results:
            continue
        tmp = window_results.copy()
        tmp["_label"] = _bool_series(tmp[col])
        for keys, g in tmp.groupby(group_cols, dropna=False, sort=True):
            key_map = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
            participant = g.groupby("participant_id", sort=False)["_label"].agg(
                attempted_windows="size",
                classifiable_windows=lambda s: int(s.notna().sum()),
                positive_windows=lambda s: int((s == True).sum()),  # noqa: E712
            )
            n_participants = int(len(participant))
            n_classifiable = int((participant["classifiable_windows"] > 0).sum())
            positives = int((participant["positive_windows"] > 0).sum())
            lo, hi = wilson_ci(positives, n_classifiable) if n_classifiable else (np.nan, np.nan)
            rows.append(
                {
                    "table_type": "participant_false_positive",
                    "subset": "any_window_per_participant",
                    "cohort": key_map["cohort"],
                    "window_type": key_map["window_type"],
                    "window_value": key_map["window_value"],
                    "definition": definition,
                    "phase_mode": key_map.get("phase_mode", "strict_herzog"),
                    "assumption_based_historical": definition in HISTORICAL_DEFINITIONS,
                    "n_windows": int(g.shape[0]),
                    "n_participants": n_participants,
                    "n_classifiable": n_classifiable,
                    "positives": positives,
                    "false_positive_rate": positives / n_classifiable if n_classifiable else np.nan,
                    "positive_rate_all_attempted": positives / n_participants if n_participants else np.nan,
                    "wilson95_low": lo,
                    "wilson95_high": hi,
                    "indeterminate_rate": 1.0 - (n_classifiable / n_participants) if n_participants else np.nan,
                    "unstable_denominator": bool(0 < n_classifiable < MIN_INTERPRETABLE_CLASSIFIABLE),
                    "interpretation_note": "unstable; not interpreted" if 0 < n_classifiable < MIN_INTERPRETABLE_CLASSIFIABLE else "",
                }
            )
    return pd.DataFrame(rows)


def summarize_pattern_decomposition(window_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if window_results.empty:
        return pd.DataFrame(rows)
    group_cols = ["cohort", "phase_mode", "window_type", "window_value"] if "phase_mode" in window_results else ["cohort", "window_type", "window_value"]
    for definition, col in PATTERN_CATEGORY_COLUMNS.items():
        if col not in window_results:
            continue
        tmp = window_results.copy()
        for keys, g in tmp.groupby(group_cols, dropna=False, sort=True):
            key_map = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
            n_windows = int(g.shape[0])
            n_classifiable = int(g[col].notna().sum())
            for category in PATTERN_CATEGORIES:
                count = int((g[col] == category).sum())
                rows.append(
                    {
                        "table_type": "pattern_decomposition",
                        "subset": "mutually_exclusive_patterns",
                        "cohort": key_map["cohort"],
                        "window_type": key_map["window_type"],
                        "window_value": key_map["window_value"],
                        "definition": definition,
                        "phase_mode": key_map.get("phase_mode", "strict_herzog"),
                        "pattern_category": category,
                        "n_windows": n_windows,
                        "n_classifiable": n_classifiable,
                        "positives": count,
                        "false_positive_rate": count / n_classifiable if n_classifiable else np.nan,
                        "positive_rate_all_attempted": count / n_windows if n_windows else np.nan,
                        "indeterminate_rate": 1.0 - (n_classifiable / n_windows) if n_windows else np.nan,
                        "unstable_denominator": bool(0 < n_classifiable < MIN_INTERPRETABLE_CLASSIFIABLE),
                        "interpretation_note": "unstable; not interpreted" if 0 < n_classifiable < MIN_INTERPRETABLE_CLASSIFIABLE else "",
                    }
                )
    return pd.DataFrame(rows)


def summarize_indeterminate_reasons(window_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if window_results.empty:
        return pd.DataFrame(rows)
    group_cols = ["cohort", "phase_mode", "window_type", "window_value"] if "phase_mode" in window_results else ["cohort", "window_type", "window_value"]
    reason_cols = {
        "A_exact_any": "a_exact_reason",
        "A_windowed_any": "a_windowed_reason",
        "B_minimum_data_any": "b_reason",
        "C_reproducibility_any": "c_reason",
        "D_nb_regression_any": "d_reason",
    }
    for definition, reason_col in reason_cols.items():
        label_col = DEFINITION_COLUMNS.get(definition)
        if reason_col not in window_results or label_col not in window_results:
            continue
        tmp = window_results.copy()
        tmp["_label"] = _bool_series(tmp[label_col])
        for keys, g in tmp.groupby(group_cols, dropna=False, sort=True):
            key_map = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
            indeterminate = g[g["_label"].isna()]
            n_indeterminate = int(indeterminate.shape[0])
            if n_indeterminate == 0:
                continue
            counts = indeterminate[reason_col].fillna("unknown").value_counts(dropna=False)
            for reason, count in counts.items():
                rows.append(
                    {
                        "table_type": "indeterminate_reasons",
                        "subset": "all",
                        "cohort": key_map["cohort"],
                        "window_type": key_map["window_type"],
                        "window_value": key_map["window_value"],
                        "definition": definition,
                        "phase_mode": key_map.get("phase_mode", "strict_herzog"),
                        "indeterminate_reason": str(reason),
                        "n_windows": int(g.shape[0]),
                        "n_indeterminate": n_indeterminate,
                        "positives": int(count),
                        "false_positive_rate": np.nan,
                        "positive_rate_all_attempted": int(count) / int(g.shape[0]) if int(g.shape[0]) else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def headline_rates(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary
    mask = (
        (summary["table_type"] == "window_false_positive")
        & (summary["subset"] == "all")
        & (summary.get("phase_mode", "strict_herzog") == "strict_herzog")
        & (summary["window_type"] == "full")
        & (summary["definition"].isin(["A_windowed_any", "A_windowed_C1_or_C2", "B_minimum_data_any", "B_minimum_data_C1_or_C2", "C_reproducibility_any", "D_nb_regression_C1_or_C2"]))
    )
    return summary.loc[
        mask,
        ["cohort", "definition", "n_classifiable", "false_positive_rate", "wilson95_low", "wilson95_high"],
    ].sort_values(["cohort", "definition"])
