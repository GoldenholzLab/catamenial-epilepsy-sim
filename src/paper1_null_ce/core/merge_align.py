"""Merge independent seizure and hormone diaries after random circular alignment."""

from __future__ import annotations

import numpy as np
import pandas as pd


def merge_independent_diaries(
    seizure_daily: pd.DataFrame,
    hormone_daily: pd.DataFrame,
    seed: int,
    shift_target: str = "seizure",
) -> tuple[pd.DataFrame, int]:
    """Apply a random circular shift to one process and merge on calendar day."""

    if len(seizure_daily) != len(hormone_daily):
        raise ValueError("Seizure and hormone diaries must have equal length before merge.")
    days = len(hormone_daily)
    rng = np.random.default_rng(seed)
    shift = int(rng.integers(0, days))
    merged = hormone_daily.copy()
    seizure_counts = seizure_daily["seizure_count"].to_numpy(copy=True)
    if shift_target == "seizure":
        seizure_counts = np.roll(seizure_counts, shift)
    elif shift_target == "hormone":
        merged = merged.iloc[np.roll(np.arange(days), shift)].reset_index(drop=True)
        merged["calendar_day_index"] = np.arange(1, days + 1, dtype=np.int32)
    else:
        raise ValueError("shift_target must be 'seizure' or 'hormone'.")
    merged["seizure_count"] = seizure_counts.astype(np.int32)
    merged["seizure_day"] = (merged["seizure_count"] > 0).astype(np.int8)
    merged["circular_shift_days"] = shift
    return merged, shift
