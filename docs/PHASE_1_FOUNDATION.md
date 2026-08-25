# Phase 1 — project foundation

Status: **implementation complete; viewport smoke check pending**

Updated: 2026-08-25

Phase 1 establishes the approved Python and Streamlit foundation without starting ESPN importing, normalization, identity reconciliation, or analytics.

## Implemented

- Python 3.12/3.13 package metadata with pinned application and development dependencies.
- Separate package boundaries for configuration, ESPN access, importing, validation, normalization, identity resolution, analytics, data access, and formatting.
- Validated server-only settings with `SecretStr` credentials and safe actionable errors.
- Central redaction for known secret values, authorization data, cookies, URL query values, exceptions, and nested diagnostic context.
- Synthetic fixture data with no private ESPN member, team, player, score, or credential values.
- A fixture-powered Streamlit overview with league summary metrics, a champions timeline, leaders, records, and an explicit demo-data notice.
- Pytest, Ruff formatting/linting, and mypy configuration.
- Local setup, run, and verification commands in the root README.
- Ignore rules for credentials, raw snapshots, processed/derived data, audits, staging files, generated exports, and local Streamlit secrets.
- A local-only Streamlit server binding (`127.0.0.1`) so the development command does not expose an unprotected refresh or preview surface to the network.

## Verification

- `pytest`: 15 passed on Python 3.13.7.
- `ruff format --check .`: passed.
- `ruff check .`: passed.
- `mypy fantasy_history app.py`: passed.
- Streamlit's programmatic app test rendered the page with no exception while socket creation was denied, proving the fixture preview does not make a network request.
- A live Streamlit server started on port 8501 and returned `ok` from `/_stcore/health`.
- Ignore-rule checks confirmed private and temporary example paths are excluded.
- Actual local ESPN secret values were checked against share-intended files without printing them; no matches were found.

## Remaining exit item

Desktop and phone-width visual smoke checks remain pending because no browser was connected to the development session. Run `streamlit run app.py`, open the local URL at a typical desktop width and a phone width, and confirm that metrics and record cards stack legibly and the Plotly chart remains usable.

Do not begin Phase 2 until this viewport check is completed and the Phase 1 exit criteria are accepted.
