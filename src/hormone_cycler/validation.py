"""Population validation against peer-reviewed menstrual cycle studies."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .hormone_constants import (
    ANCKAERT_ESTRADIOL_RATIO_BOUNDS,
    ANCKAERT_LOW_PROGESTERONE_BOUNDS_NG_ML,
    ANCKAERT_OVULATION_PROGESTERONE_BOUNDS_NG_ML,
    ANCKAERT_PROGESTERONE_RATIO_BOUNDS,
    BULL_BLEEDING_SD_VALIDATION_BOUNDS,
    BULL_BLEEDING_VALIDATION_BOUNDS,
    BULL_FOLLICULAR_VALIDATION_BOUNDS,
    BULL_LUTEAL_VALIDATION_BOUNDS,
    BULL_LUTEAL_SD_VALIDATION_BOUNDS,
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
    EXTERNAL_MEAN_CYCLE_MARGIN_DAYS,
    EXTERNAL_MEAN_CYCLE_MARGIN_51_PLUS_DAYS,
    EXTERNAL_MEAN_PERSONAL_SD_MARGIN_51_PLUS_DAYS,
    EXTERNAL_MEAN_PERSONAL_SD_MARGIN_DAYS,
    HORMONAL_IUD_VALIDATION_AMENORRHEA_BOUNDS,
    HORMONAL_IUD_VALIDATION_EXPECTED_AMENORRHEA_RATE,
    HORMONAL_IUD_VALIDATION_EXPECTED_OVULATION_RATE,
    HORMONAL_IUD_VALIDATION_OVULATION_BOUNDS,
    IRREGULARITY_THRESHOLD_DAYS,
    MENOPAUSE_TRANSITION_LONG_CYCLE_ANOVULATORY_TARGET,
    MENOPAUSE_TRANSITION_LONG_CYCLE_THRESHOLD_DAYS,
    MENOPAUSE_TRANSITION_ORDINARY_CYCLE_ANOVULATORY_TARGET,
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
    PERIMENOPAUSE_LONG_CYCLE_ANOVULATORY_BOUNDS,
    PERIMENOPAUSE_LONG_VS_ORDINARY_ANOVULATION_DELTA_BOUNDS,
    PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS,
    SUBGROUP_BASELINE_REFERENCE_PATIENTS,
    SUBGROUP_REFERENCE_PATIENTS,
    VALIDATION_CYCLE_MARGIN_MIN_DAYS,
    VALIDATION_CYCLE_TAIL_MARGIN,
    VALIDATION_CYCLE_TAIL_MARGIN_50_PLUS,
    VALIDATION_CYCLES_PER_PARTICIPANT,
    VALIDATION_EARLY_FOLLICULAR_FRACTION,
    VALIDATION_ESTRADIOL_PEAK_OFFSET_BOUNDS,
    VALIDATION_ESTRADIOL_PEAK_OFFSET_SD_BOUNDS,
    VALIDATION_ESTRADIOL_PEAK_WIDTH_DAYS_BOUNDS,
    VALIDATION_ESTRADIOL_PEAK_WIDTH_FRACTION,
    VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_BOUNDS,
    VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_SD_BOUNDS,
    VALIDATION_IRREGULARITY_MARGIN,
    VALIDATION_MID_FOLLICULAR_FRACTION,
    VALIDATION_MID_LUTEAL_END_FRACTION,
    VALIDATION_MID_LUTEAL_START_FRACTION,
    VALIDATION_MIN_EARLY_FOLLICULAR_DAYS,
    VALIDATION_MIN_EARLY_LUTEAL_DAYS,
    VALIDATION_MIN_MID_FOLLICULAR_DAYS,
    VALIDATION_MIN_MID_LUTEAL_START_DAYS,
    VALIDATION_MIN_MID_LUTEAL_END_DAYS,
    VALIDATION_MIN_PROGESTERONE_BOUND,
    VALIDATION_LUTEAL_LENGTH_P4_PEAK_CORRELATION_ABS_MAX,
    VALIDATION_PROGESTERONE_PENULTIMATE_DROP_MAX_NG_ML,
    VALIDATION_PROGESTERONE_PEAK_OFFSET_BOUNDS,
    VALIDATION_PROGESTERONE_PEAK_OFFSET_SD_BOUNDS,
    VALIDATION_PROGESTERONE_PLATEAU_DAYS_BOUNDS,
    VALIDATION_PROGESTERONE_PLATEAU_FRACTION,
    VALIDATION_PROGESTERONE_RISE_OFFSET_BOUNDS,
    VALIDATION_PROGESTERONE_TERMINAL_TO_PEAK_BOUNDS,
    VALIDATION_PROGESTERONE_WITHDRAWAL_MIN_DAYS,
    VALIDATION_CROSS_CYCLE_PROGESTERONE_JUMP_MAX_NG_ML,
    VALIDATION_EARLY_LUTEAL_FRACTION,
    VALIDATION_STRICKER_FOLLICULAR_E2_AREA_RATIO_BOUNDS,
    VALIDATION_STRICKER_MAPPED_E2_COVERAGE_MIN,
    VALIDATION_WITHIN_PERSON_SD_MARGIN_50_PLUS_DAYS,
    VALIDATION_WITHIN_PERSON_SD_MARGIN_DAYS,
)
from .literature import (
    AGE_BAND_TARGETS,
    ANCKAERT_HORMONE_SUBPHASE_TARGETS,
    BULL_PHASE_TARGETS,
    CITATIONS,
    CUNNINGHAM_AGE_TARGETS,
    STRICKER_DAILY_SERUM_REFERENCE,
    age_band_for,
)
from .model import (
    DIARY_START_RANDOM,
    LONG_ESTRADIOL_DELAYED_EMERGENCE,
    _luteal_reference_day,
    ovulatory_hormone_points,
    shape_preserving_curve,
)
from .population import simulate_population
from .types import MedicalFactors


# AWHS eligibility began at age 18 (with higher local minima in Alabama, Nebraska, and
# Puerto Rico). Restricting the baseline calibration to adults prevents the source study's
# "under 20" stratum from being represented by 13--17-year-old synthetic participants.
BASELINE_VALIDATION_AGE_RANGE = (18.0, 55.0)
SIMULATOR_VERSION = "0.4.0"
VALIDATION_SCHEMA_VERSION = 14


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


def sample_sd(values: Sequence[float]) -> float:
    """Return the sample standard deviation or NaN when fewer than two values exist."""

    if len(values) < 2:
        return float("nan")
    center = mean(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / (len(values) - 1))


def pearson_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    """Return Pearson's correlation or NaN when the paired values have no variation."""

    if len(left) != len(right) or len(left) < 2:
        return float("nan")
    left_center = mean(left)
    right_center = mean(right)
    left_ss = sum((value - left_center) ** 2 for value in left)
    right_ss = sum((value - right_center) ** 2 for value in right)
    if left_ss <= 0.0 or right_ss <= 0.0:
        return float("nan")
    covariance = sum(
        (left_value - left_center) * (right_value - right_center)
        for left_value, right_value in zip(left, right)
    )
    return covariance / math.sqrt(left_ss * right_ss)


def proportion(values: Iterable[bool]) -> float:
    """Return the fraction of truthy values in an iterable."""

    values = list(values)
    if not values:
        return float("nan")
    return sum(1 for value in values if value) / len(values)


