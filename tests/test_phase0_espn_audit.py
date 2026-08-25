from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

SCRIPT = Path(__file__).parents[1] / "scripts" / "phase0_espn_audit.py"
SPEC = importlib.util.spec_from_file_location("phase0_espn_audit", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class PhaseZeroAuditTests(unittest.TestCase):
    def test_shape_paths_never_retains_scalar_values(self) -> None:
        secret = "credential-that-must-not-survive"
        paths = audit.shape_paths({"members": [{"id": secret}], "score": 123.4})
        serialized = json.dumps({key: sorted(value) for key, value in paths.items()})
        self.assertNotIn(secret, serialized)
        self.assertNotIn("123.4", serialized)
        self.assertEqual(paths["$.members[].id"], {"string"})

    def test_shape_paths_collapses_dynamic_object_keys(self) -> None:
        paths = audit.shape_paths(
            {"stats": {"53": 1.0}, "status": {"2022-08-22T07:37:08.002+00:00": "COMPLETE"}}
        )
        self.assertIn("$.stats.{key}", paths)
        self.assertIn("$.status.{key}", paths)

    def test_representative_seasons_are_early_middle_latest(self) -> None:
        self.assertEqual(audit.representative_seasons(2019, 2026), [2019, 2022, 2026])
        self.assertEqual(audit.representative_seasons(2019, 2019), [2019])

    def test_latest_discovery_skips_unavailable_calendar_year(self) -> None:
        config = audit.Config(78212237, 2019, "secret", "{secret}")

        def fake_fetch(_config, season, _views):
            if season == 2026:
                raise audit.SeasonUnavailableError("not created")
            return {"settings": {"name": "redacted"}, "teams": [{"id": 1}]}

        now = audit.datetime(2026, 8, 25)
        with patch.object(audit, "fetch_json", side_effect=fake_fetch):
            with patch.object(audit, "datetime") as mocked_datetime:
                mocked_datetime.now.return_value = now
                latest, payload = audit.discover_latest(config, None)

        self.assertEqual(latest, 2025)
        self.assertIsNotNone(payload)

    def test_fetch_uses_history_fallback_after_unauthorized_season_endpoint(self) -> None:
        config = audit.Config(78212237, 2019, "secret", "{secret}")
        unauthorized = HTTPError("safe-url", 401, "Unauthorized", {}, None)
        history_payload = {"settings": {"name": "private"}, "teams": [{"id": 1}]}

        with patch.object(
            audit, "_request_json", side_effect=[unauthorized, history_payload]
        ) as request:
            payload = audit.fetch_json(config, 2019, ("mSettings",))

        self.assertEqual(payload, history_payload)
        self.assertIn("leagueHistory", request.call_args_list[1].args[2])

    def test_missing_credentials_fail_without_revealing_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(audit.AuditError, "Missing ESPN_S2, ESPN_SWID"):
                audit.Config.from_environment()

    def test_atomic_json_replaces_complete_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "audit.json"
            audit.atomic_json(path, {"valid": True})
            self.assertEqual(json.loads(path.read_text()), {"valid": True})
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_summary_distinguishes_unavailable_from_empty(self) -> None:
        payloads = {
            "league": {
                "settings": {
                    "scoringSettings": {
                        "scoringItems": [{"statId": 53, "points": 1.0}],
                        "scoringType": "H2H_POINTS",
                    },
                    "rosterSettings": {"lineupSlotCounts": {"0": 1, "20": 7}},
                },
                "members": [],
                "teams": [{"id": 1}],
            },
            "schedule": {"schedule": []},
            "draft": {},
            "rosters": {"teams": [{"id": 1}]},
            "lineups": {"schedule": []},
        }
        result = audit.summarize(payloads, 2019)
        self.assertTrue(result["settings"]["is_ppr"])
        self.assertEqual(result["availability"]["members"], "available-empty")
        self.assertEqual(result["availability"]["drafts"], "unavailable")
        self.assertEqual(result["availability"]["rosters"], "unavailable")


if __name__ == "__main__":
    unittest.main()
