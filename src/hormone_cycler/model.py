"""Core menstrual cycle simulator.

The simulator is intentionally hierarchical rather than purely waveform-based:

1. Sample patient-level latent traits constrained by large-scale cycle data.
2. Sample cycle-level realizations around those traits.
3. Interpolate daily estradiol and progesterone values from reference medians.

This keeps age effects, between-person variability, and within-person variability explicit.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from scipy.interpolate import PchipInterpolator

from .hormone_constants import (
    ANOVULATORY_ESTRADIOL_ANCHORS_PG_ML,
    ANOVULATORY_LATE_DAY_OFFSET,
    ANOVULATORY_MEAN_SHIFT_PERI_MENARCHE_DAYS,
    ANOVULATORY_MEAN_SHIFT_PERIMENOPAUSE_LONG_DAYS,
    ANOVULATORY_MEAN_SHIFT_PERIMENOPAUSE_SHORT_DAYS,
    ANOVULATORY_MEAN_SHIFT_REPRODUCTIVE_DAYS,
    ANOVULATORY_MIDPOINT_FRACTION,
    ANOVULATORY_PERIMENOPAUSE_LONG_CYCLE_PROBABILITY,
    ANOVULATORY_PROGESTERONE_ANCHORS_NG_ML,
    ANOVULATORY_SIGMA_MULTIPLIER,
    ANOVULATORY_STAGE_BLEED_MEAN_DELTA_DAYS,
    ANOVULATORY_STAGE_BLEED_SIGMA_DELTA_DAYS,
    ANOVULATORY_STAGE_SPOTTING_DURATION_DAYS,
    ANOVULATORY_STAGE_SPOTTING_PROBABILITY,
    ANOVULATORY_STAGE_SPOTTING_START_FRACTION,
    BASELINE_AGE_OVULATION_PROBABILITIES,
    BASELINE_BLEED_SIGMA_DAYS,
    BASELINE_ESTRADIOL_SCALE_CV,
    BASELINE_NOISE_SCALE,
    BASELINE_PROGESTERONE_SCALE_CV,
    BETWEEN_PERSON_SIGMA_BY_AGE,
    CONTINUOUS_OCP_AMENORRHEA_PROBABILITY,
    CONTINUOUS_OCP_BREAKTHROUGH_BLEED_MEAN_DAYS,
    CONTINUOUS_OCP_BREAKTHROUGH_BLEED_RANGE,
    CONTINUOUS_OCP_BREAKTHROUGH_BLEED_SIGMA_DAYS,
    CONTINUOUS_OCP_BREAKTHROUGH_START_RANGE,
    CONTINUOUS_OCP_CYCLE_SIGMA_DAYS,
    CONTINUOUS_OCP_ESTRADIOL_POINTS,
    CONTINUOUS_OCP_ESTRADIOL_SCALE,
    CONTINUOUS_OCP_PROGESTERONE_POINTS,
    CONTINUOUS_OCP_PROGESTERONE_SCALE,
    CONTINUOUS_OCP_BLEED_MEAN_DAYS,
    CONTINUOUS_OCP_BLEED_SIGMA_DAYS,
    COPPER_IUD_BLEED_MEAN_DELTA_DAYS,
    COPPER_IUD_BLEED_SIGMA_DELTA_DAYS,
    CYCLE_ESTRADIOL_SCALE_CV,
    CYCLE_LENGTH_LOGNORMAL_SHIFT_DAYS,
    CYCLE_PROGESTERONE_SCALE_CV,
    CYCLIC_OCP_BLEED_MEAN_DAYS,
    CYCLIC_OCP_BLEED_RANGE,
    CYCLIC_OCP_BLEED_SIGMA_DAYS,
    CYCLIC_OCP_CYCLE_SIGMA_DAYS,
    CYCLIC_OCP_ESTRADIOL_POINTS,
    CYCLIC_OCP_ESTRADIOL_SCALE,
    CYCLIC_OCP_PROGESTERONE_POINTS,
    CYCLIC_OCP_PROGESTERONE_SCALE,
    DYSMENORRHEA_BLEED_MEAN_DELTA_DAYS,
    DYSMENORRHEA_BLEED_SIGMA_DELTA_DAYS,
    EARLY_LUTEAL_FRACTION,
    EARLY_LUTEAL_MIN_OFFSET_DAYS,
    FAILED_FOLLICULAR_WAVE_PEAK_FRACTION,
    FOLLICULAR_MIDPOINT_FRACTION,
    HORMONE_NOISE_AR_COEFFICIENT,
    HORMONAL_IUD_AMENORRHEA_PROBABILITY,
    HORMONAL_IUD_BLEED_MEAN_DELTA_DAYS,
    HORMONAL_IUD_BLEED_SIGMA_DELTA_DAYS,
    HORMONAL_IUD_ESTRADIOL_SCALE_MULTIPLIER,
    HORMONAL_IUD_MAX_OVULATION_PROBABILITY,
    HORMONAL_IUD_MIN_BLEED_MEAN_DAYS,
    HORMONAL_IUD_MIN_BLEED_SIGMA_DAYS,
    HORMONAL_IUD_PROGESTERONE_SCALE_MULTIPLIER,
    LUTEAL_ROOM_BUFFER_DAYS,
    LUTEAL_SIGMA_DAYS,
    LH_PEAK_TO_OVULATION_DAYS,
    LONG_FOLLICULAR_FAILED_WAVE_SHARE,
    LONG_FOLLICULAR_PHASE_MIN_DAYS,
    MAX_BLEEDING_DAYS,
    MAX_CYCLE_LENGTH_DAYS,
    MAX_LUTEAL_LENGTH_DAYS,
    MID_LUTEAL_FRACTION,
    MID_LUTEAL_MIN_OFFSET_DAYS,
    MIN_CYCLE_LENGTH_DAYS,
    MIN_ESTRADIOL_PG_ML,
    MIN_FOLLICULAR_LENGTH_DAYS,
    MIN_LUTEAL_LENGTH_DAYS,
    MIN_PROGESTERONE_NG_ML,
    OCP_NOISE_SCALE,
    OCP_REFERENCE_CYCLE_LENGTH_DAYS,
    PCOS_BLEED_MEAN_DELTA_DAYS,
    PCOS_CYCLE_MEAN_MULTIPLIER_BY_AGE,
    PCOS_CYCLE_SIGMA_MULTIPLIER,
    PCOS_ESTRADIOL_SCALE_MULTIPLIER,
    PCOS_LUTEAL_MEAN_DELTA_DAYS,
    PCOS_LUTEAL_SIGMA_DELTA_DAYS,
    PCOS_NOISE_SCALE_MULTIPLIER,
    PCOS_OVULATION_MULTIPLIER,
    PCOS_PROGESTERONE_SCALE_MULTIPLIER,
    PERI_MENARCHE_BLEED_MEAN_DELTA_DAYS,
    PERI_MENARCHE_CYCLE_MEAN_DELTA_DAYS,
    PERI_MENARCHE_CYCLE_SIGMA_MULTIPLIER,
    PERI_MENARCHE_ESTRADIOL_SCALE_MULTIPLIER,
    PERI_MENARCHE_LUTEAL_MEAN_DELTA_DAYS,
    PERI_MENARCHE_LUTEAL_SIGMA_DELTA_DAYS,
    PERI_MENARCHE_MAX_OVULATION_PROBABILITY,
    PERI_MENARCHE_NOISE_SCALE_MULTIPLIER,
    PERI_MENARCHE_OVULATION_PROBABILITY_GTE16,
    PERI_MENARCHE_OVULATION_PROBABILITY_LT16,
    PERI_MENARCHE_PROGESTERONE_SCALE_MULTIPLIER,
    PERIMENOPAUSE_BLEED_MEAN_DELTA_DAYS,
    PERIMENOPAUSE_CYCLE_SIGMA_MULTIPLIER,
    PERIMENOPAUSE_LUTEAL_MEAN_DELTA_DAYS,
    PERIMENOPAUSE_LUTEAL_SIGMA_DELTA_DAYS,
    PERIMENOPAUSE_NOISE_SCALE_MULTIPLIER,
    PERIMENOPAUSE_OVULATION_MULTIPLIER,
    PERIMENOPAUSE_OVULATION_PROBABILITY_GTE52,
    PERIMENOPAUSE_OVULATION_PROBABILITY_LT52,
    PERIMENOPAUSE_PROGESTERONE_SCALE_MULTIPLIER,
    PLACEBO_WEEK_REFERENCE_DAY,
    PLACEBO_WEEK_START_DAY,
    PREMENSTRUAL_WITHDRAWAL_DAYS,
    PRE_OVULATION_PEAK_LEAD_DAYS,
    PROGESTERONE_NOISE_SCALE_MULTIPLIER,
    SERUM_REPORTING_DECIMALS,
    TERMINAL_FOLLICULAR_MATURATION_DAYS,
)
from .literature import BULL_PHASE_TARGETS, HORMONE_ANCHORS, STRICKER_DAILY_SERUM_REFERENCE
from .literature import age_band_for
from .types import CycleSummary, DailyRecord, MedicalFactors, PatientProfile, SimulationResult


DIARY_START_RANDOM = "random"
DIARY_START_CYCLE_DAY_1 = "cycle_day_1"
VALID_DIARY_START_MODES = {DIARY_START_RANDOM, DIARY_START_CYCLE_DAY_1}


def domain_separated_rng(
    seed: Optional[int],
    *,
    patient_id: str,
    stream: str,
) -> random.Random:
    """Create a reproducible RNG whose stream cannot overlap another model stage."""

    if seed is None:
        return random.Random()
    material = f"hormone-cycler|{stream}|{int(seed)}|{patient_id}".encode("utf-8")
    stream_seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return random.Random(stream_seed)


def clamp(value: float, low: float, high: float) -> float:
    """Clamp a numeric value into a closed interval.

    Args:
        value: The numeric value to constrain.
        low: Lower bound of the interval.
        high: Upper bound of the interval.

    Returns:
        The input value clipped to ``[low, high]``.
    """

    return max(low, min(high, value))


def select_diary_start_offset(
    cycle_length: int,
    *,
    start_mode: str = DIARY_START_RANDOM,
    seed: Optional[int] = None,
    patient_id: str = "patient-0001",
) -> int:
    """Select the zero-based observation offset within the first generated cycle.

    The default selects each day of the first cycle with equal probability. A
    domain-separated random stream is used so choosing the observation boundary
    does not consume values from the stream that generates patient and cycle
    characteristics.

    Args:
        cycle_length: Number of days in the first generated cycle.
        start_mode: ``"random"`` for a uniformly sampled phase or
            ``"cycle_day_1"`` to begin on cycle day 1.
        seed: Optional simulation seed. Supplying a seed makes the offset
            reproducible.
        patient_id: Participant identifier used to separate otherwise equal seeds.

    Returns:
        A zero-based index into the first cycle's daily records.
    """

    if cycle_length <= 0:
        raise ValueError("cycle_length must be positive.")
    if start_mode not in VALID_DIARY_START_MODES:
        allowed = ", ".join(sorted(VALID_DIARY_START_MODES))
        raise ValueError(f"start_mode must be one of: {allowed}.")
    if start_mode == DIARY_START_CYCLE_DAY_1:
        return 0
    if seed is None:
        return random.SystemRandom().randrange(cycle_length)

    seed_material = f"hormone-cycler-diary-start|{int(seed)}|{patient_id}".encode("utf-8")
    offset_seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
    return random.Random(offset_seed).randrange(cycle_length)


def truncated_gauss(
    rng: random.Random,
    mean: float,
    sigma: float,
    low: float,
    high: float,
) -> float:
    """Sample from a Gaussian distribution truncated to physiologic limits.

    Args:
        rng: Random-number generator controlling reproducibility.
        mean: Mean of the underlying Gaussian distribution.
        sigma: Standard deviation of the underlying Gaussian distribution.
        low: Minimum allowed return value.
        high: Maximum allowed return value.

    Returns:
        A sampled value inside the closed interval ``[low, high]``.
    """

    if sigma <= 0:
        return clamp(mean, low, high)
    for _ in range(128):
        sample = rng.gauss(mean, sigma)
        if low <= sample <= high:
            return sample
    return clamp(mean, low, high)


def sample_unit_lognormal(rng: random.Random, coefficient_of_variation: float) -> float:
    """Sample a multiplicative scale factor with expectation near one.

    Args:
        rng: Random-number generator controlling reproducibility.
        coefficient_of_variation: Desired coefficient of variation of the sampled factor.

    Returns:
        A positive log-normal scale factor centered near one.
    """

    if coefficient_of_variation <= 0:
        return 1.0
    sigma_sq = math.log1p(coefficient_of_variation ** 2)
    sigma = math.sqrt(sigma_sq)
    mu = -0.5 * sigma_sq
    return math.exp(rng.gauss(mu, sigma))


def bounded_shifted_lognormal(
    rng: random.Random,
    mean: float,
    sigma: float,
    low: float = MIN_CYCLE_LENGTH_DAYS,
    high: float = MAX_CYCLE_LENGTH_DAYS,
    shift: float = CYCLE_LENGTH_LOGNORMAL_SHIFT_DAYS,
) -> float:
    """Sample a right-skewed cycle length with a requested latent mean and SD.

    If ``Y = X - shift`` is lognormal, its two parameters are determined from
    ``E[X] = mean`` and ``SD[X] = sigma``.  The broad bounds are winsorization
    safeguards rather than calibration limits.  This distribution replaces the
    former symmetric Gaussian, which produced too many short cycles and too few
    long cycles for the same within-person variance.
    """

    residual_mean = max(mean - shift, 0.25)
    if sigma <= 0.0:
        return clamp(mean, low, high)
    log_variance = math.log1p((sigma / residual_mean) ** 2)
    log_sigma = math.sqrt(log_variance)
    log_mean = math.log(residual_mean) - 0.5 * log_variance
    sample = shift + math.exp(rng.gauss(log_mean, log_sigma))
    return clamp(sample, low, high)


def _normalized_control_points(
    points: Sequence[Tuple[float, float]],
) -> Tuple[List[float], List[float]]:
    """Return strictly increasing control-point coordinates for interpolation.

    When a very short phase makes two conceptual anchors coincide, the later anchor wins. This
    preserves the intended temporal ordering while satisfying the strict-coordinate requirement of
    shape-preserving cubic interpolation.
    """

    merged: Dict[float, float] = {}
    for x_value, y_value in points:
        merged[float(x_value)] = float(y_value)
    ordered = sorted(merged.items())
    if len(ordered) < 2:
        raise ValueError("At least two distinct hormone control points are required.")
    return [item[0] for item in ordered], [item[1] for item in ordered]


def shape_preserving_curve(
    points: Sequence[Tuple[float, float]],
) -> Callable[[float], float]:
    """Build a non-overshooting, continuously differentiable hormone curve.

    PCHIP interpolation preserves the direction of each adjacent control-point interval and avoids
    the overshoot that an unconstrained cubic spline could introduce near hormone maxima or low
    follicular baselines.
    """

    x_points, y_points = _normalized_control_points(points)
    interpolator = PchipInterpolator(x_points, y_points, extrapolate=False)

    def evaluate(x_value: float) -> float:
        if x_value <= x_points[0]:
            return y_points[0]
        if x_value >= x_points[-1]:
            return y_points[-1]
        return float(interpolator(float(x_value)))

    return evaluate


def smooth_piecewise(points: Sequence[Tuple[float, float]], x_value: float) -> float:
    """Evaluate the shape-preserving cubic curve through ordered control points.

    Args:
        points: Ordered ``(x, y)`` control points.
        x_value: X position at which to evaluate the interpolated curve.

    Returns:
        Interpolated y-value at ``x_value``. The legacy function name is retained for API
        compatibility; interpolation now uses a PCHIP curve rather than segment-wise smoothstep.
    """

    return shape_preserving_curve(points)(x_value)


def correlated_cycle_noise(
    cycle_length: int,
    rng: random.Random,
    estradiol_sigma: float,
    progesterone_sigma: float,
) -> Tuple[List[float], List[float]]:
    """Generate slowly varying fractional deviations anchored at both cycle boundaries.

    ``estradiol_sigma`` and ``progesterone_sigma`` are stationary standard deviations. Innovations
    are interleaved in the same order as the original daily renderer, keeping the random-stream
    consumption stable for subsequent cycle-level draws. A linear bridge removes the two endpoint
    values, preventing stochastic noise from reintroducing a cross-cycle reset.
    """

    if cycle_length <= 0:
        return [], []
    phi = HORMONE_NOISE_AR_COEFFICIENT
    innovation_factor = math.sqrt(max(0.0, 1.0 - phi * phi))
    estradiol_state = 0.0
    progesterone_state = 0.0
    estradiol_raw: List[float] = []
    progesterone_raw: List[float] = []
    for _ in range(cycle_length):
        estradiol_state = phi * estradiol_state + rng.gauss(
            0.0, estradiol_sigma * innovation_factor
        )
        progesterone_state = phi * progesterone_state + rng.gauss(
            0.0, progesterone_sigma * innovation_factor
        )
        estradiol_raw.append(estradiol_state)
        progesterone_raw.append(progesterone_state)

    if cycle_length == 1:
        return [0.0], [0.0]

    def bridge_to_zero(values: Sequence[float]) -> List[float]:
        first = values[0]
        last = values[-1]
        denominator = cycle_length - 1
        return [
            value - (first + (last - first) * index / denominator)
            for index, value in enumerate(values)
        ]

    return bridge_to_zero(estradiol_raw), bridge_to_zero(progesterone_raw)


def lookup_age_constant(age_years: float, ranges: Sequence[Tuple[float, float, float]]) -> float:
    """Select an age-stratified constant from a tuple of ``(low, high, value)`` ranges.

    Args:
        age_years: Age to classify.
        ranges: Inclusive-lower, exclusive-upper age ranges with attached values.

    Returns:
        The value associated with the first interval containing ``age_years``.
    """

    for age_min, age_max, constant_value in ranges:
        if age_min <= age_years < age_max:
            return constant_value
    return ranges[-1][2]


def age_stage(age_years: float, medical_factors: MedicalFactors) -> str:
    """Resolve the clinically dominant reproductive stage for a patient.

    Args:
        age_years: Chronologic age in years.
        medical_factors: User-specified medical modifiers.

    Returns:
        One of ``reproductive``, ``peri_menarche``, ``perimenopause``, or
        ``contraceptive_suppressed``.
    """

    if medical_factors.oral_contraceptive_mode:
        return "contraceptive_suppressed"
    if medical_factors.peri_menarche:
        return "peri_menarche"
    if medical_factors.perimenopause:
        return "perimenopause"
    return "reproductive"


def baseline_ovulation_probability(age_years: float, stage: str) -> float:
    """Return the baseline per-cycle probability of ovulation.

    Purpose:
        This function encodes age and stage effects on ovulation. The values are constrained by
        WHO Task Force 1986 and Venturoli et al. 1986 for peri-menarche, Santoro and
        Randolph 2011 for perimenopause,
        and the need to preserve the age-specific cycle-length targets from Li et al. 2023.

    Args:
        age_years: Chronologic age in years.
        stage: Reproductive stage string returned by :func:`age_stage`.

    Returns:
        Baseline probability that a simulated cycle is ovulatory.
    """

    if stage == "contraceptive_suppressed":
        return 0.0
    if stage == "peri_menarche":
        return PERI_MENARCHE_OVULATION_PROBABILITY_LT16 if age_years < 16.0 else PERI_MENARCHE_OVULATION_PROBABILITY_GTE16
    if stage == "perimenopause":
        return PERIMENOPAUSE_OVULATION_PROBABILITY_LT52 if age_years < 52.0 else PERIMENOPAUSE_OVULATION_PROBABILITY_GTE52
    return lookup_age_constant(age_years, BASELINE_AGE_OVULATION_PROBABILITIES)


def between_person_sigma(age_years: float) -> float:
    """Return the between-person cycle-length SD for a given age.

    Args:
        age_years: Chronologic age in years.

    Returns:
        A population-level standard deviation used when sampling each patient's latent mean cycle
        length. The values are calibration terms tied to the age-patterns reported by Li et al.
        2024.
    """

    return lookup_age_constant(age_years, BETWEEN_PERSON_SIGMA_BY_AGE)


def apply_factor_adjustments(
    age_years: float,
    medical_factors: MedicalFactors,
    personal_mean: float,
    personal_sigma: float,
    ovulation_probability: float,
    bleed_mean: float,
    bleed_sigma: float,
    estradiol_scale: float,
    progesterone_scale: float,
    noise_scale: float,
) -> Tuple[float, float, float, float, float, float, float, float]:
    """Apply condition-specific modifiers to a patient's latent parameters.

    Purpose:
        This function translates medical-factor flags into parameter shifts. The modifiers are
        constrained by the condition-specific studies summarized in ``hormone_constants.py``:
        Mortimer et al. 2026, Doi et al. 2005, and Jarrett et al. 2020 for PCOS; WHO Task
        Force 1986 and Venturoli et al. 1986 for
        peri-menarche, Santoro and Randolph 2011 for perimenopause, Edelman et al. 2014 for
        combined OCPs, Xiao et al. for levonorgestrel IUDs, Faundes et al. and Malmqvist et al. for copper IUDs,
        and Dawood 2006 for dysmenorrhea.

    Args:
        age_years: Chronologic age in years.
        medical_factors: Structured clinical modifiers requested by the caller.
        personal_mean: Current patient-level mean cycle length in days.
        personal_sigma: Current patient-level within-person cycle-length SD in days.
        ovulation_probability: Current per-cycle ovulation probability.
        bleed_mean: Current mean bleeding duration in days.
        bleed_sigma: Current bleeding-duration SD in days.
        estradiol_scale: Current patient-level estradiol amplitude scale.
        progesterone_scale: Current patient-level progesterone amplitude scale.
        noise_scale: Current day-to-day hormone noise scale.

    Returns:
        A tuple of the adjusted latent parameters in the same order they were provided.
    """

    if medical_factors.pcos:
        age_multiplier = lookup_age_constant(age_years, PCOS_CYCLE_MEAN_MULTIPLIER_BY_AGE)
        personal_mean *= age_multiplier
        personal_sigma *= PCOS_CYCLE_SIGMA_MULTIPLIER
        ovulation_probability *= PCOS_OVULATION_MULTIPLIER
        bleed_mean += PCOS_BLEED_MEAN_DELTA_DAYS
        estradiol_scale *= PCOS_ESTRADIOL_SCALE_MULTIPLIER
        progesterone_scale *= PCOS_PROGESTERONE_SCALE_MULTIPLIER
        noise_scale *= PCOS_NOISE_SCALE_MULTIPLIER

    if medical_factors.peri_menarche:
        personal_mean += PERI_MENARCHE_CYCLE_MEAN_DELTA_DAYS
        personal_sigma *= PERI_MENARCHE_CYCLE_SIGMA_MULTIPLIER
        ovulation_probability = min(ovulation_probability, PERI_MENARCHE_MAX_OVULATION_PROBABILITY)
        bleed_mean += PERI_MENARCHE_BLEED_MEAN_DELTA_DAYS
        estradiol_scale *= PERI_MENARCHE_ESTRADIOL_SCALE_MULTIPLIER
        progesterone_scale *= PERI_MENARCHE_PROGESTERONE_SCALE_MULTIPLIER
        noise_scale *= PERI_MENARCHE_NOISE_SCALE_MULTIPLIER

    if medical_factors.perimenopause:
        personal_sigma *= PERIMENOPAUSE_CYCLE_SIGMA_MULTIPLIER
        ovulation_probability *= PERIMENOPAUSE_OVULATION_MULTIPLIER
        bleed_mean += PERIMENOPAUSE_BLEED_MEAN_DELTA_DAYS
        progesterone_scale *= PERIMENOPAUSE_PROGESTERONE_SCALE_MULTIPLIER
        noise_scale *= PERIMENOPAUSE_NOISE_SCALE_MULTIPLIER

    if medical_factors.copper_iud:
        bleed_mean += COPPER_IUD_BLEED_MEAN_DELTA_DAYS
        bleed_sigma += COPPER_IUD_BLEED_SIGMA_DELTA_DAYS

    if medical_factors.hormonal_iud:
        ovulation_probability = min(ovulation_probability, HORMONAL_IUD_MAX_OVULATION_PROBABILITY)
        bleed_mean = max(HORMONAL_IUD_MIN_BLEED_MEAN_DAYS, bleed_mean + HORMONAL_IUD_BLEED_MEAN_DELTA_DAYS)
        bleed_sigma = max(HORMONAL_IUD_MIN_BLEED_SIGMA_DAYS, bleed_sigma + HORMONAL_IUD_BLEED_SIGMA_DELTA_DAYS)
        estradiol_scale *= HORMONAL_IUD_ESTRADIOL_SCALE_MULTIPLIER
        progesterone_scale *= HORMONAL_IUD_PROGESTERONE_SCALE_MULTIPLIER

    if medical_factors.dysmenorrhea:
        bleed_mean += DYSMENORRHEA_BLEED_MEAN_DELTA_DAYS
        bleed_sigma += DYSMENORRHEA_BLEED_SIGMA_DELTA_DAYS

    if medical_factors.oral_contraceptive_mode == "cyclic":
        personal_mean = OCP_REFERENCE_CYCLE_LENGTH_DAYS
        personal_sigma = CYCLIC_OCP_CYCLE_SIGMA_DAYS
        ovulation_probability = 0.0
        bleed_mean = CYCLIC_OCP_BLEED_MEAN_DAYS
        bleed_sigma = CYCLIC_OCP_BLEED_SIGMA_DAYS
        estradiol_scale = CYCLIC_OCP_ESTRADIOL_SCALE
        progesterone_scale = CYCLIC_OCP_PROGESTERONE_SCALE
        noise_scale = OCP_NOISE_SCALE

    if medical_factors.oral_contraceptive_mode == "continuous":
        personal_mean = OCP_REFERENCE_CYCLE_LENGTH_DAYS
        personal_sigma = CONTINUOUS_OCP_CYCLE_SIGMA_DAYS
        ovulation_probability = 0.0
        bleed_mean = CONTINUOUS_OCP_BLEED_MEAN_DAYS
        bleed_sigma = CONTINUOUS_OCP_BLEED_SIGMA_DAYS
        estradiol_scale = CONTINUOUS_OCP_ESTRADIOL_SCALE
        progesterone_scale = CONTINUOUS_OCP_PROGESTERONE_SCALE
        noise_scale = OCP_NOISE_SCALE

    return (
        personal_mean,
        personal_sigma,
        ovulation_probability,
        bleed_mean,
        bleed_sigma,
        estradiol_scale,
        progesterone_scale,
        noise_scale,
    )


def build_patient_profile(
    age_years: float,
    medical_factors: Optional[MedicalFactors] = None,
    seed: Optional[int] = None,
    patient_id: str = "patient-0001",
) -> PatientProfile:
    """Sample a patient-specific latent profile from age and factor inputs.

    Purpose:
        This function creates the reusable patient-level parameters that drive all simulated
        cycles: mean cycle length, within-person variability, bleeding behavior, ovulation
        probability, and hormone amplitudes. Li et al. 2023 and Bull et al. 2019 define the
        baseline timing targets; factor-specific studies modify the baseline.

    Args:
        age_years: Chronologic age in years.
        medical_factors: Optional medical modifiers to apply.
        seed: Optional random seed for reproducibility.
        patient_id: Identifier to attach to all output rows.

    Returns:
        A fully resolved :class:`PatientProfile`.
    """

    medical_factors = medical_factors or MedicalFactors()
    medical_factors.validate()
    stage = age_stage(age_years, medical_factors)
    rng = domain_separated_rng(seed, patient_id=patient_id, stream="profile")
    age_target = age_band_for(age_years)
    ovulation_probability = baseline_ovulation_probability(age_years, stage)
    variability_component = (
        "high"
        if rng.random() < age_target.high_variability_component_probability
        else "low"
    )
    personal_sigma = (
        age_target.high_component_sigma_days
        if variability_component == "high"
        else age_target.low_component_sigma_days
    )
    target_personal_mean = age_target.mean_cycle_days
    target_personal_mean -= (
        age_target.long_cycle_episode_probability
        * age_target.long_cycle_episode_extension_days
    )
    if stage == "reproductive":
        target_personal_mean -= (
            (1.0 - ovulation_probability) * ANOVULATORY_MEAN_SHIFT_REPRODUCTIVE_DAYS
        )
    personal_mean = truncated_gauss(
        rng,
        target_personal_mean,
        between_person_sigma(age_years),
        20.0,
        90.0,
    )
    bleed_mean = BULL_PHASE_TARGETS["mean_bleeding_days"]
    bleed_sigma = BASELINE_BLEED_SIGMA_DAYS
    estradiol_scale = sample_unit_lognormal(rng, BASELINE_ESTRADIOL_SCALE_CV)
    progesterone_scale = sample_unit_lognormal(rng, BASELINE_PROGESTERONE_SCALE_CV)
    noise_scale = BASELINE_NOISE_SCALE

    (
        personal_mean,
        personal_sigma,
        ovulation_probability,
        bleed_mean,
        bleed_sigma,
        estradiol_scale,
        progesterone_scale,
        noise_scale,
    ) = apply_factor_adjustments(
        age_years,
        medical_factors,
        personal_mean,
        personal_sigma,
        ovulation_probability,
        bleed_mean,
        bleed_sigma,
        estradiol_scale,
        progesterone_scale,
        noise_scale,
    )

    if medical_factors.oral_contraceptive_mode:
        variability_component = "contraceptive_suppressed"

    return PatientProfile(
        patient_id=patient_id,
        age_years=age_years,
        medical_factors=medical_factors,
        stage=stage,
        cycle_variability_component=variability_component,
        personal_cycle_mean_days=personal_mean,
        personal_cycle_sigma_days=personal_sigma,
        ovulation_probability=clamp(ovulation_probability, 0.0, 0.99),
        bleed_mean_days=max(0.0, bleed_mean),
        bleed_sigma_days=max(0.3, bleed_sigma),
        estradiol_scale=estradiol_scale,
        progesterone_scale=progesterone_scale,
        noise_scale=noise_scale,
    )


def sample_cycle_length(profile: PatientProfile, rng: random.Random, ovulatory: bool) -> int:
    """Sample the total length of one cycle for a patient.

    Args:
        profile: Patient-level latent parameters.
        rng: Random-number generator controlling reproducibility.
        ovulatory: Whether the cycle will ovulate.

    Returns:
        Total cycle length in integer days.
    """

    mean = profile.personal_cycle_mean_days
    sigma = profile.personal_cycle_sigma_days
    stage = profile.stage

    if profile.medical_factors.oral_contraceptive_mode:
        return int(OCP_REFERENCE_CYCLE_LENGTH_DAYS)

    if not ovulatory:
        sigma *= ANOVULATORY_SIGMA_MULTIPLIER
        if stage == "perimenopause":
            mean += (
                ANOVULATORY_MEAN_SHIFT_PERIMENOPAUSE_LONG_DAYS
                if rng.random() < ANOVULATORY_PERIMENOPAUSE_LONG_CYCLE_PROBABILITY
                else ANOVULATORY_MEAN_SHIFT_PERIMENOPAUSE_SHORT_DAYS
            )
        elif stage == "peri_menarche":
            mean += ANOVULATORY_MEAN_SHIFT_PERI_MENARCHE_DAYS
        else:
            mean += ANOVULATORY_MEAN_SHIFT_REPRODUCTIVE_DAYS

    sampled_length = bounded_shifted_lognormal(rng, mean, sigma)
    age_target = age_band_for(profile.age_years)
    if (
        age_target.long_cycle_episode_probability > 0.0
        and rng.random() < age_target.long_cycle_episode_probability
    ):
        sampled_length += age_target.long_cycle_episode_extension_days
    cycle_length = int(round(clamp(sampled_length, MIN_CYCLE_LENGTH_DAYS, MAX_CYCLE_LENGTH_DAYS)))
    return max(int(MIN_CYCLE_LENGTH_DAYS), cycle_length)


def sample_phase_lengths(
    profile: PatientProfile,
    cycle_length: int,
    ovulatory: bool,
    rng: random.Random,
) -> Tuple[int, int, int]:
    """Sample follicular length, luteal length, and ovulation day for one cycle.

    Purpose:
        Bull et al. 2019 showed that most cycle-length variability resides in the follicular
        phase. This function therefore samples the luteal phase from a relatively tight
        distribution and lets the follicular phase absorb the remaining variability.

    Args:
        profile: Patient-level latent parameters.
        cycle_length: Total cycle length in days.
        ovulatory: Whether the cycle will ovulate.
        rng: Random-number generator controlling reproducibility.

    Returns:
        A tuple of ``(follicular_length, luteal_length, ovulation_day)``.
    """

    if not ovulatory:
        return cycle_length, 0, 0

    # Bull et al. 2019 found most between-cycle variability in the follicular phase; the luteal
    # phase is therefore sampled from a relatively tight distribution and the follicular phase
    # absorbs the remaining cycle-length variability.
    luteal_mean = BULL_PHASE_TARGETS["luteal_mean_days"]
    luteal_sigma = LUTEAL_SIGMA_DAYS
    if profile.stage == "peri_menarche":
        luteal_mean += PERI_MENARCHE_LUTEAL_MEAN_DELTA_DAYS
        luteal_sigma += PERI_MENARCHE_LUTEAL_SIGMA_DELTA_DAYS
    if profile.stage == "perimenopause":
        luteal_mean += PERIMENOPAUSE_LUTEAL_MEAN_DELTA_DAYS
        luteal_sigma += PERIMENOPAUSE_LUTEAL_SIGMA_DELTA_DAYS
    if profile.medical_factors.pcos:
        luteal_mean += PCOS_LUTEAL_MEAN_DELTA_DAYS
        luteal_sigma += PCOS_LUTEAL_SIGMA_DELTA_DAYS

    max_luteal = min(
        int(MAX_LUTEAL_LENGTH_DAYS),
        max(int(MIN_LUTEAL_LENGTH_DAYS), cycle_length - LUTEAL_ROOM_BUFFER_DAYS),
    )
    luteal_length = int(round(truncated_gauss(rng, luteal_mean, luteal_sigma, MIN_LUTEAL_LENGTH_DAYS, float(max_luteal))))
    follicular_length = max(MIN_FOLLICULAR_LENGTH_DAYS, cycle_length - luteal_length)
    luteal_length = cycle_length - follicular_length
    ovulation_day = follicular_length
    return follicular_length, luteal_length, ovulation_day


def sample_bleeding_days(
    profile: PatientProfile,
    rng: random.Random,
    ovulatory: bool,
) -> int:
    """Sample the number of bleeding days in one cycle.

    Args:
        profile: Patient-level latent parameters.
        rng: Random-number generator controlling reproducibility.
        ovulatory: Whether the cycle will ovulate.

    Returns:
        Number of days with uterine bleeding in the cycle.
    """

    if profile.medical_factors.oral_contraceptive_mode == "cyclic":
        return int(round(truncated_gauss(rng, CYCLIC_OCP_BLEED_MEAN_DAYS, CYCLIC_OCP_BLEED_SIGMA_DAYS, *CYCLIC_OCP_BLEED_RANGE)))
    if profile.medical_factors.oral_contraceptive_mode == "continuous":
        if rng.random() < CONTINUOUS_OCP_AMENORRHEA_PROBABILITY:
            return 0
        return int(
            round(
                truncated_gauss(
                    rng,
                    CONTINUOUS_OCP_BREAKTHROUGH_BLEED_MEAN_DAYS,
                    CONTINUOUS_OCP_BREAKTHROUGH_BLEED_SIGMA_DAYS,
                    *CONTINUOUS_OCP_BREAKTHROUGH_BLEED_RANGE,
                )
            )
        )

    if profile.medical_factors.hormonal_iud and rng.random() < HORMONAL_IUD_AMENORRHEA_PROBABILITY:
        return 0

    mean = profile.bleed_mean_days
    sigma = profile.bleed_sigma_days
    if not ovulatory and profile.stage in {"peri_menarche", "perimenopause"}:
        mean += ANOVULATORY_STAGE_BLEED_MEAN_DELTA_DAYS
        sigma += ANOVULATORY_STAGE_BLEED_SIGMA_DELTA_DAYS
    return int(round(truncated_gauss(rng, mean, sigma, 0.0, MAX_BLEEDING_DAYS)))


def ovulatory_hormone_positions(
    cycle_length: int,
    follicular_length: int,
    luteal_length: int,
) -> Dict[str, int]:
    """Place the seven published sub-phase anchors within one realized cycle.

    The preovulatory maximum is centered two days before ovulation, and the late-luteal anchor is
    placed four days before the next bleeding onset. The final interval therefore represents a
    gradual steroid withdrawal rather than a vertical reset at the cycle boundary.
    """

    ovulation = int(follicular_length)
    follicular_mid = min(
        ovulation - 2,
        max(2, int(round(follicular_length * FOLLICULAR_MIDPOINT_FRACTION))),
    )
    pre_ovulatory = min(
        ovulation - 1,
        max(follicular_mid + 1, ovulation - PRE_OVULATION_PEAK_LEAD_DAYS),
    )

    late_luteal = max(ovulation + 3, cycle_length - PREMENSTRUAL_WITHDRAWAL_DAYS)
    mid_luteal = min(
        late_luteal - 1,
        ovulation
        + max(
            int(MID_LUTEAL_MIN_OFFSET_DAYS),
            int(round(luteal_length * MID_LUTEAL_FRACTION)),
        ),
    )
    early_luteal = min(
        mid_luteal - 1,
        ovulation
        + max(
            int(math.ceil(EARLY_LUTEAL_MIN_OFFSET_DAYS)),
            int(round(luteal_length * EARLY_LUTEAL_FRACTION)),
        ),
    )

    return {
        "early_follicular": 1,
        "mid_follicular": follicular_mid,
        "pre_ovulatory": pre_ovulatory,
        "ovulation": ovulation,
        "early_luteal": early_luteal,
        "mid_luteal": mid_luteal,
        "late_luteal": late_luteal,
    }


LONG_ESTRADIOL_DELAYED_EMERGENCE = "delayed_dominant_emergence"
LONG_ESTRADIOL_FAILED_WAVE = "failed_dominant_wave"


def long_follicular_estradiol_variant(
    profile: PatientProfile,
    cycle_index: int,
) -> str:
    """Select a documented long-follicular E2 geometry without consuming cycle RNG draws.

    Harlow et al. observed several heterogeneous urinary-oestrogen patterns in follicular phases
    lasting at least 24 days. The paper identifies delayed dominant-follicle emergence as the most
    common class but does not publish class frequencies in its abstract-accessible data. The model
    therefore uses delayed emergence by default and exposes a conservative 25% failed-wave class
    as an investigator-set heterogeneity component, not as an estimated prevalence.

    The selector hashes patient-level latent values already generated from the profile stream. It
    is reproducible and seed-sensitive while leaving the cycle RNG state—and therefore cycle length,
    phase timing, ovulation, bleeding, spotting, and noise streams—unchanged.
    """

    material = (
        f"hormone-cycler|long-e2-geometry|{profile.patient_id}|{cycle_index}|"
        f"{profile.age_years:.12g}|{profile.personal_cycle_mean_days:.12g}|"
        f"{profile.personal_cycle_sigma_days:.12g}|{profile.estradiol_scale:.12g}"
    ).encode("utf-8")
    unit_value = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") / 2**64
    if unit_value < LONG_FOLLICULAR_FAILED_WAVE_SHARE:
        return LONG_ESTRADIOL_FAILED_WAVE
    return LONG_ESTRADIOL_DELAYED_EMERGENCE


def _luteal_reference_day(
    lh_peak_day: float,
    lh_offset_days: int,
    cycle_length: int,
) -> float:
    """Map a Stricker LH-relative day into the realized luteal interval.

    Negative offsets retain their observed daily spacing. Positive offsets are scaled so the
    published +14-day tail reaches the final simulated day, allowing luteal-length variability to
    alter the envelope duration without moving the rise to before ovulation or creating a reset at
    the next menses.
    """

    if lh_offset_days <= 0:
        return lh_peak_day + lh_offset_days
    positive_scale = (float(cycle_length) - lh_peak_day) / 14.0
    return lh_peak_day + lh_offset_days * positive_scale


def _ovulatory_estradiol_points(
    cycle_length: int,
    follicular_length: int,
    estradiol_scale: float,
    estradiol_variant: str,
) -> List[Tuple[float, float]]:
    """Build an E2 envelope with an ovulation-anchored terminal maturation interval."""

    anchors = {anchor.name: anchor for anchor in HORMONE_ANCHORS}
    ovulation_day = float(follicular_length)
    lh_peak_day = ovulation_day - LH_PEAK_TO_OVULATION_DAYS
    early_value = anchors["early_follicular"].estradiol_pg_ml
    mid_value = anchors["mid_follicular"].estradiol_pg_ml
    preovulatory_value = anchors["pre_ovulatory"].estradiol_pg_ml
    points: List[Tuple[float, float]] = [(1.0, early_value * estradiol_scale)]

    if follicular_length >= LONG_FOLLICULAR_PHASE_MIN_DAYS:
        terminal_start = max(
            2.0,
            ovulation_day - float(TERMINAL_FOLLICULAR_MATURATION_DAYS),
        )
        if estradiol_variant not in {
            LONG_ESTRADIOL_DELAYED_EMERGENCE,
            LONG_ESTRADIOL_FAILED_WAVE,
        }:
            raise ValueError(f"Unsupported long-follicular estradiol variant: {estradiol_variant}")
        if estradiol_variant == LONG_ESTRADIOL_FAILED_WAVE and terminal_start >= 9.0:
            failed_peak_day = 2.0 + 0.42 * (terminal_start - 2.0)
            failed_resolution_day = 2.0 + 0.72 * (terminal_start - 2.0)
            points.extend(
                [
                    (
                        failed_peak_day,
                        preovulatory_value
                        * FAILED_FOLLICULAR_WAVE_PEAK_FRACTION
                        * estradiol_scale,
                    ),
                    (failed_resolution_day, early_value * 1.08 * estradiol_scale),
                ]
            )
        points.extend(
            [
                (terminal_start, early_value * estradiol_scale),
                (
                    max(terminal_start + 1.0, ovulation_day - 8.0),
                    mid_value * estradiol_scale,
                ),
            ]
        )
    else:
        follicular_mid = min(
            ovulation_day - 2.0,
            max(2.0, round(follicular_length * FOLLICULAR_MIDPOINT_FRACTION)),
        )
        points.append((follicular_mid, mid_value * estradiol_scale))

    points.append(
        (
            max(2.0, ovulation_day - PRE_OVULATION_PEAK_LEAD_DAYS),
            preovulatory_value * estradiol_scale,
        )
    )
    for reference in STRICKER_DAILY_SERUM_REFERENCE:
        if reference.lh_offset_days < -1:
            continue
        x_value = _luteal_reference_day(
            lh_peak_day,
            reference.lh_offset_days,
            cycle_length,
        )
        if 1.0 < x_value < float(cycle_length):
            points.append((x_value, reference.estradiol_pg_ml * estradiol_scale))
    points.append((float(cycle_length), early_value * estradiol_scale))
    return points


def _ovulatory_progesterone_points(
    cycle_length: int,
    follicular_length: int,
    progesterone_scale: float,
) -> List[Tuple[float, float]]:
    """Build a broad P4 envelope from all daily Stricker serum medians."""

    anchors = {anchor.name: anchor for anchor in HORMONE_ANCHORS}
    baseline = anchors["early_follicular"].progesterone_ng_ml
    lh_peak_day = float(follicular_length) - LH_PEAK_TO_OVULATION_DAYS
    points: List[Tuple[float, float]] = [(1.0, baseline * progesterone_scale)]
    for reference in STRICKER_DAILY_SERUM_REFERENCE:
        x_value = _luteal_reference_day(
            lh_peak_day,
            reference.lh_offset_days,
            cycle_length,
        )
        if 1.0 < x_value < float(cycle_length):
            points.append((x_value, reference.progesterone_ng_ml * progesterone_scale))
    points.append((float(cycle_length), baseline * progesterone_scale))
    return points


def ovulatory_hormone_points(
    cycle_length: int,
    follicular_length: int,
    luteal_length: int,
    estradiol_scale: float,
    progesterone_scale: float,
    estradiol_variant: str = LONG_ESTRADIOL_DELAYED_EMERGENCE,
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """Build estradiol and progesterone control points for an ovulatory cycle.

    Purpose:
        Stricker et al. 2006 reported daily LH-aligned serum medians. This function uses the full
        daily luteal E2/P4 series, aligns the LH peak before the simulator's ovulation marker, and
        scales only the post-LH interval to the realized luteal length. Long follicular phases use
        an ovulation-anchored terminal maturation segment rather than horizontal template stretch.

    Args:
        cycle_length: Total cycle length in days.
        follicular_length: Follicular-phase length in days.
        luteal_length: Luteal-phase length in days.
        estradiol_scale: Patient- and cycle-specific estradiol amplitude multiplier.
        progesterone_scale: Patient- and cycle-specific progesterone amplitude multiplier.
        estradiol_variant: Documented long-follicular E2 geometry. Ignored for ordinary cycles.

    Returns:
        Two ordered point lists: estradiol points and progesterone points.
    """

    del luteal_length  # Luteal duration is already encoded by cycle_length - follicular_length.
    estradiol_points = _ovulatory_estradiol_points(
        cycle_length,
        follicular_length,
        estradiol_scale,
        estradiol_variant,
    )
    progesterone_points = _ovulatory_progesterone_points(
        cycle_length,
        follicular_length,
        progesterone_scale,
    )
    return estradiol_points, progesterone_points


def anovulatory_hormone_points(
    cycle_length: int,
    estradiol_scale: float,
    progesterone_scale: float,
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """Build estradiol and progesterone control points for an anovulatory cycle.

    Purpose:
        Anovulatory cycles do not show the full luteal progesterone rise seen in Stricker et al.
        2006. The anchors here enforce a blunted progesterone curve and a moderate estradiol rise
        that stays consistent with peri-menarche and perimenopause endocrine literature.

    Args:
        cycle_length: Total cycle length in days.
        estradiol_scale: Patient- and cycle-specific estradiol amplitude multiplier.
        progesterone_scale: Patient- and cycle-specific progesterone amplitude multiplier.

    Returns:
        Two ordered point lists: estradiol points and progesterone points.
    """

    mid = max(3.0, cycle_length * ANOVULATORY_MIDPOINT_FRACTION)
    late = max(mid + 1.0, cycle_length - ANOVULATORY_LATE_DAY_OFFSET)
    estradiol_points = [
        (1.0, ANOVULATORY_ESTRADIOL_ANCHORS_PG_ML[0] * estradiol_scale),
        (mid, ANOVULATORY_ESTRADIOL_ANCHORS_PG_ML[1] * estradiol_scale),
        (late, ANOVULATORY_ESTRADIOL_ANCHORS_PG_ML[2] * estradiol_scale),
        (float(cycle_length), ANOVULATORY_ESTRADIOL_ANCHORS_PG_ML[3] * estradiol_scale),
    ]
    progesterone_points = [
        (1.0, ANOVULATORY_PROGESTERONE_ANCHORS_NG_ML[0] * progesterone_scale),
        (mid, ANOVULATORY_PROGESTERONE_ANCHORS_NG_ML[1] * progesterone_scale),
        (late, ANOVULATORY_PROGESTERONE_ANCHORS_NG_ML[2] * progesterone_scale),
        (float(cycle_length), ANOVULATORY_PROGESTERONE_ANCHORS_NG_ML[3] * progesterone_scale),
    ]
    return estradiol_points, progesterone_points


def contraceptive_points(mode: str) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """Return endogenous-equivalent hormone control points for OCP regimens.

    Args:
        mode: Either ``cyclic`` for 21/7 use or ``continuous`` for continuous active dosing.

    Returns:
        Two ordered point lists: estradiol points and progesterone points.
    """

    if mode == "cyclic":
        estradiol_points = list(CYCLIC_OCP_ESTRADIOL_POINTS)
        progesterone_points = list(CYCLIC_OCP_PROGESTERONE_POINTS)
        return estradiol_points, progesterone_points
    estradiol_points = list(CONTINUOUS_OCP_ESTRADIOL_POINTS)
    progesterone_points = list(CONTINUOUS_OCP_PROGESTERONE_POINTS)
    return estradiol_points, progesterone_points


def render_cycle(
    profile: PatientProfile,
    cycle_index: int,
    rng: random.Random,
) -> Tuple[List[DailyRecord], CycleSummary]:
    """Generate all daily records and the cycle summary for one synthetic cycle.

    Args:
        profile: Patient-level latent parameters.
        cycle_index: One-based cycle index within the diary.
        rng: Random-number generator controlling reproducibility.

    Returns:
        A tuple ``(records, summary)`` with daily diary rows and the cycle-level summary.
    """

    factors = profile.medical_factors
    if factors.oral_contraceptive_mode:
        cycle_length = int(OCP_REFERENCE_CYCLE_LENGTH_DAYS)
        follicular_length = 0
        luteal_length = 0
        ovulation_day = 0
        ovulatory = False
        bleeding_days = sample_bleeding_days(profile, rng, False)
        estradiol_points, progesterone_points = contraceptive_points(factors.oral_contraceptive_mode)
    else:
        ovulatory = rng.random() < profile.ovulation_probability
        cycle_length = sample_cycle_length(profile, rng, ovulatory)
        follicular_length, luteal_length, ovulation_day = sample_phase_lengths(profile, cycle_length, ovulatory, rng)
        bleeding_days = sample_bleeding_days(profile, rng, ovulatory)
        cycle_e2_scale = profile.estradiol_scale * sample_unit_lognormal(rng, CYCLE_ESTRADIOL_SCALE_CV)
        cycle_p4_scale = profile.progesterone_scale * sample_unit_lognormal(rng, CYCLE_PROGESTERONE_SCALE_CV)
        if ovulatory:
            estradiol_variant = long_follicular_estradiol_variant(profile, cycle_index)
            estradiol_points, progesterone_points = ovulatory_hormone_points(
                cycle_length,
                follicular_length,
                luteal_length,
                cycle_e2_scale,
                cycle_p4_scale,
                estradiol_variant,
            )
        else:
            estradiol_points, progesterone_points = anovulatory_hormone_points(
                cycle_length,
                cycle_e2_scale,
                cycle_p4_scale,
            )

    records: List[DailyRecord] = []
    spotting_window = None

    if not factors.oral_contraceptive_mode and not ovulatory and profile.stage in {"peri_menarche", "perimenopause"}:
        if rng.random() < ANOVULATORY_STAGE_SPOTTING_PROBABILITY:
            spotting_start = min(cycle_length, max(2, int(round(cycle_length * ANOVULATORY_STAGE_SPOTTING_START_FRACTION))))
            spotting_window = range(spotting_start, min(cycle_length + 1, spotting_start + ANOVULATORY_STAGE_SPOTTING_DURATION_DAYS))

    if factors.oral_contraceptive_mode == "continuous" and bleeding_days > 0:
        start_day = rng.randint(*CONTINUOUS_OCP_BREAKTHROUGH_START_RANGE)
        spotting_window = range(start_day, min(PLACEBO_WEEK_REFERENCE_DAY, start_day + bleeding_days))

    withdrawal_start = (
        max(PLACEBO_WEEK_START_DAY, PLACEBO_WEEK_REFERENCE_DAY - bleeding_days)
        if factors.oral_contraceptive_mode == "cyclic"
        else None
    )

    estradiol_curve = shape_preserving_curve(estradiol_points)
    progesterone_curve = shape_preserving_curve(progesterone_points)
    estradiol_noise, progesterone_noise = correlated_cycle_noise(
        cycle_length,
        rng,
        profile.noise_scale,
        profile.noise_scale * PROGESTERONE_NOISE_SCALE_MULTIPLIER,
    )

    for cycle_day in range(1, cycle_length + 1):
        noise_index = cycle_day - 1
        estradiol = estradiol_curve(float(cycle_day)) * (
            1.0 + estradiol_noise[noise_index]
        )
        progesterone = progesterone_curve(float(cycle_day)) * (
            1.0 + progesterone_noise[noise_index]
        )
        estradiol = max(MIN_ESTRADIOL_PG_ML, round(estradiol, SERUM_REPORTING_DECIMALS))
        progesterone = max(MIN_PROGESTERONE_NG_ML, round(progesterone, SERUM_REPORTING_DECIMALS))

        if factors.oral_contraceptive_mode == "cyclic":
            bleeding = int(withdrawal_start is not None and withdrawal_start <= cycle_day <= withdrawal_start + bleeding_days - 1)
        elif factors.oral_contraceptive_mode == "continuous":
            bleeding = int(spotting_window is not None and cycle_day in spotting_window)
        else:
            bleeding = int(cycle_day <= bleeding_days)
            if spotting_window is not None and cycle_day in spotting_window:
                bleeding = 1

        ovulation = int(ovulatory and cycle_day == ovulation_day)
        records.append(
            DailyRecord(
                patient_id=profile.patient_id,
                day_index=0,
                age_years=profile.age_years,
                cycle_index=cycle_index,
                cycle_day=cycle_day,
                cycle_length=cycle_length,
                estradiol_pg_ml=estradiol,
                progesterone_ng_ml=progesterone,
                ovulation=ovulation,
                uterine_bleeding=bleeding,
                medical_factors=factors.to_dict(),
            )
        )

    summary = CycleSummary(
        patient_id=profile.patient_id,
        cycle_index=cycle_index,
        age_years=profile.age_years,
        cycle_length=cycle_length,
        follicular_length=follicular_length,
        luteal_length=luteal_length,
        ovulation_day=ovulation_day,
        ovulatory=ovulatory,
        bleeding_days=sum(record.uterine_bleeding for record in records),
        stage=profile.stage,
        medical_factors=factors.to_dict(),
    )
    return records, summary


def render_cycle_compact(
    profile: PatientProfile,
    cycle_index: int,
    rng: random.Random,
) -> Tuple[CycleSummary, List[float]]:
    """Generate cycle structure and midluteal progesterone without daily rows.

    This path is intended for large analyses that retain only cycle structure.
    It deliberately executes the same stochastic draws, in the same order, as
    :func:`render_cycle`; therefore subsequent cycle lengths and all returned
    summary fields are identical for a shared profile and RNG state. Only the
    progesterone values needed to reproduce the adapter's ILP classification
    are evaluated and returned.
    """

    factors = profile.medical_factors
    if factors.oral_contraceptive_mode:
        cycle_length = int(OCP_REFERENCE_CYCLE_LENGTH_DAYS)
        follicular_length = 0
        luteal_length = 0
        ovulation_day = 0
        ovulatory = False
        bleeding_days = sample_bleeding_days(profile, rng, False)
        _, progesterone_points = contraceptive_points(factors.oral_contraceptive_mode)
    else:
        ovulatory = rng.random() < profile.ovulation_probability
        cycle_length = sample_cycle_length(profile, rng, ovulatory)
        follicular_length, luteal_length, ovulation_day = sample_phase_lengths(
            profile,
            cycle_length,
            ovulatory,
            rng,
        )
        bleeding_days = sample_bleeding_days(profile, rng, ovulatory)
        cycle_e2_scale = profile.estradiol_scale * sample_unit_lognormal(rng, CYCLE_ESTRADIOL_SCALE_CV)
        cycle_p4_scale = profile.progesterone_scale * sample_unit_lognormal(rng, CYCLE_PROGESTERONE_SCALE_CV)
        if ovulatory:
            _, progesterone_points = ovulatory_hormone_points(
                cycle_length,
                follicular_length,
                luteal_length,
                cycle_e2_scale,
                cycle_p4_scale,
            )
        else:
            _, progesterone_points = anovulatory_hormone_points(
                cycle_length,
                cycle_e2_scale,
                cycle_p4_scale,
            )

    spotting_window = None
    if not factors.oral_contraceptive_mode and not ovulatory and profile.stage in {"peri_menarche", "perimenopause"}:
        if rng.random() < ANOVULATORY_STAGE_SPOTTING_PROBABILITY:
            spotting_start = min(
                cycle_length,
                max(2, int(round(cycle_length * ANOVULATORY_STAGE_SPOTTING_START_FRACTION))),
            )
            spotting_window = range(
                spotting_start,
                min(cycle_length + 1, spotting_start + ANOVULATORY_STAGE_SPOTTING_DURATION_DAYS),
            )

    if factors.oral_contraceptive_mode == "continuous" and bleeding_days > 0:
        start_day = rng.randint(*CONTINUOUS_OCP_BREAKTHROUGH_START_RANGE)
        spotting_window = range(start_day, min(PLACEBO_WEEK_REFERENCE_DAY, start_day + bleeding_days))

    withdrawal_start = (
        max(PLACEBO_WEEK_START_DAY, PLACEBO_WEEK_REFERENCE_DAY - bleeding_days)
        if factors.oral_contraceptive_mode == "cyclic"
        else None
    )

    progesterone_curve = shape_preserving_curve(progesterone_points)
    _, progesterone_noise = correlated_cycle_noise(
        cycle_length,
        rng,
        profile.noise_scale,
        profile.noise_scale * PROGESTERONE_NOISE_SCALE_MULTIPLIER,
    )
    progesterone_values: List[float] = []
    realized_bleeding_days = 0
    for cycle_day in range(1, cycle_length + 1):
        progesterone = progesterone_curve(float(cycle_day)) * (
            1.0 + progesterone_noise[cycle_day - 1]
        )
        progesterone_values.append(
            max(MIN_PROGESTERONE_NG_ML, round(progesterone, SERUM_REPORTING_DECIMALS))
        )
        if factors.oral_contraceptive_mode == "cyclic":
            bleeding = int(
                withdrawal_start is not None
                and withdrawal_start <= cycle_day <= withdrawal_start + bleeding_days - 1
            )
        elif factors.oral_contraceptive_mode == "continuous":
            bleeding = int(spotting_window is not None and cycle_day in spotting_window)
        else:
            bleeding = int(cycle_day <= bleeding_days)
            if spotting_window is not None and cycle_day in spotting_window:
                bleeding = 1
        realized_bleeding_days += bleeding

    summary = CycleSummary(
        patient_id=profile.patient_id,
        cycle_index=cycle_index,
        age_years=profile.age_years,
        cycle_length=cycle_length,
        follicular_length=follicular_length,
        luteal_length=luteal_length,
        ovulation_day=ovulation_day,
        ovulatory=ovulatory,
        bleeding_days=realized_bleeding_days,
        stage=profile.stage,
        medical_factors=factors.to_dict(),
    )
    return summary, progesterone_values


def simulate_diary(
    days: int,
    age_years: float,
    medical_factors: Optional[MedicalFactors] = None,
    seed: Optional[int] = None,
    patient_id: str = "patient-0001",
    start_mode: str = DIARY_START_RANDOM,
) -> SimulationResult:
    """Generate a day-by-day hormone and bleeding diary for one synthetic patient.

    By default, diary day 1 is a uniformly selected day within simulated cycle 1.
    The diary then proceeds forward through the remainder of that cycle and through
    subsequently generated cycles without wrapping. ``start_mode="cycle_day_1"``
    retains the legacy behavior in which diary day 1 is cycle day 1. The final
    generated cycle may be only partly represented in the returned diary.

    Args:
        days: Exact number of daily records to return.
        age_years: Chronologic age in years.
        medical_factors: Optional medical modifiers to apply.
        seed: Optional random seed for reproducibility.
        patient_id: Identifier to attach to all output rows.
        start_mode: First-cycle observation rule. ``"random"`` samples a cycle
            day uniformly; ``"cycle_day_1"`` starts at cycle day 1.

    Returns:
        A :class:`SimulationResult` containing the patient profile, daily rows, and cycle-level
        summaries.
    """

    if days <= 0:
        raise ValueError("days must be positive.")
    if start_mode not in VALID_DIARY_START_MODES:
        allowed = ", ".join(sorted(VALID_DIARY_START_MODES))
        raise ValueError(f"start_mode must be one of: {allowed}.")

    profile = build_patient_profile(
        age_years=age_years,
        medical_factors=medical_factors,
        seed=seed,
        patient_id=patient_id,
    )
    rng = domain_separated_rng(seed, patient_id=patient_id, stream="cycles")
    diary: List[DailyRecord] = []
    cycles: List[CycleSummary] = []
    cycle_index = 1
    while len(diary) < days:
        # One loop iteration generates one complete cycle. The retention check below
        # clips only the final cycle's daily records to the exact requested diary length.
        cycle_records, cycle_summary = render_cycle(profile, cycle_index, rng)
        cycles.append(cycle_summary)
        start_offset = (
            select_diary_start_offset(
                len(cycle_records),
                start_mode=start_mode,
                seed=seed,
                patient_id=patient_id,
            )
            if cycle_index == 1
            else 0
        )
        for record in cycle_records[start_offset:]:
            if len(diary) >= days:
                break
            diary.append(
                DailyRecord(
                    patient_id=record.patient_id,
                    day_index=len(diary) + 1,
                    age_years=record.age_years,
                    cycle_index=record.cycle_index,
                    cycle_day=record.cycle_day,
                    cycle_length=record.cycle_length,
                    estradiol_pg_ml=record.estradiol_pg_ml,
                    progesterone_ng_ml=record.progesterone_ng_ml,
                    ovulation=record.ovulation,
                    uterine_bleeding=record.uterine_bleeding,
                    medical_factors=record.medical_factors,
                )
            )
        cycle_index += 1

    return SimulationResult(profile=profile, diary=diary, cycles=cycles)


def write_diary_csv(result: SimulationResult, output_path: Path) -> None:
    """Write the daily diary portion of a simulation result to CSV.

    Args:
        result: Simulation output from :func:`simulate_diary`.
        output_path: Destination CSV path.

    Returns:
        None. The file is written to ``output_path``.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result.diary[0].to_dict().keys()))
        writer.writeheader()
        for row in result.diary:
            writer.writerow(row.to_dict())


def write_result_json(result: SimulationResult, output_path: Path) -> None:
    """Write an entire simulation result payload to JSON.

    Args:
        result: Simulation output from :func:`simulate_diary`.
        output_path: Destination JSON path.

    Returns:
        None. The file is written to ``output_path``.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result.to_dict(), handle, indent=2)


def records_to_csv_rows(records: Iterable[DailyRecord]) -> List[Dict[str, object]]:
    """Convert diary records into plain dictionaries ready for CSV serialization.

    Args:
        records: Iterable of :class:`DailyRecord` values.

    Returns:
        A list of row dictionaries.
    """

    return [record.to_dict() for record in records]
