# HORMONE-CYCLE v0.4.0: biological-realism correction and validation

## Decision summary

HORMONE-CYCLE v0.4.0 is a qualified pass for its intended use: generating biologically
plausible menstrual/hormone null histories for the catamenial-epilepsy analysis. The deterministic
10,000-person validation passed all 89 baseline checks, all eight modifier scenarios, and every
new nuanced requirement. The corrected outputs should be described as **latent daily hormone
envelopes**, not literal serial serum measurements.

The update was intentionally limited to defects that could make the null biologically misleading:
an early/inflated follicular E2 ramp hidden by the prior validation overlay, nearly cloned cycle
timing, uniform luteal time-warping, a shifted terminal-P4 reset, an unrepresentative age-52
example, unauditable example selection, and missing dependence between long menopause-transition
intervals and anovulation. It does not attempt to reproduce every endocrine pulse or every
published long-cycle phenotype.

## What changed

### 1. Full daily ordinary-cycle source mapping

- Every Stricker serum median that maps inside a realized ordinary cycle now contributes a control
  point. For the canonical 29-day cycle this is 28 of 30 observations; LH−15 and LH−14 precede
  cycle day 1.
- The previous implementation excluded all E2 observations before LH−1. Against the omitted
  LH−13…−2 values, the old canonical envelope averaged 97.75 versus 68.82 pg/mL (1.42-fold;
  RMSE 31.9 pg/mL), starting its sustained follicular rise roughly 3–4 days too early.
- The construction audit now requires 100% coverage of all in-cycle E2 observations and a
  simulated/source follicular summed-area ratio of 0.90–1.10.

### 2. Luteal timing and terminal progesterone

- Stricker offsets through LH+7 retain daily spacing. Only the LH+7…+14 withdrawal tail is scaled
  to the realized cycle endpoint. This removes the prior near-deterministic coupling between
  luteal duration and P4-peak timing.
- The published LH+14 P4 value remains at the cycle endpoint. The model no longer replaces it one
  day early with the early-follicular baseline.
- Validation now checks both the terminal/peak ratio and the penultimate-to-terminal drop; a small
  next-cycle boundary jump can no longer conceal a reset shifted to the previous day.

### 3. Modest cycle-level waveform heterogeneity

- A separate hash-seeded stream adds −1/0/+1-day local E2 and P4 timing shifts and modest relative
  luteal-E2/P4-plateau variation.
- The stream is deterministic and consumes no production cycle RNG draws. Unit tests verify that
  cycle lengths, phase timing, ovulation, bleeding, and the compact paper-analysis path remain RNG
  equivalent.
- These perturbations are anti-template guards, not claims that the exact simulated SDs were
  estimated from a clinical cohort.

### 4. Menopause-transition joint dependence

- For profiles with an age-50+ fitted long-episode process, Bayes allocation conditions that
  episode on ovulatory status to target the published 64.7% anovulatory fraction among intervals
  of at least 36 days.
- The fitted marginal long-episode probability is preserved in an unforced population. Long
  ovulatory intervals remain possible rather than being prohibited.
- The age-52 display now uses an explicit perimenopause modifier and includes both ovulatory and
  anovulatory long cycles.

### 5. Honest, reproducible example displays

- Estradiol and progesterone use separate panels and common hormone-specific scales across rows.
- Each example shows exactly seven complete cycles; right-censored eighth cycles are no longer
  shown without a truncation mark.
- Selection is executable: ascending integer seeds are searched and the first case meeting each
  declared criterion is retained. The resulting seed, criterion, stage, cycle lengths, and
  ovulatory states are stored in `healthy_cycle_example_selection_v14.json`.

## Why the additional requirements are literature based

