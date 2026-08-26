from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from fantasy_history.identities import (
    AssignmentType,
    CanonicalManager,
    ExplicitAssignment,
    ManagerMapping,
    apply_manager_identity_overrides,
    load_manager_mapping,
    rebuild_identity_outputs,
    replace_generic_display_names,
    resolve_manager_identities,
    suggest_identity_mappings,
    write_identity_suggestions,
)
from fantasy_history.validation import IdentityValidationError


def source_managers(*rows: tuple[int, str | None, str | None]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "season": season,
                "source_member_id": member_id,
                "display_name": display_name,
            }
            for season, member_id, display_name in rows
        ]
    )


def source_teams(*rows: tuple[int, int, str | None, list[str], str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "league_id": 999,
                "season": season,
                "source_team_id": team_id,
                "team_name": team_name,
                "primary_owner_id": owners[0] if owners else None,
                "owner_ids_json": json.dumps(owners),
                "source_file": f"{season}/league.json",
                "source_row_key": f"{season}:team:{team_id}",
            }
            for season, team_id, team_name, owners, _label in rows
        ]
    )


def manager(
    name: str,
    *,
    member_ids: list[str] | None = None,
    season_teams: dict[int, int] | None = None,
    assignments: list[ExplicitAssignment] | None = None,
) -> CanonicalManager:
    return CanonicalManager(
        display_name=name,
        espn_member_ids=member_ids or [],
        season_team_ids=season_teams or {},
        explicit_assignments=assignments or [],
    )


def test_stable_member_id_resolves_renamed_teams_to_one_manager() -> None:
    members = source_managers((2019, "member-a", "Alpha"), (2020, "member-a", "Alpha"))
    teams = source_teams(
        (2019, 1, "Old Name", ["member-a"], "first"),
        (2020, 7, "New Name", ["member-a"], "renamed"),
    )
    mapping = ManagerMapping(managers={"alpha": manager("Alpha", member_ids=["member-a"])})

    result = resolve_manager_identities(members, teams, mapping)

    assert result.report.is_complete
    assert result.frames["manager_team_assignments"]["canonical_manager_id"].tolist() == [
        "alpha",
        "alpha",
    ]
    assert teams["source_row_key"].tolist() == ["2019:team:1", "2020:team:7"]


def test_generic_display_name_uses_latest_source_backed_member_name() -> None:
    mapping = ManagerMapping(managers={"alpha": manager("espn12345678", member_ids=["member-a"])})
    members = source_managers(
        (2024, "member-a", "Earlier Name"),
        (2025, "member-a", "Latest Name"),
    )

    updated, count = replace_generic_display_names(mapping, members)

    assert count == 1
    assert updated.managers["alpha"].display_name == "Latest Name"
    assert updated.managers["alpha"].espn_member_ids == ["member-a"]


def test_reviewed_handle_override_merges_existing_manager_and_deletes_shared_entry() -> None:
    shared = ExplicitAssignment(
        season=2024, source_team_id=3, assignment_type=AssignmentType.CO_OWNER
    )
    mapping = ManagerMapping(
        managers={
            "existing": manager("Real Name", member_ids=["member-a"], season_teams={2023: 1}),
            "fallback": manager("Fallback", member_ids=["member-b"], season_teams={2024: 2}),
            "shared": manager("Shared", member_ids=["member-c"], assignments=[shared]),
        }
    )

    updated, changed, deleted = apply_manager_identity_overrides(
        mapping,
        handle_member_ids={"fallback_handle": {"member-b"}, "remove_me": {"member-c"}},
        renames={"fallback_handle": "Real Name"},
        deletions={"remove_me"},
    )

    assert changed == 1
    assert deleted == 1
    assert set(updated.managers) == {"existing"}
    assert updated.managers["existing"].espn_member_ids == ["member-a", "member-b"]
    assert updated.managers["existing"].season_team_ids == {2023: 1, 2024: 2}


