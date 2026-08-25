# Fantasy History Analyzer — Python MVP Development Plan

## 1. Confirmed scope

Fantasy History Analyzer is a private, read-only Streamlit web application for exploring ESPN fantasy football league `78212237`.

- Scoring: PPR
- Seasons: 2019 through the latest available season
- Initial audience: The league owner and members given access
- Application login: Out of scope
- League support: One private ESPN league
- Language and UI: Python and Streamlit
- Storage: Local JSON, Parquet, and YAML files; no database

The main experiences are league overview, all-time standings, manager history, head-to-head rivalries, seasons, playoffs, drafts, final rosters, records, and player-value analysis.

## 2. Product principles

1. Correctness comes before novelty. Every result must be traceable to source data and a documented formula.
2. Keep the MVP simple. Do not add a database, custom frontend, accounts, or distributed services.
3. Model managers separately from ESPN teams so renames and changing IDs do not split careers.
4. Keep importing, normalization, analytics, and presentation in separate Python modules.
5. Cache ESPN history locally instead of fetching it during normal page loads.
6. Explain boom, bust, sleeper, expected-win, and luck calculations in the UI.
7. Never expose ESPN credentials through Git, cached data, logs, or the browser.

## 3. Success criteria

The MVP is complete when a league member can:

- View accurate standings, champions, playoff results, and records for every available season since 2019.
- See a combined career profile for each real manager, including renamed teams.
- Compare any two managers and inspect all historical matchups.
- Browse all available drafts and final rosters.
- Trace league records to their underlying season or matchup.
- Understand why a pick is classified as a boom, bust, or sleeper.
- Refresh cached history without damaging the last valid dataset.
- Run the app locally using documented commands.
- Use the important pages on desktop and mobile.

## 4. Non-goals

- PostgreSQL or another database
- User accounts or role-based access
- Multiple leagues or fantasy platforms
- Editing ESPN lineups or league settings
- Live scoring or a live draft room
- Betting, projections, or lineup advice
- Full trade and waiver evaluation
- AI recaps or chat historian
- Native mobile applications
- Public indexing of private league data

## 5. Architecture

```text
Private ESPN Fantasy API
          |
          v
Server-side Python importer
          |
          +------> data/raw/*.json
          |        Immutable ESPN snapshots
          v
Validation and normalization
          |
          +------> data/processed/*.parquet
          |        Clean analysis tables
          v
Pure Python analytics
          |
          +------> data/derived/*.parquet
          |        Optional calculated caches
          v
Streamlit pages
Tables, filters, charts, and comparisons
```

This fits a single league because the dataset is small, there are no concurrent edits, and pandas can load the relevant history into memory. The module boundaries also preserve a path to PostgreSQL or a different frontend later.

## 6. Technology choices

- Python 3.12 or the latest compatible stable Python version
- Streamlit for the multipage interface
- pandas for transformations and analytics
- PyArrow-backed Parquet files for normalized data
- Plotly for interactive charts
- Pydantic for configuration and boundary validation
- `requests` or `httpx` for ESPN requests
- PyYAML for manager identity configuration
- pytest for automated tests

Exact versions will be pinned during project setup after compatibility checks.

Parquet is preferred over CSV for internal tables because it preserves types, handles nulls reliably, loads quickly, and produces smaller files. CSV may still be offered as an export format.

## 7. Project structure

