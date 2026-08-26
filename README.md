# Fantasy History Analyzer

A private, read-only Streamlit application for exploring ESPN fantasy football league history. The Streamlit preview remains synthetic while the explicit Phase 2 pipeline imports private ESPN history into ignored local JSON and Parquet files.

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

## Run the fixture preview

```bash
streamlit run app.py
```

The preview reads only `data/fixtures/demo_overview.json` and makes no ESPN request during rendering.

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

## Rebuild analytics

After identity validation passes with `--require-complete`, build the versioned analytics bundle without contacting ESPN:

```bash
python scripts/rebuild_analytics.py
```

The command calculates segmented standings, official finishes, expected wins and luck, manager careers, head-to-head totals, streaks, and traceable records. Formula, processed-source, identity, and attribution-policy checksums invalidate stale output. A failed build preserves the previous valid bundle.

Private snapshots, manifests, processed tables, staging data, and the canonical manager mapping remain ignored by Git. A failed fetch, validation, write, normalization, or promotion leaves the previous valid raw and processed dataset in place.

## Verify

```bash
pytest
ruff format --check .
ruff check .
mypy fantasy_history app.py
```

To apply formatting locally:

```bash
ruff format .
```

## Current boundaries

- Phase 0 ESPN feasibility is complete; see `docs/PHASE_0_FINDINGS.md`.
- Phase 1 uses synthetic data for the UI and establishes module boundaries, configuration safety, and the overview shell.
- Phase 2 implements explicit ESPN importing, validated/manifested JSON snapshots, deterministic Parquet normalization, offline rebuilding, and integrity validation.
- Phase 3 manager reconciliation is complete; the confirmed private mapping resolves every season-team and remains ignored by Git.
- Phase 3 implementation and exit evidence are documented in [`docs/PHASE_3_STATUS.md`](docs/PHASE_3_STATUS.md).
- Phase 4 is complete: the real local analytics bundle is promoted, reconciled, source-traceable, and versioned. Exit evidence is documented in [`docs/PHASE_4_STATUS.md`](docs/PHASE_4_STATUS.md).
- Phase 5 inputs, page contracts, readiness behavior, accessibility requirements, tests, and exit criteria are prepared in [`docs/PHASE_5_HANDOFF.md`](docs/PHASE_5_HANDOFF.md).
- The MVP remains Python, Streamlit, pandas, Plotly, Parquet, YAML, and local files—no database or custom login.

See `DEVELOPMENT_PLAN.md` for the approved scope, architecture, phases, security requirements, and acceptance tests.
