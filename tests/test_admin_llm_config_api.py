from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app import admin_llm_config
from app.config import RUNTIME_LLM_API_KEY_ENV, load_and_validate_config
from app.kernel_api import (
    AdminDetectModelsRequest,
    AdminSaveLLMConfigRequest,
    app,
    detect_models,
    get_admin_llm_config,
    save_admin_llm_config,
)


class AdminLLMConfigApiTests(unittest.TestCase):
    def test_detect_models_success_with_dedup(self) -> None:
        response_payload = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o"}, {"id": "gpt-4.1", "owned_by": "openai"}]}
        with patch(
            "app.kernel_api.httpx.AsyncClient.get",
            return_value=httpx.Response(200, json=response_payload),
        ):
            resp = asyncio.run(
                detect_models(
                    AdminDetectModelsRequest(api_base="https://api.example.com/v1", api_key="sk-test")
                )
            )
        self.assertEqual(resp.raw_count, 3)
        self.assertEqual([item.id for item in resp.models], ["gpt-4o", "gpt-4.1"])

    def test_detect_models_auth_failed(self) -> None:
        with patch("app.kernel_api.httpx.AsyncClient.get", return_value=httpx.Response(401, json={"error": "bad key"})):
            with self.assertRaises(Exception) as ctx:
                asyncio.run(detect_models(AdminDetectModelsRequest(api_base="https://api.example.com/v1", api_key="sk-test")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 401)
        self.assertEqual(getattr(ctx.exception, "detail", {}).get("code"), "AUTH_FAILED")

    def test_detect_models_timeout(self) -> None:
        with patch("app.kernel_api.httpx.AsyncClient.get", side_effect=httpx.TimeoutException("timeout")):
            with self.assertRaises(Exception) as ctx:
                asyncio.run(detect_models(AdminDetectModelsRequest(api_base="https://api.example.com/v1", api_key="sk-test")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 504)
        self.assertEqual(getattr(ctx.exception, "detail", {}).get("code"), "UPSTREAM_TIMEOUT")

    def test_detect_models_network_error(self) -> None:
        request = httpx.Request("GET", "https://api.example.com/v1/models")
        with patch(
            "app.kernel_api.httpx.AsyncClient.get",
            side_effect=httpx.RequestError("network", request=request),
        ):
            with self.assertRaises(Exception) as ctx:
                asyncio.run(detect_models(AdminDetectModelsRequest(api_base="https://api.example.com/v1", api_key="sk-test")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 502)
        self.assertEqual(getattr(ctx.exception, "detail", {}).get("code"), "UPSTREAM_NETWORK_ERROR")

    def test_detect_models_invalid_payload(self) -> None:
        with patch("app.kernel_api.httpx.AsyncClient.get", return_value=httpx.Response(200, json={"data": "bad"})):
            with self.assertRaises(Exception) as ctx:
                asyncio.run(detect_models(AdminDetectModelsRequest(api_base="https://api.example.com/v1", api_key="sk-test")))
        self.assertEqual(getattr(ctx.exception, "status_code", None), 502)
        self.assertEqual(getattr(ctx.exception, "detail", {}).get("code"), "UPSTREAM_INVALID_RESPONSE")

    def test_save_admin_llm_config_masks_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_path = Path(tmp) / "llm_runtime_config.json"
            with patch("app.admin_llm_config.RUNTIME_LLM_CONFIG_PATH", runtime_path):
                payload = save_admin_llm_config(
                    payload=AdminSaveLLMConfigRequest(
                        api_base="https://api.example.com/v1",
                        api_key="sk-secret-value",
                        model="gpt-4o",
                    )
                )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["config"]["answer"]["model"], "gpt-4o")
        self.assertIn("***", payload["config"]["answer"]["api_key_masked"])

    def test_save_admin_llm_config_accepts_full_stage_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_path = Path(tmp) / "llm_runtime_config.json"
            with patch("app.admin_llm_config.RUNTIME_LLM_CONFIG_PATH", runtime_path):
                payload = save_admin_llm_config(
                    payload=AdminSaveLLMConfigRequest(
                        answer={
                            "provider": "openai",
                            "api_base": "https://answer.example.com/v1",
                            "api_key": "answer-secret",
                            "model": "gpt-4.1-mini",
                        },
                        embedding={
                            "provider": "siliconflow",
                            "api_base": "https://emb.example.com/v1",
                            "api_key": "embedding-secret",
                            "model": "BAAI/bge-m3",
                        },
                        rerank={
                            "provider": "siliconflow",
                            "api_base": "https://rerank.example.com/v1",
                            "api_key": "rerank-secret",
                            "model": "Qwen/Qwen3-Reranker-8B",
                        },
                        rewrite={
                            "provider": "ollama",
                            "api_base": "http://127.0.0.1:11434/v1",
                            "api_key": "rewrite-secret",
                            "model": "Qwen2.5-3B-Instruct",
                        },
                        graph_entity={
                            "provider": "siliconflow",
                            "api_base": "https://graph.example.com/v1",
                            "api_key": "graph-secret",
                            "model": "Pro/deepseek-ai/DeepSeek-V3.2",
                        },
                    )
                )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["config"]["answer"]["model"], "gpt-4.1-mini")
        self.assertEqual(payload["config"]["embedding"]["model"], "BAAI/bge-m3")
        self.assertEqual(payload["config"]["rerank"]["model"], "Qwen/Qwen3-Reranker-8B")
        self.assertEqual(payload["config"]["rewrite"]["model"], "Qwen2.5-3B-Instruct")
        self.assertEqual(payload["config"]["graph_entity"]["model"], "Pro/deepseek-ai/DeepSeek-V3.2")
        self.assertIn("***", payload["config"]["rerank"]["api_key_masked"])

    def test_save_admin_llm_config_rejects_partial_stage_payload(self) -> None:
        with self.assertRaises(Exception) as ctx:
            save_admin_llm_config(
                payload=AdminSaveLLMConfigRequest(
                    answer={
                        "provider": "openai",
                        "api_base": "https://answer.example.com/v1",
                        "api_key": "answer-secret",
                        "model": "gpt-4.1-mini",
                    }
                )
            )
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)
        self.assertEqual(getattr(ctx.exception, "detail", {}).get("code"), "INVALID_PARAMS")
        self.assertIn("all required", getattr(ctx.exception, "detail", {}).get("message", ""))
        self.assertIsNone(getattr(ctx.exception, "detail", {}).get("stage"))

    def test_save_admin_llm_config_stage_validation_error_contains_stage(self) -> None:
        with self.assertRaises(Exception) as ctx:
            save_admin_llm_config(
                payload=AdminSaveLLMConfigRequest(
                    answer={
                        "provider": "openai",
                        "api_base": "https://answer.example.com/v1",
                        "api_key": "answer-secret",
                        "model": "gpt-4.1-mini",
                    },
                    embedding={
                        "provider": "siliconflow",
                        "api_base": "https://emb.example.com/v1",
                        "api_key": "",
                        "model": "BAAI/bge-m3",
                    },
                    rerank={
                        "provider": "siliconflow",
                        "api_base": "https://rerank.example.com/v1",
                        "api_key": "rerank-secret",
                        "model": "Qwen/Qwen3-Reranker-8B",
                    },
                    rewrite={
                        "provider": "ollama",
                        "api_base": "http://127.0.0.1:11434/v1",
                        "api_key": "rewrite-secret",
                        "model": "Qwen2.5-3B-Instruct",
                    },
                    graph_entity={
                        "provider": "siliconflow",
                        "api_base": "https://graph.example.com/v1",
                        "api_key": "graph-secret",
                        "model": "Pro/deepseek-ai/DeepSeek-V3.2",
                    },
                )
            )
        self.assertEqual(getattr(ctx.exception, "status_code", None), 400)
        self.assertEqual(getattr(ctx.exception, "detail", {}).get("code"), "INVALID_PARAMS")
        self.assertEqual(getattr(ctx.exception, "detail", {}).get("stage"), "embedding")
        self.assertIn("embedding.api_key is required", getattr(ctx.exception, "detail", {}).get("message", ""))

    def test_get_admin_llm_config_returns_full_stage_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_path = Path(tmp) / "llm_runtime_config.json"
            runtime_path.write_text(
                '{"answer":{"provider":"openai","api_base":"https://answer.example.com/v1","api_key":"ak","model":"a-model"},'
                '"embedding":{"provider":"siliconflow","api_base":"https://emb.example.com/v1","api_key":"ek","model":"e-model"},'
                '"rerank":{"provider":"siliconflow","api_base":"https://rr.example.com/v1","api_key":"rk","model":"r-model"},'
                '"rewrite":{"provider":"ollama","api_base":"http://127.0.0.1:11434/v1","api_key":"wk","model":"w-model"},'
                '"graph_entity":{"provider":"siliconflow","api_base":"https://graph.example.com/v1","api_key":"gk","model":"g-model"}}',
                encoding="utf-8",
            )
            with patch("app.admin_llm_config.RUNTIME_LLM_CONFIG_PATH", runtime_path):
                payload = get_admin_llm_config()
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["answer"]["api_base"], "https://answer.example.com/v1")
        self.assertEqual(payload["embedding"]["model"], "e-model")
        self.assertEqual(payload["rerank"]["provider"], "siliconflow")
        self.assertEqual(payload["rewrite"]["model"], "w-model")
        self.assertEqual(payload["graph_entity"]["model"], "g-model")
        self.assertIn("api_key_masked", payload["answer"])


