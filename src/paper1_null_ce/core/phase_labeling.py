"""Menstrual phase labeling for exact Herzog and protocol-modified analyses."""

from __future__ import annotations

from typing import Literal
import weakref

import numpy as np
import pandas as pd

PhaseMode = Literal["strict_herzog", "modified_short_cycle", "luteal_anchored_ovulatory"]


def backward_day(forward_day: int, cycle_length: int) -> int:
    return int(forward_day) - (int(cycle_length) + 1)


def herzog_phase_for_day(forward_day: int, cycle_length: int) -> str | None:
    """Herzog-style phase labels for one observed cycle day."""

    d = int(forward_day)
    length = int(cycle_length)
    if d < 1 or d > length:
        return None
    b = backward_day(d, length)
    if d in {1, 2, 3} or b in {-3, -2, -1}:
        return "M"
    if d in {4, 5, 6, 7, 8, 9}:
        return "F"
    if d >= 10 and b <= -13:
        return "O"
    if b in {-12, -11, -10, -9, -8, -7, -6, -5, -4}:
        return "L"
    return None


def modified_short_cycle_phase_for_day(forward_day: int, cycle_length: int) -> str | None:
    """Protocol-modified short-cycle labels for population sensitivity analyses.

    For cycles shorter than 23 days this keeps the perimenstrual label for P/M,
    assigns the seven-day pre-luteal block ending at day -13 to O, assigns
    days -12 to -4 to L, and leaves remaining days as F. Standard-length cycles
    use exact Herzog labels.
    """

    d = int(forward_day)
    length = int(cycle_length)
    if length >= 23:
        return herzog_phase_for_day(d, length)
    if d < 1 or d > length:
        return None
    b = backward_day(d, length)
    if d in {1, 2, 3} or b in {-3, -2, -1}:
        return "M"
    if -19 <= b <= -13:
        return "O"
    if -12 <= b <= -4:
        return "L"
    return "F"


def luteal_anchored_ovulatory_phase_for_day(forward_day: int, cycle_length: int) -> str | None:
    """Biology-oriented sensitivity labels with a fixed pre-luteal ovulatory window.

    This keeps the Herzog perimenstrual and luteal windows but fixes the
    periovulatory window at backward days -16 to -13, immediately before the
    luteal phase. The follicular phase absorbs cycle-length variability.
    """

    d = int(forward_day)
    length = int(cycle_length)
    if d < 1 or d > length:
        return None
    b = backward_day(d, length)
    if d in {1, 2, 3} or b in {-3, -2, -1}:
        return "M"
    if -12 <= b <= -4:
        return "L"
    if -16 <= b <= -13:
        return "O"
    return "F"


def reddy_phase_for_day(forward_day: int, cycle_length: int) -> str | None:
    """Reddy 2007 exploratory four-phase table."""

    d = int(forward_day)
    length = int(cycle_length)
    if d < 1 or d > length:
        return None
    b = backward_day(d, length)
    if d in {1, 2, 3} or b in {-3, -2, -1}:
        return "P"
    if 4 <= d <= 9:
        return "F"
    if 10 <= d <= 16:
        return "O"
    if d >= 17 and b <= -4:
        return "L"
    return "L"


def add_phase_labels(df: pd.DataFrame, mode: PhaseMode = "strict_herzog") -> pd.DataFrame:
    """Assign phase labels on the full diary before window subsetting."""

    out = df.copy()
    if mode == "strict_herzog":
        phase_func = herzog_phase_for_day
    elif mode == "modified_short_cycle":
        phase_func = modified_short_cycle_phase_for_day
    elif mode == "luteal_anchored_ovulatory":
        phase_func = luteal_anchored_ovulatory_phase_for_day
    else:
        raise ValueError(f"Unknown phase labeling mode: {mode}")
    out["backward_day"] = [
        backward_day(day, length) for day, length in zip(out["cycle_day"], out["cycle_length"])
    ]
    out["phase"] = [
        phase_func(day, length) for day, length in zip(out["cycle_day"], out["cycle_length"])
    ]
    out["phase_reddy"] = [
        reddy_phase_for_day(day, length) for day, length in zip(out["cycle_day"], out["cycle_length"])
    ]
    out["strict_herzog_cycle_eligible"] = (
        (out["cycle_length"] >= 23) & (out["cycle_length"] <= 35)
    ).astype(bool)
    out["short_cycle_modified_flag"] = bool(mode == "modified_short_cycle")
    out["luteal_anchored_ovulatory_flag"] = bool(mode == "luteal_anchored_ovulatory")
    out = mark_complete_cycles(out)
    return out


