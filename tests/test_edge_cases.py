from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.core.classifiers_windowed import classify_reproducibility
from paper1_null_ce.core.phase_labeling import add_phase_labels, herzog_phase_for_day
from paper1_null_ce.core.regression_nb import classify_regression_nb


def _six_cycle_window(n_positive: int) -> pd.DataFrame:
    rows = []
    calendar = 1
    for cycle_id in range(1, 7):
        for day in range(1, 29):
            phase = herzog_phase_for_day(day, 28)
            seizure = 0
            if cycle_id <= n_positive and phase == "M" and day == 1:
                seizure = 1
            if cycle_id > n_positive and phase == "F" and day == 4:
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


def test_reproducibility_four_of_six_positive_is_positive() -> None:
    result = classify_reproducibility(_six_cycle_window(4), "healthy_ovulatory")
    assert result["label_C_C1"] is True
    assert result["label_C_any"] is True


def test_reproducibility_three_of_six_positive_is_negative() -> None:
    result = classify_reproducibility(_six_cycle_window(3), "healthy_ovulatory")
    assert result["label_C_C1"] is False
    assert result["label_C_any"] is False


def _regression_window(enriched: bool) -> pd.DataFrame:
    rows = []
    calendar = 1
    for cycle_id in range(1, 13):
        for day in range(1, 29):
            phase = herzog_phase_for_day(day, 28)
            seizure = 0
            if enriched:
                if phase == "M":
                    seizure = 5
                else:
                    seizure = 1
            else:
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


def test_regression_toy_menstrual_enrichment_is_c1_positive() -> None:
    result = classify_regression_nb(_regression_window(True), "healthy_ovulatory", "cycle", 12, 30, alpha=1.0)
    assert result["label_D_C1"] is True
    assert result["label_D_any"] is True


def test_regression_toy_flat_counts_is_negative_or_nonsignificant() -> None:
    result = classify_regression_nb(_regression_window(False), "healthy_ovulatory", "cycle", 12, 30, alpha=1.0)
    assert result["label_D_any"] in {False, None}
