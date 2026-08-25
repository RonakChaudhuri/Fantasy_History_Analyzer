# Fantasy History Analyzer — Repository Instructions

## Source of truth

- Read `DEVELOPMENT_PLAN.md` completely before planning or making project changes.
- Treat that document as the approved product, architecture, phase, security, and acceptance-test specification.
- If a request conflicts with the plan, point out the conflict before changing the architecture or scope.
- Do not begin a later development phase until the preceding phase's exit criteria are satisfied, unless the user explicitly changes the plan.

## Confirmed product scope

- Analyze private ESPN fantasy football league `78212237`.
- The league uses PPR scoring.
- Import seasons from 2019 through the latest available season.
- Support one league in the MVP.
- Do not build application accounts or a custom login system.

## Required MVP architecture

- Use Python for all project-authored application code.
- Use Streamlit for the web interface.
- Use pandas for transformations and analytics.
- Use Plotly for interactive charts unless the approved plan is revised.
- Store raw ESPN responses as JSON.
- Store normalized and derived tables as Parquet.
- Store manager identity mappings and manual corrections as YAML.
- Keep ESPN importing, normalization, identity resolution, analytics, data access, and UI in separate modules.

Do not introduce any of the following unless the user explicitly approves an architectural revision:

- JavaScript or TypeScript source code
- React or Next.js
- Node.js or npm tooling
- PostgreSQL, SQLite, or any other database
- A separate frontend/backend API architecture

Libraries such as Streamlit and Plotly may use browser technologies internally; do not add or maintain custom JavaScript for the MVP.

## ESPN data and secrets

- Keep `ESPN_S2` and `ESPN_SWID` in a local `.env` file or deployment secret store.
- Never ask the user to paste ESPN credentials into chat.
- Never commit secrets, display them in the UI, include them in cached data, or expose them in logs and errors.
- Commit only placeholder variable names in `.env.example`.
- Ignore `.env`, raw private snapshots, processed private league data, derived private data, and temporary import files in Git by default.
- Do not fetch ESPN during normal Streamlit page rendering; use the explicit import pipeline and cached files.
- Preserve the last valid snapshot when a refresh or validation step fails.
- Redact private or unnecessary member information from fixtures and shared artifacts.

## Data correctness

- Keep canonical managers separate from season-specific ESPN teams.
- Preserve manual YAML identity overrides across imports and rebuilds.
- Never silently merge ambiguous manager identities.
- Distinguish regular-season, playoff, and combined records.
- Treat missing or unavailable data as unavailable, not zero.
- Make derived results traceable to normalized source rows.
- Version formulas and invalidate derived caches when source data or calculation rules change.
- Do not guess injury status or other facts not supported by the imported data.
- Make boom, bust, sleeper, expected-win, luck, and report-card formulas visible and reproducible.

## Verification expectations

- Add pytest coverage for import parsing, normalization, identity mapping, standings, playoffs, rivalries, records, expected wins, and draft value.
- Include edge cases for ties, byes, missing weeks, irregular playoffs, team renames, and season boundaries.
- Verify repeated imports produce equivalent data without duplication.
- Verify a failed refresh does not corrupt the previous valid dataset.
- Manually reconcile representative early and recent seasons against ESPN before release.
- Check the main Streamlit journeys at desktop and phone widths.
- Confirm credentials do not appear in Git, generated files intended for sharing, browser output, or logs.

## Deployment boundary

- Local-only operation is acceptable for the MVP.
- Do not assume that files written on a hosted filesystem persist across restarts.
- Do not expose an unprotected remote import or refresh action.
- Before remote deployment, require an explicit decision between platform-level access protection and an accepted unlisted URL.
- Persistent hosted refreshes, multiple leagues, or concurrent editing require a separately approved storage architecture change.

