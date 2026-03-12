"""Population validation against peer-reviewed menstrual cycle studies."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .hormone_constants import (
    BULL_BLEEDING_VALIDATION_BOUNDS,
    BULL_FOLLICULAR_VALIDATION_BOUNDS,
    BULL_LUTEAL_VALIDATION_BOUNDS,
    COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS,
    COPPER_IUD_VALIDATION_MAX_OVULATION_DELTA,
    CONTINUOUS_OCP_VALIDATION_MAX_BLEEDING_DAYS,
    CONTINUOUS_OCP_VALIDATION_EXPECTED_AMENORRHEA_RATE,
    CONTINUOUS_OCP_VALIDATION_EXPECTED_BLEEDING_DAYS,
    CONTINUOUS_OCP_VALIDATION_MAX_OVULATION_RATE,
    CONTINUOUS_OCP_VALIDATION_MIN_AMENORRHEA_RATE,
    CYCLIC_OCP_VALIDATION_BLEEDING_BOUNDS,
    CYCLIC_OCP_VALIDATION_EXPECTED_BLEEDING_DAYS,
    CYCLIC_OCP_VALIDATION_MAX_OVULATION_RATE,
    DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS,
    DYSMENORRHEA_VALIDATION_MAX_OVULATION_DELTA,
    HORMONAL_IUD_VALIDATION_AMENORRHEA_BOUNDS,
    HORMONAL_IUD_VALIDATION_EXPECTED_AMENORRHEA_RATE,
    HORMONAL_IUD_VALIDATION_EXPECTED_OVULATION_RATE,
    HORMONAL_IUD_VALIDATION_OVULATION_BOUNDS,
    IRREGULARITY_THRESHOLD_DAYS,
    PCOS_VALIDATION_MIN_CYCLE_DELTA_DAYS,
    PCOS_VALIDATION_MIN_IRREGULARITY_DELTA,
    PCOS_VALIDATION_MIN_OVULATION_DELTA,
    PERI_MENARCHE_VALIDATION_MAX_OVULATION,
    PERI_MENARCHE_VALIDATION_EXPECTED_CYCLE_LENGTH,
    PERI_MENARCHE_VALIDATION_EXPECTED_IRREGULARITY,
    PERI_MENARCHE_VALIDATION_EXPECTED_OVULATION_RATE,
    PERI_MENARCHE_VALIDATION_MIN_CYCLE_LENGTH,
    PERI_MENARCHE_VALIDATION_MIN_IRREGULARITY,
    PERIMENOPAUSE_VALIDATION_EXPECTED_IRREGULARITY,
    PERIMENOPAUSE_VALIDATION_EXPECTED_OVULATION_RATE,
    PERIMENOPAUSE_VALIDATION_MIN_IRREGULARITY,
    PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS,
    SUBGROUP_BASELINE_REFERENCE_PATIENTS,
    SUBGROUP_REFERENCE_PATIENTS,
    VALIDATION_CYCLE_MARGIN_BUFFER_DAYS,
    VALIDATION_CYCLE_MARGIN_MIN_DAYS,
    VALIDATION_EARLY_FOLLICULAR_FRACTION,
    VALIDATION_ESTRADIOL_RATIO_BOUNDS,
    VALIDATION_IRREGULARITY_MARGIN_BUFFER,
    VALIDATION_IRREGULARITY_MARGIN_MIN,
    VALIDATION_MID_FOLLICULAR_FRACTION,
    VALIDATION_MID_LUTEAL_END_FRACTION,
    VALIDATION_MID_LUTEAL_START_FRACTION,
    VALIDATION_MIN_EARLY_FOLLICULAR_DAYS,
    VALIDATION_MIN_EARLY_LUTEAL_DAYS,
    VALIDATION_MIN_MID_FOLLICULAR_DAYS,
    VALIDATION_MIN_MID_LUTEAL_START_DAYS,
    VALIDATION_MIN_MID_LUTEAL_END_DAYS,
    VALIDATION_MIN_PROGESTERONE_BOUND,
    VALIDATION_PROGESTERONE_RATIO_BOUNDS,
    VALIDATION_EARLY_LUTEAL_FRACTION,
)
from .literature import AGE_BAND_TARGETS, BULL_PHASE_TARGETS, CITATIONS, HORMONE_ANCHORS, age_band_for
from .population import simulate_population
from .types import MedicalFactors


@dataclass
class ValidationMetric:
    """Container for one literature comparison metric."""

    name: str
    observed: float
    expected: float
    lower_bound: float
    upper_bound: float
    passed: bool
    citation_key: str
    notes: str

    def to_dict(self) -> Dict[str, object]:
        """Serialize the metric and attach the full citation payload."""

        payload = asdict(self)
        payload["citation"] = asdict(CITATIONS[self.citation_key])
        return payload


def mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean of a numeric sequence or NaN for empty input."""

    return sum(values) / len(values) if values else float("nan")


