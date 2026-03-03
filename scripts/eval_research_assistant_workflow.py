from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate 2-minute research assistant workflow completion.")
    parser.add_argument("--events", required=True, help="Path to workflow events json file.")
    parser.add_argument("--out", default="reports/research_assistant_workflow_eval.json", help="Output report path.")
    return parser.parse_args()


def _load_events(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    raise ValueError("events file must be a JSON list")


def evaluate(events: list[dict[str, Any]]) -> dict[str, Any]:
    sessions: dict[str, dict[str, Any]] = {}
    for row in events:
        sid = str(row.get("session_id", "")).strip()
        if not sid:
            continue
        sessions.setdefault(
            sid,
            {
                "imports": 0,
                "asked": False,
                "first_card_ts": None,
                "start_ts": None,
            },
        )
        state = sessions[sid]
        ts = float(row.get("ts", 0) or 0)
        if state["start_ts"] is None or ts < state["start_ts"]:
            state["start_ts"] = ts
        action = str(row.get("action", "")).strip()
        if action == "import_success":
            state["imports"] += int(row.get("count", 0) or 0)
        if action == "ask_question":
            state["asked"] = True
        if action == "save_idea_card" and state["first_card_ts"] is None:
            state["first_card_ts"] = ts

    completed = 0
    first_card_durations: list[float] = []
    for state in sessions.values():
        if state["imports"] >= 5 and state["asked"] and state["first_card_ts"] is not None and state["start_ts"] is not None:
            completed += 1
            first_card_durations.append(float(state["first_card_ts"]) - float(state["start_ts"]))

    total = len(sessions)
    completion_rate = (completed / total) if total else 0.0
    avg_first_card_seconds = (sum(first_card_durations) / len(first_card_durations)) if first_card_durations else None
    return {
        "sessions_total": total,
        "sessions_completed": completed,
        "completion_rate": completion_rate,
        "avg_first_card_seconds": avg_first_card_seconds,
    }


def main() -> int:
    args = parse_args()
    report = evaluate(_load_events(Path(args.events)))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
