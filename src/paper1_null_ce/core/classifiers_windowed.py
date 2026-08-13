"""Window-level Herzog-threshold classifiers and ADSF summaries."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from paper1_null_ce.core.phase_labeling import (
    complete_cycle_ids,
    count_complete_cycles,
    derived_frame_cache,
    phase_counts,
)
from paper1_null_ce.core.utils import adsf_ratio, first_reason, month_denominator, ratio_positive


DEFAULT_THRESHOLDS = {"C1": 1.69, "C2": 1.83, "C3": 1.62}


def pooled_adsf_and_ratios(
    window_df: pd.DataFrame,
    cohort: str,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    cache = derived_frame_cache(window_df)
    # Thresholds are applied by callers; the pooled ADSFs and ratios themselves
    # depend only on the window and cohort.
    cache_key = f"pooled_adsf_and_ratios:{cohort}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
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
    payload = {"adsf": adsf, "ratios": {"C1": rr_c1, "C2": rr_c2, "C3": rr_c3}}
    cache[cache_key] = payload
    return payload


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
        "label_A_windowed_C1_or_C2": _any_excluding_c3(c1, c2),
        "label_A_windowed_C1": c1,
        "label_A_windowed_C2": c2,
        "label_A_windowed_C3": c3,
        "label_A_windowed_pattern_category": pattern_category(c1, c2, c3),
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
            "label_B_C1_or_C2": None,
            "label_B_C1": None,
            "label_B_C2": None,
            "label_B_C3": None,
            "label_B_pattern_category": None,
            "b_reason": reason,
        }
    a = classify_a_windowed(window_df, cohort, thresholds)
    return {
        "label_B_any": a["label_A_windowed_any"],
        "label_B_C1_or_C2": a["label_A_windowed_C1_or_C2"],
        "label_B_C1": a["label_A_windowed_C1"],
        "label_B_C2": a["label_A_windowed_C2"],
        "label_B_C3": a["label_A_windowed_C3"],
        "label_B_pattern_category": a["label_A_windowed_pattern_category"],
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
    complete_ids = _complete_cycle_ids(window_df)
    if len(complete_ids) < min_complete_cycles:
        return {
            "label_C_any": None,
            "label_C_C1_or_C2": None,
            "label_C_C1": None,
            "label_C_C2": None,
            "label_C_C3": None,
            "label_C_pattern_category": None,
            "c_reason": "fewer_than_required_complete_cycles",
        }

    cycle_labels = _cycle_level_labels_grouped(window_df, complete_ids, cohort, thresholds)

    pooled = pooled_adsf_and_ratios(window_df, cohort, thresholds)["ratios"]
    pooled_c1, _ = ratio_positive(pooled["C1"], thresholds["C1"])
    pooled_c2, _ = ratio_positive(pooled["C2"], thresholds["C2"])
    pooled_c3 = None
    if pooled["C3"] is not None:
        pooled_c3, _ = ratio_positive(pooled["C3"], thresholds["C3"])

    required = math.ceil((2.0 / 3.0) * len(cycle_labels))
    c1_count = sum(label["C1"] is True for label in cycle_labels)
    c2_count = sum(label["C2"] is True for label in cycle_labels)
    ilp_by_cycle = _cycle_ilp_flags(window_df, complete_ids)
    ilp_labels = [label for label, cycle_id in zip(cycle_labels, complete_ids) if ilp_by_cycle.get(cycle_id, False)]
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
        "label_C_C1_or_C2": _any_excluding_c3(c1, c2),
        "label_C_C1": c1,
        "label_C_C2": c2,
        "label_C_C3": c3,
        "label_C_pattern_category": pattern_category(c1, c2, c3),
        "c_reason": None,
    }


def _complete_cycle_ids(window_df: pd.DataFrame) -> list[int]:
    return complete_cycle_ids(window_df)


def _cycle_ilp_flags(window_df: pd.DataFrame, complete_ids: list[int]) -> dict[int, bool]:
    if "ilp_flag" not in window_df or not complete_ids:
        return {}
    cache = derived_frame_cache(window_df)
    cache_key = ("cycle_ilp_flags", tuple(complete_ids))
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    row_cycle_ids = window_df["cycle_id"].to_numpy(copy=False)
    ilp_values = window_df["ilp_flag"].to_numpy(dtype=bool, copy=False)
    result = {
        int(cycle_id): bool(np.any(ilp_values[row_cycle_ids == cycle_id]))
        for cycle_id in complete_ids
    }
    cache[cache_key] = result
    return result


def _cycle_level_labels_grouped(
    window_df: pd.DataFrame,
    complete_ids: list[int],
    cohort: str,
    thresholds: dict[str, float],
) -> list[dict[str, bool | None]]:
    cache = derived_frame_cache(window_df)
    cache_key = (
        "cycle_level_labels_grouped",
        tuple(complete_ids),
        cohort,
        tuple(sorted((str(key), float(value)) for key, value in thresholds.items())),
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    row_cycle_ids = window_df["cycle_id"].to_numpy(copy=False)
    phase_values = window_df["phase"].to_numpy(copy=False)
    seizure_values = window_df["seizure_count"].to_numpy(dtype=float, copy=False)
    ovulatory_values = window_df["ovulatory_flag"].to_numpy(dtype=bool, copy=False)
    ilp_values = window_df["ilp_flag"].to_numpy(dtype=bool, copy=False)
    labeled = np.isin(phase_values, ["M", "O", "F", "L"])
    if not np.any(labeled & np.isin(row_cycle_ids, complete_ids)):
        labels = [{"C1": None, "C2": None, "C3": None} for _ in complete_ids]
        cache[cache_key] = labels
        return labels

    labels: list[dict[str, bool | None]] = []
    for cycle_id in complete_ids:
        cycle_mask = (row_cycle_ids == cycle_id) & labeled
        if not np.any(cycle_mask):
            labels.append({"C1": None, "C2": None, "C3": None})
            continue
        counts = {
            phase: {
                "days": int(np.count_nonzero(cycle_mask & (phase_values == phase))),
                "seizures": float(seizure_values[cycle_mask & (phase_values == phase)].sum()),
            }
            for phase in ["M", "O", "F", "L"]
        }
        first = int(np.flatnonzero(cycle_mask)[0])
        ovulatory = bool(ovulatory_values[first])
        ilp = bool(np.any(ilp_values[cycle_mask]))
        labels.append(
            _cycle_level_labels_from_counts(
                counts,
                cohort,
                thresholds,
                ovulatory,
                ilp,
                counts if cohort == "population" and ilp else None,
            )
        )
    cache[cache_key] = labels
    return labels


def _phase_counts_by_cycle(
    data: pd.DataFrame,
    complete_ids: list[int],
) -> dict[int, dict[str, dict[str, float]]]:
    counts_by_cycle: dict[int, dict[str, dict[str, float]]] = {
        cycle_id: {phase: {"days": 0, "seizures": 0.0} for phase in ["M", "O", "F", "L"]}
        for cycle_id in complete_ids
    }
    phase_table = (
        data.groupby(["cycle_id", "phase"], sort=False)
        .agg(days=("phase", "size"), seizures=("seizure_count", "sum"))
        .reset_index()
    )
    for row in phase_table.itertuples(index=False):
        counts_by_cycle[int(row.cycle_id)][str(row.phase)] = {
            "days": int(row.days),
            "seizures": float(row.seizures),
        }
    return counts_by_cycle


def _cycle_level_labels_from_counts(
    counts: dict[str, dict[str, float]],
    cohort: str,
    thresholds: dict[str, float],
    ovulatory: bool,
    ilp: bool,
    ilp_counts: dict[str, dict[str, float]] | None = None,
) -> dict[str, bool | None]:
    m = counts["M"]
    o = counts["O"]
    f = counts["F"]
    l = counts["L"]
    fl_days = f["days"] + l["days"]
    fl_seizures = f["seizures"] + l["seizures"]
    c1 = c2 = c3 = False
    if ovulatory:
        c1, _ = ratio_positive(adsf_ratio(m["seizures"], m["days"], fl_seizures, fl_days), thresholds["C1"])
        c2, _ = ratio_positive(adsf_ratio(o["seizures"], o["days"], fl_seizures, fl_days), thresholds["C2"])
    if cohort == "population" and ilp and ilp_counts is not None:
        cm = ilp_counts["M"]
        co = ilp_counts["O"]
        cf = ilp_counts["F"]
        cl = ilp_counts["L"]
        c3_olm_days = cm["days"] + co["days"] + cl["days"]
        c3_olm_seizures = cm["seizures"] + co["seizures"] + cl["seizures"]
        c3, _ = ratio_positive(adsf_ratio(c3_olm_seizures, c3_olm_days, cf["seizures"], cf["days"]), thresholds["C3"])
    return {"C1": c1, "C2": c2, "C3": c3}


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
    seizure_counts = window_df["seizure_count"].to_numpy(dtype=np.int64, copy=False) if n_days else np.empty(0)
    seizure_days = window_df["seizure_day"].to_numpy(dtype=np.int64, copy=False) if n_days else np.empty(0)
    seizure_count_total = int(seizure_counts.sum())
    seizure_days_total = int(seizure_days.sum())
    strict_eligible = bool(
        n_days > 0
        and np.all(window_df["strict_herzog_cycle_eligible"].to_numpy(dtype=bool, copy=False))
    )
    c3_applicable = bool(
        cohort == "population"
        and n_days > 0
        and "ilp_flag" in window_df
        and np.any(window_df["ilp_flag"].to_numpy(dtype=bool, copy=False))
    )
    calendar_days = window_df["calendar_day_index"].to_numpy(dtype=np.int64, copy=False) if n_days else np.empty(0)
    return {
        "window_type": window_type,
        "window_value": window_value,
        "window_start": int(calendar_days.min()) if n_days else None,
        "window_end": int(calendar_days.max()) if n_days else None,
        "n_days": n_days,
        "n_complete_cycles": n_complete,
        "seizure_count_total": seizure_count_total,
        "seizure_days_total": seizure_days_total,
        "strict_herzog_eligible_flag": strict_eligible,
        "short_cycle_modified_flag": bool(
            np.any(window_df["short_cycle_modified_flag"].to_numpy(dtype=bool, copy=False))
        ) if n_days else False,
        "luteal_anchored_ovulatory_flag": bool(
            np.any(window_df["luteal_anchored_ovulatory_flag"].to_numpy(dtype=bool, copy=False))
        ) if n_days and "luteal_anchored_ovulatory_flag" in window_df else False,
        "c3_applicable_flag": c3_applicable,
        "seizure_days_per_month": (
            seizure_days_total / month_denominator(n_days, days_per_month) if n_days else np.nan
        ),
        "seizures_per_month": (
            seizure_count_total / month_denominator(n_days, days_per_month) if n_days else np.nan
        ),
    }


def _any_excluding_c3(c1: Any, c2: Any) -> bool | None:
    labels = [c1, c2]
    if any(label is True for label in labels):
        return True
    if any(label is False for label in labels):
        return False
    return None


def pattern_category(c1: Any, c2: Any, c3: Any) -> str | None:
    """Return a mutually exclusive C-pattern category for a classifiable window."""

    labels = [c1, c2, c3]
    if all(label is None for label in labels):
        return None
    c1_pos = c1 is True
    c2_pos = c2 is True
    c3_pos = c3 is True
    c12_pos = c1_pos or c2_pos
    if c3_pos and c12_pos:
        return "C3 plus C1/C2"
    if c3_pos:
        return "C3 only"
    if c1_pos and c2_pos:
        return "C1+C2"
    if c1_pos:
        return "C1 only"
    if c2_pos:
        return "C2 only"
    if any(label is False for label in labels):
        return "none"
    return None
