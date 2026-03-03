from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


def render_report(samples: list[dict[str, object]], report_title: str) -> str:
    rows: list[dict[str, object]] = []
    baseline_gate = 0
    optimized_gate = 0
    hit_depth_improved = 0

    for idx, item in enumerate(samples, start=1):
        user_input = str(item.get("user_input", ""))
        baseline_query = str(item.get("baseline_query", ""))
        entities = [str(x).strip() for x in item.get("entities_from_history", []) if str(x).strip()]
        last_turn_decision = str(item.get("last_turn_decision", "")).strip() or None
        last_turn_warnings = [str(x).strip() for x in item.get("last_turn_warnings", []) if str(x).strip()]

        result = apply_state_aware_rewrite_guard(
            user_input=user_input,
            standalone_query=baseline_query,
            entities_from_history=entities,
            last_turn_decision=last_turn_decision,
            last_turn_warnings=last_turn_warnings,
        )

        before_gate = bool(item.get("before_insufficient_evidence", False))
        after_gate = bool(item.get("after_insufficient_evidence", False))
        depth_improved = bool(item.get("hit_depth_improved", False))

        if before_gate:
            baseline_gate += 1
        if after_gate:
            optimized_gate += 1
        if depth_improved:
            hit_depth_improved += 1

        rows.append(
            {
                "idx": idx,
                "sample_id": str(item.get("sample_id", f"sample-{idx:02d}")),
                "run_before": str(item.get("run_id_before", "N/A")),
                "run_after": str(item.get("run_id_after", "N/A")),
                "input": user_input,
                "before": baseline_query,
                "after": result.standalone_query,
                "entity_ok": (not entities) or any(e.lower() in result.standalone_query.lower() for e in entities),
                "no_concat": not _looks_like_mechanical_concat(result.standalone_query),
            }
        )

    total = max(1, len(rows))
    no_concat_count = sum(1 for r in rows if bool(r["no_concat"]))
    entity_ok_count = sum(1 for r in rows if bool(r["entity_ok"]))

    lines: list[str] = []
    lines.append(f"# {report_title}")
    lines.append("")
    lines.append("生成方式：`venv/bin/python scripts/eval_m7_8_meta_guard.py`")
    lines.append("")
    lines.append("## 1. standalone_query 优化前后对比（10 例）")
    lines.append("")
    lines.append("| # | sample_id | run_id(before) | run_id(after) | 场景输入（次轮） | 优化前（问题） | 优化后（M7.8） |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in rows:
        lines.append(
            "| {idx} | {sample_id} | `{run_before}` | `{run_after}` | {input} | {before} | {after} |".format(**row)
        )
    lines.append("")
    lines.append(
        f"判定结果：{no_concat_count}/{len(rows)} 样本未出现机械拼接 query，{entity_ok_count}/{len(rows)} 样本满足实体约束。"
    )
    lines.append("")
    lines.append("## 2. Evidence 命中质量变化")
    lines.append("")
    lines.append("评估口径：以样本清单中的 `hit_depth_improved` 标注计算。")
    lines.append("")
    lines.append(f"- 命中深度提升：{hit_depth_improved}/{len(rows)}")
    lines.append(f"- 噪声比例下降：{no_concat_count}/{len(rows)}（以去除机械拼接与状态词污染为代理）")
    lines.append("")
    lines.append("## 3. Gate 触发变化")
    lines.append("")
    lines.append("统计口径：同一批样本在优化前后 `insufficient_evidence_for_answer` 的触发比例。")
    lines.append("")
    lines.append(f"- 优化前：{baseline_gate}/{len(rows)}（{baseline_gate / total:.0%}）")
    lines.append(f"- 优化后：{optimized_gate}/{len(rows)}（{optimized_gate / total:.0%}）")
    lines.append(f"- 变化：下降 {baseline_gate - optimized_gate} 个样本")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate reproducible M7.8 meta guard evaluation report.")
    parser.add_argument("--samples", default="reports/m7_8_meta_guard_samples.json", help="Input sample json path")
    parser.add_argument("--output", default="reports/m7_8_meta_question_guard.md", help="Markdown report output path")
    args = parser.parse_args()

    samples_path = Path(args.samples)
    output_path = Path(args.output)

    payload = json.loads(samples_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("samples json must be a list")

    report = render_report(payload, "M7.8 Meta-question 意图重写护栏评估")
    output_path.write_text(report, encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
