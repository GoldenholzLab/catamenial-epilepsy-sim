"""Equivalence checks for the large-run compact hormone adapter path."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.adapters.hormone_cycle_adapter import HormoneCycleAdapter
from paper1_null_ce.core.utils import load_config


@pytest.mark.parametrize("cohort", ["healthy_ovulatory", "population"])
def test_compact_adapter_matches_full_cycle_structure_and_ilp(cohort: str) -> None:
    config = load_config(ROOT / "config_random_start_full.yaml")
    adapter = HormoneCycleAdapter(config)
    participant_id = f"compact-equivalence-{cohort}"
    full = adapter.simulate(
        participant_id,
        cohort,
        days=365,
        seed=1729,
        include_hormone_values=True,
    )
    compact = adapter.simulate(
        participant_id,
        cohort,
        days=365,
        seed=1729,
        include_hormone_values=False,
    )
    columns = [
        "calendar_day_index",
        "cycle_id",
        "cycle_day",
        "cycle_length",
        "menses_onset_flag",
        "ovulation_flag",
        "ovulatory_flag",
        "ovulation_day",
        "ilp_flag",
        "midluteal_progesterone",
        "cycle_stage",
    ]
    pd.testing.assert_frame_equal(
        full.daily[columns].reset_index(drop=True),
        compact.daily[columns].reset_index(drop=True),
        check_exact=True,
    )
    assert full.participant_summary == compact.participant_summary
