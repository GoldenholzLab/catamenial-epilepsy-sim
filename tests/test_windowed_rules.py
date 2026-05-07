from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.core.classifiers_windowed import classify_a_windowed
from paper1_null_ce.core.phase_labeling import add_phase_labels
from paper1_null_ce.core.utils import adsf_ratio


def test_ratio_positive_numerator_zero_comparator_is_infinite() -> None:
    result = adsf_ratio(1, 3, 0, 10)
    assert result.ratio == math.inf
    assert not result.is_indeterminate


def test_ratio_zero_over_zero_is_indeterminate() -> None:
    result = adsf_ratio(0, 3, 0, 10)
    assert result.ratio is None
    assert result.is_indeterminate
    assert result.indeterminate_reason == "undefined_zero_over_zero"


def test_windowed_rule_preserves_infinite_ratio_positive() -> None:
    rows = []
    for day in range(1, 29):
        rows.append(
            {
                "participant_id": "p1",
                "calendar_day_index": day,
                "cycle_id": 1,
                "cycle_day": day,
                "cycle_length": 28,
                "seizure_count": 1 if day == 1 else 0,
                "seizure_day": 1 if day == 1 else 0,
                "ovulatory_flag": True,
                "ilp_flag": False,
            }
        )
    df = add_phase_labels(pd.DataFrame(rows))
    result = classify_a_windowed(df, "healthy_ovulatory")
    assert result["label_A_windowed_C1"] is True
    assert result["label_A_windowed_any"] is True
