#!/usr/bin/env python3
"""Render the v0.4.0 source-fidelity and nuanced biological validation figure."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib-cache"))

import matplotlib.pyplot as plt
import numpy as np

from hormone_cycler.literature import STRICKER_DAILY_SERUM_REFERENCE
from hormone_cycler.model import (
    LONG_ESTRADIOL_DELAYED_EMERGENCE,
    _luteal_reference_day,
    ovulatory_hormone_points,
    shape_preserving_curve,
)


E2_COLOR = "#B9473B"
P4_COLOR = "#245C9E"
TARGET_COLOR = "#D99A2B"
SIM_COLOR = "#24858A"
GREEN = "#237A55"
GRAY = "#5F6368"


def _canonical_curves():
    cycle_length = 29
    follicular_length = 15
    luteal_length = cycle_length - follicular_length
    e2_points, p4_points = ovulatory_hormone_points(
        cycle_length,
        follicular_length,
        luteal_length,
        1.0,
        1.0,
        LONG_ESTRADIOL_DELAYED_EMERGENCE,
    )
    return (
        cycle_length,
        follicular_length,
        shape_preserving_curve(e2_points),
        shape_preserving_curve(p4_points),
    )


def _mapped_reference(cycle_length: int, follicular_length: int, hormone: str):
    lh_peak_day = float(follicular_length) - 0.75
    mapped = []
    for reference in STRICKER_DAILY_SERUM_REFERENCE:
        day = _luteal_reference_day(
            lh_peak_day,
            reference.lh_offset_days,
            cycle_length,
        )
        if 1.0 < day <= float(cycle_length):
            value = (
                reference.estradiol_pg_ml
                if hormone == "estradiol"
                else reference.progesterone_ng_ml
            )
            mapped.append((day, value, reference.lh_offset_days))
    return mapped


def _metric(report: dict, name: str) -> dict:
    return next(metric for metric in report["baseline_metrics"] if metric["name"] == name)


def render(report: dict, output_png: Path, output_svg: Path) -> None:
    """Write a four-panel audit of the v0.4.0 nuanced fixes."""

    output_png.parent.mkdir(parents=True, exist_ok=True)
    cycle_length, follicular_length, e2_curve, p4_curve = _canonical_curves()
    days = np.linspace(1.0, float(cycle_length), 561)
    e2 = np.asarray([e2_curve(float(day)) for day in days])
    p4 = np.asarray([p4_curve(float(day)) for day in days])
    e2_reference = _mapped_reference(cycle_length, follicular_length, "estradiol")
    p4_reference = _mapped_reference(cycle_length, follicular_length, "progesterone")
    diagnostics = report["waveform_diagnostics"]

    fig, axes = plt.subplots(2, 2, figsize=(14.4, 10.2))

    # Panel A deliberately distinguishes the observations that the previous
    # implementation and overlay both omitted.
    axis = axes[0, 0]
    axis.plot(days, e2, color=E2_COLOR, linewidth=2.3, label="Canonical envelope")
    early = [item for item in e2_reference if -13 <= item[2] <= -2]
    other = [item for item in e2_reference if item not in early]
    axis.scatter(
        [item[0] for item in other],
        [item[1] for item in other],
        color="#7A1F17",
        edgecolor="white",
        linewidth=0.5,
        s=34,
        zorder=3,
        label="Other in-cycle Stricker medians",
    )
    axis.scatter(
        [item[0] for item in early],
        [item[1] for item in early],
        marker="D",
        color=TARGET_COLOR,
        edgecolor="white",
        linewidth=0.5,
        s=39,
        zorder=4,
        label="LH−13…−2 observations now audited",
    )
    axis.axvline(follicular_length, color=GREEN, linestyle="--", linewidth=1.1)
    area = _metric(report, "estradiol_stricker_follicular_area_ratio")
    coverage = _metric(report, "estradiol_stricker_mapped_reference_coverage")
    axis.text(
        0.02,
        0.04,
        f"Mapped coverage={coverage['observed']:.0%}; follicular area ratio={area['observed']:.2f}",
        transform=axis.transAxes,
        fontsize=9,
        color=GRAY,
        bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "none", "pad": 2},
    )
    axis.set_title("A. Full ordinary-cycle E2 construction audit", loc="left")
    axis.set_xlabel("Cycle day")
    axis.set_ylabel("Estradiol (pg/mL)")
    axis.legend(frameon=False, fontsize=8.2, loc="upper left")

    axis = axes[0, 1]
    tail_start = follicular_length
    tail_mask = days >= float(tail_start)
    tail_days = days[tail_mask]
    axis.plot(tail_days, p4[tail_mask], color=P4_COLOR, linewidth=2.3, label="Canonical envelope")
    tail_reference = [item for item in p4_reference if item[0] >= tail_start]
    axis.scatter(
        [item[0] for item in tail_reference],
        [item[1] for item in tail_reference],
        color="#173A68",
        edgecolor="white",
        linewidth=0.5,
        s=36,
        zorder=3,
        label="Mapped Stricker medians",
    )
    axis.plot(
        [cycle_length, cycle_length + 1],
        [p4[-1], p4_curve(1.0)],
        color=P4_COLOR,
        linestyle=":",
        linewidth=1.8,
        label="Next-cycle baseline transition",
    )
    axis.scatter([cycle_length + 1], [p4_curve(1.0)], color=P4_COLOR, s=35, zorder=3)
    axis.axvline(cycle_length + 0.5, color=GRAY, linestyle="--", linewidth=1.1)
    terminal = _metric(report, "progesterone_terminal_to_peak_ratio")
    final_drop = _metric(report, "progesterone_penultimate_to_terminal_drop_ng_ml")
    axis.text(
        0.02,
        0.04,
        f"Terminal/peak={terminal['observed']:.3f}; final within-cycle drop={final_drop['observed']:.2f} ng/mL",
        transform=axis.transAxes,
        va="bottom",
        fontsize=9,
        color=GRAY,
        bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "none", "pad": 2},
    )
    axis.set_title("B. Published P4 tail retained to cycle end", loc="left")
    axis.set_xlabel("Cycle day (30 is next-cycle day 1)")
    axis.set_ylabel("Progesterone (ng/mL)")
    axis.legend(frameon=False, fontsize=8.2, loc="upper right")

    axis = axes[1, 0]
    e2_offsets = np.asarray(diagnostics["estradiol_peak_offsets_days"], dtype=float)
    p4_offsets = np.asarray(diagnostics["progesterone_peak_offsets_days"], dtype=float)
    all_offsets = np.concatenate([e2_offsets, p4_offsets])
    bins = np.arange(np.floor(all_offsets.min()) - 0.5, np.ceil(all_offsets.max()) + 1.5, 1.0)
    axis.hist(e2_offsets, bins=bins, alpha=0.72, color=E2_COLOR, label="E2 peak")
    axis.hist(p4_offsets, bins=bins, alpha=0.68, color=P4_COLOR, label="P4 peak")
    e2_sd = _metric(report, "estradiol_peak_offset_sd_days")
    p4_sd = _metric(report, "progesterone_peak_offset_sd_days")
    correlation = _metric(report, "progesterone_luteal_length_peak_offset_correlation")
    axis.text(
        0.02,
        0.94,
        (
            f"n={diagnostics['n_complete_ovulatory_cycles']} cycles; "
            f"SD(E2)={e2_sd['observed']:.2f} d; SD(P4)={p4_sd['observed']:.2f} d\n"
            f"corr(luteal length, P4-peak offset)={correlation['observed']:.2f}"
        ),
        transform=axis.transAxes,
        va="top",
        fontsize=9,
        color=GRAY,
        bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "none", "pad": 2},
    )
    axis.axvline(0, color=GREEN, linestyle="--", linewidth=1.0, alpha=0.8)
    axis.set_title("C. Cycle-level timing heterogeneity", loc="left")
    axis.set_xlabel("Peak day relative to ovulation")
    axis.set_ylabel("Complete cycles")
    axis.legend(frameon=False, fontsize=8.5, loc="upper right")

    axis = axes[1, 1]
    subgroup = report["subgroup_analysis"]["subgroups"]["perimenopause"]
    simulated_long = subgroup["summary"]["long_cycle_anovulatory_rate"]
    simulated_ordinary = subgroup["summary"]["ordinary_cycle_anovulatory_rate"]
    long_n = subgroup["summary"]["long_cycle_count"]
    ordinary_n = subgroup["summary"]["ordinary_cycle_count"]
    dependence = next(
        check
        for check in subgroup["checks"]
        if check["name"] == "perimenopause_long_cycle_anovulatory_rate"
    )
    contrast = next(
        check
        for check in subgroup["checks"]
        if check["name"] == "perimenopause_long_vs_ordinary_anovulation_delta"
    )
    published_long = dependence["expected"]
    published_ordinary = published_long - contrast["expected"]
    x_positions = np.asarray([0.0, 1.0])
    axis.plot(
        x_positions,
        [published_ordinary, published_long],
        marker="o",
        markersize=8,
        linewidth=2.4,
        color=TARGET_COLOR,
        label="Van Voorhis cohort context",
    )
    axis.plot(
        x_positions,
        [simulated_ordinary, simulated_long],
        marker="o",
        markersize=8,
        linewidth=2.4,
        color=SIM_COLOR,
        label="Simulated explicit perimenopause",
    )
    for x_value, value in zip(x_positions, [published_ordinary, published_long]):
        axis.annotate(
            f"{value:.1%}",
            (x_value, value),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            color="#956718",
            fontsize=9,
        )
    for x_value, value in zip(x_positions, [simulated_ordinary, simulated_long]):
        axis.annotate(
            f"{value:.1%}",
            (x_value, value),
            xytext=(0, -16),
            textcoords="offset points",
            ha="center",
            color="#1D696C",
            fontsize=9,
        )
    axis.set_xticks([0, 1], ["21–35-day intervals", "≥36-day intervals"])
    axis.set_ylim(0, 1)
    axis.set_ylabel("Anovulatory fraction")
    axis.set_title("D. Long-cycle enrichment is weaker than source context", loc="left")
    axis.text(
        0.98,
        0.06,
        (
            f"Simulated n={ordinary_n:,} ordinary / {long_n:,} long; "
            f"OR={subgroup['summary']['long_vs_ordinary_anovulation_odds_ratio']:.2f}"
        ),
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color=GRAY,
        bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "none", "pad": 2},
    )
    axis.legend(frameon=False, fontsize=8.2, loc="upper right")

    for axis in axes.flat:
        axis.grid(axis="y", alpha=0.16)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
    fig.suptitle(
        "HORMONE-CYCLE v0.4.0 nuanced biological validation",
        fontsize=16,
        fontweight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.006,
        (
            "A–B are direct Stricker construction/boundary audits. C uses Roos-informed, "
            "investigator-set anti-template guards. D shows both published and simulated "
            "conditional rates; the association is directional rather than magnitude-matched."
        ),
        ha="center",
        fontsize=8.8,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.96), h_pad=2.6, w_pad=2.0)
    fig.savefig(output_png, dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(output_svg, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validation",
        type=Path,
        default=ROOT / "examples" / "reports" / "healthy_cycle_validation_v14.json",
    )
    parser.add_argument(
        "--output-png",
        type=Path,
        default=ROOT / "examples" / "reports" / "hormone_nuanced_validation_v14.png",
    )
    parser.add_argument(
        "--output-svg",
        type=Path,
        default=ROOT / "examples" / "reports" / "hormone_nuanced_validation_v14.svg",
    )
    args = parser.parse_args()
    report = json.loads(args.validation.read_text(encoding="utf-8"))
    render(report, args.output_png, args.output_svg)
    print(args.output_png.resolve())
    print(args.output_svg.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
