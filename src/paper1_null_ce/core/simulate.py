"""End-to-end simulation and classification pipeline."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from paper1_null_ce.adapters.chocolates_adapter import ChocolatesAdapter
from paper1_null_ce.adapters.hormone_cycle_adapter import HormoneCycleAdapter
from paper1_null_ce.core.classifiers_exact import classify_exact_herzog2004
from paper1_null_ce.core.classifiers_historical import classify_historical_all
from paper1_null_ce.core.classifiers_windowed import (
    DEFAULT_THRESHOLDS,
    classify_a_windowed,
    classify_b_minimum_data,
    classify_reproducibility,
    pooled_adsf_and_ratios,
    window_base_fields,
)
from paper1_null_ce.core.merge_align import merge_independent_diaries
from paper1_null_ce.core.phase_labeling import add_phase_labels
from paper1_null_ce.core.regression_nb import classify_regression_nb, participant_alpha_from_full_diary
from paper1_null_ce.core.summarize import (
    DEFINITION_COLUMNS,
    headline_rates,
    summarize_indeterminate_reasons,
    summarize_participant_results,
    summarize_pattern_decomposition,
    summarize_study_level,
    summarize_window_results,
)
from paper1_null_ce.core.utils import elapsed_seconds, stable_seed, write_manifest
from paper1_null_ce.core.windows import (
    WindowSpec,
    sample_primary_windows,
    sample_study_pool_windows,
    subset_window,
)


REQUIRED_WINDOW_COLUMNS = [
    "participant_id",
    "cohort",
    "phase_mode",
    "window_type",
    "window_value",
    "window_start",
    "window_end",
    "n_days",
    "n_complete_cycles",
    "seizure_count_total",
    "seizure_days_total",
    "analyzable_flag",
    "indeterminate_reason",
    "strict_herzog_eligible_flag",
    "short_cycle_modified_flag",
    "luteal_anchored_ovulatory_flag",
    "c3_applicable_flag",
    "adsf_M",
    "adsf_O",
    "adsf_F",
    "adsf_L",
    "adsf_FL",
    "adsf_OLM",
    "rr_C1",
    "rr_C2",
    "rr_C3",
    "label_A_exact_any",
    "label_A_exact_C1",
    "label_A_exact_C2",
    "label_A_exact_C3",
    "label_A_windowed_any",
    "label_A_windowed_excluding_C3",
    "label_A_windowed_C1_or_C2",
    "label_A_windowed_C1",
    "label_A_windowed_C2",
    "label_A_windowed_C3",
    "label_A_windowed_pattern_category",
    "label_B_any",
    "label_B_excluding_C3",
    "label_B_C1_or_C2",
    "label_B_C1",
    "label_B_C2",
    "label_B_C3",
    "label_B_pattern_category",
    "label_C_any",
    "label_C_C1_or_C2",
    "label_C_C1",
    "label_C_C2",
    "label_C_C3",
    "label_C_pattern_category",
    "label_D_any",
    "label_D_C1_or_C2",
    "label_D_C1",
    "label_D_C2",
    "label_D_C3",
    "label_D_pattern_category",
    "label_D_window_alpha_any",
    "label_D_window_alpha_C1_or_C2",
    "label_H1_any",
    "label_H2_any",
    "label_H3_any",
    "label_H4_any",
]


def run_pipeline(config: dict[str, Any], mode: str = "smoke") -> dict[str, Any]:
    """Run the configured analysis mode and write all deliverables."""

    started = time.perf_counter()
    mode_cfg = config["analysis_modes"][mode]
    output_dir = Path(mode_cfg.get("output_dir", config.get("output_dir", "outputs")))
    output_dir.mkdir(parents=True, exist_ok=True)
    master_seed = int(config["master_seed"])
    days_per_month = int(config["days_per_month"])
    diary_months = int(mode_cfg["diary_months"])
    days = diary_months * days_per_month
    cohorts = _cohort_sizes(config, mode)
    n_jobs = int(mode_cfg.get("n_jobs", config.get("n_jobs", 1)))
    chunk_size = int(mode_cfg.get("chunk_size", config.get("chunk_size", 250)))
    progress = ProgressReporter(
        output_dir=output_dir,
        mode=mode,
        total_participants=sum(cohorts.values()),
        enabled=bool(mode_cfg.get("progress", config.get("progress", {}).get("enabled", True))),
        write_json=bool(mode_cfg.get("write_progress_json", config.get("progress", {}).get("write_json", True))),
        print_updates=bool(mode_cfg.get("print_progress", config.get("progress", {}).get("print_updates", True))),
        print_every_chunks=int(mode_cfg.get("print_every_chunks", config.get("progress", {}).get("print_every_chunks", 1))),
    )
    progress.start(
        {
            "n_jobs": n_jobs,
            "chunk_size": chunk_size,
            "cohorts": cohorts,
            "diary_months": diary_months,
            "days": days,
            "phase_modes": _configured_phase_modes(config, mode),
        }
    )

    participant_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    audit_frames: list[pd.DataFrame] = []
    study_pool_rows: list[dict[str, Any]] = []
    assumptions: set[str] = {
        "Definition D uses a participant-full-diary method-of-moments negative-binomial alpha recorded in d_alpha; "
        "Poisson robust fallback is recorded in d_reason when statsmodels NB fitting fails. Definition D_window_alpha "
        "re-estimates alpha from the analyzed window as a non-oracle sensitivity.",
        "Study-level Monte Carlo samples each selected participant from a deterministic pool of precomputed random "
        "valid 3-month windows to avoid retaining all daily diaries in memory.",
        "Historical definitions H1-H4 are assumption-based operationalizations and are flagged in summary outputs.",
    }

    for cohort, n_participants in cohorts.items():
        progress.update_stage(
            "participant_simulation",
            message=f"starting cohort {cohort}",
            cohort=cohort,
        )
        audit_ids = _audit_ids(cohort, n_participants, master_seed, float(config.get("audit_daily_fraction", 0.01)))
        for start in range(0, n_participants, chunk_size):
            chunk_started = time.perf_counter()
            stop = min(start + chunk_size, n_participants)
            args = [
                (
                    config,
                    mode,
                    cohort,
                    i,
                    days,
                    f"{cohort}-{i + 1:06d}",
                    f"{cohort}-{i + 1:06d}" in audit_ids,
                )
                for i in range(start, stop)
            ]
            if n_jobs == 1:
                results = [_simulate_one_participant(*item) for item in args]
            else:
                effective_jobs = os.cpu_count() if n_jobs < 0 else n_jobs
                sub_batches = _split_batches(args, max(1, min(len(args), int(effective_jobs or 1))))
                tasks = [delayed(_simulate_participant_batch)(sub_batch) for sub_batch in sub_batches]
                batch_results = Parallel(n_jobs=n_jobs, prefer="processes")(tasks)
                results = [item for batch in batch_results for item in batch]
            for result in results:
                participant_rows.append(result["participant_summary"])
                window_rows.extend(result["window_results"])
                study_pool_rows.extend(result["study_pool"])
                if result["audit_daily"] is not None:
                    audit_frames.append(result["audit_daily"])
                assumptions.update(result["assumptions"])
            progress.participants_completed(
                count=len(results),
                cohort=cohort,
                chunk_start=start + 1,
                chunk_end=stop,
                chunk_seconds=time.perf_counter() - chunk_started,
            )

    progress.update_stage("assembling_outputs", message="assembling participant and window tables")
    participant_summary = pd.DataFrame(participant_rows)
    window_results = pd.DataFrame(window_rows)
    study_pool = pd.DataFrame(study_pool_rows)
    audit_daily = pd.concat(audit_frames, ignore_index=True) if audit_frames else pd.DataFrame()

    progress.update_stage("study_level_monte_carlo", message="simulating study-level Monte Carlo")
    study_level = run_study_level_mc(study_pool, config, mode)
    progress.update_stage("summary_tables", message="summarizing false-positive and indeterminate rates")
    summary = pd.concat(
        [
            summarize_window_results(window_results),
            summarize_participant_results(window_results),
            summarize_pattern_decomposition(window_results),
            summarize_indeterminate_reasons(window_results),
            summarize_study_level(study_level),
        ],
        ignore_index=True,
        sort=False,
    )

    progress.update_stage("writing_outputs", message="writing parquet/csv outputs")
    paths = _write_outputs(output_dir, participant_summary, window_results, study_level, summary, audit_daily)
    from paper1_null_ce.core.plots import write_all_figures

    progress.update_stage("figures", message="writing publication figures")
    paths.extend(write_all_figures(output_dir, summary, study_level, audit_daily))
    progress.update_stage("manifest", message="writing manifest")
    manifest_path = write_manifest(output_dir, config, sorted(assumptions))
    paths.append(manifest_path)

    runtime = elapsed_seconds(started)
    progress.finish(runtime_seconds=runtime, output_files=[str(path) for path in paths])
    # ``finish`` updates progress.json one final time. Rewrite the manifest afterward so its
    # recorded progress checksum describes the completed run rather than the preceding
    # ``manifest`` stage. The first write above ensures a manifest still exists if finalization
    # itself is interrupted.
    write_manifest(output_dir, config, sorted(assumptions))
    headline = headline_rates(summary)
    return {
        "runtime_seconds": runtime,
        "participant_summary": participant_summary,
        "window_results": window_results,
        "study_level": study_level,
        "summary": summary,
        "headline": headline,
        "output_paths": paths,
        "assumptions": sorted(assumptions),
    }


@dataclass
class ProgressReporter:
    """Small progress logger with a console ETA and a JSON status file."""

    output_dir: Path
    mode: str
    total_participants: int
    enabled: bool = True
    write_json: bool = True
    print_updates: bool = True
    print_every_chunks: int = 1

    def __post_init__(self) -> None:
        self.started = time.perf_counter()
        self.completed = 0
        self.chunk_count = 0
        self.stage = "initializing"
        self.progress_path = self.output_dir / "progress.json"
        self.last_payload: dict[str, Any] = {}

    def start(self, details: dict[str, Any]) -> None:
        self._emit("initializing", message="starting analysis run", extra=details, force=True)

    def update_stage(self, stage: str, message: str | None = None, cohort: str | None = None) -> None:
        self.stage = stage
        self._emit(stage, message=message, cohort=cohort, force=True)

    def participants_completed(
        self,
        count: int,
        cohort: str,
        chunk_start: int,
        chunk_end: int,
        chunk_seconds: float,
    ) -> None:
        self.completed += count
        self.chunk_count += 1
        message = (
            f"{cohort} participants {chunk_start:,}-{chunk_end:,} completed "
            f"in {_format_duration(chunk_seconds)}"
        )
        self._emit(
            "participant_simulation",
            message=message,
            cohort=cohort,
            extra={"chunk_start": chunk_start, "chunk_end": chunk_end, "chunk_seconds": chunk_seconds},
            force=self.chunk_count % max(1, self.print_every_chunks) == 0,
        )

    def finish(self, runtime_seconds: float, output_files: list[str]) -> None:
        self.completed = self.total_participants
        self._emit(
            "complete",
            message=f"analysis complete in {_format_duration(runtime_seconds)}",
            extra={"runtime_seconds": runtime_seconds, "output_files": output_files},
            force=True,
        )

    def _emit(
        self,
        stage: str,
        message: str | None = None,
        cohort: str | None = None,
        extra: dict[str, Any] | None = None,
        force: bool = False,
    ) -> None:
        if not self.enabled:
            return
        elapsed = time.perf_counter() - self.started
        rate = self.completed / elapsed if elapsed > 0 else 0.0
        remaining = max(0, self.total_participants - self.completed)
        eta_seconds = remaining / rate if rate > 0 and stage == "participant_simulation" else None
        payload: dict[str, Any] = {
            "mode": self.mode,
            "stage": stage,
            "message": message,
            "cohort": cohort,
            "participants_completed": self.completed,
            "total_participants": self.total_participants,
            "percent_complete": 100.0 * self.completed / self.total_participants if self.total_participants else 100.0,
            "elapsed_seconds": elapsed,
            "elapsed": _format_duration(elapsed),
            "participants_per_second": rate,
            "eta_seconds": eta_seconds,
            "eta": _format_duration(eta_seconds) if eta_seconds is not None else None,
            "updated_unix_time": time.time(),
        }
        if extra:
            payload.update(extra)
        self.last_payload = payload
        if self.write_json:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.progress_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        if self.print_updates and force:
            eta_text = f", ETA {_format_duration(eta_seconds)}" if eta_seconds is not None else ""
            rate_text = f", {rate:.2f} participants/s" if rate > 0 else ""
            msg_text = f" - {message}" if message else ""
            print(
                f"[progress] {stage}: {self.completed:,}/{self.total_participants:,} "
                f"({payload['percent_complete']:.1f}%), elapsed {_format_duration(elapsed)}"
                f"{eta_text}{rate_text}{msg_text}",
                flush=True,
            )


def _format_duration(seconds: float | None) -> str:
    if seconds is None or math.isnan(seconds):
        return "unknown"
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes:d}m {secs:02d}s"
    return f"{secs:d}s"


def _cohort_sizes(config: dict[str, Any], mode: str) -> dict[str, int]:
    mode_cfg = config["analysis_modes"][mode]
    if "cohort_sizes" in mode_cfg:
        return {str(k): int(v) for k, v in mode_cfg["cohort_sizes"].items()}
    total = int(mode_cfg["n_total"])
    return {"healthy_ovulatory": total // 2, "population": total - total // 2}


def _configured_phase_modes(config: dict[str, Any], mode: str, cohort: str | None = None) -> list[str]:
    mode_cfg = config.get("analysis_modes", {}).get(mode, {})
    raw = mode_cfg.get("phase_modes", config.get("phase_modes", [config.get("phase_mode", "strict_herzog")]))
    if isinstance(raw, str):
        modes = [raw]
    else:
        modes = [str(item) for item in raw]
    deduped: list[str] = []
    for item in modes:
        if item not in deduped:
            deduped.append(item)
    if cohort is not None and cohort != "population":
        deduped = ["strict_herzog" if item == "modified_short_cycle" else item for item in deduped]
    return deduped


def _audit_ids(cohort: str, n: int, master_seed: int, fraction: float) -> set[str]:
    count = max(1, int(round(n * fraction))) if n > 0 else 0
    rng = np.random.default_rng(stable_seed(master_seed, cohort, "audit_sample"))
    selected = set(int(i) for i in rng.choice(np.arange(n), size=min(count, n), replace=False))
    return {f"{cohort}-{i + 1:06d}" for i in selected}


def _simulate_one_participant(
    config: dict[str, Any],
    mode: str,
    cohort: str,
    cohort_index: int,
    days: int,
    participant_id: str,
    audit_selected: bool,
) -> dict[str, Any]:
    return _simulate_one_participant_prepared(
        config,
        mode,
        cohort,
        cohort_index,
        days,
        participant_id,
        audit_selected,
        hormone_adapter=HormoneCycleAdapter(config),
        chocolates_adapter=ChocolatesAdapter(),
    )


def _simulate_participant_batch(args: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    config = args[0][0]
    hormone_adapter = HormoneCycleAdapter(config)
    chocolates_adapter = ChocolatesAdapter()
    return [
        _simulate_one_participant_prepared(
            *item,
            hormone_adapter=hormone_adapter,
            chocolates_adapter=chocolates_adapter,
        )
        for item in args
    ]


def _simulate_one_participant_prepared(
    config: dict[str, Any],
    mode: str,
    cohort: str,
    cohort_index: int,
    days: int,
    participant_id: str,
    audit_selected: bool,
    hormone_adapter: HormoneCycleAdapter,
    chocolates_adapter: ChocolatesAdapter,
) -> dict[str, Any]:
    master_seed = int(config["master_seed"])
    days_per_month = int(config["days_per_month"])

    hormone = hormone_adapter.simulate(
        participant_id=participant_id,
        cohort=cohort,
        days=days,
        seed=stable_seed(master_seed, participant_id, "hormone"),
        include_hormone_values=audit_selected,
    )
    seizure = chocolates_adapter.simulate(
        participant_id=participant_id,
        days=days,
        seed=stable_seed(master_seed, participant_id, "seizure"),
        default_seizure_frequency=config.get("default_seizure_frequency"),
        suppress_infradian=bool(config.get("suppress_infradian_seizure_cycles", False)),
    )
    base_daily = merge_independent_diaries(seizure.daily, hormone.daily)
    true_coupling = {
        **config.get("true_coupling", {}),
        **config.get("analysis_modes", {}).get(mode, {}).get("true_coupling", {}),
    }
    coupling_applied = bool(true_coupling.get("enabled", False))
    coupling_assumption = (
        "True-coupling positive-control modes add extra Poisson seizure events on target phase days "
        f"after diary alignment; target phase {true_coupling.get('target_phase', 'M')} and target "
        f"rate ratio {float(true_coupling.get('rate_ratio', 1.5)):.2f}."
        if coupling_applied
        else None
    )

    participant_summary = dict(hormone.participant_summary)
    participant_summary.update(
        {
            "seizure_count_total": int(base_daily["seizure_count"].sum()),
            "seizure_days_total": int(base_daily["seizure_day"].sum()),
            "seizure_days_per_month": float(base_daily["seizure_day"].sum() / (len(base_daily) / days_per_month)),
            "seizures_per_month": float(base_daily["seizure_count"].sum() / (len(base_daily) / days_per_month)),
            "mean_seizure_frequency_month": seizure.metadata.get("mean_seizure_frequency_month"),
            "latent_seizure_burden_metric": seizure.metadata.get("mean_seizure_frequency_month"),
            "dominant_seizure_cycle_days": seizure.metadata.get("dominant_seizure_cycle_days"),
            "true_coupling_applied": coupling_applied,
            "true_coupling_target_phase": str(true_coupling.get("target_phase", "M")) if coupling_applied else None,
            "true_coupling_target_rate_ratio": float(true_coupling.get("rate_ratio", 1.5)) if coupling_applied else np.nan,
        }
    )
    participant_summary["seizure_frequency_stratum"] = _seizure_frequency_stratum(
        participant_summary["seizure_days_per_month"]
    )
    participant_summary["cycle_regularity_stratum"] = _cycle_regularity_stratum(
        participant_summary["sd_cycle_length"]
    )

    alpha = participant_alpha_from_full_diary(base_daily, fallback=float(config.get("regression", {}).get("fallback_alpha", 1.0)))
    rng = np.random.default_rng(stable_seed(master_seed, participant_id, "windows"))
    window_sampling_daily = add_phase_labels(base_daily, mode="strict_herzog")
    primary_specs = sample_primary_windows(
        window_sampling_daily,
        rng,
        calendar_months=[int(x) for x in config["windows"]["calendar_months"]],
        cycle_counts=[int(x) for x in config["windows"]["cycle_counts"]],
        days_per_month=days_per_month,
    )
    study_specs = sample_study_pool_windows(
        window_sampling_daily,
        rng,
        n_per_participant=int(config["study_level"].get("window_pool_per_participant", 1)),
        months=int(config["study_level"]["window_months"]),
        days_per_month=days_per_month,
    )

    window_results: list[dict[str, Any]] = []
    study_pool: list[dict[str, Any]] = []
    audit_frames: list[pd.DataFrame] = []
    for phase_mode in _configured_phase_modes(config, mode, cohort):
        daily = add_phase_labels(base_daily, mode=phase_mode)
        if coupling_applied:
            daily = _apply_true_coupling(
                daily,
                seed=stable_seed(master_seed, participant_id, "true_coupling", phase_mode),
                target_phase=str(true_coupling.get("target_phase", "M")),
                rate_ratio=float(true_coupling.get("rate_ratio", 1.5)),
            )
        primary_phase = phase_mode == "strict_herzog"
        regression_enabled = bool(config.get("regression", {}).get("enabled", True)) and primary_phase
        window_results.extend(
            classify_window(
                participant_id,
                cohort,
                daily,
                spec,
                config,
                alpha,
                include_regression=regression_enabled,
                include_reproducibility=primary_phase,
                include_historical=primary_phase,
                phase_mode=phase_mode,
            )
            for spec in primary_specs
        )
        if primary_phase:
            study_pool.extend(
                classify_window(
                    participant_id,
                    cohort,
                    daily,
                    spec,
                    config,
                    alpha,
                    include_regression=regression_enabled,
                    include_reproducibility=True,
                    include_historical=True,
                    phase_mode=phase_mode,
                )
                for spec in study_specs
            )
        if audit_selected:
            audit_cols = [
                "participant_id",
                "calendar_day_index",
                "seizure_count",
                "seizure_day",
                "menses_onset_flag",
                "cycle_id",
                "cycle_day",
                "cycle_length",
                "ovulatory_flag",
                "ovulation_day",
                "ilp_flag",
                "progesterone",
                "estradiol",
                "phase",
                "backward_day",
            ]
            audit_daily = daily[[col for col in audit_cols if col in daily]].copy()
            audit_daily["cohort"] = cohort
            audit_daily["phase_mode"] = phase_mode
            audit_frames.append(audit_daily)
    stratification_fields = {
        "full_diary_seizure_days_per_month": participant_summary["seizure_days_per_month"],
        "full_diary_seizures_per_month": participant_summary["seizures_per_month"],
        "participant_mean_cycle_length": participant_summary["mean_cycle_length"],
        "participant_sd_cycle_length": participant_summary["sd_cycle_length"],
        "seizure_frequency_stratum": participant_summary["seizure_frequency_stratum"],
        "cycle_regularity_stratum": participant_summary["cycle_regularity_stratum"],
    }
    for row in window_results + study_pool:
        row.update(stratification_fields)
    audit_daily = pd.concat(audit_frames, ignore_index=True) if audit_frames else None
    return {
        "participant_summary": participant_summary,
        "window_results": window_results,
        "study_pool": study_pool,
        "audit_daily": audit_daily,
        "assumptions": set(hormone.assumptions) | ({coupling_assumption} if coupling_assumption else set()),
    }


def _apply_true_coupling(
    daily: pd.DataFrame,
    seed: int,
    target_phase: str = "M",
    rate_ratio: float = 1.5,
) -> pd.DataFrame:
    """Add a simple positive-control phase effect after null diary alignment.

    The null seizure diary is left unchanged outside target-phase days. On target
    days, extra Poisson events are added with mean (rate_ratio - 1) times the
    participant's baseline daily seizure rate. This creates an auditable
    sensitivity scenario rather than a mechanistic hormone model.
    """

    out = daily.copy()
    rr = max(1.0, float(rate_ratio))
    if rr <= 1.0 or "phase" not in out:
        return out
    target_mask = out["phase"].eq(target_phase)
    if not bool(target_mask.any()):
        return out
    baseline_rate = float(out["seizure_count"].mean())
    if baseline_rate <= 0:
        return out
    rng = np.random.default_rng(seed)
    extra = rng.poisson((rr - 1.0) * baseline_rate, size=int(target_mask.sum()))
    updated = out.loc[target_mask, "seizure_count"].to_numpy(dtype=np.int64) + extra.astype(np.int64)
    out.loc[target_mask, "seizure_count"] = updated.astype(out["seizure_count"].dtype, copy=False)
    out["seizure_day"] = out["seizure_count"].astype(np.int64) > 0
    return out


def _split_batches(items: list[tuple[Any, ...]], n_batches: int) -> list[list[tuple[Any, ...]]]:
    return [items[i::n_batches] for i in range(n_batches) if items[i::n_batches]]


def classify_window(
    participant_id: str,
    cohort: str,
    daily: pd.DataFrame,
    spec: WindowSpec,
    config: dict[str, Any],
    alpha: float,
    include_regression: bool,
    include_reproducibility: bool = True,
    include_historical: bool = True,
    phase_mode: str | None = None,
) -> dict[str, Any]:
    days_per_month = int(config["days_per_month"])
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(config.get("thresholds", {}))
    window_df = subset_window(daily, spec)
    base = {
        "participant_id": participant_id,
        "cohort": cohort,
        **window_base_fields(window_df, cohort, spec.window_type, spec.window_value, days_per_month),
    }
    base["phase_mode"] = str(phase_mode or config.get("phase_mode", "strict_herzog"))
    if base["phase_mode"] == "modified_short_cycle" and cohort != "population":
        base["phase_mode"] = "strict_herzog"
    base["window_start"] = spec.start_day
    base["window_end"] = spec.end_day
    base["analyzable_flag"] = bool(spec.valid and not window_df.empty and window_df["phase"].notna().any())

    if not spec.valid or window_df.empty:
        row = {
            **base,
            **_empty_adsf(),
            **_empty_labels(spec.indeterminate_reason or "invalid_window"),
        }
        return _ordered_window_row(row)

    adsf = pooled_adsf_and_ratios(window_df, cohort, thresholds)["adsf"]
    if base["phase_mode"] == "strict_herzog" and spec.window_type == "cycle" and str(spec.window_value) == "3":
        exact = classify_exact_herzog2004(window_df, cohort, thresholds)
    elif base["phase_mode"] != "strict_herzog":
        exact = _empty_exact("exact_herzog_only_evaluated_for_strict_herzog_phase_mode")
    else:
        exact = _empty_exact("exact_herzog_only_applies_to_three_cycle_windows")
    a_windowed = classify_a_windowed(window_df, cohort, thresholds)
    definition_b = config.get("definition_b", {})
    b = classify_b_minimum_data(
        window_df,
        cohort,
        spec.window_type,
        spec.window_value,
        days_per_month,
        thresholds,
        min_months=float(definition_b.get("min_months", 4.0)),
        min_cycle_window_cycles=int(definition_b.get("min_cycle_window_cycles", 6)),
        min_seizure_days=int(definition_b.get("min_seizure_days", 4)),
    )
    primary_min_cycles = int(config.get("reproducibility", {}).get("primary_min_complete_cycles", 6))
    sensitivity_min_cycles = int(config.get("reproducibility", {}).get("sensitivity_min_complete_cycles", 12))
    if include_reproducibility and int(base.get("n_complete_cycles") or 0) >= primary_min_cycles:
        c = classify_reproducibility(
            window_df,
            cohort,
            thresholds,
            min_complete_cycles=primary_min_cycles,
        )
    elif include_reproducibility:
        c = _empty_reproducibility("fewer_than_required_complete_cycles")
    else:
        c = _empty_reproducibility("reproducibility_not_evaluated_for_phase_mode")

    if include_reproducibility and int(base.get("n_complete_cycles") or 0) >= sensitivity_min_cycles:
        c12 = classify_reproducibility(
            window_df,
            cohort,
            thresholds,
            min_complete_cycles=sensitivity_min_cycles,
        )
    elif include_reproducibility:
        c12 = _empty_reproducibility("fewer_than_required_complete_cycles")
    else:
        c12 = _empty_reproducibility("reproducibility_not_evaluated_for_phase_mode")
    run_regression = include_regression and _run_regression_for_window(spec, config)
    if run_regression:
        d = classify_regression_nb(
            window_df,
            cohort,
            spec.window_type,
            spec.window_value,
            days_per_month,
            alpha,
            thresholds,
            min_months=float(definition_b.get("min_months", 4.0)),
            min_cycle_window_cycles=int(definition_b.get("min_cycle_window_cycles", 6)),
            min_seizure_days=int(definition_b.get("min_seizure_days", 4)),
        )
        if _run_window_alpha_sensitivity(spec, config):
            window_alpha = participant_alpha_from_full_diary(
                window_df,
                fallback=float(config.get("regression", {}).get("fallback_alpha", 1.0)),
            )
            # For a full-diary window, the sensitivity alpha is computed from
            # exactly the same seizure-count vector as the primary alpha. Reuse
            # the identical fit rather than running statsmodels twice.
            if window_alpha == alpha:
                d_window_alpha_raw = d
            else:
                d_window_alpha_raw = classify_regression_nb(
                    window_df,
                    cohort,
                    spec.window_type,
                    spec.window_value,
                    days_per_month,
                    window_alpha,
                    thresholds,
                    min_months=float(definition_b.get("min_months", 4.0)),
                    min_cycle_window_cycles=int(definition_b.get("min_cycle_window_cycles", 6)),
                    min_seizure_days=int(definition_b.get("min_seizure_days", 4)),
                )
            d_window_alpha = {
                key.replace("label_D_", "label_D_window_alpha_").replace("d_", "d_window_alpha_"): value
                for key, value in d_window_alpha_raw.items()
            }
        else:
            d_window_alpha = {
                "label_D_window_alpha_any": None,
                "label_D_window_alpha_C1_or_C2": None,
                "label_D_window_alpha_C1": None,
                "label_D_window_alpha_C2": None,
                "label_D_window_alpha_C3": None,
                "label_D_window_alpha_pattern_category": None,
                "d_window_alpha_reason": "window_alpha_sensitivity_not_evaluated_for_window",
            }
    else:
        regression_reason = "regression_not_evaluated_for_window" if include_regression else "regression_disabled"
        d = {
            "label_D_any": None,
            "label_D_C1_or_C2": None,
            "label_D_C1": None,
            "label_D_C2": None,
            "label_D_C3": None,
            "label_D_pattern_category": None,
            "d_reason": regression_reason,
        }
        d_window_alpha = {
            "label_D_window_alpha_any": None,
            "label_D_window_alpha_C1_or_C2": None,
            "label_D_window_alpha_C1": None,
            "label_D_window_alpha_C2": None,
            "label_D_window_alpha_C3": None,
            "label_D_window_alpha_pattern_category": None,
            "d_window_alpha_reason": regression_reason,
        }
    if include_historical:
        historical = classify_historical_all(
            window_df,
            cohort,
            h1_threshold=float(config.get("historical", {}).get("h1_threshold", 0.50)),
            h1_sensitivity_threshold=float(config.get("historical", {}).get("h1_sensitivity_threshold", 0.667)),
        )
    else:
        historical = _empty_historical()
    reason = next(
        (
            value
            for value in [
                exact.get("a_exact_reason"),
                a_windowed.get("a_windowed_reason"),
                b.get("b_reason"),
                c.get("c_reason"),
                d.get("d_reason"),
            ]
            if value
        ),
        None,
    )
    row = {
        **base,
        **adsf,
        **exact,
        **a_windowed,
        "label_A_windowed_excluding_C3": _any_excluding_c3(
            a_windowed.get("label_A_windowed_C1"),
            a_windowed.get("label_A_windowed_C2"),
        ),
        **b,
        "label_B_excluding_C3": _any_excluding_c3(
            b.get("label_B_C1"),
            b.get("label_B_C2"),
        ),
        **c,
        "label_C12_any": c12.get("label_C_any"),
        "label_C12_C1_or_C2": c12.get("label_C_C1_or_C2"),
        "label_C12_C1": c12.get("label_C_C1"),
        "label_C12_C2": c12.get("label_C_C2"),
        "label_C12_C3": c12.get("label_C_C3"),
        "label_C12_pattern_category": c12.get("label_C_pattern_category"),
        "c12_reason": c12.get("c_reason"),
        **d,
        **d_window_alpha,
        **historical,
        "indeterminate_reason": reason,
    }
    return _ordered_window_row(row)


def _empty_adsf() -> dict[str, Any]:
    return {
        "adsf_M": np.nan,
        "adsf_O": np.nan,
        "adsf_F": np.nan,
        "adsf_L": np.nan,
        "adsf_FL": np.nan,
        "adsf_OLM": np.nan,
        "rr_C1": np.nan,
        "rr_C2": np.nan,
        "rr_C3": np.nan,
    }


def _empty_exact(reason: str) -> dict[str, Any]:
    return {
        "label_A_exact_any": None,
        "label_A_exact_C1": None,
        "label_A_exact_C2": None,
        "label_A_exact_C3": None,
        "a_exact_reason": reason,
    }


def _empty_labels(reason: str) -> dict[str, Any]:
    labels = {
        "label_A_exact_any": None,
        "label_A_exact_C1": None,
        "label_A_exact_C2": None,
        "label_A_exact_C3": None,
        "label_A_windowed_any": None,
        "label_A_windowed_excluding_C3": None,
        "label_A_windowed_C1_or_C2": None,
        "label_A_windowed_C1": None,
        "label_A_windowed_C2": None,
        "label_A_windowed_C3": None,
        "label_A_windowed_pattern_category": None,
        "label_B_any": None,
        "label_B_excluding_C3": None,
        "label_B_C1_or_C2": None,
        "label_B_C1": None,
        "label_B_C2": None,
        "label_B_C3": None,
        "label_B_pattern_category": None,
        "label_C_any": None,
        "label_C_C1_or_C2": None,
        "label_C_C1": None,
        "label_C_C2": None,
        "label_C_C3": None,
        "label_C_pattern_category": None,
        "label_D_any": None,
        "label_D_C1_or_C2": None,
        "label_D_C1": None,
        "label_D_C2": None,
        "label_D_C3": None,
        "label_D_pattern_category": None,
        "label_D_window_alpha_any": None,
        "label_D_window_alpha_C1_or_C2": None,
        "label_D_window_alpha_C1": None,
        "label_D_window_alpha_C2": None,
        "label_D_window_alpha_C3": None,
        "label_D_window_alpha_pattern_category": None,
        "label_H1_any": None,
        "label_H2_any": None,
        "label_H3_any": None,
        "label_H4_any": None,
        "indeterminate_reason": reason,
    }
    return labels


def _empty_reproducibility(reason: str) -> dict[str, Any]:
    return {
        "label_C_any": None,
        "label_C_C1_or_C2": None,
        "label_C_C1": None,
        "label_C_C2": None,
        "label_C_C3": None,
        "label_C_pattern_category": None,
        "c_reason": reason,
    }


def _empty_historical() -> dict[str, Any]:
    return {
        "label_H1_any": None,
        "label_H1_sensitivity_any": None,
        "h1_threshold": np.nan,
        "h1_sensitivity_threshold": np.nan,
        "label_H2_any": None,
        "label_H3_any": None,
        "label_H3_C1": None,
        "label_H3_C2": None,
        "label_H3_C3": None,
        "label_H4_any": None,
        "label_H4_phase": None,
        "assumption_based_historical": False,
    }


def _any_excluding_c3(c1: Any, c2: Any) -> bool | None:
    labels = [c1, c2]
    if any(label is True for label in labels):
        return True
    if any(label is False for label in labels):
        return False
    return None


def _run_window_alpha_sensitivity(spec: WindowSpec, config: dict[str, Any]) -> bool:
    regression_cfg = config.get("regression", {})
    selected = regression_cfg.get("window_alpha_sensitivity_windows", [{"window_type": "full"}])
    return _window_spec_selected(spec, selected)


def _run_regression_for_window(spec: WindowSpec, config: dict[str, Any]) -> bool:
    regression_cfg = config.get("regression", {})
    selected = regression_cfg.get("evaluated_windows")
    if not selected:
        return True
    return _window_spec_selected(spec, selected)


def _window_spec_selected(spec: WindowSpec, selected: list[dict[str, Any]]) -> bool:
    for item in selected:
        if str(item.get("window_type")) != str(spec.window_type):
            continue
        if "window_value" not in item or str(item.get("window_value")) == str(spec.window_value):
            return True
    return False


def _ordered_window_row(row: dict[str, Any]) -> dict[str, Any]:
    for col in REQUIRED_WINDOW_COLUMNS:
        row.setdefault(col, None)
    ordered = {col: row.pop(col) for col in REQUIRED_WINDOW_COLUMNS}
    ordered.update(row)
    return ordered


def run_study_level_mc(study_pool: pd.DataFrame, config: dict[str, Any], mode: str) -> pd.DataFrame:
    if study_pool.empty:
        return pd.DataFrame()
    mode_cfg = config["analysis_modes"][mode]
    n_studies = int(mode_cfg.get("study_level_n_studies", config["study_level"]["n_studies"]))
    master_seed = int(config["master_seed"])
    raw_n = config["study_level"].get("n_participants_values", config["study_level"].get("n_participants", 30))
    n_per_study_values = [int(raw_n)] if isinstance(raw_n, int) else [int(value) for value in raw_n]
    definitions = list(DEFINITION_COLUMNS.items())
    rows: list[dict[str, Any]] = []
    group_cols = ["cohort", "phase_mode"] if "phase_mode" in study_pool else ["cohort"]
    pool_by_group = {
        keys if isinstance(keys, tuple) else (keys,): g.copy()
        for keys, g in study_pool.groupby(group_cols, sort=False)
    }
    for keys, cohort_pool in pool_by_group.items():
        key_map = dict(zip(group_cols, keys))
        cohort = str(key_map["cohort"])
        phase_mode = str(key_map.get("phase_mode", config.get("phase_mode", "strict_herzog")))
        participant_ids = cohort_pool["participant_id"].drop_duplicates().to_numpy()
        grouped_indices = {
            pid: group.index.to_numpy()
            for pid, group in cohort_pool.groupby("participant_id", sort=False)
        }
        for n_per_study in n_per_study_values:
            if participant_ids.size < n_per_study:
                continue
            rng = np.random.default_rng(stable_seed(master_seed, mode, "study_level_mc", cohort, phase_mode, n_per_study))
            for study_id in range(n_studies):
                sampled = rng.choice(participant_ids, size=n_per_study, replace=False)
                selected_indices = [int(rng.choice(grouped_indices[pid])) for pid in sampled]
                study_rows = cohort_pool.loc[selected_indices]
                for definition, col in definitions:
                    if col not in study_rows:
                        continue
                    labels = study_rows[col].map(lambda value: True if value is True else (False if value is False else pd.NA)).astype("boolean")
                    positives = int((labels == True).sum())  # noqa: E712
                    n_classifiable = int(labels.notna().sum())
                    rows.append(
                        {
                            "cohort": cohort,
                            "phase_mode": phase_mode,
                            "study_id": study_id,
                            "definition": definition,
                            "n_participants": n_per_study,
                            "n_classifiable": n_classifiable,
                            "positives": positives,
                            "apparent_prevalence_all": positives / n_per_study,
                            "apparent_prevalence_classifiable": positives / n_classifiable if n_classifiable else np.nan,
                        }
                    )
    return pd.DataFrame(rows)


def _seizure_frequency_stratum(seizure_days_per_month: float) -> str:
    if pd.isna(seizure_days_per_month):
        return "unknown"
    if seizure_days_per_month < 1.0:
        return "<1 seizure-day/month"
    if seizure_days_per_month < 4.0:
        return "1 to <4 seizure-days/month"
    if seizure_days_per_month < 10.0:
        return "4 to <10 seizure-days/month"
    return ">=10 seizure-days/month"


def _cycle_regularity_stratum(sd_cycle_length: float) -> str:
    if pd.isna(sd_cycle_length):
        return "unknown"
    if sd_cycle_length < 2.0:
        return "SD cycle length <2 days"
    if sd_cycle_length < 4.0:
        return "SD cycle length 2 to <4 days"
    return "SD cycle length >=4 days"


def _write_outputs(
    output_dir: Path,
    participant_summary: pd.DataFrame,
    window_results: pd.DataFrame,
    study_level: pd.DataFrame,
    summary: pd.DataFrame,
    audit_daily: pd.DataFrame,
) -> list[Path]:
    paths = [
        output_dir / "participant_summary.parquet",
        output_dir / "window_results.parquet",
        output_dir / "study_level_3month.parquet",
        output_dir / "study_level_3month_n30.parquet",
        output_dir / "summary_tables.csv",
        output_dir / "audit_daily_sample.parquet",
    ]
    participant_summary = _normalize_output_frame(participant_summary)
    window_results = _normalize_output_frame(window_results)
    study_level = _normalize_output_frame(study_level)
    audit_daily = _normalize_output_frame(audit_daily)
    participant_summary.to_parquet(paths[0], index=False)
    window_results.to_parquet(paths[1], index=False)
    study_level.to_parquet(paths[2], index=False)
    study_level.to_parquet(paths[3], index=False)
    summary.to_csv(paths[4], index=False)
    audit_daily.to_parquet(paths[5], index=False)
    return paths


def _normalize_output_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["window_value", "indeterminate_reason", "label_H4_phase"]:
        if col in out:
            out[col] = out[col].map(lambda value: None if pd.isna(value) else str(value))
    return out