def cycle_irregularity(cycle_lengths: Sequence[int]) -> float:
    """Compute one participant's mean absolute adjacent-cycle difference.

    Purpose:
        Li et al. 2023 define irregularity using a participant's mean adjacent-cycle difference
        and a seven-day threshold. Their table footnote omits "absolute," but their methods define
        adjacent-cycle differences as absolute values; this function follows that convention.

    Args:
        cycle_lengths: Ordered sequence of cycle lengths for one patient.

    Returns:
        Mean absolute adjacent-cycle difference in days.  Li et al. classify the
        participant as irregular when this value is at least seven days.
    """

    if len(cycle_lengths) < 2:
        return float("nan")
    diffs = [
        abs(right - left)
        for left, right in zip(cycle_lengths[:-1], cycle_lengths[1:])
    ]
    return mean(diffs)


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
    """Compare age-stratified healthy-cycle outcomes with Li et al. 2023."""

    by_band: Dict[str, List[Dict[str, object]]] = {target.label: [] for target in AGE_BAND_TARGETS}
    for cycle in cycles:
        label = age_band_for(float(cycle["age_years"])).label
        by_band[label].append(cycle)

    metrics: List[ValidationMetric] = []
    for target in AGE_BAND_TARGETS:
        band_cycles = by_band[target.label]
        if not band_cycles:
            continue
        patient_cycles: Dict[str, List[Tuple[int, int]]] = {}
        for cycle in band_cycles:
            patient_cycles.setdefault(str(cycle["patient_id"]), []).append(
                (int(cycle["cycle_index"]), int(cycle["cycle_length"]))
            )
        patient_lengths = [
            [length for _, length in sorted(items)[:VALIDATION_CYCLES_PER_PARTICIPANT]]
            for items in patient_cycles.values()
            if len(items) >= 3
        ]
        mean_cycle = mean([mean(lengths) for lengths in patient_lengths])
        cycle_margin = VALIDATION_CYCLE_MARGIN_MIN_DAYS
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
                citation_key="li_2023_awhs",
                notes="Equal-participant age-stratified mean; absolute targets were derived from the published adjusted age contrasts anchored to the AWHS overall mean of 28.7 days.",
            )
        )

        residual_ss = 0.0
        residual_df = 0
        for lengths in patient_lengths:
            patient_mean = mean(lengths)
            residual_ss += sum((length - patient_mean) ** 2 for length in lengths)
            residual_df += len(lengths) - 1
        within_sd = math.sqrt(residual_ss / residual_df)
        within_margin = (
            VALIDATION_WITHIN_PERSON_SD_MARGIN_50_PLUS_DAYS
            if target.label == "50+"
            else VALIDATION_WITHIN_PERSON_SD_MARGIN_DAYS
        )
        metrics.append(
            ValidationMetric(
                name=f"cycle_within_person_sd_{target.label}",
                observed=round(within_sd, 3),
                expected=target.within_person_sd_days,
                lower_bound=round(target.within_person_sd_days - within_margin, 3),
                upper_bound=round(target.within_person_sd_days + within_margin, 3),
                passed=abs(within_sd - target.within_person_sd_days) <= within_margin,
                citation_key="li_2023_awhs",
                notes="Pooled within-participant SD after subtracting each participant's mean, using up to the first 11 cycles per participant.",
            )
        )

        irregularity = proportion(
            cycle_irregularity(lengths) >= IRREGULARITY_THRESHOLD_DAYS
            for lengths in patient_lengths
        )
        irregularity_lower = max(0.0, target.irregular_participant_probability - VALIDATION_IRREGULARITY_MARGIN)
        irregularity_upper = min(1.0, target.irregular_participant_probability + VALIDATION_IRREGULARITY_MARGIN)
        metrics.append(
            ValidationMetric(
                name=f"cycle_irregularity_{target.label}",
                observed=round(irregularity, 4),
                expected=target.irregular_participant_probability,
                lower_bound=round(irregularity_lower, 4),
                upper_bound=round(irregularity_upper, 4),
                passed=irregularity_lower <= irregularity <= irregularity_upper,
                citation_key="li_2023_awhs",
                notes="Participant prevalence with mean absolute adjacent-cycle difference >=7 days, matching the AWHS estimand.",
            )
        )

        tail_margin = (
            VALIDATION_CYCLE_TAIL_MARGIN_50_PLUS
            if target.label == "50+"
            else VALIDATION_CYCLE_TAIL_MARGIN
        )
        for tail_name, observed, expected in (
            ("short_lt24", mean([proportion(length < 24 for length in lengths) for lengths in patient_lengths]), target.short_cycle_probability),
            ("long_gt38", mean([proportion(length > 38 for length in lengths) for lengths in patient_lengths]), target.long_cycle_probability),
        ):
            lower = max(0.0, expected - tail_margin)
            upper = min(1.0, expected + tail_margin)
            metrics.append(
                ValidationMetric(
                    name=f"cycle_{tail_name}_{target.label}",
                    observed=round(observed, 4),
                    expected=expected,
                    lower_bound=round(lower, 4),
                    upper_bound=round(upper, 4),
                    passed=lower <= observed <= upper,
                    citation_key="li_2023_awhs",
                    notes="Equal-participant cycle-tail prevalence compared with AWHS Supplementary Table 2.",
                )
            )
    return metrics


def _external_cycle_metrics(cycles: Sequence[Dict[str, object]]) -> List[ValidationMetric]:
    """Cross-check 12-month participant summaries against Cunningham et al. 2024."""

    metrics: List[ValidationMetric] = []
    for target in CUNNINGHAM_AGE_TARGETS:
        patient_cycles: Dict[str, List[Tuple[int, int]]] = {}
        for cycle in cycles:
            age = float(cycle["age_years"])
            if target.age_min <= age < target.age_max:
                patient_cycles.setdefault(str(cycle["patient_id"]), []).append(
                    (int(cycle["cycle_index"]), int(cycle["cycle_length"]))
                )
        series = [
            [length for _, length in sorted(items)[:VALIDATION_CYCLES_PER_PARTICIPANT]]
            for items in patient_cycles.values()
            if len(items) >= 3
        ]
        if not series:
            continue
        observed_mean = mean([mean(lengths) for lengths in series])
        observed_sd = mean([sample_sd(lengths) for lengths in series])
        sd_margin = (
            EXTERNAL_MEAN_PERSONAL_SD_MARGIN_51_PLUS_DAYS
            if target.label == "51-55"
            else EXTERNAL_MEAN_PERSONAL_SD_MARGIN_DAYS
        )
        mean_margin = (
            EXTERNAL_MEAN_CYCLE_MARGIN_51_PLUS_DAYS
            if target.label == "51-55"
            else EXTERNAL_MEAN_CYCLE_MARGIN_DAYS
        )
        for suffix, observed, expected, margin, note in (
            ("mean", observed_mean, target.mean_cycle_days, mean_margin, "Mean participant cycle length over a 12-month-equivalent window."),
            ("mean_personal_sd", observed_sd, target.mean_personal_sd_days, sd_margin, "Mean participant-specific sample SD over a 12-month-equivalent window."),
        ):
            metrics.append(
                ValidationMetric(
                    name=f"external_cunningham_{suffix}_{target.label}",
                    observed=round(observed, 3),
                    expected=expected,
                    lower_bound=round(expected - margin, 3),
                    upper_bound=round(expected + margin, 3),
                    passed=abs(observed - expected) <= margin,
                    citation_key="cunningham_2024_flo",
                    notes=note + " Held out from model calibration; wider margins reflect different cohort filters and aggregation.",
                )
            )
    return metrics


