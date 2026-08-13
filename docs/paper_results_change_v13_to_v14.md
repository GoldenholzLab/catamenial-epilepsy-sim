# Paper-result change audit: HORMONE-CYCLE v0.3.0 to v0.4.0

This report compares the two specified full-study runs. Deltas are v0.4.0 minus v0.3.0.

## Headline endpoints

| Cohort | Window | Definition | v0.3.0 rate | v0.4.0 rate | Change (percentage points) |
|---|---|---|---:|---:|---:|
| healthy_ovulatory | calendar 3 | A_windowed_any | 41.63% | 41.63% | +0.00 |
| healthy_ovulatory | cycle 3 | A_exact_any | 50.53% | 50.53% | +0.00 |
| healthy_ovulatory | full full_diary | A_windowed_C1_or_C2 | 11.35% | 11.35% | +0.00 |
| healthy_ovulatory | full full_diary | A_windowed_C3_only | — | — | — |
| healthy_ovulatory | full full_diary | A_windowed_any | 11.35% | 11.35% | +0.00 |
| healthy_ovulatory | full full_diary | D_nb_regression_C1_or_C2 | 4.29% | 4.29% | +0.00 |
| population | calendar 3 | A_windowed_any | 50.95% | 50.97% | +0.02 |
| population | cycle 3 | A_exact_any | 52.23% | 52.23% | +0.00 |
| population | full full_diary | A_windowed_C1_or_C2 | 11.59% | 11.58% | -0.01 |
| population | full full_diary | A_windowed_C3_only | 37.10% | 37.04% | -0.05 |
| population | full full_diary | A_windowed_any | 35.92% | 35.84% | -0.07 |
| population | full full_diary | D_nb_regression_C1_or_C2 | 4.25% | 4.27% | +0.01 |

## Complete summary-table alignment

- v0.3.0 rows: 19,703
- v0.4.0 rows: 19,703
- Aligned rows: 19,703
- v0.3.0-only rows: 0
- v0.4.0-only rows: 0

The JSON companion contains cohort-level changes and maximum/mean absolute movement for every aligned numeric summary column.

## Scale and interpretation of the changes

- Healthy-ovulatory cohort means and all six prespecified headline endpoints were numerically unchanged.
- In the heterogeneous cohort, mean realized cycle length changed from 30.0953 to 30.0928 days, within-person cycle-length SD from 5.6047 to 5.6081 days, and ovulatory-cycle fraction from 0.789551 to 0.789458. Seizure-process summaries and sampled modifier prevalences were unchanged.
- The waveform/cycle revision changed at least one of those three cycle summaries for 3,717 of 50,000 heterogeneous-cohort participants (7.4%) and for no healthy-ovulatory participants. This is the expected footprint of the revised long-cycle/perimenopause coupling rather than a change to the seizure generator.
- Across 9,920 comparable false-positive-rate rows, the mean absolute movement was 0.070 percentage points. The unfiltered maximum (50 percentage points) came from an unstable reproducibility stratum whose denominator changed from one to two. With at least 10,000 classifiable observations, the maximum absolute movement was 0.808 percentage points and the mean was 0.032 percentage points.
- Across study-level prevalence benchmarks, the largest absolute probability change was 1.34 percentage points and the mean absolute change was 0.147 percentage points.

## Supplementary outputs

- Supplementary Figures S1, S2, and S4 were byte-identical. Figures S3 and S5 changed because cycle-length/ovulation realizations changed in the heterogeneous cohort.
- The largest C3 window-sensitivity change was 0.396 percentage points (heterogeneous cohort, one-month calendar window). The largest plotted classification-association change was 0.466 percentage points.
- The exploratory audit-sample C3 negative-binomial rate changed from 12/197 (6.09%) to 13/198 (6.57%). This one-event movement in a 500-person audit subset is within its wide Wilson interval and does not alter interpretation.

## Manuscript-facing assessment

The scientific conclusions are unchanged. Two heterogeneous-cohort headline values change at one-decimal precision: full-diary windowed Herzog any C1-C3 changes from 35.9% to 35.8%, and full-diary C3-only changes from 37.1% to 37.0%. Other headline values retain their reported one-decimal rounding.

The v0.4.0 full run used 16 worker processes and completed in 2 h 39 m 15 s, versus 2 h 55 m 30 s for v0.3.0 (16 m 15 s faster; 9.3%). The 65-test suite and 29 subtests passed; all primary and supplementary manifest records match their current files, and the 14-cell results notebook executed without cell errors. No manuscript or appendix DOCX was edited.
