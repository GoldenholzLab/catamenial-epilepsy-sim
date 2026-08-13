"""Merge independently generated seizure and hormone diaries by calendar day."""

from __future__ import annotations

import numpy as np
import pandas as pd


def merge_independent_diaries(
    seizure_daily: pd.DataFrame,
    hormone_daily: pd.DataFrame,
) -> pd.DataFrame:
    """Align independent diary rows directly on their shared calendar-day index."""

    if len(seizure_daily) != len(hormone_daily):
        raise ValueError("Seizure and hormone diaries must have equal length before merge.")
    if not seizure_daily["calendar_day_index"].reset_index(drop=True).equals(
        hormone_daily["calendar_day_index"].reset_index(drop=True)
    ):
        raise ValueError("Seizure and hormone diaries must share the same calendar-day index.")

    merged = hormone_daily.copy()
    seizure_counts = seizure_daily["seizure_count"].to_numpy(copy=True)
    merged["seizure_count"] = seizure_counts.astype(np.int32)
    merged["seizure_day"] = (merged["seizure_count"] > 0).astype(np.int8)
    return merged
