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


def test_exact_herzog_one_positive_cycle_with_undefined_other_pattern_is_indeterminate() -> None:
    result = classify_exact_herzog2004(_three_cycle_window({1}), "healthy_ovulatory")
    assert result["label_A_exact_any"] is None
    assert result["label_A_exact_C1"] is False


def _pattern_window(patterns: list[str | None], *, ilp: bool = False) -> pd.DataFrame:
    """Use nonzero comparators to distinguish mixed from repeated patterns."""
    rows = []
    for cycle_id, pattern in enumerate(patterns, start=1):
        for day in range(1, 29):
            phase = herzog_phase_for_day(day, 28)
            seizure = 1
            if pattern == "C1" and phase == "M":
                seizure = 4
            elif pattern == "C2" and phase == "O":
                seizure = 4
            elif pattern == "C3" and phase in {"O", "L", "M"}:
                seizure = 4
            elif pattern == "undefined":
                seizure = 0
            rows.append(
                {
                    "participant_id": "p1",
                    "calendar_day_index": (cycle_id - 1) * 28 + day,
                    "cycle_id": cycle_id,
                    "cycle_day": day,
                    "cycle_length": 28,
                    "seizure_count": seizure,
                    "seizure_day": int(seizure > 0),
                    "ovulatory_flag": not ilp,
                    "ilp_flag": ilp,
                }
            )
    return add_phase_labels(pd.DataFrame(rows))


def test_exact_herzog_different_positive_patterns_do_not_qualify() -> None:
    result = classify_exact_herzog2004(_pattern_window(["C1", "C2", None]), "healthy_ovulatory")
    assert result["label_A_exact_C1"] is False
    assert result["label_A_exact_C2"] is False
    assert result["label_A_exact_any"] is False
    assert result["a_exact_reason"] is None


def test_exact_herzog_repeated_c2_qualifies() -> None:
    result = classify_exact_herzog2004(_pattern_window(["C2", "C2", None]), "healthy_ovulatory")
    assert result["label_A_exact_C2"] is True
    assert result["label_A_exact_any"] is True


def test_exact_herzog_undefined_pattern_remains_indeterminate() -> None:
    result = classify_exact_herzog2004(_pattern_window(["C1", "C2", "undefined"]), "healthy_ovulatory")
    assert result["label_A_exact_any"] is None
    assert result["a_exact_reason"] == "undefined_cycle_ratio"


def test_exact_herzog_repeated_c3_qualifies_in_applicable_cohort() -> None:
    result = classify_exact_herzog2004(_pattern_window(["C3", "C3", None], ilp=True), "population")
    assert result["label_A_exact_C3"] is True
    assert result["label_A_exact_any"] is True


def test_exact_herzog_definite_repeated_pattern_overrides_undefined_other() -> None:
    result = classify_exact_herzog2004(_pattern_window(["C1", "C1", "undefined"]), "healthy_ovulatory")
    assert result["label_A_exact_C1"] is True
    assert result["label_A_exact_C2"] is None
    assert result["label_A_exact_any"] is True