def median(values: Sequence[float]) -> float:
    """Return the median of a numeric sequence or NaN for empty input."""

    if not values:
        return float("nan")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def proportion(values: Iterable[bool]) -> float:
    """Return the fraction of truthy values in an iterable."""

    values = list(values)
    if not values:
        return float("nan")
    return sum(1 for value in values if value) / len(values)


def cycle_irregularity(cycle_lengths: Sequence[int]) -> float:
    """Compute the adjacent-cycle irregularity rate for one patient.

    Purpose:
        Li et al. 2024 define irregularity using adjacent-cycle differences of at least seven
        days. This function applies the same rule to a patient's simulated cycle-length series.

    Args:
        cycle_lengths: Ordered sequence of cycle lengths for one patient.

    Returns:
        Fraction of adjacent cycle pairs whose absolute difference is at least seven days.
    """

    if len(cycle_lengths) < 2:
        return float("nan")
    diffs = [
        abs(right - left) >= IRREGULARITY_THRESHOLD_DAYS
        for left, right in zip(cycle_lengths[:-1], cycle_lengths[1:])
    ]
    return proportion(diffs)


def phase_name(cycle_day: int, cycle: Dict[str, object]) -> Optional[str]:
    """Map a diary day onto the Stricker-style menstrual sub-phase bins.

    Purpose:
        Stricker et al. 2006 report hormone medians by menstrual sub-phase rather than by raw
        day index. This helper converts simulated cycle days into those same bins so observed
        medians can be compared with published values.

    Args:
        cycle_day: One-based day inside the current cycle.
        cycle: Cycle summary dictionary containing phase lengths and ovulation day.

    Returns:
        The sub-phase label or ``None`` if the cycle is not suitable for sub-phase comparison.
    """

    if not cycle["ovulatory"]:
        return None
    follicular_length = int(cycle["follicular_length"])
    luteal_length = int(cycle["luteal_length"])
    ovulation_day = int(cycle["ovulation_day"])
    if follicular_length <= 0 or luteal_length <= 0:
        return None
    if cycle_day <= max(VALIDATION_MIN_EARLY_FOLLICULAR_DAYS, int(round(follicular_length * VALIDATION_EARLY_FOLLICULAR_FRACTION))):
        return "early_follicular"
    if cycle_day <= max(VALIDATION_MIN_MID_FOLLICULAR_DAYS, int(round(follicular_length * VALIDATION_MID_FOLLICULAR_FRACTION))):
        return "mid_follicular"
    if cycle_day < ovulation_day:
        return "pre_ovulatory"
    if cycle_day == ovulation_day:
        return "ovulation"
    luteal_offset = cycle_day - ovulation_day
    if 1 <= luteal_offset <= max(VALIDATION_MIN_EARLY_LUTEAL_DAYS, int(round(luteal_length * VALIDATION_EARLY_LUTEAL_FRACTION))):
        return "early_luteal"
    if max(VALIDATION_MIN_MID_LUTEAL_START_DAYS, int(round(luteal_length * VALIDATION_MID_LUTEAL_START_FRACTION))) <= luteal_offset <= max(
        VALIDATION_MIN_MID_LUTEAL_END_DAYS,
        int(round(luteal_length * VALIDATION_MID_LUTEAL_END_FRACTION)),
    ):
        return "mid_luteal"
    return "late_luteal"


