"""Menstrual phase labeling for exact Herzog and protocol-modified analyses."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

PhaseMode = Literal["strict_herzog", "modified_short_cycle"]


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
    phase_func = herzog_phase_for_day if mode == "strict_herzog" else modified_short_cycle_phase_for_day
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
    out = mark_complete_cycles(out)
    return out


def mark_complete_cycles(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    complete_by_cycle: dict[int, bool] = {}
    for cycle_id, g in out.groupby("cycle_id", sort=False):
        length = int(g["cycle_length"].iloc[0])
        complete = len(g) == length and int(g["cycle_day"].min()) == 1 and int(g["cycle_day"].max()) == length
        complete_by_cycle[int(cycle_id)] = complete
    out["cycle_complete_flag"] = out["cycle_id"].map(complete_by_cycle).astype(bool)
    return out


def count_complete_cycles(window_df: pd.DataFrame) -> int:
    count = 0
    for _, g in window_df.groupby("cycle_id", sort=False):
        length = int(g["cycle_length"].iloc[0])
        if len(g) == length and int(g["cycle_day"].min()) == 1 and int(g["cycle_day"].max()) == length:
            count += 1
    return count


def complete_cycle_ids(df: pd.DataFrame, strict_only: bool = False) -> list[int]:
    ids: list[int] = []
    for cycle_id, g in df.groupby("cycle_id", sort=False):
        length = int(g["cycle_length"].iloc[0])
        complete = len(g) == length and int(g["cycle_day"].min()) == 1 and int(g["cycle_day"].max()) == length
        strict = bool(g["strict_herzog_cycle_eligible"].all())
        if complete and (strict or not strict_only):
            ids.append(int(cycle_id))
    return ids


def phase_counts(window_df: pd.DataFrame, phase_col: str = "phase") -> dict[str, dict[str, float]]:
    """Return observed days and seizure counts by phase."""

    result: dict[str, dict[str, float]] = {}
    for phase in ["M", "O", "F", "L"]:
        mask = window_df[phase_col] == phase
        result[phase] = {
            "days": int(mask.sum()),
            "seizures": float(window_df.loc[mask, "seizure_count"].sum()),
        }
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