def _overall_cycle_metrics(cycles: Sequence[Dict[str, object]]) -> List[ValidationMetric]:
    """Compare aggregate phase and bleeding statistics with Bull et al. 2019."""

    ovulatory_cycles = [cycle for cycle in cycles if cycle["ovulatory"]]
    follicular_mean = mean([float(cycle["follicular_length"]) for cycle in ovulatory_cycles])
    luteal_mean = mean([float(cycle["luteal_length"]) for cycle in ovulatory_cycles])
    bleeding_mean = mean([float(cycle["bleeding_days"]) for cycle in cycles])
    luteal_sd = sample_sd([float(cycle["luteal_length"]) for cycle in ovulatory_cycles])
    bleeding_sd = sample_sd([float(cycle["bleeding_days"]) for cycle in cycles])
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
        ValidationMetric(
            name="luteal_sd_days",
            observed=round(luteal_sd, 3),
            expected=BULL_PHASE_TARGETS["luteal_sd_days"],
            lower_bound=BULL_LUTEAL_SD_VALIDATION_BOUNDS[0],
            upper_bound=BULL_LUTEAL_SD_VALIDATION_BOUNDS[1],
            passed=BULL_LUTEAL_SD_VALIDATION_BOUNDS[0] <= luteal_sd <= BULL_LUTEAL_SD_VALIDATION_BOUNDS[1],
            citation_key="bull_2019_natural_cycles",
            notes="SD of luteal length in ovulatory cycles.",
        ),
        ValidationMetric(
            name="bleeding_sd_days",
            observed=round(bleeding_sd, 3),
            expected=BULL_PHASE_TARGETS["bleeding_sd_days"],
            lower_bound=BULL_BLEEDING_SD_VALIDATION_BOUNDS[0],
            upper_bound=BULL_BLEEDING_SD_VALIDATION_BOUNDS[1],
            passed=BULL_BLEEDING_SD_VALIDATION_BOUNDS[0] <= bleeding_sd <= BULL_BLEEDING_SD_VALIDATION_BOUNDS[1],
            citation_key="bull_2019_natural_cycles",
            notes="SD of bleeding duration across natural cycles.",
        ),
    ]


def _stricker_construction_metrics() -> List[ValidationMetric]:
    """Verify complete ordinary-cycle mapping of the source daily E2 series.

    These are construction-fidelity checks, not independent validation: the same Stricker values
    define the median envelope. They exist to prevent a future implementation or plotting filter
    from silently omitting the early/mid-follicular observations again.
    """

    cycle_length = 29
    follicular_length = 15
    lh_peak_day = float(follicular_length) - 0.75
    estradiol_points, _ = ovulatory_hormone_points(
        cycle_length,
        follicular_length,
        cycle_length - follicular_length,
        1.0,
        1.0,
        LONG_ESTRADIOL_DELAYED_EMERGENCE,
    )
    estradiol_curve = shape_preserving_curve(estradiol_points)
    mapped = [
        (
            reference,
            _luteal_reference_day(
                lh_peak_day,
                float(reference.lh_offset_days),
                cycle_length,
            ),
        )
        for reference in STRICKER_DAILY_SERUM_REFERENCE
    ]
    mapped = [
        (reference, day)
        for reference, day in mapped
        if 1.0 < day <= float(cycle_length)
    ]
    point_days = [float(day) for day, _ in estradiol_points]
    covered = sum(
        any(abs(point_day - day) <= 1e-9 for point_day in point_days)
        for _, day in mapped
    )
    coverage = covered / len(mapped)

    follicular = [
        (reference, day)
        for reference, day in mapped
        if -13 <= reference.lh_offset_days <= -2
    ]
    simulated_area = sum(estradiol_curve(day) for _, day in follicular)
    source_area = sum(reference.estradiol_pg_ml for reference, _ in follicular)
    area_ratio = simulated_area / source_area
    lower, upper = VALIDATION_STRICKER_FOLLICULAR_E2_AREA_RATIO_BOUNDS
    return [
        ValidationMetric(
            name="estradiol_stricker_mapped_reference_coverage",
            observed=round(coverage, 4),
            expected=1.0,
            lower_bound=VALIDATION_STRICKER_MAPPED_E2_COVERAGE_MIN,
            upper_bound=1.0,
            passed=coverage >= VALIDATION_STRICKER_MAPPED_E2_COVERAGE_MIN,
            citation_key="stricker_2006_reference",
            notes=(
                "Direct construction check: fraction of all in-cycle Stricker E2 medians "
                "represented as control points in the canonical 29-day envelope."
            ),
        ),
        ValidationMetric(
            name="estradiol_stricker_follicular_area_ratio",
            observed=round(area_ratio, 4),
            expected=1.0,
            lower_bound=lower,
            upper_bound=upper,
            passed=lower <= area_ratio <= upper,
            citation_key="stricker_2006_reference",
            notes=(
                "Direct construction check: simulated/source summed E2 at mapped LH-13 through "
                "LH-2 observations; prevents an early or inflated follicular ramp."
            ),
        ),
    ]


