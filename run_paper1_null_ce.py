#!/usr/bin/env python3
"""Single entrypoint for the Paper 1 null catamenial-epilepsy analysis."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paper1_null_ce.core.simulate import run_pipeline
from paper1_null_ce.core.summarize import DEFINITION_COLUMNS
from paper1_null_ce.core.utils import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--smoke-test", action="store_true", help="Run N=100, 6-month smoke analysis.")
    group.add_argument("--full", action="store_true", help="Run the full N=100,000, 36-month analysis.")
    group.add_argument("--mode", help="Explicit analysis mode from config.yaml, e.g. smoke, full, coupled_smoke, or coupled_full.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    mode = args.mode or ("full" if args.full else "smoke")
    if mode not in config["analysis_modes"]:
        raise KeyError(f"Unknown mode {mode!r}; available modes: {sorted(config['analysis_modes'])}")
    result = run_pipeline(config, mode=mode)

    print(f"mode: {mode}")
    print(f"total runtime: {result['runtime_seconds']:.2f} seconds")
    print("total number of classifiable windows by definition:")
    window_results = result["window_results"]
    for definition, col in DEFINITION_COLUMNS.items():
        if col in window_results:
            print(f"  {definition}: {int(window_results[col].notna().sum())}")
    print("headline false-positive rates by cohort and definition:")
    headline = result["headline"]
    if headline.empty:
        print("  no classifiable full-window headline rows")
    else:
        for _, row in headline.iterrows():
            fpr = row["false_positive_rate"]
            lo = row["wilson95_low"]
            hi = row["wilson95_high"]
            print(
                f"  {row['cohort']} {row['definition']}: "
                f"{fpr:.4f} ({lo:.4f}, {hi:.4f}), n={int(row['n_classifiable'])}"
            )
    print("locations of output files:")
    for path in result["output_paths"]:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