```text
Fantasy_History_Analyzer/
|-- app.py
|-- pages/
|   |-- 1_Overview.py
|   |-- 2_Standings.py
|   |-- 3_Managers.py
|   |-- 4_Rivalries.py
|   |-- 5_Seasons.py
|   |-- 6_Drafts.py
|   `-- 7_Records.py
|-- fantasy_history/
|   |-- config.py
|   |-- espn_client.py
|   |-- importer.py
|   |-- validation.py
|   |-- normalization.py
|   |-- identities.py
|   |-- standings.py
|   |-- rivalries.py
|   |-- records.py
|   |-- draft_value.py
|   |-- data_access.py
|   `-- formatting.py
|-- data/
|   |-- raw/
|   |-- processed/
|   |-- derived/
|   `-- config/
|       `-- managers.example.yaml
|-- scripts/
|   |-- import_history.py
|   |-- rebuild_processed.py
|   `-- validate_data.py
|-- tests/
|   `-- fixtures/
|-- .env.example
|-- .gitignore
|-- pyproject.toml
|-- README.md
`-- DEVELOPMENT_PLAN.md
```

The exact number of modules can change, but the boundaries between ESPN access, normalized data, calculations, and UI should remain.

## 8. File-based data design

### Raw snapshots

Store original ESPN responses by season:

```text
data/raw/2019/league.json
data/raw/2019/draft.json
data/raw/2019/matchups.json
data/raw/2019/rosters.json
...
data/raw/2026/league.json
```

Each season also receives a manifest containing league ID, season, fetch time, importer version, source checksums, coverage, and warnings.

Requirements:

- Never store authentication cookies in snapshots.
- Write refreshed output to temporary files and validate it before replacement.
- Preserve the previous valid snapshot after any failed refresh.
- Treat raw snapshots as immutable inputs for rebuilding processed data.
- Ignore private raw and processed data in Git by default.

### Processed tables

Normalization produces:

```text
data/processed/seasons.parquet
data/processed/managers.parquet
data/processed/season_teams.parquet
data/processed/matchups.parquet
data/processed/team_scores.parquet
data/processed/playoff_results.parquet
data/processed/players.parquet
data/processed/drafts.parquet
data/processed/draft_picks.parquet
data/processed/roster_snapshots.parquet
data/processed/roster_players.parquet
```

Every processed row should retain enough source keys to trace it to a season and raw record.

### Derived data

Calculations can initially run in memory. Frequently reused or expensive results may be saved as:

```text
data/derived/manager_seasons.parquet
data/derived/manager_careers.parquet
data/derived/head_to_head.parquet
data/derived/record_holders.parquet
data/derived/player_values.parquet
```

Derived files must record the source checksum and calculation version so stale results can be detected and rebuilt.

## 9. Manager identity mapping

ESPN teams are season-specific, so a YAML file will define canonical real managers:

```yaml
managers:
  manager_key:
    display_name: "Manager Name"
    espn_member_ids:
      - "{REDACTED-ESPN-ID}"
    season_team_ids:
      2019: 4
      2020: 4
      2021: 7