def _hormone_metrics(
    sample_diaries: Sequence[Dict[str, object]],
    diagnostics: Optional[Dict[str, object]] = None,
) -> List[ValidationMetric]:
    """Compare subphase amplitudes and daily morphology in retained healthy diaries.

    Stricker daily medians supply the model envelope. Anckaert et al.'s larger, separate cohort
    supplies the independent subphase comparison; wide equivalence windows acknowledge assay and
    population differences. Explicit daily-shape metrics guard against narrow P4 peaks, misplaced
    rise/withdrawal transitions, loss of the luteal E2 rebound, and cross-cycle discontinuities.
    """

    phase_values: Dict[str, Dict[str, List[float]]] = {
        target.name: {"estradiol": [], "progesterone": []}
        for target in ANCKAERT_HORMONE_SUBPHASE_TARGETS
    }
    estradiol_peak_widths: List[float] = []
    estradiol_peak_offsets: List[float] = []
    estradiol_secondary_peak_ratios: List[float] = []
    progesterone_plateau_days: List[float] = []
    progesterone_peak_offsets: List[float] = []
    progesterone_peak_luteal_lengths: List[float] = []
    progesterone_rise_offsets: List[float] = []
    progesterone_withdrawal_days: List[float] = []
    progesterone_terminal_ratios: List[float] = []
    progesterone_penultimate_drops: List[float] = []
    cross_cycle_progesterone_jumps: List[float] = []

    for diary_payload in sample_diaries:
        cycle_map = {int(cycle["cycle_index"]): cycle for cycle in diary_payload["cycles"]}
        rows_by_cycle: Dict[int, List[Dict[str, object]]] = {}
        for row in diary_payload["diary"]:
            rows_by_cycle.setdefault(int(row["cycle_index"]), []).append(row)

        complete_ovulatory: Dict[int, List[Dict[str, object]]] = {}
        for cycle_index, rows in rows_by_cycle.items():
            cycle = cycle_map[cycle_index]
            cycle_length = int(cycle["cycle_length"])
            ordered = sorted(rows, key=lambda row: int(row["cycle_day"]))
            if (
                not bool(cycle["ovulatory"])
                or len(ordered) != cycle_length
                or int(ordered[0]["cycle_day"]) != 1
                or int(ordered[-1]["cycle_day"]) != cycle_length
            ):
                continue
            complete_ovulatory[cycle_index] = ordered
            for row in ordered:
                name = phase_name(int(row["cycle_day"]), cycle)
                if name is None:
                    continue
                phase_values[name]["estradiol"].append(float(row["estradiol_pg_ml"]))
                phase_values[name]["progesterone"].append(float(row["progesterone_ng_ml"]))

            ovulation_day = int(cycle["ovulation_day"])
            follicular_e2 = [
                float(row["estradiol_pg_ml"])
                for row in ordered
                if int(row["cycle_day"]) <= ovulation_day
            ]
            follicular_peak = max(follicular_e2)
            follicular_peak_day = follicular_e2.index(follicular_peak) + 1
            estradiol_peak_offsets.append(float(follicular_peak_day - ovulation_day))
            estradiol_peak_widths.append(
                float(
                    sum(
                        value
                        >= follicular_peak * VALIDATION_ESTRADIOL_PEAK_WIDTH_FRACTION
                        for value in follicular_e2
                    )
                )
            )

            luteal_e2 = [
                float(row["estradiol_pg_ml"])
                for row in ordered
                if int(row["cycle_day"]) > ovulation_day
            ]
            if luteal_e2 and follicular_peak > 0.0:
                estradiol_secondary_peak_ratios.append(max(luteal_e2) / follicular_peak)

            progesterone_values = [float(row["progesterone_ng_ml"]) for row in ordered]
            progesterone_peak = max(progesterone_values)
            progesterone_peak_day = progesterone_values.index(progesterone_peak) + 1
            progesterone_peak_offsets.append(float(progesterone_peak_day - ovulation_day))
            progesterone_peak_luteal_lengths.append(float(cycle["luteal_length"]))
            progesterone_plateau_days.append(
                float(
                    sum(
                        value
                        >= progesterone_peak * VALIDATION_PROGESTERONE_PLATEAU_FRACTION
                        for value in progesterone_values
                    )
                )
            )
            rise_day = next(
                (
                    day
                    for day, value in enumerate(progesterone_values, start=1)
                    if day >= ovulation_day and value >= 5.0
                ),
                None,
            )
            if rise_day is not None:
                progesterone_rise_offsets.append(float(rise_day - ovulation_day))
            progesterone_terminal_ratios.append(
                progesterone_values[-1] / progesterone_peak
                if progesterone_peak > 0.0
                else float("nan")
            )
            if len(progesterone_values) >= 2:
                progesterone_penultimate_drops.append(
                    abs(progesterone_values[-1] - progesterone_values[-2])
                )
            withdrawal_transitions = 0
            for earlier, later in zip(
                reversed(progesterone_values[:-1]),
                reversed(progesterone_values[1:]),
            ):
                if later < earlier:
                    withdrawal_transitions += 1
                else:
                    break
            progesterone_withdrawal_days.append(float(withdrawal_transitions))

        for cycle_index in sorted(complete_ovulatory):
            next_index = cycle_index + 1
            if next_index not in complete_ovulatory:
                continue
            current = complete_ovulatory[cycle_index]
            following = complete_ovulatory[next_index]
            cross_cycle_progesterone_jumps.append(
                abs(
                    float(following[0]["progesterone_ng_ml"])
                    - float(current[-1]["progesterone_ng_ml"])
                )
            )

    metrics: List[ValidationMetric] = _stricker_construction_metrics()
    for target in ANCKAERT_HORMONE_SUBPHASE_TARGETS:
        estradiol_obs = median(phase_values[target.name]["estradiol"])
        progesterone_obs = median(phase_values[target.name]["progesterone"])
        estradiol_lower = target.estradiol_pg_ml * ANCKAERT_ESTRADIOL_RATIO_BOUNDS[0]
        estradiol_upper = target.estradiol_pg_ml * ANCKAERT_ESTRADIOL_RATIO_BOUNDS[1]
        if target.name == "ovulation":
            progesterone_lower, progesterone_upper = (
                ANCKAERT_OVULATION_PROGESTERONE_BOUNDS_NG_ML
            )
        elif target.name in {
            "early_follicular",
            "mid_follicular",
            "pre_ovulatory",
        }:
            progesterone_lower, progesterone_upper = ANCKAERT_LOW_PROGESTERONE_BOUNDS_NG_ML
        else:
            progesterone_lower = max(
                VALIDATION_MIN_PROGESTERONE_BOUND,
                target.progesterone_ng_ml * ANCKAERT_PROGESTERONE_RATIO_BOUNDS[0],
            )
            progesterone_upper = target.progesterone_ng_ml * ANCKAERT_PROGESTERONE_RATIO_BOUNDS[1]
        metrics.append(
            ValidationMetric(
                name=f"estradiol_{target.name}",
                observed=round(estradiol_obs, 3),
                expected=round(target.estradiol_pg_ml, 3),
                lower_bound=round(estradiol_lower, 3),
                upper_bound=round(estradiol_upper, 3),
                passed=estradiol_lower <= estradiol_obs <= estradiol_upper,
                citation_key="anckaert_2021_hormones",
                notes="Independent Anckaert serum-E2 subphase median; broad bound accounts for assay and cohort differences.",
            )
        )
        metrics.append(
            ValidationMetric(
                name=f"progesterone_{target.name}",
                observed=round(progesterone_obs, 3),
                expected=round(target.progesterone_ng_ml, 3),
                lower_bound=round(progesterone_lower, 3),
                upper_bound=round(progesterone_upper, 3),
                passed=progesterone_lower <= progesterone_obs <= progesterone_upper,
                citation_key="anckaert_2021_hormones",
                notes="Independent Anckaert serum-P4 subphase median; broad bound accounts for assay and cohort differences.",
            )
        )
    peak_width = median(estradiol_peak_widths)
    metrics.append(
        ValidationMetric(
            name="estradiol_preovulatory_peak_width_days",
            observed=round(peak_width, 3),
            expected=3.0,
            lower_bound=VALIDATION_ESTRADIOL_PEAK_WIDTH_DAYS_BOUNDS[0],
            upper_bound=VALIDATION_ESTRADIOL_PEAK_WIDTH_DAYS_BOUNDS[1],
            passed=(
                VALIDATION_ESTRADIOL_PEAK_WIDTH_DAYS_BOUNDS[0]
                <= peak_width
                <= VALIDATION_ESTRADIOL_PEAK_WIDTH_DAYS_BOUNDS[1]
            ),
            citation_key="stricker_2006_reference",
            notes="Median number of follicular days at or above 80% of the cycle-specific estradiol maximum; investigator-selected kinetic smoke-check bound.",
        )
    )
    estradiol_peak_offset = median(estradiol_peak_offsets)
    metrics.append(
        ValidationMetric(
            name="estradiol_peak_offset_from_ovulation_days",
            observed=round(estradiol_peak_offset, 3),
            expected=-2.0,
            lower_bound=VALIDATION_ESTRADIOL_PEAK_OFFSET_BOUNDS[0],
            upper_bound=VALIDATION_ESTRADIOL_PEAK_OFFSET_BOUNDS[1],
            passed=(
                VALIDATION_ESTRADIOL_PEAK_OFFSET_BOUNDS[0]
                <= estradiol_peak_offset
                <= VALIDATION_ESTRADIOL_PEAK_OFFSET_BOUNDS[1]
            ),
            citation_key="roos_2015_true_ovulation",
            notes=(
                "Median E2-peak day relative to ultrasound-aligned ovulation context; Roos "
                "supports a preovulatory rise with heterogeneous signal timing."
            ),
        )
    )
    estradiol_peak_offset_sd = sample_sd(estradiol_peak_offsets)
    metrics.append(
        ValidationMetric(
            name="estradiol_peak_offset_sd_days",
            observed=round(estradiol_peak_offset_sd, 3),
            expected=1.0,
            lower_bound=VALIDATION_ESTRADIOL_PEAK_OFFSET_SD_BOUNDS[0],
            upper_bound=VALIDATION_ESTRADIOL_PEAK_OFFSET_SD_BOUNDS[1],
            passed=(
                VALIDATION_ESTRADIOL_PEAK_OFFSET_SD_BOUNDS[0]
                <= estradiol_peak_offset_sd
                <= VALIDATION_ESTRADIOL_PEAK_OFFSET_SD_BOUNDS[1]
            ),
            citation_key="roos_2015_true_ovulation",
            notes=(
                "Cycle-level SD of E2-peak timing. Roos establishes interindividual signal "
                "heterogeneity; the numerical floor is an investigator-set anti-template guard."
            ),
        )
    )
    secondary_peak_ratio = median(estradiol_secondary_peak_ratios)
    metrics.append(
        ValidationMetric(
            name="estradiol_luteal_secondary_peak_ratio",
            observed=round(secondary_peak_ratio, 4),
            expected=0.59,
            lower_bound=VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_BOUNDS[0],
            upper_bound=VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_BOUNDS[1],
            passed=(
                VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_BOUNDS[0]
                <= secondary_peak_ratio
                <= VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_BOUNDS[1]
            ),
            citation_key="stricker_2006_reference",
            notes="Median ratio of luteal E2 maximum to the follicular maximum; checks the daily-series secondary luteal rise.",
        )
    )
    secondary_peak_ratio_sd = sample_sd(estradiol_secondary_peak_ratios)
    metrics.append(
        ValidationMetric(
            name="estradiol_luteal_secondary_peak_ratio_sd",
            observed=round(secondary_peak_ratio_sd, 4),
            expected=0.08,
            lower_bound=VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_SD_BOUNDS[0],
            upper_bound=VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_SD_BOUNDS[1],
            passed=(
                VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_SD_BOUNDS[0]
                <= secondary_peak_ratio_sd
                <= VALIDATION_ESTRADIOL_SECONDARY_PEAK_RATIO_SD_BOUNDS[1]
            ),
            citation_key="roos_2015_true_ovulation",
            notes=(
                "Cycle-level SD of the luteal/follicular E2 peak ratio; numerical bounds are "
                "investigator-set guards against cloned or pathologically unstable morphology."
            ),
        )
    )
    plateau_days = median(progesterone_plateau_days)
    metrics.append(
        ValidationMetric(
            name="progesterone_plateau_width_days",
            observed=round(plateau_days, 3),
            expected=6.0,
            lower_bound=VALIDATION_PROGESTERONE_PLATEAU_DAYS_BOUNDS[0],
            upper_bound=VALIDATION_PROGESTERONE_PLATEAU_DAYS_BOUNDS[1],
            passed=(
                VALIDATION_PROGESTERONE_PLATEAU_DAYS_BOUNDS[0]
                <= plateau_days
                <= VALIDATION_PROGESTERONE_PLATEAU_DAYS_BOUNDS[1]
            ),
            citation_key="stricker_2006_reference",
            notes="Median days at or above 75% of cycle-specific P4 maximum; directly guards against a one-day triangular peak.",
        )
    )
    peak_offset = median(progesterone_peak_offsets)
    metrics.append(
        ValidationMetric(
            name="progesterone_peak_offset_from_ovulation_days",
            observed=round(peak_offset, 3),
            expected=6.0,
            lower_bound=VALIDATION_PROGESTERONE_PEAK_OFFSET_BOUNDS[0],
            upper_bound=VALIDATION_PROGESTERONE_PEAK_OFFSET_BOUNDS[1],
            passed=(
                VALIDATION_PROGESTERONE_PEAK_OFFSET_BOUNDS[0]
                <= peak_offset
                <= VALIDATION_PROGESTERONE_PEAK_OFFSET_BOUNDS[1]
            ),
            citation_key="stricker_2006_reference",
            notes="Median day of maximum P4 relative to the simulator ovulation event after explicit LH-to-ovulation alignment.",
        )
    )
    progesterone_peak_offset_sd = sample_sd(progesterone_peak_offsets)
    metrics.append(
        ValidationMetric(
            name="progesterone_peak_offset_sd_days",
            observed=round(progesterone_peak_offset_sd, 3),
            expected=1.0,
            lower_bound=VALIDATION_PROGESTERONE_PEAK_OFFSET_SD_BOUNDS[0],
            upper_bound=VALIDATION_PROGESTERONE_PEAK_OFFSET_SD_BOUNDS[1],
            passed=(
                VALIDATION_PROGESTERONE_PEAK_OFFSET_SD_BOUNDS[0]
                <= progesterone_peak_offset_sd
                <= VALIDATION_PROGESTERONE_PEAK_OFFSET_SD_BOUNDS[1]
            ),
            citation_key="roos_2015_true_ovulation",
            notes=(
                "Cycle-level SD of P4-peak timing; Roos supports heterogeneous postovulatory "
                "signals and the numerical floor is an investigator-set anti-template guard."
            ),
        )
    )
    luteal_peak_correlation = pearson_correlation(
        progesterone_peak_luteal_lengths,
        progesterone_peak_offsets,
    )
    metrics.append(
        ValidationMetric(
            name="progesterone_luteal_length_peak_offset_correlation",
            observed=round(luteal_peak_correlation, 4),
            expected=0.0,
            lower_bound=-VALIDATION_LUTEAL_LENGTH_P4_PEAK_CORRELATION_ABS_MAX,
            upper_bound=VALIDATION_LUTEAL_LENGTH_P4_PEAK_CORRELATION_ABS_MAX,
            passed=(
                math.isfinite(luteal_peak_correlation)
                and abs(luteal_peak_correlation)
                <= VALIDATION_LUTEAL_LENGTH_P4_PEAK_CORRELATION_ABS_MAX
            ),
            citation_key="roos_2015_true_ovulation",
            notes=(
                "Correlation between realized luteal length and P4-peak offset; the ceiling is "
                "an investigator-set guard against uniformly time-warping the entire luteal curve."
            ),
        )
    )
    rise_offset = median(progesterone_rise_offsets)
    metrics.append(
        ValidationMetric(
            name="progesterone_rise_to_5ng_offset_days",
            observed=round(rise_offset, 3),
            expected=2.0,
            lower_bound=VALIDATION_PROGESTERONE_RISE_OFFSET_BOUNDS[0],
            upper_bound=VALIDATION_PROGESTERONE_RISE_OFFSET_BOUNDS[1],
            passed=(
                VALIDATION_PROGESTERONE_RISE_OFFSET_BOUNDS[0]
                <= rise_offset
                <= VALIDATION_PROGESTERONE_RISE_OFFSET_BOUNDS[1]
            ),
            citation_key="stricker_2006_reference",
            notes="Median first post-ovulation day reaching 5 ng/mL; guards the luteal-rise transition.",
        )
    )
    withdrawal_days = median(progesterone_withdrawal_days)
    metrics.append(
        ValidationMetric(
            name="progesterone_premenstrual_withdrawal_days",
            observed=round(withdrawal_days, 3),
            expected=4.0,
            lower_bound=VALIDATION_PROGESTERONE_WITHDRAWAL_MIN_DAYS,
            upper_bound=8.0,
            passed=withdrawal_days >= VALIDATION_PROGESTERONE_WITHDRAWAL_MIN_DAYS,
            citation_key="stricker_2006_reference",
            notes="Median consecutive declining transitions before the next bleeding onset; investigator-selected kinetic smoke check.",
        )
    )
    terminal_ratio = median(
        [value for value in progesterone_terminal_ratios if math.isfinite(value)]
    )
    terminal_lower, terminal_upper = VALIDATION_PROGESTERONE_TERMINAL_TO_PEAK_BOUNDS
    metrics.append(
        ValidationMetric(
            name="progesterone_terminal_to_peak_ratio",
            observed=round(terminal_ratio, 4),
            expected=0.10,
            lower_bound=terminal_lower,
            upper_bound=terminal_upper,
            passed=terminal_lower <= terminal_ratio <= terminal_upper,
            citation_key="stricker_2006_reference",
            notes=(
                "Median final-cycle P4 divided by the cycle maximum; the two-sided bound retains "
                "the published LH+14 tail while requiring substantial premenstrual withdrawal."
            ),
        )
    )
    penultimate_drop = median(progesterone_penultimate_drops)
    metrics.append(
        ValidationMetric(
            name="progesterone_penultimate_to_terminal_drop_ng_ml",
            observed=round(penultimate_drop, 4),
            expected=0.4,
            lower_bound=0.0,
            upper_bound=VALIDATION_PROGESTERONE_PENULTIMATE_DROP_MAX_NG_ML,
            passed=penultimate_drop <= VALIDATION_PROGESTERONE_PENULTIMATE_DROP_MAX_NG_ML,
            citation_key="stricker_2006_reference",
            notes=(
                "Median absolute final within-cycle P4 drop; added because a boundary-only check "
                "can miss a reset that was shifted to the preceding day."
            ),
        )
    )
    cross_cycle_jump = median(cross_cycle_progesterone_jumps)
    metrics.append(
        ValidationMetric(
            name="progesterone_cross_cycle_jump_ng_ml",
            observed=round(cross_cycle_jump, 4),
            expected=0.0,
            lower_bound=0.0,
            upper_bound=VALIDATION_CROSS_CYCLE_PROGESTERONE_JUMP_MAX_NG_ML,
            passed=(
                cross_cycle_jump
                <= VALIDATION_CROSS_CYCLE_PROGESTERONE_JUMP_MAX_NG_ML
            ),
            citation_key="stricker_2006_reference",
            notes="Median absolute progesterone difference between one complete cycle's final day and the next complete cycle's first day.",
        )
    )
    if diagnostics is not None:
        diagnostics.update(
            {
                "scope": (
                    f"Complete ovulatory cycles in the {len(sample_diaries)} age-balanced "
                    "retained baseline diaries; "
                    "values support distribution and dependence QA, not population estimates."
                ),
                "n_complete_ovulatory_cycles": len(estradiol_peak_offsets),
                "estradiol_peak_offsets_days": estradiol_peak_offsets,
                "progesterone_peak_offsets_days": progesterone_peak_offsets,
                "luteal_lengths_days": progesterone_peak_luteal_lengths,
                "estradiol_secondary_peak_ratios": estradiol_secondary_peak_ratios,
                "progesterone_terminal_to_peak_ratios": progesterone_terminal_ratios,
                "progesterone_penultimate_drops_ng_ml": progesterone_penultimate_drops,
                "progesterone_cross_cycle_jumps_ng_ml": cross_cycle_progesterone_jumps,
            }
        )
    return metrics


