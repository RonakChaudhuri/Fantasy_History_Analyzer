# Fantasy History Analyzer

A private, read-only Streamlit application for exploring ESPN fantasy football league history. Phase 1 provides the project foundation and a fully synthetic preview; it does not import or display private ESPN data.

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
- Phase 1 uses synthetic data and establishes module boundaries, configuration safety, and the overview shell.
- ESPN importing, normalization, identity resolution, and analytics begin in later phases after their plan gates.
- The MVP remains Python, Streamlit, pandas, Plotly, Parquet, YAML, and local files—no database or custom login.

See `DEVELOPMENT_PLAN.md` for the approved scope, architecture, phases, security requirements, and acceptance tests.
