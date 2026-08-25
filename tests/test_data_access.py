from __future__ import annotations

from fantasy_history.data_access import champions_frame, load_demo_overview


def test_synthetic_fixture_powers_overview() -> None:
    overview = load_demo_overview()
    champions = champions_frame(overview)

    assert "Synthetic demo data" in overview["notice"]
    assert overview["summary"]["seasons"] == len(champions)
    assert list(champions.columns) == ["season", "manager", "points"]
    assert set(champions["manager"]) == {
        "Audible Chaos",
        "Fourth & Long",
        "Goal Line Poets",
        "Sunday Scaries",
    }
