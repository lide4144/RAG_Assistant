from __future__ import annotations

import unittest
from unittest.mock import patch

from app.llm_client import (
    LLMCallResult,
    call_chat_completion,
    clear_llm_event_callbacks,
    register_llm_event_callback,
)
from app import llm_routing


class LLMClientRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        llm_routing._COOLDOWN_UNTIL.clear()
        llm_routing._FAILURE_COUNTS.clear()
        clear_llm_event_callbacks()

    def test_primary_failure_falls_back_to_secondary_model(self) -> None:
        first = LLMCallResult(
            ok=False,
            content=None,
            reason="timeout",
            status_code=None,
            attempts_used=1,
            max_retries=0,
            elapsed_ms=12,
            timestamp="2026-03-01T00:00:00Z",
            provider_used="openai",
            model_used="primary",
            error_category="timeout",
        )
        second = LLMCallResult(
            ok=True,
            content="ok",
            reason=None,
            status_code=200,
            attempts_used=1,
            max_retries=0,
            elapsed_ms=18,
            timestamp="2026-03-01T00:00:00Z",
            provider_used="openai",
            model_used="backup",
        )

        with patch("app.llm_client._call_completion_once", side_effect=[first, second]):
            out = call_chat_completion(
                provider="openai",
                model="primary",
                api_key="k1",
                api_base="https://api.example.com/v1",
                fallback_provider="openai",
                fallback_model="backup",
                fallback_api_key="k2",
                fallback_api_base="https://api.example.com/v1",
                system_prompt="s",
                user_prompt="u",
                timeout_ms=100,
                max_retries=0,
                router_retry=0,
            )

        self.assertTrue(out.ok)
        self.assertEqual(out.content, "ok")
        self.assertEqual(out.attempts_used, 2)
        self.assertEqual(out.provider_used, "openai")
        self.assertEqual(out.model_used, "backup")
        self.assertEqual(out.fallback_reason, "timeout")

    def test_route_enters_cooldown_after_failure_threshold(self) -> None:
        fail = LLMCallResult(
            ok=False,
            content=None,
            reason="timeout",
            status_code=None,
            attempts_used=1,
            max_retries=0,
            elapsed_ms=10,
            timestamp="2026-03-01T00:00:00Z",
            provider_used="openai",
            model_used="primary",
            error_category="timeout",
        )
        with patch("app.llm_client._call_completion_once", return_value=fail):
            out1 = call_chat_completion(
                provider="openai",
                model="primary",
                api_key="k1",
                api_base="https://api.example.com/v1",
                system_prompt="s",
                user_prompt="u",
                timeout_ms=100,
                max_retries=0,
                router_retry=0,
                router_failure_threshold=1,
                router_cooldown_sec=60,
            )
        self.assertFalse(out1.ok)
        self.assertEqual(out1.reason, "timeout")

        with patch("app.llm_client._call_completion_once") as mocked_once:
            out2 = call_chat_completion(
                provider="openai",
                model="primary",
                api_key="k1",
                api_base="https://api.example.com/v1",
                system_prompt="s",
                user_prompt="u",
                timeout_ms=100,
                max_retries=0,
                router_retry=0,
                router_failure_threshold=1,
                router_cooldown_sec=60,
            )

        mocked_once.assert_not_called()
        self.assertFalse(out2.ok)
        self.assertEqual(out2.reason, "cooldown_active")

    def test_event_callback_receives_failure_and_fallback_success(self) -> None:
        events: list[dict[str, object]] = []
        register_llm_event_callback(events.append)
        first = LLMCallResult(
            ok=False,
            content=None,
            reason="timeout",
            status_code=None,
            attempts_used=1,
            max_retries=0,
            elapsed_ms=12,
            timestamp="2026-03-01T00:00:00Z",
            provider_used="openai",
            model_used="primary",
            error_category="timeout",
        )
        second = LLMCallResult(
            ok=True,
            content="ok",
            reason=None,
            status_code=200,
            attempts_used=1,
            max_retries=0,
            elapsed_ms=18,
            timestamp="2026-03-01T00:00:00Z",
            provider_used="openai",
            model_used="backup",
        )
        with patch("app.llm_client._call_completion_once", side_effect=[first, second]):
            out = call_chat_completion(
                provider="openai",
                model="primary",
                api_key="k1",
                api_base="https://api.example.com/v1",
                fallback_provider="openai",
                fallback_model="backup",
                fallback_api_key="k2",
                fallback_api_base="https://api.example.com/v1",
                system_prompt="s",
                user_prompt="u",
                timeout_ms=100,
                max_retries=0,
                router_retry=0,
            )
        self.assertTrue(out.ok)
        names = [str(e.get("event")) for e in events]
        self.assertIn("request_failure", names)
        self.assertIn("fallback_attempt", names)
        self.assertIn("request_success", names)

    def test_network_error_triggers_fallback_success(self) -> None:
        first = LLMCallResult(
            ok=False,
            content=None,
            reason="network_error",
            status_code=None,
            attempts_used=1,
            max_retries=0,
            elapsed_ms=10,
            timestamp="2026-03-01T00:00:00Z",
            provider_used="openai",
            model_used="primary",
            error_category="network",
        )
        second = LLMCallResult(
            ok=True,
            content="backup-ok",
            reason=None,
            status_code=200,
            attempts_used=1,
            max_retries=0,
            elapsed_ms=17,
            timestamp="2026-03-01T00:00:00Z",
            provider_used="openai",
            model_used="backup",
        )
        with patch("app.llm_client._call_completion_once", side_effect=[first, second]):
            out = call_chat_completion(
                provider="openai",
                model="primary",
                api_key="k1",
                api_base="https://api.primary.example.com/v1",
                fallback_provider="openai",
                fallback_model="backup",
                fallback_api_key="k2",
                fallback_api_base="https://api.backup.example.com/v1",
                system_prompt="s",
                user_prompt="u",
                timeout_ms=100,
                max_retries=0,
                router_retry=0,
            )
        self.assertTrue(out.ok)
        self.assertEqual(out.content, "backup-ok")
        self.assertEqual(out.model_used, "backup")
        self.assertEqual(out.fallback_reason, "network_error")


if __name__ == "__main__":
    unittest.main()
