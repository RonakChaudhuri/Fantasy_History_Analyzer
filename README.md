# Fantasy History Analyzer

A private, read-only Streamlit application for exploring ESPN fantasy football league history. The application reads promoted local Parquet analytics and never contacts ESPN during normal rendering.

## Requirements

- Python 3.12 or 3.13
- Local ESPN credentials are needed only for explicit audit/import commands, never to view the demo

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Copy `.env.example` to the ignored `.env` file if you need to run a credentialed command. Set `ESPN_S2` and `ESPN_SWID` locally; never paste them into chat or commit them.

## Run the local app

```bash
streamlit run app.py
```

The Overview, Standings, Managers, Rivalries, Seasons, Drafts, and Records journeys read only validated processed, identity, and analytics files. Missing or stale data produces local rebuild instructions rather than an automatic import.

## Import and normalize history

These commands use local credentials and are the only workflows that contact ESPN. They stage and validate a complete replacement before promoting either raw snapshots or processed tables.

```bash
# One season
python scripts/import_history.py --season 2019

# Every season from ESPN_FIRST_SEASON through the latest accessible season
python scripts/import_history.py --all

# Refresh only the latest accessible season
python scripts/import_history.py --latest
```

Rebuild Parquet without ESPN access, then validate local manifests, checksums, source references, and table integrity:

```bash
python scripts/rebuild_processed.py
python scripts/validate_data.py
```

## Reconcile canonical managers

Generate an ignored suggestion file for review, then edit the ignored canonical mapping manually. Suggestions are evidence only and are never applied automatically.

```bash
python scripts/validate_identities.py --write-suggestions data/config/managers.suggestions.yaml
cp data/config/managers.example.yaml data/config/managers.yaml
# Review and edit data/config/managers.yaml locally.
python scripts/validate_identities.py --require-complete
```

The YAML supports stable member identifiers, explicit season/team overrides, aliases, co-owners, and ownership transfers. A valid rebuild writes source-traceable Parquet files under `data/derived/identities/` atomically; conflicts or required-completeness failures preserve the prior valid output.

If ESPN supplied numeric fallback display handles, normalized history prefers the member's first/last name. Preview and then apply source-backed label replacements without changing identity assignments:

```bash
python scripts/update_manager_display_names.py
python scripts/update_manager_display_names.py --apply
python scripts/validate_identities.py --require-complete
python scripts/rebuild_analytics.py
```

Reviewed handle-specific corrections can also be dry-run and atomically applied. A rename merges into an existing canonical display name when present; deleting one side of a shared assignment collapses the remaining side to a single-owner assignment only when the complete identity validator approves the result.

```bash
python scripts/apply_identity_overrides.py --rename 'HANDLE=Manager Name' --delete OLD_HANDLE
python scripts/apply_identity_overrides.py --rename 'HANDLE=Manager Name' --delete OLD_HANDLE --apply
```

## Rebuild analytics

After identity validation passes with `--require-complete`, build the versioned analytics bundle without contacting ESPN:

```bash
python scripts/rebuild_analytics.py
python scripts/rebuild_draft_analytics.py
```

The commands calculate segmented standings, official finishes, expected wins and luck, manager careers, head-to-head totals, streaks, traceable records, replacement baselines, expected draft value, normalized surplus, classifications, and draft report cards. Formula, threshold, processed-source, identity, and attribution-policy checksums invalidate stale output. A failed build preserves the previous valid bundle.

Private snapshots, manifests, processed tables, staging data, and the canonical manager mapping remain ignored by Git. A failed fetch, validation, write, normalization, or promotion leaves the previous valid raw and processed dataset in place.

## Verify

```bash
.venv/bin/python scripts/release_check.py
.venv/bin/python scripts/validate_data.py
.venv/bin/python scripts/validate_identities.py --require-complete
.venv/bin/python scripts/rebuild_analytics.py
.venv/bin/python scripts/rebuild_draft_analytics.py
.venv/bin/pytest
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy fantasy_history app.py pages scripts
```

The release preflight is offline and read-only. It verifies core and draft bundle currency,
identity completeness, prohibited tracked paths, and apparent credential assignments in tracked
text files. It intentionally reports the manual reconciliation, responsive/keyboard, recovery,
and deployment gates separately; a passing preflight does not by itself declare a release.

To apply formatting locally:

```bash
ruff format .
```

## Current boundaries

- Phase 0 ESPN feasibility is complete; see `docs/PHASE_0_FINDINGS.md`.
- Phase 1 established the synthetic UI foundation, module boundaries, configuration safety, and overview shell.
- Phase 2 implements explicit ESPN importing, validated/manifested JSON snapshots, deterministic Parquet normalization, offline rebuilding, and integrity validation.
- Phase 3 manager reconciliation is complete; the confirmed private mapping resolves every season-team and remains ignored by Git.
- Phase 3 implementation and exit evidence are documented in [`docs/PHASE_3_STATUS.md`](docs/PHASE_3_STATUS.md).
- Phase 4 is complete: the real local analytics bundle is promoted, reconciled, source-traceable, and versioned. Exit evidence is documented in [`docs/PHASE_4_STATUS.md`](docs/PHASE_4_STATUS.md).
- Phase 5 inputs, page contracts, readiness behavior, accessibility requirements, tests, and exit criteria are prepared in [`docs/PHASE_5_HANDOFF.md`](docs/PHASE_5_HANDOFF.md).
- Phase 5 implementation is in progress: all six core journeys and their shared readiness boundary are implemented; viewport and final manual reconciliation remain. See [`docs/PHASE_5_STATUS.md`](docs/PHASE_5_STATUS.md).
- Phase 6 draft/roster inputs and source-sufficiency requirements are defined in [`docs/PHASE_6_HANDOFF.md`](docs/PHASE_6_HANDOFF.md). The user explicitly authorized development while Phase 5's manual exit checks remain open. Draft boards, pick history, tendencies, safe completed-season rosters, actual production, replacement baselines, expected value, boom/bust/drafted-sleeper labels, and report cards are implemented. Undrafted sleeper attribution remains unavailable because retained snapshots lack acquisition type. See [`docs/PHASE_6_STATUS.md`](docs/PHASE_6_STATUS.md) and [`docs/PHASE_6_SOURCE_SUFFICIENCY.md`](docs/PHASE_6_SOURCE_SUFFICIENCY.md).
- Phase 7 validation, operations, privacy, recovery, and deployment decisions are prepared in [`docs/PHASE_7_HANDOFF.md`](docs/PHASE_7_HANDOFF.md). Development began by explicit user authorization on 2026-08-27 while the open Phase 5 and Phase 6 checks remain release debt. See [`docs/PHASE_7_STATUS.md`](docs/PHASE_7_STATUS.md).
- The MVP remains Python, Streamlit, pandas, Plotly, Parquet, YAML, and local files—no database or custom login.

See `DEVELOPMENT_PLAN.md` for the approved scope, architecture, phases, security requirements, and acceptance tests.
