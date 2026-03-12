"""Validation smoke tests.

The cohort sizes here are smaller than the full calibration run to keep CI execution practical.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hormone_cycler.validation import run_population_validation


class ValidationTest(unittest.TestCase):
    """Smoke tests for the literature-validation workflow."""

    def test_baseline_population_validation_passes(self) -> None:
        """A moderately sized baseline cohort should satisfy the validation suite."""

        report = run_population_validation(num_patients=800, days=180, seed=7, include_subgroups=False)
        self.assertTrue(report["baseline_passed"])


if __name__ == "__main__":
    unittest.main()
