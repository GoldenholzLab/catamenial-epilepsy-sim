"""Shared utilities for reproducible Paper 1 analysis runs."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RatioResult:
    """ADSF ratio result with explicit undefined states."""

    ratio: float | None
    numerator_adsf: float | None
    comparator_adsf: float | None
    indeterminate_reason: str | None = None

    @property
    def is_indeterminate(self) -> bool:
        return self.indeterminate_reason is not None


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON-compatible YAML config with a PyYAML fallback when installed."""

    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text)
    except Exception:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"Config at {config_path} must parse to a mapping.")
    return payload


def stable_seed(master_seed: int, *parts: object) -> int:
    """Derive a deterministic 32-bit seed from a master seed and stable identifiers."""

    key = "|".join([str(master_seed), *(str(part) for part in parts)])
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little") % (2**32 - 1)


def make_rng(master_seed: int, *parts: object) -> np.random.Generator:
    return np.random.default_rng(stable_seed(master_seed, *parts))


def safe_float(value: Any) -> float | None:
    """Convert scalar or one-element numpy values to plain floats."""

    if value is None:
        return None
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None
        return float(value.reshape(-1)[0])
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)


def adsf_ratio(
    numerator_count: float,
    numerator_days: int,
    comparator_count: float,
    comparator_days: int,
) -> RatioResult:
    """Compute an average-daily-seizure-frequency ratio with CE edge-case semantics."""

    if numerator_days <= 0:
        return RatioResult(None, None, None, "missing_numerator_phase")
    if comparator_days <= 0:
        return RatioResult(None, None, None, "missing_comparator_phase")
    numerator_adsf = float(numerator_count) / float(numerator_days)
    comparator_adsf = float(comparator_count) / float(comparator_days)
    if comparator_adsf == 0.0:
        if numerator_adsf > 0.0:
            return RatioResult(math.inf, numerator_adsf, comparator_adsf)
        return RatioResult(None, numerator_adsf, comparator_adsf, "undefined_zero_over_zero")
    return RatioResult(numerator_adsf / comparator_adsf, numerator_adsf, comparator_adsf)


def ratio_positive(ratio: RatioResult, threshold: float) -> tuple[bool | None, str | None]:
    """Return threshold positivity while preserving indeterminate ratios."""

    if ratio.is_indeterminate:
        return None, ratio.indeterminate_reason
    assert ratio.ratio is not None
    return bool(ratio.ratio >= threshold), None


def wilson_ci(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""

    if total <= 0:
        return (math.nan, math.nan)
    phat = successes / total
    denom = 1.0 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    half = z * math.sqrt((phat * (1.0 - phat) + z * z / (4 * total)) / total) / denom
    return max(0.0, center - half), min(1.0, center + half)


def first_reason(reasons: Iterable[str | None]) -> str | None:
    for reason in reasons:
        if reason:
            return reason
    return None


def month_denominator(n_days: int, days_per_month: float) -> float:
    if n_days <= 0:
        return math.nan
    return n_days / days_per_month


def elapsed_seconds(start: float) -> float:
    return time.perf_counter() - start


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(output_dir: str | Path, config: dict[str, Any], assumptions: list[str]) -> Path:
    """Write a machine-readable manifest for every output file currently in output_dir."""

    out = Path(output_dir)
    files: list[dict[str, Any]] = []
    for path in sorted(p for p in out.rglob("*") if p.is_file() and p.name != "manifest.json"):
        files.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
        )
    manifest = {
        "created_unix_time": time.time(),
        "output_dir": str(out),
        "files": files,
        "config": config,
        "assumptions": assumptions,
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path