def _age_band_metrics(cycles: Sequence[Dict[str, object]]) -> List[ValidationMetric]:
    """Compare age-stratified cycle statistics with Li et al. 2024 targets."""

    by_band: Dict[str, List[Dict[str, object]]] = {target.label: [] for target in AGE_BAND_TARGETS}
    for cycle in cycles:
        label = age_band_for(float(cycle["age_years"])).label
        by_band[label].append(cycle)

    metrics: List[ValidationMetric] = []
    for target in AGE_BAND_TARGETS:
        band_cycles = by_band[target.label]
        if not band_cycles:
            continue
        cycle_lengths = [int(cycle["cycle_length"]) for cycle in band_cycles]
        mean_cycle = mean(cycle_lengths)
        cycle_margin = max(
            VALIDATION_CYCLE_MARGIN_MIN_DAYS,
            (target.cycle_length_ci[1] - target.cycle_length_ci[0]) / 2.0 + VALIDATION_CYCLE_MARGIN_BUFFER_DAYS,
        )
        cycle_lower = target.mean_cycle_days - cycle_margin
        cycle_upper = target.mean_cycle_days + cycle_margin
        metrics.append(
            ValidationMetric(
                name=f"cycle_mean_{target.label}",
                observed=round(mean_cycle, 3),
                expected=target.mean_cycle_days,
                lower_bound=round(cycle_lower, 3),
                upper_bound=round(cycle_upper, 3),
                passed=cycle_lower <= mean_cycle <= cycle_upper,
                citation_key="li_2024_awhs",
                notes="Age-stratified mean cycle length compared with AWHS / NHS3 targets using an equivalence margin around the published estimate.",
            )
        )

        patient_lengths: Dict[str, List[int]] = {}
        for cycle in band_cycles:
            patient_lengths.setdefault(str(cycle["patient_id"]), []).append(int(cycle["cycle_length"]))
        irregularity_values = [
            cycle_irregularity(lengths)
            for lengths in patient_lengths.values()
            if len(lengths) >= 2 and not math.isnan(cycle_irregularity(lengths))
        ]
        irregularity = mean(irregularity_values)
        irregularity_margin = max(
            VALIDATION_IRREGULARITY_MARGIN_MIN,
            (target.irregularity_ci[1] - target.irregularity_ci[0]) / 2.0 + VALIDATION_IRREGULARITY_MARGIN_BUFFER,
        )
        irregularity_lower = max(0.0, target.irregularity_probability - irregularity_margin)
        irregularity_upper = min(1.0, target.irregularity_probability + irregularity_margin)
        metrics.append(
            ValidationMetric(
                name=f"cycle_irregularity_{target.label}",
                observed=round(irregularity, 4),
                expected=target.irregularity_probability,
                lower_bound=round(irregularity_lower, 4),
                upper_bound=round(irregularity_upper, 4),
                passed=irregularity_lower <= irregularity <= irregularity_upper,
                citation_key="li_2024_awhs",
                notes="Age-stratified probability that adjacent cycles differ by at least 7 days, assessed with a prespecified equivalence margin.",
            )
        )
    return metrics


