"""Shared dataclasses used across the simulator, validation, and visualization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MedicalFactors:
    """Supported clinical modifiers for the simulator."""

    pcos: bool = False
    oral_contraceptive_mode: Optional[str] = None
    hormonal_iud: bool = False
    copper_iud: bool = False
    perimenopause: bool = False
    peri_menarche: bool = False
    dysmenorrhea: bool = False

    def validate(self) -> None:
        """Validate that the selected factor combination is internally consistent."""

        modes = {None, "cyclic", "continuous"}
        if self.oral_contraceptive_mode not in modes:
            raise ValueError("oral_contraceptive_mode must be None, 'cyclic', or 'continuous'.")
        if self.hormonal_iud and self.copper_iud:
            raise ValueError("Only one IUD mode may be active at a time.")
        if self.oral_contraceptive_mode and (self.hormonal_iud or self.copper_iud):
            raise ValueError("Oral contraceptives and IUDs are mutually exclusive in this model.")

    def to_dict(self) -> Dict[str, object]:
        """Serialize the factor configuration to a plain dictionary."""

        return asdict(self)


@dataclass(frozen=True)
class PatientProfile:
    """Resolved patient-level latent parameters after age and factor calibration."""

    patient_id: str
    age_years: float
    medical_factors: MedicalFactors
    stage: str
    cycle_variability_component: str
    personal_cycle_mean_days: float
    personal_cycle_sigma_days: float
    ovulation_probability: float
    bleed_mean_days: float
    bleed_sigma_days: float
    estradiol_scale: float
    progesterone_scale: float
    noise_scale: float
    adaptation_months: int = 12

    def to_dict(self) -> Dict[str, object]:
        """Serialize the patient profile to a plain dictionary."""

        payload = asdict(self)
        payload["medical_factors"] = self.medical_factors.to_dict()
        return payload


@dataclass(frozen=True)
class DailyRecord:
    """One row in the daily diary."""

    patient_id: str
    day_index: int
    age_years: float
    cycle_index: int
    cycle_day: int
    cycle_length: int
    estradiol_pg_ml: float
    progesterone_ng_ml: float
    ovulation: int
    uterine_bleeding: int
    medical_factors: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Serialize the daily record to a plain dictionary."""

        return asdict(self)


@dataclass(frozen=True)
class CycleSummary:
    """Cycle-level summary statistics used for validation."""

    patient_id: str
    cycle_index: int
    age_years: float
    cycle_length: int
    follicular_length: int
    luteal_length: int
    ovulation_day: int
    ovulatory: bool
    bleeding_days: int
    stage: str
    medical_factors: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        """Serialize the cycle summary to a plain dictionary."""

        return asdict(self)


@dataclass
class SimulationResult:
    """Container returned by high-level simulation APIs."""

    profile: PatientProfile
    diary: List[DailyRecord]
    cycles: List[CycleSummary]

    def to_dict(self) -> Dict[str, object]:
        """Serialize the full simulation result to a nested dictionary."""

        return {
            "profile": self.profile.to_dict(),
            "diary": [row.to_dict() for row in self.diary],
            "cycles": [cycle.to_dict() for cycle in self.cycles],
        }
