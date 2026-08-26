# Phase 4 handoff — analytics engine

Prepared: 2026-08-26

Status: **implementation guidance prepared; Phase 3 exit gate remains pending**

Source of truth: `DEVELOPMENT_PLAN.md`, `AGENTS.md`, and `docs/PHASE_3_STATUS.md`

Phase 4 must not begin until the ignored canonical mapping resolves all 96 season teams with zero conflicts and the five multi-owner evidence rows are deliberately classified. The earlier Phase 1 desktop/phone smoke check is still release debt, but it does not change the analytics design.

## Inputs available

Phase 2 provides ignored, source-traceable Parquet tables:

- `seasons.parquet` — league/season settings, regular-season period count, playoff-team count, active-season state, and source keys;
- `season_teams.parquet` — season-specific teams and owner evidence;
- `matchups.parquet` — matchup IDs, periods, teams, scores, ESPN winner, playoff tier, consolation/bye flags, and source keys;
- `team_scores.parquet` — team/opponent scoring-period rows, points, result when available, and source keys;
- `playoff_results.parquet` — ESPN playoff-tier rows and winners;
- raw snapshot manifests — source checksums, coverage states, active-season warnings, and importer versions.

Phase 3 adds ignored derived identity inputs:

- `data/derived/identities/canonical_managers.parquet`;
- `data/derived/identities/manager_team_assignments.parquet`; and
- `data/derived/identities/manifest.json`, containing identity, mapping, and relevant processed-source checksums.

Do not read raw JSON during analytics or normal Streamlit rendering. Do not mutate processed or identity tables.

## Phase 3 prerequisite and attribution policy

Run this before any manager-level aggregate is built:

```bash
python scripts/validate_identities.py --require-complete
```

The command must report 96 resolved season teams and zero conflicts. The identity manifest must match the current mapping and processed input checksums.

Co-owned teams and ownership transfers require an explicit analytics policy:

- team-level league totals remain authoritative and count each ESPN team result exactly once;
- manager-level rows must retain `resolution_type` and a shared-attribution flag;
- co-owner credit may be shown for each named manager, but shared rows must never be summed to produce league totals;
- an ownership transfer must not be divided by matchup or scoring period unless the mapping contains reviewed effective-period boundaries;
- without effective-period evidence, expose the season-team result as shared/transfer attribution rather than guessing which manager owned individual games.

Record the selected policy and its version before calculating careers, rivalries, streaks, or records.

## Required source-sufficiency audit

Before implementing formulas, confirm every required output can be derived from retained normalized fields. In particular, audit whether official final placement, playoff seed, ESPN standings records, and championship-round identification are sufficiently retained.

If an official ESPN field is present in validated snapshots but missing from the processed contracts, amend Phase 2 normalization to preserve the field and its source key. Rebuild deterministically and add regression coverage. Do not infer an official finish or playoff seed from points, team ID, or incomplete brackets.

For unavailable historical fields or the active 2026 season, return an explicit unavailable/partial state rather than zero or a guessed result.

## Approved Phase 4 scope

- Team-season and canonical-manager career standings.
- Regular-season, championship-playoff, consolation, and combined records as separate views.
- Championship, runner-up, playoff appearance, and finish results when supported by source evidence.
- Pairwise head-to-head results, margins, streaks, and chronological history.
- Weekly all-play expected wins and luck differential.
- Source-traceable league and manager records.
- Versioned formulas and derived-cache invalidation.

Draft value, boom/bust/sleeper labels, draft report cards, and UI page construction remain Phases 6 and 5 respectively.

## Calculation contracts

### Completed matchup

A matchup is completed only when both participating teams and both scores are present and ESPN supplies a completed winner/result, or a documented validated completion rule establishes the same fact. Ignore byes for wins, losses, ties, margins, rivalry meetings, and streaks. Never treat missing scores as zero.

### Competition segment

Assign each row one explicit segment:

- `regular_season` — not marked as a playoff or consolation matchup;
- `championship_playoff` — in the championship bracket and not consolation;
- `consolation` — explicitly marked consolation;
- `unknown` — source evidence is insufficient.

Combined records may include regular season and championship playoffs only by default. Consolation results must remain separately selectable and must not silently affect playoff records.

### Win percentage and point differential

- Win percentage: `(wins + 0.5 * ties) / completed_games`.
- Point differential: points for minus points against.
- Return unavailable when there are no completed eligible games; do not return zero percent.

### Playoff results

- A playoff appearance means entry into the championship bracket, excluding consolation play.
- Champion and runner-up must come from a validated championship-final result or an official retained ESPN finish.
- Multi-period or irregular brackets must group the correct round/series before selecting a winner.
- Active or incomplete brackets remain partial and produce no champion.

### Expected wins and luck

Calculate all-play results within each eligible regular-season scoring period:

