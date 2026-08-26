# Phase 6 handoff — draft and roster analytics

Prepared: 2026-08-26

Status: **design and input audit prepared; implementation remains gated by Phase 5 exit**

Source of truth: `DEVELOPMENT_PLAN.md`, `AGENTS.md`, `docs/PHASE_5_HANDOFF.md`, and `docs/PHASE_5_STATUS.md`

Phase 6 must not begin until the remaining Phase 5 desktop/phone, keyboard, displayed-value reconciliation, and browser privacy checks are completed or the user explicitly revises the phase gate. This document prepares the next implementation without changing that boundary.

## Approved Phase 6 scope

- Draft board by round and source team.
- Searchable pick and player history.
- Manager position allocation, repeated-player, and favorite-player tendencies.
- Completed-season final rosters with an explicit snapshot definition.
- League-specific expected-value curves, position-adjusted production, and season-normalized surplus value.
- Reproducible boom, bust, sleeper, steal-rate, bust-rate, and report-card outputs.
- Draft and roster integration on Drafts, Managers, and Seasons pages.

Trades, waiver evaluation, injury inference, projections, betting, lineup advice, and live draft functionality remain out of scope.

## Ready normalized inputs

The promoted private dataset currently contains:

| Input | Rows or coverage | Phase 6 use |
| --- | ---: | --- |
| `drafts.parquet` | 8 seasons | Draft state, completion timestamp, pick count |
| `draft_picks.parquet` | 1,560 picks | Pick cost, round, team, player, keeper, auction fields |
| `players.parquet` | 2,251 season-player rows | Player name, pro team ID, default position ID |
| `roster_snapshots.parquet` | 1,080 team snapshots | Snapshot type, week, coverage state, entry count |
| `roster_players.parquet` | 17,886 rows | Team/player membership, lineup slot, acquisition metadata |
| `season_teams.parquet` | 96 season teams | Team labels and source keys |
| reviewed identity assignments | 96/96 teams resolved | Canonical manager attribution |

Draft coverage is 192 picks per season from 2019–2024 and 204 picks per season in 2025–2026. The active 2026 draft is available, but production/value results must remain partial until the season completes.

Completed-season `season_roster` entry counts are 192, 198, 189, 190, 194, 197, and 206 for 2019–2025. The active 2026 season-roster snapshot is available-empty and must not be displayed as a final roster.

Weekly lineup coverage is unavailable for 2019–2021, complete at 204 team-week snapshots per season for 2022–2025, and partial at 168 snapshots for active 2026. This coverage difference must remain visible in roster and sleeper eligibility.

Every normalized input retains season and processed source keys. Normal Streamlit rendering must continue to read Parquet only, never raw ESPN JSON.

## Required source-sufficiency amendment

The current processed contracts do **not** retain player fantasy-point production. Raw roster and weekly-lineup entry structures contain `playerPoolEntry.appliedStatTotal` and player `stats` records with season, scoring period, stat source, split type, and applied totals, but their semantics and completeness have not yet been promoted into a normalized contract.

Before calculating draft value:

1. Verify which ESPN stat source represents actual versus projected scoring for completed and active seasons. Do not infer this from an undocumented numeric ID.
2. Determine whether each score is weekly or cumulative and prove that aggregation cannot double count it.
3. Add a source-traceable player-score table with, at minimum, league, season, scoring period or season-total scope, source player ID, stat-source/split identifiers, applied fantasy points, availability, source file, and source row key.
4. Rebuild deterministically and add manifest/checksum invalidation.
5. Measure drafted-player production coverage by season before making any player eligible for a value label.

The `mRoster` season snapshot covers final rostered players, not necessarily every drafted player who was dropped. Weekly lineups improve player coverage from 2022 onward but are unavailable for 2019–2021. If retained sources cannot provide actual full-season production for all drafted players, Phase 6 must either add a separately validated ESPN player-data import or mark affected picks/seasons ineligible. Missing production must never become zero.

## Final-roster contract to approve

Recommended MVP definition:

- A final roster is the `season_roster` snapshot explicitly imported after ESPN marks the season complete.
- It represents the roster returned by ESPN at that snapshot, not every player held during the season.
- Completed seasons with populated snapshots may be displayed after manual reconciliation.
- Active seasons, available-empty snapshots, and missing snapshots are unavailable—not empty final rosters.
- The UI must display snapshot type, coverage status, season state, and a concise definition.

Confirm this interpretation against representative early and recent ESPN rosters before using the label “final roster.” If the import timestamp is needed for user-facing freshness, propagate a share-safe timestamp into a processed or derived manifest; do not read raw manifests during rendering or infer freshness from file modification time.

## Draft-value calculation contract

All formulas must be pure pandas calculations, versioned, source-traceable, and displayed in the UI.

### Eligibility

- Draft cost requires a valid overall pick, round, source team, and player.
- Production requires validated actual scoring with documented season coverage.
- Active/incomplete seasons are excluded from final labels.
- Keepers and auction-cost rows must be separated when their cost is not comparable with ordinary snake-draft picks.
- A pick with unavailable production remains unavailable; it is not a bust.

