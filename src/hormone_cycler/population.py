"""Population simulation helpers built on the patient-level simulator."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Optional

from .literature import AGE_BAND_TARGETS
from .model import simulate_diary
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


def _sample_age_within_band(rng: random.Random, label: str) -> float:
    """Sample a representative age inside one validation age band.

    Args:
        rng: Random-number generator controlling reproducibility.
        label: Age-band label from the published target table.

    Returns:
        A one-decimal-place age in years.
    """

    band = next(target for target in AGE_BAND_TARGETS if target.label == label)
    if label == "<20":
        return round(rng.uniform(13.0, 19.9), 1)
    if label == "50+":
        return round(rng.uniform(50.0, 54.9), 1)
    return round(rng.uniform(band.age_min, band.age_max - 0.1), 1)


def simulate_population(
    num_patients: int,
    days: int,
    seed: Optional[int] = None,
    medical_factors: Optional[MedicalFactors] = None,
    balanced_age_bands: bool = True,
    include_diaries: bool = False,
    capture_limit: int = 25,
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
            is true.

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
    patient_counter = 0
    for label, count in counts.items():
        for _ in range(count):
            patient_counter += 1
            age = _sample_age_within_band(rng, label)
            patient_seed = rng.randint(0, 2**31 - 1)
            patient_id = f"patient-{patient_counter:05d}"
            result = simulate_diary(
                days=days,
                age_years=age,
                medical_factors=factors,
                seed=patient_seed,
                patient_id=patient_id,
            )
            profiles.append(result.profile.to_dict())
            cycles.extend(cycle.to_dict() for cycle in result.cycles)
            if include_diaries and len(diaries) < capture_limit:
                diaries.append(result.to_dict())

    return {
        "num_patients": num_patients,
        "days_per_patient": days,
        "balanced_age_bands": balanced_age_bands,
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
