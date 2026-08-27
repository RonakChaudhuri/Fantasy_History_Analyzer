# Phase 6 — draft and roster analytics status

Updated: 2026-08-27

Status: **in progress; automated draft and roster analytics implemented, manual exit gate pending**

## Phase gate

Phase 5 still has documented desktop/phone, keyboard, displayed-value reconciliation, and
browser privacy checks outstanding. On 2026-08-27, the user explicitly authorized starting
Phase 6. Those Phase 5 checks remain release debt and have not been marked complete.

## Implemented

- A Drafts and Rosters page provides a query-linked season selector, draft state and player-name
  coverage notices, a round-by-source-team draft board, searchable pick history, null-preserving
  CSV download, manager position allocation, repeated-player history, and completed-season roster
  snapshots.
- Draft pick presentation joins pick cost to normalized player metadata, season-specific source
  teams, and reviewed canonical-manager assignments without exposing source member IDs.
- Unknown player names and positions stay unavailable. Irregular same-team round selections are
  retained, and keeper picks are visibly marked.
- Completed-season roster selection requires a non-active season, one populated `season_roster`
  snapshot for every season team, complete coverage status, and source-traceable membership rows.
  Active, available-empty, partial, and missing snapshots are unavailable rather than empty.
- Manager profiles now show source-supported position and repeated-player tendencies. Season pages
  show roster availability and link to the corresponding draft.
- A separate checksum over the six Phase 6 processed Parquet inputs and identity manifest
  invalidates the Streamlit cache when draft or roster sources change.
- ESPN actual/projected and season-total/weekly semantics are approved and normalized in a new
  source-traceable `player_scores.parquet` contract. The offline rebuild retained 37,206 score
  observations; detailed eligibility coverage is documented in `PHASE_6_SOURCE_SUFFICIENCY.md`.
- The Drafts value tab displays actual season-total production, eligibility reasons, observation
  counts, and honest per-season denominators. Repeated observations are deduplicated rather than
  summed; projected, weekly, missing, conflicting, and active-season totals are ineligible.
- Season/position replacement ranks use fixed starter demand plus FLEX slots allocated to the
  highest remaining RB/WR/TE scorers. The 2025 change from one to two FLEX slots is applied from
  that season forward; the same algorithm supports superflex with QB included if it appears.
- League-specific expected value is the median position-adjusted result for the same position and
  a ±24-overall-pick window from other completed seasons. At least eight samples are required.
- Raw surplus, within-season normalized surplus, boom/bust/drafted-sleeper labels, manager rates,
  and report-card grades are persisted in a separate atomic, versioned draft analytics bundle.
  Source, identity, formula, and threshold changes invalidate the bundle.
- The UI shows the inputs, thresholds, formula version, replacement tables, classifications, and
  report-card components on Drafts; manager profiles include their season report cards.
- Selecting a season directly in a manager's season-by-season stat sheet reveals that manager's
  validated final-roster snapshot, with explicit unavailable states for unsafe snapshots.
- The app-wide visual refresh presents headline results before dense tables, groups secondary
  analysis into tabs and expanders, and uses consistent summary cards and explanatory copy.
- Pure pandas tests cover draft order, keepers, irregular picks, missing player metadata, reviewed
  manager attribution, repeated-player identity, known-position denominators, active/empty/missing
  roster states, and completed roster traceability.

## Classification contract

- Boom: normalized surplus at least `+1.00`.
- Bust: normalized surplus at most `-1.00`.
- Drafted sleeper: round 10 or later, at or above replacement, and normalized surplus at least
  `+0.75`.
- Report-card score: the manager's within-season percentile by average eligible-pick percentile.
  Grades are A at 80+, B at 65+, C at 50+, D at 35+, and F below 35.

The completed-season distributions yield 10–21 booms, 16–25 busts, and 2–10 drafted sleepers per
season. One to three otherwise production-eligible picks per season are excluded for sparse
expected-value samples. Missing production is not converted to zero and never becomes a bust.

## Next implementation gate

Undrafted sleeper attribution remains unavailable because every retained roster-player acquisition
type is missing. A separately validated acquisition/player-data import is required before assigning
an undrafted sleeper to a manager. The current sleeper label therefore means drafted sleeper only.

## Remaining Phase 6 exit work

- Reconcile an early and recent draft plus representative roster snapshots against ESPN.
- Manually reproduce sampled value rows and report-card grades from displayed inputs.
- Complete desktop/phone, keyboard, privacy, displayed-formula, and full verification gates.

Phase 7 preparation and the consolidated release checklist are documented in
`PHASE_7_HANDOFF.md`. Phase 6 is not marked complete until the manual work above is recorded.
