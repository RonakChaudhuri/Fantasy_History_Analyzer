# Phase 2 — import and normalization status

Updated: 2026-08-25

Status: **implemented and verified against 2019–2026 private league data**

The user explicitly directed Phase 2 to start while the Phase 1 desktop/phone browser smoke check remained blocked by the absence of a connected browser. That unresolved visual check is still documented in `PHASE_1_FOUNDATION.md`; it has not been marked as passed.

## Implemented

- Injectable HTTPX ESPN adapter with timeouts, bounded exponential retries, permanent-error handling, credential rejection detection, current-season routing, and historical `leagueHistory` fallback/list unwrapping.
- Boundary validation that requires stable ESPN containers while allowing dynamic statistic, slot, scoring-period, and timestamp maps.
- Explicit `unavailable`, `available-empty`, `partial`, and `complete` coverage states.
- Per-season atomic JSON staging with manifests containing version, route, fetch time, checksums, structural field paths, coverage, counts, and warnings.
- Removal of unnecessary member contact and notification fields before snapshots are persisted.
- Transactional promotion with rollback of both the prior season snapshot and processed dataset if promotion fails.
- Eleven deterministic, source-traceable Parquet contracts: seasons, source managers, season teams, matchups, team scores, playoff results, players, drafts, draft picks, roster snapshots, and roster players.
- Season-specific lineup slot settings, source member/team IDs, draft team ownership, weekly lineup snapshots, and explicit active-season partial states.
- Single-season, full-history, latest-season, offline-rebuild, and local-validation commands.
- Regression fixtures and failure injection for fetch, response validation, snapshot write, checksum corruption, and raw/processed promotion boundaries.

Phase 2 deliberately does not merge canonical manager identities or calculate standings, rivalries, records, expected wins, luck, or draft value.

## Real-data verification

- All eight seasons from 2019 through the latest accessible 2026 season imported successfully.
- The full dataset produced 25,497 normalized rows across 11 tables.
- A repeated import produced the same row total and byte-identical Parquet hashes without duplicates.
- Offline rebuilding from the raw snapshot set succeeded and local validation accepted all eight manifests and all eleven tables.
- Completed seasons are marked complete where populated; 2019–2021 weekly lineups are explicitly unavailable; the active 2026 schedule, playoffs, draft, lineups, and rosters are explicitly partial.
- Representative early, middle, and current season counts reconcile with the Phase 0 audit coverage.
- Unnecessary notification/contact fields are absent from persisted snapshots; 2022–2026 manifests record the privacy removal warning.

Generated private raw and processed data remains ignored and is not part of the Git worktree.

## Verification commands

```bash
pytest
ruff format --check .
ruff check .
mypy fantasy_history app.py scripts/import_history.py scripts/rebuild_processed.py scripts/validate_data.py
python scripts/validate_data.py
python scripts/rebuild_processed.py
```

Do not begin Phase 3 until this status and the remaining Phase 1 viewport debt are reviewed against `DEVELOPMENT_PLAN.md`.
