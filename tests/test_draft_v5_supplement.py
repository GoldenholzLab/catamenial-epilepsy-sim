from __future__ import annotations

import numpy as np
import pandas as pd

from paper1_null_ce.core.regression_nb import classify_regression_nb_c3_exploratory
from scripts.build_draft_v5_supplement import cumulative_herzog_table


def _cycle(cycle_id: int, ilp: bool, f_count: int = 0, olm_count: int = 0) -> pd.DataFrame:
    rows = []
    phases = ["M", "M", "M", "F", "F", "F", "O", "O", "L", "L"]
    for day, phase in enumerate(phases, start=1):
        count = f_count if phase == "F" else olm_count
        rows.append(
            {
                "cycle_id": cycle_id,
                "cycle_day": day,
                "cycle_length": len(phases),
                "phase": phase,
                "ilp_flag": ilp,
                "seizure_count": count,
                "seizure_day": int(count > 0),
            }
        )
    return pd.DataFrame(rows)


def test_c3_nb_not_applicable_to_healthy_cohort() -> None:
    daily = pd.concat([_cycle(i, True, 0, 1) for i in range(1, 5)], ignore_index=True)
    result = classify_regression_nb_c3_exploratory(daily, "healthy_ovulatory")
    assert result["label_D_C3_exploratory"] is None
    assert result["d_c3_exploratory_reason"] == "not_applicable_to_cohort"


def test_c3_nb_requires_minimum_cycles() -> None:
    daily = pd.concat([_cycle(i, True, 0, 1) for i in range(1, 4)], ignore_index=True)
    result = classify_regression_nb_c3_exploratory(daily, "population")
    assert result["label_D_C3_exploratory"] is None
    assert result["d_c3_exploratory_reason"] == "fewer_than_required_complete_ilp_cycles"


def test_c3_nb_detects_constructed_enrichment() -> None:
    daily = pd.concat([_cycle(i, True, 1, 4) for i in range(1, 9)], ignore_index=True)
    result = classify_regression_nb_c3_exploratory(daily, "population", alpha=0.2)
    assert result["label_D_C3_exploratory"] is True
    assert result["d_c3_exploratory_rr"] >= 1.62


def test_c3_nb_constructed_null_is_not_positive() -> None:
    daily = pd.concat([_cycle(i, True, 1, 1) for i in range(1, 9)], ignore_index=True)
    result = classify_regression_nb_c3_exploratory(daily, "population", alpha=0.2)
    assert result["label_D_C3_exploratory"] is False


def test_c3_nb_missing_comparator_phase_is_indeterminate() -> None:
    daily = pd.concat([_cycle(i, True, 1, 4) for i in range(1, 9)], ignore_index=True)
    daily.loc[daily["phase"] == "F", "phase"] = None
    result = classify_regression_nb_c3_exploratory(daily, "population", alpha=0.2)
    assert result["label_D_C3_exploratory"] is None
    assert result["d_c3_exploratory_reason"] == "missing_follicular_phase"


def test_cumulative_table_handles_infinity_and_undefined() -> None:
    rows = []
    for participant, rr1, rr2, rr3, applicable in [
        ("p1", np.inf, 2.0, np.inf, True),
        ("p2", 1.0, np.nan, np.nan, True),
        ("p3", np.nan, 0.5, np.nan, False),
    ]:
        rows.append(
            {
                "participant_id": participant,
                "cohort": "population",
                "phase_mode": "strict_herzog",
                "window_type": "cycle",
                "window_value": 3,
                "rr_C1": rr1,
                "rr_C2": rr2,
                "rr_C3": rr3,
                "c3_applicable_flag": applicable,
                "label_A_windowed_C1": None if pd.isna(rr1) else rr1 >= 1.69,
                "label_A_windowed_C2": None if pd.isna(rr2) else rr2 >= 1.83,
                "label_A_windowed_C3": None if pd.isna(rr3) else rr3 >= 1.62,
            }
        )
    result = cumulative_herzog_table(pd.DataFrame(rows))
    population = result[result["cohort"] == "population"]
    c1_zero = population[(population["pattern"] == "C1") & (population["threshold"] == 0)].iloc[0]
    c1_ten = population[(population["pattern"] == "C1") & (population["threshold"] == 10)].iloc[0]
    c3_zero = result[(result["pattern"] == "C3") & (result["threshold"] == 0)].iloc[0]
    assert c1_zero["n_defined"] == 2
    assert c1_zero["n_at_or_above"] == 2
    assert c1_ten["n_at_or_above"] == 1
    assert c3_zero["n_applicable"] == 2
    assert c3_zero["n_defined"] == 1
