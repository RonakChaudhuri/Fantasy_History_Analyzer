# Phase 0 findings

Audit date: 2026-08-25

Representative seasons: 2019, 2022, and 2026

Result: Phase 0 exit criteria satisfied

This document contains aggregate counts and configuration only. It contains no manager names, team names, member identifiers, player names, scores, credentials, request headers, or raw ESPN responses.

## Coverage matrix

| Season | Settings | Members | Teams | Schedule | Playoffs | Draft picks | Week 1 lineup entries | Roster entries | PPR |
| ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 2019 | yes | 12 | 12 | 97 | 19 | 192 | unavailable | 192 | yes |
| 2022 | yes | 13 | 12 | 103 | 19 | 192 | 195 | 190 | yes |
| 2026 | yes | 12 | 12 | 84 | 0 | 204 | 206 | 0 | yes |

PPR is confirmed by a value of `1.0` for ESPN reception statistic ID `53` in every representative season. ESPN reports the scoring type as `H2H_POINTS`.

The 2026 season is active and incomplete at audit time. Zero playoff and roster entries are therefore an available-but-empty state, not historical zeroes. The application must preserve that distinction.

## Lineup configuration

The audit retains ESPN lineup slot IDs so later normalization can map them deliberately instead of guessing.

| Slot ID | 2019 | 2022 | 2026 |
| ---: | ---: | ---: | ---: |
| 0 | 1 | 1 | 1 |
| 2 | 2 | 2 | 2 |
| 4 | 2 | 2 | 2 |
| 6 | 1 | 1 | 1 |
| 16 | 1 | 1 | 1 |
| 17 | 1 | 1 | 1 |
| 20 | 7 | 7 | 7 |
| 21 | 0 | 1 | 1 |
| 23 | 1 | 1 | 2 |

All other returned slot counts are zero. The 2026 configuration changes slot `23` from one to two and has 204 draft picks rather than 192, so lineup and draft schemas must remain season-specific.

## Response-shape findings

- The normal season endpoint returns HTTP 401 for the 2019 league, while ESPN's `leagueHistory` endpoint succeeds with the same credentials. The importer must support both endpoint shapes and unwrap the list returned by league history.
- The 2019 scoring-period request does not expose `rosterForCurrentScoringPeriod`; 2022 and 2026 do. Historical lineups must be treated as unavailable unless another validated ESPN request supplies them.
- Completed seasons expose cumulative scores, points by scoring period, standings update dates, and populated playoff records that are absent or incomplete in the active 2026 season.
- The active season exposes live/delayed matchup rosters, roster-lock fields, rankings, and other current-state fields that are not consistently present in completed seasons.
- The 2022 response includes member notification settings. These are unnecessary private data and must be discarded during normalization and excluded from fixtures.
- Member count does not always equal team count: 2022 returns 13 members for 12 teams. Members cannot be assumed to map one-to-one to season teams.
- Draft `memberId` is absent from the active 2026 draft response. Draft ownership must use validated team/source keys rather than depending on that field.
- ESPN returns dynamic object maps keyed by statistic ID, slot ID, scoring period, and timestamps. Validation must allow those keys while strictly validating the surrounding record shape.

## Constraints carried forward

- Missing or active-season data is represented as unavailable or incomplete, never zero-filled.
- Phase 2 import adapters must support both current-season and `leagueHistory` responses.
- Week-specific lineup importing requires explicit scoring-period requests; a single unfiltered league response is insufficient.
- Final-roster semantics remain a documented deferred decision. The `mRoster` response is usable for completed representative seasons but empty for the active season at audit time.
- Private response bodies remain ignored local data. Only structural field paths and aggregate audit results are shareable.