def test_deleting_one_co_owner_collapses_remaining_rule_to_single_owner() -> None:
    shared = ExplicitAssignment(
        season=2024, source_team_id=3, assignment_type=AssignmentType.CO_OWNER
    )
    mapping = ManagerMapping(
        managers={
            "remaining": manager("Remaining", member_ids=["member-a"], assignments=[shared]),
            "removed": manager("Removed", member_ids=["member-b"], assignments=[shared]),
        }
    )

    updated, _, deleted = apply_manager_identity_overrides(
        mapping,
        handle_member_ids={"remove_me": {"member-b"}},
        renames={},
        deletions={"remove_me"},
    )

    assert deleted == 1
    assert set(updated.managers) == {"remaining"}
    assert updated.managers["remaining"].season_team_ids == {2024: 3}
    assert updated.managers["remaining"].explicit_assignments == []


def test_committed_example_mapping_is_valid_and_share_safe() -> None:
    path = Path(__file__).parents[1] / "data" / "config" / "managers.example.yaml"

    mapping = load_manager_mapping(path)

    assert mapping.mapping_version == 1
    assert set(mapping.managers) == {"demo_manager", "demo_co_owner"}
    assert all(
        "SYNTHETIC" in member_id
        for manager in mapping.managers.values()
        for member_id in manager.espn_member_ids
    )


def test_changed_team_id_resolves_only_through_explicit_season_override() -> None:
    members = source_managers((2021, None, None))
    teams = source_teams((2021, 8, "Changed ID", [], "changed"))
    mapping = ManagerMapping(managers={"alpha": manager("Alpha", season_teams={2021: 8})})

    result = resolve_manager_identities(members, teams, mapping)

    row = result.frames["manager_team_assignments"].iloc[0]
    assert row["canonical_manager_id"] == "alpha"
    assert row["resolution_type"] == "single_owner"
    assert row["source_team_row_key"] == "2021:team:8"
    assert row["source_member_ids_json"] == "[]"


@pytest.mark.parametrize(
    ("assignment_type", "report_field"),
    [
        (AssignmentType.CO_OWNER, "co_owned_teams"),
        (AssignmentType.OWNERSHIP_TRANSFER, "transferred_teams"),
    ],
)
def test_multi_manager_attribution_is_explicit(
    assignment_type: AssignmentType, report_field: str
) -> None:
    members = source_managers((2022, "member-a", "Alpha"), (2022, "member-b", "Beta"))
    teams = source_teams((2022, 4, "Shared Team", ["member-a", "member-b"], "shared"))
    assignment = ExplicitAssignment(season=2022, source_team_id=4, assignment_type=assignment_type)
    mapping = ManagerMapping(
        managers={
            "alpha": manager("Alpha", member_ids=["member-a"], assignments=[assignment]),
            "beta": manager("Beta", member_ids=["member-b"], assignments=[assignment]),
        }
    )

    result = resolve_manager_identities(members, teams, mapping)

    rows = result.frames["manager_team_assignments"]
    assert result.report.is_complete
    assert getattr(result.report, report_field) == 1
    assert set(rows["canonical_manager_id"]) == {"alpha", "beta"}
    assert set(rows["resolution_type"]) == {assignment_type.value}


def test_missing_and_ambiguous_owners_remain_unresolved_without_conflicts() -> None:
    members = source_managers((2023, "member-a", "Alpha"), (2023, "member-b", "Beta"))
    teams = source_teams(
        (2023, 1, "No Owner", [], "missing"),
        (2023, 2, "Two Owners", ["member-a", "member-b"], "ambiguous"),
    )
    mapping = ManagerMapping(
        managers={
            "alpha": manager("Alpha", member_ids=["member-a"]),
            "beta": manager("Beta", member_ids=["member-b"]),
        }
    )

    result = resolve_manager_identities(members, teams, mapping)

    assert result.report.is_valid
    assert not result.report.is_complete
    assert result.report.unresolved_teams == 2
    assert set(result.frames["manager_team_assignments"]["resolution_type"]) == {"unresolved"}


def test_duplicate_team_or_member_assignments_fail_validation() -> None:
    members = source_managers((2024, "same-member", "Alpha"))
    teams = source_teams((2024, 5, "Conflict", ["same-member"], "conflict"))
    mapping = ManagerMapping(
        managers={
            "alpha": manager("Alpha", member_ids=["same-member"], season_teams={2024: 5}),
            "beta": manager("Beta", member_ids=["same-member"], season_teams={2024: 5}),
        }
    )

    result = resolve_manager_identities(members, teams, mapping)

    assert not result.report.is_valid
    assert result.report.conflict_count >= 2


