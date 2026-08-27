# Phase 7 — validation and release handoff

Updated: 2026-08-27

Status: **prepared; implementation is gated by the open Phase 5 and Phase 6 manual checks**

## Purpose and gate

Phase 7 turns the local MVP into a reproducible, recoverable release. It does not add product
scope or change the approved Python, Streamlit, pandas, Plotly, Parquet, YAML, and local-file
architecture.

Phase 5 still requires desktop/phone, keyboard, displayed-value, and browser privacy checks.
Phase 6 still requires early/recent ESPN draft reconciliation, representative final-roster
reconciliation, sampled value/report-card reproduction, and the same browser checks. The user
authorized Phase 6 before Phase 5 exited, but neither phase should be described as complete until
its remaining evidence is recorded. Phase 7 implementation should begin only after those gates,
unless the user explicitly authorizes another override.

## Current automated baseline

At handoff, the application has offline validation and rebuild commands for snapshots, processed
tables, reviewed identities, core analytics, and draft analytics. The test suite covers safe import
and rollback behavior, normalization, identities, standings, playoffs, rivalries, records,
expected wins, draft value, final-roster states, report cards, and Streamlit smoke journeys.

Run the release baseline from the repository root:

```bash
.venv/bin/python scripts/rebuild_processed.py
.venv/bin/python scripts/validate_data.py
.venv/bin/python scripts/validate_identities.py --require-complete
.venv/bin/python scripts/rebuild_analytics.py
.venv/bin/python scripts/rebuild_draft_analytics.py
.venv/bin/pytest
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy fantasy_history app.py pages scripts
```

Rebuilding processed data is offline but replaces the current processed bundle from retained raw
snapshots after validation. Back up the current valid private data first when running the formal
release drill. A repeated rebuild must produce equivalent validated results without duplicate
rows, and each derived manifest must report current source, identity, formula, and threshold
checksums.

## Ordered Phase 7 work

1. Close and record every remaining Phase 5 and Phase 6 manual check.
2. Profile cold and warm page loads plus analytics rebuilds; optimize only measured bottlenecks.
3. Confirm file-read caches invalidate on processed, identity, analytics, formula, and threshold
   changes. Normal page rendering must stay offline and read-only.
4. Run the complete automated baseline and the acceptance matrix below.
5. Perform the privacy audit against Git, generated shareable files, rendered browser output, and
   logs.
6. Exercise backup, failed-refresh recovery, offline rebuild, and expired-cookie recovery.
7. Record the deployment decision: local-only, or hosting protected at the platform level.
8. Produce release evidence with dates, seasons sampled, commands/results, known limitations, and
   the approved deployment mode.

## Manual reconciliation matrix

Record exact source rows or ESPN screens used; do not rely on memory or convert missing values to
zero.

| Area | Required sample | Evidence to record |
| --- | --- | --- |
| Careers/standings | At least one early and one recent completed season | W-L-T, points, finish, segment, and canonical manager |
| Playoffs | Every completed season | Champion, runner-up, teams, rounds, byes, and irregular bracket notes |
| Rivalries | One long-running pair | Chronological meetings, ties, margins, record, lead, and streak |
| Records | Samples from each category | Displayed holder/value and exact processed source row keys |
| Expected wins | One scoring period, including a tie when available | Team scores, comparisons, tie credit, expected wins, and luck |
| Drafts | One early and one recent complete board | Round/pick order, source team, reviewed manager, player, and keeper state |
| Final rosters | Representative early and recent completed seasons | `season_roster` definition, coverage state, team, and player membership |
| Player value | Several boom, bust, drafted-sleeper, and neutral picks | Points, replacement baseline, expected value, surplus, normalized surplus, and threshold |
| Report cards | Several manager-seasons | Eligible pick set, component percentile, score, and grade boundary |

Undrafted sleeper attribution remains unavailable because retained roster-player rows lack
acquisition type. Do not infer it from a player appearing on a final roster. Injury context also
remains unavailable unless a separately validated source is added.

## Refresh and recovery procedure

Credentialed ESPN access occurs only through the explicit importer; Streamlit must never refresh
during page rendering.

