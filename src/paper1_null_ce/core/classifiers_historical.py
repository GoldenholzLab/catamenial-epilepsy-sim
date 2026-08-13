"""Assumption-based exploratory historical CE definitions."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from paper1_null_ce.core.classifiers_windowed import DEFAULT_THRESHOLDS, pooled_adsf_and_ratios
from paper1_null_ce.core.utils import adsf_ratio, ratio_positive


def _seizure_fraction_in_mask(
    window_df: pd.DataFrame,
    mask: pd.Series | np.ndarray,
    threshold: float,
    strict_greater: bool,
) -> bool | None:
    seizure_values = window_df["seizure_count"].to_numpy(dtype=float, copy=False)
    mask_values = np.asarray(mask, dtype=bool)
    total = float(seizure_values.sum())
    if total <= 0:
        return None
    fraction = float(seizure_values[mask_values].sum()) / total
    return bool(fraction > threshold) if strict_greater else bool(fraction >= threshold)


def classify_h1_newmark_penry(window_df: pd.DataFrame, threshold: float = 0.50) -> dict[str, Any]:
    cycle_day = window_df["cycle_day"].to_numpy(dtype=np.int64, copy=False)
    backward = window_df["backward_day"].to_numpy(dtype=np.int64, copy=False)
    mask = ((cycle_day >= 1) & (cycle_day <= 4)) | ((backward >= -3) & (backward <= -1))
    return {
        "label_H1_any": _seizure_fraction_in_mask(window_df, mask, threshold, strict_greater=True),
        "h1_threshold": threshold,
        "assumption_based_historical": True,
    }


def classify_h2_duncan1993(window_df: pd.DataFrame) -> dict[str, Any]:
    cycle_day = window_df["cycle_day"].to_numpy(dtype=np.int64, copy=False)
    backward = window_df["backward_day"].to_numpy(dtype=np.int64, copy=False)
    mask = ((cycle_day >= 1) & (cycle_day <= 6)) | ((backward >= -4) & (backward <= -1))
    return {
        "label_H2_any": _seizure_fraction_in_mask(window_df, mask, 0.75, strict_greater=False),
        "assumption_based_historical": True,
    }


def classify_h3_herzog1997_twofold(window_df: pd.DataFrame, cohort: str) -> dict[str, Any]:
    thresholds = {"C1": 2.0, "C2": 2.0, "C3": 2.0}
    ratios = pooled_adsf_and_ratios(window_df, cohort, thresholds)["ratios"]
    c1, _ = ratio_positive(ratios["C1"], thresholds["C1"])
    c2, _ = ratio_positive(ratios["C2"], thresholds["C2"])
    c3 = None
    if ratios["C3"] is not None:
        c3, _ = ratio_positive(ratios["C3"], thresholds["C3"])
    labels = [c1, c2] + ([] if c3 is None else [c3])
    return {
        "label_H3_any": True if any(label is True for label in labels) else (False if any(label is False for label in labels) else None),
        "label_H3_C1": c1,
        "label_H3_C2": c2,
        "label_H3_C3": c3,
        "assumption_based_historical": True,
    }


def classify_h4_reddy2007_any_phase2x(window_df: pd.DataFrame) -> dict[str, Any]:
    labels: dict[str, bool | None] = {}
    triggering: list[str] = []
    phase_values = window_df["phase_reddy"].to_numpy(copy=False)
    seizure_values = window_df["seizure_count"].to_numpy(dtype=float, copy=False)
    total_count = float(seizure_values.sum())
    total_days = int(len(window_df))
    for phase in ["P", "F", "O", "L"]:
        phase_mask = phase_values == phase
        numerator_count = float(seizure_values[phase_mask].sum())
        numerator_days = int(np.count_nonzero(phase_mask))
        comparator_count = total_count - numerator_count
        comparator_days = total_days - numerator_days
        ratio = adsf_ratio(numerator_count, numerator_days, comparator_count, comparator_days)
        label, _ = ratio_positive(ratio, 2.0)
        labels[phase] = label
        if label is True:
            triggering.append(phase)
    any_label = True if triggering else (False if any(value is False for value in labels.values()) else None)
    return {
        "label_H4_any": any_label,
        "label_H4_phase": ",".join(triggering) if triggering else None,
        "assumption_based_historical": True,
    }


def classify_historical_all(
    window_df: pd.DataFrame,
    cohort: str,
    h1_threshold: float = 0.50,
    h1_sensitivity_threshold: float = 0.667,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    payload.update(classify_h1_newmark_penry(window_df, threshold=h1_threshold))
    h1_sensitivity = classify_h1_newmark_penry(window_df, threshold=h1_sensitivity_threshold)
    payload["label_H1_sensitivity_any"] = h1_sensitivity["label_H1_any"]
    payload["h1_sensitivity_threshold"] = h1_sensitivity_threshold
    payload.update(classify_h2_duncan1993(window_df))
    payload.update(classify_h3_herzog1997_twofold(window_df, cohort))
    payload.update(classify_h4_reddy2007_any_phase2x(window_df))
    return payload
