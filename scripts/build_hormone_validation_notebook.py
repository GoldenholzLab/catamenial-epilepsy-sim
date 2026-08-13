#!/usr/bin/env python3
"""Build the executable hormone-cycle validation and kinetic-check notebook."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import nbformat as nbf


def _code(source: str) -> object:
    return nbf.v4.new_code_cell(textwrap.dedent(source).strip())


def _markdown(source: str) -> object:
    return nbf.v4.new_markdown_cell(textwrap.dedent(source).strip())


def build_notebook() -> object:
    """Return a notebook that reproduces target and kinetic validation checks."""

    cells = [
        _markdown(
            """
            # `hormone_cycler` healthy-cycle calibration and validation

            This notebook distinguishes two kinds of evidence:

            1. **Calibration-target reproduction:** simulated age-band means, within-person SDs,
               participant-level irregularity, cycle tails, phase lengths, and bleeding are
               compared with Li et al. (AWHS) and Bull et al.
            2. **Held-out external cross-check:** 12-month participant summaries are compared with
               Cunningham et al.'s independent global Flo cohort, which was not used for fitting.
            3. **Waveform validation:** Stricker et al.'s complete daily LH-aligned serum medians
               determine the luteal envelope. Anckaert et al.'s separate 85-woman serum cohort is
               an independent subphase amplitude/order check. Daily morphology checks require a
               broad postovulatory progesterone summit, correctly ordered rise/peak/withdrawal,
               a secondary luteal estradiol rise, and continuity across cycle boundaries.
            4. **Long-follicular estradiol stress test:** Harlow et al.'s observed delayed-dominant-
               emergence and failed-dominant-wave geometries are shown without stretching one
               ordinary E2 curve across all extra follicular days. Mumford et al. provides an
               independent timing context: long-cycle E2 peaks were about three days later, not
               proportionally stretched over the entire long cycle.

            The central correction in v0.2.0 is estimand alignment: AWHS classified a participant
            as irregular when that person's *mean adjacent-cycle difference* was at least seven
            days. The table footnote omits “absolute,” but the methods define adjacent-cycle
            differences as absolute values; v0.2.0 follows that convention. The previous notebook
            instead averaged pairwise threshold exceedances.

            The baseline validation cohort is restricted to ages 18–54.9 because AWHS enrollment
            required adulthood. The separate peri-menarche modifier scenario retains adolescent
            ages and tests that distinct physiology explicitly.
            """
        ),
        _code(
            """
            from pathlib import Path
            import json
            import os
            import sys

            ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
            sys.path.insert(0, str(ROOT / "src"))
            sys.path.insert(0, str(ROOT / "scripts"))
            os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib-cache"))

            import matplotlib.pyplot as plt
            import pandas as pd
            from IPython.display import display

            from hormone_cycler.literature import CITATIONS
            from hormone_cycler.model import simulate_diary
            from hormone_cycler.validation import run_population_validation
            from render_healthy_cycle_examples_v12 import render as render_examples
            from render_hormone_validation_figure_v12 import render as render_validation_figure

            REPORT_PATH = ROOT / "examples" / "reports" / "healthy_cycle_validation_v12.json"
            KINETICS_FIGURE_PATH = ROOT / "examples" / "reports" / "hormone_kinetics_validation.png"
            VALIDATION_FIGURE_PATH = ROOT / "examples" / "reports" / "hormone_cycle_validation_v12.png"
            EXAMPLE_PNG_PATH = ROOT / "examples" / "reports" / "healthy_cycle_example_traces_v12.png"
            EXAMPLE_SVG_PATH = ROOT / "examples" / "reports" / "healthy_cycle_example_traces_v12.svg"
            WAVEFORM_FIGURE_PATH = ROOT / "examples" / "reports" / "hormone_waveform_validation_v13.png"
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            """
        ),
        _markdown(
            """
            ## Cohort-size convergence

            All runs use the same deterministic base seed but generate distinct patient seeds.
            The baseline cohorts are ages 18–54.9, matching AWHS adult eligibility. The retained
            16-diary hormone sample is balanced across the eight age bands (two per band) so the
            kinetic checks are not restricted to participants younger than 20 years.
            """
        ),
        _code(
            """
            cohort_sizes = [500, 2_000, 10_000]
            reports = {
                size: run_population_validation(
                    num_patients=size,
                    days=365,
                    seed=7,
                    include_subgroups=(size == 10_000),
                    start_mode="random",
                )
                for size in cohort_sizes
            }

            convergence = pd.DataFrame(
                [
                    {
                        "patients": size,
                        "overall_passed": report["baseline_passed"],
                        "calibration_passed": report["calibration_passed"],
                        "external_crosscheck_passed": report["external_crosscheck_passed"],
                        "checks_passed": sum(metric["passed"] for metric in report["baseline_metrics"]),
                        "checks_total": len(report["baseline_metrics"]),
                        "hormone_diaries": report["hormone_smoke_sample"]["n_diaries"],
                    }
                    for size, report in reports.items()
                ]
            )
            display(convergence)
            print("10,000-participant hormone sample by age band:")
            display(pd.Series(reports[10_000]["hormone_smoke_sample"]["age_band_counts"], name="diaries").to_frame())
            """
        ),
        _markdown(
            """
            ## Healthy-cycle calibration outcomes

            The AWHS comparisons use equal participant weighting and at most the first 11 cycles,
            matching the source cohort's median follow-up. Within-person SD is pooled after
            subtracting each participant's mean. Irregularity is the proportion of participants
            whose mean absolute adjacent-cycle difference is at least seven days.
            """
        ),
        _code(
            """
            full_report = reports[10_000]
            calibration_cycle_metrics = pd.DataFrame(
                [
                    metric for metric in full_report["calibration_metrics"]
                    if metric["name"].startswith("cycle_")
                ]
            )
            display(calibration_cycle_metrics[["name", "observed", "expected", "lower_bound", "upper_bound", "passed"]])
            assert calibration_cycle_metrics["passed"].all()
            """
        ),
        _markdown(
            """
            ## Held-out external cross-check

            Cunningham et al. use different inclusion filters and average each user's ordinary
            12-month sample SD, so these values are not expected to equal AWHS mixed-model residual
            SDs. Agreement is strongest from ages 26–45. The simulator remains higher than Flo at
            ages 51–55, while closely matching the larger AWHS residual SD; that conflict is retained
            as a limitation rather than hidden by refitting to the held-out cohort.
            """
        ),
        _code(
            """
            external_metrics = pd.DataFrame(full_report["external_crosscheck_metrics"])
            display(external_metrics[["name", "observed", "expected", "lower_bound", "upper_bound", "passed", "notes"]])
            assert external_metrics["passed"].all()
            """
        ),
        _markdown(
            """
            ## Hormone amplitude and daily-morphology checks

            The amplitude rows compare simulated subphases with Anckaert et al., which was not used
            to build the waveform. Broad windows are intentional because the cohorts and assays
            differ. The daily rows then test the specific morphology that motivated this update:
            P4 plateau width, rise and peak timing, withdrawal, the luteal E2 rebound, and boundary
            continuity. This separates external amplitude evidence from internal shape checks.
            """
        ),
        _code(
            """
            hormone_metrics = pd.DataFrame(
                [
                    metric
                    for metric in full_report["baseline_metrics"]
                    if metric["name"].startswith(("estradiol_", "progesterone_"))
                ]
            )
            display(
                hormone_metrics[
                    ["name", "observed", "expected", "lower_bound", "upper_bound", "passed", "notes"]
                ]
            )
            assert hormone_metrics["passed"].all()
            """
        ),
        _markdown(
            """
            ## Direct visual and numerical kinetic check

            The displayed interval contains one complete ovulatory cycle plus the first day of the
            next cycle. Estradiol and progesterone have separate axes because their units and scales
            are not commensurate. The dashed line is the next bleeding onset/cycle boundary.
            """
        ),
        _code(
            """
            result = simulate_diary(
                days=140,
                age_years=31,
                seed=1,
                patient_id="kinetic-validation",
                start_mode="cycle_day_1",
            )
            complete_cycle = next(cycle for cycle in result.cycles if cycle.ovulatory)
            cycle_rows = [row for row in result.diary if row.cycle_index == complete_cycle.cycle_index]
            next_rows = [row for row in result.diary if row.cycle_index == complete_cycle.cycle_index + 1]
            display_rows = cycle_rows + next_rows[:1]

            e2 = [row.estradiol_pg_ml for row in cycle_rows[: complete_cycle.ovulation_day]]
            p4 = [row.progesterone_ng_ml for row in cycle_rows]
            peak_width = sum(value >= 0.80 * max(e2) for value in e2)
            p4_peak = max(p4)
            p4_peak_day = p4.index(p4_peak) + 1
            p4_plateau_width = sum(value >= 0.75 * p4_peak for value in p4)
            p4_rise_day = next(
                day
                for day, value in enumerate(p4, start=1)
                if day >= complete_cycle.ovulation_day and value >= 5.0
            )
            luteal_e2 = [row.estradiol_pg_ml for row in cycle_rows[complete_cycle.ovulation_day:]]
            secondary_e2_ratio = max(luteal_e2) / max(e2)
            withdrawal_transitions = 0
            for earlier, later in zip(reversed(p4[:-1]), reversed(p4[1:])):
                if later < earlier:
                    withdrawal_transitions += 1
                else:
                    break
            diagnostics = pd.DataFrame(
                [
                    {"check": "Estradiol days at >=80% follicular maximum", "observed": peak_width, "criterion": ">=2 days"},
                    {"check": "Luteal E2 peak / follicular E2 peak", "observed": secondary_e2_ratio, "criterion": "0.35-0.80"},
                    {"check": "Progesterone days at >=75% maximum", "observed": p4_plateau_width, "criterion": "3-9 days"},
                    {"check": "Progesterone peak offset from ovulation", "observed": p4_peak_day - complete_cycle.ovulation_day, "criterion": "3-9 days"},
                    {"check": "Progesterone 5 ng/mL rise offset", "observed": p4_rise_day - complete_cycle.ovulation_day, "criterion": "1-4 days"},
                    {"check": "Consecutive progesterone-decline transitions before bleeding", "observed": withdrawal_transitions, "criterion": ">=3"},
                    {"check": "Final-cycle progesterone / cycle maximum", "observed": p4[-1] / max(p4), "criterion": "<=0.20"},
                    {"check": "Progesterone jump across cycle boundary (ng/mL)", "observed": abs(next_rows[0].progesterone_ng_ml - p4[-1]), "criterion": "<=1.0"},
                    {"check": "Realized luteal length (days)", "observed": complete_cycle.luteal_length, "criterion": "9-17"},
                ]
            )
            display(diagnostics)

            x = list(range(1, len(display_rows) + 1))
            boundary = len(cycle_rows) + 0.5
            fig, axes = plt.subplots(3, 1, figsize=(13, 8.5), sharex=True, gridspec_kw={"height_ratios": [3, 3, 1]})
            axes[0].plot(x, [row.estradiol_pg_ml for row in display_rows], color="#C44E52", linewidth=2.2)
            axes[0].set_ylabel("Estradiol (pg/mL)")
            axes[0].set_title("Complete ovulatory cycle and first day of the next cycle")
            axes[1].plot(x, [row.progesterone_ng_ml for row in display_rows], color="#4C72B0", linewidth=2.2)
            axes[1].set_ylabel("Progesterone (ng/mL)")
            bleeding_x = [position for position, row in zip(x, display_rows) if row.uterine_bleeding]
            ovulation_x = [position for position, row in zip(x, display_rows) if row.ovulation]
            axes[2].bar(bleeding_x, [1] * len(bleeding_x), width=0.85, color="#DD8452", label="Bleeding")
            axes[2].scatter(ovulation_x, [1.08] * len(ovulation_x), marker="^", s=65, color="#55A868", label="Ovulation")
            axes[2].set_ylabel("Events")
            axes[2].set_xlabel("Day within displayed interval")
            axes[2].set_ylim(0, 1.25)
            axes[2].legend(frameon=False, loc="upper right")
            for axis in axes:
                axis.axvline(boundary, color="#666666", linestyle="--", linewidth=1.2)
            fig.suptitle("Hormone-waveform validation: luteal E2 rebound and broad P4 summit", fontsize=15)
            fig.tight_layout()
            fig.savefig(KINETICS_FIGURE_PATH, dpi=180, bbox_inches="tight")
            plt.show()
            """
        ),
        _markdown(
            """
            ## Ordinary versus prolonged-follicular E2 geometry

            The left panel holds luteal length and amplitude fixed while lengthening only the
            follicular phase. In the revised model the final maturation segment stays aligned to
            ovulation; excess time is assigned to a low/moderate early interval. The right panel
            shows the alternate failed-dominant-wave geometry described by Harlow et al. The 25%
            failed-wave share is an investigator-set heterogeneity component because the accessible
            report establishes pattern existence and identifies delayed emergence as most common,
            but does not supply class-frequency estimates suitable for calibration.
            """
        ),
        _code(
            """
            from hormone_cycler.model import (
                LONG_ESTRADIOL_DELAYED_EMERGENCE,
                LONG_ESTRADIOL_FAILED_WAVE,
                ovulatory_hormone_points,
                shape_preserving_curve,
            )

            waveform_cases = [
                ("Ordinary 29-day cycle", 29, 15, 14, LONG_ESTRADIOL_DELAYED_EMERGENCE),
                ("53-day delayed emergence", 53, 39, 14, LONG_ESTRADIOL_DELAYED_EMERGENCE),
                ("53-day failed wave", 53, 39, 14, LONG_ESTRADIOL_FAILED_WAVE),
            ]
            fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
            for label, cycle_length, follicular_length, luteal_length, variant in waveform_cases[:2]:
                points, _ = ovulatory_hormone_points(
                    cycle_length, follicular_length, luteal_length, 1.0, 1.0, variant
                )
                curve = shape_preserving_curve(points)
                relative_day = list(range(-follicular_length + 1, 1))
                values = [curve(float(day)) for day in range(1, follicular_length + 1)]
                axes[0].plot(relative_day, values, linewidth=2.0, label=label)
            axes[0].axvline(0, color="#27855B", linestyle="--", linewidth=1.2)
            axes[0].set_title("A. Extra days precede terminal maturation")
            axes[0].set_xlabel("Days relative to ovulation")
            axes[0].set_ylabel("Estradiol (pg/mL; scale=1)")
            axes[0].legend(frameon=False)

            for label, cycle_length, follicular_length, luteal_length, variant in waveform_cases[1:]:
                points, _ = ovulatory_hormone_points(
                    cycle_length, follicular_length, luteal_length, 1.0, 1.0, variant
                )
                curve = shape_preserving_curve(points)
                days = list(range(1, follicular_length + 1))
                axes[1].plot(days, [curve(float(day)) for day in days], linewidth=2.0, label=label)
            axes[1].axvline(39, color="#27855B", linestyle="--", linewidth=1.2)
            axes[1].set_title("B. Harlow-supported long-phase heterogeneity")
            axes[1].set_xlabel("Cycle day")
            axes[1].legend(frameon=False)
            for axis in axes:
                axis.grid(axis="y", alpha=0.18)
                axis.spines["top"].set_visible(False)
                axis.spines["right"].set_visible(False)
            fig.tight_layout()
            fig.savefig(WAVEFORM_FIGURE_PATH, dpi=200, bbox_inches="tight")
            plt.show()
            print(f"Wrote {WAVEFORM_FIGURE_PATH}")
            """
        ),
        _markdown(
            """
            ## Medical-factor checks and reproducibility artifact

            Factor-specific checks are run only after both the calibration suite and held-out
            cross-check pass. The JSON report preserves all estimands, targets, bounds, citations,
            and age-balanced sample counts.
            """
        ),
        _code(
            """
            subgroup_rows = []
            for name, payload in full_report.get("subgroup_analysis", {}).get("subgroups", {}).items():
                subgroup_rows.append(
                    {
                        "subgroup": name,
                        "passed": payload["passed"],
                        "mean_cycle_days": payload["summary"]["mean_cycle_days"],
                        "ovulation_rate": payload["summary"]["ovulation_rate"],
                        "mean_bleeding_days": payload["summary"]["mean_bleeding_days"],
                        "amenorrhea_rate": payload["summary"]["amenorrhea_rate"],
                    }
                )
            display(pd.DataFrame(subgroup_rows))

            REPORT_PATH.write_text(json.dumps(full_report, indent=2), encoding="utf-8")
            render_validation_figure(full_report, VALIDATION_FIGURE_PATH)
            render_examples(EXAMPLE_PNG_PATH, EXAMPLE_SVG_PATH)
            print(f"Wrote {REPORT_PATH}")
            print(f"Wrote {KINETICS_FIGURE_PATH}")
            print(f"Wrote {VALIDATION_FIGURE_PATH}")
            print(f"Wrote {EXAMPLE_PNG_PATH}")
            """
        ),
        _markdown(
            """
            ## Calibration references

            The machine-readable report contains full references and PubMed/source URLs for every
            target family, plus exact PMIDs, DOIs, and evidence roles. Stricker et al. supplies the
            daily waveform source; Anckaert et al. is the independent serum-subphase comparison;
            Harlow and Mumford constrain long-cycle morphology and timing. Threshold-based daily
            morphology criteria remain declared software validation guards rather than independent
            prevalence estimates. Modifier scenarios are age-matched direction/range software
            stress tests; their exact numerical margins are regression guards, not estimates copied
            from the cited papers.
            """
        ),
        _code(
            """
            pd.DataFrame(
                [
                    {
                        "key": key,
                        "evidence_role": citation.evidence_role,
                        "pmid": citation.pmid,
                        "doi": citation.doi,
                        "reference": citation.full_reference,
                        "url": citation.url,
                    }
                    for key, citation in CITATIONS.items()
                ]
            )
            """
        ),
    ]
    notebook = nbf.v4.new_notebook(cells=cells)
    notebook.metadata.kernelspec = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    notebook.metadata.language_info = {"name": "python", "version": "3"}
    return notebook


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="show_validation.ipynb")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(build_notebook(), output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
