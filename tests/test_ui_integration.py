from __future__ import annotations

import json
import unittest

from streamlit.testing.v1 import AppTest

from app.paths import DATA_DIR

def _report_payload(*, source: str = "graph_expand", history_used_turns: int = 0) -> dict:
    return {
        "question": "原始问题",
        "rewrite_rule_query": "rewrite query",
        "calibrated_query": "calibrated query",
        "intent_router_enabled": True,
        "intent_type": "style_control",
        "anchor_query": "Transformer architecture",
        "topic_query_source": "anchor_query",
        "decision": "answer",
        "decision_reason": "evidence ok",
        "output_warnings": [],
        "history_used_turns": history_used_turns,
        "answer": "这是回答 [1]",
        "topic_name": "专题A",
        "answer_citations": [{"chunk_id": "c:1", "paper_id": "p1", "section_page": "p.1"}],
        "evidence_grouped": [
            {
                "paper_id": "p1",
                "paper_title": "Paper One",
                "evidence": [
                    {
                        "chunk_id": "c:1",
                        "score_retrieval": 0.91,
                        "score_rerank": 0.87,
                        "source": source,
                        "quote": "evidence quote",
                    }
                ],
            }
        ],
    }


def _trace_payload() -> dict:
    return {
        "rewrite_query": "rewrite query",
        "calibrated_query": "calibrated query",
        "intent_router_enabled": True,
        "intent_type": "style_control",
        "anchor_query": "Transformer architecture",
        "topic_query_source": "anchor_query",
        "decision": "answer",
        "output_warnings": [],
    }


def _ui_wrapper_script(report: dict, trace: dict, *, include_navigation: bool = False) -> str:
    report_json = json.dumps(report, ensure_ascii=False)
    trace_json = json.dumps(trace, ensure_ascii=False)
    nav_patch = ""
    if include_navigation:
        nav_patch = """
ui._build_paper_navigation = lambda report: [
    {
        "paper_id": "p1",
        "title": "Paper One",
        "one_paragraph_summary": "这是论文级摘要导航信息。",
        "key_points": ["要点一", "要点二"],
    }
]
"""
    return f"""
import json
import streamlit as st
import app.ui as ui

REPORT = json.loads({report_json!r})
TRACE = json.loads({trace_json!r})

def _fake_run_turn(question, session_id, **kwargs):
    return dict(REPORT), dict(TRACE), ""

def _fake_clear_session(session_id, store_path):
    st.session_state["__clear_called_with"] = [session_id, store_path]
    return True

ui._run_turn = _fake_run_turn
ui.clear_session = _fake_clear_session
{nav_patch}
ui.main()
"""


def _ui_wrapper_streaming_script() -> str:
    report = _report_payload()
    report["answer"] = "流式回答完成 [1]"
    trace = _trace_payload()
    report_json = json.dumps(report, ensure_ascii=False)
    trace_json = json.dumps(trace, ensure_ascii=False)
    return f"""
import json
import app.ui as ui

REPORT = json.loads({report_json!r})
TRACE = json.loads({trace_json!r})

def _fake_run_turn(question, session_id, **kwargs):
    cb = kwargs.get("on_stream_delta")
    if callable(cb):
        cb("流式")
        cb("回答")
    return dict(REPORT), dict(TRACE), ""

ui._run_turn = _fake_run_turn
ui.main()
"""


def _ui_wrapper_timeout_script() -> str:
    return """
import app.ui as ui

def _fake_run_turn(question, session_id, **kwargs):
    raise TimeoutError("simulated timeout")

ui._run_turn = _fake_run_turn
ui.main()
"""


def _ui_wrapper_timeout_then_success_script() -> str:
    report = _report_payload()
    report_json = json.dumps(report, ensure_ascii=False)
    trace_json = json.dumps(_trace_payload(), ensure_ascii=False)
    return f"""
import json
import app.ui as ui

REPORT = json.loads({report_json!r})
TRACE = json.loads({trace_json!r})

def _fake_run_turn(question, session_id, **kwargs):
    if "超时" in str(question):
        raise TimeoutError("simulated timeout")
    return dict(REPORT), dict(TRACE), ""

ui._run_turn = _fake_run_turn
ui.main()
"""


