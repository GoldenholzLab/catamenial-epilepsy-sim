#!/usr/bin/env python3
"""Render auditable selected latent hormone-envelope examples for simulator v0.4.0."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib-cache"))

import matplotlib.pyplot as plt
import numpy as np

from hormone_cycler.model import simulate_diary
from hormone_cycler.types import MedicalFactors, SimulationResult
from hormone_cycler.validation import cycle_irregularity


SEARCH_DAYS = 360
DISPLAY_CYCLES = 7
E2_COLOR = "#B9473B"
P4_COLOR = "#245C9E"
BLEED_COLOR = "#C64536"
OVULATION_COLOR = "#237A55"
DISPLAY_TITLES = {
    "age31_low": "A. Age 31 · low-variability ovulatory profile",
    "age31_high": "B. Age 31 · high-variability ovulatory profile",
    "age52_perimenopause": "C. Age 52 · explicit perimenopause profile",
}


@dataclass(frozen=True)
class DisplayCase:
    """One reproducibly selected display case and its executable criterion."""

    key: str
    title: str
    age_years: float
    medical_factors: MedicalFactors
    criterion: str
    matches: Callable[[SimulationResult], bool]


def _first_cycles(result: SimulationResult):
    return result.cycles[:DISPLAY_CYCLES]


def _age31_low_matches(result: SimulationResult) -> bool:
    cycles = _first_cycles(result)
    lengths = [cycle.cycle_length for cycle in cycles]
    return (
        len(cycles) == DISPLAY_CYCLES
        and sum(lengths) <= SEARCH_DAYS
        and result.profile.cycle_variability_component == "low"
        and all(cycle.ovulatory for cycle in cycles)
        and max(lengths) - min(lengths) <= 4
        and cycle_irregularity(lengths) <= 2.0
    )


def _age31_high_matches(result: SimulationResult) -> bool:
    cycles = _first_cycles(result)
    lengths = [cycle.cycle_length for cycle in cycles]
    return (
        len(cycles) == DISPLAY_CYCLES
        and sum(lengths) <= SEARCH_DAYS
        and result.profile.cycle_variability_component == "high"
        and all(cycle.ovulatory for cycle in cycles)
        and max(lengths) - min(lengths) >= 8
        and cycle_irregularity(lengths) >= 4.0
    )


def _perimenopause_mixed_matches(result: SimulationResult) -> bool:
    cycles = _first_cycles(result)
    if len(cycles) != DISPLAY_CYCLES or result.profile.stage != "perimenopause":
        return False
    lengths = [cycle.cycle_length for cycle in cycles]
    long_cycles = [cycle for cycle in cycles if cycle.cycle_length >= 36]
    ordinary_cycles = [cycle for cycle in cycles if 24 <= cycle.cycle_length <= 35]
    return (
        min(lengths) >= 21
        and max(lengths) <= 60
        and sum(lengths) <= SEARCH_DAYS
        and any(not cycle.ovulatory for cycle in long_cycles)
        and any(cycle.ovulatory for cycle in long_cycles)
        and sum(cycle.ovulatory for cycle in ordinary_cycles) >= 2
    )


DISPLAY_CASES = (
    DisplayCase(
        key="age31_low",
        title="A. Age 31, selected low-variability ovulatory profile",
        age_years=31.0,
        medical_factors=MedicalFactors(),
        criterion=(
            "first seven cycles all ovulatory; fitted low-variability component; length range "
            "<=4 days; mean absolute adjacent difference <=2 days; all seven fit inside the "
            "360-day render horizon"
        ),
        matches=_age31_low_matches,
    ),
    DisplayCase(
        key="age31_high",
        title="B. Age 31, selected high-variability ovulatory profile",
        age_years=31.0,
        medical_factors=MedicalFactors(),
        criterion=(
            "first seven cycles all ovulatory; fitted high-variability component; length range "
            ">=8 days; mean absolute adjacent difference >=4 days; all seven fit inside the "
            "360-day render horizon"
        ),
        matches=_age31_high_matches,
    ),
    DisplayCase(
        key="age52_perimenopause",
        title="C. Age 52 with explicit perimenopause modifier, selected mixed profile",
        age_years=52.0,
        medical_factors=MedicalFactors(perimenopause=True),
        criterion=(
            "first seven cycles 21-60 days; at least one long (>=36-day) anovulatory cycle, "
            "one long ovulatory cycle, two ordinary-length ovulatory cycles, and all seven fit "
            "inside the 360-day render horizon"
        ),
        matches=_perimenopause_mixed_matches,
    ),
)


def select_display_cases(max_seed: int = 5000) -> list[tuple[DisplayCase, int, SimulationResult]]:
    """Return the first seed meeting each declared display criterion."""

    selected: list[tuple[DisplayCase, int, SimulationResult]] = []
    for case in DISPLAY_CASES:
        for seed in range(max_seed + 1):
            patient_id = f"display-{case.key}-seed-{seed}"
            result = simulate_diary(
                days=SEARCH_DAYS,
                age_years=case.age_years,
                medical_factors=case.medical_factors,
                seed=seed,
                patient_id=patient_id,
                start_mode="cycle_day_1",
            )
            if case.matches(result):
                selected.append((case, seed, result))
                break
        else:
            raise RuntimeError(
                f"No display seed met criterion {case.key!r} through seed {max_seed}."
            )
    return selected


def _selection_manifest(
    selected: list[tuple[DisplayCase, int, SimulationResult]],
    max_seed: int,
) -> dict[str, object]:
    cases = []
    for case, seed, result in selected:
        cycles = _first_cycles(result)
        cases.append(
            {
                "key": case.key,
                "title": case.title,
                "criterion": case.criterion,
                "search_order": f"ascending integer seeds 0..{max_seed}; first match retained",
                "selected_seed": seed,
                "patient_id": result.profile.patient_id,
                "age_years": result.profile.age_years,
                "stage": result.profile.stage,
                "medical_factors": result.profile.medical_factors.to_dict(),
                "cycle_lengths": [cycle.cycle_length for cycle in cycles],
                "ovulatory": [cycle.ovulatory for cycle in cycles],
            }
        )
    return {
        "simulator_version": "0.4.0",
        "selection_role": "illustrative, not validation observations",
        "selection_is_executable": True,
        "display_cycles": DISPLAY_CYCLES,
        "cases": cases,
    }


def render(
    output_png: Path,
    output_svg: Path,
    days: int = SEARCH_DAYS,
    manifest_path: Path | None = None,
    max_seed: int = 5000,
) -> None:
    """Write three complete-cycle examples with overlaid, shared hormone scales."""

    del days  # Retained for backward-compatible callers; seven complete cycles are always shown.
    output_png.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_path or (
        ROOT / "examples" / "reports" / "healthy_cycle_example_selection_v14.json"
    )
    selected = select_display_cases(max_seed=max_seed)
    manifest = _selection_manifest(selected, max_seed)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    cropped_rows = []
    for _, _, result in selected:
        stop_day = sum(cycle.cycle_length for cycle in _first_cycles(result))
        cropped_rows.append(result.diary[:stop_day])
    e2_upper = 1.12 * max(row.estradiol_pg_ml for rows in cropped_rows for row in rows)
    p4_upper = 1.12 * max(row.progesterone_ng_ml for rows in cropped_rows for row in rows)

    fig, axes = plt.subplots(len(selected), 1, figsize=(15.8, 10.6))
    for row_index, ((case, seed, result), rows) in enumerate(zip(selected, cropped_rows)):
        e2_axis = axes[row_index]
        p4_axis = e2_axis.twinx()
        x = np.arange(1, len(rows) + 1)
        e2 = np.asarray([row.estradiol_pg_ml for row in rows])
        p4 = np.asarray([row.progesterone_ng_ml for row in rows])
        cycles = _first_cycles(result)
        lengths = [cycle.cycle_length for cycle in cycles]
        states = ["O" if cycle.ovulatory else "AO" for cycle in cycles]
        mad = cycle_irregularity(lengths)

        e2_axis.plot(x, e2, color=E2_COLOR, linewidth=1.65, zorder=3)
        p4_axis.plot(x, p4, color=P4_COLOR, linewidth=1.65, zorder=4)
        e2_axis.set_ylim(0.0, e2_upper)
        p4_axis.set_ylim(0.0, p4_upper)
        e2_axis.set_xlim(1, len(rows))
        e2_axis.grid(axis="y", alpha=0.16)
        e2_axis.spines["top"].set_visible(False)
        p4_axis.spines["top"].set_visible(False)
        p4_axis.patch.set_visible(False)

        # Show each bleeding day twice: a light full-height tint locates it against the
        # hormone curves, and an opaque baseline rug makes the daily binary event explicit.
        for record in rows:
            if record.uterine_bleeding:
                e2_axis.axvspan(
                    record.day_index - 0.5,
                    record.day_index + 0.5,
                    color=BLEED_COLOR,
                    alpha=0.055,
                    linewidth=0,
                    zorder=0,
                )
                e2_axis.axvspan(
                    record.day_index - 0.5,
                    record.day_index + 0.5,
                    ymin=0.0,
                    ymax=0.055,
                    facecolor=BLEED_COLOR,
                    alpha=0.82,
                    edgecolor="white",
                    linewidth=0.28,
                    zorder=2,
                )
        for cycle_end in np.cumsum(lengths)[:-1]:
            e2_axis.axvline(
                cycle_end + 0.5,
                color="#777777",
                linestyle="--",
                linewidth=0.75,
                alpha=0.42,
                zorder=1,
            )

        for record in rows:
            if record.ovulation:
                e2_axis.scatter(
                    record.day_index,
                    e2_upper * 0.96,
                    marker="v",
                    s=28,
                    color=OVULATION_COLOR,
                    zorder=5,
                )

        subtitle = (
            f"first seed {seed} · lengths {'/'.join(map(str, lengths))} d · "
            f"{'/'.join(states)} · adjacent MAD {mad:.1f} d"
        )
        e2_axis.set_title(DISPLAY_TITLES[case.key], loc="left", fontsize=10.8, pad=28)
        e2_axis.text(
            0.0,
            1.015,
            subtitle,
            transform=e2_axis.transAxes,
            fontsize=8.4,
            color="#555555",
            va="bottom",
        )
        e2_axis.set_ylabel("Estradiol (pg/mL)", color="#85352E")
        p4_axis.set_ylabel("Progesterone (ng/mL)", color="#1C477A", rotation=270, labelpad=18)
        e2_axis.tick_params(axis="y", colors="#85352E")
        p4_axis.tick_params(axis="y", colors="#1C477A")
        e2_axis.set_xlabel("Simulation day")

    handles = [
        plt.Line2D([0], [0], color=E2_COLOR, lw=2, label="Estradiol envelope"),
        plt.Line2D([0], [0], color=P4_COLOR, lw=2, label="Progesterone envelope"),
        plt.Rectangle(
            (0, 0),
            1,
            1,
            facecolor=BLEED_COLOR,
            edgecolor="none",
            alpha=0.82,
            label="Bleeding day (baseline band)",
        ),
        plt.Line2D(
            [0],
            [0],
            color="#777777",
            linestyle="--",
            lw=0.9,
            alpha=0.65,
            label="Cycle boundary",
        ),
        plt.Line2D(
            [0],
            [0],
            marker="v",
            color="none",
            markerfacecolor=OVULATION_COLOR,
            markeredgecolor=OVULATION_COLOR,
            label="Ovulation",
        ),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=5, frameon=False, bbox_to_anchor=(0.5, 0.992))
    fig.suptitle(
        "Selected synthetic daily hormone envelopes",
        fontsize=16,
        fontweight="bold",
        y=1.012,
    )
    fig.text(
        0.5,
        0.004,
        (
            "Seven complete cycles per case; E2 and P4 share one time panel but retain separate "
            "common scales across rows. Red baseline cells are individual bleeding days. These are "
            "latent daily envelopes, not measured serum traces. Selection criteria and seed search are "
            f"recorded in {manifest_path.name}."
        ),
        ha="center",
        fontsize=9.2,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.95), h_pad=2.25)
    fig.savefig(output_png, dpi=220, bbox_inches="tight", facecolor="white")
    fig.savefig(output_svg, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-png",
        type=Path,
        default=ROOT / "examples" / "reports" / "healthy_cycle_example_traces_v14.png",
    )
    parser.add_argument(
        "--output-svg",
        type=Path,
        default=ROOT / "examples" / "reports" / "healthy_cycle_example_traces_v14.svg",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "examples" / "reports" / "healthy_cycle_example_selection_v14.json",
    )
    parser.add_argument("--days", type=int, default=SEARCH_DAYS)
    parser.add_argument("--max-seed", type=int, default=5000)
    args = parser.parse_args()
    render(args.output_png, args.output_svg, args.days, args.manifest, args.max_seed)
    print(args.output_png.resolve())
    print(args.output_svg.resolve())
    print(args.manifest.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
