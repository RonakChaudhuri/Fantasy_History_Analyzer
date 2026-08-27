from __future__ import annotations

import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from fantasy_history.data_access import load_identity_table

APP = Path(__file__).parents[1] / "app.py"


def test_overview_renders_without_network(monkeypatch) -> None:
    def deny_network(*_args, **_kwargs):
        raise AssertionError("Normal page rendering must not open a network connection.")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    app = AppTest.from_file(str(APP), default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "🏈 Fantasy History Analyzer"
    assert any("active" in item.value.lower() for item in app.warning)
    assert any("no ESPN request" in item.value for item in app.caption)


@pytest.mark.parametrize(
    ("relative_path", "expected_title"),
    [
        ("pages/2_Standings.py", "All-time standings"),
        ("pages/3_Managers.py", "Manager profiles"),
        ("pages/4_Rivalries.py", "Rivalries"),
        ("pages/5_Seasons.py", "Seasons"),
        ("pages/6_Drafts.py", "Drafts and rosters"),
        ("pages/7_Records.py", "Records cabinet"),
    ],
)
def test_core_page_smoke_without_network(
    monkeypatch, relative_path: str, expected_title: str
) -> None:
    def deny_network(*_args, **_kwargs):
        raise AssertionError("Normal page rendering must not open a network connection.")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    page = Path(__file__).parents[1] / relative_path
    app = AppTest.from_file(str(page), default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == expected_title


def test_manager_dropdown_changes_profile_and_query_with_one_interaction() -> None:
    page = Path(__file__).parents[1] / "pages/3_Managers.py"
    managers = load_identity_table("canonical_managers").sort_values(
        "display_name", key=lambda values: values.str.casefold()
    )
    target = managers.iloc[1]
    app = AppTest.from_file(str(page), default_timeout=10).run()

    app.selectbox[0].set_value(str(target["display_name"])).run()

    assert not app.exception
    assert app.selectbox[0].value == str(target["canonical_manager_id"])
    assert app.query_params["manager"] == [str(target["canonical_manager_id"])]
    assert any(item.value == str(target["display_name"]) for item in app.subheader)
    assert any("Biggest drafted sleepers and busts" in item.value for item in app.markdown)


def test_season_dropdown_changes_page_and_query_with_one_interaction() -> None:
    page = Path(__file__).parents[1] / "pages/5_Seasons.py"
    app = AppTest.from_file(str(page), default_timeout=10).run()
    target = str(app.selectbox[0].options[1])

    app.selectbox[0].set_value(target).run()

    assert not app.exception
    assert app.selectbox[0].value == target
    assert app.query_params["season"] == [target]


def test_draft_dropdown_changes_page_and_query_with_one_interaction() -> None:
    page = Path(__file__).parents[1] / "pages/6_Drafts.py"
    app = AppTest.from_file(str(page), default_timeout=10).run()
    target = str(app.selectbox[0].options[1])

    app.selectbox[0].set_value(target).run()

    assert not app.exception
    assert app.selectbox[0].value == target
    assert app.query_params["season"] == [target]
