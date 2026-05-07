"""Thin adapter for the hormone_cycler menstrual/hormone simulator."""

from __future__ import annotations

import importlib
import random
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HormoneSimulation:
    daily: pd.DataFrame
    participant_summary: dict[str, Any]
    assumptions: list[str]


class HormoneCycleAdapter:
    """Adapter around hormone_cycler with cohort-specific sampling policy."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.model = importlib.import_module("hormone_cycler.model")
        self.types = importlib.import_module("hormone_cycler.types")
        self.MedicalFactors = getattr(self.types, "MedicalFactors")

    def sample_age(self, cohort: str, rng: np.random.Generator) -> float:
        cohort_cfg = self.config["cohorts"][cohort]
        lo, hi = cohort_cfg["age_range"]
        return round(float(rng.uniform(lo, hi)), 1)

    def sample_medical_factors(self, cohort: str, age: float, rng: np.random.Generator) -> Any:
        if cohort == "healthy_ovulatory":
            return self.MedicalFactors()

        rates = self.config.get("population_factor_rates", {})
        pcos = bool(rng.random() < float(rates.get("pcos", 0.0)))
        peri_menarche = bool(age < 20.0 and rng.random() < float(rates.get("peri_menarche_if_age_lt_20", 0.0)))
        perimenopause = bool(age >= 45.0 and rng.random() < float(rates.get("perimenopause_if_age_gte_45", 0.0)))
        dysmenorrhea = bool(rng.random() < float(rates.get("dysmenorrhea", 0.0)))
        return self.MedicalFactors(
            pcos=pcos,
            peri_menarche=peri_menarche,
            perimenopause=perimenopause,
            dysmenorrhea=dysmenorrhea,
        )

    def simulate(
        self,
        participant_id: str,
        cohort: str,
        days: int,
        seed: int,
    ) -> HormoneSimulation:
        rng = np.random.default_rng(seed)
        age = self.sample_age(cohort, rng)
        factors = self.sample_medical_factors(cohort, age, rng)
        assumptions: list[str] = []
        force_ovulatory = bool(self.config["cohorts"][cohort].get("force_ovulatory_cycles", False))
        if cohort == "population":
            assumptions.append(
                "The hormone simulator exposes medical-factor knobs but no natural prevalence sampler; "
                "population medical factors were sampled from config.yaml rates."
            )

        if force_ovulatory and all(hasattr(self.model, name) for name in ("build_patient_profile", "render_cycle")):
            records, cycles, profile = self._simulate_force_ovulatory(days, age, factors, seed, participant_id)
            assumptions.append(
                "Healthy ovulatory cohort used hormone_cycler build_patient_profile/render_cycle with "
                "ovulation_probability set to 1.0 because simulate_diary does not expose a public force-ovulation knob."
            )
        else:
            result = self.model.simulate_diary(
                days=days,
                age_years=age,
                medical_factors=factors,
                seed=seed,
                patient_id=participant_id,
            )
            records = [row.to_dict() for row in result.diary]
            cycles = [cycle.to_dict() for cycle in result.cycles]
            profile = result.profile

        daily = self._daily_frame(participant_id, records, cycles)
        summary = self._participant_summary(participant_id, cohort, age, profile, cycles, daily)
        return HormoneSimulation(daily=daily, participant_summary=summary, assumptions=assumptions)

    def _simulate_force_ovulatory(
        self,
        days: int,
        age: float,
        factors: Any,
        seed: int,
        participant_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Any]:
        profile = self.model.build_patient_profile(
            age_years=age,
            medical_factors=factors,
            seed=seed,
            patient_id=participant_id,
        )
        profile = replace(profile, ovulation_probability=1.0)
        rng_py = random.Random(seed)
        records: list[dict[str, Any]] = []
        cycles: list[dict[str, Any]] = []
        cycle_index = 1
        while len(records) < days:
            cycle_records, cycle_summary = self.model.render_cycle(profile, cycle_index, rng_py)
            cycles.append(cycle_summary.to_dict())
            for record in cycle_records:
                if len(records) >= days:
                    break
                payload = record.to_dict()
                payload["day_index"] = len(records) + 1
                records.append(payload)
            cycle_index += 1
        return records, cycles, profile

    def _daily_frame(
        self,
        participant_id: str,
        records: list[dict[str, Any]],
        cycles: list[dict[str, Any]],
    ) -> pd.DataFrame:
        df = pd.DataFrame.from_records(records)
        cycle_df = pd.DataFrame.from_records(cycles)
        cycle_lookup = cycle_df.set_index("cycle_index") if not cycle_df.empty else pd.DataFrame()
        df = df.rename(
            columns={
                "day_index": "calendar_day_index",
                "cycle_index": "cycle_id",
                "estradiol_pg_ml": "estradiol",
                "progesterone_ng_ml": "progesterone",
                "ovulation": "ovulation_flag",
                "uterine_bleeding": "uterine_bleeding_flag",
                "age_years": "age",
            }
        )
        df["participant_id"] = participant_id
        df["menses_onset_flag"] = (df["cycle_day"] == 1).astype(np.int8)
        if not cycle_lookup.empty:
            df["ovulatory_flag"] = df["cycle_id"].map(cycle_lookup["ovulatory"]).astype(bool)
            df["ovulation_day"] = df["cycle_id"].map(cycle_lookup["ovulation_day"]).fillna(0).astype(np.int16)
            df["cycle_stage"] = df["cycle_id"].map(cycle_lookup["stage"]).astype(str)
        else:
            df["ovulatory_flag"] = df["ovulation_flag"] > 0
            df["ovulation_day"] = 0
            df["cycle_stage"] = "unknown"
        df["cycle_id"] = df["cycle_id"].astype(np.int32)
        df["cycle_length"] = df["cycle_length"].astype(np.int16)
        df["calendar_day_index"] = df["calendar_day_index"].astype(np.int32)
        self._add_ilp_flags(df)
        return df

    def _add_ilp_flags(self, df: pd.DataFrame) -> None:
        threshold = float(self.config.get("ilp_progesterone_threshold_ng_ml", 5.0))
        ilp_by_cycle: dict[int, bool] = {}
        midp4_by_cycle: dict[int, float] = {}
        for cycle_id, g in df.groupby("cycle_id", sort=False):
            ovulatory = bool(g["ovulatory_flag"].iloc[0])
            ov_day = int(g["ovulation_day"].iloc[0]) if "ovulation_day" in g else 0
            if not ovulatory or ov_day <= 0 or "progesterone" not in g:
                ilp = True
                midp4 = float(g["progesterone"].max()) if "progesterone" in g else float("nan")
            else:
                mid = g[(g["cycle_day"] >= ov_day + 5) & (g["cycle_day"] <= ov_day + 9)]
                if mid.empty:
                    mid = g[g["cycle_day"] > ov_day]
                midp4 = float(mid["progesterone"].max()) if not mid.empty else float("nan")
                ilp = bool(midp4 < threshold)
            ilp_by_cycle[int(cycle_id)] = ilp
            midp4_by_cycle[int(cycle_id)] = midp4
        df["ilp_flag"] = df["cycle_id"].map(ilp_by_cycle).astype(bool)
        df["midluteal_progesterone"] = df["cycle_id"].map(midp4_by_cycle).astype(float)

    def _participant_summary(
        self,
        participant_id: str,
        cohort: str,
        age: float,
        profile: Any,
        cycles: list[dict[str, Any]],
        daily: pd.DataFrame,
    ) -> dict[str, Any]:
        cycle_df = pd.DataFrame.from_records(cycles)
        complete = cycle_df[cycle_df["cycle_length"].notna()] if not cycle_df.empty else cycle_df
        seizure_placeholder = {
            "seizure_count_total": 0,
            "seizure_days_total": 0,
            "seizure_days_per_month": np.nan,
            "seizures_per_month": np.nan,
        }
        factors = getattr(profile, "medical_factors", None)
        factors_dict = factors.to_dict() if hasattr(factors, "to_dict") else {}
        return {
            "participant_id": participant_id,
            "cohort": cohort,
            "age": age,
            "mean_cycle_length": float(complete["cycle_length"].mean()) if not complete.empty else np.nan,
            "sd_cycle_length": float(complete["cycle_length"].std(ddof=1)) if len(complete) > 1 else 0.0,
            "ovulatory_fraction": float(complete["ovulatory"].mean()) if "ovulatory" in complete else np.nan,
            "personal_cycle_mean_days": float(getattr(profile, "personal_cycle_mean_days", np.nan)),
            "personal_cycle_sigma_days": float(getattr(profile, "personal_cycle_sigma_days", np.nan)),
            "latent_cycle_regularity_metric": float(getattr(profile, "personal_cycle_sigma_days", np.nan)),
            "pcos": bool(factors_dict.get("pcos", False)),
            "peri_menarche": bool(factors_dict.get("peri_menarche", False)),
            "perimenopause": bool(factors_dict.get("perimenopause", False)),
            **seizure_placeholder,
        }
