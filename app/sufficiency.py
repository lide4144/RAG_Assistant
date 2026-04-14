from __future__ import annotations

from typing import Any

from app.evidence_judge import judge_semantic_evidence
from app.planner_policy import build_constraint_envelope

NOISY_CONTENT_TYPES = {"front_matter", "reference"}


def _flatten_evidence(evidence_grouped: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for group in evidence_grouped:
        for item in group.get("evidence", []):
            if isinstance(item, dict):
                flat.append(item)
    return flat


def _is_insufficient_evidence(
    evidence_grouped: list[dict[str, Any]],
    *,
    min_evidence: int = 1,
) -> bool:
    flat = _flatten_evidence(evidence_grouped)
    if len(flat) < min_evidence:
        return True
    noisy_only = all(
        (item.get("content_type", "body") or "body").lower() in NOISY_CONTENT_TYPES
        for item in flat
    )
    return noisy_only


def _is_low_confidence_evidence(
    evidence_grouped: list[dict[str, Any]],
    *,
    low_confidence_threshold: int = 2,
) -> bool:
    """Check if evidence count indicates low confidence (below threshold but >= 1).

    Returns True if evidence count is >= 1 but < low_confidence_threshold.
    This triggers the low_confidence_with_model_knowledge mode.
    """
    flat = _flatten_evidence(evidence_grouped)
    count = len(flat)
    # Low confidence: has at least 1 evidence but less than threshold
    return 1 <= count < low_confidence_threshold


def _count_evidence(evidence_grouped: list[dict[str, Any]]) -> int:
    """计算证据总数"""
    return len(_flatten_evidence(evidence_grouped))


def _has_traceable_evidence(evidence_grouped: list[dict[str, Any]]) -> bool:
    for item in _flatten_evidence(evidence_grouped):
        if str(item.get("quote", "")).strip():
            return True
    return False


def _build_advice_message(
    evidence_count: int,
    has_traceable: bool,
    topic_aligned: bool,
    missing_aspects: list[str],
    open_summary_intent: bool = False,
) -> dict[str, Any]:
    """构建建议信息"""
    advice = {
        "type": "none",  # none | info | caution | warning
        "append_to_answer": False,
        "messages": [],
        "suggested_actions": [],
    }

    # 证据为0：严重警告
    if evidence_count == 0:
        advice["type"] = "warning"
        advice["append_to_answer"] = True
        advice["messages"] = [
            "⚠️ 当前问题在知识库中未找到相关证据。",
            "以下回答基于模型的一般知识，可能不够准确。",
        ]
        advice["suggested_actions"] = [
            "补充论文标题、作者、年份或会议等线索",
            "确认知识库是否包含相关主题",
        ]
        return advice

    # 只有噪声类证据
    if evidence_count > 0 and not has_traceable:
        advice["type"] = "caution"
        advice["append_to_answer"] = True
        advice["messages"] = [
            "⚠️ 检索到的证据缺少可追溯的引用内容（仅找到参考文献或元数据）。",
            "回答可能缺乏直接的文本支持。",
        ]
        advice["suggested_actions"] = [
            "补充包含具体内容的证据片段",
            "检查检索范围是否包含正文内容",
        ]
        return advice

    # 证据有限（仅1条）
    if evidence_count == 1:
        advice["type"] = "caution"
        advice["append_to_answer"] = True
        advice["messages"] = ["⚠️ 当前回答基于有限的证据（仅1条），建议谨慎参考。"]
        if open_summary_intent:
            advice["messages"].append("开放式总结需要更多主题线索以获得全面视角。")
        advice["suggested_actions"] = [
            "补充更多相关论文或实验证据",
            "明确更具体的问题范围",
        ]
        return advice

    # 主题不匹配
    if not topic_aligned:
        advice["type"] = "warning"
        advice["append_to_answer"] = True
        advice["messages"] = [
            "⚠️ 现有证据与问题主题不完全匹配。",
            "回答可能无法准确回应您的核心问题。",
        ]
        advice["suggested_actions"] = [
            "补充与问题更相关的论文线索",
            "调整问题表述以匹配知识库内容",
        ]
        return advice

    # 有缺失方面
    if missing_aspects:
        advice["type"] = "info"
        advice["append_to_answer"] = True
        advice["messages"] = [
            f"ℹ️ 当前证据覆盖了问题的部分方面，但未涉及：{', '.join(missing_aspects[:3])}",
            "回答仅基于现有证据，可能不够全面。",
        ]
        if len(missing_aspects) > 3:
            advice["messages"][0] += f" 等 {len(missing_aspects)} 个方面"
        advice["suggested_actions"] = [f"补充关于 [{missing_aspects[0]}] 的具体信息"]
        return advice

    # 证据充足
    if evidence_count >= 3:
        advice["type"] = "none"
        advice["append_to_answer"] = False
        return advice

    # 默认：证据一般（2条）
    if evidence_count == 2:
        advice["type"] = "info"
        advice["append_to_answer"] = False  # 2条证据不强制显示提示
        advice["messages"] = ["ℹ️ 当前回答基于2条证据，如有需要可补充更多线索。"]
        return advice

    return advice


def run_sufficiency_gate(
    *,
    question: str,
    query_used: str | None = None,
    topic_query_source: str = "user_query",
    topic_query_text: str | None = None,
    open_summary_intent: bool = False,
    scope_mode: str,
    evidence_grouped: list[dict[str, Any]],
    config: Any,
    clarify_count_for_topic: int = 0,
    clarify_limit: int = 2,
    force_partial_answer_on_limit: bool = True,
) -> dict[str, Any]:
    """
    Sufficiency Gate - 后置建议模式

    不再强制拦截或替换回答，而是：
    1. 评估证据质量和匹配度
    2. 生成建议信息
    3. 由调用方决定在回答后追加提示

    Returns:
        dict: 包含建议信息的报告
    """
    enabled = bool(getattr(config, "sufficiency_gate_enabled", True))
    evidence_count = _count_evidence(evidence_grouped)
    has_traceable = _has_traceable_evidence(evidence_grouped)

    # 基础报告结构
    report: dict[str, Any] = {
        "enabled": enabled,
        "decision": "answer",  # 默认允许回答，不再强制拦截
        "answer_mode": "evidence_only"
        if evidence_count >= 2
        else "low_confidence_with_model_knowledge",
        "allows_model_knowledge": evidence_count < 2,
        "confidence_level": "high"
        if evidence_count >= 3
        else ("medium" if evidence_count >= 2 else "low"),
        "evidence_count": evidence_count,
        "has_traceable_evidence": has_traceable,
        "evidence_quality": "high"
        if evidence_count >= 3 and has_traceable
        else ("medium" if evidence_count >= 2 and has_traceable else "low"),
        "reason": "证据评估完成。",
        "reason_code": "evaluation_complete",
        "severity": "info",
        "clarify_questions": [],
        "output_warnings": [],
        "triggered_rules": [],
        "allows_partial_answer": True,  # 默认允许部分回答
        "guardrail_blocked": False,  # 不再强制拦截
        "constraints_envelope": None,
        "semantic_policy": "balanced",
        "semantic_threshold": 0.25,
        "topic_query_source": topic_query_source,
        "topic_query_text": str(topic_query_text or query_used or question),
        "missing_aspects": [],
        "coverage_summary": {},
        "judge_source": None,
        "judge_status": "not_run",
        "validator_source": "deterministic_validator_v1",
        "validator_summary": {"passed": True, "checks": []},
        "clarify_count": max(0, int(clarify_count_for_topic)),
        "clarify_limit_hit": False,
        "forced_partial_answer": False,
        # 新增：建议信息
        "advice": {
            "type": "none",
            "append_to_answer": False,
            "messages": [],
            "suggested_actions": [],
        },
        # 新增：原始评估结果（供调用方参考）
        "evaluation": {
            "is_insufficient": _is_insufficient_evidence(evidence_grouped),
            "is_noisy_only": evidence_count > 0 and not has_traceable,
            "topic_aligned": True,  # 将在语义判断后更新
            "scope_mode": scope_mode,
        },
    }

    if not enabled:
        report["reason"] = "Sufficiency Gate 已关闭。"
        return report

    # 范围澄清模式：仍需要澄清，但不强制拦截回答
    if scope_mode == "clarify_scope":
        report["reason"] = "问题范围不明确，建议补充论文范围。"
        report["reason_code"] = "scope_clarify_suggested"
        report["severity"] = "warning"
        report["clarify_questions"] = ["请提供论文标题、作者、年份或会议等线索。"]
        report["triggered_rules"].append("scope_clarify_suggested")
        report["advice"] = {
            "type": "warning",
            "append_to_answer": True,
            "messages": [
                "⚠️ 未指定具体论文范围。",
                "为获得更准确的回答，建议补充论文信息。",
            ],
            "suggested_actions": ["提供论文标题、作者、年份或会议等线索"],
        }
        return report

    # 基础验证：证据数量和质量
    if _is_insufficient_evidence(evidence_grouped):
        report["validator_summary"] = {
            "passed": False,
            "checks": ["evidence_count_or_quality"],
        }
        report["evaluation"]["is_insufficient"] = True

        # 证据为0或只有噪声：生成警告建议，但不强制拦截
        if evidence_count == 0:
            report["reason"] = "未找到相关证据。"
            report["reason_code"] = "no_evidence_found"
            report["severity"] = "warning"
            report["triggered_rules"].append("no_evidence_found")
            report["output_warnings"].append("no_evidence_found")
            report["advice"] = _build_advice_message(
                evidence_count=0,
                has_traceable=False,
                topic_aligned=False,
                missing_aspects=[],
            )
            return report

    # 检查可追溯性
    if not has_traceable:
        report["reason"] = "证据缺少可追溯引用。"
        report["reason_code"] = "traceable_evidence_missing"
        report["severity"] = "warning"
        report["triggered_rules"].append("traceable_evidence_missing")
        report["output_warnings"].append("traceable_evidence_missing")
        report["advice"] = _build_advice_message(
            evidence_count=evidence_count,
            has_traceable=False,
            topic_aligned=True,
            missing_aspects=[],
        )
        return report

    # 低置信度模式（1条证据）
    if evidence_count == 1 and not open_summary_intent:
        report["answer_mode"] = "low_confidence_with_model_knowledge"
        report["allows_model_knowledge"] = True
        report["confidence_level"] = "low"
        report["reason"] = "证据有限（仅1条），将结合模型知识给出最佳回答。"
        report["reason_code"] = "low_evidence_with_model_knowledge"
        report["severity"] = "info"
        report["triggered_rules"].append("low_evidence_with_model_knowledge")
        report["advice"] = _build_advice_message(
            evidence_count=1,
            has_traceable=True,
            topic_aligned=True,
            missing_aspects=[],
        )
        return report

    # 开放式总结 + 1条证据
    if evidence_count == 1 and open_summary_intent:
        report["reason"] = "开放式总结需要更多主题线索。"
        report["reason_code"] = "open_summary_needs_more_evidence"
        report["severity"] = "info"
        report["triggered_rules"].append("open_summary_needs_more_evidence")
        report["advice"] = _build_advice_message(
            evidence_count=1,
            has_traceable=True,
            topic_aligned=True,
            missing_aspects=[],
            open_summary_intent=True,
        )
        return report

    # 语义证据判断
    query_used_text = str(topic_query_text or query_used or "").strip() or question
    judge = judge_semantic_evidence(
        question=question,
        topic_query_text=query_used_text,
        evidence_grouped=evidence_grouped,
        config=config,
    )

    semantic_threshold = judge.get("semantic_threshold")
    report["semantic_policy"] = str(judge.get("semantic_policy") or "balanced")
    report["semantic_threshold"] = float(
        semantic_threshold if semantic_threshold is not None else 0.25
    )
    report["missing_aspects"] = [
        str(x).strip() for x in judge.get("missing_aspects", []) if str(x).strip()
    ]
    report["coverage_summary"] = judge.get("coverage_summary") or {}
    report["judge_source"] = judge.get("judge_source")
    report["judge_status"] = str(judge.get("judge_status") or "ok")
    report["output_warnings"] = [
        str(x).strip() for x in (judge.get("output_warnings") or []) if str(x).strip()
    ]
    report["evaluation"]["topic_aligned"] = judge.get("coverage_summary", {}).get(
        "topic_aligned", True
    )

    # 判断服务错误
    if report["judge_status"] in {"error", "unavailable"}:
        report["reason"] = "语义证据判别服务暂时不可用。"
        report["reason_code"] = "judge_service_unavailable"
        report["severity"] = "warning"
        report["triggered_rules"].append("judge_service_unavailable")
        report["output_warnings"].append("judge_service_unavailable")
        # 当 judge 服务不可用时，降低置信度和证据质量（缺少深度语义验证）
        report["confidence_level"] = "low"
        report["evidence_quality"] = "medium" if evidence_count >= 2 else "low"
        report["advice"] = {
            "type": "caution",
            "append_to_answer": True,
            "messages": [
                "⚠️ 证据质量评估服务暂时不可用。",
                "回答基于基础检索结果，未经过深度语义验证。",
            ],
            "suggested_actions": [
                "稍后重试以获得更准确的评估",
                "自行核验回答中的关键结论",
            ],
        }
        return report

    # 处理判断结果
    decision_hint = str(judge.get("decision_hint") or "answer")

    if decision_hint == "mismatch":
        report["reason"] = "证据与问题主题不完全匹配。"
        report["reason_code"] = "topic_mismatch"
        report["severity"] = "warning"
        report["triggered_rules"].append("topic_mismatch")
        report["output_warnings"].append("topic_mismatch")
        report["evaluation"]["topic_aligned"] = False
        report["advice"] = _build_advice_message(
            evidence_count=evidence_count,
            has_traceable=True,
            topic_aligned=False,
            missing_aspects=[],
        )
        return report

    if decision_hint == "uncertain":
        report["reason"] = "语义判别存在不确定性。"
        report["reason_code"] = "judge_uncertain"
        report["severity"] = "info"
        report["triggered_rules"].append("judge_uncertain")
        report["output_warnings"].append("judge_uncertain")
        report["advice"] = {
            "type": "caution",
            "append_to_answer": True,
            "messages": [
                "⚠️ 证据与问题的相关性存在不确定性。",
                "建议补充更具体的论文线索以提高回答准确性。",
            ],
            "suggested_actions": ["补充更聚焦的主题描述", "明确具体的问题焦点"],
        }
        return report

    if decision_hint == "partial":
        report["reason"] = "当前证据仅覆盖了问题的一部分。"
        report["reason_code"] = "partial_coverage"
        report["severity"] = "info"
        report["allows_partial_answer"] = True
        report["triggered_rules"].append("partial_coverage")
        report["output_warnings"].append("partial_coverage")
        report["advice"] = _build_advice_message(
            evidence_count=evidence_count,
            has_traceable=True,
            topic_aligned=True,
            missing_aspects=report["missing_aspects"],
        )
        return report

    # 正常回答
    report["reason"] = "证据充分，可进入回答。"
    report["reason_code"] = "ready_to_answer"
    report["severity"] = "info"
    report["advice"] = _build_advice_message(
        evidence_count=evidence_count,
        has_traceable=True,
        topic_aligned=True,
        missing_aspects=[],
    )
    return report


def format_advice_for_answer(advice: dict[str, Any], report: dict[str, Any]) -> str:
    """
    将建议格式化为可追加到回答中的文本

    Args:
        advice: 建议信息字典
        report: Sufficiency Gate 完整报告

    Returns:
        str: 格式化后的建议文本
    """
    if not advice.get("append_to_answer"):
        return ""

    lines = [
        "",
        "=" * 50,
        "📋 回答质量提示",
        "=" * 50,
    ]

    # 添加建议消息
    for msg in advice.get("messages", []):
        lines.append(msg)

    # 添加建议行动
    actions = advice.get("suggested_actions", [])
    if actions:
        lines.append("")
        lines.append("💡 建议:")
        for i, action in enumerate(actions, 1):
            lines.append(f"  {i}. {action}")

    # 添加证据概况
    lines.append("")
    lines.append("📊 证据概况:")
    lines.append(f"  - 证据数量: {report.get('evidence_count', 0)}")
    lines.append(f"  - 证据质量: {report.get('evidence_quality', 'unknown')}")
    lines.append(f"  - 置信度: {report.get('confidence_level', 'unknown')}")

    # 如果有缺失方面，显示出来
    missing = report.get("missing_aspects", [])
    if missing:
        lines.append(f"  - 未覆盖方面: {', '.join(missing[:3])}")
        if len(missing) > 3:
            lines[-1] += f" 等 {len(missing)} 项"

    lines.append("=" * 50)

    return "\n".join(lines)
