"""Validation smoke tests.

The cohort sizes here are smaller than the full calibration run to keep CI execution practical.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hormone_cycler.population import simulate_population
from hormone_cycler.types import MedicalFactors
from hormone_cycler.validation import (
    _summarize_subgroup,
    cycle_irregularity,
    run_population_validation,
)


class ValidationTest(unittest.TestCase):
    """Smoke tests for the literature-validation workflow."""

    def test_baseline_population_validation_passes(self) -> None:
        """The declared 10,000-adult cohort should satisfy every primary gate."""

        report = run_population_validation(
            num_patients=10_000,
            days=365,
            seed=7,
            include_subgroups=False,
        )
        self.assertTrue(report["baseline_passed"])
        self.assertTrue(report["calibration_passed"])
        self.assertTrue(report["external_crosscheck_passed"])
        self.assertTrue(report["waveform_validation_passed"])
        self.assertEqual(report["simulator_version"], "0.4.0")
        self.assertEqual(report["validation_schema_version"], 14)
        self.assertEqual(report["hormone_smoke_sample"]["n_diaries"], 160)
        self.assertGreater(
            report["waveform_diagnostics"]["n_complete_ovulatory_cycles"],
            1_000,
        )

    def test_waveform_gate_uses_independent_amplitude_and_daily_shape_checks(self) -> None:
        """The hormone pass should cover both external subphases and daily morphology."""

        report = run_population_validation(
            num_patients=2_000,
            days=365,
            seed=7,
            include_subgroups=False,
        )
        metrics = {
            metric["name"]: metric
            for metric in report["calibration_metrics"]
            if metric["name"].startswith(("estradiol_", "progesterone_"))
        }
        required = {
            "estradiol_stricker_mapped_reference_coverage",
            "estradiol_stricker_follicular_area_ratio",
            "estradiol_early_follicular",
            "estradiol_peak_offset_sd_days",
            "estradiol_luteal_secondary_peak_ratio",
            "estradiol_luteal_secondary_peak_ratio_sd",
            "progesterone_early_luteal",
            "progesterone_plateau_width_days",
            "progesterone_peak_offset_from_ovulation_days",
            "progesterone_peak_offset_sd_days",
            "progesterone_luteal_length_peak_offset_correlation",
            "progesterone_rise_to_5ng_offset_days",
            "progesterone_premenstrual_withdrawal_days",
            "progesterone_penultimate_to_terminal_drop_ng_ml",
            "progesterone_cross_cycle_jump_ng_ml",
        }
        self.assertTrue(required.issubset(metrics))
        self.assertTrue(all(metrics[name]["passed"] for name in required))
        self.assertEqual(
            metrics["progesterone_early_luteal"]["citation_key"],
            "anckaert_2021_hormones",
        )
        self.assertEqual(
            metrics["progesterone_plateau_width_days"]["citation_key"],
            "stricker_2006_reference",
        )
        self.assertEqual(
            metrics["estradiol_peak_offset_sd_days"]["citation_key"],
            "roos_2015_true_ovulation",
        )
        requirement_names = {
            item["requirement"] for item in report["additional_validation_requirements"]
        }
        self.assertIn(
            "Perimenopausal long intervals enriched for anovulation",
            requirement_names,
        )

    def test_irregularity_uses_participant_mean_absolute_difference(self) -> None:
        """The AWHS estimand is a participant statistic, not a pairwise exceedance rate."""

        self.assertEqual(cycle_irregularity([28, 35, 28]), 7.0)
        self.assertEqual(cycle_irregularity([28, 36, 28, 36]), 8.0)

    def test_perimenopause_long_cycles_are_more_often_anovulatory(self) -> None:
        """The joint-dependence check must not pass from high background anovulation alone."""

        population = simulate_population(
            num_patients=1_200,
            days=365,
            seed=1_013,
            medical_factors=MedicalFactors(perimenopause=True),
            balanced_age_bands=False,
            include_diaries=False,
            age_range=(45.0, 55.0),
        )
        summary = _summarize_subgroup(population)
        self.assertGreaterEqual(summary["long_vs_ordinary_anovulation_delta"], 0.05)
        self.assertGreater(summary["long_vs_ordinary_anovulation_odds_ratio"], 1.0)

    def test_baseline_population_age_range_can_match_adult_source_cohort(self) -> None:
        """The AWHS <20 band must sample adults, not peri-menarche adolescents."""

        population = simulate_population(
            num_patients=16,
            days=60,
            seed=11,
            include_diaries=False,
            age_range=(18.0, 55.0),
        )
        ages = [float(profile["age_years"]) for profile in population["profiles"]]
        self.assertGreaterEqual(min(ages), 18.0)
        self.assertLess(max(ages), 55.0)

    def test_population_compact_path_matches_full_profiles_and_cycles(self) -> None:
        """Validation acceleration must not change any scientific population output."""

        compact = simulate_population(
            num_patients=16,
            days=120,
            seed=29,
            include_diaries=True,
            capture_limit=4,
            age_range=(18.0, 55.0),
            compact_non_capture=True,
        )
        full = simulate_population(
            num_patients=16,
            days=120,
            seed=29,
            include_diaries=True,
            capture_limit=4,
            age_range=(18.0, 55.0),
            compact_non_capture=False,
        )
        self.assertEqual(compact["profiles"], full["profiles"])
        self.assertEqual(compact["cycles"], full["cycles"])
        self.assertEqual(compact["sample_diaries"], full["sample_diaries"])


if __name__ == "__main__":
    unittest.main()
