#!/usr/bin/env python3
"""Render the v0.4.0 waveform-construction and long-cycle visual check."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from hormone_cycler.literature import STRICKER_DAILY_SERUM_REFERENCE
from hormone_cycler.model import (
    LONG_ESTRADIOL_DELAYED_EMERGENCE,
    LONG_ESTRADIOL_FAILED_WAVE,
    _luteal_reference_day,
    ovulatory_hormone_points,
    shape_preserving_curve,
)


ROOT = Path(__file__).resolve().parents[1]
E2_COLOR = "#C54E40"
P4_COLOR = "#2D67B1"
GREEN = "#27855B"
GRAY = "#5F6368"


def _ordinary_curves() -> tuple[np.ndarray, list[float], list[float], float]:
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
    e2_curve = shape_preserving_curve(e2_points)
    p4_curve = shape_preserving_curve(p4_points)
    days = np.linspace(1.0, float(cycle_length), 561)
    return (
        days,
        [e2_curve(float(day)) for day in days],
        [p4_curve(float(day)) for day in days],
        float(follicular_length),
    )


def _mapped_reference(
    cycle_length: int,
    follicular_length: int,
    hormone: str,
) -> tuple[list[float], list[float]]:
    lh_peak_day = float(follicular_length) - 0.75
    mapped: list[tuple[float, float]] = []
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
            mapped.append((day, value))
    return [item[0] for item in mapped], [item[1] for item in mapped]


def _long_e2(
    variant: str,
) -> tuple[list[int], list[float]]:
    cycle_length = 53
    follicular_length = 39
    e2_points, _ = ovulatory_hormone_points(
        cycle_length,
        follicular_length,
        cycle_length - follicular_length,
        1.0,
        1.0,
        variant,
    )
    curve = shape_preserving_curve(e2_points)
    days = list(range(1, follicular_length + 1))
    return days, [curve(float(day)) for day in days]


def render(output_png: Path, output_svg: Path) -> None:
    """Write a publication-ready three-panel validation figure."""

    output_png.parent.mkdir(parents=True, exist_ok=True)
    days, e2, p4, ovulation_day = _ordinary_curves()
    e2_x, e2_y = _mapped_reference(29, 15, "estradiol")
    p4_x, p4_y = _mapped_reference(29, 15, "progesterone")
    delayed_x, delayed_y = _long_e2(LONG_ESTRADIOL_DELAYED_EMERGENCE)
    failed_x, failed_y = _long_e2(LONG_ESTRADIOL_FAILED_WAVE)

    fig, axes = plt.subplots(1, 3, figsize=(15.8, 5.2))

    axes[0].plot(days, e2, color=E2_COLOR, linewidth=2.4, label="v0.4.0 envelope")
    axes[0].scatter(
        e2_x,
        e2_y,
        color="#7A1F17",
        edgecolor="white",
        linewidth=0.6,
        s=38,
        zorder=3,
        label=f"All {len(e2_x)} in-cycle Stricker medians",
    )
    axes[0].axvline(ovulation_day, color=GREEN, linestyle="--", linewidth=1.2)
    axes[0].set_title("A. Ordinary-cycle estradiol")
    axes[0].set_ylabel("Estradiol (pg/mL)")
    axes[0].set_xlabel("Cycle day")
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper right")

    axes[1].plot(days, p4, color=P4_COLOR, linewidth=2.4, label="v0.4.0 envelope")
    axes[1].scatter(
        p4_x,
        p4_y,
        color="#173A68",
        edgecolor="white",
        linewidth=0.6,
        s=38,
        zorder=3,
        label=f"All {len(p4_x)} in-cycle Stricker medians",
    )
    axes[1].axvline(ovulation_day, color=GREEN, linestyle="--", linewidth=1.2)
    axes[1].set_title("B. Broad luteal progesterone summit")
    axes[1].set_ylabel("Progesterone (ng/mL)")
    axes[1].set_xlabel("Cycle day")
    axes[1].legend(frameon=False, fontsize=8.5, loc="upper left")

    axes[2].plot(
        [day - 39 for day in delayed_x],
        delayed_y,
        color=E2_COLOR,
        linewidth=2.3,
        label="53-day delayed emergence",
    )
    axes[2].plot(
        [day - 39 for day in failed_x],
        failed_y,
        color="#B07AA1",
        linewidth=2.3,
        label="53-day failed wave",
    )
    # Draw the ordinary terminal follicular segment last. It is intentionally
    # similar to the terminal segments of the long-cycle branches; keeping the
    # dotted comparator on top makes that shared, non-stretched geometry visible.
    ordinary_relative = [day - ovulation_day for day in days if day <= ovulation_day]
    ordinary_e2 = [value for day, value in zip(days, e2) if day <= ovulation_day]
    axes[2].plot(
        ordinary_relative,
        ordinary_e2,
        color=GRAY,
        linewidth=2.0,
        linestyle=":",
        zorder=4,
        label="29-day ordinary cycle",
    )
    axes[2].axvline(0, color=GREEN, linestyle="--", linewidth=1.2)
    axes[2].set_title("C. Qualitative long-follicular E2 branches")
    axes[2].set_ylabel("Estradiol (pg/mL)")
    axes[2].set_xlabel("Days relative to ovulation")
    handles, labels = axes[2].get_legend_handles_labels()
    axes[2].legend(
        [handles[index] for index in (2, 0, 1)],
        [labels[index] for index in (2, 0, 1)],
        frameon=False,
        fontsize=8.2,
        loc="upper left",
    )

    for axis in axes:
        axis.grid(axis="y", alpha=0.18)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
    fig.suptitle(
        "HORMONE-CYCLE v0.4.0 waveform construction and visual validation",
        fontsize=16,
        fontweight="bold",
        y=1.02,
    )
    fig.text(
        0.5,
        0.005,
        (
            "Panels A-B are construction-fidelity overlays, not independent validation. "
            "Panel C is qualitative: Harlow supports the pattern classes, not their simulated "
            "serum amplitudes or mixture weights."
        ),
        ha="center",
        fontsize=8.8,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(output_png, dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(output_svg, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-png",
        type=Path,
        default=ROOT / "examples" / "reports" / "hormone_waveform_validation_v14.png",
    )
    parser.add_argument(
        "--output-svg",
        type=Path,
        default=ROOT / "examples" / "reports" / "hormone_waveform_validation_v14.svg",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    render(args.output_png, args.output_svg)