def _summarize_subgroup(population: Dict[str, object], baseline: Optional[Dict[str, float]] = None) -> Dict[str, object]:
    """Reduce a simulated subgroup cohort to headline validation statistics."""

    cycles = population["cycles"]
    cycle_lengths = [int(cycle["cycle_length"]) for cycle in cycles]
    ovulation_rate = proportion(bool(cycle["ovulatory"]) for cycle in cycles)
    long_cycles = [
        cycle
        for cycle in cycles
        if int(cycle["cycle_length"])
        >= MENOPAUSE_TRANSITION_LONG_CYCLE_THRESHOLD_DAYS
    ]
    long_cycle_anovulatory_rate = proportion(
        not bool(cycle["ovulatory"])
        for cycle in long_cycles
    )
    ordinary_cycles = [
        cycle
        for cycle in cycles
        if 21 <= int(cycle["cycle_length"]) < MENOPAUSE_TRANSITION_LONG_CYCLE_THRESHOLD_DAYS
    ]
    ordinary_cycle_anovulatory_rate = proportion(
        not bool(cycle["ovulatory"])
        for cycle in ordinary_cycles
    )
    long_vs_ordinary_delta = (
        long_cycle_anovulatory_rate - ordinary_cycle_anovulatory_rate
    )
    if (
        0.0 < long_cycle_anovulatory_rate < 1.0
        and 0.0 < ordinary_cycle_anovulatory_rate < 1.0
    ):
        long_vs_ordinary_odds_ratio = (
            long_cycle_anovulatory_rate / (1.0 - long_cycle_anovulatory_rate)
        ) / (
            ordinary_cycle_anovulatory_rate / (1.0 - ordinary_cycle_anovulatory_rate)
        )
    else:
        long_vs_ordinary_odds_ratio = float("nan")
    bleeding_days = mean([float(cycle["bleeding_days"]) for cycle in cycles])
    irregularity_by_patient: Dict[str, List[int]] = {}
    for cycle in cycles:
        irregularity_by_patient.setdefault(str(cycle["patient_id"]), []).append(int(cycle["cycle_length"]))
    irregularity = proportion(
        cycle_irregularity(lengths) >= IRREGULARITY_THRESHOLD_DAYS
        for lengths in irregularity_by_patient.values()
        if len(lengths) >= 2 and not math.isnan(cycle_irregularity(lengths))
    )
    amenorrhea = proportion(int(cycle["bleeding_days"]) == 0 for cycle in cycles)
    summary = {
        "mean_cycle_days": round(mean(cycle_lengths), 3),
        "ovulation_rate": round(ovulation_rate, 3),
        "mean_bleeding_days": round(bleeding_days, 3),
        "irregularity_rate": round(irregularity, 3),
        "amenorrhea_rate": round(amenorrhea, 3),
        "long_cycle_count": len(long_cycles),
        "long_cycle_anovulatory_rate": round(long_cycle_anovulatory_rate, 3),
        "ordinary_cycle_count": len(ordinary_cycles),
        "ordinary_cycle_anovulatory_rate": round(ordinary_cycle_anovulatory_rate, 3),
        "long_vs_ordinary_anovulation_delta": round(long_vs_ordinary_delta, 3),
        "long_vs_ordinary_anovulation_odds_ratio": round(
            long_vs_ordinary_odds_ratio,
            3,
        ),
    }
    if baseline:
        comparable_delta_keys = {
            "mean_cycle_days",
            "ovulation_rate",
            "mean_bleeding_days",
            "irregularity_rate",
            "amenorrhea_rate",
            "long_cycle_anovulatory_rate",
            "ordinary_cycle_anovulatory_rate",
            "long_vs_ordinary_anovulation_delta",
        }
        summary["delta_vs_baseline"] = {
            key: round(summary[key] - baseline[key], 3)
            for key in baseline
            if key in comparable_delta_keys and key in summary
        }
    return summary


