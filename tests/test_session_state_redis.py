from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.session_state import append_turn_record, clear_session, load_dialog_state, load_history_window


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.last_setex: tuple[str, int, str] | None = None

    def ping(self) -> bool:
        return True

    def get(self, key: str):
        return self.kv.get(key)

    def set(self, key: str, value: str):
        self.kv[key] = value
        return True

    def setex(self, key: str, ttl: int, value: str):
        self.kv[key] = value
        self.last_setex = (key, ttl, value)
        return True

    def delete(self, key: str) -> int:
        if key in self.kv:
            self.kv.pop(key, None)
            return 1
        return 0


class SessionStateRedisTests(unittest.TestCase):
    def test_redis_backend_uses_key_prefix_and_ttl(self) -> None:
        fake = _FakeRedis()
        with patch("app.session_state._get_redis_client", return_value=fake):
            turn = append_turn_record(
                "s-1",
                user_input="RAG 是什么",
                standalone_query="RAG 是什么",
                answer="RAG 是检索增强生成。",
                cited_chunk_ids=["c:1"],
                decision="answer_with_evidence",
                output_warnings=[],
                backend="redis",
                redis_url="redis://fake:6379/0",
                redis_ttl_sec=120,
                redis_key_prefix="kb",
            )
            self.assertEqual(turn, 1)
            self.assertIsNotNone(fake.last_setex)
            assert fake.last_setex is not None
            self.assertEqual(fake.last_setex[0], "kb:session:s-1")
            self.assertEqual(fake.last_setex[1], 120)

            history, _ = load_history_window(
                "s-1",
                backend="redis",
                redis_url="redis://fake:6379/0",
                redis_key_prefix="kb",
                window_size=3,
            )
            self.assertTrue(history)
            self.assertEqual(history[0].get("user_input"), "RAG 是什么")

            self.assertEqual(load_dialog_state("s-1", backend="redis", redis_url="redis://fake:6379/0", redis_key_prefix="kb"), "normal")

            self.assertTrue(clear_session("s-1", backend="redis", redis_url="redis://fake:6379/0", redis_key_prefix="kb"))
            self.assertIsNone(fake.get("kb:session:s-1"))

    def test_redis_fallback_to_file_keeps_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "session_store.json"
            store.write_text(
                json.dumps(
                    {
                        "sessions": {
                            "legacy": {
                                "turns": [
                                    {
                                        "turn_number": 1,
                                        "user_input": "老问题",
                                        "standalone_query": "老问题",
                                        "answer": "老回答",
                                        "cited_chunk_ids": [],
                                        "decision": "answer_with_evidence",
                                        "output_warnings": [],
                                        "entity_mentions": ["RAG"],
                                        "topic_anchors": ["RAG"],
                                        "transient_constraints": [],
                                        "clarify_count_for_topic": 0,
                                    }
                                ]
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch("app.session_state._get_redis_client", return_value=None):
                history, _ = load_history_window(
                    "legacy",
                    store_path=store,
                    backend="redis",
                    redis_fallback_to_file=True,
                )
                self.assertTrue(history)
                self.assertEqual(history[0].get("user_input"), "老问题")

                append_turn_record(
                    "legacy",
                    user_input="第二问",
                    standalone_query="第二问",
                    answer="第二答",
                    cited_chunk_ids=[],
                    decision="need_scope_clarification",
                    output_warnings=[],
                    store_path=store,
                    backend="redis",
                    redis_fallback_to_file=True,
                )
            payload = json.loads(store.read_text(encoding="utf-8"))
            turns = payload["sessions"]["legacy"]["turns"]
            self.assertEqual(len(turns), 2)
            self.assertEqual(payload["sessions"]["legacy"]["state"]["dialog_state"], "waiting_followup")

    def test_redis_concurrent_sessions_isolation_and_state_recovery(self) -> None:
        fake = _FakeRedis()
        with patch("app.session_state._get_redis_client", return_value=fake):
            append_turn_record(
                "s-a",
                user_input="问题A1",
                standalone_query="问题A1",
                answer="请补充范围",
                cited_chunk_ids=[],
                decision="need_scope_clarification",
                output_warnings=[],
                backend="redis",
                redis_url="redis://fake:6379/0",
                redis_key_prefix="kb",
            )
            append_turn_record(
                "s-b",
                user_input="问题B1",
                standalone_query="问题B1",
                answer="回答B1",
                cited_chunk_ids=["c:b1"],
                decision="answer_with_evidence",
                output_warnings=[],
                backend="redis",
                redis_url="redis://fake:6379/0",
                redis_key_prefix="kb",
            )
            append_turn_record(
                "s-a",
                user_input="问题A2",
                standalone_query="问题A2",
                answer="回答A2",
                cited_chunk_ids=["c:a2"],
                decision="answer_with_evidence",
                output_warnings=[],
                clear_pending_clarify=True,
                backend="redis",
                redis_url="redis://fake:6379/0",
                redis_key_prefix="kb",
            )

            a_history, _ = load_history_window(
                "s-a",
                backend="redis",
                redis_url="redis://fake:6379/0",
                redis_key_prefix="kb",
                window_size=10,
                include_layered_memory=False,
            )
            b_history, _ = load_history_window(
                "s-b",
                backend="redis",
                redis_url="redis://fake:6379/0",
                redis_key_prefix="kb",
                window_size=10,
                include_layered_memory=False,
            )
            self.assertEqual(len(a_history), 2)
            self.assertEqual(len(b_history), 1)
            self.assertEqual(str(a_history[-1].get("answer")), "回答A2")
            self.assertEqual(str(b_history[-1].get("answer")), "回答B1")
            self.assertEqual(
                load_dialog_state("s-a", backend="redis", redis_url="redis://fake:6379/0", redis_key_prefix="kb"),
                "normal",
            )
            self.assertEqual(
                load_dialog_state("s-b", backend="redis", redis_url="redis://fake:6379/0", redis_key_prefix="kb"),
                "normal",
            )


if __name__ == "__main__":
    unittest.main()
