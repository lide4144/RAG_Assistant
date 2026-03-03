from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:-[0-9]+)?\b")

COREFERENCE_MARKERS = {
    "it",
    "its",
    "they",
    "them",
    "this",
    "that",
    "those",
    "these",
    "the former",
    "the latter",
    "this paper",
    "that paper",
    "另一篇",
    "这篇",
    "那篇",
    "它",
    "其",
    "前者",
    "后者",
    "该论文",
    "这项",
    "那项",
}

ENTITY_STOPWORDS = {
    "what",
    "how",
    "which",
    "paper",
    "study",
    "method",
    "approach",
    "analysis",
    "请问",
    "什么",
    "怎么",
    "这个",
    "那个",
    "论文",
    "方法",
    "分析",
}
CONTROL_STYLE_PATTERNS = (
    r"^(请)?(用|以)?中文(来)?(回答|说|写)",
    r"^(请)?(用|以)?英文(来)?(回答|说|写)",
    r"^(请)?(换成|切换到).*(中文|英文)",
    r"^(请)?(简短|详细|更详细|更简短)(一点|些)?",
)
CONTROL_FORMAT_PATTERNS = (
    r"^(请)?(用|按).*(列表|表格|markdown|json|要点|bullet|项目符号)",
    r"^(请)?(分点|分条|给出要点|列出来)",
)
CONTROL_CONTINUATION_PATTERNS = (
    r"^(继续|接着|再说|往下|继续回答|继续说)",
    r"^(然后呢|后面呢|继续讲)",
)
ALLOWED_DIALOG_STATES = {"normal", "need_clarify", "waiting_followup"}
_REDIS_CLIENT_CACHE: dict[str, Any] = {}


def _resolve_store_backend(backend: str | None) -> str:
    selected = (backend or "").strip().lower()
    if selected:
        return selected
    return "file"


def _redis_session_key(prefix: str, session_id: str) -> str:
    safe_prefix = (prefix or "rag").strip() or "rag"
    return f"{safe_prefix}:session:{session_id}"


def _get_redis_client(redis_url: str | None) -> Any | None:
    url = (redis_url or os.environ.get("RAG_SESSION_REDIS_URL") or "").strip()
    if not url:
        return None
    if url in _REDIS_CLIENT_CACHE:
        return _REDIS_CLIENT_CACHE[url]
    try:
        import redis  # type: ignore
    except Exception:
        return None
    try:
        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        _ = client.ping()
        _REDIS_CLIENT_CACHE[url] = client
        return client
    except Exception:
        return None


def _read_store(path: str | Path) -> dict[str, Any]:
    store_path = Path(path)
    if not store_path.exists():
        return {"sessions": {}}
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception:
        return {"sessions": {}}
    if not isinstance(payload, dict):
        return {"sessions": {}}
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict):
        return {"sessions": {}}
    return payload


