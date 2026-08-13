"""Unit tests for the core simulator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hormone_cycler.model import (
    LONG_ESTRADIOL_DELAYED_EMERGENCE,
    LONG_ESTRADIOL_FAILED_WAVE,
    bounded_shifted_lognormal,
    build_patient_profile,
    domain_separated_rng,
    long_follicular_estradiol_variant,
    ovulatory_hormone_points,
    render_cycle,
    render_cycle_compact,
    shape_preserving_curve,
    simulate_diary,
)
from hormone_cycler.visualization import render_svg
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

    def test_profile_records_calibrated_variability_component(self) -> None:
        """Healthy profiles should expose the fitted low/high variability component."""

        profile = build_patient_profile(age_years=32, seed=2)
        self.assertIn(profile.cycle_variability_component, {"low", "high"})
        self.assertGreater(profile.personal_cycle_sigma_days, 0.0)

    def test_compact_cycle_path_is_rng_and_structure_equivalent(self) -> None:
        """The large-run fast path must not change simulated cycle structure."""

        profile = build_patient_profile(age_years=32, seed=73, patient_id="compact-equivalence")
        full_rng = domain_separated_rng(73, patient_id=profile.patient_id, stream="cycles")
        compact_rng = domain_separated_rng(73, patient_id=profile.patient_id, stream="cycles")
        for cycle_index in range(1, 7):
            records, full_summary = render_cycle(profile, cycle_index, full_rng)
            compact_summary, progesterone = render_cycle_compact(profile, cycle_index, compact_rng)
            self.assertEqual(full_summary, compact_summary)
            self.assertEqual(
                [record.progesterone_ng_ml for record in records],
                progesterone,
            )
        self.assertEqual(full_rng.random(), compact_rng.random())

    def test_waveform_update_preserves_fixed_seed_upstream_cycle_structure(self) -> None:
        """Waveform-only changes must not alter the protected cycle/event calibration."""

        cases = {
            "healthy-regular-age31": (
                31.0,
                4,
                [
                    (29, 15, 14, 15, True, 4),
                    (31, 16, 15, 16, True, 5),
                    (29, 19, 10, 19, True, 7),
                    (29, 18, 11, 18, True, 2),
                    (29, 13, 16, 13, True, 3),
                    (29, 17, 12, 17, True, 6),
                    (29, 18, 11, 18, True, 3),
                ],
            ),
            "healthy-variable-age31": (
                31.0,
                6,
                [
                    (27, 16, 11, 16, True, 3),
                    (33, 20, 13, 20, True, 5),
                    (25, 16, 9, 16, True, 6),
                    (33, 18, 15, 18, True, 4),
                    (22, 9, 13, 9, True, 4),
                    (28, 14, 14, 14, True, 5),
                    (28, 17, 11, 17, True, 5),
                ],
            ),
            "healthy-later-age52": (
                52.0,
                17,
                [
                    (26, 10, 16, 10, True, 3),
                    (27, 11, 16, 11, True, 5),
                    (28, 15, 13, 15, True, 5),
                    (53, 39, 14, 39, True, 4),
                    (26, 10, 16, 10, True, 4),
                    (27, 16, 11, 16, True, 4),
                    (27, 14, 13, 14, True, 5),
                ],
            ),
        }
        for patient_id, (age, seed, expected) in cases.items():
            with self.subTest(patient_id=patient_id):
                result = simulate_diary(
                    days=220,
                    age_years=age,
                    seed=seed,
                    patient_id=patient_id,
                    start_mode="cycle_day_1",
                )
                observed = [
                    (
                        cycle.cycle_length,
                        cycle.follicular_length,
                        cycle.luteal_length,
                        cycle.ovulation_day,
                        cycle.ovulatory,
                        cycle.bleeding_days,
                    )
                    for cycle in result.cycles[:7]
                ]
                self.assertEqual(observed, expected)

    def test_shifted_lognormal_has_a_longer_right_tail(self) -> None:
        """Cycle-length sampling should preserve the published right-skewed tail."""

        import random

        rng = random.Random(19)
        values = [bounded_shifted_lognormal(rng, 29.0, 5.0) for _ in range(20_000)]
        self.assertGreater(sum(value > 38 for value in values), sum(value < 20 for value in values))

    def test_random_start_is_default_and_reproducible(self) -> None:
        """The default should choose a reproducible phase within the first cycle."""

        first = simulate_diary(days=90, age_years=31, seed=2, patient_id="random-start")
        second = simulate_diary(days=90, age_years=31, seed=2, patient_id="random-start")
        self.assertEqual(first.diary[0].cycle_day, second.diary[0].cycle_day)
        self.assertNotEqual(first.diary[0].cycle_day, 1)
        self.assertEqual(
            [row.cycle_day for row in first.diary],
            [row.cycle_day for row in second.diary],
        )

    def test_cycle_day_1_start_remains_available(self) -> None:
        """An explicit option should retain the original cycle-day-1 boundary."""

        result = simulate_diary(
            days=90,
            age_years=31,
            seed=2,
            patient_id="fixed-start",
            start_mode="cycle_day_1",
        )
        self.assertEqual(result.diary[0].cycle_day, 1)
        self.assertEqual(result.diary[0].day_index, 1)

    def test_random_start_continues_forward_without_wrapping(self) -> None:
        """A random start should continue to the next generated cycle in order."""

        result = simulate_diary(days=90, age_years=31, seed=2, patient_id="random-start")
        first_cycle = [row for row in result.diary if row.cycle_index == 1]
        self.assertEqual(
            [row.cycle_day for row in first_cycle],
            list(range(first_cycle[0].cycle_day, first_cycle[0].cycle_length + 1)),
        )
        next_row = result.diary[len(first_cycle)]
        self.assertEqual(next_row.cycle_index, 2)
        self.assertEqual(next_row.cycle_day, 1)

    def test_invalid_start_mode_raises(self) -> None:
        """Unsupported observation-boundary rules should fail clearly."""

        with self.assertRaises(ValueError):
            simulate_diary(days=30, age_years=31, seed=2, start_mode="phase_shift")

    def test_ovulatory_cycles_withdraw_progesterone_before_bleeding(self) -> None:
        """Complete ovulatory cycles should taper progesterone rather than reset vertically."""

        result = simulate_diary(
            days=180,
            age_years=31,
            seed=1,
            patient_id="kinetic-check",
            start_mode="cycle_day_1",
        )
        first_cycle = result.cycles[0]
        first_rows = [row for row in result.diary if row.cycle_index == first_cycle.cycle_index]
        second_rows = [row for row in result.diary if row.cycle_index == first_cycle.cycle_index + 1]

        self.assertTrue(first_cycle.ovulatory)
        self.assertLessEqual(first_cycle.luteal_length, 17)
        terminal_progesterone = [row.progesterone_ng_ml for row in first_rows[-4:]]
        self.assertTrue(
            all(later < earlier for earlier, later in zip(terminal_progesterone, terminal_progesterone[1:]))
        )
        self.assertLess(terminal_progesterone[-1], max(row.progesterone_ng_ml for row in first_rows) * 0.20)
        self.assertLess(
            abs(second_rows[0].progesterone_ng_ml - terminal_progesterone[-1]),
            1.0,
        )

    def test_progesterone_has_broad_postovulatory_summit(self) -> None:
        """Daily-series calibration should replace the one-day P4 spike with a broad summit."""

        result = simulate_diary(
            days=180,
            age_years=31,
            seed=1,
            patient_id="progesterone-morphology-check",
            start_mode="cycle_day_1",
        )
        cycle = next(cycle for cycle in result.cycles if cycle.ovulatory)
        rows = [row for row in result.diary if row.cycle_index == cycle.cycle_index]
        progesterone = [row.progesterone_ng_ml for row in rows]
        peak = max(progesterone)
        peak_day = progesterone.index(peak) + 1
        plateau_days = sum(value >= 0.75 * peak for value in progesterone)
        rise_day = next(
            day
            for day, value in enumerate(progesterone, start=1)
            if day >= cycle.ovulation_day and value >= 5.0
        )
        self.assertGreaterEqual(plateau_days, 4)
        self.assertLessEqual(plateau_days, 9)
        self.assertGreaterEqual(peak_day - cycle.ovulation_day, 3)
        self.assertLessEqual(peak_day - cycle.ovulation_day, 9)
        self.assertGreaterEqual(rise_day - cycle.ovulation_day, 1)
        self.assertLessEqual(rise_day - cycle.ovulation_day, 4)

    def test_luteal_estradiol_has_secondary_peak(self) -> None:
        """The Stricker daily envelope should retain the mid-luteal E2 rebound."""

        result = simulate_diary(
            days=180,
            age_years=31,
            seed=1,
            patient_id="estradiol-secondary-peak-check",
            start_mode="cycle_day_1",
        )
        cycle = next(cycle for cycle in result.cycles if cycle.ovulatory)
        rows = [row for row in result.diary if row.cycle_index == cycle.cycle_index]
        luteal = rows[cycle.ovulation_day :]
        early_luteal = luteal[:3]
        mid_luteal = luteal[3:9]
        self.assertGreater(
            max(row.estradiol_pg_ml for row in mid_luteal),
            min(row.estradiol_pg_ml for row in early_luteal),
        )

    def test_long_follicular_e2_is_not_horizontally_stretched(self) -> None:
        """Extra long-cycle days should precede a normal-length terminal E2 maturation."""

        for variant in (LONG_ESTRADIOL_DELAYED_EMERGENCE, LONG_ESTRADIOL_FAILED_WAVE):
            with self.subTest(variant=variant):
                estradiol_points, _ = ovulatory_hormone_points(
                    cycle_length=53,
                    follicular_length=39,
                    luteal_length=14,
                    estradiol_scale=1.0,
                    progesterone_scale=1.0,
                    estradiol_variant=variant,
                )
                curve = shape_preserving_curve(estradiol_points)
                values = [curve(float(day)) for day in range(1, 40)]
                peak = max(values)
                half_peak_days = [
                    day for day, value in enumerate(values, start=1) if value >= 0.5 * peak
                ]
                self.assertLessEqual(39 - half_peak_days[-1], 2)
                terminal_crossings = [day for day in half_peak_days if day >= 25]
                self.assertLessEqual(39 - terminal_crossings[0], 14)
                if variant == LONG_ESTRADIOL_FAILED_WAVE:
                    self.assertGreater(max(values[3:22]), values[22])

    def test_long_follicular_variant_selection_is_rng_free_and_reproducible(self) -> None:
        """Long-E2 heterogeneity should not consume or depend on the cycle random stream."""

        profile = build_patient_profile(age_years=52, seed=17, patient_id="variant-check")
        first = long_follicular_estradiol_variant(profile, 4)
        second = long_follicular_estradiol_variant(profile, 4)
        self.assertEqual(first, second)
        self.assertIn(first, {LONG_ESTRADIOL_DELAYED_EMERGENCE, LONG_ESTRADIOL_FAILED_WAVE})

    def test_preovulatory_estradiol_peak_spans_multiple_days(self) -> None:
        """The preovulatory estradiol maximum should not collapse into a one-day needle."""

        result = simulate_diary(
            days=180,
            age_years=31,
            seed=1,
            patient_id="estradiol-width-check",
            start_mode="cycle_day_1",
        )
        cycle = next(cycle for cycle in result.cycles if cycle.ovulatory)
        rows = [row for row in result.diary if row.cycle_index == cycle.cycle_index]
        follicular = rows[: cycle.ovulation_day]
        peak = max(row.estradiol_pg_ml for row in follicular)
        peak_width = sum(row.estradiol_pg_ml >= 0.80 * peak for row in follicular)
        self.assertGreaterEqual(peak_width, 2)

    def test_svg_uses_separate_hormone_scales(self) -> None:
        """The diagnostic plot should not compare different hormone units on one scale."""

        result = simulate_diary(days=60, age_years=31, seed=1, start_mode="cycle_day_1")
        svg = render_svg(result.diary, title="Kinetic validation")
        self.assertIn("Estradiol (pg/mL)", svg)
        self.assertIn("Progesterone (ng/mL)", svg)
        self.assertIn("Separate physiological scales", svg)

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
