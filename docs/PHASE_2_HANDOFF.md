# Phase 2 handoff — import and normalization

Prepared: 2026-08-25

Current state: Phase 1 foundation implemented; desktop and phone-width visual smoke checks remain the final documented Phase 1 exit item.

Source of truth: `DEVELOPMENT_PLAN.md` and `AGENTS.md`

This handoff preserves context for Phase 2. It does not revise the approved plan or authorize starting Phase 2 before the Phase 1 exit criteria are accepted.

## Foundation available to Phase 2

- Python 3.12/3.13 package with pinned Streamlit, pandas, Plotly, PyArrow, Pydantic, HTTPX, PyYAML, pytest, Ruff, and mypy dependencies.
- Module boundaries already exist for ESPN access, importing, validation, normalization, identities, analytics, data access, and presentation formatting.
- `fantasy_history.config.load_settings()` validates local ESPN configuration and keeps credentials wrapped as Pydantic secrets.
- `fantasy_history.redaction` sanitizes credentials, authorization data, cookies, URL query values, exceptions, and nested diagnostic context.
- Private raw, processed, derived, audit, manager-mapping, staging, temporary, and Streamlit secret files are ignored.
- Streamlit rendering uses only synthetic fixture data and makes no ESPN request.
- The local development server binds to `127.0.0.1`.

The boundary modules are placeholders, not partial Phase 2 implementations. Replace their docstring-only contents deliberately rather than assuming behavior already exists.

## Phase 0 constraints to retain

1. League `78212237` is PPR and begins in 2019.
2. The latest audited league season is 2026, which was active and incomplete on 2026-08-25.
3. The normal season endpoint returned HTTP 401 for 2019 while the `leagueHistory` endpoint succeeded. The client needs a validated historical fallback and must unwrap its top-level list.
4. Week-specific lineup data requires an explicit `scoringPeriodId` request.
5. The audited 2019 response did not expose `rosterForCurrentScoringPeriod`; represent it as unavailable unless another validated request supplies it.
6. Active-season playoff and roster collections can be available but empty. Do not convert this state into a completed historical zero.
7. Member count and team count are not interchangeable; 2022 returned 13 members and 12 teams.
8. Discard member notification settings and other unnecessary personal fields during normalization.
9. Active-season draft picks may omit `memberId`; retain and use validated team/source keys.
10. Lineup slot settings changed between seasons. Store season-specific settings rather than applying the latest settings to history.
11. ESPN returns dynamic maps keyed by statistic ID, lineup slot ID, scoring period, and timestamps. Validate the surrounding structure while allowing documented dynamic keys.

See `PHASE_0_FINDINGS.md` for the share-safe coverage matrix and response-shape report.

## Approved Phase 2 scope

- Implement ESPN adapters with bounded retries, timeouts, authentication-error detection, current/historical response handling, and centralized redaction.
- Validate responses before any snapshot is promoted.
- Write immutable season JSON snapshots and manifests atomically through a staging location.
- Preserve the last valid dataset whenever fetch, validation, normalization, or promotion fails.
- Normalize supported league, season, manager-source, team, matchup, score, playoff, player, draft, and roster entities into Parquet.
- Add single-season import, full-history import, offline rebuild, and validation scripts.
- Add integrity checks and sanitized regression fixtures.
- Keep manager reconciliation out of Phase 2. Preserve source identifiers and leave ambiguous canonical-manager decisions for Phase 3.
- Keep standings, rivalry, record, expected-win, and draft-value formulas out of Phase 2.

## Recommended implementation sequence

1. Define Pydantic boundary models for raw response envelopes, coverage states, and manifests.
2. Define processed-table column contracts, nullability, source keys, and traceability fields before writing transformations.
3. Implement the ESPN client with injected HTTP transport so tests never need the network.
4. Add response-route selection and historical-list unwrapping using sanitized Phase 0 shapes.
5. Implement checksum calculation, staging directories, validation, and atomic snapshot promotion.
6. Normalize season and team/member source entities.
7. Normalize schedules, team scores, and playoffs while preserving unavailable/incomplete states.
8. Normalize drafts, players, scoring-period lineups, and roster snapshots where covered.
9. Add manifests with league ID, season, fetch time, importer version, checksums, coverage, counts, and warnings.
10. Add the explicit CLI scripts and verify rebuilds require no ESPN access.
11. Test repeat imports for equivalent output and deliberately fail refreshes at fetch, validation, write, and promotion boundaries.
12. Run privacy and traceability audits before declaring the phase complete.

## Data contracts to settle before implementation

- Stable source-row keys for every normalized table.
- A coverage vocabulary that distinguishes `unavailable`, `available-empty`, `partial`, and `complete`.
- Timezone-aware timestamps and the canonical representation for scoring periods.
- Regular-season, championship-playoff, and consolation classification fields without computing later-phase standings.
- Draft ownership keys when member IDs are missing.
- Roster snapshot type and timestamp semantics; final-roster semantics remain deferred until validated.
- Manifest and importer schema versions used to detect incompatible snapshots.
- Deterministic Parquet ordering and serialization rules so equivalent imports can be compared reliably.

## Required Phase 2 tests

- Current-season and historical fallback parsing, including top-level list unwrapping.
- Authentication rejection and safe error messages with no credential values.
- Bounded retry behavior for temporary errors and no retry for permanent validation/authentication failures.
- Missing optional branches, dynamic maps, available-empty collections, and partial active seasons.
- Ties, byes, missing weeks, irregular playoff shapes, and season boundaries in normalized source rows without calculating Phase 4 analytics.
- Team renames and changing source identifiers retained without premature canonical-manager merging.
- Repeated imports produce equivalent, non-duplicated JSON/Parquet outputs.
- Offline rebuild reproduces processed files from raw snapshots.
- Failed refreshes leave the prior valid snapshot and processed dataset intact.
- Every normalized sample row traces to a season and raw source key.
- Cookies, authorization headers, URLs/query values, notification settings, and unnecessary personal data are absent from fixtures, logs, errors, and shareable outputs.

## Phase 2 exit gate

Do not advance to manager reconciliation until:

- Every available season from 2019 through the latest season imports successfully.
- Repeating the import produces equivalent output without duplication.
- Offline rebuild succeeds from raw snapshots.
- Failure injection proves the previous valid data remains intact.
- Coverage and warnings accurately describe unavailable, empty, partial, and complete source sections.
- Tests, formatting, linting, typing, privacy scans, and representative source-row reconciliation pass.

Do not use the private ESPN API during normal Streamlit rendering, expose a refresh control remotely, or commit any generated private data.