def _write_store(path: str | Path, payload: dict[str, Any]) -> None:
    store_path = Path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_session_record(
    session_id: str,
    *,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> tuple[dict[str, Any], str]:
    selected = _resolve_store_backend(backend)
    if selected == "redis":
        client = _get_redis_client(redis_url)
        if client is not None:
            key = _redis_session_key(redis_key_prefix, session_id)
            raw = client.get(key)
            if isinstance(raw, str) and raw.strip():
                try:
                    payload = json.loads(raw)
                    if isinstance(payload, dict):
                        return _ensure_session({"sessions": {session_id: payload}}, session_id), "redis"
                except Exception:
                    pass
            if not redis_fallback_to_file:
                return _ensure_session({"sessions": {}}, session_id), "redis"
    payload = _read_store(store_path)
    return _ensure_session(payload, session_id), "file"


def _persist_session_record(
    session_id: str,
    session: dict[str, Any],
    *,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_ttl_sec: int = 86400,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> None:
    selected = _resolve_store_backend(backend)
    if selected == "redis":
        client = _get_redis_client(redis_url)
        if client is not None:
            key = _redis_session_key(redis_key_prefix, session_id)
            value = json.dumps(session, ensure_ascii=False)
            if redis_ttl_sec > 0:
                client.setex(key, redis_ttl_sec, value)
            else:
                client.set(key, value)
            return
        if not redis_fallback_to_file:
            return
    payload = _read_store(store_path)
    sessions = payload.setdefault("sessions", {})
    sessions[session_id] = session
    _write_store(store_path, payload)


def _estimate_tokens(text: str) -> int:
    return len(TOKEN_RE.findall(text or ""))


def _normalize_spaces(text: str) -> str:
    return " ".join((text or "").split())


def _contains_coreference(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in COREFERENCE_MARKERS)


def _extract_entities(text: str, *, max_entities: int = 6) -> list[str]:
    entities: list[str] = []
    for m in ACRONYM_RE.finditer(text or ""):
        token = m.group(0).strip()
        if token and token not in entities:
            entities.append(token)

    for token in TOKEN_RE.findall(text or ""):
        norm = token.strip()
        if not norm:
            continue
        lower = norm.lower()
        if lower in ENTITY_STOPWORDS or len(lower) <= 1:
            continue
        if norm not in entities:
            entities.append(norm)
        if len(entities) >= max_entities:
            break
    return entities[:max_entities]


def _is_control_only_query(text: str) -> bool:
    normalized = _normalize_spaces(text).lower()
    if not normalized:
        return False
    for pattern in CONTROL_CONTINUATION_PATTERNS + CONTROL_FORMAT_PATTERNS + CONTROL_STYLE_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return True
    return False


def _ensure_session(payload: dict[str, Any], session_id: str) -> dict[str, Any]:
    sessions = payload.setdefault("sessions", {})
    if session_id not in sessions or not isinstance(sessions.get(session_id), dict):
        sessions[session_id] = {
            "turns": [],
            "pending_clarify": None,
            "state": {
                "topic_anchors": [],
                "transient_constraints": [],
                "last_reset_turn_number": 0,
                "clarify_count_for_topic": 0,
                "dialog_state": "normal",
                "summary_memory": "",
                "semantic_recall_memory": [],
            },
        }
    session = sessions[session_id]
    turns = session.get("turns")
    if not isinstance(turns, list):
        session["turns"] = []
    if "pending_clarify" not in session:
        session["pending_clarify"] = None
    state = session.get("state")
    if not isinstance(state, dict):
        state = {}
        session["state"] = state
    anchors = state.get("topic_anchors")
    if not isinstance(anchors, list):
        state["topic_anchors"] = []
    constraints = state.get("transient_constraints")
    if not isinstance(constraints, list):
        state["transient_constraints"] = []
    if not isinstance(state.get("last_reset_turn_number"), int):
        state["last_reset_turn_number"] = 0
    if not isinstance(state.get("clarify_count_for_topic"), int):
        state["clarify_count_for_topic"] = 0
    dialog_state = str(state.get("dialog_state", "normal")).strip().lower()
    if dialog_state not in ALLOWED_DIALOG_STATES:
        state["dialog_state"] = "normal"
    summary_memory = state.get("summary_memory")
    if not isinstance(summary_memory, str):
        state["summary_memory"] = ""
    semantic_memory = state.get("semantic_recall_memory")
    if not isinstance(semantic_memory, list):
        state["semantic_recall_memory"] = []
    else:
        normalized_semantic: list[str] = []
        for row in semantic_memory:
            value = str(row).strip()
            if value and value not in normalized_semantic:
                normalized_semantic.append(value)
        state["semantic_recall_memory"] = normalized_semantic[:12]
    return session


def clear_session(
    session_id: str,
    store_path: str | Path = "data/session_store.json",
    *,
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> bool:
    cleared = False
    selected = _resolve_store_backend(backend)
    if selected == "redis":
        client = _get_redis_client(redis_url)
        if client is not None:
            key = _redis_session_key(redis_key_prefix, session_id)
            cleared = bool(client.delete(key))
            if not redis_fallback_to_file:
                return cleared
    payload = _read_store(store_path)
    sessions = payload.get("sessions", {})
    if isinstance(sessions, dict) and session_id in sessions:
        sessions.pop(session_id, None)
        _write_store(store_path, payload)
        return True
    return cleared


def _assemble_summary_memory(turns: list[dict[str, Any]], *, max_chars: int = 360) -> str:
    if not turns:
        return ""
    rows: list[str] = []
    for turn in turns[-4:]:
        q = _normalize_spaces(str(turn.get("user_input", "")))
        if not q:
            continue
        rows.append(q[:80])
    out = " | ".join(rows)
    return out[:max_chars]


def _assemble_semantic_memory(turns: list[dict[str, Any]], *, max_items: int = 10) -> list[str]:
    memory: list[str] = []
    for turn in reversed(turns):
        entities = turn.get("entity_mentions", [])
        if not isinstance(entities, list):
            continue
        for entity in entities:
            value = str(entity).strip()
            if value and value not in memory:
                memory.append(value)
        if len(memory) >= max_items:
            break
    return memory[:max_items]


def load_history_window(
    session_id: str,
    *,
    store_path: str | Path = "data/session_store.json",
    window_size: int = 3,
    include_layered_memory: bool = True,
    backend: str | None = None,
    redis_url: str | None = None,
    redis_ttl_sec: int = 86400,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    session, _ = _read_session_record(
        session_id,
        store_path=store_path,
        backend=backend,
        redis_url=redis_url,
        redis_key_prefix=redis_key_prefix,
        redis_fallback_to_file=redis_fallback_to_file,
    )
    turns = [t for t in session.get("turns", []) if isinstance(t, dict)]
    state = session.get("state", {})
    if not isinstance(state, dict):
        state = {}
        session["state"] = state
    summary_memory = _normalize_spaces(str(state.get("summary_memory", "")))
    semantic_memory = [str(x).strip() for x in state.get("semantic_recall_memory", []) if str(x).strip()]
    if include_layered_memory:
        if not summary_memory:
            summary_memory = _assemble_summary_memory(turns)
            state["summary_memory"] = summary_memory
        if not semantic_memory:
            semantic_memory = _assemble_semantic_memory(turns)
            state["semantic_recall_memory"] = semantic_memory
        _persist_session_record(
            session_id,
            session,
            store_path=store_path,
            backend=backend,
            redis_url=redis_url,
            redis_ttl_sec=redis_ttl_sec,
            redis_key_prefix=redis_key_prefix,
            redis_fallback_to_file=redis_fallback_to_file,
        )
    if window_size <= 0:
        return [], 0
    window = turns[-window_size:]
    if include_layered_memory:
        if summary_memory:
            window.append(
                {
                    "turn_type": "summary_memory",
                    "user_input": "",
                    "answer": summary_memory,
                    "decision": "memory",
                    "entity_mentions": semantic_memory[:8],
                }
            )
        if semantic_memory:
            window.append(
                {
                    "turn_type": "semantic_recall_memory",
                    "user_input": "",
                    "answer": " ".join(semantic_memory[:8]),
                    "decision": "memory",
                    "entity_mentions": semantic_memory[:8],
                }
            )
    token_est = 0
    for row in window:
        token_est += _estimate_tokens(str(row.get("user_input", "")))
        token_est += _estimate_tokens(str(row.get("answer", "")))
        token_est += len([x for x in row.get("cited_chunk_ids", []) if isinstance(x, str)])
        token_est += _estimate_tokens(str(row.get("decision", "")))
    return window, token_est


def derive_rewrite_context(
    history_turns: list[dict[str, Any]],
) -> tuple[str | None, list[str], list[str], list[str], list[str]]:
    real_turns = [t for t in history_turns if str(t.get("turn_type", "")).strip() not in {"summary_memory", "semantic_recall_memory"}]
    last_turn_decision: str | None = None
    last_turn_warnings: list[str] = []
    entities_from_history: list[str] = []
    topic_anchors: list[str] = []
    transient_constraints: list[str] = []

    if real_turns:
        last = real_turns[-1]
        decision = str(last.get("decision", "")).strip()
        if decision:
            last_turn_decision = decision
        warnings = last.get("output_warnings", [])
        if isinstance(warnings, list):
            for warning in warnings:
                value = str(warning).strip()
                if value and value not in last_turn_warnings:
                    last_turn_warnings.append(value)
        for anchor in (last.get("topic_anchors", []) or []):
            value = str(anchor).strip()
            if value and value not in topic_anchors:
                topic_anchors.append(value)
        for constraint in (last.get("transient_constraints", []) or []):
            value = str(constraint).strip()
            if value and value not in transient_constraints:
                transient_constraints.append(value)

    for turn in reversed(real_turns):
        entities = turn.get("entity_mentions", [])
        if not isinstance(entities, list):
            continue
        for entity in entities:
            value = str(entity).strip()
            if value and value not in entities_from_history:
                entities_from_history.append(value)
        if len(entities_from_history) >= 8:
            break
    if topic_anchors:
        for anchor in topic_anchors:
            if anchor not in entities_from_history:
                entities_from_history.append(anchor)
    return (
        last_turn_decision,
        last_turn_warnings,
        entities_from_history[:8],
        topic_anchors[:8],
        transient_constraints[:8],
    )


def merge_with_pending_clarify(
    session_id: str,
    user_input: str,
    *,
    allow_pending_merge: bool = True,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> tuple[str, bool]:
    if not allow_pending_merge:
        return user_input, False
    session, _ = _read_session_record(
        session_id,
        store_path=store_path,
        backend=backend,
        redis_url=redis_url,
        redis_key_prefix=redis_key_prefix,
        redis_fallback_to_file=redis_fallback_to_file,
    )
    pending = session.get("pending_clarify")
    if not isinstance(pending, dict):
        return user_input, False
    original_question = str(pending.get("original_question", "")).strip()
    clarify_question = str(pending.get("clarify_question", "")).strip()
    if not original_question:
        return user_input, False
    merged = f"{original_question} {clarify_question} 用户补充：{user_input}".strip()
    return merged, True


def rewrite_with_history_context(
    user_input: str,
    history_turns: list[dict[str, Any]],
) -> tuple[str, bool]:
    resolved = False
    standalone_query = user_input.strip()
    if not standalone_query:
        return "paper overview", False

    if _contains_coreference(standalone_query):
        history_entities: list[str] = []
        for turn in reversed(history_turns):
            entities = turn.get("entity_mentions", [])
            if isinstance(entities, list):
                for entity in entities:
                    value = str(entity).strip()
                    if value and value not in history_entities:
                        history_entities.append(value)
            if len(history_entities) >= 4:
                break
        if history_entities:
            missing = [e for e in history_entities if e.lower() not in standalone_query.lower()]
            if missing:
                standalone_query = f"{' '.join(missing[:3])} {standalone_query}".strip()
                resolved = True
    return standalone_query, resolved


def build_history_brief(history_turns: list[dict[str, Any]], *, max_chars: int = 220) -> str:
    if not history_turns:
        return ""
    rows: list[str] = []
    for turn in history_turns[-3:]:
        q = str(turn.get("user_input", "")).strip()
        a = str(turn.get("answer", "")).strip()
        if not q and not a:
            continue
        rows.append(f"Q:{q[:50]} | A:{a[:50]}")
    out = " ; ".join(rows).strip()
    return out[:max_chars]


def build_control_intent_anchor_query(
    history_turns: list[dict[str, Any]],
    *,
    max_turn_distance: int = 3,
) -> tuple[str | None, dict[str, Any]]:
    if max_turn_distance <= 0:
        max_turn_distance = 1
    real_turns = [t for t in history_turns if str(t.get("turn_type", "")).strip() not in {"summary_memory", "semantic_recall_memory"}]
    if not real_turns:
        return None, {"status": "anchor_missing", "reason": "no_history"}

    latest_idx = len(real_turns) - 1
    chosen_query: str | None = None
    chosen_entities: list[str] = []
    chosen_distance: int | None = None
    chosen_turn_number: int | None = None
    recent_cited_chunk_ids: list[str] = []
    recent_evidence_terms: list[str] = []

    for idx in range(latest_idx, -1, -1):
        turn = real_turns[idx]
        if not isinstance(turn, dict):
            continue
        turn_distance = latest_idx - idx + 1
        if turn_distance <= max_turn_distance:
            cited_raw = turn.get("cited_chunk_ids", [])
            if isinstance(cited_raw, list):
                for chunk_id in cited_raw:
                    value = str(chunk_id).strip()
                    if value and value not in recent_cited_chunk_ids:
                        recent_cited_chunk_ids.append(value)
            answer_text = _normalize_spaces(str(turn.get("answer", "")))
            if answer_text:
                for term in _extract_entities(answer_text, max_entities=4):
                    lowered = term.lower()
                    if lowered in ENTITY_STOPWORDS:
                        continue
                    if term not in recent_evidence_terms:
                        recent_evidence_terms.append(term)

        standalone_query = _normalize_spaces(str(turn.get("standalone_query", "")))
        if not standalone_query:
            continue
        if _is_control_only_query(standalone_query):
            continue
        chosen_query = standalone_query
        chosen_distance = turn_distance
        turn_number_raw = turn.get("turn_number")
        if isinstance(turn_number_raw, int):
            chosen_turn_number = turn_number_raw
        entities_raw = turn.get("entity_mentions", [])
        if isinstance(entities_raw, list):
            chosen_entities = [str(e).strip() for e in entities_raw if str(e).strip()]
        break

    if not chosen_query or chosen_distance is None:
        return None, {"status": "anchor_missing", "reason": "no_standalone_query_in_window"}
    if chosen_distance > max_turn_distance:
        return None, {
            "status": "anchor_stale",
            "reason": "turn_distance_exceeded",
            "distance": chosen_distance,
            "max_turn_distance": max_turn_distance,
            "anchor_turn_number": chosen_turn_number,
        }

    anchor_query = chosen_query
    anchor_seed = f" {anchor_query.lower()} "
    extras: list[str] = []
    for token in chosen_entities + recent_evidence_terms:
        token_norm = str(token).strip()
        if not token_norm:
            continue
        if f" {token_norm.lower()} " in anchor_seed:
            continue
        if token_norm not in extras:
            extras.append(token_norm)
    if extras:
        anchor_query = _normalize_spaces(f"{anchor_query} {' '.join(extras[:4])}")

    return anchor_query, {
        "status": "anchor_ready",
        "distance": chosen_distance,
        "max_turn_distance": max_turn_distance,
        "anchor_turn_number": chosen_turn_number,
        "anchor_entities": chosen_entities[:6],
        "recent_cited_chunk_ids": recent_cited_chunk_ids[:8],
        "recent_evidence_terms": recent_evidence_terms[:8],
    }


def append_turn_record(
    session_id: str,
    *,
    user_input: str,
    standalone_query: str,
    answer: str,
    cited_chunk_ids: list[str],
    decision: str,
    output_warnings: list[str] | None,
    clear_pending_clarify: bool = False,
    set_pending_clarify: dict[str, str] | None = None,
    topic_anchors: list[str] | None = None,
    transient_constraints: list[str] | None = None,
    clarify_count_for_topic: int | None = None,
    session_reset_applied: bool = False,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_ttl_sec: int = 86400,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> int:
    session, _ = _read_session_record(
        session_id,
        store_path=store_path,
        backend=backend,
        redis_url=redis_url,
        redis_key_prefix=redis_key_prefix,
        redis_fallback_to_file=redis_fallback_to_file,
    )
    turns = [t for t in session.get("turns", []) if isinstance(t, dict)]
    state = session.get("state", {})
    if not isinstance(state, dict):
        state = {}
        session["state"] = state

    merged_anchors: list[str] = []
    for anchor in (topic_anchors or _extract_entities(standalone_query)):
        value = str(anchor).strip()
        if value and value not in merged_anchors:
            merged_anchors.append(value)
    merged_constraints: list[str] = []
    for constraint in (transient_constraints or []):
        value = str(constraint).strip()
        if value and value not in merged_constraints:
            merged_constraints.append(value)

    turn_number = len(turns) + 1
    turn_record = {
        "turn_number": turn_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_input": user_input,
        "standalone_query": standalone_query,
        "answer": answer,
        "cited_chunk_ids": [c for c in cited_chunk_ids if c],
        "decision": decision,
        "output_warnings": [str(w).strip() for w in (output_warnings or []) if str(w).strip()],
        "entity_mentions": _extract_entities(standalone_query),
        "topic_anchors": merged_anchors,
        "transient_constraints": merged_constraints,
        "clarify_count_for_topic": (
            max(0, int(clarify_count_for_topic)) if clarify_count_for_topic is not None else int(state.get("clarify_count_for_topic", 0))
        ),
    }
    turns.append(turn_record)
    session["turns"] = turns
    state["topic_anchors"] = merged_anchors
    state["transient_constraints"] = merged_constraints
    state["summary_memory"] = _assemble_summary_memory(turns)
    state["semantic_recall_memory"] = _assemble_semantic_memory(turns)
    dialog_state = str(state.get("dialog_state", "normal")).strip().lower()
    if dialog_state not in ALLOWED_DIALOG_STATES:
        dialog_state = "normal"
    if decision in {"clarify", "need_scope_clarification"}:
        dialog_state = "waiting_followup"
    elif set_pending_clarify is not None:
        dialog_state = "need_clarify"
    else:
        dialog_state = "normal"
    state["dialog_state"] = dialog_state
    if session_reset_applied:
        state["last_reset_turn_number"] = turn_number
    if clarify_count_for_topic is not None:
        state["clarify_count_for_topic"] = max(0, int(clarify_count_for_topic))
    if clear_pending_clarify:
        session["pending_clarify"] = None
        if not merged_constraints:
            state["transient_constraints"] = []
    if set_pending_clarify is not None:
        session["pending_clarify"] = {
            "original_question": str(set_pending_clarify.get("original_question", "")).strip(),
            "clarify_question": str(set_pending_clarify.get("clarify_question", "")).strip(),
        }
        if dialog_state == "normal":
            state["dialog_state"] = "need_clarify"
    _persist_session_record(
        session_id,
        session,
        store_path=store_path,
        backend=backend,
        redis_url=redis_url,
        redis_ttl_sec=redis_ttl_sec,
        redis_key_prefix=redis_key_prefix,
        redis_fallback_to_file=redis_fallback_to_file,
    )
    return turn_number


def load_dialog_state(
    session_id: str,
    *,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> str:
    session, _ = _read_session_record(
        session_id,
        store_path=store_path,
        backend=backend,
        redis_url=redis_url,
        redis_key_prefix=redis_key_prefix,
        redis_fallback_to_file=redis_fallback_to_file,
    )
    state = session.get("state", {})
    if not isinstance(state, dict):
        return "normal"
    value = str(state.get("dialog_state", "normal")).strip().lower()
    if value not in ALLOWED_DIALOG_STATES:
        return "normal"
    return value
