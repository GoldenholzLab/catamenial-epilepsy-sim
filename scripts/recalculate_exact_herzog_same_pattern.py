"""Recalculate the exact three-cycle union from saved per-pattern labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paper1_null_ce.core.summarize import summarize_window_results


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recalculate(source: Path, destination: Path) -> dict:
    windows = pd.read_parquet(
        source,
        filters=[("window_type", "==", "cycle"), ("phase_mode", "==", "strict_herzog")],
    )
    windows = windows[windows["window_value"].astype(str) == "3"].copy()
    assert not windows.duplicated(["cohort", "participant_id"]).any()
    old = windows["label_A_exact_any"].astype("boolean")
    windows["label_A_exact_any_before_correction"] = old
    corrected = pd.Series(pd.NA, index=windows.index, dtype="boolean")
    audit = {}
    for cohort, group in windows.groupby("cohort"):
        columns = ["label_A_exact_C1", "label_A_exact_C2"]
        if cohort == "population":
            columns.append("label_A_exact_C3")
        patterns = group[columns].astype("boolean")
        positive = patterns.eq(True).fillna(False).any(axis=1)
        negative = patterns.eq(False).fillna(False).all(axis=1)
        corrected.loc[group.index[positive]] = True
        corrected.loc[group.index[negative]] = False
        previous = old.loc[group.index]
        current = corrected.loc[group.index]
        assert not (current.eq(True).fillna(False) & ~previous.eq(True).fillna(False)).any()
        audit[cohort] = {
            "attempted": len(group),
            "previous_positive": int(previous.eq(True).sum()),
            "previous_classifiable": int(previous.notna().sum()),
            "corrected_positive": int(current.eq(True).sum()),
            "corrected_classifiable": int(current.notna().sum()),
            "corrected_indeterminate": int(current.isna().sum()),
            "newly_indeterminate": int((previous.notna() & current.isna()).sum()),
        }
    windows["label_A_exact_any"] = corrected
    newly_indeterminate = old.notna() & corrected.isna()
    windows.loc[newly_indeterminate, "a_exact_reason"] = "undefined_cycle_ratio"
    # Keep the existing per-pattern and cycle-level indeterminate policies.
    # Only the order of the union and two-of-three operations changes.
    summary_input = windows.drop(
        columns=[c for c in windows if c.startswith("label_") and c != "label_A_exact_any"]
    )
    summary = summarize_window_results(summary_input)
    headline = summary[summary["subset"] == "all"].copy()
    for cohort, positive, classifiable in [
        ("healthy_ovulatory", 8501, 18803),
        ("population", 6285, 15291),
    ]:
        row = headline[headline["cohort"] == cohort].iloc[0]
        assert int(row["positives"]) == positive
        assert int(row["n_classifiable"]) == classifiable
        assert int(row["n_windows"]) == 50000
    destination.mkdir(parents=True, exist_ok=True)
    windows.to_parquet(destination / "window_results.parquet", index=False)
    summary.to_csv(destination / "summary_tables.csv", index=False)
    headline.to_csv(destination / "headline_results.csv", index=False)
    payload = {
        "source": str(source.resolve()),
        "source_sha256": sha256(source),
        "classifier_sha256": sha256(ROOT / "src/paper1_null_ce/core/classifiers_exact.py"),
        "rule": "Same applicable pattern positive in at least two of three complete 23-35-day cycles",
        "union": "Positive if any applicable subject pattern is true; negative if all are false; otherwise indeterminate",
        "retained_policies": "Original per-pattern eligibility and conservative undefined-cycle-ratio handling",
        "cohorts": audit,
        "headline_results": headline.to_dict(orient="records"),
    }
    (destination / "recalculation_audit.json").write_text(json.dumps(payload, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = recalculate(args.source, args.destination)
    print(json.dumps(result["cohorts"], indent=2))
