"""Matplotlib figures for the Paper 1 null CE analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter


CORE_DEFS = ["A_windowed_any", "A_windowed_C1_or_C2", "B_minimum_data_C1_or_C2", "D_nb_regression_C1_or_C2"]
PRACTICAL_WINDOW_DEFS = ["A_windowed_any", "A_windowed_C1_or_C2", "B_minimum_data_C1_or_C2"]
HIST_DEFS = ["H1_newmark_penry_any", "H2_duncan1993_any", "H3_herzog1997_twofold_any", "H4_reddy2007_any_phase2x_any"]
COLORS = ["#1b9e77", "#d95f02", "#7570b3", "#333333", "#66a61e", "#e7298a", "#a6761d", "#1f78b4"]
COHORT_DISPLAY = {
    "healthy_ovulatory": "Healthy ovulatory",
    "population": "Heterogeneous menstruating-age",
}
DEFINITION_DISPLAY = {
    "A_windowed_any": "Windowed Herzog any C1-C3",
    "A_windowed": "Windowed Herzog",
    "A_windowed_C1_or_C2": "Windowed Herzog C1/C2",
    "B_minimum_data_any": "Herzog + >=4 seizure days",
    "B_minimum_data": "Herzog + >=4 seizure days",
    "B_minimum_data_C1_or_C2": "Herzog C1/C2 + >=4 seizure days",
    "C_reproducibility_any": "Cycle reproducibility >=2/3",
    "D_nb_regression_any": "Negative-binomial regression C1/C2",
    "D_nb_regression_C1_or_C2": "Negative-binomial regression C1/C2",
    "H1_newmark_penry_any": "Newmark-Penry",
    "H2_duncan1993_any": "Duncan 1993",
    "H3_herzog1997_twofold_any": "Herzog 1997 twofold",
    "H4_reddy2007_any_phase2x_any": "Reddy 2007 any phase",
}


def _cohort_label(value: object) -> str:
    return COHORT_DISPLAY.get(str(value), str(value).replace("_", " "))


def _definition_label(value: object) -> str:
    return DEFINITION_DISPLAY.get(str(value), str(value).replace("_any", "").replace("_", " "))


def write_all_figures(output_dir: str | Path, summary: pd.DataFrame, study_level: pd.DataFrame, audit_daily: pd.DataFrame) -> list[Path]:
    out = Path(output_dir)
    paths: list[Path] = []
    figures = [
        ("fig1_false_positive_by_window", lambda: fig1_false_positive_by_window(summary)),
        ("fig2_pattern_decomposition", lambda: fig2_pattern_decomposition(summary)),
        ("fig3_study_prevalence_distribution_3month", lambda: fig3_study_prevalence(study_level)),
        ("fig4_indeterminate_vs_fpr_frontier", lambda: fig4_frontier(summary)),
        ("fig4_historical_vs_core_definitions", lambda: fig4_historical_vs_core(summary)),
        ("fig5_qc_null_cycle_day_profile", lambda: fig5_cycle_day_profile(audit_daily)),
    ]
    for stem, factory in figures:
        fig = factory()
        png = out / f"{stem}.png"
        pdf = out / f"{stem}.pdf"
        svg = out / f"{stem}.svg"
        fig.savefig(png, dpi=200, bbox_inches="tight")
        fig.savefig(pdf, bbox_inches="tight")
        fig.savefig(svg, bbox_inches="tight")
        plt.close(fig)
        paths.extend([png, pdf, svg])
    return paths


def fig1_false_positive_by_window(summary: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    data = _window_summary(summary)
    if "unstable_denominator" in data.columns:
        unstable = data["unstable_denominator"].astype(str).str.lower().isin({"true", "1", "yes"})
    else:
        unstable = pd.Series(False, index=data.index)
    data = data[
        (data["definition"].isin(PRACTICAL_WINDOW_DEFS))
        & (data["phase_mode"] == "strict_herzog")
        & (data["window_type"] == "calendar")
        & (~unstable)
    ]
    if data.empty:
        return _placeholder(fig, axes, "No classifiable core window summaries")
    cohorts = list(data["cohort"].drop_duplicates())
    for ax_index, (ax, cohort) in enumerate(zip(axes, cohorts + [""] * (2 - len(cohorts)))):
        if not cohort:
            ax.axis("off")
            continue
        g = data[data["cohort"] == cohort]
        labels = _ordered_window_labels(g)
        x = np.arange(len(labels))
        width = 0.22
        midpoint = (len(PRACTICAL_WINDOW_DEFS) - 1) / 2.0
        for i, definition in enumerate(PRACTICAL_WINDOW_DEFS):
            values = [
                float(g[(g["_window_label"] == label) & (g["definition"] == definition)]["false_positive_rate"].mean())
                if not g[(g["_window_label"] == label) & (g["definition"] == definition)].empty
                else np.nan
                for label in labels
            ]
            ax.bar(
                x + (i - midpoint) * width,
                values,
                width=width,
                label=_definition_label(definition),
                color=COLORS[i],
            )
        ax.set_title(_cohort_label(cohort))
        ax.axhline(
            0.05,
            color="#444444",
            linestyle="--",
            linewidth=1.0,
            label="5% Type I error reference" if ax_index == 0 else None,
        )
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right")
        ax.set_ylabel("False-positive classifiable windows (%)" if ax_index == 0 else "")
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
        ax.set_ylim(0, min(1.0, max(0.05, np.nanmax(g["false_positive_rate"]) * 1.25)))
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False, fontsize=8, title="Definition / reference", title_fontsize=8)
    fig.suptitle("Calendar-window false-positive rate by monitoring duration")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return fig


def fig2_pattern_decomposition(summary: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    if summary.empty:
        return _placeholder(fig, [ax], "No pattern-decomposition rows")
    data = summary[
        (summary["table_type"] == "pattern_decomposition")
        & (summary["phase_mode"] == "strict_herzog")
        & (summary["window_type"] == "full")
        & (summary["definition"].isin(["A_windowed", "B_minimum_data"]))
    ].copy()
    if data.empty:
        return _placeholder(fig, [ax], "No full-diary pattern-decomposition rows")
    categories = ["none", "indeterminate", "C3 only", "C3 plus C1/C2", "C1 only", "C2 only", "C1+C2"]
    colors = {
        "none": "#d9d9d9",
        "C1 only": "#1b9e77",
        "C2 only": "#7570b3",
        "C1+C2": "#66a61e",
        "C3 only": "#d95f02",
        "C3 plus C1/C2": "#e7298a",
        "indeterminate": "#969696",
    }
    bars = []
    labels = []
    for cohort in ["healthy_ovulatory", "population"]:
        for definition in ["A_windowed", "B_minimum_data"]:
            bars.append((cohort, definition))
            cohort_text = "Healthy" if cohort == "healthy_ovulatory" else "Heterogeneous"
            definition_text = (
                "Windowed Herzog"
                if definition == "A_windowed"
                else "Minimum-data"
            )
            labels.append(f"{cohort_text}\n{definition_text}")
    x = np.arange(len(bars))
    bottoms = np.zeros(len(bars), dtype=float)
    for category in categories:
        values = []
        for cohort, definition in bars:
            g = data[(data["cohort"] == cohort) & (data["definition"] == definition)]
            if category == "indeterminate":
                value = float(g["indeterminate_rate"].dropna().iloc[0]) if not g.empty else 0.0
            else:
                row = g[g["pattern_category"] == category]
                value = float(row["positive_rate_all_attempted"].iloc[0]) if not row.empty else 0.0
            values.append(value)
        display_category = "C3 with C1 and/or C2" if category == "C3 plus C1/C2" else category
        ax.bar(x, values, bottom=bottoms, label=display_category, color=colors[category])
        bottoms += np.array(values)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0, ha="center", fontsize=9)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax.set_ylim(0, 1)
    ax.set_ylabel("All attempted full-diary windows (%)")
    ax.set_title("Pattern decomposition of false-positive catamenial classifications")
    ax.legend(
        frameon=False,
        fontsize=8,
        ncol=1,
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        title="Bottom to top",
        title_fontsize=8,
    )
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout(rect=(0, 0, 0.78, 1))
    return fig


def fig3_study_prevalence(study_level: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), sharey=True)
    if study_level.empty:
        return _placeholder(fig, axes, "No study-level Monte Carlo rows")
    data = study_level[(study_level["definition"] == "A_windowed_any") & (study_level["phase_mode"] == "strict_herzog")]
    if data.empty:
        data = study_level[study_level["phase_mode"] == "strict_herzog"]
    for ax_index, (ax, cohort) in enumerate(zip(axes, ["healthy_ovulatory", "population"])):
        g_cohort = data[data["cohort"] == cohort]
        if g_cohort.empty:
            ax.axis("off")
            continue
        for i, (n_participants, g) in enumerate(g_cohort.groupby("n_participants", sort=True)):
            values = g["apparent_prevalence_all"].dropna()
            weights = np.ones(len(values)) / len(values) if len(values) else None
            ax.hist(
                values,
                bins=np.linspace(0, 1, 31),
                weights=weights,
                histtype="step",
                linewidth=2.0,
                label=f"n={int(n_participants)}",
                color=COLORS[i],
            )
        ax.axvline(0.391, color="#555555", linestyle="--", linewidth=1.4, label="39.1%" if ax_index == 0 else None)
        ax.axvline(0.442, color="#111111", linestyle=":", linewidth=1.6, label="44.2%" if ax_index == 0 else None)
        ax.set_xlim(0, 1)
        ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
        ax.set_xlabel("Apparent CE prevalence among all participants (%)")
        ax.set_ylabel("Simulated studies (%)" if ax_index == 0 else "")
        ax.set_title(_cohort_label(cohort))
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False, title="Study size", title_fontsize=9)
    fig.suptitle("False-positive CE prevalence in simulated 3-month studies")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.tight_layout()
    return fig


def fig4_frontier(summary: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    data = _window_summary(summary)
    if data.empty:
        return _placeholder(fig, [ax], "No window summaries")
    for i, definition in enumerate(CORE_DEFS + HIST_DEFS):
        g = data[data["definition"] == definition]
        if g.empty:
            continue
        ax.scatter(
            g["indeterminate_rate"],
            g["false_positive_rate"],
            s=32,
            alpha=0.75,
            label=_definition_label(definition),
            color=COLORS[i % len(COLORS)],
        )
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax.set_xlabel("Indeterminate windows (%)")
    ax.set_ylabel("False-positive windows among classifiable windows (%)")
    ax.set_title("False positives and indeterminate windows")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, fontsize=7, ncol=2, title="CE definition", title_fontsize=8)
    fig.tight_layout()
    return fig


def fig4_historical_vs_core(summary: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    data = _window_summary(summary)
    data = data[(data["window_type"] == "calendar") & (data["window_value"].astype(str) == "3")]
    if data.empty:
        data = _window_summary(summary)
    if data.empty:
        return _placeholder(fig, [ax], "No 3-month summaries")
    defs = [d for d in CORE_DEFS + HIST_DEFS if d in set(data["definition"])]
    cohorts = list(data["cohort"].drop_duplicates())
    y = np.arange(len(defs))
    height = 0.35 if len(cohorts) > 1 else 0.55
    for i, cohort in enumerate(cohorts):
        values = [
            float(data[(data["cohort"] == cohort) & (data["definition"] == definition)]["false_positive_rate"].mean())
            for definition in defs
        ]
        ax.barh(
            y + (i - (len(cohorts) - 1) / 2) * height,
            values,
            height=height,
            label=_cohort_label(cohort),
            color=COLORS[i],
        )
    ax.set_yticks(y)
    ax.set_yticklabels([_definition_label(d) for d in defs])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax.set_xlabel("False-positive windows (%)")
    ax.set_title("Core and historical definitions in 3-month windows")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(frameon=False, title="Cohort", title_fontsize=9)
    fig.tight_layout()
    return fig


def fig5_cycle_day_profile(audit_daily: pd.DataFrame) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    if audit_daily.empty:
        return _placeholder(fig, [ax], "No audit daily sample")
    data = audit_daily[audit_daily["cycle_day"].between(1, 35)].copy()
    if "phase_mode" in data:
        data = data[data["phase_mode"] == "strict_herzog"].copy()
    if data.empty:
        return _placeholder(fig, [ax], "No standard cycle days in audit sample")
    for i, (cohort, g) in enumerate(data.groupby("cohort", sort=True)):
        profile = g.groupby("cycle_day").agg(seizures=("seizure_count", "sum"), days=("seizure_count", "size"))
        y = profile["seizures"] / profile["days"]
        yerr = np.sqrt(profile["seizures"].clip(lower=1.0)) / profile["days"]
        ax.errorbar(profile.index, y, yerr=yerr, marker="o", markersize=2.5, linewidth=1.5, capsize=2, label=_cohort_label(cohort), color=COLORS[i])
    ax.set_xlabel("Cycle day")
    ax.set_xlim(1, 35)
    ax.set_ylabel("Average seizures per day")
    ax.set_ylim(bottom=0)
    ax.set_title("QC null seizure profile by menstrual cycle day")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False, title="Cohort", title_fontsize=9)
    fig.tight_layout()
    return fig


def _window_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary
    data = summary[
        (summary["table_type"] == "window_false_positive")
        & (summary["subset"] == "all")
        & summary["false_positive_rate"].notna()
    ].copy()
    if data.empty:
        return data
    data["_window_label"] = data.apply(lambda row: _window_label(row["window_type"], row["window_value"]), axis=1)
    return data


def _ordered_window_labels(data: pd.DataFrame) -> list[str]:
    order = ["1 month", "3 months", "4 months", "6 months", "9 months", "12 months", "18 months", "24 months", "36 months", "3 cycles", "6 cycles", "12 cycles"]
    present = list(data["_window_label"].drop_duplicates())
    return [label for label in order if label in present] + [label for label in present if label not in order]


def _window_label(window_type: object, window_value: object) -> str:
    if window_type == "calendar":
        value = int(float(window_value))
        return f"{value} month" if value == 1 else f"{value} months"
    if window_type == "cycle":
        value = int(float(window_value))
        return f"{value} cycle" if value == 1 else f"{value} cycles"
    if window_type == "full":
        return "36 months"
    return f"{window_type} {window_value}"


def _placeholder(fig: plt.Figure, axes: Iterable[plt.Axes], message: str) -> plt.Figure:
    for ax in axes:
        ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
    return fig
