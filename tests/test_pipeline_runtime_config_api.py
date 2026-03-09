from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.admin_llm_config import RuntimeLLMConfig, RuntimeStageConfig
from app.kernel_api import (
    AdminSavePipelineConfigRequest,
    get_admin_pipeline_config,
    get_runtime_overview,
    save_admin_pipeline_config,
)
from app.pipeline_runtime_config import MarkerTuning


class PipelineRuntimeConfigApiTests(unittest.TestCase):
    def test_save_and_get_pipeline_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_path = Path(tmp) / "pipeline_runtime_config.json"
            with patch("app.pipeline_runtime_config.PIPELINE_RUNTIME_CONFIG_PATH", runtime_path):
                saved = save_admin_pipeline_config(
                    AdminSavePipelineConfigRequest(
                        marker_tuning={
                            "recognition_batch_size": 3,
                            "detector_batch_size": 4,
                            "layout_batch_size": 2,
                            "ocr_error_batch_size": 1,
                            "table_rec_batch_size": 1,
                            "model_dtype": "float16",
                        },
                        marker_llm={
                            "use_llm": True,
                            "llm_service": "marker.services.openai.OpenAIService",
                            "openai_api_key": "sk-test-openai",
                            "openai_model": "gpt-4.1-mini",
                            "openai_base_url": "https://api.openai.com/v1",
                        },
                    )
                )
                loaded = get_admin_pipeline_config()
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["config"]["marker_tuning"]["recognition_batch_size"], 3)
        self.assertEqual(saved["config"]["marker_llm"]["llm_service"], "marker.services.openai.OpenAIService")
        self.assertNotEqual(saved["config"]["marker_llm"]["openai_api_key"], "sk-test-openai")
        self.assertTrue(loaded["configured"])
        self.assertEqual(loaded["saved"]["marker_tuning"]["detector_batch_size"], 4)
        self.assertEqual(loaded["effective"]["marker_tuning"]["model_dtype"], "float16")
        self.assertEqual(loaded["effective"]["marker_llm"]["openai_model"], "gpt-4.1-mini")

    def test_save_pipeline_config_rejects_invalid_field(self) -> None:
        with self.assertRaises(Exception) as ctx:
            save_admin_pipeline_config(
                AdminSavePipelineConfigRequest(
                    marker_tuning={
                        "recognition_batch_size": 0,
                        "detector_batch_size": 2,
                        "layout_batch_size": 2,
                        "ocr_error_batch_size": 1,
                        "table_rec_batch_size": 1,
                        "model_dtype": "float16",
                    }
                )
            )
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)
        self.assertEqual(getattr(ctx.exception, "detail", {}).get("code"), "INVALID_PARAMS")
        self.assertIn("recognition_batch_size", getattr(ctx.exception, "detail", {}).get("field_errors", {}))

    def test_save_pipeline_config_rejects_missing_vertex_project_id(self) -> None:
        with self.assertRaises(Exception) as ctx:
            save_admin_pipeline_config(
                AdminSavePipelineConfigRequest(
                    marker_tuning={
                        "recognition_batch_size": 2,
                        "detector_batch_size": 2,
                        "layout_batch_size": 2,
                        "ocr_error_batch_size": 1,
                        "table_rec_batch_size": 1,
                        "model_dtype": "float16",
                    },
                    marker_llm={
                        "use_llm": True,
                        "llm_service": "marker.services.vertex.GoogleVertexService",
                        "vertex_project_id": "",
                    },
                )
            )
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)
        self.assertIn("vertex_project_id", getattr(ctx.exception, "detail", {}).get("field_errors", {}))

    def test_runtime_overview_blocked_when_answer_missing(self) -> None:
        with (
            patch("app.kernel_api.load_runtime_llm_config", return_value=(None, None)),
            patch(
                "app.kernel_api.resolve_effective_marker_tuning",
                return_value=type(
                    "EffectiveMarker",
                    (),
                    {
                        "values": MarkerTuning(),
                        "source": {
                            "recognition_batch_size": "default",
                            "detector_batch_size": "default",
                            "layout_batch_size": "default",
                            "ocr_error_batch_size": "default",
                            "table_rec_batch_size": "default",
                            "model_dtype": "default",
                        },
                        "warnings": [],
                    },
                )(),
            ),
        ):
            payload = get_runtime_overview()
        self.assertEqual(payload["status"]["level"], "BLOCKED")
        self.assertIn("answer stage is not configured", payload["status"]["reasons"][0])
        self.assertIn("effective_source", payload["pipeline"])

    def test_runtime_overview_ready_when_all_required_stages_present(self) -> None:
        llm = RuntimeLLMConfig(
            answer=RuntimeStageConfig(provider="openai", api_base="https://api.example.com/v1", api_key="a", model="gpt-4.1"),
            embedding=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="b", model="bge"),
            rerank=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="c", model="rerank"),
            rewrite=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="d", model="rewrite"),
            graph_entity=RuntimeStageConfig(
                provider="siliconflow",
                api_base="https://api.example.com/v1",
                api_key="e",
                model="graph",
            ),
            updated_at="2026-03-07T00:00:00Z",
        )
        with (
            patch("app.kernel_api.load_runtime_llm_config", return_value=(llm, None)),
            patch(
                "app.kernel_api.resolve_effective_marker_tuning",
                return_value=type(
                    "EffectiveMarker",
                    (),
                    {
                        "values": MarkerTuning(),
                        "source": {
                            "recognition_batch_size": "runtime",
                            "detector_batch_size": "runtime",
                            "layout_batch_size": "runtime",
                            "ocr_error_batch_size": "runtime",
                            "table_rec_batch_size": "runtime",
                            "model_dtype": "runtime",
                        },
                        "warnings": [],
                    },
                )(),
            ),
        ):
            payload = get_runtime_overview()
        self.assertEqual(payload["status"]["level"], "READY")
        self.assertEqual(payload["llm"]["answer"]["configured"], True)
        self.assertEqual(payload["pipeline"]["marker_tuning"]["model_dtype"], "float16")


if __name__ == "__main__":
    unittest.main()