def _ui_wrapper_library_catalog_script() -> str:
    return """
import streamlit as st
import app.ui as ui

def _fake_load_papers():
    return [
        {
            "paper_id": "p1",
            "title": "Alpha Paper",
            "path": "/tmp/a.pdf",
            "source_type": "pdf",
            "source_uri": "pdf://sha1/a1",
            "imported_at": "2026-02-28T08:00:00+00:00",
            "status": "active",
            "fingerprint": "a1",
        },
        {
            "paper_id": "p2",
            "title": "Beta URL",
            "path": "https://example.com/b",
            "source_type": "url",
            "source_uri": "https://example.com/b",
            "imported_at": "2026-02-28T07:00:00+00:00",
            "status": "active",
            "fingerprint": "b2",
        },
    ]

def _fake_load_topics():
    return {"专题A": ["p1"], "专题B": []}

def _fake_save_topics(topics):
    st.session_state["__saved_topics"] = topics

ui.load_papers = _fake_load_papers
ui.load_topics = _fake_load_topics
ui.save_topics = _fake_save_topics
ui._load_paper_summary_lookup = lambda: {
    "p1": {"one_paragraph_summary": "alpha summary", "key_points": ["k1", "k2"]},
    "p2": {"one_paragraph_summary": "beta summary", "key_points": ["k3"]},
}
st.session_state["workspace"] = "Library"
ui.main()
"""


def _ui_wrapper_library_auto_import_summary_script() -> str:
    return """
import streamlit as st
import app.ui as ui

class _FakeUpload:
    name = "demo.pdf"
    def getvalue(self):
        return b"%PDF-1.4\\n%fake\\n"

def _fake_button(label, *args, **kwargs):
    if label == "开始导入论文":
        return True
    return False

ui.load_papers = lambda: []
ui.load_topics = lambda: {}
ui.run_import_workflow = lambda **kwargs: {
    "ok": True,
    "success_count": 1,
    "failed_count": 0,
    "failure_reasons": [],
    "import_summary": {"added": 1, "skipped": 2, "conflicts": 0, "failed": 1},
    "index_stage": {"status": "success", "duration_sec": 1.23},
    "next_steps": ["下一步A"],
    "message": "done",
}
ui.st.file_uploader = lambda *args, **kwargs: [_FakeUpload()]
ui.st.button = _fake_button
st.session_state["workspace"] = "Library"
ui.main()
"""


