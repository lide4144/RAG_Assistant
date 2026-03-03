from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.qa import semantic_route_intent
from app.rewrite import apply_state_aware_rewrite_guard

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+(?:[-/][A-Za-z0-9_]+)*|[\u4e00-\u9fff]+")


def _looks_like_mechanical_concat(text: str) -> bool:
    tokens = [t.lower() for t in TOKEN_RE.findall(text or "")]
    if len(tokens) < 4:
        return False
    if len(tokens) % 2 == 0:
        half = len(tokens) // 2
        if half >= 2 and tokens[:half] == tokens[half:]:
            return True
    normalized = " ".join((text or "").split())
    return bool(re.search(r"(.{8,})\s+\1", normalized, flags=re.IGNORECASE))


def evaluate_samples(
    samples: list[dict[str, Any]],
    *,
    rewrite_entity_keep_rate_min: float = 0.9,
    route_accuracy_min: float = 0.85,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    rewrite_entity_kept = 0
    rewrite_entity_total = 0
    rewrite_no_concat = 0
    route_correct = 0
    route_total = 0

    for idx, sample in enumerate(samples, start=1):
        query = str(sample.get("query", "")).strip()
        baseline_query = str(sample.get("baseline_query", query)).strip() or query
        entities = [str(x).strip() for x in (sample.get("entities") or []) if str(x).strip()]
        expected_intent = str(sample.get("expected_intent", "")).strip() or "retrieval_query"
        history_entities = [str(x).strip() for x in (sample.get("history_entities") or entities) if str(x).strip()]

        guard = apply_state_aware_rewrite_guard(
            user_input=query,
            standalone_query=baseline_query,
            entities_from_history=history_entities,
            last_turn_decision=str(sample.get("last_turn_decision") or "").strip() or None,
            last_turn_warnings=[str(x).strip() for x in (sample.get("last_turn_warnings") or []) if str(x).strip()],
        )
        rewritten = guard.standalone_query
        route_intent, route_confidence, route_source, _ = semantic_route_intent(query)

        kept_terms: list[str] = []
        lost_terms: list[str] = []
        for ent in entities:
            rewrite_entity_total += 1
            if ent.lower() in rewritten.lower():
                rewrite_entity_kept += 1
                kept_terms.append(ent)
            else:
                lost_terms.append(ent)
        no_concat = not _looks_like_mechanical_concat(rewritten)
        if no_concat:
            rewrite_no_concat += 1
        route_total += 1
        is_route_correct = route_intent == expected_intent
        if is_route_correct:
            route_correct += 1

        rows.append(
            {
                "id": str(sample.get("id") or f"sample-{idx:02d}"),
                "query": query,
                "rewritten_query": rewritten,
                "expected_intent": expected_intent,
                "predicted_intent": route_intent,
                "route_confidence": route_confidence,
                "route_source": route_source,
                "route_correct": is_route_correct,
                "no_mechanical_concat": no_concat,
                "kept_entities": kept_terms,
                "lost_entities": lost_terms,
            }
        )

    total = max(1, len(rows))
    keep_rate = (rewrite_entity_kept / rewrite_entity_total) if rewrite_entity_total else 1.0
    no_concat_rate = rewrite_no_concat / total
    route_accuracy = route_correct / max(1, route_total)
    alerts: list[str] = []
    if keep_rate < rewrite_entity_keep_rate_min:
        alerts.append(
            "rewrite_entity_keep_rate_below_threshold:"
            f"{keep_rate:.3f}<{rewrite_entity_keep_rate_min:.3f}"
        )
    if route_accuracy < route_accuracy_min:
        alerts.append(
            "route_accuracy_below_threshold:"
            f"{route_accuracy:.3f}<{route_accuracy_min:.3f}"
        )

    return {
        "total_samples": len(rows),
        "rewrite_entity_keep_rate": keep_rate,
        "rewrite_no_concat_rate": no_concat_rate,
        "route_accuracy": route_accuracy,
        "thresholds": {
            "rewrite_entity_keep_rate_min": rewrite_entity_keep_rate_min,
            "route_accuracy_min": route_accuracy_min,
        },
        "alerts": alerts,
        "passed": not alerts,
        "rows": rows,
    }


def _load_samples(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("samples must be a json list")
    return [row for row in payload if isinstance(row, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate rewrite quality and semantic intent routing accuracy.")
    parser.add_argument("--samples", default="reports/rewrite_route_quality_samples.json")
    parser.add_argument("--out-json", default="reports/rewrite_route_quality_eval.json")
    parser.add_argument("--out-md", default="reports/rewrite_route_quality_eval.md")
    parser.add_argument("--rewrite-keep-min", type=float, default=0.9)
    parser.add_argument("--route-accuracy-min", type=float, default=0.85)
    args = parser.parse_args()

    samples = _load_samples(Path(args.samples))
    result = evaluate_samples(
        samples,
        rewrite_entity_keep_rate_min=float(args.rewrite_keep_min),
        route_accuracy_min=float(args.route_accuracy_min),
    )

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Rewrite + Routing Quality Eval",
        "",
        f"- total_samples: {result['total_samples']}",
        f"- rewrite_entity_keep_rate: {result['rewrite_entity_keep_rate']:.3f}",
        f"- rewrite_no_concat_rate: {result['rewrite_no_concat_rate']:.3f}",
        f"- route_accuracy: {result['route_accuracy']:.3f}",
        f"- passed: {result['passed']}",
        "",
        "## Alerts",
    ]
    if result["alerts"]:
        lines.extend([f"- {x}" for x in result["alerts"]])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Sample Details",
            "",
            "| id | expected_intent | predicted_intent | route_correct | no_concat | lost_entities |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for row in result["rows"]:
        lines.append(
            "| {id} | {expected_intent} | {predicted_intent} | {route_correct} | {no_mechanical_concat} | {lost_entities} |".format(
                **row
            )
        )
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
