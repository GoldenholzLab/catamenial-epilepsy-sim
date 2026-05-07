from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.core.phase_labeling import herzog_phase_for_day, modified_short_cycle_phase_for_day


def phases(length: int) -> list[str | None]:
    return [herzog_phase_for_day(day, length) for day in range(1, length + 1)]


def test_herzog_23_day_cycle_boundaries() -> None:
    labels = phases(23)
    assert labels[0:3] == ["M", "M", "M"]
    assert labels[3:9] == ["F"] * 6
    assert labels[9:11] == ["O", "O"]
    assert labels[11:20] == ["L"] * 9
    assert labels[20:23] == ["M", "M", "M"]


def test_herzog_28_day_cycle_boundaries() -> None:
    labels = phases(28)
    assert labels[0:3] == ["M", "M", "M"]
    assert labels[3:9] == ["F"] * 6
    assert labels[9:16] == ["O"] * 7
    assert labels[16:25] == ["L"] * 9
    assert labels[25:28] == ["M", "M", "M"]


def test_herzog_35_day_cycle_boundaries() -> None:
    labels = phases(35)
    assert labels[0:3] == ["M", "M", "M"]
    assert labels[3:9] == ["F"] * 6
    assert labels[9:23] == ["O"] * 14
    assert labels[23:32] == ["L"] * 9
    assert labels[32:35] == ["M", "M", "M"]


def test_modified_short_cycle_labels() -> None:
    assert modified_short_cycle_phase_for_day(1, 21) == "M"
    assert modified_short_cycle_phase_for_day(4, 21) == "O"
    assert modified_short_cycle_phase_for_day(9, 21) == "O"
    assert modified_short_cycle_phase_for_day(10, 21) == "L"
    assert modified_short_cycle_phase_for_day(19, 21) == "M"
