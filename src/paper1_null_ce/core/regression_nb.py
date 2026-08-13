"""Within-participant negative-binomial regression classifier."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from paper1_null_ce.core.classifiers_windowed import DEFAULT_THRESHOLDS, passes_definition_b_threshold
from paper1_null_ce.core.classifiers_windowed import pattern_category
from paper1_null_ce.core.phase_labeling import count_complete_cycles


def holm_adjust_two(p_m: float, p_o: float) -> tuple[float, float]:
    pvals = np.array([p_m, p_o], dtype=float)
    order = np.argsort(pvals)
    adjusted = np.empty_like(pvals)
    running = 0.0
    m = len(pvals)
    for rank, idx in enumerate(order):
        value = min(1.0, (m - rank) * pvals[idx])
        running = max(running, value)
        adjusted[idx] = running
    return float(adjusted[0]), float(adjusted[1])


def participant_alpha_from_full_diary(daily: pd.DataFrame, fallback: float = 1.0) -> float:
    """Estimate a stable NB alpha from full-diary mean/variance for one participant."""

    y = daily["seizure_count"].to_numpy(dtype=float)
    mean = float(y.mean())
    var = float(y.var(ddof=1)) if len(y) > 1 else 0.0
    if mean <= 0 or var <= mean:
        return fallback
    return max(1e-6, min(50.0, (var - mean) / (mean * mean)))


def classify_regression_nb(
    window_df: pd.DataFrame,
    cohort: str,
    window_type: str,
    window_value: Any,
    days_per_month: float,
    alpha: float = 1.0,
    thresholds: dict[str, float] | None = None,
    min_months: float = 4.0,
    min_cycle_window_cycles: int = 6,
    min_seizure_days: int = 4,
) -> dict[str, Any]:
    """Definition D: one-sided NB tests for menstrual and ovulatory enrichment."""

    thresholds = thresholds or DEFAULT_THRESHOLDS
    ok, reason = passes_definition_b_threshold(
        window_df,
        window_type,
        window_value,
        days_per_month,
        min_months=min_months,
        min_cycle_window_cycles=min_cycle_window_cycles,
        min_seizure_days=min_seizure_days,
    )
    if not ok:
        return _empty(reason)
    data = window_df[window_df["phase"].isin(["M", "O", "F", "L"])].copy()
    if data.empty or data["seizure_count"].sum() <= 0:
        return _empty("no_labeled_seizure_data")
    if not (data["phase"].eq("M").any() and data["phase"].eq("O").any()):
        return _empty("missing_m_or_o_phase")

    data["phase_M"] = data["phase"].eq("M").astype(float)
    data["phase_O"] = data["phase"].eq("O").astype(float)
    x = pd.DataFrame({"const": 1.0, "phase_M": data["phase_M"], "phase_O": data["phase_O"]}, index=data.index)
    if count_complete_cycles(data) >= 4:
        dummies = pd.get_dummies(data["cycle_id"].astype(str), prefix="cycle", drop_first=True, dtype=float)
        x = pd.concat([x, dummies], axis=1)
    y = data["seizure_count"].astype(float)
    fallback = False
    try:
        import statsmodels.api as sm

        model = sm.GLM(y, x, family=sm.families.NegativeBinomial(alpha=alpha))
        fit = model.fit(maxiter=100, disp=0)
    except Exception:
        try:
            import statsmodels.api as sm

            model = sm.GLM(y, x, family=sm.families.Poisson())
            fit = model.fit(maxiter=100, disp=0, cov_type="HC0")
            fallback = True
        except Exception as exc:
            return _empty(f"regression_failed:{type(exc).__name__}")

    if "phase_M" not in fit.params or "phase_O" not in fit.params:
        return _empty("phase_coefficients_not_estimated")
    beta_m = float(fit.params["phase_M"])
    beta_o = float(fit.params["phase_O"])
    se_m = float(fit.bse["phase_M"])
    se_o = float(fit.bse["phase_O"])
    p_m = 1.0 - norm.cdf(beta_m / se_m) if se_m > 0 else (0.0 if beta_m > 0 else 1.0)
    p_o = 1.0 - norm.cdf(beta_o / se_o) if se_o > 0 else (0.0 if beta_o > 0 else 1.0)
    p_adj_m, p_adj_o = holm_adjust_two(p_m, p_o)
    rr_m = math.exp(beta_m)
    rr_o = math.exp(beta_o)
    c1 = bool(rr_m >= thresholds["C1"] and p_adj_m < 0.05)
    c2 = bool(rr_o >= thresholds["C2"] and p_adj_o < 0.05)
    return {
        "label_D_any": bool(c1 or c2),
        "label_D_C1_or_C2": bool(c1 or c2),
        "label_D_C1": c1,
        "label_D_C2": c2,
        "label_D_C3": None,
        "label_D_pattern_category": pattern_category(c1, c2, None),
        "d_reason": "poisson_robust_fallback" if fallback else None,
        "d_beta_M": beta_m,
        "d_beta_O": beta_o,
        "d_rr_M": rr_m,
        "d_rr_O": rr_o,
        "d_p_adj_M": p_adj_m,
        "d_p_adj_O": p_adj_o,
        "d_alpha": alpha,
    }


def classify_regression_nb_c3_exploratory(
    daily: pd.DataFrame,
    cohort: str,
    alpha: float = 1.0,
    threshold: float = 1.62,
    min_complete_ilp_cycles: int = 4,
    min_seizure_days: int = 4,
) -> dict[str, Any]:
    """Exploratory model-concordant C3 calibration check.

    The estimand is the daily seizure-count rate ratio for combined
    ovulatory+luteal+menstrual days versus follicular days, restricted to
    complete cycles designated by the simulator as inadequate luteal phase
    (ILP).  A log-link negative-binomial GLM includes cycle fixed effects.
    Positivity requires both a one-sided Wald p value below 0.05 and a fitted
    rate ratio of at least 1.62.

    This is a standalone exploratory C3 family.  It is not combined with the
    primary C1/C2 tests, so no across-family multiplicity adjustment is made.
    """

    if cohort != "population":
        return _empty_c3("not_applicable_to_cohort")
    required = {
        "seizure_count",
        "seizure_day",
        "cycle_id",
        "cycle_day",
        "cycle_length",
        "phase",
        "ilp_flag",
    }
    missing = sorted(required.difference(daily.columns))
    if missing:
        return _empty_c3("missing_columns:" + ",".join(missing))
    if daily.empty:
        return _empty_c3("empty_diary")

    complete_ids = _complete_cycle_ids(daily)
    if not complete_ids:
        return _empty_c3("no_complete_cycles")
    cycle_ilp = (
        daily[daily["cycle_id"].isin(complete_ids)]
        .groupby("cycle_id", sort=False)["ilp_flag"]
        .max()
    )
    ilp_ids = [cycle_id for cycle_id, value in cycle_ilp.items() if bool(value)]
    if len(ilp_ids) < min_complete_ilp_cycles:
        return _empty_c3("fewer_than_required_complete_ilp_cycles")

    data = daily[
        daily["cycle_id"].isin(ilp_ids)
        & daily["phase"].isin(["M", "O", "F", "L"])
    ].copy()
    if data.empty:
        return _empty_c3("no_labeled_ilp_data")
    if int(data["seizure_day"].sum()) < min_seizure_days:
        return _empty_c3("seizure_days_below_minimum")
    if not data["phase"].eq("F").any():
        return _empty_c3("missing_follicular_phase")
    if not data["phase"].isin(["M", "O", "L"]).any():
        return _empty_c3("missing_nonfollicular_phase")

    data["phase_OLM"] = data["phase"].isin(["M", "O", "L"]).astype(float)
    x = pd.DataFrame({"const": 1.0, "phase_OLM": data["phase_OLM"]}, index=data.index)
    dummies = pd.get_dummies(data["cycle_id"].astype(str), prefix="cycle", drop_first=True, dtype=float)
    if not dummies.empty:
        x = pd.concat([x, dummies], axis=1)
    y = data["seizure_count"].astype(float)

    fallback = False
    try:
        import statsmodels.api as sm

        model = sm.GLM(y, x, family=sm.families.NegativeBinomial(alpha=alpha))
        fit = model.fit(maxiter=100, disp=0)
    except Exception:
        try:
            import statsmodels.api as sm

            model = sm.GLM(y, x, family=sm.families.Poisson())
            fit = model.fit(maxiter=100, disp=0, cov_type="HC0")
            fallback = True
        except Exception as exc:
            return _empty_c3(f"regression_failed:{type(exc).__name__}")

    if "phase_OLM" not in fit.params:
        return _empty_c3("phase_coefficient_not_estimated")
    beta = float(fit.params["phase_OLM"])
    se = float(fit.bse["phase_OLM"])
    p_one_sided = 1.0 - norm.cdf(beta / se) if se > 0 else (0.0 if beta > 0 else 1.0)
    rr = math.exp(beta)
    return {
        "label_D_C3_exploratory": bool(rr >= threshold and p_one_sided < 0.05),
        "d_c3_exploratory_reason": "poisson_robust_fallback" if fallback else None,
        "d_c3_exploratory_beta": beta,
        "d_c3_exploratory_rr": rr,
        "d_c3_exploratory_p_one_sided": p_one_sided,
        "d_c3_exploratory_alpha": alpha,
        "d_c3_exploratory_n_complete_ilp_cycles": len(ilp_ids),
        "d_c3_exploratory_n_labeled_days": int(len(data)),
        "d_c3_exploratory_seizure_days": int(data["seizure_day"].sum()),
    }


def _complete_cycle_count(data: pd.DataFrame) -> int:
    count = 0
    for _, g in data.groupby("cycle_id", sort=False):
        length = int(g["cycle_length"].iloc[0])
        if len(g) == length and int(g["cycle_day"].min()) == 1 and int(g["cycle_day"].max()) == length:
            count += 1
    return count


def _complete_cycle_ids(data: pd.DataFrame) -> list[Any]:
    ids: list[Any] = []
    for cycle_id, g in data.groupby("cycle_id", sort=False):
        length = int(g["cycle_length"].iloc[0])
        if len(g) == length and int(g["cycle_day"].min()) == 1 and int(g["cycle_day"].max()) == length:
            ids.append(cycle_id)
    return ids


def _empty(reason: str) -> dict[str, Any]:
    return {
        "label_D_any": None,
        "label_D_C1_or_C2": None,
        "label_D_C1": None,
        "label_D_C2": None,
        "label_D_C3": None,
        "label_D_pattern_category": None,
        "d_reason": reason,
        "d_beta_M": np.nan,
        "d_beta_O": np.nan,
        "d_rr_M": np.nan,
        "d_rr_O": np.nan,
        "d_p_adj_M": np.nan,
        "d_p_adj_O": np.nan,
        "d_alpha": np.nan,
    }


def _empty_c3(reason: str) -> dict[str, Any]:
    return {
        "label_D_C3_exploratory": None,
        "d_c3_exploratory_reason": reason,
        "d_c3_exploratory_beta": np.nan,
        "d_c3_exploratory_rr": np.nan,
        "d_c3_exploratory_p_one_sided": np.nan,
        "d_c3_exploratory_alpha": np.nan,
        "d_c3_exploratory_n_complete_ilp_cycles": 0,
        "d_c3_exploratory_n_labeled_days": 0,
        "d_c3_exploratory_seizure_days": 0,
    }
