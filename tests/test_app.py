from __future__ import annotations

import socket
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).parents[1] / "app.py"


def test_overview_renders_without_network(monkeypatch) -> None:
    def deny_network(*_args, **_kwargs):
        raise AssertionError("Normal page rendering must not open a network connection.")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    app = AppTest.from_file(str(APP), default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "🏈 Fantasy History Analyzer"
    assert any("Synthetic demo data" in item.value for item in app.info)
    assert any("no ESPN request" in item.value for item in app.caption)
