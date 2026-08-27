# Phase 7 — validation and release status

Updated: 2026-08-27

Status: **in progress; automated release preflight implemented, manual gates remain open**

## Phase gate

The user explicitly authorized Phase 7 development on 2026-08-27 while the documented Phase 5
and Phase 6 manual exit checks remain incomplete. This starts release work but does not mark either
earlier phase—or the MVP release—as complete.

## Implemented

- `scripts/release_check.py` runs a fast, offline, read-only release preflight.
- Core readiness includes required promoted files, complete reviewed identities, and current core
  analytics source/formula/attribution checksums.
- Draft readiness verifies its processed inputs, identity manifest, formula version, and threshold
  contract are current.
- The privacy preflight rejects tracked raw, processed, derived, audit, export, canonical identity,
  local environment, and Streamlit-secret files while allowing directory `.gitkeep` placeholders.
- Tracked text is scanned for apparent non-placeholder `ESPN_S2` and `ESPN_SWID` assignments. The
  scan also includes new non-ignored files intended for version control; the report names a file
  but never prints a detected value.
- Human-only reconciliation, browser, recovery, and deployment checks are always reported
  separately. Automated success cannot mark the release ready.

Run the preflight from the repository root:

```bash
.venv/bin/python scripts/release_check.py
```

Use `--json` for a share-safe machine-readable result. Do not publish private datasets or other
manual evidence merely because the preflight output itself is share-safe.

## Remaining work

- Close the Phase 5 desktop/phone, keyboard, displayed-value, and rendered-browser privacy checks.
- Close the Phase 6 draft, final-roster, value-row, and report-card reconciliations.
- Profile cold/warm page loads and analytics rebuilds, then optimize measured bottlenecks only.
- Run and record the complete automated baseline and acceptance matrix.
- Exercise private backup/restore, fixture-backed failed refresh, offline rebuild, and
  expired-cookie recovery.
- Complete the Git/history, generated-output, browser, and log privacy audit.
- Record the local-only or platform-protected deployment decision and final release evidence.

## Verification recorded 2026-08-27

- Release preflight: four automated checks passed; eight manual gates reported open.
- Offline source validation: 8 snapshots and 12 processed tables passed.
- Identity validation: 96/96 season teams resolved with zero conflicts.
- Automated tests: 78 passed.
- Ruff formatting and lint: passed across the repository.
- mypy: passed across 35 application, page, and script source files.

The formal repeated rebuild/import, private backup/restore, browser, and manual reconciliation
drills are not included in this evidence and remain open.
