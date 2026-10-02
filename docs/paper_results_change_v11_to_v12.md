# Paper-result change audit: HORMONE-CYCLE v0.1.x to v0.2.0

This report compares the previous repaired full run with the definitive cycle-calibrated full run. Deltas are v12 minus v11.

## Headline endpoints

| Cohort | Window | Definition | v11 rate | v12 rate | Change (percentage points) |
|---|---|---|---:|---:|---:|
| healthy_ovulatory | calendar 3 | A_windowed_any | 41.39% | 41.63% | +0.24 |
| healthy_ovulatory | cycle 3 | A_exact_any | 49.81% | 50.53% | +0.72 |
| healthy_ovulatory | full full_diary | A_windowed_C1_or_C2 | 11.68% | 11.35% | -0.33 |
| healthy_ovulatory | full full_diary | A_windowed_C3_only | — | — | — |
| healthy_ovulatory | full full_diary | A_windowed_any | 11.68% | 11.35% | -0.33 |
| healthy_ovulatory | full full_diary | D_nb_regression_C1_or_C2 | 4.39% | 4.29% | -0.10 |
| population | calendar 3 | A_windowed_any | 50.67% | 51.31% | +0.64 |
| population | cycle 3 | A_exact_any | 51.47% | 52.66% | +1.19 |
| population | full full_diary | A_windowed_C1_or_C2 | 11.67% | 11.59% | -0.08 |
| population | full full_diary | A_windowed_C3_only | 36.72% | 36.58% | -0.14 |
| population | full full_diary | A_windowed_any | 36.16% | 36.42% | +0.26 |
| population | full full_diary | D_nb_regression_C1_or_C2 | 4.21% | 4.25% | +0.04 |

## Complete summary-table alignment

- v11 rows: 19,701
- v12 rows: 19,703
- Aligned rows: 19,701
- v11-only rows: 0
- v12-only rows: 2

The JSON companion contains cohort-level changes and maximum/mean absolute movement for every aligned numeric summary column.