def _overall_cycle_metrics(cycles: Sequence[Dict[str, object]]) -> List[ValidationMetric]:
    """Compare aggregate phase and bleeding statistics with Bull et al. 2019."""

    ovulatory_cycles = [cycle for cycle in cycles if cycle["ovulatory"]]
    follicular_mean = mean([float(cycle["follicular_length"]) for cycle in ovulatory_cycles])
    luteal_mean = mean([float(cycle["luteal_length"]) for cycle in ovulatory_cycles])
    bleeding_mean = mean([float(cycle["bleeding_days"]) for cycle in cycles])
    return [
        ValidationMetric(
            name="follicular_mean_days",
            observed=round(follicular_mean, 3),
            expected=BULL_PHASE_TARGETS["follicular_mean_days"],
            lower_bound=BULL_FOLLICULAR_VALIDATION_BOUNDS[0],
            upper_bound=BULL_FOLLICULAR_VALIDATION_BOUNDS[1],
            passed=BULL_FOLLICULAR_VALIDATION_BOUNDS[0] <= follicular_mean <= BULL_FOLLICULAR_VALIDATION_BOUNDS[1],
            citation_key="bull_2019_natural_cycles",
            notes="Mean follicular length in ovulatory cycles.",
        ),
        ValidationMetric(
            name="luteal_mean_days",
            observed=round(luteal_mean, 3),
            expected=BULL_PHASE_TARGETS["luteal_mean_days"],
            lower_bound=BULL_LUTEAL_VALIDATION_BOUNDS[0],
            upper_bound=BULL_LUTEAL_VALIDATION_BOUNDS[1],
            passed=BULL_LUTEAL_VALIDATION_BOUNDS[0] <= luteal_mean <= BULL_LUTEAL_VALIDATION_BOUNDS[1],
            citation_key="bull_2019_natural_cycles",
            notes="Mean luteal length in ovulatory cycles.",
        ),
        ValidationMetric(
            name="bleeding_mean_days",
            observed=round(bleeding_mean, 3),
            expected=BULL_PHASE_TARGETS["mean_bleeding_days"],
            lower_bound=BULL_BLEEDING_VALIDATION_BOUNDS[0],
            upper_bound=BULL_BLEEDING_VALIDATION_BOUNDS[1],
            passed=BULL_BLEEDING_VALIDATION_BOUNDS[0] <= bleeding_mean <= BULL_BLEEDING_VALIDATION_BOUNDS[1],
            citation_key="bull_2019_natural_cycles",
            notes="Mean days with bleeding per cycle.",
        ),
    ]


def _hormone_metrics(sample_diaries: Sequence[Dict[str, object]]) -> List[ValidationMetric]:
    """Compare simulated sub-phase hormone medians with Stricker et al. 2006."""

    phase_values: Dict[str, Dict[str, List[float]]] = {
        anchor.name: {"estradiol": [], "progesterone": []} for anchor in HORMONE_ANCHORS
    }

    for diary_payload in sample_diaries:
        cycle_map = {cycle["cycle_index"]: cycle for cycle in diary_payload["cycles"]}
        for row in diary_payload["diary"]:
            cycle = cycle_map[row["cycle_index"]]
            name = phase_name(int(row["cycle_day"]), cycle)
            if not name:
                continue
            phase_values[name]["estradiol"].append(float(row["estradiol_pg_ml"]))
            phase_values[name]["progesterone"].append(float(row["progesterone_ng_ml"]))

    metrics: List[ValidationMetric] = []
    for anchor in HORMONE_ANCHORS:
        estradiol_obs = median(phase_values[anchor.name]["estradiol"])
        progesterone_obs = median(phase_values[anchor.name]["progesterone"])
        metrics.append(
            ValidationMetric(
                name=f"estradiol_{anchor.name}",
                observed=round(estradiol_obs, 3),
                expected=anchor.estradiol_pg_ml,
                lower_bound=anchor.estradiol_pg_ml * VALIDATION_ESTRADIOL_RATIO_BOUNDS[0],
                upper_bound=anchor.estradiol_pg_ml * VALIDATION_ESTRADIOL_RATIO_BOUNDS[1],
                passed=anchor.estradiol_pg_ml * VALIDATION_ESTRADIOL_RATIO_BOUNDS[0] <= estradiol_obs <= anchor.estradiol_pg_ml * VALIDATION_ESTRADIOL_RATIO_BOUNDS[1],
                citation_key="stricker_2006_reference",
                notes="Median estradiol by menstrual sub-phase compared with Stricker et al.",
            )
        )
        metrics.append(
            ValidationMetric(
                name=f"progesterone_{anchor.name}",
                observed=round(progesterone_obs, 3),
                expected=anchor.progesterone_ng_ml,
                lower_bound=max(VALIDATION_MIN_PROGESTERONE_BOUND, anchor.progesterone_ng_ml * VALIDATION_PROGESTERONE_RATIO_BOUNDS[0]),
                upper_bound=anchor.progesterone_ng_ml * VALIDATION_PROGESTERONE_RATIO_BOUNDS[1],
                passed=max(VALIDATION_MIN_PROGESTERONE_BOUND, anchor.progesterone_ng_ml * VALIDATION_PROGESTERONE_RATIO_BOUNDS[0]) <= progesterone_obs <= anchor.progesterone_ng_ml * VALIDATION_PROGESTERONE_RATIO_BOUNDS[1],
                citation_key="stricker_2006_reference",
                notes="Median progesterone by menstrual sub-phase compared with Stricker et al.",
            )
        )
    return metrics


