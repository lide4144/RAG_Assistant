from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import load_and_validate_config
from app.kernel_api import (
    AdminSavePlannerConfigRequest,
    get_admin_planner_config,
    get_runtime_overview,
    save_admin_planner_config,
)


class PlannerRuntimeConfigApiTests(unittest.TestCase):
    def test_save_and_get_planner_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_path = Path(tmp) / "planner_runtime_config.json"
            with patch("app.planner_runtime_config.PLANNER_RUNTIME_CONFIG_PATH", runtime_path):
                saved = save_admin_planner_config(
                    AdminSavePlannerConfigRequest(
                        use_llm=True,
                        provider="openai",
                        api_base="https://planner.example.com/v1",
                        api_key="sk-planner",
                        model="gpt-4.1-mini",
                        timeout_ms=9000,
                    )
                )
                loaded = get_admin_planner_config()
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["config"]["provider"], "openai")
        self.assertEqual(saved["config"]["model"], "gpt-4.1-mini")
        self.assertIn("***", saved["config"]["api_key_masked"])
        self.assertTrue(loaded["configured"])
        self.assertEqual(loaded["timeout_ms"], 9000)

    def test_load_and_validate_config_applies_planner_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "default.yaml"
            cfg_path.write_text("planner_use_llm: false\nplanner_model: baseline-model\n", encoding="utf-8")
            runtime_path = Path(tmp) / "planner_runtime_config.json"
            runtime_path.write_text(
                '{"use_llm":true,"provider":"openai","api_base":"https://planner.example.com/v1","api_key":"sk-planner","model":"gpt-4.1-mini","timeout_ms":9000}',
                encoding="utf-8",
            )
            with patch("app.planner_runtime_config.PLANNER_RUNTIME_CONFIG_PATH", runtime_path):
                loaded, warnings = load_and_validate_config(cfg_path)
        self.assertEqual(loaded.planner_provider, "openai")
        self.assertEqual(loaded.planner_model, "gpt-4.1-mini")
        self.assertEqual(loaded.planner_api_base, "https://planner.example.com/v1")
        self.assertEqual(loaded.planner_timeout_ms, 9000)
        self.assertEqual(loaded.planner_api_key_env, "PLANNER_RUNTIME_API_KEY")
        self.assertEqual(warnings, [])

    def test_runtime_overview_exposes_planner_runtime_source(self) -> None:
        with (
            patch.dict("os.environ", {"PLANNER_MODEL": "env-planner"}, clear=False),
        ):
            payload = get_runtime_overview()
        self.assertIn("planner", payload)
        self.assertEqual(payload["planner"]["source"], "env")
        self.assertEqual(payload["planner"]["model"], "env-planner")


if __name__ == "__main__":
    unittest.main()
