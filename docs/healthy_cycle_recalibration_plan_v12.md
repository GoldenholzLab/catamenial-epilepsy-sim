# Healthy-cycle recalibration plan (v0.2.0)

## Objective

Correct the healthy-cycle duration model so its estimands and aggregate output match published
data, then propagate any material change through the paper only if a prespecified validation gate
passes. The intended use is population-level simulation, not individual diagnosis or forecasting.

## Source separation

- **Fit targets:** Li et al. 2023 (AWHS) age-band cycle means, pooled within-person SD,
  participant-level irregularity, and short/long tails; Bull et al. 2019 phase and bleeding
  summaries; Stricker et al. 2006 hormone subphase anchors.
- **Held-out cross-check:** Cunningham et al. 2024 age-band 12-month participant means and mean
  personal SDs. These values must not alter fitted parameters after the gate is specified.
- **Face-validity examples:** low-variability, high-variability, and later-life long-cycle traces.
  These illustrate behavior but do not determine the pass decision.

## Execution plan

1. Audit the old implementation and reconstruct the original example-figure provenance.
2. Align every validation statistic with the source-study estimand and correct source-table values.
3. Replace the symmetric cycle sampler with a right-skewed model; use a deterministic surrogate to
   initialize age-specific participant heterogeneity, then refine and accept parameters against the
   complete simulator's joint AWHS outcomes.
4. Separate profile, cycle, and observation-start random streams and add regression tests.
5. Freeze practical equivalence margins, run the 10,000-participant adult validation (ages
   18--54.9, matching AWHS eligibility), and compare with the held-out Flo summaries.
6. Inspect representative traces for hormone ordering, withdrawal, bleeding timing, and plausible
   manifestations of participant heterogeneity.
7. Proceed to the full 100,000-participant paper rerun only after all fitted and held-out gates pass.
8. Rebuild affected notebooks, tables, figures, manuscript text, appendix methods/validation text,
   native Word equations, Zotero fields, and reproducibility manifests.
9. Audit the complete simulator citation registry against PubMed, record PMID/DOI/title/evidence
   roles, and correct provenance before freezing the final source hash.
10. Perform automated integrity checks and final visual verification in Microsoft Word.

## Gate and interpretation

The numeric margins and results are recorded in
[`healthy_cycle_validation_v12.md`](healthy_cycle_validation_v12.md). Passing establishes adequate
aggregate similarity for the paper's null simulations. It does not establish person-level clinical
validity. The decision is explicitly qualified at ages 46–55 because AWHS and Flo report different
older-age variability magnitudes.
