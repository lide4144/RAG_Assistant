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
from app.planner_runtime import _build_planner_llm_candidate


class PlannerRuntimeConfigApiTests(unittest.TestCase):
    def test_save_and_get_planner_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_path = Path(tmp) / "planner_runtime_config.json"
            with patch("app.planner_runtime_config.PLANNER_RUNTIME_CONFIG_PATH", runtime_path):
                saved = save_admin_planner_config(
                    AdminSavePlannerConfigRequest(
                        service_mode="production",
                        provider="openai",
                        api_base="https://planner.example.com/v1",
                        api_key="sk-planner",
                        model="gpt-4.1-mini",
                        timeout_ms=9000,
                    )
                )
                loaded = get_admin_planner_config()
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["config"]["service_mode"], "production")
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
                '{"service_mode":"production","provider":"openai","api_base":"https://planner.example.com/v1","api_key":"sk-planner","model":"gpt-4.1-mini","timeout_ms":9000}',
                encoding="utf-8",
            )
            with patch("app.planner_runtime_config.PLANNER_RUNTIME_CONFIG_PATH", runtime_path):
                loaded, warnings = load_and_validate_config(cfg_path)
        self.assertEqual(loaded.planner_provider, "openai")
        self.assertEqual(loaded.planner_model, "gpt-4.1-mini")
        self.assertEqual(loaded.planner_api_base, "https://planner.example.com/v1")
        self.assertEqual(loaded.planner_timeout_ms, 9000)
        self.assertEqual(loaded.planner_service_mode, "production")
        self.assertFalse(loaded.planner_legacy_use_llm)
        self.assertEqual(loaded.planner_api_key_env, "PLANNER_RUNTIME_API_KEY")
        self.assertTrue(any("planner_use_llm=false" in item for item in warnings))

    def test_runtime_overview_exposes_planner_runtime_source(self) -> None:
        with (
            patch.dict("os.environ", {"PLANNER_MODEL": "env-planner"}, clear=False),
        ):
            payload = get_runtime_overview()
        self.assertIn("planner", payload)
        self.assertEqual(payload["planner"]["source"], "env")
        self.assertEqual(payload["planner"]["model"], "env-planner")

    def test_planner_llm_candidate_uses_default_config_when_request_path_missing(self) -> None:
        request = {
            "sessionId": "s1",
            "mode": "local",
            "query": "我录入了哪些论文",
            "history": [],
            "traceId": "t1",
            "configPath": "",
        }
        planner_input_context = {
            "request": {"query": "我录入了哪些论文", "mode": "local", "trace_id": "t1"},
            "conversation_context": {},
            "capability_registry": [],
            "policy_flags": {},
        }
        with (
            patch("app.planner_runtime.load_and_validate_config") as load_cfg,
            patch("app.planner_runtime.evaluate_planner_service_state", return_value={"formal_chat_available": False, "reason_code": "planner_api_key_missing"}),
        ):
            load_cfg.return_value = (type("Cfg", (), {
                "planner_provider": "openai",
                "planner_model": "gpt-4.1-mini",
                "planner_api_base": "https://planner.example.com/v1",
                "planner_api_key_env": "PLANNER_RUNTIME_API_KEY",
                "planner_timeout_ms": 6000,
                "llm_max_retries": 0,
            })(), [])
            payload, diagnostics = _build_planner_llm_candidate(
                request=request,
                planner_input_context=planner_input_context,
            )
        self.assertIsNone(payload)
        self.assertEqual(diagnostics["reason"], "planner_api_key_missing")
        load_cfg.assert_called_once()
        self.assertTrue(str(load_cfg.call_args.args[0]).endswith("configs/default.yaml"))


if __name__ == "__main__":
    unittest.main()
