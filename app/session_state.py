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
_ALLOWED_BACKENDS = {"file", "redis", "sqlite"}
_REDIS_CLIENT_CACHE: dict[str, Any] = {}
_STORE_CACHE: dict[str, Any] = {}


def _resolve_store_backend(backend: str | None) -> str:
    """Resolve storage backend from configuration.

    Supports: 'file' (default), 'redis', 'sqlite'

    Priority:
    1. Explicit backend parameter
    2. SESSION_BACKEND environment variable
    3. session_store_backend from YAML config
    4. Default 'file'

    Args:
        backend: Explicit backend choice, or None to read from config/env.

    Returns:
        str: Resolved backend name.
    """
    # Priority 1: Explicit parameter
    if backend:
        selected = backend.strip().lower()
        if selected in _ALLOWED_BACKENDS:
            return selected

    # Priority 2: Environment variable
    env_backend = os.environ.get("SESSION_BACKEND", "").strip().lower()
    if env_backend in _ALLOWED_BACKENDS:
        return env_backend

    # Priority 3: YAML config
    try:
        from app.config import load_config

        config = load_config()
        config_backend = getattr(config, "session_store_backend", "")
        if config_backend:
            selected = config_backend.strip().lower()
            if selected in _ALLOWED_BACKENDS:
                return selected
    except Exception:
        pass

    # Priority 4: Default
    return "file"


def _get_session_config_value(
    field_name: str, env_var: str | None, default: str, param_value: str | None = None
) -> str:
    """Get session configuration value with proper priority.

    Priority:
    1. Explicit parameter value
    2. Environment variable
    3. YAML config (session_* field)
    4. Default value
    """
    # Priority 1: Explicit parameter
    if param_value:
        return param_value

    # Priority 2: Environment variable
    if env_var:
        env_val = os.environ.get(env_var, "").strip()
        if env_val:
            return env_val

    # Priority 3: YAML config
    try:
        from app.config import load_config

        config = load_config()
        config_val = getattr(config, f"session_{field_name}", "")
        if config_val:
            return str(config_val)
    except Exception:
        pass

    # Priority 4: Default
    return default


