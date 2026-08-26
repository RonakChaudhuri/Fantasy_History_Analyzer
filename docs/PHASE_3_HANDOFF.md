# Phase 3 handoff — manager reconciliation

Prepared: 2026-08-25

Phase 2 is complete and has produced validated source-level manager and team rows for league `78212237`. Phase 3 may now add canonical manager identities, while preserving source identifiers and keeping all ambiguous assignments explicit.

## Inputs available

Use the ignored local Parquet files produced by Phase 2:

- `data/processed/managers.parquet` — one row per season-specific ESPN member, with `season`, `source_member_id`, `display_name`, `is_league_manager`, `source_file`, and `source_row_key`.
- `data/processed/season_teams.parquet` — one row per season-specific ESPN team, with `season`, `source_team_id`, team-name fields, `primary_owner_id`, `owner_ids_json`, and source traceability.
- `data/processed/draft_picks.parquet` and roster/matchup tables — additional validated team/member references that can expose ownership changes or missing member IDs.
- `data/raw/<season>/manifest.json` — checksums, coverage state, warnings, and structural source paths for auditability.

Do not copy private IDs, names, or raw response values into committed documentation, tests, fixtures, logs, or chat.

## Mapping authority

The ignored `data/config/managers.yaml` file is the final authority. Keep the committed `data/config/managers.example.yaml` synthetic and share-safe. A mapping entry follows this shape:

```yaml
managers:
  manager_key:
    display_name: "Manager Name"
    espn_member_ids:
      - "member-id"
    season_team_ids:
      2019: 4
      2020: 4
      2021: 7
```

The implementation should permit aliases/team-name history and explicit co-owner or ownership-transfer records without changing the source Parquet rows.

## Required behavior

1. Generate suggestions from stable ESPN identifiers and corroborating season/team evidence; suggestions are never automatic merges.
2. Apply YAML overrides after suggestions and preserve them across every import and rebuild.
3. Require every season team to be either deliberately assigned to one canonical manager, explicitly represented as a co-owner/transfer, or reported unresolved.
4. Reject multiply assigned team IDs and conflicting member assignments with actionable, secret-free diagnostics.
5. Keep canonical manager keys stable when ESPN team IDs or names change.
6. Never infer ownership solely from a display name, draft `memberId`, or a team rename.
7. Treat missing member IDs and unavailable sections as unresolved evidence, not as a reason to merge or drop a team.
8. Retain source season/team/member keys on every resolved row so career aggregates remain traceable.

## Suggested Phase 3 modules and functions

- `fantasy_history/identities.py`: YAML models, suggestion generation, override loading, resolution, and conflict reporting.
- `fantasy_history/validation.py`: mapping validation errors and unresolved/conflict counts.
- `fantasy_history/data_access.py`: cached reads of source tables and resolved tables.
- `scripts/validate_identities.py`: explicit local command that reads ignored data and the ignored mapping only.

Keep the resolver pure and injectable: tests should pass DataFrames and mapping dictionaries without contacting ESPN or requiring private files.

## Required tests before Phase 4

- Stable member ID across a team rename resolves to one canonical manager.
- Changed ESPN team IDs resolve through explicit season overrides.
- A co-owner is represented without silently choosing one person.
- Ownership transfer is represented by season and team, not merged across the entire career.
- Missing/ambiguous member IDs remain unresolved and appear in the validation report.
- A team assigned to two canonical managers fails validation.
- YAML overrides survive import/rebuild and do not mutate the source tables.
- Every resolved row retains season, source team/member IDs, and source-row traceability.
- A failed mapping validation leaves the prior resolved dataset untouched.

## Acceptance evidence

Before starting Phase 4, record only aggregate evidence in a share-safe status document:

- total season teams examined;
- deliberately resolved, co-owned/transferred, and unresolved counts;
- conflict count (must be zero for exit);
- proof that a rebuild preserves the mapping and source-row keys;
- representative renamed-team and changed-ID checks, with private values kept local.

The unresolved Phase 1 viewport smoke check is still documented in `PHASE_1_FOUNDATION.md` and should be completed before release even though the user explicitly authorized starting Phase 2.