| Requirement | Evidence role | Data-driven reason |
|---|---|---|
| Complete in-cycle Stricker E2 mapping and LH−13…−2 area ratio | Direct construction fidelity | Stricker reports daily LH-aligned serum medians. Omitting the follicular observations both from construction and the overlay hid the largest source mismatch. |
| Nonzero E2/P4 timing and relative-shape dispersion | Literature-informed, investigator-bounded plausibility guard | Roos et al. observed heterogeneous hormone signal timing relative to ultrasound-confirmed ovulation. The literature supports heterogeneity; it does not directly estimate the chosen simulator bounds. |
| Two-sided terminal-P4 ratio plus final within-cycle drop | Direct source-shape and boundary-integrity check | Stricker LH+14 remains above the early-follicular baseline. A boundary-jump-only test failed to detect the old one-day-early reset. |
| Anovulation enriched among perimenopausal intervals ≥36 days | Published conditional-rate context plus investigator-bounded directional check | Van Voorhis et al. reported 64.7% anovulation in ≥36-day versus 8.1% in 21–35-day intervals. The simulator must reproduce a positive material contrast, while O'Connor et al. supports retaining long ovulatory cycles and treating reproductive stage as important context. |

Primary sources: [Stricker et al. 2006](https://pubmed.ncbi.nlm.nih.gov/16776638/),
[Roos et al. 2015](https://pubmed.ncbi.nlm.nih.gov/26018113/),
[Van Voorhis et al. 2008](https://pubmed.ncbi.nlm.nih.gov/18591314/), and
[O'Connor et al. 2009](https://pubmed.ncbi.nlm.nih.gov/19568209/).

## Definitive validation outcome

Configuration: 10,000 adults, 365 days, seed 7, random diary start, age-balanced baseline,
160 retained full diaries (20 per age band), and all modifier scenarios enabled after the primary
gate passed.

| Gate | Result |
|---|---:|
| Calibration metrics | 75/75 passed |
| Waveform metrics (included above) | 30/30 passed |
| Held-out Cunningham cycle cross-checks | 14/14 passed |
| All baseline metrics | 89/89 passed |
| Modifier scenarios | 8/8 passed |
| Citation registry audit | 24/24 PubMed records passed |
| Unit/regression tests | 33/33 passed |
| Executed notebook | 11/11 code cells; no cell errors |

### New waveform results

The timing and dependence diagnostics used 1,713 complete ovulatory cycles.

| Metric | Observed | Acceptance range |
|---|---:|---:|
| In-cycle Stricker E2 coverage | 1.000 | 1.000 |
| LH−13…−2 follicular E2 area ratio | 1.000 | 0.90–1.10 |
| Median E2-peak offset | −2.0 d | −3 to −1 d |
| E2-peak offset SD | 0.707 d | 0.45–2.50 d |
| Luteal/follicular E2-peak-ratio SD | 0.0608 | 0.03–0.30 |
| Median P4-peak offset | +6.0 d | +3 to +9 d |
| P4-peak offset SD | 0.699 d | 0.45–2.50 d |
| Correlation: luteal length vs P4-peak offset | 0.051 | −0.75–0.75 |
| Terminal/peak P4 ratio | 0.0997 | 0.05–0.18 |
| Final within-cycle P4 drop | 0.50 ng/mL | 0–1.0 ng/mL |

As a non-gating robustness check, the nuanced metrics were repeated in three alternate
2,000-person cohorts (seeds 3, 11, and 29). All passed. Across those runs, E2-peak timing SD was
0.701–0.703 days, P4-peak timing SD was 0.686–0.703 days, luteal-length/P4-peak correlation was
0.044–0.079, terminal/peak P4 was 0.100–0.1001, and the final P4 drop was 0.48–0.51 ng/mL.

### External hormone context

All independent Anckaert subphase bounds passed. The comparison is approximate, not a fit: for
example, simulated E2 at the simulator's ovulation marker was 102 pg/mL versus the Anckaert
LH-peak-labelled phase median of 223 pg/mL, while late-luteal P4 was 2.79 versus 5.72 ng/mL.
Those values remain within the prespecified broad assay/cohort windows. The true-ovulation timing
in Roos is the more appropriate context for the simulator's ovulation marker because Anckaert's
phase label is tied to LH.

### Perimenopause result

The explicit perimenopause scenario generated 2,067 intervals of at least 36 days; 61.6% were
anovulatory, close to the 64.7% published conditional rate and inside the prespecified 45–80%
range. However, 50.0% of 12,518 ordinary 21–35-day intervals were also anovulatory, versus 8.1% in
Van Voorhis. The simulated long-versus-ordinary contrast was therefore only 11.6 percentage points
(odds ratio 1.60), versus a much stronger source association. This is now displayed rather than
hidden and is classified as directional joint calibration, not magnitude matching. Overall
ovulation was 48.3%, and long ovulatory cycles remained present.

### Compatibility with the catamenial-epilepsy null analysis

An isolated 100-participant, six-month smoke analysis used the same master seed and configuration
as the retained v0.3.0 waveform benchmark, with a new output directory.

- All 100 participant-summary rows and values were identical.
- All 16,267 aggregate summary rows and values were identical.
- Hormone values changed, as intended.
- Four of 2,600 window rows changed only in C3 applicability/reason fields because the corrected
  P4 envelope can change inadequate-luteal-phase eligibility at a threshold boundary.

This supports the intended separation: seizure generation and cycle/event RNG structure are
unchanged, while P4-dependent C3 eligibility is allowed to respond to the biologically corrected
waveform. A future definitive paper release should regenerate the full analysis rather than reuse
v0.3.0 C3-dependent outputs.

## Critical interpretation

### What is now convincing

- The ordering and approximate magnitudes are plausible: follicular E2 rise and preovulatory peak,
  periovulatory fall, secondary luteal E2 elevation, delayed broad P4 summit, and withdrawal.
- Ordinary-cycle construction is transparent and now faithful to every source value that lies
  inside the canonical cycle.
- Cycle-to-cycle timing is no longer exactly cloned, and luteal duration no longer mechanically
  determines P4-peak day.
- The explicit perimenopause scenario now has a credible mixture of ordinary, long ovulatory, and
  long anovulatory intervals rather than an implausibly selected all-ovulatory age-52 trace.
- Aggregate cycle distributions and all existing covariate-direction checks remain intact.

### Material limitations that remain acceptable for the null purpose

1. **Latent envelope, not measured serum.** Endpoint-bridged smooth daily noise omits intraday
   pulsatility and much of assay/individual variability. Filicori et al. documents pronounced
   pulsatile luteal P4 secretion. Literal individual serum traces would require an observation
   model layered over this latent process. In a non-gating exploratory audit of 7,845 within-person
   ordinary-cycle pairs, separately phase-aligned and z-scored shape correlations remained high:
   median r=0.881 for E2 and r=0.981 for P4. This is substantially less cloned than before for E2,
   but P4 remains deliberately template-dominant.
2. **Waveform calibration is small and partly circular.** Stricker includes 20 volunteers and
   directly constructs the ordinary waveform. Construction-fidelity checks must not be called
   independent validation.
3. **Independent hormone bounds are broad.** Anckaert supports scale and ordering, not exact
   person-level longitudinal realism; some observed values sit toward the lower side of those
   windows.
4. **Long-follicular morphology is qualitative.** Only two of Harlow's five reported urinary-E2
   patterns are implemented. The 25% failed-wave share and its simulated serum amplitude are
   sensitivity choices, not prevalence estimates.
5. **Perimenopause dependence is only directionally calibrated.** The model closely reproduces
   `P(anovulatory | ≥36 days)` but has a much higher ordinary-cycle anovulation rate than Van
   Voorhis, so the long-cycle association is far weaker. This may reflect the deliberately broad
   explicit-stage scenario and differing cohort definitions, but the 64.7% bar alone is not an
   adequate description of joint fit.
6. **Modifier evidence is uneven.** Several comorbidity/contraceptive gates test direction or a
   broad clinical range rather than a fitted daily joint distribution. The explicit factor/stage
   flag remains important; chronological age alone does not assert menopause-transition stage.
7. **Older-age cycle dispersion remains imperfect.** The simulator intentionally remains above
   the held-out Flo personal-SD estimate at ages 51–55 while matching the AWHS calibration more
   closely. This source conflict is visible in the summary figure.
8. **Boundary gates summarize the typical cycle.** The median final P4 drop was 0.50 ng/mL and the
   median cross-cycle jump was 0.81 ng/mL, but their 95th percentiles were 3.06 and 1.31 ng/mL.
   Those tails arise mainly when a short luteal phase compresses withdrawal and are compatible
   with rapid luteolysis/daily hormone variability; the model should not be described as enforcing
   a uniformly gentle boundary in every cycle.

[Filicori et al. 1984](https://pubmed.ncbi.nlm.nih.gov/6427277/) supports the pulsatility limitation;
[Anckaert et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8042396/) is the independent serum
subphase comparator; [Harlow et al. 2000](https://pubmed.ncbi.nlm.nih.gov/10611180/) supports the
long-follicular pattern classes.

## Reproducibility artifacts

- `examples/reports/healthy_cycle_validation_v14.json`: complete machine-readable validation
- `show_validation.ipynb`: executed validation notebook
- `examples/reports/hormone_cycle_validation_v14.png`: calibration and held-out cycle summary
- `examples/reports/hormone_waveform_validation_v14.png` and `.svg`: construction overlay
- `examples/reports/hormone_nuanced_validation_v14.png` and `.svg`: new nuanced checks
- `examples/reports/healthy_cycle_example_traces_v14.png` and `.svg`: complete-cycle examples with
  E2 and P4 overlaid on one time panel per case and individual bleeding days shown as baseline rugs
- `examples/reports/healthy_cycle_example_selection_v14.json`: executable selection manifest
- `examples/reports/hormone_kinetics_validation_v14.png`: single-cycle boundary audit
- `examples/reports/hormone_citation_audit_v14.json`: PubMed registry audit
- `outputs_smoke_v14_waveform/`: isolated paper-pipeline smoke output

## Independent post-change critique and adjudication

The dedicated reviewer made no edits and classified findings relative to the null-distribution
purpose.

### A — Mission-critical before use

**None.** The reviewer found the previously hidden follicular-E2 mismatch resolved, timing no
longer exact, whole-luteal time warping removed, the terminal P4 source value retained, the age-52
example correctly staged, display selection auditable, and long cycles directionally enriched for
anovulation. E2 does not enter the paper's catamenial classification; P4 affects only ILP/C3
eligibility.

### B — Material but acceptable with disclosure or downstream sensitivity

- Short luteal phases compress withdrawal: 31.4% of retained cycles had a final P4 drop >1 ng/mL,
  16.7% exceeded 2 ng/mL, and the maximum was 6.3 ng/mL. This is implementation-driven but does not
  affect the midluteal P4 maximum used by the paper adapter.
- Perimenopause posterior agreement overstates joint-association agreement. The corrected figure
  now shows both ordinary and long conditional rates; the model remains a directional rather than
  magnitude calibration.
- Timing heterogeneity remains a discrete −1/0/+1-day perturbation around one median template. The
  SD gates prevent exact cloning but are not clinical estimates.
- Anckaert phase values pass broad bounds but are not close at every phase; assay and event
  definitions differ.
- Condition-specific daily endocrine distributions and combined-factor stacking are much less
  directly validated than cycle timing, ovulation direction, bleeding, and amenorrhea.
- The age-51–55 held-out Flo personal-SD result remains near its upper margin.
- Long-follicular E2 classes and mixture weights remain coarse sensitivity choices.
- The full 100,000-participant paper analysis must be regenerated under v0.4.0 because corrected
  P4 can change C3 threshold eligibility even though the smoke summary was unchanged.

### C — Optional polish

- Add uncertainty intervals to the cycle-summary figure.
- Call the single-cycle kinetics panel a “smoke check” rather than clinical validation.
- Keep construction fidelity, investigator guards, fitted targets, and held-out comparisons
  separate whenever reporting the composite pass flag.
- Consider future percentile- or luteal-length-stratified P4 boundary metrics and a richer
  observation model for individual serum-like traces.

### Final loop decision

**No model loop.** The remaining issues do not make the null generator biologically indefensible
and do not justify additional fitting before use. The only immediate post-critique update was to
make the weaker simulated perimenopause association explicit in the validation summary and add a
positive long-versus-ordinary anovulation contrast check. Before publication, rerun the definitive
paper analysis under v0.4.0 and report P4-threshold/ILP/C3 sensitivity. A further simulator loop is
warranted only if that full rerun shows a consequential downstream shift.
