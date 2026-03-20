from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.fs_utils import atomic_text_writer, file_lock
from app.paths import RUNS_DIR


ALLOWED_SHADOW_REVIEW_LABELS = ("accepted", "needs_followup", "incorrect", "blocked")
SHADOW_REVIEW_DIRNAME = "planner_shadow_reviews"
SHADOW_REVIEW_HISTORY_FILENAME = "reviews.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_trace_id(trace_id: str) -> str:
    cleaned = "".join(ch for ch in str(trace_id or "").strip() if ch.isalnum() or ch in {"-", "_"})
    if not cleaned:
        raise ValueError("trace_id is required")
    return cleaned


def _review_store_dir(base_dir: str | Path = RUNS_DIR) -> Path:
    return Path(base_dir) / SHADOW_REVIEW_DIRNAME


def save_shadow_review(
    *,
    trace_id: str,
    label: str,
    reviewer: str | None = None,
    notes: str | None = None,
    planner_source_mode: str | None = None,
    base_dir: str | Path = RUNS_DIR,
) -> dict[str, Any]:
    normalized_trace_id = _normalize_trace_id(trace_id)
    normalized_label = str(label or "").strip()
    if normalized_label not in ALLOWED_SHADOW_REVIEW_LABELS:
        raise ValueError(f"invalid label: {normalized_label}")

    store_dir = _review_store_dir(base_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    history_path = store_dir / SHADOW_REVIEW_HISTORY_FILENAME
    latest_path = store_dir / f"{normalized_trace_id}.json"
    payload = {
        "trace_id": normalized_trace_id,
        "label": normalized_label,
        "reviewer": (str(reviewer).strip() or None) if reviewer is not None else None,
        "notes": (str(notes).strip() or None) if notes is not None else None,
        "planner_source_mode": (str(planner_source_mode).strip() or None) if planner_source_mode is not None else None,
        "updated_at": _utc_now(),
        "allowed_labels": list(ALLOWED_SHADOW_REVIEW_LABELS),
    }

    with file_lock(history_path.with_suffix(".lock")):
        with atomic_text_writer(latest_path) as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n")
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

    return payload