def mark_complete_cycles(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    cycle_ids, complete, _ = _cycle_completion_arrays(out)
    complete_ids = cycle_ids[complete]
    out["cycle_complete_flag"] = np.isin(
        out["cycle_id"].to_numpy(copy=False),
        complete_ids,
    )
    return out


_DERIVED_FRAME_CACHES: dict[
    int,
    tuple[weakref.ReferenceType[pd.DataFrame], dict[object, object]],
] = {}


def derived_frame_cache(df: pd.DataFrame) -> dict[object, object]:
    """Return a cache that is valid only for this concrete DataFrame object.

    The cache is kept outside ``DataFrame.attrs`` because pandas deep-copies
    attributes during many selections; putting derived tables there makes the
    intended optimization slower. Weak references clear each entry as soon as
    its short-lived window frame is released.
    """

    key = id(df)
    existing = _DERIVED_FRAME_CACHES.get(key)
    if existing is not None and existing[0]() is df:
        return existing[1]

    cache: dict[object, object] = {}

    def discard(reference: weakref.ReferenceType[pd.DataFrame], *, frame_key: int = key) -> None:
        current = _DERIVED_FRAME_CACHES.get(frame_key)
        if current is not None and current[0] is reference:
            _DERIVED_FRAME_CACHES.pop(frame_key, None)

    reference = weakref.ref(df, discard)
    _DERIVED_FRAME_CACHES[key] = (reference, cache)
    return cache


def count_complete_cycles(window_df: pd.DataFrame) -> int:
    if window_df.empty:
        return 0
    return int(np.count_nonzero(_cycle_completion_arrays(window_df)[1]))


def complete_cycle_ids(df: pd.DataFrame, strict_only: bool = False) -> list[int]:
    if df.empty:
        return []
    cycle_ids, complete, strict = _cycle_completion_arrays(df)
    mask = complete
    if strict_only:
        mask = mask & strict
    return [int(cycle_id) for cycle_id in cycle_ids[mask]]


def _cycle_completion_arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cache = derived_frame_cache(df)
    cached = cache.get("cycle_completion_arrays")
    if cached is not None:
        return cached
    if df.empty:
        result = (
            np.empty(0, dtype=np.int64),
            np.empty(0, dtype=bool),
            np.empty(0, dtype=bool),
        )
        cache["cycle_completion_arrays"] = result
        return result

    row_cycle_ids = df["cycle_id"].to_numpy()
    starts = np.flatnonzero(np.r_[True, row_cycle_ids[1:] != row_cycle_ids[:-1]])
    ends = np.r_[starts[1:], len(row_cycle_ids)]
    cycle_days = df["cycle_day"].to_numpy(dtype=np.int64, copy=False)
    cycle_lengths = df["cycle_length"].to_numpy(dtype=np.int64, copy=False)
    strict_rows = df["strict_herzog_cycle_eligible"].to_numpy(dtype=bool, copy=False)
    cycle_ids = row_cycle_ids[starts]
    lengths = cycle_lengths[starts]
    complete = (
        ((ends - starts) == lengths)
        & (np.minimum.reduceat(cycle_days, starts) == 1)
        & (np.maximum.reduceat(cycle_days, starts) == lengths)
    )
    strict = np.logical_and.reduceat(strict_rows, starts)
    result = (cycle_ids, complete, strict)
    cache["cycle_completion_arrays"] = result
    return result


def _cycle_completion_stats(df: pd.DataFrame) -> pd.DataFrame:
    # A window is classified by several definitions in succession.  Repeating
    # the same small pandas groupby for every definition dominated the full
    # Monte-Carlo runtime, so retain immutable derived summaries on the
    # short-lived window frame.
    cache = derived_frame_cache(df)
    cached = cache.get("cycle_completion_stats")
    if cached is not None:
        return cached
    if df.empty:
        stats = pd.DataFrame(
            columns=["n_days", "cycle_length", "min_day", "max_day", "strict", "complete"],
            index=pd.Index([], name="cycle_id"),
        )
        cache["cycle_completion_stats"] = stats
        return stats

    row_cycle_ids = df["cycle_id"].to_numpy()
    starts = np.flatnonzero(np.r_[True, row_cycle_ids[1:] != row_cycle_ids[:-1]])
    ends = np.r_[starts[1:], len(row_cycle_ids)]
    cycle_days = df["cycle_day"].to_numpy(dtype=np.int64, copy=False)
    cycle_lengths = df["cycle_length"].to_numpy(dtype=np.int64, copy=False)
    strict = df["strict_herzog_cycle_eligible"].to_numpy(dtype=bool, copy=False)
    stats = pd.DataFrame(
        {
            "n_days": ends - starts,
            "cycle_length": cycle_lengths[starts],
            "min_day": np.minimum.reduceat(cycle_days, starts),
            "max_day": np.maximum.reduceat(cycle_days, starts),
            "strict": np.logical_and.reduceat(strict, starts),
        },
        index=pd.Index(row_cycle_ids[starts], name="cycle_id"),
    )
    stats["complete"] = (
        (stats["n_days"].astype(int) == stats["cycle_length"].astype(int))
        & (stats["min_day"].astype(int) == 1)
        & (stats["max_day"].astype(int) == stats["cycle_length"].astype(int))
    )
    cache["cycle_completion_stats"] = stats
    return stats


def phase_counts(window_df: pd.DataFrame, phase_col: str = "phase") -> dict[str, dict[str, float]]:
    """Return observed days and seizure counts by phase."""

    cache = derived_frame_cache(window_df)
    cache_key = f"phase_counts:{phase_col}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    phase_values = window_df[phase_col].to_numpy(copy=False)
    seizure_values = window_df["seizure_count"].to_numpy(dtype=float, copy=False)
    result: dict[str, dict[str, float]] = {}
    for phase in ["M", "O", "F", "L"]:
        mask = phase_values == phase
        result[phase] = {
            "days": int(np.count_nonzero(mask)),
            "seizures": float(seizure_values[mask].sum()),
        }
    cache[cache_key] = result
    return result


def observed_phase_adsf(window_df: pd.DataFrame) -> dict[str, float]:
    counts = phase_counts(window_df)
    adsf: dict[str, float] = {}
    for phase, values in counts.items():
        adsf[phase] = values["seizures"] / values["days"] if values["days"] > 0 else np.nan
    fl_days = counts["F"]["days"] + counts["L"]["days"]
    fl_seizures = counts["F"]["seizures"] + counts["L"]["seizures"]
    olm_days = counts["O"]["days"] + counts["L"]["days"] + counts["M"]["days"]
    olm_seizures = counts["O"]["seizures"] + counts["L"]["seizures"] + counts["M"]["seizures"]
    adsf["FL"] = fl_seizures / fl_days if fl_days > 0 else np.nan
    adsf["OLM"] = olm_seizures / olm_days if olm_days > 0 else np.nan
    return adsf
