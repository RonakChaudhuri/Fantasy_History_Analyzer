# Phase 0 — ESPN feasibility and audit

Status: **complete — audited 2026-08-25**

Phase 0 checks representative early, middle, and latest seasons before the application architecture is built. The audit inventories settings, members, teams, schedules, playoffs, drafts, lineups, and rosters; verifies PPR and lineup configuration; and compares response field paths between seasons.

## Secret setup

1. Open the ignored local `.env` file created at the repository root.
2. Set `ESPN_S2` and `ESPN_SWID` from the league owner's authenticated ESPN browser session.
3. Do not paste either value into chat, commit them, or put them in a command line.

The audit loads `.env` directly. It does not print cookies, request headers, response bodies, or private member fields.

## Run the audit

```bash
python3 scripts/phase0_espn_audit.py
```

Latest-season discovery probes from the current calendar year backward and chooses the newest season with league settings and teams. To test a known season without discovery:

```bash
python3 scripts/phase0_espn_audit.py --latest-season 2025
```

Results are written beneath ignored `data/audit/phase0/` run directories. A completed run contains:

- `audit.json`: aggregate coverage, selected scoring/lineup settings, and field-path differences.
- `report.md`: the coverage matrix and a concise response-shape report.
- `<season>/<section>.shape.json`: JSON paths and scalar types only, never response values.
- `latest.json`: an atomically replaced pointer to the most recent successful run. Earlier runs are preserved.

The script intentionally does not persist raw response bodies during feasibility work. Phase 2 will implement validated immutable raw snapshots after the supported fields and response variants are known.

## Exit checklist

- [x] 2019 fetch succeeds.
- [x] The discovered latest available season fetch succeeds (2026).
- [x] A representative middle season fetch succeeds (2022).
- [x] PPR and lineup settings are confirmed for all three representative seasons.
- [x] Coverage is known for settings, members, teams, schedules, playoffs, drafts, lineups, and rosters.
- [x] Response-shape differences and unsupported fields have been reviewed and documented.
- [x] Secret values are absent from Git, audit outputs, terminal output, and errors.

See `PHASE_0_FINDINGS.md` for the share-safe coverage matrix and implementation constraints carried into later phases.
