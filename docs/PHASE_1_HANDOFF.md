# Phase 1 handoff — project foundation

Prepared: 2026-08-25

Current phase: Phase 0 complete; Phase 1 approved to start next

Source of truth: `DEVELOPMENT_PLAN.md` and `AGENTS.md`

This is a context handoff, not a revision to the approved plan. If it conflicts with `DEVELOPMENT_PLAN.md`, follow the plan.

## Repository state at handoff

- Phase 0 successfully audited ESPN league `78212237` for representative seasons 2019, 2022, and 2026.
- Local Python is 3.13.7. Phase 1 must perform dependency compatibility checks before pinning exact versions.
- There is no application package, Streamlit app, dependency manifest, or general README yet. Creating those is Phase 1 work.
- The local `.env` contains working credentials and is ignored. Preserve it; never copy its values into fixtures, logs, documentation, tests, or Git.
- Generated audit artifacts are beneath ignored `data/audit/phase0/`. The share-safe conclusions are in `docs/PHASE_0_FINDINGS.md`.
- The Phase 0 audit has eight passing standard-library unit tests.

## Phase 0 constraints that affect implementation

1. Support both ESPN response routes:
   - Current shape: `/seasons/{season}/segments/0/leagues/{league_id}`
   - Historical fallback: `/leagueHistory/{league_id}?seasonId={season}`
2. The historical fallback can return a top-level list and must be normalized to its league object.
3. A week-specific lineup request requires `scoringPeriodId`; an unfiltered league response is insufficient.
4. The validated 2019 response does not expose `rosterForCurrentScoringPeriod`. Treat those historical lineups as unavailable unless a later validated request supplies them.
5. Active-season fields are incomplete by design. In the 2026 audit, playoffs and the `mRoster` entries were available but empty; this is not a zero historical result.
6. ESPN fields vary by season. Validators must allow documented optional branches and dynamic maps keyed by statistic ID, slot ID, scoring period, or timestamp.
7. Member count and team count are not interchangeable: the 2022 sample contains 13 members and 12 teams.
8. Discard member notification settings and other unnecessary private member data.
9. Draft ownership cannot depend solely on `memberId`, which was absent from the active 2026 draft response.
10. Lineup slot configuration changed across seasons. Retain season-specific settings rather than applying the latest configuration historically.

## Phase 1 scope

Implement only the project foundation defined in the approved plan:

- Create `pyproject.toml` with compatible, pinned application and development dependencies after checking Python 3.12/3.13 support.
- Create the `fantasy_history` package boundaries, Streamlit entry point, page directory, scripts directory, data directories, and test layout from the plan.
- Configure formatting, linting, pytest, and optional static type checking.
- Implement configuration validation and centralized secret redaction without building the Phase 2 importer.
- Add sanitized synthetic fixtures; do not derive committed fixtures from private member/team/player values.
- Build a recognizable fixture-powered Streamlit overview shell with an explicit fixture/demo-data notice.
- Add a root `README.md` with setup, test, lint, and local app commands.

Do not begin ESPN normalization, Parquet schema implementation, manager reconciliation, analytics, or production pages during Phase 1.

## Suggested implementation order

1. Confirm compatible package versions and create `pyproject.toml`.
2. Add package and data-directory scaffolding with minimal module docstrings.
3. Add validated settings loading and redaction helpers.
4. Create fully synthetic, recognizable league fixtures.
5. Build `app.py` and the fixture-powered Overview page shell.
6. Configure and run pytest, formatter/linter, and optional type checks.
7. Run the Streamlit app and verify the primary shell at desktop and phone widths.
8. Perform a Git/output/browser/log secret scan before declaring the phase complete.

## Phase 1 exit checklist

- [ ] The Streamlit app runs locally using documented commands.
- [ ] Tests pass from a clean environment.
- [ ] Synthetic fixtures power the preview without private data.
- [ ] The overview is recognizable as Fantasy History Analyzer.
- [ ] Missing secrets produce a safe, actionable error with no values exposed.
- [ ] Redaction covers cookies, authorization headers, URLs/query data, and nested error context.
- [ ] `.env`, private ESPN data, generated audit data, processed/derived data, and temporary files remain ignored.
- [ ] No network request occurs during normal Streamlit rendering or fixture-based tests.
- [ ] Formatting and lint checks pass; type-check status is documented.
- [ ] Desktop and phone-width smoke checks pass.
- [ ] Phase 1 changes stay within Python, Streamlit, pandas, Plotly, Parquet, YAML, and file-backed architecture.

## Commands available now

Run the Phase 0 regression tests:

```bash
python3 -m unittest discover -s tests -v
```

Rerun the private audit only when intentionally refreshing feasibility results:

```bash
python3 scripts/phase0_espn_audit.py
```

The Phase 1 README should replace this section with the final environment, install, lint, test, type-check, and Streamlit commands after they are actually verified.
