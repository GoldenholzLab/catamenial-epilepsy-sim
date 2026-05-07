"""Exact Herzog 2004-style three-cycle classifier."""

from __future__ import annotations

from typing import Any

import pandas as pd

from paper1_null_ce.core.classifiers_windowed import DEFAULT_THRESHOLDS, pooled_adsf_and_ratios
from paper1_null_ce.core.phase_labeling import complete_cycle_ids
from paper1_null_ce.core.utils import ratio_positive


def _cycle_exact_labels(cycle_df: pd.DataFrame, cohort: str, thresholds: dict[str, float]) -> dict[str, bool | None]:
    ratios = pooled_adsf_and_ratios(cycle_df, cohort, thresholds)["ratios"]
    ovulatory = bool(cycle_df["ovulatory_flag"].iloc[0]) if "ovulatory_flag" in cycle_df else True
    ilp = bool(cycle_df["ilp_flag"].iloc[0]) if "ilp_flag" in cycle_df else False
    c1: bool | None = False
    c2: bool | None = False
    c3: bool | None = False
    if ovulatory:
        c1, _ = ratio_positive(ratios["C1"], thresholds["C1"])
        c2, _ = ratio_positive(ratios["C2"], thresholds["C2"])
    if cohort == "population" and ilp and ratios["C3"] is not None:
        c3, _ = ratio_positive(ratios["C3"], thresholds["C3"])
    any_label = True if any(x is True for x in (c1, c2, c3)) else (False if all(x is not None for x in (c1, c2, c3)) else None)
    return {"any": any_label, "C1": c1, "C2": c2, "C3": c3}


def _subject_label(cycle_labels: list[bool | None]) -> bool | None:
    if sum(label is True for label in cycle_labels) >= 2:
        return True
    if any(label is None for label in cycle_labels):
        return None
    return False


def classify_exact_herzog2004(
    window_df: pd.DataFrame,
    cohort: str,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Definition A_exact_herzog2004.

    Exact analyses are limited to windows containing exactly three complete,
    strict 23-35 day cycles.
    """

    thresholds = thresholds or DEFAULT_THRESHOLDS
    if window_df.empty:
        return _empty("empty_window")
    cycle_ids = complete_cycle_ids(window_df, strict_only=True)
    if len(cycle_ids) != 3:
        return _empty("requires_three_complete_strict_23_35_day_cycles")

    cycle_results = [_cycle_exact_labels(window_df[window_df["cycle_id"] == cycle_id], cohort, thresholds) for cycle_id in cycle_ids]
    any_label = _subject_label([result["any"] for result in cycle_results])
    c1 = _subject_label([result["C1"] for result in cycle_results])
    c2 = _subject_label([result["C2"] for result in cycle_results])
    c3 = None if cohort != "population" else _subject_label([result["C3"] for result in cycle_results])
    return {
        "label_A_exact_any": any_label,
        "label_A_exact_C1": c1,
        "label_A_exact_C2": c2,
        "label_A_exact_C3": c3,
        "a_exact_reason": None if any_label is not None else "undefined_cycle_ratio",
    }


def _empty(reason: str) -> dict[str, Any]:
    return {
        "label_A_exact_any": None,
        "label_A_exact_C1": None,
        "label_A_exact_C2": None,
        "label_A_exact_C3": None,
        "a_exact_reason": reason,
    }
