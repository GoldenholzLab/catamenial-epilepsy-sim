"""Build draft-v5 supplemental tables, figures, and exploratory analyses.

The completed primary simulation outputs are treated as immutable.  All
derived artifacts are written below outputs/draft_v5_supplement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from matplotlib.ticker import PercentFormatter
from scipy.stats import norm

from paper1_null_ce.core.regression_nb import (
    classify_regression_nb_c3_exploratory,
    participant_alpha_from_full_diary,
)
from paper1_null_ce.core.utils import analysis_code_fingerprint, file_sha256


COHORT_LABELS = {
    "healthy_ovulatory": "Healthy ovulatory",
    "population": "Heterogeneous menstruating-age",
}
THRESHOLDS = {
    "C1": [0, 1, 1.69, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "C2": [0, 1, 1.83, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "C3": [0, 1, 1.62, 2, 3, 4, 5, 6, 7, 8, 9, 10],
}
COLORS = {"healthy_ovulatory": "#2a788e", "population": "#d1495b"}


def cumulative_herzog_table(window_results: pd.DataFrame) -> pd.DataFrame:
    """Summarize cumulative ratio distributions in strict three-cycle windows."""

    base = window_results[
        (window_results["phase_mode"] == "strict_herzog")
        & (window_results["window_type"] == "cycle")
        & (window_results["window_value"].astype(str) == "3")
    ].copy()
    key = ["participant_id", "cohort", "phase_mode", "window_type", "window_value"]
    duplicates = base.duplicated(key, keep=False)
    if duplicates.any():
        raise ValueError(f"duplicate three-cycle participant-window keys: {int(duplicates.sum())}")

    rows: list[dict[str, Any]] = []
    for pattern in ["C1", "C2", "C3"]:
        cohorts = ["population"] if pattern == "C3" else ["healthy_ovulatory", "population"]
        ratio_col = f"rr_{pattern}"
        label_col = f"label_A_windowed_{pattern}"
        for cohort in cohorts:
            group = base[base["cohort"] == cohort].copy()
            applicable = (
                group["c3_applicable_flag"].fillna(False).astype(bool)
                if pattern == "C3"
                else pd.Series(True, index=group.index)
            )
            applicable_group = group[applicable]
            defined = applicable_group[ratio_col].notna()
            defined_group = applicable_group[defined]
            n_attempted = int(len(group))
            n_applicable = int(len(applicable_group))
            n_defined = int(len(defined_group))
            n_undefined = n_applicable - n_defined
            for threshold in THRESHOLDS[pattern]:
                n_at_or_above = int((defined_group[ratio_col] >= threshold).sum())
                rows.append(
                    {
                        "panel": {"C1": "A", "C2": "B", "C3": "C"}[pattern],
                        "pattern": pattern,
                        "cohort": cohort,
                        "phase_mode": "strict_herzog",
                        "window_type": "cycle",
                        "window_value": 3,
                        "threshold": float(threshold),
                        "n_attempted": n_attempted,
                        "n_applicable": n_applicable,
                        "n_defined": n_defined,
                        "n_undefined": n_undefined,
                        "n_at_or_above": n_at_or_above,
                        "pct_defined_at_or_above": (
                            100.0 * n_at_or_above / n_defined if n_defined else np.nan
                        ),
                    }
                )
            canonical = {"C1": 1.69, "C2": 1.83, "C3": 1.62}[pattern]
            observed = int((defined_group[ratio_col] >= canonical).sum())
            labeled = int((applicable_group[label_col] == True).sum())  # noqa: E712
            if observed != labeled:
                raise AssertionError(
                    f"{pattern}/{cohort} threshold reconciliation failed: ratio={observed}, label={labeled}"
                )

    out = pd.DataFrame(rows)
    for (pattern, cohort), group in out.groupby(["pattern", "cohort"], sort=False):
        counts = group["n_at_or_above"].to_numpy()
        if np.any(np.diff(counts) > 0):
            raise AssertionError(f"nonmonotone cumulative counts for {pattern}/{cohort}")
        first = group.iloc[0]
        if int(first["n_at_or_above"]) != int(first["n_defined"]):
            raise AssertionError(f"threshold-zero denominator mismatch for {pattern}/{cohort}")
    return out


def c3_window_sensitivity(window_results: pd.DataFrame) -> pd.DataFrame:
    base = window_results[
        (window_results["phase_mode"] == "strict_herzog")
        & (window_results["cohort"] == "population")
    ].copy()
    rows: list[dict[str, Any]] = []
    for (window_type, window_value), group in base.groupby(["window_type", "window_value"], sort=False):
        applicable = group["c3_applicable_flag"].fillna(False).astype(bool)
        labels = group.loc[applicable, "label_A_windowed_C3"]
        classifiable = labels.notna()
        n_attempted = int(len(group))
        n_applicable = int(applicable.sum())
        n_classifiable = int(classifiable.sum())
        positives = int((labels[classifiable] == True).sum())  # noqa: E712
        low, high = wilson_interval(positives, n_classifiable)
        reasons = (
            group.loc[applicable & group["label_A_windowed_C3"].isna(), "a_windowed_reason"]
            .fillna("unspecified")
            .value_counts()
            .to_dict()
        )
        rows.append(
            {
                "cohort": "population",
                "window_type": window_type,
                "window_value": window_value,
                "n_attempted": n_attempted,
                "n_applicable": n_applicable,
                "n_classifiable": n_classifiable,
                "positives": positives,
                "false_positive_rate_classifiable": positives / n_classifiable if n_classifiable else np.nan,
                "wilson95_low": low,
                "wilson95_high": high,
                "positive_rate_all_attempted": positives / n_attempted if n_attempted else np.nan,
                "indeterminate_reasons": json.dumps(reasons, sort_keys=True),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["window_type", "window_value"],
        key=lambda s: s.map({"calendar": 0, "cycle": 1, "full": 2}) if s.name == "window_type" else s,
    )


def minimum_data_sensitivity(window_results: pd.DataFrame) -> pd.DataFrame:
    base = window_results[window_results["phase_mode"] == "strict_herzog"].copy()
    rows: list[dict[str, Any]] = []
    for min_seizure_days in [2, 3, 4, 6]:
        eligible_duration = (
            ((base["window_type"] == "calendar") & (pd.to_numeric(base["window_value"], errors="coerce") >= 4))
            | ((base["window_type"] == "cycle") & (pd.to_numeric(base["window_value"], errors="coerce") >= 6))
            | (base["window_type"] == "full")
        )
        eligible_events = base["seizure_days_total"] >= min_seizure_days
        for (cohort, window_type, window_value), group in base.groupby(
            ["cohort", "window_type", "window_value"], sort=False
        ):
            idx = group.index
            passed_minimum = eligible_duration.loc[idx] & eligible_events.loc[idx]
            labels = group.loc[passed_minimum, "label_A_windowed_C1_or_C2"]
            classifiable = labels.notna()
            positives = int((labels[classifiable] == True).sum())  # noqa: E712
            n_classifiable = int(classifiable.sum())
            n_attempted = int(len(group))
            low, high = wilson_interval(positives, n_classifiable)
            rows.append(
                {
                    "min_seizure_days": min_seizure_days,
                    "cohort": cohort,
                    "window_type": window_type,
                    "window_value": window_value,
                    "n_attempted": n_attempted,
                    "n_meeting_minimum": int(passed_minimum.sum()),
                    "n_classifiable": n_classifiable,
                    "positives": positives,
                    "false_positive_rate_classifiable": positives / n_classifiable if n_classifiable else np.nan,
                    "wilson95_low": low,
                    "wilson95_high": high,
                    "positive_rate_all_attempted": positives / n_attempted if n_attempted else np.nan,
                }
            )
    return pd.DataFrame(rows)


def run_c3_nb_exploratory(
    audit_daily: pd.DataFrame,
    window_results: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = audit_daily[
        (audit_daily["cohort"] == "population")
        & (audit_daily["phase_mode"] == "strict_herzog")
    ].copy()
    rows: list[dict[str, Any]] = []
    for participant_id, group in data.groupby("participant_id", sort=True):
        alpha = participant_alpha_from_full_diary(group)
        payload = classify_regression_nb_c3_exploratory(group, cohort="population", alpha=alpha)
        rows.append({"participant_id": participant_id, **payload})
    result = pd.DataFrame(rows)

    matching = window_results[
        (window_results["cohort"] == "population")
        & (window_results["phase_mode"] == "strict_herzog")
        & (window_results["window_type"] == "full")
        & (window_results["participant_id"].isin(result["participant_id"]))
    ][["participant_id", "c3_applicable_flag", "label_A_windowed_C3"]].copy()
    if matching["participant_id"].duplicated().any():
        raise AssertionError("duplicate full-window audit participant rows")
    result = result.merge(matching, on="participant_id", how="left", validate="one_to_one")

    label = result["label_D_C3_exploratory"]
    n_attempted = int(len(result))
    n_ratio_applicable = int(result["c3_applicable_flag"].fillna(False).sum())
    n_classifiable = int(label.notna().sum())
    positives = int((label == True).sum())  # noqa: E712
    low, high = wilson_interval(positives, n_classifiable)
    reasons = result["d_c3_exploratory_reason"].fillna("classifiable").value_counts().to_dict()
    summary = pd.DataFrame(
        [
            {
                "analysis": "Exploratory NB C3 calibration check",
                "n_attempted_audit_participants": n_attempted,
                "n_ratio_c3_applicable": n_ratio_applicable,
                "n_nb_classifiable": n_classifiable,
                "positives": positives,
                "false_positive_rate_classifiable": positives / n_classifiable if n_classifiable else np.nan,
                "wilson95_low": low,
                "wilson95_high": high,
                "positive_rate_all_attempted": positives / n_attempted if n_attempted else np.nan,
                "reason_counts": json.dumps(reasons, sort_keys=True),
                "multiplicity": "Standalone exploratory C3 family; no cross-family adjustment",
                "effect_threshold": 1.62,
                "p_threshold_one_sided": 0.05,
            }
        ]
    )
    return result, summary


def driver_analysis(participants: pd.DataFrame, window_results: pd.DataFrame) -> pd.DataFrame:
    full = window_results[
        (window_results["phase_mode"] == "strict_herzog")
        & (window_results["window_type"] == "full")
    ][
        [
            "participant_id",
            "label_A_windowed_any",
            "label_A_windowed_C1_or_C2",
            "label_A_windowed_C3",
        ]
    ].copy()
    data = participants.merge(full, on="participant_id", how="inner", validate="one_to_one")
    continuous = [
        "age",
        "seizure_days_per_month",
        "seizures_per_month",
        "mean_cycle_length",
        "sd_cycle_length",
        "ovulatory_fraction",
        "dominant_seizure_cycle_days",
    ]
    binary = ["pcos", "peri_menarche", "perimenopause"]
    rows: list[dict[str, Any]] = []
    outcomes = [
        "label_A_windowed_any",
        "label_A_windowed_C1_or_C2",
        "label_A_windowed_C3",
    ]
    for cohort, cohort_data in data.groupby("cohort", sort=False):
        for feature in continuous:
            values = cohort_data[feature]
            if values.notna().sum() < 10 or values.nunique(dropna=True) < 2:
                continue
            bins = pd.qcut(values, q=5, duplicates="drop")
            for level, group in cohort_data.groupby(bins, observed=True, sort=True):
                rows.extend(_driver_rows(cohort, feature, str(level), group, outcomes))
        for feature in binary:
            for level, group in cohort_data.groupby(feature, observed=True, sort=True):
                rows.extend(_driver_rows(cohort, feature, str(bool(level)), group, outcomes))
    return pd.DataFrame(rows)


def _driver_rows(
    cohort: str,
    feature: str,
    level: str,
    group: pd.DataFrame,
    outcomes: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        if outcome == "label_A_windowed_C3" and cohort != "population":
            continue
        labels = group[outcome]
        classifiable = labels.notna()
        positives = int((labels[classifiable] == True).sum())  # noqa: E712
        n = int(classifiable.sum())
        low, high = wilson_interval(positives, n)
        rows.append(
            {
                "cohort": cohort,
                "feature": feature,
                "level": level,
                "outcome": outcome,
                "n_group": int(len(group)),
                "n_classifiable": n,
                "positives": positives,
                "rate": positives / n if n else np.nan,
                "wilson95_low": low,
                "wilson95_high": high,
                "interpretation_scope": "Association between simulator inputs/realizations and simulated classification",
            }
        )
    return rows


def realized_audit_features(audit_daily: pd.DataFrame) -> pd.DataFrame:
    daily = audit_daily[audit_daily["phase_mode"] == "strict_herzog"].copy()
    rows: list[dict[str, Any]] = []
    for participant_id, group in daily.groupby("participant_id", sort=True):
        y = group.sort_values("calendar_day_index")["seizure_count"].to_numpy(dtype=float)
        event = (y > 0).astype(float)
        mean = float(y.mean())
        variance = float(y.var(ddof=1)) if len(y) > 1 else np.nan
        overdispersion = variance / mean if mean > 0 else np.nan
        base_event = float(event.mean())
        after_event = float(event[1:][event[:-1] > 0].mean()) if np.any(event[:-1] > 0) else np.nan
        cluster_propensity = after_event - base_event if np.isfinite(after_event) else np.nan
        centered = y - mean
        spectrum = np.abs(np.fft.rfft(centered))
        frequencies = np.fft.rfftfreq(len(y), d=1.0)
        valid = (frequencies > 0) & (frequencies <= 1 / 2) & (frequencies >= 1 / 365)
        if valid.any() and np.any(spectrum[valid] > 0):
            idx = np.where(valid)[0][int(np.argmax(spectrum[valid]))]
            spectral_period = 1.0 / frequencies[idx]
            spectral_amplitude = 2.0 * spectrum[idx] / len(y)
        else:
            spectral_period = np.nan
            spectral_amplitude = np.nan
        cycle = (
            group.groupby("cycle_id", sort=False)
            .agg(
                cycle_length=("cycle_length", "first"),
                ovulatory=("ovulatory_flag", "first"),
                ilp=("ilp_flag", "max"),
            )
            .reset_index()
        )
        rows.append(
            {
                "participant_id": participant_id,
                "cohort": str(group["cohort"].iloc[0]),
                "daily_count_overdispersion": overdispersion,
                "next_day_cluster_propensity": cluster_propensity,
                "spectral_dominant_period_days": spectral_period,
                "spectral_amplitude_seizures_per_day": spectral_amplitude,
                "audit_mean_cycle_length": float(cycle["cycle_length"].mean()),
                "audit_sd_cycle_length": float(cycle["cycle_length"].std(ddof=1)),
                "audit_ovulatory_fraction": float(cycle["ovulatory"].mean()),
                "audit_ilp_fraction": float(cycle["ilp"].mean()),
                "n_audit_cycles": int(len(cycle)),
            }
        )
    return pd.DataFrame(rows)


def make_supplement_figures(
    participants: pd.DataFrame,
    audit_features: pd.DataFrame,
    driver: pd.DataFrame,
    out_dir: Path,
) -> list[Path]:
    merged = participants.merge(audit_features, on=["participant_id", "cohort"], how="left")
    paths: list[Path] = []
    paths += _save_figure(
        _distribution_figure(
            merged,
            [
                ("seizures_per_month", "Seizures/month"),
                ("seizure_days_per_month", "Seizure days/month"),
                ("daily_count_overdispersion", "Daily variance/mean"),
                ("next_day_cluster_propensity", "Next-day clustering propensity"),
            ],
            "Supplementary Figure S1. Realized seizure-process distributions",
        ),
        out_dir / "figS1_seizure_process_distributions",
    )
    paths += _save_figure(
        _distribution_figure(
            merged,
            [
                ("dominant_seizure_cycle_days", "Generator dominant period (days)"),
                ("spectral_dominant_period_days", "Audit spectral period (days)"),
                ("spectral_amplitude_seizures_per_day", "Audit spectral amplitude"),
                ("mean_seizure_frequency_month", "Latent monthly burden"),
            ],
            "Supplementary Figure S2. Realized seizure-rhythm distributions",
        ),
        out_dir / "figS2_seizure_rhythm_distributions",
    )
    paths += _save_figure(
        _distribution_figure(
            merged,
            [
                ("mean_cycle_length", "Mean cycle length (days)"),
                ("sd_cycle_length", "Within-person cycle-length SD"),
                ("ovulatory_fraction", "Ovulatory-cycle fraction"),
                ("audit_ilp_fraction", "ILP-cycle fraction (audit sample)"),
            ],
            "Supplementary Figure S3. Realized menstrual-cycle distributions",
        ),
        out_dir / "figS3_menstrual_cycle_distributions",
    )
    paths += _save_figure(
        _age_modifier_figure(participants),
        out_dir / "figS4_age_and_modifier_distributions",
    )
    paths += _save_figure(
        _driver_figure(driver),
        out_dir / "figS5_simulated_classification_associations",
    )
    return paths


def _distribution_figure(
    data: pd.DataFrame,
    panels: list[tuple[str, str]],
    title: str,
) -> plt.Figure:
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.3))
    for ax, (field, label) in zip(axes.flat, panels):
        cohorts = ["population"] if field == "audit_ilp_fraction" else ["healthy_ovulatory", "population"]
        for cohort in cohorts:
            values = data.loc[data["cohort"] == cohort, field].replace([np.inf, -np.inf], np.nan).dropna()
            if values.empty:
                continue
            low, high = values.quantile([0.005, 0.995])
            clipped = values.clip(low, high)
            ax.hist(
                clipped,
                bins=35,
                density=True,
                histtype="step",
                linewidth=1.7,
                color=COLORS[cohort],
                label=COHORT_LABELS[cohort],
            )
        ax.set_xlabel(label)
        ax.set_ylabel("Density")
        ax.grid(alpha=0.2)
    axes.flat[0].legend(frameon=False, fontsize=8)
    fig.suptitle(title)
    fig.text(
        0.5,
        0.01,
        "Completed-run distributions; extreme 0.5% tails are winsorized for display. "
        "These panels are descriptive calibration outputs, not external empirical validation.",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    return fig


def _age_modifier_figure(participants: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3))
    for cohort in ["healthy_ovulatory", "population"]:
        values = participants.loc[participants["cohort"] == cohort, "age"].dropna()
        axes[0].hist(
            values,
            bins=30,
            density=True,
            histtype="step",
            linewidth=1.8,
            color=COLORS[cohort],
            label=COHORT_LABELS[cohort],
        )
    axes[0].set_xlabel("Age (years)")
    axes[0].set_ylabel("Density")
    axes[0].legend(frameon=False, fontsize=8)
    modifiers = ["pcos", "peri_menarche", "perimenopause"]
    x = np.arange(len(modifiers))
    width = 0.36
    for offset, cohort in enumerate(["healthy_ovulatory", "population"]):
        group = participants[participants["cohort"] == cohort]
        values = [float(group[m].mean()) for m in modifiers]
        axes[1].bar(
            x + (offset - 0.5) * width,
            values,
            width=width,
            color=COLORS[cohort],
            label=COHORT_LABELS[cohort],
        )
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(["PCOS", "Peri-menarche", "Perimenopause"])
    axes[1].yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes[1].set_ylabel("Participants (%)")
    axes[1].legend(frameon=False, fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("Supplementary Figure S4. Age and configured medical modifiers")
    fig.text(
        0.5,
        0.01,
        "Modifier prevalences are investigator-configured stress-test assumptions, not population estimates.",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    return fig


def _driver_figure(driver: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True)
    selected = ["seizure_days_per_month", "sd_cycle_length", "ovulatory_fraction", "age"]
    data = driver[
        (driver["outcome"] == "label_A_windowed_any")
        & (driver["feature"].isin(selected))
    ].copy()
    for ax, cohort in zip(axes, ["healthy_ovulatory", "population"]):
        group = data[data["cohort"] == cohort]
        for feature in selected:
            fg = group[group["feature"] == feature]
            if fg.empty:
                continue
            ax.plot(
                np.arange(1, len(fg) + 1),
                fg["rate"],
                marker="o",
                linewidth=1.5,
                label=feature.replace("_", " "),
            )
        ax.set_title(COHORT_LABELS[cohort])
        ax.set_xlabel("Within-cohort feature quintile")
        ax.set_xticks(range(1, 6))
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Simulated apparent classification (%)")
    axes[0].yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes[1].legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.suptitle("Supplementary Figure S5. Associations with simulated apparent classification")
    fig.text(
        0.5,
        0.01,
        "Descriptive associations between simulator inputs/realizations and simulated outcomes; "
        "not clinical risk factors or causal effects.",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.05, 0.86, 0.94))
    return fig


def _save_figure(fig: plt.Figure, stem: Path) -> list[Path]:
    paths: list[Path] = []
    for suffix in [".png", ".pdf", ".svg"]:
        path = stem.with_suffix(suffix)
        fig.savefig(path, dpi=220 if suffix == ".png" else None, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def parameter_source_table(config: dict[str, Any], commit: str) -> pd.DataFrame:
    rows = [
        ("Seizure", "Monthly burden", "CHOCOLATES/defaultSeizureFreq", "Both", "Simulator-native empirical distribution", "Participant", "Goldenholz & Westover 2023", "No", "Realized seizures/month", commit),
        ("Seizure", "Overdispersion", "CHOCOLATES gamma-Poisson process", "Both", "Simulator-native", "Participant/day", "Goldenholz & Westover 2023", "No", "Audit daily variance/mean", commit),
        ("Seizure", "Clustering", "CHOCOLATES clustered process", "Both", "Simulator-native", "Participant/day", "Goldenholz & Westover 2023", "No", "Audit next-day clustering proxy", commit),
        ("Seizure", "Multidien periods and amplitudes", "CHOCOLATES seizure cycles", "Both", "Simulator-native", "Participant/day", "Goldenholz & Westover 2023; Karoly et al.", "No", "Generator period and audit spectrum", commit),
        ("Seizure", "Interseizure constraints", "CHOCOLATES refractory/cluster logic", "Both", "Simulator-native", "Day", "Goldenholz & Westover 2023", "No", "Not separately stored", commit),
        ("Menstrual", "Age", "cohorts.*.age_range", "Cohort-specific", str(config["cohorts"]), "Participant", "Investigator-configured study cohorts", "No", "Participant age", commit),
        ("Menstrual", "Cycle length and variability", "hormone_cycler profile/cycle sampling", "Both", "Age-specific low/high participant-variability mixture initialized by a deterministic surrogate and refined in the full simulator; 17-day-shifted lognormal cycle sampler; broad 18–120-day software bounds", "Participant/cycle", "Calibrated to Li et al. 2023; Cunningham et al. 2024 held out", "No", "Age-specific mean, pooled within-person SD, participant irregularity, short/long tails, and held-out 12-month cross-check", commit),
        ("Menstrual", "Bleeding duration", "hormone_cycler bleeding sampling", "Both", "Literature-calibrated", "Cycle", "Bull et al. 2019", "No", "Available in simulator validation suite", commit),
        ("Menstrual", "Ovulation and phase timing", "hormone_cycler profile/render_cycle", "Cohort-specific", "Age/stage/modifier-dependent", "Participant/cycle", "Bull et al. 2019; simulator literature registry", "No", "Ovulatory fraction", commit),
        ("Menstrual", "Hormone trajectories", "hormone_cycler hormone anchors", "Both", "Interpolated daily reference medians", "Cycle/day", "Stricker et al. 2006", "No", "Simulator validation suite", commit),
        ("Menstrual", "ILP rule", "ilp_progesterone_threshold_ng_ml", "Population", f"Maximum P4 on O+5 to O+9 < {config['ilp_progesterone_threshold_ng_ml']} ng/mL; nonovulatory/missing cycles flagged", "Cycle", "Investigator operationalization; threshold requires biological citation", "No", "Audit ILP fraction", commit),
        ("Menstrual", "PCOS", "population_factor_rates.pcos", "Population", config["population_factor_rates"]["pcos"], "Participant", "Investigator-configured stress-test rate", "No", "Participant prevalence", commit),
        ("Menstrual", "Peri-menarche", "population_factor_rates.peri_menarche_if_age_lt_20", "Population", config["population_factor_rates"]["peri_menarche_if_age_lt_20"], "Participant conditional on age <20", "Investigator-configured stress-test rate", "No", "Participant prevalence", commit),
        ("Menstrual", "Perimenopause", "population_factor_rates.perimenopause_if_age_gte_45", "Population", config["population_factor_rates"]["perimenopause_if_age_gte_45"], "Participant conditional on age ≥45", "Investigator-configured stress-test rate", "No", "Participant prevalence", commit),
        ("Menstrual", "Dysmenorrhea", "population_factor_rates.dysmenorrhea", "Population", config["population_factor_rates"]["dysmenorrhea"], "Participant", "Investigator-configured stress-test rate", "No", "Not retained in participant summary", commit),
        ("Menstrual", "Contraception/IUD settings", "hormone_cycler MedicalFactors", "Both", "Available but not sampled in completed run", "Participant", "Simulator literature registry", "No", "Not applicable to completed run", commit),
        ("Computational", "Compact hormone rendering", "render_cycle_compact; audit_daily_fraction", "Non-audit participants", "Consumes the same cycle RNG draws as the full renderer and retains identical cycle structure, ovulation, midluteal progesterone, and ILP status while omitting unused daily concentration objects; full curves retained for validation and the 1% audit sample", "Participant/cycle", "Result-preserving implementation optimization with automated full-versus-compact equivalence tests", "No", "Structural and ILP equivalence; full hormone values in retained audit rows", commit),
        ("Observation", "Diary duration and start", "analysis_modes.full.diary_months; hormone_cycle_start_mode", "Both", f"{config['analysis_modes']['full']['diary_months']} months; diary day 1 sampled uniformly within the first generated menstrual cycle", "Participant", "Study design", "Across analyzed windows", "36 months with randomized starting phase", commit),
        ("Observation", "Missingness", "None", "Both", "No diary missingness simulated", "Day", "Study-design simplification", "No", "Complete synthetic diaries", commit),
        ("Null construction", "Independent generators", "stable_seed(..., 'seizure'/'hormone'); domain-separated profile/cycle/start streams", "Both", "Separately seeded generators; HORMONE-CYCLE uses SHA-256-separated profile, cycle, and observation-start streams, starts at a uniformly sampled first-cycle day, and aligns directly without wrapping", "Participant", "Study design", "No", "Direct alignment and randomized menstrual starting phase preserved without changing latent profile/cycle draws", commit),
        ("Null construction", "Master seed", "master_seed", "Both", config["master_seed"], "Run", "Reproducibility control", "No", "Manifested", commit),
        ("Null construction", "Phase modes", "phase_modes", "Both", ", ".join(config["phase_modes"]), "Analysis", "Herzog criteria plus sensitivity", "Yes", "Both modes retained", commit),
        ("Null construction", "Cohort sizes", "analysis_modes.full.cohort_sizes", "Cohort-specific", str(config["analysis_modes"]["full"]["cohort_sizes"]), "Run", "Monte Carlo design", "No", "100,000 total", commit),
    ]
    columns = [
        "domain",
        "parameter",
        "code_config_field",
        "cohort",
        "setting_or_sampling_distribution",
        "sampling_level",
        "source_or_rationale",
        "varied_in_sensitivity_analysis",
        "realized_validation_target",
        "run_version_commit",
    ]
    return pd.DataFrame(rows, columns=columns)


def wilson_interval(successes: int, total: int, alpha: float = 0.05) -> tuple[float, float]:
    if total <= 0:
        return np.nan, np.nan
    z = float(norm.ppf(1 - alpha / 2))
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/draft_v5_supplement"))
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--skip-c3-nb", action="store_true")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    participants = pd.read_parquet(args.outputs / "participant_summary.parquet")
    windows = pd.read_parquet(args.outputs / "window_results.parquet")
    audit = pd.read_parquet(args.outputs / "audit_daily_sample.parquet")
    with args.config.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    with (args.outputs / "manifest.json").open("r", encoding="utf-8") as handle:
        primary_manifest = json.load(handle)
    code_sha256 = primary_manifest.get("analysis_code_sha256", analysis_code_fingerprint())
    config_sha256 = primary_manifest.get(
        "analysis_config_sha256",
        hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    )
    run_version = f"code-sha256:{code_sha256}; config-sha256:{config_sha256}"

    cumulative_herzog_table(windows).to_csv(args.out_dir / "tableS1_cumulative_herzog_ratios.csv", index=False)
    c3_window_sensitivity(windows).to_csv(args.out_dir / "tableS2_c3_window_sensitivity.csv", index=False)
    minimum_data_sensitivity(windows).to_csv(args.out_dir / "tableS3_minimum_data_sensitivity.csv", index=False)
    driver = driver_analysis(participants, windows)
    driver.to_csv(args.out_dir / "tableS4_simulated_classification_associations.csv", index=False)
    audit_features = realized_audit_features(audit)
    audit_features.to_csv(args.out_dir / "audit_realized_features.csv", index=False)
    parameter_source_table(config, run_version).to_csv(
        args.out_dir / "tableS5_simulator_parameters_and_assumptions.csv",
        index=False,
    )
    figure_paths = make_supplement_figures(participants, audit_features, driver, args.out_dir)
    if not args.skip_c3_nb:
        c3_rows, c3_summary = run_c3_nb_exploratory(audit, windows)
        c3_rows.to_csv(args.out_dir / "tableS6_c3_nb_exploratory_participants.csv", index=False)
        c3_summary.to_csv(args.out_dir / "tableS6_c3_nb_exploratory_summary.csv", index=False)

    manifest = {
        "source_outputs": str(args.outputs),
        "primary_outputs_modified": False,
        "primary_analysis_code_sha256": code_sha256,
        "primary_analysis_config_sha256": config_sha256,
        "supplement_builder_sha256": file_sha256(Path(__file__)),
        "cumulative_ratio_window": {"phase_mode": "strict_herzog", "window_type": "cycle", "window_value": 3},
        "c3_nb_source": "deterministic 1% saved daily audit sample",
        "figures": [str(path) for path in figure_paths],
        "files": [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in sorted(args.out_dir.iterdir())
            if path.is_file() and path.name != "manifest.json"
        ],
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
