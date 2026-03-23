from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.admin_llm_config import RuntimeLLMConfig, RuntimeStageConfig
from app.kernel_api import (
    AdminSavePipelineConfigRequest,
    ImportLatestResultResponse,
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

    def test_runtime_overview_falls_back_to_static_baseline_when_runtime_missing(self) -> None:
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
        self.assertEqual(payload["status"]["level"], "DEGRADED")
        self.assertEqual(payload["llm"]["answer"]["configured"], True)
        self.assertEqual(payload["llm"]["answer"]["source"], "default")
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
            sufficiency_judge=RuntimeStageConfig(
                provider="siliconflow",
                api_base="https://api.example.com/v1",
                api_key="f",
                model="judge",
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
            patch(
                "app.kernel_api._load_latest_import_result",
                return_value=ImportLatestResultResponse(artifact_summary={"counts": {"healthy": 0, "missing": 0, "stale": 0}}),
            ),
        ):
            payload = get_runtime_overview()
        self.assertEqual(payload["status"]["level"], "READY")
        self.assertEqual(payload["llm"]["answer"]["configured"], True)
        self.assertEqual(payload["llm"]["answer"]["source"], "runtime")
        self.assertEqual(payload["pipeline"]["marker_tuning"]["model_dtype"], "float16")

    def test_runtime_overview_exposes_stage_updated_at(self) -> None:
        llm = RuntimeLLMConfig(
            answer=RuntimeStageConfig(provider="openai", api_base="https://api.example.com/v1", api_key="a", model="gpt-4.1"),
            embedding=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="b", model="bge"),
            rerank=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="c", model="rerank"),
            rewrite=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="d", model="rewrite"),
            graph_entity=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="e", model="graph"),
            sufficiency_judge=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="f", model="judge"),
            updated_at="2026-03-07T00:00:00Z",
        )
        latest_import = ImportLatestResultResponse(
            updated_at="2026-03-12T16:15:30Z",
            stage_updated_at={
                "import": "2026-03-12T16:15:20Z",
                "clean": "2026-03-12T16:15:24Z",
                "index": "2026-03-12T16:15:30Z",
            },
            artifact_summary={"counts": {"healthy": 3, "missing": 0, "stale": 0}},
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
            patch("app.kernel_api._load_latest_import_result", return_value=latest_import),
        ):
            payload = get_runtime_overview()
        self.assertEqual(payload["pipeline"]["last_ingest"]["updated_at"], "2026-03-12T16:15:30Z")
        self.assertEqual(payload["pipeline"]["last_ingest"]["stage_updated_at"]["clean"], "2026-03-12T16:15:24Z")

    def test_runtime_overview_marks_llm_stage_env_override(self) -> None:
        llm = RuntimeLLMConfig(
            answer=RuntimeStageConfig(provider="openai", api_base="https://api.example.com/v1", api_key="a", model="gpt-4.1"),
            embedding=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="b", model="bge"),
            rerank=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="c", model="rerank"),
            rewrite=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="d", model="rewrite"),
            graph_entity=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="e", model="graph"),
            sufficiency_judge=RuntimeStageConfig(provider="siliconflow", api_base="https://api.example.com/v1", api_key="f", model="judge"),
            updated_at="2026-03-07T00:00:00Z",
        )
        with (
            patch("app.kernel_api.load_runtime_llm_config", return_value=(llm, None)),
            patch.dict("os.environ", {"RAG_LLM_ANSWER_MODEL": "gpt-4.1-nano"}, clear=False),
            patch(
                "app.kernel_api._load_latest_import_result",
                return_value=ImportLatestResultResponse(artifact_summary={"counts": {"healthy": 0, "missing": 0, "stale": 0}}),
            ),
        ):
            payload = get_runtime_overview()
        self.assertEqual(payload["llm"]["answer"]["model"], "gpt-4.1-nano")
        self.assertEqual(payload["llm"]["answer"]["source"], "env")
        self.assertEqual(payload["llm"]["answer"]["effective_source"]["model"], "env")


if __name__ == "__main__":
    unittest.main()
