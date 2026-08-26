# Phase 4 — analytics engine status

Updated: 2026-08-26

Status: **complete; analytics bundle promoted and exit criteria verified**

The user explicitly authorized Phase 4 development and subsequently confirmed the generated Phase 3 identity suggestions. The private canonical mapping and real manager-level analytics bundle are now promoted locally. No private manager identities are present in tracked artifacts. The Phase 1 desktop/phone smoke check remains release debt.

## Implemented

- Normalization version `phase2.v2` retains ESPN playoff seed, official/calculated final rank, official regular-season W-L-T and points, current matchup period, final scoring period, and manifest-backed active-season state.
- A completed-matchup fact table excludes byes, missing scores, and undecided results while preserving exact source keys.
- Explicit `regular_season`, `championship_playoff`, `consolation`, `combined`, and `unknown` segment contracts.
- Team-season standings with wins, losses, ties, win percentage, points, and point differential.
- Source-backed final placement, champion, runner-up, and championship-bracket appearance results. Active-season finishes remain unavailable.
- Weekly all-play expected-win shares, season expected wins, actual wins, and luck differential with tie credit and reduced comparison pools.
- Manager-season and career attribution using canonical identities, with co-owner and transfer rows visibly marked under policy `shared-credit.v1`.
- Career average/best/worst finish, expected wins, luck differential, championship, runner-up, playoff-appearance, and playoff W-L-T totals.
- Directed head-to-head totals, points, average margin, biggest win, closest margin, and highest-scoring meeting, with pairwise symmetry validation.
- W/L/T streaks that span season boundaries, ignore absent bye rows, and can be reset by an explicit coverage break.
- Source-traceable score, matchup, season, streak, championship, runner-up, playoff-win, and playoff-appearance record holders with tied-holder retention and explicit unavailable rows.
- An atomic `scripts/rebuild_analytics.py` pipeline with formula, source, identity-manifest, and attribution-policy checksum invalidation.
- File-backed analytics accessors for later Streamlit pages.

## Automated verification

Synthetic tests cover ties, byes, missing scores, incomplete games, competition splits, multi-season streaks, explicit coverage breaks, reduced all-play pools, renamed/changed team IDs, shared ownership, rivalry symmetry, tied records, source traceability, equivalent rebuilds, checksum invalidation, incomplete identity rejection, and failed-build rollback.

The repository currently passes 45 pytest tests, Ruff formatting/linting, and mypy for application and script code.

## Share-safe local-data evidence

The ignored 2019–2026 dataset was rebuilt offline and validated after the source-contract amendment:

- 8 snapshots and 11 processed tables validate;
- 7 seasons are complete and the active 2026 season is partial;
- all 84 completed team-seasons match ESPN's retained official W-L-T records;
- all 84 completed team-seasons match ESPN's retained points-for and points-against totals;
- calculated actual wins used by luck match all 84 official completed team-season win totals;
- all 7 completed seasons have exactly one source-backed champion and runner-up;
- championship-bracket entrant counts match ESPN's configured playoff-team count in all 7 completed seasons; and
- a full team-level dry run produced 10 analytics tables and exactly one active-season coverage warning.
- the complete private identity bundle contains 20 canonical careers, 320 directed head-to-head rows, 23 record-holder rows, and 4 careers with explicit shared attribution; and
- the promoted analytics manifest is current after a repeated rebuild.

No private names or identifiers are recorded in this document or tracked test data.

## Exit evidence

The league owner confirmed completion of the required manual verification on 2026-08-26, including representative early/recent standings, completed championship brackets, rivalry and expected-win checks, and sampled source traces.

The final automated exit run confirms:

- all 45 pytest tests pass;
- Ruff formatting and linting pass;
- mypy passes for application and script code;
- all 8 snapshots and 11 processed tables validate;
- repeated identity and analytics rebuilds are equivalent;
- the analytics manifest matches the current formula, source, identity, and attribution-policy checksums;
- all available record rows retain processed source keys;
- the active 2026 season remains explicitly partial; and
- configured ESPN secret values appear in zero tracked files.

Phase 4's exit criteria are satisfied. Phase 5 may begin when explicitly authorized.
