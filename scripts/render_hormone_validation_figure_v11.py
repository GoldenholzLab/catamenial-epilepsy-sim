#!/usr/bin/env python3
"""Render the v11 appendix hormone calibration and kinetic-validation figure."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib-cache"))

import matplotlib.pyplot as plt
import numpy as np

from hormone_cycler.model import simulate_diary


BLUE = "#1F4E79"
TEAL = "#2A788E"
GOLD = "#D99A2B"
RED = "#B24745"
P4_BLUE = "#3B67A8"
AGE_LABELS = ["<20", "20–24", "25–29", "30–34", "35–39", "40–44", "45–49", "≥50"]


def metric_map(validation: dict) -> dict[str, dict]:
    """Index baseline metrics by their stable machine-readable names."""

    return {metric["name"]: metric for metric in validation["baseline_metrics"]}


def render(validation: dict, output: Path) -> None:
    """Write a six-panel calibration and kinetic-validation figure."""

    output.parent.mkdir(parents=True, exist_ok=True)
    metrics = metric_map(validation)
    # The appendix places this figure on a landscape page with a 9 x 6.5 inch text block.
    fig, axes = plt.subplots(3, 2, figsize=(13.2, 9.2))

    age_keys = ["<20", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50+"]
    x = np.arange(len(age_keys))
    axes[0, 0].plot(
        x,
        [metrics[f"cycle_mean_{key}"]["expected"] for key in age_keys],
        "o--",
        color=GOLD,
        label="Calibration target",
    )
    axes[0, 0].plot(
        x,
        [metrics[f"cycle_mean_{key}"]["observed"] for key in age_keys],
        "o-",
        color=TEAL,
        label="Simulated",
    )
    axes[0, 0].set_xticks(x, AGE_LABELS, rotation=25)
    axes[0, 0].set_ylabel("Mean cycle length (days)")
    axes[0, 0].set_title("A. Age-stratified cycle length")
    axes[0, 0].legend(frameon=False, fontsize=9)

    axes[0, 1].plot(
        x,
        [100 * metrics[f"cycle_irregularity_{key}"]["expected"] for key in age_keys],
        "o--",
        color=GOLD,
        label="Calibration target",
    )
    axes[0, 1].plot(
        x,
        [100 * metrics[f"cycle_irregularity_{key}"]["observed"] for key in age_keys],
        "o-",
        color=TEAL,
        label="Simulated",
    )
    axes[0, 1].set_xticks(x, AGE_LABELS, rotation=25)
    axes[0, 1].set_ylabel("Adjacent-cycle difference ≥7 days (%)")
    axes[0, 1].set_title("B. Age-stratified irregularity")

    phases = [
        ("Follicular", "follicular_mean_days"),
        ("Luteal", "luteal_mean_days"),
        ("Bleeding", "bleeding_mean_days"),
    ]
    phase_x = np.arange(len(phases))
    width = 0.36
    axes[1, 0].bar(
        phase_x - width / 2,
        [4.0 if key == "bleeding_mean_days" else metrics[key]["expected"] for _, key in phases],
        width,
        color=GOLD,
        label="Calibration target",
    )
    axes[1, 0].bar(
        phase_x + width / 2,
        [metrics[key]["observed"] for _, key in phases],
        width,
        color=TEAL,
        label="Simulated",
    )
    axes[1, 0].set_xticks(phase_x, [label for label, _ in phases])
    axes[1, 0].set_ylabel("Days")
    axes[1, 0].set_title("C. Phase and bleeding duration")

    phase_names = [
        "early_follicular",
        "mid_follicular",
        "pre_ovulatory",
        "ovulation",
        "early_luteal",
        "mid_luteal",
        "late_luteal",
    ]
    phase_labels = ["Early F", "Mid F", "Pre-O", "O", "Early L", "Mid L", "Late L"]
    axes[1, 1].axhline(100, color=GOLD, linestyle="--", linewidth=1.5)
    axes[1, 1].plot(
        np.arange(7),
        [100 * metrics[f"estradiol_{phase}"]["observed"] / metrics[f"estradiol_{phase}"]["expected"] for phase in phase_names],
        "o-",
        color=TEAL,
        label="Estradiol",
    )
    axes[1, 1].plot(
        np.arange(7),
        [100 * metrics[f"progesterone_{phase}"]["observed"] / metrics[f"progesterone_{phase}"]["expected"] for phase in phase_names],
        "s-",
        color=RED,
        label="Progesterone",
    )
    axes[1, 1].set_xticks(np.arange(7), phase_labels, rotation=25)
    axes[1, 1].set_ylabel("Simulated value / target (%)")
    axes[1, 1].set_ylim(65, 115)
    axes[1, 1].set_title("D. Hormone subphase calibration")
    axes[1, 1].legend(frameon=False, fontsize=9)

    result = simulate_diary(
        days=140,
        age_years=31,
        seed=1,
        patient_id="appendix-kinetic-validation",
        start_mode="cycle_day_1",
    )
    cycle = next(item for item in result.cycles if item.ovulatory)
    cycle_rows = [row for row in result.diary if row.cycle_index == cycle.cycle_index]
    next_rows = [row for row in result.diary if row.cycle_index == cycle.cycle_index + 1]
    rows = cycle_rows + next_rows[:1]
    day = np.arange(1, len(rows) + 1)
    boundary = len(cycle_rows) + 0.5

    axes[2, 0].plot(day, [row.estradiol_pg_ml for row in rows], color=RED, linewidth=2.1)
    axes[2, 0].set_ylabel("Estradiol (pg/mL)")
    axes[2, 0].set_xlabel("Day within displayed interval")
    axes[2, 0].set_title("E. Estradiol kinetic check")

    axes[2, 1].plot(day, [row.progesterone_ng_ml for row in rows], color=P4_BLUE, linewidth=2.1)
    axes[2, 1].set_ylabel("Progesterone (ng/mL)")
    axes[2, 1].set_xlabel("Day within displayed interval")
    axes[2, 1].set_title("F. Progesterone withdrawal before bleeding")

    for axis in axes[2, :]:
        axis.axvline(boundary, color="#555555", linestyle="--", linewidth=1.2)
        axis.axvspan(1, 5.5, color="#D99A2B", alpha=0.10)
        axis.axvspan(boundary, boundary + 1, color="#D99A2B", alpha=0.18)
        axis.text(
            boundary - 0.2,
            0.96,
            "next bleeding onset",
            transform=axis.get_xaxis_transform(),
            ha="right",
            va="top",
            fontsize=8.5,
            color="#555555",
        )

    for axis in axes.flat:
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.grid(axis="y", alpha=0.18)
    fig.suptitle(
        "HORMONE-CYCLE internal target reproduction and kinetic checks",
        fontsize=16,
        fontweight="bold",
        color=BLUE,
        y=0.995,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validation",
        type=Path,
        default=ROOT / "examples" / "reports" / "notebook_validation_report.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".codex_review" / "v11_hormone_fix" / "hormone_cycle_validation_v11.png",
    )
    args = parser.parse_args()
    render(json.loads(args.validation.read_text(encoding="utf-8")), args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
