# Phase 5 handoff — core Streamlit experience

Prepared: 2026-08-26

Status: **ready to begin after explicit authorization**

Source of truth: `DEVELOPMENT_PLAN.md`, `AGENTS.md`, and `docs/PHASE_4_STATUS.md`

Phases 0–4 are complete. Phase 5 may replace the synthetic Phase 1 preview with the real, read-only Streamlit experience. Draft value, boom/bust/sleeper classifications, report cards, and the full draft/final-roster experience remain Phase 6.

## Ready inputs

Normal Streamlit rendering must read only processed, identity, and analytics files—never ESPN or raw response JSON.

Processed tables under ignored `data/processed/`:

- `seasons.parquet` — season state, schedule settings, playoff size, and source traceability;
- `season_teams.parquet` — team names, aliases, official records, seeds, and final ranks;
- `matchups.parquet` and `team_scores.parquet` — normalized matchup and weekly score sources; and
- the remaining draft/roster tables, reserved primarily for Phase 6.

Identity tables under ignored `data/derived/identities/`:

- `canonical_managers.parquet`; and
- `manager_team_assignments.parquet`.

Analytics tables under ignored `data/derived/analytics/`:

- `matchup_facts.parquet`;
- `team_standings.parquet`;
- `season_finishes.parquet`;
- `weekly_expected_wins.parquet`;
- `expected_wins.parquet`;
- `manager_seasons.parquet`;
- `manager_careers.parquet`;
- `head_to_head.parquet`;
- `streaks.parquet`; and
- `record_holders.parquet`.

The analytics manifest records formula, schema, attribution-policy, processed-source, and identity-manifest versions plus row counts and coverage warnings. Call `analytics_bundle_is_current()` before presenting real analytics. A missing or stale bundle must produce an actionable unavailable state, never an automatic rebuild or an ESPN request.

## Required pages and primary journeys

### Overview

- League age, completed and active seasons, completed matchups, and total points.
- Latest completed champion plus championship leaders.
- Best all-time record, weekly scoring extremes, closest game, and largest blowout.
- Champions timeline, rivalry spotlight, formula version, coverage warnings, and data readiness.
- Do not label active 2026 results as final.

### Standings

- Career wins, losses, ties, win percentage, points, point differential, seasons played, championships, runner-up finishes, playoff appearances, playoff wins, average/best/worst finish, expected wins, and luck.
- Separate regular-season, championship-playoff, consolation, and combined views.
- Sortable/filterable display and a CSV download generated from the currently filtered table.
- Shared-attribution careers must be visibly marked and must not be summed as league totals.

### Managers

- Canonical manager selector and shareable query parameter.
- Career summary, team-name history, season finishes, records/points trends, expected wins and luck.
- Opponent table, nemesis/favorite opponent, playoff history, and records held.
- Treat unavailable finish, luck, or season values as unavailable—not zero.

### Rivalries

- Directed head-to-head matrix and two-manager selector with query parameters.
- Combined, regular-season, championship-playoff, and consolation filters.
- Wins/losses/ties, points, margins, closest game, biggest win, highest-scoring meeting, and streaks.
- Chronological history can be built by joining `matchup_facts` to reviewed assignments with `attribute_matchup_facts()`; cache the pure result by analytics/identity manifest versions.
- Prevent selection of the same manager on both sides and preserve pairwise symmetry.

### Seasons

- Season selector defaulting to the latest available season.
- Official finish/seed, regular and playoff records, weekly schedule, scores, and championship-bracket results.
- Explicit partial notice for active 2026 and explicit unavailable notices for missing historical sections.
- Draft and final-roster links/placeholders may identify Phase 6 scope but must not invent incomplete features.

### Records

- Category and season filters, all tied holders, values, and readable source details.
- Score, matchup, season, streak, championship, runner-up, playoff-win, and playoff-appearance categories.
- A details expander may show season, matchup/team source identifiers, file, and row key; never expose ESPN member IDs, raw payloads, cookies, or request headers.

## UI and module boundaries