class RuntimeLLMConfigPersistenceTests(unittest.TestCase):
    def test_save_and_load_runtime_llm_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "llm_runtime_config.json"
            saved = admin_llm_config.save_runtime_llm_config(
                api_base="https://api.example.com/v1",
                api_key="sk-test-value",
                model="gpt-4.1",
                path=path,
            )
            loaded, err = admin_llm_config.load_runtime_llm_config(path=path)
        self.assertIsNone(err)
        assert loaded is not None
        self.assertEqual(saved.answer.api_base, loaded.answer.api_base)
        self.assertEqual(saved.answer.model, loaded.answer.model)
        self.assertEqual(saved.answer.api_key, loaded.answer.api_key)

    def test_runtime_config_overrides_static_llm_route_with_legacy_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "default.yaml"
            cfg_path.write_text("answer_use_llm: true\nrewrite_use_llm: true\n", encoding="utf-8")
            runtime_path = Path(tmp) / "llm_runtime_config.json"
            runtime_path.write_text(
                '{"api_base":"https://api.override.com/v1","api_key":"sk-runtime","model":"gpt-4o-mini"}',
                encoding="utf-8",
            )
            with patch("app.admin_llm_config.RUNTIME_LLM_CONFIG_PATH", runtime_path):
                loaded, warnings = load_and_validate_config(cfg_path)
        self.assertEqual(loaded.answer_llm_api_base, "https://api.override.com/v1")
        self.assertEqual(loaded.rewrite_llm_api_base, "https://api.override.com/v1")
        self.assertEqual(loaded.answer_llm_model, "gpt-4o-mini")
        self.assertEqual(loaded.rewrite_llm_model, "gpt-4o-mini")
        self.assertEqual(loaded.answer_llm_api_key_env, f"{RUNTIME_LLM_API_KEY_ENV}_ANSWER")
        self.assertEqual(loaded.rewrite_llm_api_key_env, f"{RUNTIME_LLM_API_KEY_ENV}_REWRITE")
        self.assertEqual(loaded.graph_entity_llm_provider, "siliconflow")
        self.assertEqual(loaded.graph_entity_llm_base_url, "https://api.override.com/v1")
        self.assertEqual(loaded.graph_entity_llm_api_key_env, f"{RUNTIME_LLM_API_KEY_ENV}_GRAPH_ENTITY")
        self.assertEqual(warnings, [])

    def test_runtime_config_overrides_full_routes_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "default.yaml"
            cfg_path.write_text("dense_backend: embedding\n", encoding="utf-8")
            runtime_path = Path(tmp) / "llm_runtime_config.json"
            runtime_path.write_text(
                '{"answer":{"provider":"openai","api_base":"https://answer.example.com/v1","api_key":"ak","model":"a-model"},'
                '"embedding":{"provider":"siliconflow","api_base":"https://emb.example.com/v1","api_key":"ek","model":"e-model"},'
                '"rerank":{"provider":"siliconflow","api_base":"https://rr.example.com/v1","api_key":"rk","model":"r-model"},'
                '"rewrite":{"provider":"ollama","api_base":"http://127.0.0.1:11434/v1","api_key":"wk","model":"w-model"},'
                '"graph_entity":{"provider":"siliconflow","api_base":"https://graph.example.com/v1","api_key":"gk","model":"g-model"}}',
                encoding="utf-8",
            )
            with patch("app.admin_llm_config.RUNTIME_LLM_CONFIG_PATH", runtime_path):
                loaded, warnings = load_and_validate_config(cfg_path)
        self.assertEqual(loaded.embedding_api_base, "https://emb.example.com/v1")
        self.assertEqual(loaded.embedding_model, "e-model")
        self.assertEqual(loaded.rerank_api_base, "https://rr.example.com/v1")
        self.assertEqual(loaded.rerank_model, "r-model")
        self.assertEqual(loaded.rewrite_llm_api_base, "http://127.0.0.1:11434/v1")
        self.assertEqual(loaded.rewrite_llm_model, "w-model")
        self.assertEqual(loaded.graph_entity_llm_provider, "siliconflow")
        self.assertEqual(loaded.graph_entity_llm_base_url, "https://graph.example.com/v1")
        self.assertEqual(loaded.graph_entity_llm_model, "g-model")
        self.assertEqual(loaded.answer_llm_model, "a-model")
        self.assertNotEqual(loaded.rewrite_llm_model, loaded.answer_llm_model)
        self.assertEqual(warnings, [])

    def test_runtime_config_invalid_falls_back_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "default.yaml"
            cfg_path.write_text("answer_use_llm: true\n", encoding="utf-8")
            runtime_path = Path(tmp) / "llm_runtime_config.json"
            runtime_path.write_text('{"api_base":"not-a-url"}', encoding="utf-8")
            with patch("app.admin_llm_config.RUNTIME_LLM_CONFIG_PATH", runtime_path):
                loaded, warnings = load_and_validate_config(cfg_path)
        self.assertEqual(loaded.answer_llm_api_base, "https://api.siliconflow.cn/v1")
        self.assertTrue(any("Runtime LLM config ignored" in item for item in warnings))


class AdminCorsPreflightTests(unittest.TestCase):
    def test_detect_models_preflight_has_cors_headers(self) -> None:
        async def _send_options() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.options(
                    "/api/admin/detect-models",
                    headers={
                        "Origin": "http://localhost:3000",
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )

        resp = asyncio.run(_send_options())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertIn("POST", resp.headers.get("access-control-allow-methods", ""))


if __name__ == "__main__":
    unittest.main()
