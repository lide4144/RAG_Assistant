from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SUMMARY_CUE_PATTERNS = (
    r"\bin\s+summary\b",
    r"\bsummary\b",
    r"\boverview\b",
    r"\babstract\s+overview\b",
    r"\bpaper\s+overview\b",
    r"\breporting\b",
)

INTENT_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "limitation": {
        "triggers": (
            "局限",
            "不足",
            "缺点",
            "问题",
            "限制",
            "威胁",
            "未来工作",
            "limitation",
            "limitations",
            "drawback",
            "weakness",
            "threat",
            "future work",
        ),
        "cues": (
            "limitations",
            "drawbacks",
            "weakness",
            "threats to validity",
            "future work",
            "局限",
            "不足",
            "缺点",
            "威胁",
            "未来工作",
        ),
    },
    "contribution": {
        "triggers": (
            "贡献",
            "创新点",
            "提出",
            "主要工作",
            "核心思想",
            "contribution",
            "novelty",
            "propose",
            "main idea",
            "key idea",
        ),
        "cues": (
            "main contribution",
            "novelty",
            "key idea",
            "proposed method",
            "主要贡献",
            "创新点",
            "核心思想",
            "提出",
            "方法",
        ),
    },
    "dataset": {
        "triggers": (
            "数据集",
            "基准",
            "数据来源",
            "训练数据",
            "测试集",
            "dataset",
            "benchmark",
            "corpus",
            "evaluation dataset",
        ),
        "cues": (
            "dataset",
            "benchmark",
            "corpus",
            "evaluation dataset",
            "数据集",
            "基准",
            "数据来源",
            "测试集",
            "训练集",
        ),
    },
    "metric": {
        "triggers": (
            "指标",
            "评价",
            "准确率",
            "分数",
            "性能",
            "metric",
            "evaluation",
            "accuracy",
            "score",
            "performance",
        ),
        "cues": (
            "metrics",
            "evaluation",
            "measure",
            "accuracy",
            "F1",
            "BLEU",
            "ROUGE",
            "指标",
            "评价",
            "准确率",
            "F1",
            "BLEU",
            "ROUGE",
        ),
    },
    "architecture": {
        "triggers": (
            "架构",
            "结构",
            "流程",
            "框架",
            "pipeline",
            "模块",
            "architecture",
            "framework",
            "workflow",
        ),
        "cues": (
            "architecture",
            "framework",
            "pipeline",
            "system design",
            "架构",
            "框架",
            "流程",
            "系统设计",
        ),
    },
}


@dataclass
class CalibrationResult:
    calibrated_query: str
    calibration_reason: dict[str, Any]


def strip_summary_cues(text: str) -> tuple[str, list[str]]:
    """移除会把检索引向 summary 外壳句的提示词。"""
    removed: list[str] = []
    output = text
    for pattern in SUMMARY_CUE_PATTERNS:
        if re.search(pattern, output, flags=re.IGNORECASE):
            removed.append(pattern)
            output = re.sub(pattern, " ", output, flags=re.IGNORECASE)
    output = " ".join(output.split())
    return output, removed


def _match_intents(question: str) -> tuple[list[str], list[str]]:
    q = question.lower()
    matched_intents: list[str] = []
    cues: list[str] = []
    for intent, rule in INTENT_RULES.items():
        triggers = [t for t in rule["triggers"] if t.lower() in q]
        if not triggers:
            continue
        matched_intents.append(intent)
        for cue in rule["cues"]:
            if cue not in cues:
                cues.append(cue)
    return matched_intents, cues


def calibrate_query_intent(
    *,
    question: str,
    rewritten_query: str,
    keywords_entities: dict[str, list[str]] | None,
    scope_mode: str,
    scope_reason: dict[str, Any] | None,
) -> CalibrationResult:
    """根据问题意图对检索查询进行轻量校准，返回可复现原因。"""
    base_query = (rewritten_query or question).strip()
    reason: dict[str, Any] = {
        "scope_mode": scope_mode,
        "has_paper_clue": bool((scope_reason or {}).get("has_paper_clue")),
        "matched_intents": [],
        "added_cues": [],
        "removed_summary_cues": [],
        "keywords_entities": keywords_entities or {"keywords": [], "entities": []},
    }

    should_strip_summary = scope_mode == "rewrite_scope" and not reason["has_paper_clue"]
    if should_strip_summary:
        base_query, removed = strip_summary_cues(base_query)
        reason["removed_summary_cues"] = removed

    intents, cues = _match_intents(question)
    reason["matched_intents"] = intents

    calibrated_parts: list[str] = [base_query]
    for cue in cues:
        if cue.lower() not in " ".join(calibrated_parts).lower():
            calibrated_parts.append(cue)
            reason["added_cues"].append(cue)

    calibrated_query = " ".join(part for part in calibrated_parts if part).strip()
    if not calibrated_query:
        calibrated_query = question.strip() or rewritten_query.strip()
    reason["rule"] = "intent_calibration"
    return CalibrationResult(calibrated_query=calibrated_query, calibration_reason=reason)
