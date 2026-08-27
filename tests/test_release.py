from __future__ import annotations

from pathlib import Path

from fantasy_history.release import (
    credential_assignments,
    prohibited_tracked_paths,
    tracked_credential_files,
)


def test_prohibited_tracked_paths_allow_only_private_directory_placeholders() -> None:
    paths = (
        ".env.example",
        "data/raw/.gitkeep",
        "data/processed/.gitkeep",
        "data/raw/2025/league.json",
        "data/derived/analytics/manifest.json",
        "data/config/managers.yaml",
        "exports/standings.csv",
        ".streamlit/secrets.toml",
        "fantasy_history/release.py",
    )

    assert prohibited_tracked_paths(paths) == (
        ".streamlit/secrets.toml",
        "data/config/managers.yaml",
        "data/derived/analytics/manifest.json",
        "data/raw/2025/league.json",
        "exports/standings.csv",
    )


def test_credential_assignments_ignore_placeholders_and_never_return_values() -> None:
    credential_name = "ESPN_" + "S2"
    live_value = "apparently-live-value"
    text = f"""
    ESPN_S2=
    ESPN_SWID=<replace-me>
    export ESPN_S2=${{ESPN_S2_SECRET}}
    ESPN_SWID={{private-value}}
    {credential_name}={live_value}
    """

    assert credential_assignments(text) == ("ESPN_S2",)


def test_credential_assignments_keeps_adjacent_empty_lines_separate() -> None:
    assert credential_assignments("ESPN_S2=\nESPN_SWID=\n") == ()


def test_tracked_credential_files_reports_filename_only(tmp_path: Path) -> None:
    safe = tmp_path / ".env.example"
    unsafe = tmp_path / "notes.txt"
    binary = tmp_path / "image.bin"
    safe.write_text("ESPN_S2=<replace-me>\n", encoding="utf-8")
    unsafe.write_text(f"ESPN_SWID={'apparently-' + 'live-value'}\n", encoding="utf-8")
    binary.write_bytes(b"\xff\xfe")

    assert tracked_credential_files(tmp_path, (safe.name, unsafe.name, binary.name)) == (
        "notes.txt",
    )
