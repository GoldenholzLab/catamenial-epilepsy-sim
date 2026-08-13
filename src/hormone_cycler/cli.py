"""Command-line interface for simulation, population generation, and validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .model import (
    DIARY_START_CYCLE_DAY_1,
    DIARY_START_RANDOM,
    simulate_diary,
    write_diary_csv,
    write_result_json,
)
from .population import simulate_population, write_population_json
from .types import MedicalFactors
from .validation import run_population_validation, write_validation_report


def add_factor_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach the supported medical-factor flags to an ``argparse`` parser."""

    parser.add_argument("--pcos", action="store_true", help="Enable PCOS profile modifiers.")
    parser.add_argument("--oral-contraceptive-mode", choices=["cyclic", "continuous"], help="Combined OCP regimen.")
    parser.add_argument("--hormonal-iud", action="store_true", help="Enable levonorgestrel IUD profile.")
    parser.add_argument("--copper-iud", action="store_true", help="Enable copper IUD profile.")
    parser.add_argument("--perimenopause", action="store_true", help="Force a perimenopause profile.")
    parser.add_argument("--peri-menarche", action="store_true", help="Force a peri-menarche profile.")
    parser.add_argument("--dysmenorrhea", action="store_true", help="Enable dysmenorrhea phenotype modifiers.")


def factors_from_args(args: argparse.Namespace) -> MedicalFactors:
    """Build a :class:`MedicalFactors` instance from parsed CLI arguments."""

    return MedicalFactors(
        pcos=args.pcos,
        oral_contraceptive_mode=args.oral_contraceptive_mode,
        hormonal_iud=args.hormonal_iud,
        copper_iud=args.copper_iud,
        perimenopause=args.perimenopause,
        peri_menarche=args.peri_menarche,
        dysmenorrhea=args.dysmenorrhea,
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser for simulation, population, and validation."""

    parser = argparse.ArgumentParser(prog="hormone_cycler", description="Data-calibrated menstrual cycle simulator.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    simulate_parser = subparsers.add_parser("simulate", help="Simulate a single diary.")
    simulate_parser.add_argument("--days", type=int, required=True)
    simulate_parser.add_argument("--age", type=float, required=True)
    simulate_parser.add_argument("--seed", type=int, default=11)
    simulate_parser.add_argument("--patient-id", default="patient-0001")
    simulate_parser.add_argument(
        "--start-mode",
        choices=[DIARY_START_RANDOM, DIARY_START_CYCLE_DAY_1],
        default=DIARY_START_RANDOM,
        help="Begin at a random first-cycle phase (default) or explicitly at cycle day 1.",
    )
    simulate_parser.add_argument("--csv-output", type=Path, help="Write diary rows to CSV.")
    simulate_parser.add_argument("--json-output", type=Path, help="Write the full result to JSON.")
    add_factor_arguments(simulate_parser)

    population_parser = subparsers.add_parser("population", help="Simulate a population of diaries.")
    population_parser.add_argument("--patients", type=int, default=10_000)
    population_parser.add_argument("--days", type=int, default=365)
    population_parser.add_argument("--seed", type=int, default=7)
    population_parser.add_argument("--json-output", type=Path, required=True)
    population_parser.add_argument("--include-diaries", action="store_true", help="Embed sample diaries in the JSON payload.")
    population_parser.add_argument(
        "--start-mode",
        choices=[DIARY_START_RANDOM, DIARY_START_CYCLE_DAY_1],
        default=DIARY_START_RANDOM,
        help="First-cycle observation rule for each diary.",
    )
    add_factor_arguments(population_parser)

    validate_parser = subparsers.add_parser("validate", help="Compare simulated cohorts with literature targets.")
    validate_parser.add_argument("--patients", type=int, default=10_000)
    validate_parser.add_argument("--days", type=int, default=365)
    validate_parser.add_argument("--seed", type=int, default=7)
    validate_parser.add_argument("--json-output", type=Path)
    validate_parser.add_argument("--skip-subgroups", action="store_true")
    validate_parser.add_argument(
        "--start-mode",
        choices=[DIARY_START_RANDOM, DIARY_START_CYCLE_DAY_1],
        default=DIARY_START_RANDOM,
        help="First-cycle observation rule for all validation diaries.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the ``hormone_cycler`` command-line interface.

    Args:
        argv: Optional argument vector. When omitted, ``argparse`` reads ``sys.argv``.

    Returns:
        Process exit status code.
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "simulate":
        result = simulate_diary(
            days=args.days,
            age_years=args.age,
            medical_factors=factors_from_args(args),
            seed=args.seed,
            patient_id=args.patient_id,
            start_mode=args.start_mode,
        )
        if args.csv_output:
            write_diary_csv(result, args.csv_output)
        if args.json_output:
            write_result_json(result, args.json_output)
        if not args.csv_output and not args.json_output:
            print(json.dumps(result.to_dict(), indent=2))
        return 0

    if args.command == "population":
        payload = simulate_population(
            num_patients=args.patients,
            days=args.days,
            seed=args.seed,
            medical_factors=factors_from_args(args),
            include_diaries=args.include_diaries,
            start_mode=args.start_mode,
        )
        write_population_json(payload, args.json_output)
        return 0

    if args.command == "validate":
        report = run_population_validation(
            num_patients=args.patients,
            days=args.days,
            seed=args.seed,
            include_subgroups=not args.skip_subgroups,
            start_mode=args.start_mode,
        )
        if args.json_output:
            write_validation_report(report, args.json_output)
        else:
            print(json.dumps(report, indent=2))
        return 0

    parser.error("Unsupported command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