### Cost and production

- Retain overall pick and round as the primary draft-cost evidence.
- Use ESPN-applied PPR fantasy points only after actual/projected and weekly/cumulative semantics are verified.
- Preserve raw position IDs internally and add one reviewed display mapping for positions and lineup slots.
- Do not infer injury status or explain low production using unsupported context.

### Position adjustment and replacement

- Derive season-specific starter demand from `lineup_slot_counts_json` and the number of active teams.
- Document how flex and superflex slots contribute to positional replacement ranks.
- Calculate one replacement baseline per season and position from eligible actual production.
- Position-adjusted value is actual production minus the documented replacement baseline.
- Return unavailable when the season/position pool cannot support a baseline.

### Expected value and surplus

- Build league-specific expected position-adjusted value from historical eligible picks by overall-pick range and position.
- Select bucket sizes or smoothing only after reporting sample sizes and distribution stability; avoid a curve that overfits 1,560 total picks.
- Surplus value is actual position-adjusted value minus expected value for the pick cost.
- Normalize surplus within each completed season before cross-season comparisons.
- Retain expected value, actual value, replacement baseline, raw surplus, normalized surplus, eligibility reason, and formula version on every row.

### Labels and report cards

- Choose boom, bust, late-round, sleeper, and starter-level thresholds only after inspecting the completed-season distributions.
- Store thresholds and formula versions in code and in the derived manifest.
- Show the exact threshold beside every classification.
- Undrafted sleeper eligibility requires sufficient acquisition/roster coverage and a documented attribution rule; 2019–2021 may remain unavailable.
- Steal and bust rates use eligible selections as their denominators, never all picks by default.
- Report-card grades must be reproducible from displayed component metrics and cannot hide unavailable picks inside a zero score.

## Recommended derived contracts

Build into staging, validate the complete set, and atomically promote it. Either extend the existing analytics bundle deliberately or use a separate versioned draft bundle with a manifest that references processed, identity, player-score, formula, threshold, and attribution checksums.

Suggested tables:

- `player_scores.parquet` — validated actual player production facts;
- `final_rosters.parquet` — completed-season roster membership and coverage;
- `draft_pick_values.parquet` — cost, production, baselines, expected value, surplus, labels, and source trace;
- `draft_tendencies.parquet` — canonical-manager position/round and repeated-player summaries;
- `draft_report_cards.parquet` — explainable manager-season components and grades.

Derived tables must retain source pick/player/team keys and enough source-row references to reproduce each displayed result.

## UI requirements

### Drafts page

- Season selector and availability notice.
- Draft board by round/team plus searchable pick table.
- Player history and repeated-player views.
- Position allocation by manager and round.
- Value table with eligibility, expected/actual/baseline/surplus fields, thresholds, and formula version.
- Explainable report cards and explicit partial/unavailable states.

### Existing pages

- Managers: draft tendencies, repeated/favorite players, eligible value rates, and report cards.
- Seasons: link to the selected draft and show the approved final-roster snapshot.
- Overview should remain focused; do not add draft cards unless they materially improve the primary journey.

Use the existing manifest-derived Streamlit cache boundary, session-state controls, and query-parameter callback pattern so selectors respond with one interaction.

## Required automated tests

- Draft board ordering for snake, keeper, and irregular pick counts.
- Source-team to canonical-manager attribution across renames and merged identities.
- Player-score actual/projected filtering and weekly/cumulative deduplication.
- Missing production remains null and ineligible rather than becoming zero or a bust.
- Position/lineup-slot mapping and season-specific flex replacement rules.
- Expected-value curve stability, sparse buckets, and season normalization.
- Boom, bust, sleeper, steal-rate, bust-rate, and report-card reproducibility.
- Active-season, missing-lineup, available-empty roster, and incomplete-draft states.
- Final-roster snapshot selection and definition.
- Equivalent rebuilds, checksum/threshold invalidation, and failed-build rollback.
- Draft/roster page smoke tests with share-safe synthetic Parquet bundles and denied network access.
- One-click query-linked selectors and null-preserving CSV downloads.

## Manual reconciliation and exit gate

Before Phase 7:

- compare one early and one recent complete draft board with ESPN;
- verify the approved final-roster definition for representative seasons;
- reproduce several value rows from source pick, player points, positional baseline, expected value, and surplus;
- inspect the completed-season distributions and approve classification thresholds;
- verify every label and report-card grade from displayed inputs;
- confirm unavailable early-season production and active-season rows are clearly labeled;
- complete Drafts, Managers, and Seasons journeys at desktop and phone widths with keyboard controls;
- confirm no credentials, member identifiers, raw responses, or private generated data enter tracked artifacts or browser output; and
- run pytest, Ruff, mypy, data validation, derived-currentness, and privacy checks.

Phase 6 exits only when sampled drafts and final rosters match ESPN, source sufficiency is documented by season, and every value classification and grade is reproducible without guessed production or injury context.
