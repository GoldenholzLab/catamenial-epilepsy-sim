#!/usr/bin/env python3
"""Audit the surrogate used to initialize healthy-cycle variability calibration.

The optimizer matches four Apple Women's Health Study outcomes for each age
band: pooled within-participant SD, participant prevalence with mean absolute
adjacent-cycle difference >=7 days, and the short/long cycle tails.  It uses 11
cycles per synthetic participant, the published median follow-up in Li et al.
2023. This fast surrogate supplies starting values for full-model refinement;
the production parameters are accepted or rejected only by the complete
population validation. The output is an audit artifact and never rewrites
source constants.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hormone_cycler.hormone_constants import (  # noqa: E402
    ANOVULATORY_MEAN_SHIFT_REPRODUCTIVE_DAYS,
    ANOVULATORY_SIGMA_MULTIPLIER,
    BASELINE_AGE_OVULATION_PROBABILITIES,
    CYCLE_LENGTH_LOGNORMAL_SHIFT_DAYS,
    IRREGULARITY_THRESHOLD_DAYS,
    MAX_CYCLE_LENGTH_DAYS,
    MIN_CYCLE_LENGTH_DAYS,
)
from hormone_cycler.literature import AGE_BAND_TARGETS  # noqa: E402


def ovulation_probability(age: float) -> float:
    """Return the baseline reproductive-stage probability for a representative age."""

    for low, high, probability in BASELINE_AGE_OVULATION_PROBABILITIES:
        if low <= age < high:
            return probability
    return BASELINE_AGE_OVULATION_PROBABILITIES[-1][2]


def sigma_curve(
    mean_days: float,
    sigma_grid: np.ndarray,
    ovulation_probability_value: float,
    normal_draws: np.ndarray,
    ovulation_draws: np.ndarray,
    episode_draws: np.ndarray,
    long_cycle_episode_probability: float,
    long_cycle_episode_extension_days: float,
) -> dict[str, np.ndarray]:
    """Evaluate outcome curves as a function of one latent personal SD."""

    pooled_sd: list[float] = []
    irregularity: list[float] = []
    short_tail: list[float] = []
    long_tail: list[float] = []
    is_ovulatory = ovulation_draws < ovulation_probability_value
    # The production model compensates the latent mean for both expected
    # anovulatory lengthening and any explicit older-age long-cycle episode.
    # Reproduce that compensation here so the audit evaluates the implemented
    # data-generating process rather than a nearby approximation.
    compensated_mean = mean_days
    compensated_mean -= (
        long_cycle_episode_probability * long_cycle_episode_extension_days
    )
    compensated_mean -= (
        (1.0 - ovulation_probability_value)
        * ANOVULATORY_MEAN_SHIFT_REPRODUCTIVE_DAYS
    )
    has_long_episode = episode_draws < long_cycle_episode_probability
    for sigma in sigma_grid:
        realized_mean = np.where(
            is_ovulatory,
            compensated_mean,
            compensated_mean + ANOVULATORY_MEAN_SHIFT_REPRODUCTIVE_DAYS,
        )
        realized_sigma = np.where(
            is_ovulatory,
            sigma,
            sigma * ANOVULATORY_SIGMA_MULTIPLIER,
        )
        residual_mean = realized_mean - CYCLE_LENGTH_LOGNORMAL_SHIFT_DAYS
        log_variance = np.log1p((realized_sigma / residual_mean) ** 2)
        log_mean = np.log(residual_mean) - 0.5 * log_variance
        values = CYCLE_LENGTH_LOGNORMAL_SHIFT_DAYS + np.exp(
            log_mean + np.sqrt(log_variance) * normal_draws
        )
        values = values + np.where(
            has_long_episode, long_cycle_episode_extension_days, 0.0
        )
        values = np.clip(
            np.rint(values), MIN_CYCLE_LENGTH_DAYS, MAX_CYCLE_LENGTH_DAYS
        )
        centered = values - values.mean(axis=1, keepdims=True)
        pooled_sd.append(
            math.sqrt(float(np.square(centered).sum()) / (values.size - len(values)))
        )
        mean_absolute_difference = np.abs(np.diff(values, axis=1)).mean(axis=1)
        irregularity.append(
            float(np.mean(mean_absolute_difference >= IRREGULARITY_THRESHOLD_DAYS))
        )
        short_tail.append(float(np.mean(values < 24)))
        long_tail.append(float(np.mean(values > 38)))
    return {
        "pooled_sd": np.maximum.accumulate(np.asarray(pooled_sd)),
        "irregularity": np.asarray(irregularity),
        "short_tail": np.asarray(short_tail),
        "long_tail": np.asarray(long_tail),
    }


def fit_band(
    target: Any,
    normal_draws: np.ndarray,
    ovulation_draws: np.ndarray,
    episode_draws: np.ndarray,
) -> dict[str, Any]:
    """Fit one low/high SD mixture by deterministic grid search."""

    representative_age = (target.age_min + target.age_max) / 2.0
    sigma_grid = np.geomspace(0.25, 40.0, 180)
    curves = sigma_curve(
        target.mean_cycle_days,
        sigma_grid,
        ovulation_probability(representative_age),
        normal_draws,
        ovulation_draws,
        episode_draws,
        target.long_cycle_episode_probability,
        target.long_cycle_episode_extension_days,
    )

    def interp(metric: str, sigma: float) -> float:
        return float(np.interp(sigma, sigma_grid, curves[metric]))

    best: tuple[float, dict[str, Any]] | None = None
    for high_probability in np.linspace(0.01, 0.99, 197):
        for low_sigma in np.geomspace(0.25, max(0.30, target.within_person_sd_days), 160):
            low_pooled = interp("pooled_sd", low_sigma)
            needed_high_variance = (
                target.within_person_sd_days**2
                - (1.0 - high_probability) * low_pooled**2
            ) / high_probability
            if needed_high_variance <= low_pooled**2:
                continue
            needed_high_sd = math.sqrt(needed_high_variance)
            if needed_high_sd > curves["pooled_sd"][-1]:
                continue
            high_sigma = float(
                np.interp(needed_high_sd, curves["pooled_sd"], sigma_grid)
            )
            irregularity = (
                (1.0 - high_probability) * interp("irregularity", low_sigma)
                + high_probability * interp("irregularity", high_sigma)
            )
            short_tail = (
                (1.0 - high_probability) * interp("short_tail", low_sigma)
                + high_probability * interp("short_tail", high_sigma)
            )
            long_tail = (
                (1.0 - high_probability) * interp("long_tail", low_sigma)
                + high_probability * interp("long_tail", high_sigma)
            )
            loss = (
                ((irregularity - target.irregular_participant_probability) / 0.002) ** 2
                + ((short_tail - target.short_cycle_probability) / 0.025) ** 2
                + ((long_tail - target.long_cycle_probability) / 0.025) ** 2
                + 0.002 * (high_sigma / low_sigma - 3.0) ** 2
            )
            payload: dict[str, Any] = {
                "age_band": target.label,
                "high_component_probability": round(float(high_probability), 6),
                "low_component_sigma_days": round(float(low_sigma), 6),
                "high_component_sigma_days": round(float(high_sigma), 6),
                "achieved_within_person_sd_days": target.within_person_sd_days,
                "achieved_irregular_participant_probability": round(irregularity, 6),
                "achieved_short_cycle_probability": round(short_tail, 6),
                "achieved_long_cycle_probability": round(long_tail, 6),
                "loss": round(float(loss), 6),
            }
            if best is None or loss < best[0]:
                best = (loss, payload)
    if best is None:
        raise RuntimeError(f"No feasible calibration for {target.label}")
    payload = best[1]
    implemented_probability = target.high_variability_component_probability
    implemented_low = target.low_component_sigma_days
    implemented_high = target.high_component_sigma_days
    payload["implemented_full_model_parameters"] = {
        "high_component_probability": implemented_probability,
        "low_component_sigma_days": implemented_low,
        "high_component_sigma_days": implemented_high,
    }
    payload["implemented_parameters_in_surrogate"] = {
        "within_person_sd_days": round(
            math.sqrt(
                (1.0 - implemented_probability) * interp("pooled_sd", implemented_low) ** 2
                + implemented_probability * interp("pooled_sd", implemented_high) ** 2
            ),
            6,
        ),
        "irregular_participant_probability": round(
            (1.0 - implemented_probability) * interp("irregularity", implemented_low)
            + implemented_probability * interp("irregularity", implemented_high),
            6,
        ),
        "short_cycle_probability": round(
            (1.0 - implemented_probability) * interp("short_tail", implemented_low)
            + implemented_probability * interp("short_tail", implemented_high),
            6,
        ),
        "long_cycle_probability": round(
            (1.0 - implemented_probability) * interp("long_tail", implemented_low)
            + implemented_probability * interp("long_tail", implemented_high),
            6,
        ),
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patients", type=int, default=40_000)
    parser.add_argument("--cycles", type=int, default=11)
    parser.add_argument("--seed", type=int, default=20_260_812)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    normal_draws = rng.standard_normal((args.patients, args.cycles))
    ovulation_draws = rng.random((args.patients, args.cycles))
    episode_draws = rng.random((args.patients, args.cycles))
    payload = {
        "method": "deterministic two-component shifted-lognormal surrogate grid search",
        "role": "initialization and sensitivity audit; not the final acceptance test",
        "limitations": (
            "The surrogate fixes the age-band mean and 11-cycle follow-up. It omits the full "
            "simulator's between-person mean distribution, random observation boundaries, and "
            "variable realized cycle counts. Production parameters were subsequently refined and "
            "are evaluated by the 10,000-participant full-model validation report."
        ),
        "seed": args.seed,
        "patients_per_age_band": args.patients,
        "cycles_per_participant": args.cycles,
        "source": "Li et al. 2023 AWHS Tables 4-5 and Supplementary Table 2",
        "fits": [
            fit_band(target, normal_draws, ovulation_draws, episode_draws)
            for target in AGE_BAND_TARGETS
        ],
    }
    rendered = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