def _subgroup_analysis(seed: int, days: int, start_mode: str) -> Dict[str, object]:
    """Run age-matched factor-specific software stress tests after the primary gate passes.

    Args:
        seed: Base random seed used to derive subgroup-specific seeds.
        days: Diary length in days for each subgroup member.
        start_mode: First-cycle observation rule used for all subgroup diaries.

    Returns:
        A dictionary containing an adult display reference and one age-matched entry per factor.
        These scenarios are secondary direction/range regression checks, not external validation.
    """

    baseline_population = simulate_population(
        num_patients=SUBGROUP_BASELINE_REFERENCE_PATIENTS,
        days=days,
        seed=seed + 100,
        medical_factors=MedicalFactors(),
        balanced_age_bands=False,
        include_diaries=False,
        start_mode=start_mode,
        age_range=(18.0, 45.0),
    )
    baseline_summary = _summarize_subgroup(baseline_population)

    subgroup_definitions = {
        "pcos": (MedicalFactors(pcos=True), (18.0, 45.0)),
        "cyclic_ocp": (MedicalFactors(oral_contraceptive_mode="cyclic"), (18.0, 45.0)),
        "continuous_ocp": (MedicalFactors(oral_contraceptive_mode="continuous"), (18.0, 45.0)),
        "hormonal_iud": (MedicalFactors(hormonal_iud=True), (18.0, 45.0)),
        "copper_iud": (MedicalFactors(copper_iud=True), (18.0, 45.0)),
        "perimenopause": (MedicalFactors(perimenopause=True), (45.0, 55.0)),
        "peri_menarche": (MedicalFactors(peri_menarche=True), (13.0, 18.0)),
        "dysmenorrhea": (MedicalFactors(dysmenorrhea=True), (18.0, 45.0)),
    }

    results: Dict[str, object] = {
        "evaluation_type": "secondary direction/range software stress tests",
        "interpretation": (
            "Numerical margins are prespecified investigator-selected regression guards. "
            "The cited studies support effect direction or broad ranges; these scenarios are "
            "not held-out participant-level external validation."
        ),
        "baseline_reference": baseline_summary,
        "baseline_reference_age_range": [18.0, 45.0],
        "subgroups": {},
    }
    for index, (name, (factors, age_range)) in enumerate(subgroup_definitions.items(), start=1):
        scenario_seed = seed + 1000 + index
        matched_baseline_population = simulate_population(
            num_patients=SUBGROUP_REFERENCE_PATIENTS,
            days=days,
            seed=scenario_seed,
            medical_factors=MedicalFactors(),
            balanced_age_bands=False,
            include_diaries=False,
            start_mode=start_mode,
            age_range=age_range,
        )
        matched_baseline = _summarize_subgroup(matched_baseline_population)
        population = simulate_population(
            num_patients=SUBGROUP_REFERENCE_PATIENTS,
            days=days,
            seed=scenario_seed,
            medical_factors=factors,
            balanced_age_bands=False,
            include_diaries=False,
            start_mode=start_mode,
            age_range=age_range,
        )
        summary = _summarize_subgroup(population, baseline=matched_baseline)
        checks: List[ValidationMetric] = []

        if name == "pcos":
            checks.extend(
                [
                    ValidationMetric("pcos_longer_cycles", summary["mean_cycle_days"], matched_baseline["mean_cycle_days"] + PCOS_VALIDATION_MIN_CYCLE_DELTA_DAYS, matched_baseline["mean_cycle_days"] + PCOS_VALIDATION_MIN_CYCLE_DELTA_DAYS, 999.0, summary["mean_cycle_days"] >= matched_baseline["mean_cycle_days"] + PCOS_VALIDATION_MIN_CYCLE_DELTA_DAYS, "mortimer_2026_pcos", "Direction-only check: PCOS should shift mean cycle length upward versus its age-matched baseline."),
                    ValidationMetric("pcos_higher_irregularity", summary["irregularity_rate"], matched_baseline["irregularity_rate"] + PCOS_VALIDATION_MIN_IRREGULARITY_DELTA, matched_baseline["irregularity_rate"] + PCOS_VALIDATION_MIN_IRREGULARITY_DELTA, 1.0, summary["irregularity_rate"] >= matched_baseline["irregularity_rate"] + PCOS_VALIDATION_MIN_IRREGULARITY_DELTA, "mortimer_2026_pcos", "Direction-only check: PCOS should increase cycle irregularity versus its age-matched baseline."),
                    ValidationMetric("pcos_lower_ovulation", summary["ovulation_rate"], matched_baseline["ovulation_rate"] - PCOS_VALIDATION_MIN_OVULATION_DELTA, 0.0, matched_baseline["ovulation_rate"] - PCOS_VALIDATION_MIN_OVULATION_DELTA, summary["ovulation_rate"] <= matched_baseline["ovulation_rate"] - PCOS_VALIDATION_MIN_OVULATION_DELTA, "doi_2005_pcos_hormones", "Direction-only check: PCOS should reduce ovulation frequency versus its age-matched baseline."),
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
                    ValidationMetric("copper_iud_ovulation_preserved", summary["ovulation_rate"], matched_baseline["ovulation_rate"], matched_baseline["ovulation_rate"] - COPPER_IUD_VALIDATION_MAX_OVULATION_DELTA, matched_baseline["ovulation_rate"] + COPPER_IUD_VALIDATION_MAX_OVULATION_DELTA, abs(summary["ovulation_rate"] - matched_baseline["ovulation_rate"]) <= COPPER_IUD_VALIDATION_MAX_OVULATION_DELTA, "faundes_1980_copper_iud", "Direction-only check: copper IUDs should not materially suppress ovulation versus an age-matched baseline."),
                    ValidationMetric("copper_iud_bleeding_increase", summary["mean_bleeding_days"], matched_baseline["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[0], matched_baseline["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[0], matched_baseline["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[1], matched_baseline["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[0] <= summary["mean_bleeding_days"] <= matched_baseline["mean_bleeding_days"] + COPPER_IUD_VALIDATION_BLEEDING_DELTA_BOUNDS[1], "malmqvist_1974_copper_bleeding", "Direction-only check: copper IUDs should increase bleeding duration versus an age-matched baseline."),
                ]
            )
        elif name == "perimenopause":
            checks.extend(
                [
                    ValidationMetric("perimenopause_irregularity", summary["irregularity_rate"], PERIMENOPAUSE_VALIDATION_EXPECTED_IRREGULARITY, PERIMENOPAUSE_VALIDATION_MIN_IRREGULARITY, 1.00, summary["irregularity_rate"] >= PERIMENOPAUSE_VALIDATION_MIN_IRREGULARITY, "santoro_2011_perimenopause", "Direction-only check: perimenopause should increase cycle irregularity."),
                    ValidationMetric("perimenopause_lower_ovulation", summary["ovulation_rate"], PERIMENOPAUSE_VALIDATION_EXPECTED_OVULATION_RATE, PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS[0], PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS[1], PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS[0] <= summary["ovulation_rate"] <= PERIMENOPAUSE_VALIDATION_OVULATION_BOUNDS[1], "santoro_2011_perimenopause", "Direction/range check: perimenopause should reduce ovulation frequency."),
                    ValidationMetric(
                        "perimenopause_long_cycle_anovulatory_rate",
                        summary["long_cycle_anovulatory_rate"],
                        MENOPAUSE_TRANSITION_LONG_CYCLE_ANOVULATORY_TARGET,
                        PERIMENOPAUSE_LONG_CYCLE_ANOVULATORY_BOUNDS[0],
                        PERIMENOPAUSE_LONG_CYCLE_ANOVULATORY_BOUNDS[1],
                        PERIMENOPAUSE_LONG_CYCLE_ANOVULATORY_BOUNDS[0]
                        <= summary["long_cycle_anovulatory_rate"]
                        <= PERIMENOPAUSE_LONG_CYCLE_ANOVULATORY_BOUNDS[1],
                        "van_voorhis_2008_perimenopause",
                        "Direct published-context check: Van Voorhis reported 64.7% anovulation among intervals of at least 36 days; the broad interval allows cohort and simulator differences.",
                    ),
                    ValidationMetric(
                        "perimenopause_long_vs_ordinary_anovulation_delta",
                        summary["long_vs_ordinary_anovulation_delta"],
                        (
                            MENOPAUSE_TRANSITION_LONG_CYCLE_ANOVULATORY_TARGET
                            - MENOPAUSE_TRANSITION_ORDINARY_CYCLE_ANOVULATORY_TARGET
                        ),
                        PERIMENOPAUSE_LONG_VS_ORDINARY_ANOVULATION_DELTA_BOUNDS[0],
                        PERIMENOPAUSE_LONG_VS_ORDINARY_ANOVULATION_DELTA_BOUNDS[1],
                        (
                            PERIMENOPAUSE_LONG_VS_ORDINARY_ANOVULATION_DELTA_BOUNDS[0]
                            <= summary["long_vs_ordinary_anovulation_delta"]
                            <= PERIMENOPAUSE_LONG_VS_ORDINARY_ANOVULATION_DELTA_BOUNDS[1]
                        ),
                        "van_voorhis_2008_perimenopause",
                        (
                            "Direction/range check: Van Voorhis reported 64.7% anovulation in "
                            ">=36-day versus 8.1% in 21-35-day intervals. The exact contrast is "
                            "context, not a fitted target, because stage mixtures differ."
                        ),
                    ),
                ]
            )
        elif name == "peri_menarche":
            checks.extend(
                [
                    ValidationMetric("peri_menarche_long_cycles", summary["mean_cycle_days"], PERI_MENARCHE_VALIDATION_EXPECTED_CYCLE_LENGTH, PERI_MENARCHE_VALIDATION_MIN_CYCLE_LENGTH, 40.0, summary["mean_cycle_days"] >= PERI_MENARCHE_VALIDATION_MIN_CYCLE_LENGTH, "who_1986_adolescent_cycles", "Direction/range check: early post-menarche cycles should be longer on average."),
                    ValidationMetric("peri_menarche_irregularity", summary["irregularity_rate"], PERI_MENARCHE_VALIDATION_EXPECTED_IRREGULARITY, PERI_MENARCHE_VALIDATION_MIN_IRREGULARITY, 1.00, summary["irregularity_rate"] >= PERI_MENARCHE_VALIDATION_MIN_IRREGULARITY, "who_1986_adolescent_cycles", "Direction-only check: early post-menarche cycles should be more irregular."),
                    ValidationMetric("peri_menarche_lower_ovulation", summary["ovulation_rate"], PERI_MENARCHE_VALIDATION_EXPECTED_OVULATION_RATE, 0.30, PERI_MENARCHE_VALIDATION_MAX_OVULATION, summary["ovulation_rate"] <= PERI_MENARCHE_VALIDATION_MAX_OVULATION, "venturoli_1986_menarche", "Direction/range check: adolescents with irregular menses should be frequently anovulatory; this is not a universal perimenarche estimate."),
                ]
            )
        elif name == "dysmenorrhea":
            checks.extend(
                [
                    ValidationMetric("dysmenorrhea_preserved_ovulation", summary["ovulation_rate"], matched_baseline["ovulation_rate"], matched_baseline["ovulation_rate"] - DYSMENORRHEA_VALIDATION_MAX_OVULATION_DELTA, matched_baseline["ovulation_rate"] + DYSMENORRHEA_VALIDATION_MAX_OVULATION_DELTA, abs(summary["ovulation_rate"] - matched_baseline["ovulation_rate"]) <= DYSMENORRHEA_VALIDATION_MAX_OVULATION_DELTA, "dawood_2006_dysmenorrhea", "Direction-only check: primary dysmenorrhea should preserve ovulation versus an age-matched baseline."),
                    ValidationMetric("dysmenorrhea_bleeding_shift", summary["mean_bleeding_days"], matched_baseline["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[0], matched_baseline["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[0], matched_baseline["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[1], matched_baseline["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[0] <= summary["mean_bleeding_days"] <= matched_baseline["mean_bleeding_days"] + DYSMENORRHEA_VALIDATION_BLEEDING_DELTA_BOUNDS[1], "dawood_2006_dysmenorrhea", "Investigator-bounded check: dysmenorrhea should only mildly shift bleeding duration versus an age-matched baseline."),
                ]
            )

        results["subgroups"][name] = {
            "evaluation_type": "secondary direction/range software stress test",
            "age_range": list(age_range),
            "matched_baseline": matched_baseline,
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
    start_mode: str = DIARY_START_RANDOM,
) -> Dict[str, object]:
    """Run the full population validation workflow and optional subgroup checks.

    Args:
        num_patients: Number of women in the baseline validation cohort.
        days: Diary length in days for each simulated patient.
        seed: Random seed for reproducibility.
        include_subgroups: Whether to run factor-specific subgroup validation after the baseline
            cohort passes.
        start_mode: First-cycle observation rule used for all simulated diaries.

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
        # Distributional morphology checks need substantially more than the legacy
        # two diaries per age band.  Twenty per band remains a tiny retained subset
        # of the 10,000-person cohort while stabilizing SD and correlation guards.
        capture_limit=160,
        start_mode=start_mode,
        age_range=BASELINE_VALIDATION_AGE_RANGE,
    )
    cycles = population["cycles"]
    waveform_diagnostics: Dict[str, object] = {}
    calibration_metrics = (
        _age_band_metrics(cycles)
        + _overall_cycle_metrics(cycles)
        + _hormone_metrics(population["sample_diaries"], waveform_diagnostics)
    )
    waveform_metrics = [
        metric
        for metric in calibration_metrics
        if metric.name.startswith(("estradiol_", "progesterone_"))
    ]
    external_metrics = _external_cycle_metrics(cycles)
    metrics = calibration_metrics + external_metrics
    calibration_passed = all(metric.passed for metric in calibration_metrics)
    waveform_validation_passed = all(metric.passed for metric in waveform_metrics)
    external_crosscheck_passed = all(metric.passed for metric in external_metrics)
    baseline_passed = calibration_passed and external_crosscheck_passed
    hormone_sample_age_bands: Dict[str, int] = {}
    for diary in population["sample_diaries"]:
        label = age_band_for(float(diary["profile"]["age_years"])).label
        hormone_sample_age_bands[label] = hormone_sample_age_bands.get(label, 0) + 1
    report: Dict[str, object] = {
        "simulator_version": SIMULATOR_VERSION,
        "validation_schema_version": VALIDATION_SCHEMA_VERSION,
        "input": {
            "num_patients": num_patients,
            "days": days,
            "seed": seed,
            "diary_start_mode": start_mode,
            "age_range": list(BASELINE_VALIDATION_AGE_RANGE),
        },
        "evaluation_scope": (
            "AWHS/Bull target reproduction plus held-out Flo cycle checks; complete Stricker "
            "mapping is audited as construction fidelity, Anckaert provides independent serum "
            "subphase checks, Roos motivates timing-heterogeneity guards, and Van Voorhis "
            "constrains long-cycle/anovulation dependence in perimenopause."
        ),
        "additional_validation_requirements": [
            {
                "requirement": "Complete in-cycle Stricker E2 mapping and follicular-area fidelity",
                "evidence_role": "direct construction-fidelity check",
                "reason": (
                    "Stricker reports daily LH-aligned medians; the prior filter omitted the "
                    "early/mid-follicular observations and concealed an early, inflated ramp."
                ),
                "citation_key": "stricker_2006_reference",
            },
            {
                "requirement": "Nonzero E2/P4 peak-timing and relative-shape dispersion",
                "evidence_role": "literature-informed investigator-set plausibility guard",
                "reason": (
                    "Roos observed heterogeneous serum hormone signal characteristics relative "
                    "to ultrasound-confirmed ovulation; exact simulator SD bounds are not direct "
                    "published estimates."
                ),
                "citation_key": "roos_2015_true_ovulation",
            },
            {
                "requirement": "Two-sided terminal P4 ratio and final within-cycle drop check",
                "evidence_role": "direct source-shape and boundary-integrity check",
                "reason": (
                    "The Stricker LH+14 median remains above the early-follicular baseline; "
                    "checking only the cross-cycle jump can miss a reset shifted one day earlier."
                ),
                "citation_key": "stricker_2006_reference",
            },
            {
                "requirement": "Perimenopausal long intervals enriched for anovulation",
                "evidence_role": (
                    "published conditional-rate context plus investigator-bounded directional "
                    "joint-dependence check"
                ),
                "reason": (
                    "Van Voorhis reported 64.7% anovulation among intervals of at least 36 days "
                    "versus 8.1% among 21-35-day intervals; both the long-cycle posterior and a "
                    "positive long-versus-ordinary contrast are shown. O'Connor confirms that "
                    "long ovulatory cycles remain possible minorities."
                ),
                "citation_key": "van_voorhis_2008_perimenopause",
            },
        ],
        "hormone_smoke_sample": {
            "n_diaries": len(population["sample_diaries"]),
            "age_band_counts": hormone_sample_age_bands,
        },
        "waveform_diagnostics": waveform_diagnostics,
        "baseline_passed": baseline_passed,
        "calibration_passed": calibration_passed,
        "waveform_validation_passed": waveform_validation_passed,
        "external_crosscheck_passed": external_crosscheck_passed,
        "calibration_metrics": [metric.to_dict() for metric in calibration_metrics],
        "external_crosscheck_metrics": [metric.to_dict() for metric in external_metrics],
        "baseline_metrics": [metric.to_dict() for metric in metrics],
        "citations": {key: asdict(value) for key, value in CITATIONS.items()},
    }
    if baseline_passed and include_subgroups:
        report["subgroup_analysis"] = _subgroup_analysis(
            seed=seed,
            days=days,
            start_mode=start_mode,
        )
        subgroup_validation_passed = all(
            payload["passed"]
            for payload in report["subgroup_analysis"]["subgroups"].values()
        )
        report["subgroup_validation_passed"] = subgroup_validation_passed
        report["all_validation_passed"] = baseline_passed and subgroup_validation_passed
    else:
        report["subgroup_validation_passed"] = None
        report["all_validation_passed"] = baseline_passed
    return report


def write_validation_report(payload: Dict[str, object], output_path: Path) -> None:
    """Write a validation report dictionary to disk as JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
