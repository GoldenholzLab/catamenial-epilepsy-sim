from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.core.classifiers_exact import classify_exact_herzog2004
from paper1_null_ce.core.phase_labeling import add_phase_labels, herzog_phase_for_day


def _three_cycle_window(positive_cycles: set[int]) -> pd.DataFrame:
    rows = []
    calendar = 1
    for cycle_id in range(1, 4):
        for day in range(1, 29):
            phase = herzog_phase_for_day(day, 28)
            seizure = 0
            if cycle_id in positive_cycles and phase == "M" and day == 1:
                seizure = 1
            if cycle_id not in positive_cycles and phase == "F" and day == 4:
                seizure = 1
            rows.append(
                {
                    "participant_id": "p1",
                    "calendar_day_index": calendar,
                    "cycle_id": cycle_id,
                    "cycle_day": day,
                    "cycle_length": 28,
                    "seizure_count": seizure,
                    "seizure_day": int(seizure > 0),
                    "ovulatory_flag": True,
                    "ilp_flag": False,
                }
            )
            calendar += 1
    return add_phase_labels(pd.DataFrame(rows))


def test_exact_herzog_two_of_three_positive_cycles_is_positive() -> None:
    result = classify_exact_herzog2004(_three_cycle_window({1, 2}), "healthy_ovulatory")
    assert result["label_A_exact_any"] is True
    assert result["label_A_exact_C1"] is True


def test_exact_herzog_one_of_three_positive_cycles_is_negative() -> None:
    result = classify_exact_herzog2004(_three_cycle_window({1}), "healthy_ovulatory")
    assert result["label_A_exact_any"] is False
    assert result["label_A_exact_C1"] is False
