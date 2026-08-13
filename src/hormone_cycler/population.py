"""Population simulation helpers built on the patient-level simulator."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .literature import AGE_BAND_TARGETS
from .model import (
    DIARY_START_RANDOM,
    build_patient_profile,
    domain_separated_rng,
    render_cycle_compact,
    select_diary_start_offset,
    simulate_diary,
)
from .types import MedicalFactors


def _balanced_band_counts(num_patients: int) -> Dict[str, int]:
    """Split a cohort size as evenly as possible across the published age bands.

    Args:
        num_patients: Total number of simulated women to allocate.

    Returns:
        Mapping from age-band label to patient count.
    """

    base = num_patients // len(AGE_BAND_TARGETS)
    remainder = num_patients % len(AGE_BAND_TARGETS)
    counts: Dict[str, int] = {}
    for index, target in enumerate(AGE_BAND_TARGETS):
        counts[target.label] = base + (1 if index < remainder else 0)
    return counts


def _sample_age_within_band(
    rng: random.Random,
    label: str,
    age_range: Optional[Tuple[float, float]] = None,
) -> float:
    """Sample a representative age inside one validation age band.

    Args:
        rng: Random-number generator controlling reproducibility.
        label: Age-band label from the published target table.
        age_range: Optional inclusive-lower, exclusive-upper sampling range. This lets a
            validation cohort reproduce an adult source population without changing the
            simulator's adolescent age band or the public population command.

    Returns:
        A one-decimal-place age in years.
    """

    band = next(target for target in AGE_BAND_TARGETS if target.label == label)
    default_low = 13.0 if label == "<20" else band.age_min
    default_high = 55.0 if label == "50+" else band.age_max
    low = max(default_low, age_range[0]) if age_range is not None else default_low
    high = min(default_high, age_range[1]) if age_range is not None else default_high
    if high <= low:
        raise ValueError(f"Age range {age_range!r} does not overlap age band {label!r}.")
    return round(rng.uniform(low, high - 0.1), 1)


def _simulate_profile_and_cycles_compact(
    days: int,
    age_years: float,
    medical_factors: MedicalFactors,
    seed: int,
    patient_id: str,
    start_mode: str,
) -> tuple[object, List[Dict[str, object]]]:
    """Return the exact full-render profile and cycle summaries without daily objects."""

    profile = build_patient_profile(
        age_years=age_years,
        medical_factors=medical_factors,
        seed=seed,
        patient_id=patient_id,
    )
    cycle_rng = domain_separated_rng(seed, patient_id=patient_id, stream="cycles")
    cycles: List[Dict[str, object]] = []
    observed_days = 0
    cycle_index = 1
    while observed_days < days:
        summary, _ = render_cycle_compact(profile, cycle_index, cycle_rng)
        cycles.append(summary.to_dict())
        start_offset = (
            select_diary_start_offset(
                summary.cycle_length,
                start_mode=start_mode,
                seed=seed,
                patient_id=patient_id,
            )
            if cycle_index == 1
            else 0
        )
        observed_days += min(days - observed_days, summary.cycle_length - start_offset)
        cycle_index += 1
    return profile, cycles


def simulate_population(
    num_patients: int,
    days: int,
    seed: Optional[int] = None,
    medical_factors: Optional[MedicalFactors] = None,
    balanced_age_bands: bool = True,
    include_diaries: bool = False,
    capture_limit: int = 25,
    start_mode: str = DIARY_START_RANDOM,
    age_range: Optional[Tuple[float, float]] = None,
    compact_non_capture: bool = True,
) -> Dict[str, object]:
    """Simulate a cohort of patients and aggregate their outputs.

    Args:
        num_patients: Number of patients to simulate.
        days: Diary length in days for each patient.
        seed: Optional random seed for reproducibility.
        medical_factors: Optional shared factor profile to apply to every patient.
        balanced_age_bands: Whether to allocate patients evenly across the published age bands.
        include_diaries: Whether to retain a limited number of full diary payloads.
        capture_limit: Maximum number of full diary payloads to retain when ``include_diaries``
            is true. Balanced-age simulations allocate this capture quota across age bands rather
            than taking only the first simulated band.
        start_mode: First-cycle observation rule passed to :func:`simulate_diary`.
        age_range: Optional inclusive-lower, exclusive-upper age range used when sampling
            within each balanced band. When ``balanced_age_bands`` is false, ages are sampled
            uniformly across this range. The default retains the simulator's 13.0--54.9-year
            population.
        compact_non_capture: Whether participants whose full diaries are not retained use the
            RNG-equivalent compact renderer. Set false only for equivalence auditing.

    Returns:
        Dictionary containing patient profiles, cycle summaries, and optional sample diaries.
    """

    if num_patients <= 0:
        raise ValueError("num_patients must be positive.")
    if days <= 0:
        raise ValueError("days must be positive.")

    rng = random.Random(seed)
    factors = medical_factors or MedicalFactors()
    counts = _balanced_band_counts(num_patients) if balanced_age_bands else {AGE_BAND_TARGETS[3].label: num_patients}

    profiles: List[Dict[str, object]] = []
    cycles: List[Dict[str, object]] = []
    diaries: List[Dict[str, object]] = []
    capture_targets = (
        _balanced_band_counts(capture_limit)
        if include_diaries and balanced_age_bands
        else {label: capture_limit for label in counts}
    )
    captured_by_band = {label: 0 for label in counts}
    patient_counter = 0
    for label, count in counts.items():
        for _ in range(count):
            patient_counter += 1
            if not balanced_age_bands and age_range is not None:
                low, high = age_range
                if high <= low:
                    raise ValueError("age_range upper bound must exceed its lower bound.")
                age = round(rng.uniform(low, high - 0.1), 1)
            else:
                age = _sample_age_within_band(rng, label, age_range=age_range)
            patient_seed = rng.randint(0, 2**31 - 1)
            patient_id = f"patient-{patient_counter:05d}"
            capture_this = bool(
                include_diaries
                and len(diaries) < capture_limit
                and captured_by_band[label] < capture_targets.get(label, 0)
            )
            if compact_non_capture and not capture_this:
                profile, patient_cycles = _simulate_profile_and_cycles_compact(
                    days=days,
                    age_years=age,
                    medical_factors=factors,
                    seed=patient_seed,
                    patient_id=patient_id,
                    start_mode=start_mode,
                )
                profiles.append(profile.to_dict())
                cycles.extend(patient_cycles)
            else:
                result = simulate_diary(
                    days=days,
                    age_years=age,
                    medical_factors=factors,
                    seed=patient_seed,
                    patient_id=patient_id,
                    start_mode=start_mode,
                )
                profiles.append(result.profile.to_dict())
                cycles.extend(cycle.to_dict() for cycle in result.cycles)
            if capture_this:
                diaries.append(result.to_dict())
                captured_by_band[label] += 1

    return {
        "num_patients": num_patients,
        "days_per_patient": days,
        "balanced_age_bands": balanced_age_bands,
        "diary_start_mode": start_mode,
        "age_range": list(age_range) if age_range is not None else [13.0, 55.0],
        "compact_non_capture": compact_non_capture,
        "medical_factors": factors.to_dict(),
        "profiles": profiles,
        "cycles": cycles,
        "sample_diaries": diaries,
    }


def write_population_json(payload: Dict[str, object], output_path: Path) -> None:
    """Serialize a population payload to JSON on disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
