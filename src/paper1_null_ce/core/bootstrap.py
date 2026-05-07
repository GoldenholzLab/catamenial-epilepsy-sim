"""Participant bootstrap helpers for derived summaries."""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd


def bootstrap_by_participant(
    data: pd.DataFrame,
    statistic: Callable[[pd.DataFrame], float],
    participant_col: str = "participant_id",
    n_replicates: int = 1000,
    seed: int = 1,
) -> pd.DataFrame:
    """Bootstrap a scalar statistic by resampling participants with replacement."""

    rng = np.random.default_rng(seed)
    participants = data[participant_col].drop_duplicates().to_numpy()
    rows: list[dict[str, float | int]] = []
    if participants.size == 0:
        return pd.DataFrame(rows)
    grouped = {pid: g for pid, g in data.groupby(participant_col, sort=False)}
    for replicate in range(n_replicates):
        sampled = rng.choice(participants, size=participants.size, replace=True)
        sample_df = pd.concat([grouped[pid] for pid in sampled], ignore_index=True)
        rows.append({"replicate": replicate, "statistic": float(statistic(sample_df))})
    return pd.DataFrame(rows)
