from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IDEAS_STORE_PATH = Path("data/ideas_cards.json")
IDEA_STATUS_FLOW = ["draft", "shortlisted", "in_progress", "validated", "archived"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_store(path: Path = IDEAS_STORE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"cards": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"cards": []}
    cards = payload.get("cards")
    if not isinstance(cards, list):
        return {"cards": []}
    return {"cards": [row for row in cards if isinstance(row, dict)]}


def _write_store(payload: dict[str, Any], path: Path = IDEAS_STORE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_cards(path: Path = IDEAS_STORE_PATH) -> list[dict[str, Any]]:
    payload = _read_store(path)
    cards = payload.get("cards", [])
    return sorted(cards, key=lambda row: str(row.get("updated_at", "")), reverse=True)


def create_draft(
    *,
    title: str,
    research_question: str,
    method_outline: str,
    next_experiments: list[str],
    evidence: list[dict[str, str]],
    source_session_id: str,
    source_turn_idx: int,
    topic: str = "",
) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "card_id": f"idea-{uuid.uuid4().hex[:10]}",
        "title": title.strip() or "未命名灵感卡片",
        "research_question": research_question.strip(),
        "method_outline": method_outline.strip(),
        "next_experiments": [str(x).strip() for x in next_experiments if str(x).strip()],
        "evidence": [
            {
                "chunk_id": str(item.get("chunk_id", "")).strip(),
                "paper_id": str(item.get("paper_id", "")).strip(),
                "section_page": str(item.get("section_page", "")).strip(),
                "quote": str(item.get("quote", "")).strip(),
            }
            for item in evidence
            if isinstance(item, dict) and str(item.get("chunk_id", "")).strip()
        ],
        "source_session_id": source_session_id.strip(),
        "source_turn_idx": int(source_turn_idx),
        "topic": topic.strip(),
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }


def save_card(card: dict[str, Any], path: Path = IDEAS_STORE_PATH) -> dict[str, Any]:
    payload = _read_store(path)
    cards = payload.get("cards", [])
    now = _utc_now_iso()
    row = dict(card)
    row["title"] = str(row.get("title", "")).strip() or "未命名灵感卡片"
    row["research_question"] = str(row.get("research_question", "")).strip()
    row["method_outline"] = str(row.get("method_outline", "")).strip()
    row["next_experiments"] = [str(x).strip() for x in row.get("next_experiments", []) if str(x).strip()]
    row["evidence"] = [x for x in row.get("evidence", []) if isinstance(x, dict)]
    row["status"] = str(row.get("status", "draft")).strip() or "draft"
    if row["status"] not in IDEA_STATUS_FLOW:
        row["status"] = "draft"
    if not row.get("card_id"):
        row["card_id"] = f"idea-{uuid.uuid4().hex[:10]}"
    if not row.get("created_at"):
        row["created_at"] = now
    row["updated_at"] = now

    replaced = False
    for idx, existing in enumerate(cards):
        if str(existing.get("card_id")) == str(row["card_id"]):
            cards[idx] = row
            replaced = True
            break
    if not replaced:
        cards.append(row)
    payload["cards"] = cards
    _write_store(payload, path)
    return row


def can_transition(from_status: str, to_status: str) -> bool:
    current = str(from_status or "").strip()
    target = str(to_status or "").strip()
    if current not in IDEA_STATUS_FLOW or target not in IDEA_STATUS_FLOW:
        return False
    if current == target:
        return True
    return IDEA_STATUS_FLOW.index(target) == IDEA_STATUS_FLOW.index(current) + 1


def update_card_status(card_id: str, to_status: str, path: Path = IDEAS_STORE_PATH) -> tuple[bool, str]:
    payload = _read_store(path)
    cards = payload.get("cards", [])
    for idx, card in enumerate(cards):
        if str(card.get("card_id")) != str(card_id):
            continue
        current = str(card.get("status", "draft"))
        if not can_transition(current, to_status):
            return False, f"状态变更不合法: {current} -> {to_status}"
        updated = dict(card)
        updated["status"] = to_status
        updated["updated_at"] = _utc_now_iso()
        cards[idx] = updated
        payload["cards"] = cards
        _write_store(payload, path)
        return True, ""
    return False, f"未找到卡片: {card_id}"