def test_suggestions_are_non_authoritative_and_preserve_all_team_evidence(
    tmp_path: Path,
) -> None:
    members = source_managers((2024, "member-a", "Alpha"))
    teams = source_teams(
        (2024, 1, "Before Transfer", ["member-a"], "before"),
        (2024, 2, "After Transfer", ["member-a"], "after"),
    )

    suggestions = suggest_identity_mappings(members, teams)
    destination = tmp_path / "managers.suggestions.yaml"
    write_identity_suggestions(suggestions, destination)
    payload = yaml.safe_load(destination.read_text())

    assert len(suggestions[0].season_team_ids) == 2
    assert len(payload["suggestions"][0]["season_team_evidence"]) == 2
    assert "managers" not in payload


def write_processed_inputs(root: Path, managers: pd.DataFrame, teams: pd.DataFrame) -> None:
    root.mkdir(parents=True)
    managers.to_parquet(root / "managers.parquet", index=False)
    teams.to_parquet(root / "season_teams.parquet", index=False)


def write_mapping(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_rebuild_preserves_mapping_and_failed_validation_preserves_output(
    tmp_path: Path,
) -> None:
    processed = tmp_path / "processed"
    derived = tmp_path / "derived" / "identities"
    mapping_path = tmp_path / "config" / "managers.yaml"
    staging = tmp_path / "staging"
    members = source_managers((2025, "member-a", "Alpha"))
    teams = source_teams((2025, 9, "Traceable", ["member-a"], "trace"))
    write_processed_inputs(processed, members, teams)
    valid_mapping = {
        "mapping_version": 1,
        "managers": {
            "alpha": {
                "display_name": "Alpha",
                "espn_member_ids": ["member-a"],
                "season_team_ids": {2025: 9},
            }
        },
    }
    write_mapping(mapping_path, valid_mapping)
    mapping_before = mapping_path.read_bytes()

    first = rebuild_identity_outputs(
        processed_root=processed,
        mapping_path=mapping_path,
        derived_root=derived,
        staging_root=staging,
        require_complete=True,
    )
    output_before = {path.name: path.read_bytes() for path in derived.iterdir()}
    second = rebuild_identity_outputs(
        processed_root=processed,
        mapping_path=mapping_path,
        derived_root=derived,
        staging_root=staging,
        require_complete=True,
    )

    assert mapping_path.read_bytes() == mapping_before
    assert (
        first.frames["manager_team_assignments"].iloc[0]["source_team_row_key"]
        == (second.frames["manager_team_assignments"].iloc[0]["source_team_row_key"])
    )

    invalid_mapping = {
        "managers": {
            "alpha": {"display_name": "Alpha", "espn_member_ids": ["member-a"]},
            "beta": {"display_name": "Beta", "espn_member_ids": ["member-a"]},
        }
    }
    write_mapping(mapping_path, invalid_mapping)
    with pytest.raises(IdentityValidationError, match="no output was promoted"):
        rebuild_identity_outputs(
            processed_root=processed,
            mapping_path=mapping_path,
            derived_root=derived,
            staging_root=staging,
        )

    assert {path.name: path.read_bytes() for path in derived.iterdir()} == output_before


def test_required_completeness_failure_preserves_previous_output(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    derived = tmp_path / "derived" / "identities"
    mapping_path = tmp_path / "config" / "managers.yaml"
    staging = tmp_path / "staging"
    members = source_managers((2025, "member-a", "Alpha"))
    teams = source_teams((2025, 9, "Traceable", ["member-a"], "trace"))
    write_processed_inputs(processed, members, teams)
    write_mapping(
        mapping_path,
        {"managers": {"alpha": {"display_name": "Alpha", "espn_member_ids": ["member-a"]}}},
    )
    rebuild_identity_outputs(
        processed_root=processed,
        mapping_path=mapping_path,
        derived_root=derived,
        staging_root=staging,
        require_complete=True,
    )
    output_before = {path.name: path.read_bytes() for path in derived.iterdir()}
    write_mapping(mapping_path, {"managers": {}})

    with pytest.raises(IdentityValidationError, match="unresolved"):
        rebuild_identity_outputs(
            processed_root=processed,
            mapping_path=mapping_path,
            derived_root=derived,
            staging_root=staging,
            require_complete=True,
        )

    assert {path.name: path.read_bytes() for path in derived.iterdir()} == output_before
