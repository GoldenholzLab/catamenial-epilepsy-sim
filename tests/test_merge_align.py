from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.core.merge_align import merge_independent_diaries


def _seizure_diary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "participant_id": ["p1"] * 4,
            "calendar_day_index": [1, 2, 3, 4],
            "seizure_count": [0, 1, 3, 2],
        }
    )


def _hormone_diary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "participant_id": ["p1"] * 4,
            "calendar_day_index": [1, 2, 3, 4],
            "cycle_day": [1, 2, 3, 4],
        }
    )


def test_merge_preserves_calendar_order_without_rotation() -> None:
    merged = merge_independent_diaries(_seizure_diary(), _hormone_diary())

    assert merged["calendar_day_index"].tolist() == [1, 2, 3, 4]
    assert merged["seizure_count"].tolist() == [0, 1, 3, 2]
    assert merged["seizure_day"].tolist() == [0, 1, 1, 1]
    assert merged.columns.tolist() == [
        "participant_id",
        "calendar_day_index",
        "cycle_day",
        "seizure_count",
        "seizure_day",
    ]


def test_merge_rejects_mismatched_calendar_indices() -> None:
    hormone = _hormone_diary()
    hormone["calendar_day_index"] = [2, 3, 4, 5]

    with pytest.raises(ValueError, match="same calendar-day index"):
        merge_independent_diaries(_seizure_diary(), hormone)