def _summarize_subgroup(population: Dict[str, object], baseline: Optional[Dict[str, float]] = None) -> Dict[str, object]:
    """Reduce a simulated subgroup cohort to headline validation statistics."""

    cycles = population["cycles"]
    cycle_lengths = [int(cycle["cycle_length"]) for cycle in cycles]
    ovulation_rate = proportion(bool(cycle["ovulatory"]) for cycle in cycles)
    bleeding_days = mean([float(cycle["bleeding_days"]) for cycle in cycles])
    irregularity_by_patient: Dict[str, List[int]] = {}
    for cycle in cycles:
        irregularity_by_patient.setdefault(str(cycle["patient_id"]), []).append(int(cycle["cycle_length"]))
    irregularity = mean(
        [
            cycle_irregularity(lengths)
            for lengths in irregularity_by_patient.values()
            if len(lengths) >= 2 and not math.isnan(cycle_irregularity(lengths))
        ]
    )
    amenorrhea = proportion(int(cycle["bleeding_days"]) == 0 for cycle in cycles)
    summary = {
        "mean_cycle_days": round(mean(cycle_lengths), 3),
        "ovulation_rate": round(ovulation_rate, 3),
        "mean_bleeding_days": round(bleeding_days, 3),
        "irregularity_rate": round(irregularity, 3),
        "amenorrhea_rate": round(amenorrhea, 3),
    }
    if baseline:
        summary["delta_vs_baseline"] = {
            key: round(summary[key] - baseline[key], 3)
            for key in baseline
            if key in summary
        }
    return summary