1. Select active teams with an available score for that scoring period.
2. Compare each score with every other active score exactly once.
3. Award one all-play win for a lower opponent score and one-half for a tie.
4. Expected-win share is `(all_play_wins + 0.5 * all_play_ties) / possible_opponents`.
5. Season expected wins are the sum of weekly expected-win shares.
6. Luck differential is actual regular-season wins minus expected wins.

Require at least two active scored teams. Missing teams reduce the documented comparison pool; they are not assigned zero. Validate uniqueness at `(league_id, season, scoring_period, source_team_id)` before calculating.

### Head-to-head and margins

- Count each completed, non-bye ESPN matchup once.
- Preserve regular-season, championship-playoff, consolation, and combined splits.
- Margin is the selected manager/team score minus the opponent score.
- Pairwise totals must reconcile from either manager perspective with wins/losses reversed, ties equal, and points swapped.
- Shared ownership must follow the versioned attribution policy and remain marked in output.

### Streaks

- A streak is consecutive completed eligible matchups with the same result.
- Byes do not extend or break a streak.
- Missing/unavailable matchup coverage breaks the ability to claim continuity and must be flagged.
- Career streaks may span the offseason when the next known eligible matchup is complete; the offseason itself neither extends nor breaks the streak.
- Regular-season, championship-playoff, consolation, and combined streaks are calculated separately.

### Records

Every record row must retain enough source fields to locate the exact processed input: season, source matchup/team IDs where applicable, source file, and source row key. Tied record holders must all be retained. A record category with no eligible rows is unavailable, not zero.

Initial categories:

- highest and lowest weekly score;
- largest win and closest result;
- most points in a loss and fewest points in a win;
- highest combined matchup score;
- best and worst season records;
- season scoring highs/lows;
- longest win/loss/tie streaks;
- championships, runner-up finishes, playoff wins, and playoff appearances.

## Derived contracts and versioning

Calculations should remain pure pandas functions. Persist only reused or expensive outputs, with stable schemas such as:

- `manager_seasons.parquet`;
- `manager_careers.parquet`;
- `head_to_head.parquet`;
- `expected_wins.parquet`; and
- `record_holders.parquet`.

Each persisted analytics bundle must include:

- analytics schema/formula version;
- processed source checksums;
- identity manifest checksum;
- attribution-policy version;
- row counts and coverage warnings.

Build into staging, validate the complete bundle, and atomically promote it. A formula, source, mapping, or attribution-policy checksum change invalidates the bundle.

## Recommended implementation sequence

1. Complete the Phase 3 private mapping and attribution decisions.
2. Audit source sufficiency for official finishes, seeds, records, and playoff finals.
3. Define typed analytics schemas, formula versions, coverage vocabulary, and source-key requirements.
4. Build a canonical completed-matchup fact table with segment classification and identity attribution.
5. Implement team-season standings and reconcile representative seasons.
6. Implement championship/playoff results, including irregular and multi-period fixtures.
7. Implement manager-season and career aggregates without double-counting shared teams.
8. Implement pairwise head-to-head, margins, rivalry history, and streaks.
9. Implement weekly expected wins and season luck.
10. Implement traceable record categories with tied-holder handling.
11. Add atomic derived rebuild/validation commands and checksum invalidation.
12. Reconcile early and recent completed seasons plus the partial active season before declaring Phase 4 complete.

## Required automated tests

- Wins, losses, ties, win percentage, and point differential.
- Byes and missing scores excluded without becoming losses or zeroes.
- Missing weeks and incomplete active-season rows remain partial/unavailable.
- Regular-season, championship-playoff, consolation, and combined splits.
- Standard, irregular, and multi-period playoffs; champion and runner-up traceability.
- Team rename and changed source team ID aggregating under one canonical manager.
- Co-owner/transfer attribution without double-counting league totals.
- Rivalry symmetry, ties, margins, closest games, and chronological ordering.
- Streaks across byes, missing coverage, playoffs, and season boundaries.
- Hand-calculated expected wins, including equal scores and a reduced comparison pool.
- Record ties and exact source-row traceability.
- Equivalent rebuilds and stale-cache invalidation after source, mapping, or formula changes.
- Failed derived rebuild preserving the previous valid bundle.

## Manual reconciliation and exit gate

Before Phase 5:

- manually compare at least one early and one recent completed season with ESPN;
- verify champion, runner-up, championship bracket, and playoff entrants for every completed season;
- hand-calculate one long-running rivalry from processed matchups;
- hand-calculate one expected-win scoring period, including a tie when available;
- trace sampled records to exact processed source rows;
- prove pairwise results reconcile in both directions;
- verify the active 2026 season remains explicitly partial; and
- confirm no names, member identifiers, or private derived data entered tracked fixtures, documentation, logs, or Git.

Phase 4 exits only when selected standings match ESPN, every completed-season playoff result is reconciled, pairwise totals balance, records are traceable, formula/checksum invalidation works, and the full test/format/lint/type/privacy suite passes.
