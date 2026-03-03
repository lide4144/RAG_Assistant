from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+")


@dataclass
class ContextAssemblyResult:
    assembled_prompt: str
    discarded_evidence: list[dict[str, Any]]
    prompt_tokens_est: int
    history_trimmed_turns: int
    remaining_evidence_count: int
    context_overflow_fallback: bool


def estimate_tokens(text: str) -> int:
    return len(TOKEN_RE.findall(text or ""))


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _history_min_turn(turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_input": str(turn.get("user_input", "")),
        "standalone_query": str(turn.get("standalone_query", "")),
        "answer": str(turn.get("answer", "")),
    }


def _build_payload_prompt(
    *,
    user_prompt: str,
    chat_history: list[dict[str, Any]],
    evidence_grouped: list[dict[str, Any]],
) -> str:
    payload = {
        "chat_history": chat_history,
        "evidence_grouped": evidence_grouped,
    }
    return f"{user_prompt}\n\nContextPayload:\n{json.dumps(payload, ensure_ascii=False)}"


def _estimate_total_tokens(*, system_prompt: str, assembled_user_prompt: str) -> int:
    return estimate_tokens(system_prompt) + estimate_tokens(assembled_user_prompt)


def _iter_evidence_rows(evidence_grouped: list[dict[str, Any]]) -> list[tuple[int, int, dict[str, Any], str]]:
    rows: list[tuple[int, int, dict[str, Any], str]] = []
    for gidx, group in enumerate(evidence_grouped):
        paper_id = str(group.get("paper_id", "unknown-paper"))
        evidence = group.get("evidence", [])
        if not isinstance(evidence, list):
            continue
        for eidx, item in enumerate(evidence):
            if not isinstance(item, dict):
                continue
            rows.append((gidx, eidx, item, paper_id))
    return rows


def _drop_priority(item: dict[str, Any]) -> tuple[int, float]:
    source = str(item.get("source", "")).strip().lower()
    source_rank = 0 if source == "graph_expand" else 1
    score = _safe_float(item.get("score_rerank"))
    if "score_rerank" not in item:
        score = _safe_float(item.get("score_retrieval"))
    return (source_rank, score)


def assemble_prompt_with_budget(
    *,
    system_prompt: str,
    user_prompt: str,
    chat_history: list[dict[str, Any]],
    evidence_grouped: list[dict[str, Any]],
    max_context_tokens: int,
) -> ContextAssemblyResult:
    history = [_history_min_turn(h) for h in chat_history if isinstance(h, dict)]
    grouped: list[dict[str, Any]] = []
    for group in evidence_grouped:
        if not isinstance(group, dict):
            continue
        copied = dict(group)
        ev = group.get("evidence", [])
        copied["evidence"] = [dict(item) for item in ev if isinstance(item, dict)] if isinstance(ev, list) else []
        grouped.append(copied)

    discarded: list[dict[str, Any]] = []
    trimmed_history = 0
    budget = max(1, int(max_context_tokens))

    assembled_user_prompt = _build_payload_prompt(
        user_prompt=user_prompt,
        chat_history=history,
        evidence_grouped=grouped,
    )
    total_tokens = _estimate_total_tokens(system_prompt=system_prompt, assembled_user_prompt=assembled_user_prompt)

    while total_tokens > budget and len(history) > 1:
        history.pop(0)
        trimmed_history += 1
        assembled_user_prompt = _build_payload_prompt(
            user_prompt=user_prompt,
            chat_history=history,
            evidence_grouped=grouped,
        )
        total_tokens = _estimate_total_tokens(system_prompt=system_prompt, assembled_user_prompt=assembled_user_prompt)

    while total_tokens > budget:
        rows = _iter_evidence_rows(grouped)
        if not rows:
            break
        rows.sort(key=lambda row: _drop_priority(row[2]))
        gidx, eidx, item, paper_id = rows[0]
        grouped[gidx]["evidence"].pop(eidx)
        discarded.append(
            {
                "chunk_id": str(item.get("chunk_id", "")),
                "paper_id": paper_id,
                "source": str(item.get("source", "")),
                "score_retrieval": _safe_float(item.get("score_retrieval")),
                "score_rerank": _safe_float(item.get("score_rerank")),
            }
        )
        assembled_user_prompt = _build_payload_prompt(
            user_prompt=user_prompt,
            chat_history=history,
            evidence_grouped=grouped,
        )
        total_tokens = _estimate_total_tokens(system_prompt=system_prompt, assembled_user_prompt=assembled_user_prompt)

    remaining = sum(len(group.get("evidence", [])) for group in grouped if isinstance(group.get("evidence", []), list))
    fallback = remaining < 1

    return ContextAssemblyResult(
        assembled_prompt=assembled_user_prompt,
        discarded_evidence=discarded,
        prompt_tokens_est=total_tokens,
        history_trimmed_turns=trimmed_history,
        remaining_evidence_count=remaining,
        context_overflow_fallback=fallback,
    )
