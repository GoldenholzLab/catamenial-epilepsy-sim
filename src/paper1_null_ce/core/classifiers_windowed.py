"""Window-level Herzog-threshold classifiers and ADSF summaries."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from paper1_null_ce.core.phase_labeling import count_complete_cycles, phase_counts
from paper1_null_ce.core.utils import adsf_ratio, first_reason, month_denominator, ratio_positive


DEFAULT_THRESHOLDS = {"C1": 1.69, "C2": 1.83, "C3": 1.62}


def pooled_adsf_and_ratios(
    window_df: pd.DataFrame,
    cohort: str,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    counts = phase_counts(window_df)
    m = counts["M"]
    o = counts["O"]
    f = counts["F"]
    l = counts["L"]
    fl_days = f["days"] + l["days"]
    fl_seizures = f["seizures"] + l["seizures"]
    olm_days = o["days"] + l["days"] + m["days"]
    olm_seizures = o["seizures"] + l["seizures"] + m["seizures"]

    short_cycle_modified = bool(
        "short_cycle_modified_flag" in window_df
        and window_df["short_cycle_modified_flag"].any()
        and (window_df["cycle_length"] < 23).any()
    )
    if short_cycle_modified:
        rr_c1 = adsf_ratio(m["seizures"], m["days"], l["seizures"], l["days"])
    else:
        rr_c1 = adsf_ratio(m["seizures"], m["days"], fl_seizures, fl_days)
    rr_c2 = adsf_ratio(o["seizures"], o["days"], fl_seizures, fl_days)

    c3_applicable = bool(cohort == "population" and "ilp_flag" in window_df and window_df["ilp_flag"].any())
    if c3_applicable:
        c3_df = window_df[window_df["ilp_flag"].astype(bool)]
        c3_counts = phase_counts(c3_df)
        cm = c3_counts["M"]
        co = c3_counts["O"]
        cf = c3_counts["F"]
        cl = c3_counts["L"]
        c3_olm_days = cm["days"] + co["days"] + cl["days"]
        c3_olm_seizures = cm["seizures"] + co["seizures"] + cl["seizures"]
        rr_c3 = adsf_ratio(c3_olm_seizures, c3_olm_days, cf["seizures"], cf["days"])
    else:
        rr_c3 = None

    adsf = {
        "adsf_M": m["seizures"] / m["days"] if m["days"] > 0 else np.nan,
        "adsf_O": o["seizures"] / o["days"] if o["days"] > 0 else np.nan,
        "adsf_F": f["seizures"] / f["days"] if f["days"] > 0 else np.nan,
        "adsf_L": l["seizures"] / l["days"] if l["days"] > 0 else np.nan,
        "adsf_FL": fl_seizures / fl_days if fl_days > 0 else np.nan,
        "adsf_OLM": olm_seizures / olm_days if olm_days > 0 else np.nan,
        "rr_C1": rr_c1.ratio,
        "rr_C2": rr_c2.ratio,
        "rr_C3": rr_c3.ratio if rr_c3 is not None else np.nan,
        "c3_applicable_flag": c3_applicable,
    }
    return {"adsf": adsf, "ratios": {"C1": rr_c1, "C2": rr_c2, "C3": rr_c3}}


def classify_a_windowed(
    window_df: pd.DataFrame,
    cohort: str,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Protocol extension using pooled Herzog ratios across an arbitrary window."""

    thresholds = thresholds or DEFAULT_THRESHOLDS
    if window_df.empty:
        return {
            "label_A_windowed_any": None,
            "label_A_windowed_C1": None,
            "label_A_windowed_C2": None,
            "label_A_windowed_C3": None,
            "a_windowed_reason": "empty_window",
        }
    payload = pooled_adsf_and_ratios(window_df, cohort, thresholds)
    ratios = payload["ratios"]
    c1, r1 = ratio_positive(ratios["C1"], thresholds["C1"])
    c2, r2 = ratio_positive(ratios["C2"], thresholds["C2"])
    c3 = None
    r3 = None
    if ratios["C3"] is not None:
        c3, r3 = ratio_positive(ratios["C3"], thresholds["C3"])
    labels = [c1, c2] + ([c3] if ratios["C3"] is not None else [])
    any_label = True if any(label is True for label in labels) else (False if any(label is False for label in labels) else None)
    return {
        "label_A_windowed_any": any_label,
        "label_A_windowed_C1": c1,
        "label_A_windowed_C2": c2,
        "label_A_windowed_C3": c3,
        "a_windowed_reason": first_reason([r1, r2, r3]),
        **payload["adsf"],
    }


