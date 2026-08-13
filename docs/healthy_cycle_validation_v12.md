# Healthy-cycle simulator recalibration and validation (v0.2.0)

## Decision

**Qualified pass for the paper's intended population-level null simulations.** All prespecified
calibration checks passed in the deterministic 10,000-participant adult, 365-day cohort, as did the
held-out Cunningham et al. cross-check under the declared practical margins. This is not a claim
of individual clinical validity. The pass is strongest for ages 18–45 and qualified at ages 46–55,
where the two large source cohorts report materially different variability levels.

## Why recalibration was necessary

The former code treated Li et al.'s irregularity percentage as the probability that an individual
adjacent pair differed by at least seven days. Li et al. instead classified a *participant* using
that person's **mean difference across adjacent cycles** and a seven-day threshold. The table
footnote omits the word “absolute,” but the article's methods define adjacent-cycle differences as
absolute values; v0.2.0 therefore uses the mean absolute adjacent difference. A signed mean would
mostly telescope to the first-to-last change and would not behave like the reported variability
measure. The former Gaussian inversion matched a different statistic and made its validation
circular. The age-band values in the old target table also did not match Li et al. Tables 4–5.

## Revised model and estimands

- Age-band within-person SD and participant irregularity are direct values from Li et al. Tables
  4–5. Short-cycle (<24 d) and long-cycle (>38 d) proportions are from Supplementary Table 2.
- Absolute age-band cycle means are transparently derived from Li et al.'s adjusted differences
  from ages 35–39, anchored so the published age-band cycle-count-weighted mean is 28.7 days.
- Cycle lengths use a bounded shifted-lognormal distribution rather than a symmetric Gaussian.
- A low/high variability-component mixture supplies the heterogeneity needed to match both pooled
  within-person SD and participant-level irregularity. A deterministic shifted-lognormal surrogate
  supplied starting values; production values were refined and accepted against the complete
  10,000-participant simulator, which includes between-person means, rounding/truncation, random
  diary boundaries, and variable realized follow-up.
- For ages 50–55, a fitted 10.9% per-cycle long-episode process adds 25.5 days. This reproduces the
  coexistence of ordinary cycles and intermittent long cycles, but is a phenomenological calibration
  term rather than a proposed biological mechanism.
- Profile, cycle, and diary-start random streams are domain-separated.
- Bull et al.'s bleeding mean/SD (4.0/1.5 d) and luteal SD (2.4 d) replace the former unsupported
  bleeding mean of 4.7 d and narrower latent luteal dispersion.

The AWHS metrics use equal participant weighting and up to the first 11 cycles per participant,
matching the source cohort's median follow-up. Within-person SD is pooled after subtracting each
participant's mean.

## Prespecified acceptance margins

| Outcome | Margin |
|---|---:|
| Age-band mean cycle length | ±0.55 d |
| Within-person SD, ages <50 | ±0.35 d |
| Within-person SD, ages ≥50 | ±1.00 d |
| Participant irregularity | ±3.5 percentage points |
| Short/long cycle tails, ages <50 | ±3.0 percentage points |
| Short/long cycle tails, ages ≥50 | ±5.0 percentage points |
| Held-out Flo mean cycle length | ±1.5 d (±2.5 d at 51–55) |
| Held-out Flo mean personal SD | ±1.25 d (±3.5 d at 51–55) |

## Results

In the 10,000-participant adult validation cohort (ages 18--54.9, matching AWHS eligibility):

- The largest absolute age-band mean-cycle error was 0.151 d.
- The largest within-person SD error was 0.255 d below age 50 and 0.035 d at age 50+.
- The largest participant-irregularity error was 2.06 percentage points.
- The largest short/long-tail error was 1.96 percentage points.
- Simulated follicular and luteal means were 16.170 and 12.575 d versus Bull targets of 16.9 and
  12.4 d. Bleeding mean/SD were 4.015/1.503 d versus 4.0/1.5 d. Luteal SD was 2.040 d versus 2.4 d,
  inside the prespecified 2.0–2.8 d interval but near its lower edge.
