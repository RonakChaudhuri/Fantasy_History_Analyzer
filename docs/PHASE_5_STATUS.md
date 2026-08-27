# Phase 5 — core Streamlit experience status

Updated: 2026-08-27

Status: **in progress; core journeys implemented, visual/manual exit gate pending**

## Implemented

- One shared readiness boundary checks required files, identity completeness, analytics currency, manifest-versioned cache invalidation, and partial-coverage warnings.
- Overview uses the promoted analytics for league totals, latest completed champion, championship leaders, records, champions timeline, and rivalry spotlight.
- Standings provides combined and segmented career tables, manager filtering, shared-credit markers, and a null-preserving filtered CSV download.
- Manager profiles provide query-linked selection, career and season history, reviewed aliases, actual/expected-win trends, opponent summaries, nemesis/favorite opponent, and manager-level records.
- Rivalries provide query-linked two-manager selection, all four segment views, symmetric summaries, margins, streaks, chronological meetings, rivalry lead, and a league matrix.
- Seasons provide query-linked selection, partial active-season notices, official finishes/seeds, regular standings, completed weekly scores, and championship-bracket results.
- Records provide category/season filters, tied holders, availability state, and processed source details without exposing raw payloads or member identifiers.
- Shared formula and attribution explanations keep missing and incomplete values unavailable rather than converting them to zero.
- Normalization version `phase2.v3` prefers source-backed member first/last names over generated numeric ESPN handles; canonical labels remain controlled by the ignored YAML mapping.
- Normal rendering remains read-only and provides no import or refresh action.

## Automated verification

- Readiness tests cover missing, stale, partial, and current manifest contracts with synthetic temporary Parquet bundles.
- Presentation tests cover ties, segmented win percentage, shared credit, and unavailable formatting.
- Streamlit smoke tests cover all six pages while denying network connections.
- The current suite passes 60 tests, Ruff formatting/linting, and mypy for application, page, and script code.
- The reviewed private mapping now contains 17 canonical managers, resolves all 96 season teams with zero conflicts, and has no remaining shared-attribution rows after the owner-requested merges and removals.
- Manager and season query-linked selectors now commit widget, page, and URL state in one interaction, with regression coverage for the prior double-selection bug.
- A shared visual refresh reduces page density with summary cards, clearer hierarchy, tabs, and
  expandable detail while preserving unavailable states and formula explanations.
- Selecting a row in a manager's season-by-season stat sheet now reveals that season's validated
  final-roster snapshot and its coverage/definition metadata.

## Remaining exit work

- Complete and document desktop and common-phone viewport journeys with an available browser connection.
- Verify keyboard operation for navigation, selectors, filters, expanders, and downloads.
- Reconcile representative displayed figures against the promoted private Phase 4 tables.
- Perform the final browser privacy review and confirm no private identifiers appear in rendered source details.

The standalone browser-verification CLI and in-app browser connection were unavailable during this implementation pass. Streamlit's page test harness rendered every journey without exceptions, but that does not satisfy the visual/keyboard exit gate. Phase 5 therefore remains in progress. The user explicitly authorized Phase 6 work on 2026-08-27 despite this gate; the outstanding checks remain release debt.

Phase 6 input coverage, source-sufficiency prerequisites, calculation contracts, tests, and exit criteria are documented in `PHASE_6_HANDOFF.md`; implemented status and remaining manual checks are documented in `PHASE_6_STATUS.md`.
