from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from fantasy_history.analytics import analytics_bundle_is_current
from fantasy_history.deployment import build_deployment_bundle
from fantasy_history.draft_analytics import draft_analytics_bundle_is_current


def test_public_bundle_preserves_rendered_data_and_removes_member_ids(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    source = project_root / "data"
    destination = tmp_path / "public"

    build_deployment_bundle(source_root=source, destination_root=destination)

    public_teams = pd.read_parquet(destination / "processed" / "season_teams.parquet")
    private_teams = pd.read_parquet(source / "processed" / "season_teams.parquet")
    visible_columns = [
        "season",
        "source_team_id",
        "team_name",
        "official_wins",
        "official_losses",
        "official_ties",
        "official_points_for",
        "official_points_against",
    ]
    pd.testing.assert_frame_equal(public_teams[visible_columns], private_teams[visible_columns])
    assert public_teams["primary_owner_id"].isna().all()
    assert public_teams["owner_ids_json"].eq("[]").all()

    managers = pd.read_parquet(destination / "processed" / "managers.parquet")
    canonical = pd.read_parquet(
        destination / "derived" / "identities" / "canonical_managers.parquet"
    )
    assert managers["source_member_id"].isna().all()
    assert canonical["espn_member_ids_json"].eq("[]").all()
    assert analytics_bundle_is_current(
        processed_root=destination / "processed",
        identities_root=destination / "derived" / "identities",
        analytics_root=destination / "derived" / "analytics",
    )
    assert draft_analytics_bundle_is_current(
        processed_root=destination / "processed",
        identities_root=destination / "derived" / "identities",
        draft_analytics_root=destination / "derived" / "draft_analytics",
    )
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["privacy"]["espn_member_identifiers_removed"] is True