def _subgroup_analysis(seed: int, days: int) -> Dict[str, object]:
    """Run factor-specific validation checks after the baseline cohort passes.

    Args:
        seed: Base random seed used to derive subgroup-specific seeds.
        days: Diary length in days for each subgroup member.

    Returns:
        A dictionary containing the baseline reference subgroup and one entry per medical factor.
    """

    baseline_population = simulate_population(
        num_patients=SUBGROUP_BASELINE_REFERENCE_PATIENTS,
        days=days,
        seed=seed + 100,
        medical_factors=MedicalFactors(),
        include_diaries=False,
    )
    baseline_summary = _summarize_subgroup(baseline_population)

    subgroup_definitions = {
        "pcos": MedicalFactors(pcos=True),
        "cyclic_ocp": MedicalFactors(oral_contraceptive_mode="cyclic"),
        "continuous_ocp": MedicalFactors(oral_contraceptive_mode="continuous"),
        "hormonal_iud": MedicalFactors(hormonal_iud=True),
        "copper_iud": MedicalFactors(copper_iud=True),
        "perimenopause": MedicalFactors(perimenopause=True),
        "peri_menarche": MedicalFactors(peri_menarche=True),
        "dysmenorrhea": MedicalFactors(dysmenorrhea=True),
    }

    results: Dict[str, object] = {"baseline_reference": baseline_summary, "subgroups": {}}
    for index, (name, factors) in enumerate(subgroup_definitions.items(), start=1):
        population = simulate_population(
            num_patients=SUBGROUP_REFERENCE_PATIENTS,
            days=days,
            seed=seed + 1000 + index,
            medical_factors=factors,
            include_diaries=False,
        )
        summary = _summarize_subgroup(population, baseline=baseline_summary)
        checks: List[ValidationMetric] = []

        if name == "pcos":
            checks.extend(
                [
                    ValidationMetric("pcos_longer_cycles", summary["mean_cycle_days"], baseline_summary["mean_cycle_days"] + PCOS_VALIDATION_MIN_CYCLE_DELTA_DAYS, baseline_summary["mean_cycle_days"] + PCOS_VALIDATION_MIN_CYCLE_DELTA_DAYS, 999.0, summary["mean_cycle_days"] >= baseline_summary["mean_cycle_days"] + PCOS_VALIDATION_MIN_CYCLE_DELTA_DAYS, "mortimer_2025_pcos", "PCOS should shift mean cycle length upward versus baseline."),
                    ValidationMetric("pcos_higher_irregularity", summary["irregularity_rate"], baseline_summary["irregularity_rate"] + PCOS_VALIDATION_MIN_IRREGULARITY_DELTA, baseline_summary["irregularity_rate"] + PCOS_VALIDATION_MIN_IRREGULARITY_DELTA, 1.0, summary["irregularity_rate"] >= baseline_summary["irregularity_rate"] + PCOS_VALIDATION_MIN_IRREGULARITY_DELTA, "mortimer_2025_pcos", "PCOS should increase cycle irregularity."),
                    ValidationMetric("pcos_lower_ovulation", summary["ovulation_rate"], baseline_summary["ovulation_rate"] - PCOS_VALIDATION_MIN_OVULATION_DELTA, 0.0, baseline_summary["ovulation_rate"] - PCOS_VALIDATION_MIN_OVULATION_DELTA, summary["ovulation_rate"] <= baseline_summary["ovulation_rate"] - PCOS_VALIDATION_MIN_OVULATION_DELTA, "doi_2005_pcos_hormones", "PCOS should reduce ovulation frequency."),
                ]
            )
        elif name == "cyclic_ocp":
            checks.extend(
                [
                    ValidationMetric("cyclic_ocp_ovulation_suppression", summary["ovulation_rate"], 0.0, 0.0, CYCLIC_OCP_VALIDATION_MAX_OVULATION_RATE, summary["ovulation_rate"] <= CYCLIC_OCP_VALIDATION_MAX_OVULATION_RATE, "edelman_2014_ocp", "21/7 combined OCPs should suppress ovulation."),
                    ValidationMetric("cyclic_ocp_withdrawal_bleeding", summary["mean_bleeding_days"], CYCLIC_OCP_VALIDATION_EXPECTED_BLEEDING_DAYS, CYCLIC_OCP_VALIDATION_BLEEDING_BOUNDS[0], CYCLIC_OCP_VALIDATION_BLEEDING_BOUNDS[1], CYCLIC_OCP_VALIDATION_BLEEDING_BOUNDS[0] <= summary["mean_bleeding_days"] <= CYCLIC_OCP_VALIDATION_BLEEDING_BOUNDS[1], "edelman_2014_ocp", "21/7 regimens should preserve scheduled withdrawal bleeding."),
                ]
            )
        elif name == "continuous_ocp":
            checks.extend(
                [
                    ValidationMetric("continuous_ocp_ovulation_suppression", summary["ovulation_rate"], 0.0, 0.0, CONTINUOUS_OCP_VALIDATION_MAX_OVULATION_RATE, summary["ovulation_rate"] <= CONTINUOUS_OCP_VALIDATION_MAX_OVULATION_RATE, "edelman_2014_ocp", "Continuous combined OCPs should suppress ovulation."),
                    ValidationMetric("continuous_ocp_low_bleeding", summary["mean_bleeding_days"], CONTINUOUS_OCP_VALIDATION_EXPECTED_BLEEDING_DAYS, 0.0, CONTINUOUS_OCP_VALIDATION_MAX_BLEEDING_DAYS, summary["mean_bleeding_days"] <= CONTINUOUS_OCP_VALIDATION_MAX_BLEEDING_DAYS, "edelman_2014_ocp", "Continuous use should reduce bleeding days relative to cyclic use."),
                    ValidationMetric("continuous_ocp_amenorrhea", summary["amenorrhea_rate"], CONTINUOUS_OCP_VALIDATION_EXPECTED_AMENORRHEA_RATE, CONTINUOUS_OCP_VALIDATION_MIN_AMENORRHEA_RATE, 0.90, summary["amenorrhea_rate"] >= CONTINUOUS_OCP_VALIDATION_MIN_AMENORRHEA_RATE, "edelman_2014_ocp", "Continuous use should produce substantial amenorrhea/infrequent bleeding."),
                ]
            )
        elif name == "hormonal_iud":
            checks.extend(
                [
                    ValidationMetric("hormonal_iud_preserved_ovulation", summary["ovulation_rate"], HORMONAL_IUD_VALIDATION_EXPECTED_OVULATION_RATE, HORMONAL_IUD_VALIDATION_OVULATION_BOUNDS[0], HORMONAL_IUD_VALIDATION_OVULATION_BOUNDS[1], HORMONAL_IUD_VALIDATION_OVULATION_BOUNDS[0] <= summary["ovulation_rate"] <= HORMONAL_IUD_VALIDATION_OVULATION_BOUNDS[1], "xiao_1995_lng_iud", "Long-term LNG-IUD users should remain ovulatory in most cycles."),
                    ValidationMetric("hormonal_iud_amenorrhea", summary["amenorrhea_rate"], HORMONAL_IUD_VALIDATION_EXPECTED_AMENORRHEA_RATE, HORMONAL_IUD_VALIDATION_AMENORRHEA_BOUNDS[0], HORMONAL_IUD_VALIDATION_AMENORRHEA_BOUNDS[1], HORMONAL_IUD_VALIDATION_AMENORRHEA_BOUNDS[0] <= summary["amenorrhea_rate"] <= HORMONAL_IUD_VALIDATION_AMENORRHEA_BOUNDS[1], "xiao_1995_lng_iud", "Amenorrhea should occur in a minority but not rare fraction of LNG-IUD cycles."),
                ]
            )
        elif name == "copper_iud":
            checks.extend(
                [
                    ValidationMetric("copper_iud_ovulation_preserved", summary["ovulation_rate"], baseline_summary["ovulation_rate"], baseline_summary["ovulation_rate"] - COPPER_IUD_VALIDATION_MAX_OVULATION_DELTA, baseline_summary["ovulation_rate"] + COPPER_IUD_VALIDATION_MAX_OVULATION_DELTA, abs(summary["ovulation_rate"] - baseline_summary["ovulation_rate"]) <= COPPER_IUD_VALIDATION_MAX_OVULATION_DELTA, "hubacher_2009_copper_iud", "Copper IUDs should not materially suppress ovulation."),
                    ValidationMetric("copper_iud_bleeding_increase", summary["mean_bleeding_days"], baseline_summary["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[0], baseline_summary["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[0], baseline_summary["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[1], baseline_summary["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[0] <= summary["mean_bleeding_days"] <= baseline_summary["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[1], "hubacher_2009_copper_iud", "Copper IUDs should increase bleeding duration."),
                ]
            )
        elif name == "perimenopause":
            checks.extend(
                [
                    ValidationMetric("perimenopause_irregularity", summary["irregularity_rate"], PERIMENOPAUSE_VALIDATION_EXPECTED_IRREGULARITY, PERIMENOPAUSE_VALIDATION_MIN_IRREGULARITY, 1.00, summary["irregularity_rate"] >= PERIMENOPAUSE_VALIDATION_MIN_IRREGULARITY, "santoro_2008_perimenopause", "Perimenopause should increase cycle irregularity."),
                    ValidationMetric("perimenopause_lower_ovulation", summary["ovulation_rate"], PERIMENOPAUSE_VALIDATION_EXPECTED_OVULATION_RATE, PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS[0], PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS[1], PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS[0] <= summary["ovulation_rate"] <= PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS[1], "santoro_2008_perimenopause", "Perimenopause should reduce ovulation frequency."),
                ]
            )
        elif name == "peri_menarche":
            checks.extend(
                [
                    ValidationMetric("peri_menarche_long_cycles", summary["mean_cycle_days"], PERI_MENARCHE_VALIDATION_EXPECTED_CYCLE_LENGTH, PERI_MENARCHE_VALIDATION_MIN_CYCLE_LENGTH, 40.0, summary["mean_cycle_days"] >= PERI_MENARCHE_VALIDATION_MIN_CYCLE_LENGTH, "venturoli_1987_menarche", "Peri-menarche cycles should be longer on average."),
                    ValidationMetric("peri_menarche_irregularity", summary["irregularity_rate"], PERI_MENARCHE_VALIDATION_EXPECTED_IRREGULARITY, PERI_MENARCHE_VALIDATION_MIN_IRREGULARITY, 1.00, summary["irregularity_rate"] >= PERI_MENARCHE_VALIDATION_MIN_IRREGULARITY, "venturoli_1987_menarche", "Peri-menarche cycles should be more irregular."),
                    ValidationMetric("peri_menarche_lower_ovulation", summary["ovulation_rate"], PERI_MENARCHE_VALIDATION_EXPECTED_OVULATION_RATE, 0.30, PERI_MENARCHE_VALIDATION_MAX_OVULATION, summary["ovulation_rate"] <= PERI_MENARCHE_VALIDATION_MAX_OVULATION, "venturoli_1987_menarche", "Peri-menarche cycles should be frequently anovulatory."),
                ]
            )
        elif name == "dysmenorrhea":
            checks.extend(
                [
                    ValidationMetric("dysmenorrhea_preserved_ovulation", summary["ovulation_rate"], baseline_summary["ovulation_rate"], baseline_summary["ovulation_rate"] - DYSMENORRHEA_VALIDATION_MAX_OVULATION_DELTA, baseline_summary["ovulation_rate"] + DYSMENORRHEA_VALIDATION_MAX_OVULATION_DELTA, abs(summary["ovulation_rate"] - baseline_summary["ovulation_rate"]) <= DYSMENORRHEA_VALIDATION_MAX_OVULATION_DELTA, "dawood_2006_dysmenorrhea", "Primary dysmenorrhea should remain mostly ovulatory."),
                    ValidationMetric("dysmenorrhea_bleeding_shift", summary["mean_bleeding_days"], baseline_summary["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[0], baseline_summary["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[0], baseline_summary["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[1], baseline_summary["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[0] <= summary["mean_bleeding_days"] <= baseline_summary["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[1], "dawood_2006_dysmenorrhea", "Dysmenorrhea should mildly lengthen bleeding rather than strongly alter steroids."),
                ]
            )

        results["subgroups"][name] = {
            "summary": summary,
            "checks": [metric.to_dict() for metric in checks],
            "passed": all(metric.passed for metric in checks),
        }
    return results


def run_population_validation(
    num_patients: int = 10_000,
    days: int = 365,
    seed: int = 7,
    include_subgroups: bool = True,
) -> Dict[str, object]:
    """Run the full population validation workflow and optional subgroup checks.

    Args:
        num_patients: Number of women in the baseline validation cohort.
        days: Diary length in days for each simulated patient.
        seed: Random seed for reproducibility.
        include_subgroups: Whether to run factor-specific subgroup validation after the baseline
            cohort passes.

    Returns:
        A validation report dictionary containing baseline metrics, citations, and optional
        subgroup summaries.
    """

    population = simulate_population(
        num_patients=num_patients,
        days=days,
        seed=seed,
        medical_factors=MedicalFactors(),
        balanced_age_bands=True,
        include_diaries=True,
        capture_limit=16,
    )
    cycles = population["cycles"]
    metrics = _age_band_metrics(cycles) + _overall_cycle_metrics(cycles) + _hormone_metrics(population["sample_diaries"])
    baseline_passed = all(metric.passed for metric in metrics)
    report: Dict[str, object] = {
        "input": {
            "num_patients": num_patients,
            "days": days,
            "seed": seed,
        },
        "baseline_passed": baseline_passed,
        "baseline_metrics": [metric.to_dict() for metric in metrics],
        "citations": {key: asdict(value) for key, value in CITATIONS.items()},
    }
    if baseline_passed and include_subgroups:
        report["subgroup_analysis"] = _subgroup_analysis(seed=seed, days=days)
    return report


def write_validation_report(payload: Dict[str, object], output_path: Path) -> None:
    """Write a validation report dictionary to disk as JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
