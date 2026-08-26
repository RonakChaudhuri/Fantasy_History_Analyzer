# Phase 3 — manager reconciliation status

Updated: 2026-08-26

Status: **complete; canonical private mapping validated and promoted**

Phase 2's technical exit criteria are satisfied. The user explicitly authorized Phase 3 while the earlier Phase 1 desktop/phone browser smoke check remains open. That visual release debt is unchanged and has not been marked as passed.

## Implemented

- Strict, versioned Pydantic models for the ignored canonical `data/config/managers.yaml` authority.
- Stable canonical manager keys, ESPN member evidence, team-name aliases, explicit season/team overrides, co-owner attribution, and ownership-transfer attribution.
- Non-authoritative suggestions based only on stable member/owner identifiers and corroborating season-team evidence. Suggestions are written to a separate ignored review file and are never automatically applied.
- Pure pandas reconciliation that does not mutate Phase 2 source tables.
- One source-traceable assignment row per canonical attribution, or one explicitly unresolved row when the evidence is missing or ambiguous.
- Rejection of duplicate member mappings, multiple single-owner assignments, mixed attribution modes, incomplete co-owner/transfer groups, unknown season teams, and missing source team identifiers.
- Atomic promotion of canonical-manager and manager-team Parquet outputs plus a manifest containing mapping/source checksums, schema version, and aggregate counts.
- Safe rollback when mapping validation or required completeness fails.
- A local `scripts/validate_identities.py` command for suggestions, validation, completeness enforcement, and rebuilding without ESPN access.
- File-backed accessors for promoted identity tables.

## Automated verification

Synthetic tests cover:

- stable member identity across team renames;
- changed team IDs resolved through explicit season overrides;
- explicit co-owner and ownership-transfer rows;
- missing and ambiguous owners remaining unresolved;
- conflicting member and team assignments failing validation;
- suggestion files remaining non-authoritative and retaining same-season transfer evidence;
- source team/member traceability;
- mapping persistence across rebuilds;
- failed validation preserving the previous resolved dataset; and
- the committed example mapping remaining valid and synthetic.

The full repository currently passes pytest, Ruff formatting/linting, and mypy.

## Share-safe local-data evidence

The ignored 2019–2026 processed dataset contains:

- 8 seasons;
- 96 season-team rows;
- 20 stable-member suggestion candidates;
- 91 team rows with one stable-owner evidence candidate;
- 5 team rows with multi-owner evidence; and
- 0 team rows lacking owner evidence.

Names and source identifiers remain only in ignored local files and are not recorded here.

## Exit evidence

The league owner confirmed that the generated identity suggestions are correct. The ignored canonical `data/config/managers.yaml` was generated from that confirmation. Season-teams listed under multiple confirmed managers are represented conservatively as explicit co-ownership because no effective-period transfer boundaries were supplied.

`python scripts/validate_identities.py --require-complete` now reports:

- 20 canonical managers;
- 96 season teams examined and deliberately resolved;
- 5 co-owned season teams;
- 0 ownership transfers;
- 0 unresolved teams; and
- 0 conflicts.

A repeated identity rebuild succeeds without altering the ignored canonical mapping or source-row traceability. Phase 3's exit gate is satisfied. The outstanding Phase 1 viewport smoke check remains required before release.
