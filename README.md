# catamenial-epilepsy-sim

## Paper 1 null CE analysis

This repository now includes a reproducible Paper 1 analysis package for the null-simulation study of apparent catamenial epilepsy (CE) false positives. The analysis combines independent seizure diaries from CHOCOLATES with independent menstrual/hormone diaries from `hormone_cycler`, aligns them directly by calendar day, labels Herzog phases, and evaluates exact, windowed, reproducibility, regression, and assumption-based historical CE definitions. HORMONE-CYCLE diaries begin at a uniformly selected day within the first generated cycle by default.

Paper 1 scope only:

- no wavelets
- no HMMs
- no true seizure-hormone coupling simulations

Install the analysis dependencies:

```bash
python3.11 -m pip install -e .
```

Run the focused tests:

```bash
python3.11 -m pytest tests/test_phase_labeling.py tests/test_exact_herzog2004.py tests/test_windowed_rules.py tests/test_edge_cases.py
```

Run the end-to-end smoke test (`N=100`, six-month diaries):

```bash
python3.11 run_paper1_null_ce.py --config config.yaml --smoke-test
```

Run the full randomized-start analysis (`N=100,000`, 36-month diaries):

```bash
python3.11 run_paper1_null_ce.py --config config_random_start_full.yaml --full
```

While a run is active, progress and ETA are printed after each participant chunk and also written to `outputs/progress.json`. From another terminal, check the latest ETA with:

```bash
python3.11 scripts/check_paper1_progress.py --progress outputs/progress.json
```

Primary outputs are written to `outputs/`:

- `participant_summary.parquet`
- `window_results.parquet`
- `study_level_3month_n30.parquet`
- `summary_tables.csv`
- `fig1_false_positive_by_window.png`
- `fig2_study_prevalence_distribution_3month_n30.png`
- `fig3_indeterminate_vs_fpr_frontier.png`
- `fig4_historical_vs_core_definitions.png`
- `fig5_null_cycle_day_profile.png`
- `audit_daily_sample.parquet`
- `manifest.json`

The full daily table is processed participant-by-participant and is not retained. Daily audit rows are saved only for the configured 1% participant sample.

Implementation assumptions recorded in `outputs/manifest.json` include simulator API substitutions that are not directly exposed as public knobs. In particular, the healthy cohort is forced ovulatory through `hormone_cycler`'s profile/render helpers, and population medical-factor prevalence is sampled from `config.yaml` because the simulator exposes condition modifiers but not a public natural-prevalence sampler. Exact Herzog 2004 labels are emitted only for sampled 3-complete-cycle windows; strict and modified short-cycle sensitivity outputs are separated by the `phase_mode` column.

## Hormone-cycle simulator

`hormone_cycler` is a pure-Python simulator for menstrual-cycle diaries. Given a patient age, diary length, and medical modifiers, it generates daily values for:

- estradiol (`estradiol_pg_ml`)
- progesterone (`progesterone_ng_ml`)
- ovulation (`0/1`)
- uterine bleeding (`0/1`)

By default, diary day 1 is selected uniformly from the days of the first generated cycle. The output then proceeds forward continuously through subsequent cycles. Use `--start-mode cycle_day_1` to make cycle day 1 the first output day.

The repo also includes:

- `vis_cycles`: an SVG visualizer for individual diaries
- population simulation utilities for 10,000-woman cohorts
- a validation harness that compares simulated outputs with peer-reviewed literature targets

## Scientific basis

The model is hierarchical rather than a hand-drawn waveform:

1. Age-specific cycle means, within-person SDs, participant-level irregularity, and short/long-cycle tails come from the Apple Women's Health Study analysis in [Li et al. 2023](https://pubmed.ncbi.nlm.nih.gov/37248288/). Version 0.2.0 uses a participant-level mean adjacent-cycle difference of at least seven days and operationalizes “difference” as absolute, consistent with the article's methods definition of adjacent-cycle differences.
2. Follicular and luteal phase timing targets come from the 600,000-cycle Natural Cycles analysis in [Bull et al. 2019](https://pubmed.ncbi.nlm.nih.gov/31482137/).
3. Daily estradiol and progesterone curves use shape-preserving cubic interpolation through serum sub-phase medians reported in [Stricker et al. 2006](https://pubmed.ncbi.nlm.nih.gov/16776638/). Ovulatory curves reserve the final four cycle days for gradual steroid withdrawal before the next bleeding onset, and preovulatory estradiol maxima span multiple daily samples.
4. Bleeding-duration targets use the Natural Cycles analysis and normal uterine-bleeding terminology/range context from [Fraser et al. 2011](https://pubmed.ncbi.nlm.nih.gov/22065325/).
5. Twelve-month participant means and personal SDs from [Cunningham et al. 2024](https://pubmed.ncbi.nlm.nih.gov/38702411/) are held out from fitting and used as an external cross-check.
6. Clinical-factor modifiers are constrained by peer-reviewed subgroup literature:
   - PCOS: [Mortimer et al. 2026](https://pubmed.ncbi.nlm.nih.gov/41297783/), [Doi et al. 2005](https://pubmed.ncbi.nlm.nih.gov/15932911/), and [Jarrett et al. 2020](https://pubmed.ncbi.nlm.nih.gov/32785651/)
   - Peri-menarche: [WHO Task Force 1986](https://pubmed.ncbi.nlm.nih.gov/3721946/), [Venturoli et al. 1986](https://pubmed.ncbi.nlm.nih.gov/3491030/), with [Zhang et al. 2008](https://pubmed.ncbi.nlm.nih.gov/18252789/) retained as a counterpoint
   - Perimenopause: [Santoro and Randolph 2011](https://pubmed.ncbi.nlm.nih.gov/21961713/)
   - Combined oral contraceptives: [Edelman et al. 2014](https://pubmed.ncbi.nlm.nih.gov/25072731/)
   - Levonorgestrel IUD: [Xiao et al. 1995](https://pubmed.ncbi.nlm.nih.gov/7554977/)
   - Copper IUD / non-hormonal IUD effects: [Faundes et al. 1980](https://pubmed.ncbi.nlm.nih.gov/7439408/) and [Malmqvist et al. 1974](https://pubmed.ncbi.nlm.nih.gov/4448089/)
   - Dysmenorrhea: [Dawood 2006](https://pubmed.ncbi.nlm.nih.gov/16880317/)

Important modeling note:

- The combined oral-contraceptive modes simulate suppression of endogenous ovarian estradiol and progesterone. They do not separately model synthetic ethinyl estradiol or progestin assay concentrations.
- "Bare metal IUD" is implemented as a copper / non-hormonal IUD phenotype.
- For several factor subgroups, the literature provides effect direction or broad clinical ranges rather than directly estimable daily-hormone distributions. Those checks are explicitly labeled direction/range checks; their numerical margins are investigator-specified regression guards, not estimates copied from the cited papers. The healthy adult calibration and held-out validation are reported separately.

## Layout

```text
src/hormone_cycler/model.py          Core patient and cycle simulator
src/hormone_cycler/hormone_constants.py Centralized literature-derived constants
src/hormone_cycler/population.py     Cohort generation
src/hormone_cycler/validation.py     Literature comparisons and subgroup checks
src/hormone_cycler/visualization.py  SVG rendering for single diaries
hormone_cycler                       Local CLI wrapper
vis_cycles                           Local CLI wrapper
show_validation.ipynb                Validation notebook
```

## Usage

Single-patient simulation to JSON and CSV:

```bash
python3 hormone_cycler simulate \
  --days 180 \
  --age 29 \
  --pcos \
  --json-output examples/reports/patient_pcos.json \
  --csv-output examples/reports/patient_pcos.csv
```

Render an SVG from a saved diary:

```bash
python3 vis_cycles \
  --input examples/reports/patient_pcos.json \
  --output examples/reports/patient_pcos.svg \
  --title "PCOS Example"
```

Simulate a population:

```bash
python3 hormone_cycler population \
  --patients 10000 \
  --days 365 \
  --json-output examples/reports/population.json
```

Run the literature validation suite:

```bash
python3 hormone_cycler validate \
  --patients 10000 \
  --days 365 \
  --json-output examples/reports/healthy_cycle_validation_v12.json
```

Run the deterministic low/high variability surrogate audit without changing source files:

```bash
python3 scripts/calibrate_healthy_cycle_variability.py \
  --output examples/reports/healthy_cycle_calibration_fit_v12.json
```

The surrogate supplies transparent initialization and sensitivity results; it deliberately omits
some full-simulator features. Production constants were refined and are evaluated by the complete
validation run above, including the held-out Cunningham cross-check.

Verify every simulator citation title, PMID, DOI, URL, and evidence role against PubMed:

```bash
PYTHONPATH=src python3 scripts/audit_hormone_citations.py \
  --output examples/reports/hormone_citation_audit_v12.json
```

The executed [recalibration plan](docs/healthy_cycle_recalibration_plan_v12.md) and
[critical validation report](docs/healthy_cycle_validation_v12.md) document the source separation,
acceptance gate, results, and remaining limitations.

Open the validation notebook:

```bash
jupyter notebook show_validation.ipynb
```

## Validation design

Baseline validation compares a balanced 10,000-woman adult natural-cycle cohort (ages 18--54.9,
matching AWHS adult eligibility) with literature targets:

- age-stratified mean cycle length
- pooled age-stratified within-person cycle-length SD
- participant-level age-stratified cycle irregularity
- age-stratified short-cycle (<24 days) and long-cycle (>38 days) tails
- mean follicular length
- mean luteal length
- mean and SD of bleeding duration and luteal length
- held-out 12-month mean cycle length and mean personal SD by age (Cunningham et al. 2024)
- sub-phase estradiol and progesterone medians
- preovulatory estradiol peak width
- consecutive premenstrual progesterone withdrawal
- terminal-to-peak progesterone ratio
- progesterone continuity across cycle boundaries

The 16 full diaries retained for hormone checks are balanced across the eight age bands (two per band). Hormone plotting uses separate estradiol (pg/mL) and progesterone (ng/mL) panels, because those concentrations do not share a commensurate physical scale. Hormone-anchor and waveform checks remain internal software checks; the Cunningham comparison is genuinely held out from calibration.

Age-stratified cycle metrics use equivalence windows centered on the published target estimates rather than requiring the simulator to fall inside the source-study confidence interval exactly. That choice is deliberate: the source cohorts are extremely large, so their confidence intervals are much narrower than a reasonable calibration tolerance for a simulator built from summary statistics rather than raw participant-level data.

If the healthy-cycle primary gate passes, secondary modifier stress tests run for:

- PCOS
- cyclic OCP use
- continuous OCP use
- levonorgestrel IUD
- copper IUD
- perimenopause
- peri-menarche
- dysmenorrhea

Each modifier is compared with an unmodified cohort generated from the same seed and age range: ages 18–44.9 for PCOS, contraception, IUD, and dysmenorrhea scenarios; ages 45–54.9 for perimenopause; and ages 13–17.9 for peri-menarche. The checks assess literature-supported directions or broad ranges—for example, higher irregularity and lower ovulation in PCOS, preserved ovulation with shorter bleeding under levonorgestrel IUD use, and longer bleeding without ovarian suppression under copper IUD use. Exact margins are investigator-selected regression guards, so these passes are software stress-test results rather than clinical validation.

## Running tests

The repo uses the standard library `unittest` module:

```bash
python3 -m unittest discover -s tests -v
```

## Outputs

`simulate` produces daily diary rows with these columns:

- `patient_id`
- `day_index`
- `age_years`
- `cycle_index`
- `cycle_day`
- `cycle_length`
- `estradiol_pg_ml`
- `progesterone_ng_ml`
- `ovulation`
- `uterine_bleeding`

The visualizer writes plain SVG, so no plotting libraries are required.