1. Confirm the current app and both derived bundles are valid.
2. Make a private backup as described below.
3. Run `.venv/bin/python scripts/import_history.py --latest` for a normal refresh, or `--all` for
   the formal 2019-through-latest equivalence test.
4. Run data validation and complete identity validation.
5. Rebuild core analytics and draft analytics.
6. Start Streamlit and inspect coverage warnings before accepting the refreshed dataset.

Imports stage and validate a complete replacement before promotion. A failed fetch, validation,
write, normalization, or promotion must leave the previous valid raw and processed dataset in
place. If a refresh fails, do not delete the valid dataset: capture the redacted error, rerun the
offline validators, and repair credentials or source handling before retrying.

For the acceptance drill, import 2019 through latest twice and compare manifests/table counts and
content checksums for equivalent output. Deliberately exercise a fixture-backed failed refresh and
confirm the previous valid snapshot and processed bundle remain intact; do not create failures
against the live private league.

## Private backup procedure

The minimum durable backup is `data/raw/` plus `data/config/managers.yaml`; those inputs reproduce
processed and derived tables offline. Keeping `data/processed/` and `data/derived/` in the same
encrypted backup shortens recovery and preserves release evidence. Treat the whole backup as
private league data.

- Store the backup outside the repository in encrypted, access-controlled storage.
- Preserve directory names, manifests, and checksums.
- Do not commit, upload as a public CI artifact, or place it in a shared export directory.
- Keep ESPN credentials in a password/secret manager, separately from the data backup.
- Test restoration into a temporary private directory, then run the complete offline baseline.

If restoration is needed, keep the damaged copy, restore the last known-good raw snapshots and
manager mapping, rebuild processed/identity/analytics bundles, validate them, and only then replace
the local working dataset.

## Expired-cookie procedure

Authentication failures should be reported without credential values. When ESPN cookies expire:

1. Obtain fresh `ESPN_S2` and `ESPN_SWID` values through the owner's normal ESPN browser session.
2. Replace them only in the ignored local `.env` file or approved deployment secret store. Never
   paste them into chat, logs, screenshots, issues, or commits.
3. Run a one-season or latest-season import to validate access.
4. Run the normal validation and rebuild sequence.
5. Confirm `git status` contains no secret or private-data files before committing code or docs.

Do not weaken authentication-error handling, print request headers/cookies, or expose a remote
refresh endpoint to work around expired credentials.

## Privacy and release audit

- Confirm `.env`, `.streamlit/secrets.toml`, raw snapshots, processed/derived data, audit output,
  canonical manager mappings, staging files, and exports remain ignored and untracked.
- Search tracked files and commit history for credential names with assigned real values, ESPN
  member identifiers, raw payload fragments, and unnecessary private member information.
- Inspect rendered pages, downloads, browser console/network output, exception messages, and logs.
- Confirm the application never contacts ESPN during normal rendering and exposes no import or
  refresh control.
- Confirm missing/unavailable data is labeled unavailable, not zero, and all formulas and source
  references remain reproducible.

Synthetic fixtures may contain clearly fictional identifiers. They must stay share-safe and must
not be copied from the private league.

## Deployment decision

Local-only operation is acceptable for the MVP and is the default release recommendation until a
different decision is recorded. Remote deployment requires platform-level access protection or an
explicitly accepted unlisted-URL risk. It must not expose an unprotected refresh action, assume
hosted files persist across restarts, or bundle private data without approval.

Persistent hosted refreshes, multiple leagues, or concurrent editing require a separately approved
storage architecture revision. Do not introduce a database, custom login, frontend/backend split,
or custom JavaScript as part of Phase 7 without that approval.

## Phase 7 exit evidence

Phase 7 exits only when:

- every critical flow and automated check passes;
- the manual reconciliation matrix is completed and dated;
- cold/warm performance and cache invalidation are measured and acceptable;
- backup, restore, failed-refresh, offline rebuild, and expired-cookie procedures are exercised;
- credentials and private identifiers are absent from Git, shareable output, browser output, and
  logs;
- phone, desktop, and keyboard journeys pass; and
- the deployment decision, setup steps, recovery steps, known limitations, and release version are
  recorded.
