# Exploratory C3 negative-binomial calibration specification

## Status and purpose

This specification was frozen before inspecting the exploratory C3 regression
results. The analysis is a model-concordant statistical calibration check. It
is not an alternative clinical diagnostic method, an independent validation of
CHOCOLATES or HORMONE-CYCLE, or evidence of clinical superiority.

## Saved-data population and estimand

- Data source: the deterministic 1% daily audit sample retained by the completed
  100,000-participant null simulation.
- Cohort: heterogeneous menstruating-age participants only.
- Window: the complete 36-month diary in strict Herzog phase mode.
- Applicability: complete cycles carrying the simulator-generated
  inadequate-luteal-phase (ILP) indicator.
- Contrast: daily seizure-count rate on combined ovulatory, luteal, and
  menstrual days versus follicular days. This matches the C3
  ADSF(O+L+M)/ADSF(F) numerator and comparator.

The model is restricted to ILP cycles rather than using an interaction because
the implemented C3 ratio is itself defined only within ILP-designated cycles.
Cycle fixed effects control for cycle-to-cycle baseline seizure-count
differences without changing that estimand.

## Model and decision rule

- Generalized linear model with daily seizure count, log link, and a
  negative-binomial variance function.
- Participant-full-diary method-of-moments dispersion, with the same stabilized
  bounds used for the existing C1/C2 calibration analysis.
- Predictors: an indicator for O+L+M days and fixed effects for complete ILP
  cycles.
- Robust Poisson fallback only if the negative-binomial fit fails; fallback is
  reported as a reason code.
- One-sided Wald test for enrichment on O+L+M days.
- Positive only when the one-sided p value is below 0.05 and the fitted rate
  ratio is at least 1.62.
- Minimum data: at least four complete ILP cycles and four seizure days in the
  labeled ILP-cycle data.

The C3 test is a separate exploratory family and is not pooled into the primary
C1/C2 endpoint. No across-family multiplicity adjustment is therefore applied.

## Indeterminate and non-applicable behavior

The analysis returns an explicit reason when the cohort is not applicable, the
required columns or phases are absent, fewer than four complete ILP cycles are
available, fewer than four seizure days occur, or both negative-binomial and
robust-Poisson fits fail. Classifiable and all-attempted rates are reported
separately. The saved audit-sample applicability denominator is reconciled with
the matching full-window C3 ratio rows before interpretation.

## Scope limitation

Full daily trajectories were not retained for the other 99% of the completed
simulation. Reproducing this analysis in all 50,000 heterogeneous participants
would require a new deterministic rerun and is outside this revision pass.
