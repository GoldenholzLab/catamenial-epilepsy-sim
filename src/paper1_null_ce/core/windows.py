"""Observation-window sampling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from paper1_null_ce.core.phase_labeling import complete_cycle_ids


@dataclass(frozen=True)
class WindowSpec:
    window_type: str
    window_value: Any
    start_day: int | None
    end_day: int | None
    valid: bool = True
    indeterminate_reason: str | None = None
    study_pool: bool = False


def sample_primary_windows(
    daily: pd.DataFrame,
    rng: np.random.Generator,
    calendar_months: list[int],
    cycle_counts: list[int],
    days_per_month: int,
) -> list[WindowSpec]:
    specs: list[WindowSpec] = []
    total_days = int(daily["calendar_day_index"].max())
    for months in calendar_months:
        n_days = int(months * days_per_month)
        if n_days <= total_days:
            start = int(rng.integers(1, total_days - n_days + 2))
            specs.append(WindowSpec("calendar", months, start, start + n_days - 1))
        else:
            specs.append(WindowSpec("calendar", months, None, None, False, "calendar_window_longer_than_diary"))
    specs.append(WindowSpec("full", "full_diary", 1, total_days))

    complete_ids = complete_cycle_ids(daily, strict_only=False)
    complete_set = set(complete_ids)
    for count in cycle_counts:
        starts: list[int] = []
        for cycle_id in complete_ids:
            wanted = list(range(cycle_id, cycle_id + count))
            if all(item in complete_set for item in wanted):
                starts.append(cycle_id)
        if starts:
            start_cycle = int(rng.choice(starts))
            end_cycle = start_cycle + count - 1
            chunk = daily[daily["cycle_id"].between(start_cycle, end_cycle)]
            specs.append(
                WindowSpec(
                    "cycle",
                    count,
                    int(chunk["calendar_day_index"].min()),
                    int(chunk["calendar_day_index"].max()),
                )
            )
        else:
            specs.append(WindowSpec("cycle", count, None, None, False, "not_enough_complete_cycles"))
    return specs


def sample_study_pool_windows(
    daily: pd.DataFrame,
    rng: np.random.Generator,
    n_per_participant: int,
    months: int,
    days_per_month: int,
) -> list[WindowSpec]:
    total_days = int(daily["calendar_day_index"].max())
    n_days = int(months * days_per_month)
    if n_days > total_days:
        return [
            WindowSpec(
                "study_mc_calendar",
                months,
                None,
                None,
                False,
                "study_calendar_window_longer_than_diary",
                study_pool=True,
            )
        ]
    specs: list[WindowSpec] = []
    for _ in range(n_per_participant):
        start = int(rng.integers(1, total_days - n_days + 2))
        specs.append(WindowSpec("study_mc_calendar", months, start, start + n_days - 1, study_pool=True))
    return specs


def subset_window(daily: pd.DataFrame, spec: WindowSpec) -> pd.DataFrame:
    if not spec.valid or spec.start_day is None or spec.end_day is None:
        return daily.iloc[0:0].copy()
    # Simulated diaries use a contiguous one-based calendar index. Positional
    # slicing is equivalent to the boolean mask below and avoids constructing
    # 31 full-length masks per participant in the primary analysis.
    if (
        len(daily) > 0
        and int(daily["calendar_day_index"].iloc[0]) == 1
        and int(daily["calendar_day_index"].iloc[-1]) == len(daily)
    ):
        return daily.iloc[spec.start_day - 1 : spec.end_day].copy()
    return daily[
        (daily["calendar_day_index"] >= spec.start_day)
        & (daily["calendar_day_index"] <= spec.end_day)
    ].copy()