```

Rules:

- ESPN IDs can suggest matches but ambiguous people must not be silently merged.
- YAML overrides are the final authority and survive every reimport.
- Team names appear as aliases under the canonical manager.
- Co-owners and ownership transfers are represented explicitly if they exist.
- Validation reports unresolved or multiply assigned teams.
- A graphical identity editor is not required for the MVP.

## 10. ESPN import strategy

ESPN's fantasy endpoints are unofficial and may change. Private and historical requests generally require ESPN session cookies.

The local `.env` will use:

```text
ESPN_LEAGUE_ID=78212237
ESPN_FIRST_SEASON=2019
ESPN_S2=private-value
ESPN_SWID={private-value}
```

The real `.env` must never be committed, and credentials should not be sent through chat.

### Import workflow

1. Load and validate server-only configuration.
2. Determine the latest available season.
3. Fetch one season at a time from 2019 onward.
4. Request available league, team, matchup, playoff, draft, and roster data.
5. Validate responses before promoting them to current snapshots.
6. Record coverage, warnings, row counts, and source-shape information.
7. Normalize snapshots into Parquet tables.
8. Apply canonical manager mappings.
9. Run integrity and reconciliation checks.
10. Rebuild derived analytics.
11. Expose the new dataset to Streamlit only after the full pipeline succeeds.

Supported modes:

- Import one season
- Import all seasons
- Refresh the latest season
- Rebuild processed files without ESPN access
- Recalculate analytics without reimporting data

The importer must handle current and historical response shapes, use bounded retries for temporary failures, detect invalid credentials, and never contact ESPN on each Streamlit page load.

## 11. Application pages

### Overview

- League age, seasons, matchups, and total points
- Most recent champion and championship leaders
- Best all-time record
- Highest and lowest weekly scores
- Closest game and largest blowout
- Champions timeline and rivalry spotlight
- Data freshness and coverage

### All-time standings

- Wins, losses, ties, and win percentage
- Points for, points against, and point differential
- Championships, runner-up finishes, and playoff appearances
- Regular-season and playoff records
- Average, best, and worst finish
- Seasons played
- Expected wins and luck differential
- Sorting, filtering, and CSV download

### Manager profiles

- Career summary and team-name history
- Season results and finishes
- Points and record trends
- Head-to-head opponent table
- Nemesis and favorite opponent
- Draft tendencies and value metrics
- Records held

### Rivalries

- League-wide head-to-head matrix
- Two-manager comparison
- Overall, regular-season, and playoff records
- Total points, averages, and margins
- Longest streak, biggest win, closest game, and highest-scoring meeting
- Chronological matchup history and rivalry lead over time

### Seasons

- Regular-season and final standings
- Playoff bracket or reconstructed results
- Weekly schedule and scores
- Draft and final rosters
- Season leaders, awards, and records
- Explicit unavailable-data notices

### Drafts

- Draft board by round and team
- Searchable pick history
- Player history across seasons
- Position allocation by manager and round
- League-specific average draft position
- Repeated-player and favorite-player analysis
- Boom, bust, sleeper, and surplus-value results
- Draft report cards

### Records

- Highest and lowest weekly scores
- Largest win and closest result
- Most points in a loss and fewest in a win
- Highest combined matchup score
- Best and worst season records
- Season scoring records
- Longest streaks
- Championships, playoff wins, and appearances
- Filters and source details

## 12. Analytics definitions

All calculations distinguish regular season, playoffs, and combined results.

- **Win percentage:** `(wins + 0.5 * ties) / completed games`
- **Point differential:** Points for minus points against
- **Average finish:** Mean official final placement across seasons played
- **Playoff appearance:** Entry into the championship bracket, excluding consolation play
- **Championship:** Winner of the championship playoff bracket
- **Streak:** Consecutive completed matchups with the same result

Season-spanning streak behavior must be documented and applied consistently.

### Expected wins and luck

For each scoring period, compare every team's score with all other active teams:

- **All-play wins:** Number of other teams the score would have beaten
- **Expected-win share:** All-play wins divided by possible opponents, with half credit for ties
- **Season expected wins:** Sum of weekly expected-win shares
- **Luck differential:** Actual wins minus expected wins

This estimates schedule fortune, not injuries or managerial skill.

### Draft value

1. Measure cost using overall pick and round.
2. Measure production using the most reliable scoring data available from ESPN.
3. Calculate position-adjusted value from league lineup settings and a replacement baseline.
4. Build expected-value curves from the league's draft history by pick range and position.
5. Calculate surplus as actual position-adjusted value minus expected value.
6. Normalize within each season so schedule or scoring changes do not distort comparisons.

Exact thresholds are selected only after inspecting the 2019-present distribution:

- **Boom:** Drafted player above the documented surplus-value threshold
- **Bust:** Drafted player below the documented low-value threshold
- **Sleeper:** Late-round or undrafted player producing starter-level adjusted value
- **Steal rate:** Eligible booms or sleepers divided by eligible selections
- **Bust rate:** Eligible busts divided by eligible selections

The UI must show the pick, expected value, actual value, positional baseline, surplus, threshold, and formula version. The MVP must not guess injury status without a reliable separate source.

## 13. Performance and caching

- Load Parquet through cached data-access functions.
- Cache pure calculations using dataset and formula versions.
- Invalidate caches when source manifests change.
- Use Streamlit session state for appropriate filters.
- Use URL query parameters for shareable manager, season, and rivalry selections where supported.
- Never load raw JSON during normal page rendering.
- Precompute expensive pairwise or all-time calculations only when needed.

## 14. Security, privacy, and deployment

Required controls:

- Store ESPN credentials only in local or deployment secrets.
- Commit only placeholder names in `.env.example`.
- Ignore `.env`, raw snapshots, private processed data, and temporary imports in Git.
- Do not add a browser form for ESPN cookies.
- Redact cookies, headers, and private response fields from logs.
- Discard unnecessary personal data such as email addresses.
- Do not expose raw ESPN responses through Streamlit.
- Do not expose an unprotected remote data-refresh action.

No application login means anyone with an unprotected deployed URL may see the league history. Before deployment, choose local-only use, platform-level access protection, or an unlisted URL accepted by the league.

Many hosting environments use temporary filesystems. Therefore:

- Treat deployed data files as read-only.
- Run imports locally and deploy processed data only if its privacy is acceptable.
- Do not assume a hosted refresh will survive a restart.
- Add object storage or a database later if persistent remote refresh becomes necessary.

## 15. Development phases

### Phase 0 — ESPN feasibility and audit

- Configure secrets locally.
- Fetch redacted samples for 2019, a middle season, and the latest season.
- Inventory settings, members, teams, schedules, playoffs, drafts, lineups, and rosters.
- Confirm PPR and lineup settings for each season.
- Document response-shape differences and a season coverage matrix.

Exit when early and recent seasons fetch successfully, secrets are absent from saved data, and unsupported fields are known.

### Phase 1 — Project foundation

- Initialize Python tooling, modules, pages, data directories, and tests.
- Configure Python formatting, linting, optional static type checks, and pytest.
- Add secret validation and redaction.
- Create safe fixtures and a recognizable Streamlit overview.

Exit when the app runs locally, tests pass, fixtures power the preview, and private files are ignored.

### Phase 2 — Import and normalization

- Build ESPN adapters and response validation.
- Add atomic snapshots and manifests.
- Normalize all supported entities into Parquet.
- Add single-season, full-history, rebuild, and validation scripts.
- Add integrity checks and regression fixtures.

Exit when all seasons import, repeated imports are equivalent, and failed refreshes preserve valid data.

### Phase 3 — Manager reconciliation

- Suggest identity mappings from ESPN identifiers.
- Create the canonical YAML mapping.
- Handle renames, changed IDs, co-owners, and ownership transfers.
- Validate unresolved and conflicting mappings.

Exit when every team is deliberately resolved or flagged and overrides survive rebuilding.

### Phase 4 — Analytics engine

- Implement standings, playoffs, head-to-head, margins, streaks, expected wins, luck, and records.
- Version formulas and retain source references.
- Test ties, byes, missing weeks, irregular playoffs, and season boundaries.

Exit when selected seasons match ESPN, pairwise totals reconcile, and every record is traceable.

### Phase 5 — Core Streamlit experience

- Build Overview, Standings, Managers, Rivalries, Seasons, and Records.
- Add filters, charts, downloads, coverage notices, and explanations.
- Check keyboard operation and common phone layouts.

Exit when all core journeys work and missing data is never silently treated as zero.

### Phase 6 — Draft and roster analytics

- Build draft board, pick history, player history, tendencies, and final rosters.
- Develop expected draft-value curves and normalized surplus value.
- Set documented boom, bust, and sleeper thresholds.
- Add explainable report cards.

Exit when sampled drafts and rosters match ESPN and every classification is reproducible.

### Phase 7 — Validation and release

- Profile calculations and finalize caching.
- Run import, analytics, and UI tests.
- Audit selected careers, rivalries, drafts, playoffs, and records manually.
- Review privacy, secrets, output files, and logs.
- Document setup, refresh, backup, and expired-cookie procedures.
- Decide on local-only or protected deployment.

Exit when the critical flows pass, secrets remain private, and setup and recovery are documented.

## 16. Ordered implementation checklist

1. Initialize Python and Streamlit tooling.
2. Build the page shell and fixture-based overview.
3. Add secret configuration, `.gitignore`, and redaction.
4. Fetch and redact representative ESPN samples.
5. Complete the source coverage matrix.
6. Define snapshot, manifest, and Parquet schemas.
7. Implement safe snapshot writing.
8. Implement ESPN adapters and validation.
9. Normalize league, season, member, and team data.
10. Normalize matchups, scores, and playoffs.
11. Normalize drafts, players, lineups, and rosters.
12. Add import, rebuild, and validation scripts.
13. Create canonical manager mappings.
14. Verify identities before career aggregation.
15. Implement and test standings and records.
16. Implement and test rivalries and expected wins.
17. Build Overview and Standings.
18. Build Manager Profiles.
19. Build Rivalries and the matchup matrix.
20. Build Seasons, Playoffs, and Records.
21. Build Draft and Final Roster history.
22. Establish draft-value distributions.
23. Add boom, bust, sleeper, and report-card metrics.
24. Complete caching, accessibility, responsive, and privacy checks.
25. Reconcile real data and run end-to-end verification.
26. Document local operation and refresh procedures.
27. Decide whether to remain local or use protected hosting.

## 17. Acceptance tests

| Area | Minimum acceptance test |
| --- | --- |
| Import | Import 2019 through latest twice and confirm equivalent output. |
| Recovery | Fail one refresh and retain the previous valid snapshot. |
| Rebuild | Reproduce processed and derived files from raw snapshots without ESPN access. |
| Identity | Rename a fixture team across seasons and retain one manager career. |
| Standings | Compare at least two seasons manually with ESPN. |
| Playoffs | Verify champion, runner-up, teams, and rounds for every season. |
| Rivalries | Hand-calculate one long-running matchup history. |
| Records | Trace sampled records to exact processed source rows. |
| Expected wins | Hand-calculate one scoring period, including a tie if available. |
| Drafts | Compare one early and one recent complete draft board. |
| Rosters | Verify the documented final-roster definition for sample seasons. |
| Player value | Reproduce several classifications from displayed inputs. |
| Cache | Change a manifest or formula version and rebuild stale results. |
| Privacy | Find no credentials in Git, shared files, UI output, or logs. |
| Responsive UI | Complete primary journeys on phone and desktop widths. |

## 18. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| ESPN changes its unofficial API | Isolate the client, retain snapshots, validate shapes, and preserve good data. |
| ESPN cookies expire | Detect authentication errors and document secret replacement. |
| Older seasons have less detail | Maintain coverage metadata and explicit unavailable states. |
| Team IDs do not equal managers | Use validated canonical YAML mappings. |
| Co-ownership distorts records | Represent it explicitly and agree on attribution. |
| Refresh partially overwrites a file | Validate temporary output and replace atomically. |
| Derived files become stale | Track source checksums and formula versions. |
| Final roster is ambiguous | Define and display the exact snapshot point. |
| Draft labels compare positions unfairly | Use position-adjusted and season-normalized value. |
| Injuries are mislabeled | Do not infer injury context from production alone. |
| Hosted files disappear after restart | Import locally or add persistent storage later. |
| No login exposes league history | Stay local or use deployment-level protection. |
| Streamlit limits later UI customization | Keep analytics independent of presentation. |

## 19. Future migration path

If the app later needs persistent hosted refreshes, many concurrent users, multiple leagues, or richer administration:

1. Load normalized Parquet tables into PostgreSQL.
2. Replace file-backed functions in `data_access.py` with database queries.
3. Retain the ESPN importer, normalization rules, identities, and analytics formulas.
4. Move imports into protected server jobs.
5. Keep Streamlit or replace only the UI with Next.js.

The Python MVP is therefore a first version of the durable analytics core, not disposable work.

## 20. Deferred decisions

- Community ESPN client versus direct validated HTTP calls
- Exact availability and definition of final rosters
- Direct playoff data versus bracket reconstruction
- Boom, bust, and sleeper thresholds
- Co-owner attribution, if applicable
- In-memory versus persisted derived tables
- Local-only versus protected deployment
- Whether private processed data can be bundled for deployment

## 21. Approval gate

This document defines the Python, Streamlit, and file-based MVP. Project initialization, dependency installation, ESPN access, and feature implementation begin only after explicit approval of this revised plan.