def passes_definition_b_threshold(
    window_df: pd.DataFrame,
    window_type: str,
    window_value: Any,
    days_per_month: float,
    min_months: float = 4.0,
    min_cycle_window_cycles: int = 6,
    min_seizure_days: int = 4,
) -> tuple[bool, str | None]:
    n_days = int(len(window_df))
    seizure_days = int(window_df["seizure_day"].sum()) if not window_df.empty else 0
    if seizure_days < min_seizure_days:
        return False, "seizure_days_below_minimum"
    duration_ok = month_denominator(n_days, days_per_month) >= min_months
    cycle_ok = window_type == "cycle" and int(window_value) >= min_cycle_window_cycles
    if not (duration_ok or cycle_ok):
        return False, "window_duration_below_minimum"
    return True, None


def classify_b_minimum_data(
    window_df: pd.DataFrame,
    cohort: str,
    window_type: str,
    window_value: Any,
    days_per_month: float,
    thresholds: dict[str, float] | None = None,
    min_months: float = 4.0,
    min_cycle_window_cycles: int = 6,
    min_seizure_days: int = 4,
) -> dict[str, Any]:
    ok, reason = passes_definition_b_threshold(
        window_df,
        window_type,
        window_value,
        days_per_month,
        min_months=min_months,
        min_cycle_window_cycles=min_cycle_window_cycles,
        min_seizure_days=min_seizure_days,
    )
    if not ok:
        return {
            "label_B_any": None,
            "label_B_C1": None,
            "label_B_C2": None,
            "label_B_C3": None,
            "b_reason": reason,
        }
    a = classify_a_windowed(window_df, cohort, thresholds)
    return {
        "label_B_any": a["label_A_windowed_any"],
        "label_B_C1": a["label_A_windowed_C1"],
        "label_B_C2": a["label_A_windowed_C2"],
        "label_B_C3": a["label_A_windowed_C3"],
        "b_reason": a.get("a_windowed_reason"),
    }


def _cycle_level_labels(cycle_df: pd.DataFrame, cohort: str, thresholds: dict[str, float]) -> dict[str, bool | None]:
    payload = pooled_adsf_and_ratios(cycle_df, cohort, thresholds)
    ratios = payload["ratios"]
    ovulatory = bool(cycle_df["ovulatory_flag"].iloc[0]) if "ovulatory_flag" in cycle_df else True
    ilp = bool(cycle_df["ilp_flag"].iloc[0]) if "ilp_flag" in cycle_df else False

    c1 = c2 = c3 = False
    if ovulatory:
        c1, _ = ratio_positive(ratios["C1"], thresholds["C1"])
        c2, _ = ratio_positive(ratios["C2"], thresholds["C2"])
    if cohort == "population" and ilp and ratios["C3"] is not None:
        c3, _ = ratio_positive(ratios["C3"], thresholds["C3"])
    return {"C1": c1, "C2": c2, "C3": c3}