def _create_store(
    backend: str | None = None,
    store_path: str | Path = "data/session_store.json",
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_ttl_sec: int = 86400,
) -> Any:
    """Create a session store instance based on backend configuration.

    This factory function creates the appropriate store backend
    (FileStore, RedisStore, or SQLiteStore) based on configuration.

    Configuration priority:
    1. Explicit function parameters
    2. Environment variables (SESSION_BACKEND, SESSION_SQLITE_PATH, etc.)
    3. YAML config (session_store_backend, session_sqlite_path, etc.)
    4. Default values

    Args:
        backend: Backend type ('file', 'redis', 'sqlite').
                If None, reads from config/env.
        store_path: Path for file-based backends.
        redis_url: Redis connection URL.
        redis_key_prefix: Prefix for Redis keys.
        redis_ttl_sec: Redis TTL in seconds.

    Returns:
        SessionStore: Configured store instance.
    """
    selected = _resolve_store_backend(backend)

    # Resolve effective paths/values with config fallback
    effective_store_path = _get_session_config_value(
        "store_path", None, str(store_path), str(store_path)
    )
    effective_redis_url = _get_session_config_value(
        "redis_url", "RAG_SESSION_REDIS_URL", "", redis_url
    )
    effective_redis_prefix = _get_session_config_value(
        "redis_key_prefix", None, redis_key_prefix, redis_key_prefix
    )
    effective_redis_ttl = int(
        _get_session_config_value(
            "redis_ttl_sec", None, str(redis_ttl_sec), str(redis_ttl_sec)
        )
    )

    cache_key = f"{selected}:{effective_store_path}:{effective_redis_url}:{effective_redis_prefix}"

    if cache_key in _STORE_CACHE:
        return _STORE_CACHE[cache_key]

    if selected == "sqlite":
        # Lazy import to avoid circular dependencies
        try:
            from app.db import SQLiteStore

            db_path = _get_session_config_value(
                "sqlite_path", "SESSION_SQLITE_PATH", "data/session_store.db"
            )
            store = SQLiteStore(db_path)
        except ImportError:
            # Fallback to file if sqlite3 not available (shouldn't happen)
            from app.db import FileStore

            store = FileStore(effective_store_path)
    elif selected == "redis":
        try:
            from app.db import RedisStore

            store = RedisStore(
                effective_redis_url, effective_redis_prefix, effective_redis_ttl
            )
        except (ImportError, Exception):
            # Fallback to file if Redis unavailable
            from app.db import FileStore

            store = FileStore(effective_store_path)
    else:
        # Default: file backend
        from app.db import FileStore

        store = FileStore(effective_store_path)

    _STORE_CACHE[cache_key] = store
    return store


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
    store_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_session_record(
    session_id: str,
    *,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> tuple[dict[str, Any], str]:
    """Read a session record from storage.

    Supports file, redis, and sqlite backends via the Store interface.
    """
    selected = _resolve_store_backend(backend)

    try:
        store = _create_store(
            backend=selected,
            store_path=store_path,
            redis_url=redis_url,
            redis_key_prefix=redis_key_prefix,
        )
        session = store.read_session(session_id)
        return _ensure_session(
            {"sessions": {session_id: session}}, session_id
        ), selected
    except Exception as e:
        # Fallback to file backend on error (if not sqlite which has no fallback)
        if selected != "file" and redis_fallback_to_file:
            try:
                from app.db import FileStore

                store = FileStore(store_path)
                session = store.read_session(session_id)
                return _ensure_session(
                    {"sessions": {session_id: session}}, session_id
                ), "file"
            except Exception:
                pass
        # Return empty session on error
        return _ensure_session({"sessions": {}}, session_id), selected


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
    """Persist a session record to storage.

    Supports file, redis, and sqlite backends via the Store interface.
    """
    selected = _resolve_store_backend(backend)

    try:
        store = _create_store(
            backend=selected,
            store_path=store_path,
            redis_url=redis_url,
            redis_key_prefix=redis_key_prefix,
            redis_ttl_sec=redis_ttl_sec,
        )
        store.write_session(session_id, session)
    except Exception as e:
        # Fallback to file backend on error
        if selected != "file" and redis_fallback_to_file:
            try:
                from app.db import FileStore

                store = FileStore(store_path)
                store.write_session(session_id, session)
            except Exception:
                pass
        else:
            raise


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
    for pattern in (
        CONTROL_CONTINUATION_PATTERNS + CONTROL_FORMAT_PATTERNS + CONTROL_STYLE_PATTERNS
    ):
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
                "user_honesty_preferences": {
                    "hide_low_confidence_warnings": False,
                    "acknowledged_at": None,
                    "acknowledgment_count": 0,
                },
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
    planner_summary = state.get("last_planner_summary")
    if not isinstance(planner_summary, dict):
        state["last_planner_summary"] = {}
    # Initialize user_honesty_preferences if not exists
    honesty_prefs = state.get("user_honesty_preferences")
    if not isinstance(honesty_prefs, dict):
        honesty_prefs = {
            "hide_low_confidence_warnings": False,
            "acknowledged_at": None,
            "acknowledgment_count": 0,
        }
        state["user_honesty_preferences"] = honesty_prefs
    return session


def _normalize_planner_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    normalized: dict[str, Any] = {}
    for key in (
        "decision_result",
        "primary_capability",
        "strictness",
        "standalone_query",
        "clarify_question",
    ):
        value = _normalize_spaces(str(summary.get(key, "")))
        if value:
            normalized[key] = value
    selected = [
        str(item).strip()
        for item in list(summary.get("selected_tools_or_skills") or [])
        if str(item).strip()
    ]
    if selected:
        normalized["selected_tools_or_skills"] = selected
    return normalized or None


def clear_session(
    session_id: str,
    store_path: str | Path = "data/session_store.json",
    *,
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> bool:
    """Clear a session from storage.

    Supports file, redis, and sqlite backends.
    """
    selected = _resolve_store_backend(backend)

    try:
        store = _create_store(
            backend=selected,
            store_path=store_path,
            redis_url=redis_url,
            redis_key_prefix=redis_key_prefix,
        )
        return store.delete_session(session_id)
    except Exception:
        # Fallback to file if needed
        if selected != "file" and redis_fallback_to_file:
            try:
                from app.db import FileStore

                store = FileStore(store_path)
                return store.delete_session(session_id)
            except Exception:
                pass
        return False


def _assemble_summary_memory(
    turns: list[dict[str, Any]], *, max_chars: int = 360
) -> str:
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


def _assemble_semantic_memory(
    turns: list[dict[str, Any]], *, max_items: int = 10
) -> list[str]:
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
    semantic_memory = [
        str(x).strip()
        for x in state.get("semantic_recall_memory", [])
        if str(x).strip()
    ]
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
        token_est += len(
            [x for x in row.get("cited_chunk_ids", []) if isinstance(x, str)]
        )
        token_est += _estimate_tokens(str(row.get("decision", "")))
    return window, token_est


def derive_rewrite_context(
    history_turns: list[dict[str, Any]],
) -> tuple[str | None, list[str], list[str], list[str], list[str]]:
    real_turns = [
        t
        for t in history_turns
        if str(t.get("turn_type", "")).strip()
        not in {"summary_memory", "semantic_recall_memory"}
    ]
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
        for anchor in last.get("topic_anchors", []) or []:
            value = str(anchor).strip()
            if value and value not in topic_anchors:
                topic_anchors.append(value)
        for constraint in last.get("transient_constraints", []) or []:
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
    if not original_question:
        return user_input, False
    # Keep the original question chain, but avoid mechanically injecting the prior
    # clarify prompt into the next-turn query. That old stitching path caused rewrite
    # and meta-guard drift after planner state had already decided this is a follow-up.
    merged = f"{original_question} 用户补充：{user_input}".strip()
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
            missing = [
                e for e in history_entities if e.lower() not in standalone_query.lower()
            ]
            if missing:
                standalone_query = f"{' '.join(missing[:3])} {standalone_query}".strip()
                resolved = True
    return standalone_query, resolved


def build_history_brief(
    history_turns: list[dict[str, Any]], *, max_chars: int = 220
) -> str:
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
    real_turns = [
        t
        for t in history_turns
        if str(t.get("turn_type", "")).strip()
        not in {"summary_memory", "semantic_recall_memory"}
    ]
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
        return None, {
            "status": "anchor_missing",
            "reason": "no_standalone_query_in_window",
        }
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
    planner_summary: dict[str, Any] | None = None,
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
    for anchor in topic_anchors or _extract_entities(standalone_query):
        value = str(anchor).strip()
        if value and value not in merged_anchors:
            merged_anchors.append(value)
    merged_constraints: list[str] = []
    for constraint in transient_constraints or []:
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
        "output_warnings": [
            str(w).strip() for w in (output_warnings or []) if str(w).strip()
        ],
        "entity_mentions": _extract_entities(standalone_query),
        "topic_anchors": merged_anchors,
        "transient_constraints": merged_constraints,
        "clarify_count_for_topic": (
            max(0, int(clarify_count_for_topic))
            if clarify_count_for_topic is not None
            else int(state.get("clarify_count_for_topic", 0))
        ),
    }
    normalized_planner_summary = _normalize_planner_summary(planner_summary)
    if normalized_planner_summary is not None:
        turn_record["planner_summary"] = normalized_planner_summary
    turns.append(turn_record)
    session["turns"] = turns
    state["topic_anchors"] = merged_anchors
    state["transient_constraints"] = merged_constraints
    state["summary_memory"] = _assemble_summary_memory(turns)
    state["semantic_recall_memory"] = _assemble_semantic_memory(turns)
    if normalized_planner_summary is not None:
        state["last_planner_summary"] = normalized_planner_summary
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
            "original_question": str(
                set_pending_clarify.get("original_question", "")
            ).strip(),
            "clarify_question": str(
                set_pending_clarify.get("clarify_question", "")
            ).strip(),
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


def load_pending_clarify(
    session_id: str,
    *,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> dict[str, Any] | None:
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
        return None
    original_question = str(pending.get("original_question", "")).strip()
    clarify_question = str(pending.get("clarify_question", "")).strip()
    if not original_question and not clarify_question:
        return None
    return {
        "original_question": original_question,
        "clarify_question": clarify_question,
    }


def load_planner_conversation_state(
    session_id: str,
    *,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> dict[str, Any]:
    session, _ = _read_session_record(
        session_id,
        store_path=store_path,
        backend=backend,
        redis_url=redis_url,
        redis_key_prefix=redis_key_prefix,
        redis_fallback_to_file=redis_fallback_to_file,
    )
    state = session.get("state", {})
    turns = [t for t in session.get("turns", []) if isinstance(t, dict)]
    recent_topic_anchors = [
        str(item).strip()
        for item in list(state.get("topic_anchors") or [])
        if str(item).strip()
    ]
    pending_clarify = load_pending_clarify(
        session_id,
        store_path=store_path,
        backend=backend,
        redis_url=redis_url,
        redis_key_prefix=redis_key_prefix,
        redis_fallback_to_file=redis_fallback_to_file,
    )
    previous_planner = _normalize_planner_summary(state.get("last_planner_summary"))
    if previous_planner is None and turns:
        previous_planner = _normalize_planner_summary(turns[-1].get("planner_summary"))
    if previous_planner is None and turns:
        previous_planner = _normalize_planner_summary(
            {
                "decision_result": turns[-1].get("decision"),
                "standalone_query": turns[-1].get("standalone_query"),
            }
        )
    return {
        "recent_topic_anchors": recent_topic_anchors[:8],
        "pending_clarify": pending_clarify,
        "previous_planner": previous_planner,
    }


def load_user_honesty_preferences(
    session_id: str,
    *,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
    max_age_hours: int = 24,
) -> dict[str, Any]:
    """加载用户对低置信度提示的偏好设置。

    Args:
        session_id: 会话ID
        store_path: 存储路径
        backend: 存储后端
        redis_url: Redis URL
        redis_key_prefix: Redis键前缀
        redis_fallback_to_file: 是否回退到文件
        max_age_hours: 偏好设置的最大有效期（小时）

    Returns:
        用户偏好设置字典，包含 hide_low_confidence_warnings、acknowledged_at、acknowledgment_count
    """
    session, _ = _read_session_record(
        session_id,
        store_path=store_path,
        backend=backend,
        redis_url=redis_url,
        redis_key_prefix=redis_key_prefix,
        redis_fallback_to_file=redis_fallback_to_file,
    )
    state = session.get("state", {})
    honesty_prefs = state.get("user_honesty_preferences", {})

    if not isinstance(honesty_prefs, dict):
        return {
            "hide_low_confidence_warnings": False,
            "acknowledged_at": None,
            "acknowledgment_count": 0,
        }

    # 检查偏好是否过期
    acknowledged_at = honesty_prefs.get("acknowledged_at")
    if acknowledged_at and max_age_hours > 0:
        try:
            ack_time = datetime.fromisoformat(
                str(acknowledged_at).replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            age_hours = (now - ack_time).total_seconds() / 3600
            if age_hours > max_age_hours:
                # 偏好已过期，重置
                return {
                    "hide_low_confidence_warnings": False,
                    "acknowledged_at": None,
                    "acknowledgment_count": 0,
                }
        except (ValueError, TypeError):
            pass

    return {
        "hide_low_confidence_warnings": bool(
            honesty_prefs.get("hide_low_confidence_warnings", False)
        ),
        "acknowledged_at": honesty_prefs.get("acknowledged_at"),
        "acknowledgment_count": int(honesty_prefs.get("acknowledgment_count", 0)),
    }


def save_user_honesty_preference(
    session_id: str,
    hide_warnings: bool = True,
    *,
    store_path: str | Path = "data/session_store.json",
    backend: str | None = None,
    redis_url: str | None = None,
    redis_ttl_sec: int = 86400,
    redis_key_prefix: str = "rag",
    redis_fallback_to_file: bool = True,
) -> bool:
    """保存用户对低置信度提示的偏好设置。

    Args:
        session_id: 会话ID
        hide_warnings: 是否隐藏低置信度警告
        store_path: 存储路径
        backend: 存储后端
        redis_url: Redis URL
        redis_ttl_sec: Redis TTL
        redis_key_prefix: Redis键前缀
        redis_fallback_to_file: 是否回退到文件

    Returns:
        是否保存成功
    """
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
        state = {}
        session["state"] = state

    # 获取当前的偏好设置
    honesty_prefs = state.get("user_honesty_preferences", {})
    if not isinstance(honesty_prefs, dict):
        honesty_prefs = {}

    # 更新偏好设置
    current_count = int(honesty_prefs.get("acknowledgment_count", 0))
    honesty_prefs["hide_low_confidence_warnings"] = hide_warnings
    honesty_prefs["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
    honesty_prefs["acknowledgment_count"] = current_count + 1

    state["user_honesty_preferences"] = honesty_prefs

    # 保存会话
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
    return True