- Against the held-out Flo cohort, ages 18–45 differed by at most 0.670 d in mean cycle length and
  0.719 d in mean personal SD. At ages 51–55, the simulator produced a mean cycle length of 30.00 d
  and mean personal SD of 9.777 d versus Flo values of 28.00 and 6.52 d.

The older-age discrepancy is scientifically informative: AWHS reports a residual SD of 11.19 d at
age 50+, whereas Flo reports an average 12-month personal SD of 6.52 d at ages 51–55. The simulator
lies between those estimates and was not refitted to erase the held-out difference.

All 19 secondary checks across eight clinical-modifier scenarios also passed after comparison with
seed- and age-matched unmodified cohorts. These are direction/range software stress tests, not
external clinical validation. Exact margins are investigator-specified regression guards. The
relevant age ranges are 18–44.9 years for PCOS, contraception, IUD, and dysmenorrhea; 45–54.9 years
for perimenopause; and 13–17.9 years for peri-menarche.

## Critical visual assessment

The age-31 low-variability trace shows repeated 29–31-day cycles, follicular estradiol peaks before
ovulation, luteal progesterone peaks afterward, and steroid withdrawal before bleeding. The
high-variability age-31 trace changes primarily through follicular/cycle timing while retaining the
ordered hormone morphology. The age-52 trace combines ordinary 26–28-day cycles with one 53-day
episode, matching the later-life right tail better than the former symmetric Gaussian.

Remaining differences and limitations are important:

1. The low/high variability mixture and older-age episode are statistical devices, not latent
   diagnoses or mechanistic ovarian-aging states.
2. Successive cycle lengths are conditionally independent. The model does not yet represent gradual
   trends, stress episodes, seasonal effects, or serial correlation.
3. Ethnicity, BMI, parity, smoking, and socioeconomic covariates adjusted in AWHS are not sampled as
   baseline individual traits, so the simulator reproduces marginal age patterns rather than all
   joint demographic distributions.
4. Flo and AWHS use different cohort filters and variance estimators. The 51–55 result should not be
   presented as uniquely resolved.
5. Hormone curves reproduce subphase medians and morphology constraints; they are not fitted to
   dense longitudinal hormone measurements from a large independent cohort.
6. The illustrative traces were selected using declared display criteria. Population metrics—not
   the examples—determine the pass decision.
7. A registry-wide provenance audit verified all 17 scientific-source entries against PubMed title,
   PMID, and DOI metadata. Five formerly recorded PMIDs pointed to unrelated articles, and one valid
   PMID had mismatched citation text; those identifiers and records were corrected before the final
   validation and paper rerun. Evidence roles now distinguish fitted targets, a held-out aggregate
   cross-check, waveform/context sources, and direction/range modifier evidence.

## Primary sources

- Li H, et al. *Menstrual cycle length variation by demographic characteristics from the Apple
  Women's Health Study.* npj Digital Medicine. 2023;6:100.
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC10226714/>
- Cunningham AC, et al. *Chronicling menstrual cycle patterns across the reproductive lifespan with
  real-world data.* Scientific Reports. 2024;14:10172.
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC11068910/>
- Bull JR, et al. *Real-world menstrual cycle characteristics of more than 600,000 menstrual cycles.*
  npj Digital Medicine. 2019;2:83. <https://doi.org/10.1038/s41746-019-0152-7>
- Stricker R, et al. *Establishment of detailed reference values for luteinizing hormone, follicle
  stimulating hormone, estradiol, and progesterone during different phases of the menstrual cycle
  on the Abbott ARCHITECT analyzer.* Clinical Chemistry and Laboratory Medicine. 2006;44:883–887.
  <https://pubmed.ncbi.nlm.nih.gov/16776638/>
