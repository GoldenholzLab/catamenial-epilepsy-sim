from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.core.summarize import summarize_pattern_decomposition, summarize_window_results


def test_c1_or_c2_union_matches_c3_excluding_summary() -> None:
    rows = []
    labels = [
        (True, False),
        (False, True),
        (True, True),
        (False, False),
        (None, None),
    ]
    for i, (c12, excluding_c3) in enumerate(labels, start=1):
        rows.append(
            {
                "participant_id": f"p{i}",
                "cohort": "healthy_ovulatory",
                "phase_mode": "strict_herzog",
                "window_type": "full",
                "window_value": "full_diary",
                "label_A_windowed_C1_or_C2": c12,
                "label_A_windowed_excluding_C3": excluding_c3,
                "seizure_days_per_month": 2.0,
                "seizures_per_month": 4.0,
                "seizure_days_total": 10,
                "strict_herzog_eligible_flag": True,
            }
        )
    summary = summarize_window_results(pd.DataFrame(rows))
    c12 = summary[(summary["definition"] == "A_windowed_C1_or_C2") & (summary["subset"] == "all")].iloc[0]
    excluding = summary[(summary["definition"] == "A_windowed_excluding_C3") & (summary["subset"] == "all")].iloc[0]
    assert c12["positives"] == excluding["positives"]
    assert c12["n_classifiable"] == excluding["n_classifiable"]
    assert c12["false_positive_rate"] == excluding["false_positive_rate"]


def test_small_classifiable_denominator_is_flagged() -> None:
    rows = [
        {
            "participant_id": f"p{i}",
            "cohort": "healthy_ovulatory",
            "phase_mode": "strict_herzog",
            "window_type": "cycle",
            "window_value": 3,
            "label_B_any": True if i == 0 else None,
            "seizure_days_per_month": 2.0,
            "seizures_per_month": 4.0,
            "seizure_days_total": 4,
            "strict_herzog_eligible_flag": True,
        }
        for i in range(10)
    ]
    summary = summarize_window_results(pd.DataFrame(rows))
    row = summary[(summary["definition"] == "B_minimum_data_any") & (summary["subset"] == "all")].iloc[0]
    assert bool(row["unstable_denominator"]) is True
    assert row["interpretation_note"] == "unstable; not interpreted"


def test_pattern_decomposition_counts_mutually_exclusive_categories() -> None:
    rows = [
        {
            "participant_id": f"p{i}",
            "cohort": "population",
            "phase_mode": "strict_herzog",
            "window_type": "full",
            "window_value": "full_diary",
            "label_A_windowed_pattern_category": category,
        }
        for i, category in enumerate(["C1 only", "C2 only", "C1+C2", "C3 only", "C3 plus C1/C2", "none"], start=1)
    ]
    summary = summarize_pattern_decomposition(pd.DataFrame(rows))
    counts = summary.set_index("pattern_category")["positives"].to_dict()
    assert counts["C1 only"] == 1
    assert counts["C2 only"] == 1
    assert counts["C1+C2"] == 1
    assert counts["C3 only"] == 1
    assert counts["C3 plus C1/C2"] == 1
    assert counts["none"] == 1
