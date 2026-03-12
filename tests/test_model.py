"""Unit tests for the core simulator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hormone_cycler.model import simulate_diary
from hormone_cycler.types import MedicalFactors


class SimulatorTest(unittest.TestCase):
    """Regression tests for single-patient simulation behavior."""

    def test_simulate_diary_returns_requested_days(self) -> None:
        """The simulator should emit exactly the requested number of diary rows."""

        result = simulate_diary(days=90, age_years=31, seed=2)
        self.assertEqual(len(result.diary), 90)
        self.assertGreaterEqual(len(result.cycles), 3)
        self.assertEqual(result.diary[0].day_index, 1)
        self.assertIn("pcos", result.diary[0].medical_factors)

    def test_cyclic_ocp_suppresses_ovulation(self) -> None:
        """Cyclic OCP mode should eliminate ovulation and preserve withdrawal bleeding."""

        result = simulate_diary(
            days=84,
            age_years=28,
            seed=3,
            medical_factors=MedicalFactors(oral_contraceptive_mode="cyclic"),
        )
        self.assertEqual(sum(row.ovulation for row in result.diary), 0)
        bleed_days = sum(row.uterine_bleeding for row in result.diary)
        self.assertGreaterEqual(bleed_days, 9)
        self.assertLessEqual(bleed_days, 18)

    def test_pcos_shifts_cycle_lengths_upward(self) -> None:
        """PCOS should materially lengthen mean cycle length relative to baseline."""

        baseline = simulate_diary(days=365, age_years=27, seed=10)
        pcos = simulate_diary(days=365, age_years=27, seed=10, medical_factors=MedicalFactors(pcos=True))
        baseline_mean = sum(cycle.cycle_length for cycle in baseline.cycles) / len(baseline.cycles)
        pcos_mean = sum(cycle.cycle_length for cycle in pcos.cycles) / len(pcos.cycles)
        self.assertGreater(pcos_mean, baseline_mean + 2.0)

    def test_conflicting_contraception_modes_raise(self) -> None:
        """Mutually exclusive contraception settings should raise an error."""

        with self.assertRaises(ValueError):
            MedicalFactors(oral_contraceptive_mode="cyclic", copper_iud=True).validate()


if __name__ == "__main__":
    unittest.main()
