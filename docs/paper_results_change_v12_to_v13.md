# Paper-result change audit: HORMONE-CYCLE v0.2.0 to v0.3.0

This report compares the definitive cycle-calibrated full run with the waveform-recalibrated full run. Deltas are v0.3.0 minus v0.2.0.

## Headline endpoints

| Cohort | Window | Definition | v0.2.0 rate | v0.3.0 rate | Change (percentage points) |
|---|---|---|---:|---:|---:|
| healthy_ovulatory | calendar 3 | A_windowed_any | 41.63% | 41.63% | +0.00 |
| healthy_ovulatory | cycle 3 | A_exact_any | 50.53% | 50.53% | +0.00 |
| healthy_ovulatory | full full_diary | A_windowed_C1_or_C2 | 11.35% | 11.35% | +0.00 |
| healthy_ovulatory | full full_diary | A_windowed_C3_only | — | — | — |
| healthy_ovulatory | full full_diary | A_windowed_any | 11.35% | 11.35% | +0.00 |
| healthy_ovulatory | full full_diary | D_nb_regression_C1_or_C2 | 4.29% | 4.29% | +0.00 |
| population | calendar 3 | A_windowed_any | 51.31% | 50.95% | -0.36 |
| population | cycle 3 | A_exact_any | 52.66% | 52.23% | -0.43 |
| population | full full_diary | A_windowed_C1_or_C2 | 11.59% | 11.59% | +0.00 |
| population | full full_diary | A_windowed_C3_only | 36.58% | 37.10% | +0.52 |
| population | full full_diary | A_windowed_any | 36.42% | 35.92% | -0.50 |
| population | full full_diary | D_nb_regression_C1_or_C2 | 4.25% | 4.25% | +0.00 |

## Complete summary-table alignment

- v0.2.0 rows: 19,703
- v0.3.0 rows: 19,703
- Aligned rows: 19,703
- v0.2.0-only rows: 0
- v0.3.0-only rows: 0

The JSON companion contains cohort-level changes and maximum/mean absolute movement for every aligned numeric summary column.
