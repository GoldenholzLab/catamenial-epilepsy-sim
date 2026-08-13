#!/usr/bin/env python3
"""Render transparent healthy-cycle example traces for simulator v0.2.0."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib-cache"))

import matplotlib.pyplot as plt
import numpy as np

from hormone_cycler.model import long_follicular_estradiol_variant, simulate_diary
from hormone_cycler.validation import cycle_irregularity


CASES = [
    ("A. Healthy age 31, low-variability component", 31.0, 4, "healthy-regular-age31"),
    ("B. Healthy age 31, high-variability component", 31.0, 6, "healthy-variable-age31"),
    ("C. Healthy age 52, later-life long-cycle episode", 52.0, 17, "healthy-later-age52"),
]


def render(output_png: Path, output_svg: Path, days: int = 220) -> None:
    """Write three aligned hormone/event traces with separate hormone axes."""

    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(CASES), 1, figsize=(14.2, 10.4), sharex=True)
    for axis, (title, age, seed, patient_id) in zip(axes, CASES):
        result = simulate_diary(
            days=days,
            age_years=age,
            seed=seed,
            patient_id=patient_id,
            start_mode="cycle_day_1",
        )
        x = np.arange(1, len(result.diary) + 1)
        e2 = np.asarray([row.estradiol_pg_ml for row in result.diary])
        p4 = np.asarray([row.progesterone_ng_ml for row in result.diary])
        cycle_lengths = [cycle.cycle_length for cycle in result.cycles[:7]]
        mad = cycle_irregularity(cycle_lengths)

        axis.plot(x, e2, color="#C04B3E", linewidth=1.65, label="Estradiol")
        axis.set_ylabel("Estradiol\n(pg/mL)", color="#8E352C")
        axis.tick_params(axis="y", colors="#8E352C")
        p4_axis = axis.twinx()
        p4_axis.plot(x, p4, color="#2B65B1", linewidth=1.65, label="Progesterone")
        p4_axis.set_ylabel("Progesterone\n(ng/mL)", color="#214E88")
        p4_axis.tick_params(axis="y", colors="#214E88")

        for row in result.diary:
            if row.uterine_bleeding:
                axis.axvspan(row.day_index - 0.5, row.day_index + 0.5, color="#C64536", alpha=0.12, linewidth=0)
            if row.ovulation:
                axis.scatter(row.day_index, axis.get_ylim()[1] * 0.94, marker="v", s=34, color="#27855B", zorder=5)

        subtitle = (
            f"component={result.profile.cycle_variability_component}; first 7 lengths={cycle_lengths}; "
            f"mean absolute adjacent difference={mad:.1f} d"
        )
        long_variants = [
            f"cycle {cycle.cycle_index}: {long_follicular_estradiol_variant(result.profile, cycle.cycle_index).replace('_', ' ')}"
            for cycle in result.cycles[:7]
            if cycle.ovulatory and cycle.follicular_length >= 24
        ]
        if long_variants:
            subtitle += "; long-follicular E2=" + ", ".join(long_variants)
        axis.set_title(f"{title}\n{subtitle}", loc="left", fontsize=11.2, fontweight="semibold")
        axis.grid(axis="y", alpha=0.16)
        axis.spines["top"].set_visible(False)
        p4_axis.spines["top"].set_visible(False)

    axes[-1].set_xlabel("Simulation day (diary begins on cycle day 1)")
    handles = [
        plt.Line2D([0], [0], color="#C04B3E", lw=2, label="Estradiol"),
        plt.Line2D([0], [0], color="#2B65B1", lw=2, label="Progesterone"),
        plt.Rectangle((0, 0), 1, 1, color="#C64536", alpha=0.18, label="Bleeding"),
        plt.Line2D([0], [0], marker="v", color="none", markerfacecolor="#27855B", markeredgecolor="#27855B", label="Ovulation"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.995))
    fig.suptitle(
        "Healthy-cycle examples after daily hormone-waveform recalibration",
        fontsize=16,
        fontweight="bold",
        y=1.025,
    )
    fig.text(
        0.5,
        0.004,
        "Examples were selected by prespecified display criteria and are illustrative, not validation observations.",
        ha="center",
        fontsize=9.5,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.025, 1, 0.965), h_pad=2.2)
    fig.savefig(output_png, dpi=220, bbox_inches="tight", facecolor="white")
    fig.savefig(output_svg, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-png",
        type=Path,
        default=ROOT / "examples" / "reports" / "healthy_cycle_example_traces_v12.png",
    )
    parser.add_argument(
        "--output-svg",
        type=Path,
        default=ROOT / "examples" / "reports" / "healthy_cycle_example_traces_v12.svg",
    )
    parser.add_argument("--days", type=int, default=220)
    args = parser.parse_args()
    render(args.output_png, args.output_svg, args.days)
    print(args.output_png.resolve())
    print(args.output_svg.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