- Keep pages thin. Put reusable joins, filters, readiness checks, and cached reads in `fantasy_history/data_access.py` or presentation-specific helpers—not in analytics formula modules.
- Keep number/date/record formatting in `fantasy_history/formatting.py`.
- Use Plotly for interactive charts and pandas for transformations.
- Use `st.cache_data` only around file reads and pure presentation joins. Cache keys must change with the analytics and identity manifest checksums.
- Use session state for local filters and `st.query_params` for manager, season, and rivalry selections where practical.
- Do not add JavaScript, a custom API, a database, accounts, or an import/refresh button.
- The app remains local/private. Do not expose raw private files or assume hosted filesystem persistence.

## Data readiness and freshness

Implement one shared readiness boundary before individual pages load data:

1. Confirm required processed, identity, and analytics files exist.
2. Confirm the identity report is complete and conflict-free.
3. Confirm `analytics_bundle_is_current()`.
4. Surface analytics coverage warnings, especially active-season partial state.
5. If unavailable or stale, show the local commands needed to rebuild; do not rebuild during rendering.

The current analytics manifest records coverage warnings but not a user-facing fetch timestamp. Phase 5 must either propagate a share-safe freshness timestamp into a processed/derived manifest during an explicit offline rebuild or label freshness as unavailable. Do not read raw snapshots during page rendering and do not infer freshness from file modification time.

## Formula and attribution explanations

Every relevant page should expose concise expandable explanations:

- Win percentage: `(wins + 0.5 × ties) / completed games`.
- Expected-win share: all-play wins plus half of all-play ties divided by possible opponents.
- Luck: actual regular-season wins minus expected wins.
- Combined records: regular season plus championship playoffs; consolation excluded by default.
- Shared credit: confirmed co-owned teams credit each named manager, but shared rows are not summed for league-wide totals.
- Active or incomplete data: unavailable values remain null and are not converted to zero.

Display formula version `phase4.v1` and attribution policy `shared-credit.v1` where explanations or downloads depend on them.

## Accessibility and responsive requirements

- All controls need visible labels and usable keyboard focus/order.
- Do not communicate result or status using color alone.
- Tables must remain horizontally usable without truncating essential labels.
- Metric/card grids should collapse cleanly at common phone widths.
- Plotly charts need descriptive titles, axis labels, hover text, and readable legends.
- Avoid dense multi-column layouts on manager, rivalry, and season detail pages.
- Check common desktop and phone widths with the real page journeys before Phase 5 exits. This also closes the outstanding Phase 1 viewport debt.

## Required automated verification

- Readiness states for missing, stale, partial, and current analytics bundles.
- No page render calls ESPN, reads raw response JSON, or exposes a refresh action.
- Overview metrics reconcile with derived tables.
- Standings filters and CSV exports preserve nulls and selected segment semantics.
- Manager selection handles renamed teams and shared attribution.
- Rivalry selections remain symmetric and reject self-comparisons.
- Season pages keep active/incomplete results partial.
- Records retain tied holders and source details.
- Query-parameter selections handle invalid or unavailable values safely.
- Formatting helpers cover ties, null percentages/finishes, points, and signed luck/margins.
- App smoke tests cover every page with synthetic, share-safe temporary Parquet bundles.

## Manual exit gate

Before Phase 6:

- complete Overview, Standings, Managers, Rivalries, Seasons, and Records journeys on desktop and phone widths;
- verify keyboard access to navigation, filters, selectors, expanders, and downloads;
- reconcile displayed figures with the promoted Phase 4 tables;
- confirm missing/partial values never render as zero;
- confirm formulas and shared attribution are understandable from the UI;
- confirm no ESPN calls occur during rendering;
- confirm credentials, member IDs, raw responses, and private generated data remain absent from tracked artifacts and browser output; and
- run pytest, Ruff, mypy, analytics-current, and privacy checks.

Phase 5 exits only when all six core pages work with real local data, the primary journeys pass at desktop and phone widths, and the Phase 1 viewport debt is closed.