class UIIntegrationTests(unittest.TestCase):
    def test_ui_script_can_bootstrap_via_streamlit_runner(self) -> None:
        at = AppTest.from_file("app/ui.py")
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertGreaterEqual(len(at.chat_input), 1)

    def test_citation_click_links_to_sidebar_and_graph_expand_badge_visible(self) -> None:
        at = AppTest.from_string(_ui_wrapper_script(_report_payload(source="graph_expand"), _trace_payload()))
        at.run()
        at.chat_input[0].set_value("测试问题").run()
        citation_button = next(btn for btn in at.button if btn.label == "[1]")
        citation_button.click().run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("证据来源" in str(item.label) for item in at.expander))

    def test_clear_session_then_first_turn_history_zero_has_no_leak_warning(self) -> None:
        at = AppTest.from_string(_ui_wrapper_script(_report_payload(history_used_turns=0), _trace_payload()))
        at.run()
        original_session_id = str(at.session_state["session_id"])

        clear_button = next(btn for btn in at.button if btn.label == "开启新对话")
        clear_button.click().run()
        clear_called_with = at.session_state["__clear_called_with"]
        self.assertEqual(clear_called_with[0], original_session_id)
        self.assertEqual(clear_called_with[1], str(DATA_DIR / "session_store.json"))

        at.chat_input[0].set_value("清空后首问").run()

        self.assertEqual(len(at.exception), 0)
        self.assertFalse(any("history_used_turns 非 0" in w.value for w in at.warning))
        self.assertFalse(bool(at.session_state["expect_zero_history_turn"]))

    def test_inspector_shows_intent_router_fields(self) -> None:
        at = AppTest.from_string(_ui_wrapper_script(_report_payload(), _trace_payload()))
        at.run()
        at.checkbox[0].check().run()
        at.chat_input[0].set_value("测试问题").run()

        sidebar_lines = [md.value for md in at.sidebar.markdown]
        self.assertTrue(any("intent_type" in line for line in sidebar_lines))
        self.assertTrue(any("topic_query_source" in line for line in sidebar_lines))

    def test_chat_shows_paper_level_navigation_summary(self) -> None:
        at = AppTest.from_string(_ui_wrapper_script(_report_payload(), _trace_payload(), include_navigation=True))
        at.run()
        at.chat_input[0].set_value("测试问题").run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("摘要层" in str(item.label) for item in at.expander))

    def test_ui_logs_only_present_in_dev_panel_mode(self) -> None:
        at = AppTest.from_string(_ui_wrapper_script(_report_payload(), _trace_payload()))
        at.run()
        at.chat_input[0].set_value("默认模式问题").run()
        traces = at.session_state["turn_traces"]
        self.assertFalse("ui_logs" in traces[-1]["trace"])

        at.checkbox[0].check().run()
        at.chat_input[0].set_value("开发者模式问题").run()
        traces = at.session_state["turn_traces"]
        self.assertTrue("ui_logs" in traces[-1]["trace"])

    def test_ui_handles_turn_timeout_with_recoverable_error(self) -> None:
        at = AppTest.from_string(_ui_wrapper_timeout_script())
        at.run()
        at.chat_input[0].set_value("触发超时").run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("推理过程中出现错误" in str(item.value) for item in at.error))

    def test_ui_consumes_stream_delta_callback(self) -> None:
        at = AppTest.from_string(_ui_wrapper_streaming_script())
        at.run()
        at.chat_input[0].set_value("流式测试").run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("流式回答完成" in str(item.value) for item in at.markdown))

    def test_ui_keeps_history_after_timeout_and_allows_next_turn(self) -> None:
        at = AppTest.from_string(_ui_wrapper_timeout_then_success_script())
        at.run()
        at.chat_input[0].set_value("先触发超时").run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("推理过程中出现错误" in str(item.value) for item in at.error))
        # 失败后应至少保留用户消息，不丢会话历史
        self.assertGreaterEqual(len(at.session_state["chat_messages"]), 1)

        at.chat_input[0].set_value("再来一轮").run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("这是回答" in str(item.value) for item in at.markdown))
        # 第二轮成功后历史应包含多条消息（未被错误回合清空）
        self.assertGreaterEqual(len(at.session_state["chat_messages"]), 3)

    def test_library_catalog_supports_search_filter_and_detail(self) -> None:
        at = AppTest.from_string(_ui_wrapper_library_catalog_script())
        at.run()
        search = next(item for item in at.text_input if item.label == "搜索论文（标题/来源）")
        search.set_value("alpha").run()
        topic_filter = next(item for item in at.selectbox if item.label == "专题筛选")
        topic_filter.set_value("专题A").run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("目录命中 1 / 2" in str(item.value) for item in at.caption))
        self.assertTrue(any(item.label == "查看详情" for item in at.expander))

    def test_library_batch_topic_management_updates_mapping(self) -> None:
        at = AppTest.from_string(_ui_wrapper_library_catalog_script())
        at.run()
        picker = next(item for item in at.multiselect if item.label == "选择论文（可多选）")
        picker.set_value(["p2"]).run()
        target_topic = next(item for item in at.selectbox if item.label == "目标专题")
        target_topic.set_value("专题B").run()
        action = next(item for item in at.radio if item.label == "操作")
        action.set_value("加入专题").run()
        apply_button = next(btn for btn in at.button if btn.label == "应用批量变更")
        apply_button.click().run()

        self.assertEqual(len(at.exception), 0)
        saved = at.session_state["__saved_topics"]
        self.assertIn("p2", saved.get("专题B", []))

    def test_library_import_summary_metrics_are_rendered(self) -> None:
        at = AppTest.from_string(_ui_wrapper_library_auto_import_summary_script())
        at.run()
        labels = [item.label for item in at.metric]
        self.assertEqual(len(at.exception), 0)
        self.assertIn("新增", labels)
        self.assertIn("已存在跳过", labels)
        self.assertIn("冲突", labels)
        self.assertIn("失败", labels)
        self.assertTrue(any("知识库准备阶段" in str(item.value) for item in at.caption))


if __name__ == "__main__":
    unittest.main()
