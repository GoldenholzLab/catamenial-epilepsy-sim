# catamenial-epilepsy-sim

`hormone_cycler` is a pure-Python simulator for menstrual-cycle diaries. Given a patient age, diary length, and medical modifiers, it generates daily values for:

- estradiol (`estradiol_pg_ml`)
- progesterone (`progesterone_ng_ml`)
- ovulation (`0/1`)
- uterine bleeding (`0/1`)

The repo also includes:

- `vis_cycles`: an SVG visualizer for individual diaries
- population simulation utilities for 10,000-woman cohorts
- a validation harness that compares simulated outputs with peer-reviewed literature targets

## Scientific basis

The model is hierarchical rather than a hand-drawn waveform:

1. Age-specific cycle-length targets come from the Apple Women's Health Study / Nurses' Health Study 3 analysis in [Li et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11228203/).
2. Follicular and luteal phase timing targets come from the 600,000-cycle Natural Cycles analysis in [Bull et al. 2019](https://www.nature.com/articles/s41746-019-0152-7).
3. Daily estradiol and progesterone curves are interpolated from serum sub-phase medians reported in [Stricker et al. 2006](https://pubmed.ncbi.nlm.nih.gov/16776638/).
4. Bleeding-duration targets use normal uterine-bleeding ranges summarized by [Fraser et al. 2011](https://pubmed.ncbi.nlm.nih.gov/22045566/).
5. Clinical-factor modifiers are constrained by peer-reviewed subgroup literature:
   - PCOS: [Mortimer et al. 2025](https://pubmed.ncbi.nlm.nih.gov/39960584/) and [Doi et al. 2005](https://pubmed.ncbi.nlm.nih.gov/16117815/)
   - Peri-menarche: [Venturoli et al. 1987](https://pubmed.ncbi.nlm.nih.gov/3127843/)
   - Perimenopause: [Santoro and Randolph 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3414596/)
   - Combined oral contraceptives: [Edelman et al. 2014](https://pubmed.ncbi.nlm.nih.gov/25072731/)
   - Levonorgestrel IUD: [Xiao et al.](https://pubmed.ncbi.nlm.nih.gov/7554977/)
   - Copper IUD / non-hormonal IUD bleeding effects: [Hubacher et al.](https://pubmed.ncbi.nlm.nih.gov/17157103/)
   - Dysmenorrhea: [Dawood 2006](https://pubmed.ncbi.nlm.nih.gov/16880317/)

Important modeling note:

- The combined oral-contraceptive modes simulate suppression of endogenous ovarian estradiol and progesterone. They do not separately model synthetic ethinyl estradiol or progestin assay concentrations.
- "Bare metal IUD" is implemented as a copper / non-hormonal IUD phenotype.
- For several factor subgroups, the published literature provides effect direction and clinically useful ranges rather than full raw daily hormone series. In those cases, the simulator uses fitted latent modifiers constrained by the reported study summaries instead of unconstrained ad hoc constants. Those fit decisions are documented inline in the code comments.

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
  --json-output examples/reports/validation_report.json
```

Open the validation notebook:

```bash
jupyter notebook show_validation.ipynb
```

## Validation design

Baseline validation compares a balanced 10,000-woman natural-cycle cohort with literature targets:

- age-stratified mean cycle length
- age-stratified cycle irregularity
- mean follicular length
- mean luteal length
- mean bleeding duration
- sub-phase estradiol and progesterone medians

Age-stratified cycle metrics use equivalence windows centered on the published target estimates rather than requiring the simulator to fall inside the source-study confidence interval exactly. That choice is deliberate: the source cohorts are extremely large, so their confidence intervals are much narrower than a reasonable calibration tolerance for a simulator built from summary statistics rather than raw participant-level data.

If the baseline cohort passes, subgroup validation runs for:

- PCOS
- cyclic OCP use
- continuous OCP use
- levonorgestrel IUD
- copper IUD
- perimenopause
- peri-menarche
- dysmenorrhea

Each subgroup check compares the simulated cohort against the relevant literature-backed direction or range: for example, higher irregularity and lower ovulation in PCOS, preserved ovulation with shorter bleeding under levonorgestrel IUD use, and longer bleeding without ovarian suppression under copper IUD use.

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
