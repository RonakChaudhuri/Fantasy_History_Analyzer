# Phase 6 — ESPN player-scoring source sufficiency

Validated: 2026-08-27

## Approved semantics

The user confirmed the ESPN scoring semantics. The normalized implementation records the numeric
identifiers alongside these approved labels:

| ESPN field contract | Meaning used by the MVP |
| --- | --- |
| `statSourceId = 0` | Actual scoring |
| `statSourceId = 1` | Projected scoring |
| `statSplitTypeId = 0`, `scoringPeriodId = 0` | Season total |
| `statSplitTypeId = 1`, positive `scoringPeriodId` | Weekly scoring |
| Any other combination | Unknown and ineligible |

Normalization version `phase2.v4` preserves every observed stat record in
`player_scores.parquet`, including the observation snapshot type/week, source team and player,
score season/week, numeric source/split identifiers, approved semantic labels, applied fantasy
points, availability, semantic version, source file, and source row key.

Production formula `phase6.actual-season-total.v1` uses only available actual season-total rows for
the same league season. Repeated observations with the same value are deduplicated and retain all
source-row references. Conflicting season totals are ineligible. Projected and weekly rows are not
summed into full-season production.

## Current retained-source coverage

The offline rebuild produced 37,206 player-score observations. Draft-pick production eligibility is:

| Season | Draft picks | Eligible actual season totals | Eligible share |
| ---: | ---: | ---: | ---: |
| 2019 | 192 | 134 | 69.8% |
| 2020 | 192 | 138 | 71.9% |
| 2021 | 192 | 128 | 66.7% |
| 2022 | 192 | 138 | 71.9% |
| 2023 | 192 | 137 | 71.4% |
| 2024 | 192 | 134 | 69.8% |
| 2025 | 204 | 149 | 73.0% |
| 2026 | 204 | 0 | 0.0% |

Every non-eligible completed-season pick currently lacks an actual season-total observation; none
is converted to zero. All 2026 picks are ineligible because the season is active.

## Remaining boundary

This is sufficient to calculate production for the eligible subset, but not to label every pick.
Any full-history player-value view must show the eligibility denominator. A separately validated
player-data import would be required to cover drafted players missing from retained roster and
lineup observations.
