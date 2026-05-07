"""Thin adapter for the CHOCOLATES seizure diary simulator."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

from paper1_null_ce.core.utils import safe_float


@dataclass(frozen=True)
class SeizureSimulation:
    daily: pd.DataFrame
    metadata: dict[str, Any]


def _load_chocolates_module() -> ModuleType:
    """Load CHOCOLATES even if the source directory is not an installed package."""

    candidates = ["CHOCOLATES.realSim_turbo", "chocolates.realSim_turbo"]
    for name in candidates:
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
    src_root = Path(__file__).resolve().parents[2]
    module_path = src_root / "CHOCOLATES" / "realSim_turbo.py"
    if not module_path.exists():
        module_path = src_root / "chocolates" / "realSim_turbo.py"
    if not module_path.exists():
        raise ImportError("Could not locate CHOCOLATES realSim_turbo.py under src/.")
    spec = importlib.util.spec_from_file_location("paper1_chocolates_realsim_turbo", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import CHOCOLATES from {module_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ChocolatesAdapter:
    """Adapter around CHOCOLATES without changing simulator internals."""

    def __init__(self) -> None:
        self.module = _load_chocolates_module()
        self.api_name = self.module.__name__

    def simulate(
        self,
        participant_id: str,
        days: int,
        seed: int,
        default_seizure_frequency: float | None = None,
        suppress_infradian: bool = False,
    ) -> SeizureSimulation:
        rng = np.random.default_rng(seed)
        metadata: dict[str, Any] = {
            "participant_id": participant_id,
            "chocolates_api": self.api_name,
            "suppress_infradian": suppress_infradian,
        }

        if hasattr(self.module, "simulator_base"):
            default_arg = -1 if default_seizure_frequency is None else default_seizure_frequency
            result = self.module.simulator_base(
                sampRATE=1,
                number_of_days=days,
                cyclesTF=not suppress_infradian,
                defaultSeizureFreq=default_arg,
                returnDetails=True,
                rng=rng,
            )
            counts = np.asarray(result[0], dtype=np.int64)
            metadata.update(
                {
                    "mean_seizure_frequency_month": safe_float(result[1]),
                    "overdispersion": safe_float(result[2]),
                    "clustered": bool(result[8]) if len(result) > 8 else None,
                }
            )
            if len(result) > 6:
                freqs = np.asarray(result[5], dtype=float)
                amps = np.asarray(result[6], dtype=float)
                if freqs.size and amps.size:
                    periods = 1.0 / freqs
                    dominant_index = int(np.argmax(np.abs(amps)))
                    metadata["dominant_seizure_cycle_days"] = float(periods[dominant_index])
                    metadata["seizure_cycle_periods_days"] = periods.tolist()
                    metadata["seizure_cycle_amplitudes"] = amps.tolist()
                else:
                    metadata["dominant_seizure_cycle_days"] = None
            source = "simulator_base_returnDetails"
        elif hasattr(self.module, "simple_CHOCOLATES"):
            func = self.module.simple_CHOCOLATES
            kwargs: dict[str, Any] = {}
            params = inspect.signature(func).parameters
            if "defaultSeizureFreq" in params:
                kwargs["defaultSeizureFreq"] = default_seizure_frequency
            if "rng" in params:
                kwargs["rng"] = rng
            counts, mean_sf = func(days, **kwargs)
            counts = np.asarray(counts, dtype=np.int64)
            metadata["mean_seizure_frequency_month"] = safe_float(mean_sf)
            metadata["dominant_seizure_cycle_days"] = None
            source = "simple_CHOCOLATES"
        else:
            raise AttributeError("CHOCOLATES module has neither simulator_base nor simple_CHOCOLATES.")

        if counts.shape[0] != days:
            counts = counts[:days]
            if counts.shape[0] < days:
                counts = np.pad(counts, (0, days - counts.shape[0]))
        metadata["chocolates_source"] = source
        daily = pd.DataFrame(
            {
                "participant_id": participant_id,
                "calendar_day_index": np.arange(1, days + 1, dtype=np.int32),
                "seizure_count": counts.astype(np.int32),
            }
        )
        daily["seizure_day"] = (daily["seizure_count"] > 0).astype(np.int8)
        return SeizureSimulation(daily=daily, metadata=metadata)