def classify_reproducibility(
    window_df: pd.DataFrame,
    cohort: str,
    thresholds: dict[str, float] | None = None,
    min_complete_cycles: int = 6,
) -> dict[str, Any]:
    """Definition C: repeated same-pattern positivity across complete cycles."""

    thresholds = thresholds or DEFAULT_THRESHOLDS
    complete_ids = []
    for cycle_id, g in window_df.groupby("cycle_id", sort=False):
        length = int(g["cycle_length"].iloc[0])
        if len(g) == length and int(g["cycle_day"].min()) == 1 and int(g["cycle_day"].max()) == length:
            complete_ids.append(int(cycle_id))
    if len(complete_ids) < min_complete_cycles:
        return {
            "label_C_any": None,
            "label_C_C1": None,
            "label_C_C2": None,
            "label_C_C3": None,
            "c_reason": "fewer_than_required_complete_cycles",
        }

    cycle_labels = []
    for cycle_id in complete_ids:
        cycle_labels.append(_cycle_level_labels(window_df[window_df["cycle_id"] == cycle_id], cohort, thresholds))

    pooled = pooled_adsf_and_ratios(window_df, cohort, thresholds)["ratios"]
    pooled_c1, _ = ratio_positive(pooled["C1"], thresholds["C1"])
    pooled_c2, _ = ratio_positive(pooled["C2"], thresholds["C2"])
    pooled_c3 = None
    if pooled["C3"] is not None:
        pooled_c3, _ = ratio_positive(pooled["C3"], thresholds["C3"])

    required = math.ceil((2.0 / 3.0) * len(cycle_labels))
    c1_count = sum(label["C1"] is True for label in cycle_labels)
    c2_count = sum(label["C2"] is True for label in cycle_labels)
    ilp_labels = [label for label, cycle_id in zip(cycle_labels, complete_ids) if bool(window_df[window_df["cycle_id"] == cycle_id]["ilp_flag"].iloc[0])]
    c3_required = math.ceil((2.0 / 3.0) * len(ilp_labels)) if len(ilp_labels) >= min_complete_cycles else None
    c3_count = sum(label["C3"] is True for label in ilp_labels)

    c1 = _repro_pattern_label(c1_count, required, pooled_c1, [label["C1"] for label in cycle_labels])
    c2 = _repro_pattern_label(c2_count, required, pooled_c2, [label["C2"] for label in cycle_labels])
    c3 = None
    if cohort == "population" and c3_required is not None and pooled_c3 is not None:
        c3 = _repro_pattern_label(c3_count, c3_required, pooled_c3, [label["C3"] for label in ilp_labels])
    applicable = [c1, c2] + ([] if c3 is None else [c3])
    any_label = True if any(label is True for label in applicable) else (False if any(label is False for label in applicable) else None)
    return {
        "label_C_any": any_label,
        "label_C_C1": c1,
        "label_C_C2": c2,
        "label_C_C3": c3,
        "c_reason": None,
    }


def _repro_pattern_label(
    positive_count: int,
    required: int,
    pooled_positive: bool | None,
    cycle_pattern_labels: list[bool | None],
) -> bool | None:
    if positive_count >= required and pooled_positive is True:
        return True
    if pooled_positive is None or any(label is None for label in cycle_pattern_labels):
        return None
    return False


def window_base_fields(
    window_df: pd.DataFrame,
    cohort: str,
    window_type: str,
    window_value: Any,
    days_per_month: float,
) -> dict[str, Any]:
    n_days = int(len(window_df))
    n_complete = count_complete_cycles(window_df) if n_days else 0
    strict_eligible = bool(n_days > 0 and window_df["strict_herzog_cycle_eligible"].all())
    c3_applicable = bool(cohort == "population" and n_days > 0 and "ilp_flag" in window_df and window_df["ilp_flag"].any())
    return {
        "window_type": window_type,
        "window_value": window_value,
        "window_start": int(window_df["calendar_day_index"].min()) if n_days else None,
        "window_end": int(window_df["calendar_day_index"].max()) if n_days else None,
        "n_days": n_days,
        "n_complete_cycles": n_complete,
        "seizure_count_total": int(window_df["seizure_count"].sum()) if n_days else 0,
        "seizure_days_total": int(window_df["seizure_day"].sum()) if n_days else 0,
        "strict_herzog_eligible_flag": strict_eligible,
        "short_cycle_modified_flag": bool(window_df["short_cycle_modified_flag"].any()) if n_days else False,
        "c3_applicable_flag": c3_applicable,
        "seizure_days_per_month": (
            int(window_df["seizure_day"].sum()) / month_denominator(n_days, days_per_month) if n_days else np.nan
        ),
        "seizures_per_month": (
            int(window_df["seizure_count"].sum()) / month_denominator(n_days, days_per_month) if n_days else np.nan
        ),
    }
