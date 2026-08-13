#!/usr/bin/env python3
"""Render the v14 healthy-cycle calibration and external-validation figure."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", ".matplotlib-cache")

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BLUE = "#1F4E79"
TEAL = "#24858A"
GOLD = "#D99A2B"
RED = "#B24745"
PURPLE = "#665191"
AGE_KEYS = ["<20", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50+"]
AGE_LABELS = ["<20", "20–24", "25–29", "30–34", "35–39", "40–44", "45–49", "≥50"]


def render(validation: dict, output: Path) -> None:
    """Write a six-panel source-versus-simulator validation summary."""

    output.parent.mkdir(parents=True, exist_ok=True)
    metrics = {metric["name"]: metric for metric in validation["baseline_metrics"]}
    x = np.arange(len(AGE_KEYS))
    fig, axes = plt.subplots(3, 2, figsize=(13.2, 9.4))

    def target_sim_lines(axis: plt.Axes, prefix: str, ylabel: str, title: str, multiplier: float = 1.0) -> None:
        axis.plot(x, [multiplier * metrics[f"{prefix}{key}"]["expected"] for key in AGE_KEYS], "o--", color=GOLD, label="Published")
        axis.plot(x, [multiplier * metrics[f"{prefix}{key}"]["observed"] for key in AGE_KEYS], "o-", color=TEAL, label="Simulated")
        axis.set_xticks(x, AGE_LABELS, rotation=25)
        axis.set_ylabel(ylabel)
        axis.set_title(title)

    target_sim_lines(axes[0, 0], "cycle_mean_", "Days", "A. Mean cycle length (AWHS)")
    target_sim_lines(axes[0, 1], "cycle_within_person_sd_", "Days", "B. Within-person SD (AWHS)")
    target_sim_lines(axes[1, 0], "cycle_irregularity_", "Participants (%)", "C. Participant-level irregularity (AWHS)", 100.0)

    axes[1, 1].plot(x, [100 * metrics[f"cycle_short_lt24_{key}"]["expected"] for key in AGE_KEYS], "o--", color=GOLD, label="Short, published")
    axes[1, 1].plot(x, [100 * metrics[f"cycle_short_lt24_{key}"]["observed"] for key in AGE_KEYS], "o-", color=TEAL, label="Short, simulated")
    axes[1, 1].plot(x, [100 * metrics[f"cycle_long_gt38_{key}"]["expected"] for key in AGE_KEYS], "s--", color=RED, label="Long, published")
    axes[1, 1].plot(x, [100 * metrics[f"cycle_long_gt38_{key}"]["observed"] for key in AGE_KEYS], "s-", color=PURPLE, label="Long, simulated")
    axes[1, 1].set_xticks(x, AGE_LABELS, rotation=25)
    axes[1, 1].set_ylabel("Cycles (%)")
    axes[1, 1].set_title("D. Short (<24 d) and long (>38 d) tails")
    axes[1, 1].legend(frameon=False, fontsize=8, ncol=2)

    external_labels = ["18–25", "26–30", "31–35", "36–40", "41–45", "46–50", "51–55"]
    external_keys = [label.replace("–", "-") for label in external_labels]
    ex = np.arange(len(external_keys))
    axes[2, 0].plot(ex, [metrics[f"external_cunningham_mean_personal_sd_{key}"]["expected"] for key in external_keys], "o--", color=GOLD, label="Flo (held out)")
    axes[2, 0].plot(ex, [metrics[f"external_cunningham_mean_personal_sd_{key}"]["observed"] for key in external_keys], "o-", color=TEAL, label="Simulated")
    axes[2, 0].set_xticks(ex, external_labels, rotation=25)
    axes[2, 0].set_ylabel("Mean personal SD (days)")
    axes[2, 0].set_title("E. Independent 12-month Flo cross-check")

    phase_keys = ["follicular_mean_days", "luteal_mean_days", "bleeding_mean_days", "luteal_sd_days", "bleeding_sd_days"]
    phase_labels = ["Follicular\nmean", "Luteal\nmean", "Bleeding\nmean", "Luteal\nSD", "Bleeding\nSD"]
    px = np.arange(len(phase_keys))
    width = 0.36
    axes[2, 1].bar(px - width / 2, [metrics[key]["expected"] for key in phase_keys], width, color=GOLD, label="Bull et al.")
    axes[2, 1].bar(px + width / 2, [metrics[key]["observed"] for key in phase_keys], width, color=TEAL, label="Simulated")
    axes[2, 1].set_xticks(px, phase_labels)
    axes[2, 1].set_ylabel("Days")
    axes[2, 1].set_title("F. Ovulatory phase and bleeding checks")

    for axis in axes.flat:
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.grid(axis="y", alpha=0.18)
    axes[0, 0].legend(frameon=False, fontsize=9)
    axes[2, 0].legend(frameon=False, fontsize=9)
    axes[2, 1].legend(frameon=False, fontsize=9)
    fig.suptitle(
        "Healthy-cycle simulator calibration and held-out validation",
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
    parser.add_argument("--validation", type=Path, default=ROOT / "examples" / "reports" / "healthy_cycle_validation_v14.json")
    parser.add_argument("--output", type=Path, default=ROOT / "examples" / "reports" / "hormone_cycle_validation_v14.png")
    args = parser.parse_args()
    render(json.loads(args.validation.read_text(encoding="utf-8")), args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
