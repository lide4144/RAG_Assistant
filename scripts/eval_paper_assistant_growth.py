from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_SAMPLE_FIELDS = {
    "id",
    "session_id",
    "turn_index",
    "question",
    "bucket",
    "same_topic",
    "is_out_of_corpus",
}

BUCKETS = ("A_open_summary", "B_multi_turn", "C_control_mixed", "D_ooc")

# Growth-first gates
GATE = {
    "a_answer_with_citation_min": 0.70,
    "a_refuse_max": 0.10,
    "b_chain_has_answer_with_citation_min": 0.80,
    "b_max_clarify_streak": 2,
    "b_third_turn_force_answer_min": 0.95,
    "c_control_recovery_min": 0.85,
    "c_control_misroute_max": 0.15,
    "d_answer_rate_max": 0.10,
    "d_unsafe_answer_max": 0.03,
    "delta_answer_with_citation_min": 0.15,
    "delta_refuse_max": -0.10,
    "hard_no_citation_assertion_max": 0.02,
}

LOW_CONF_MARKERS = ("低置信", "待验证", "不确定", "insufficient", "uncertain")


@dataclass
class EvalSample:
    sample_id: str
    session_id: str
    turn_index: int
    question: str
    bucket: str
    same_topic: bool
    is_out_of_corpus: bool


@dataclass
class RunRow:
    strategy: str
    sample: EvalSample
    run_dir: str
    decision: str
    answer: str
    answer_citations: list[dict[str, Any]]
    clarify_count: int
    clarify_limit_hit: bool
    final_refuse_source: str | None
    intent_type: str
    topic_query_source: str


@dataclass
class StrategyMetrics:
    totals: dict[str, Any]
    buckets: dict[str, dict[str, Any]]
    by_session: dict[str, list[RunRow]]


def _load_samples(path: Path) -> list[EvalSample]:
    rows: list[EvalSample] = []
    seen_ids: set[str] = set()
    buckets_seen: set[str] = set()
    for ln, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        payload = json.loads(line)
        missing = REQUIRED_SAMPLE_FIELDS - set(payload.keys())
        if missing:
            raise ValueError(f"line {ln}: missing required fields: {sorted(missing)}")
        sample_id = str(payload["id"]).strip()
        if not sample_id:
            raise ValueError(f"line {ln}: empty id")
        if sample_id in seen_ids:
            raise ValueError(f"line {ln}: duplicate id `{sample_id}`")
        seen_ids.add(sample_id)
        bucket = str(payload["bucket"])
        if bucket not in BUCKETS:
            raise ValueError(f"line {ln}: unknown bucket `{bucket}`")
        buckets_seen.add(bucket)
        rows.append(
            EvalSample(
                sample_id=sample_id,
                session_id=str(payload["session_id"]),
                turn_index=int(payload["turn_index"]),
                question=str(payload["question"]),
                bucket=bucket,
                same_topic=bool(payload["same_topic"]),
                is_out_of_corpus=bool(payload["is_out_of_corpus"]),
            )
        )
    if set(BUCKETS) - buckets_seen:
        raise ValueError(f"missing buckets: {sorted(set(BUCKETS) - buckets_seen)}")
    return sorted(rows, key=lambda r: (r.session_id, r.turn_index, r.sample_id))


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return payload


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def validate_comparable_configs(legacy_cfg: Path, growth_cfg: Path) -> tuple[bool, list[str], dict[str, Any], dict[str, Any]]:
    a = _flatten(_load_yaml(legacy_cfg))
    b = _flatten(_load_yaml(growth_cfg))
    errors: list[str] = []
    allowed_diff = {"assistant_mode_force_legacy_gate"}

    keys = set(a.keys()) | set(b.keys())
    for key in sorted(keys):
        va = a.get(key)
        vb = b.get(key)
        if key in allowed_diff:
            continue
        if va != vb:
            errors.append(f"config mismatch on `{key}`: legacy={va!r}, growth={vb!r}")

    if a.get("assistant_mode_force_legacy_gate") is not True:
        errors.append("legacy config must set assistant_mode_force_legacy_gate=true")
    if b.get("assistant_mode_force_legacy_gate") is not False:
        errors.append("growth config must set assistant_mode_force_legacy_gate=false")
    return (len(errors) == 0, errors, a, b)


def _latest_new_run_dir(runs_dir: Path, before: set[str]) -> Path | None:
    candidates = [p for p in runs_dir.glob("*") if p.is_dir() and p.name not in before]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def decision_from_report(report: dict[str, Any]) -> str:
    # Release scoring uses qa_report.decision as the only decision source.
    return str(report.get("decision") or "")


def _run_one(
    *,
    python_bin: str,
    repo_root: Path,
    runs_dir: Path,
    sample: EvalSample,
    strategy: str,
    config_path: str,
    mode: str,
    chunks: str,
    bm25_index: str,
    vec_index: str,
    embed_index: str,
    top_k: int,
    top_evidence: int,
) -> RunRow:
    before = {p.name for p in runs_dir.glob("*") if p.is_dir()}
    cmd = [
        python_bin,
        "-m",
        "app.qa",
        "--q",
        sample.question,
        "--mode",
        mode,
        "--config",
        config_path,
        "--chunks",
        chunks,
        "--bm25-index",
        bm25_index,
        "--vec-index",
        vec_index,
        "--embed-index",
        embed_index,
        "--session-id",
        sample.session_id,
        "--top-k",
        str(top_k),
        "--top-evidence",
        str(top_evidence),
    ]
    if sample.turn_index == 1:
        cmd.append("--clear-session")

    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-20:])
        raise RuntimeError(f"qa command failed for {sample.sample_id} ({strategy}):\n{tail}")

    run_dir = _latest_new_run_dir(runs_dir, before)
    if run_dir is None:
        raise RuntimeError(f"no run dir generated for {sample.sample_id} ({strategy})")

    report_path = run_dir / "qa_report.json"
    if not report_path.exists():
        raise RuntimeError(f"qa_report.json missing: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    decision = decision_from_report(report)
    return RunRow(
        strategy=strategy,
        sample=sample,
        run_dir=str(run_dir.relative_to(repo_root)),
        decision=decision,
        answer=str(report.get("answer") or ""),
        answer_citations=report.get("answer_citations") if isinstance(report.get("answer_citations"), list) else [],
        clarify_count=int(report.get("clarify_count") or 0),
        clarify_limit_hit=bool(report.get("clarify_limit_hit")),
        final_refuse_source=(str(report.get("final_refuse_source")) if report.get("final_refuse_source") else None),
        intent_type=str(report.get("intent_type") or ""),
        topic_query_source=str(report.get("topic_query_source") or ""),
    )


def _answer_with_citation(row: RunRow) -> bool:
    return row.decision == "answer" and len(row.answer_citations) > 0


def _unsafe_ooc_answer(row: RunRow) -> bool:
    if not row.sample.is_out_of_corpus or row.decision != "answer":
        return False
    if not row.answer_citations:
        return True
    lowered = row.answer.lower()
    return not any(marker.lower() in lowered for marker in LOW_CONF_MARKERS)


def _max_clarify_streak(rows: list[RunRow]) -> int:
    streak = 0
    best = 0
    for row in sorted(rows, key=lambda x: (x.sample.turn_index, x.sample.sample_id)):
        if row.decision == "clarify":
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def _bucket_metrics(rows: list[RunRow]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {"total": 0}
    refuse = sum(1 for r in rows if r.decision == "refuse")
    clarify = sum(1 for r in rows if r.decision == "clarify")
    answer = sum(1 for r in rows if r.decision == "answer")
    answer_cited = sum(1 for r in rows if _answer_with_citation(r))
    unsafe_ooc = sum(1 for r in rows if _unsafe_ooc_answer(r))
    no_citation_answer = sum(1 for r in rows if r.decision == "answer" and not r.answer_citations)
    return {
        "total": total,
        "answer": answer,
        "clarify": clarify,
        "refuse": refuse,
        "answer_with_citation": answer_cited,
        "refuse_rate": refuse / total,
        "clarify_rate": clarify / total,
        "answer_rate": answer / total,
        "answer_with_citation_rate": answer_cited / total,
        "unsafe_ooc_answer": unsafe_ooc,
        "unsafe_ooc_answer_rate": unsafe_ooc / total,
        "no_citation_answer": no_citation_answer,
        "no_citation_answer_rate": no_citation_answer / total,
    }


def summarize(rows: list[RunRow]) -> StrategyMetrics:
    by_bucket: dict[str, list[RunRow]] = defaultdict(list)
    by_session: dict[str, list[RunRow]] = defaultdict(list)
    for row in rows:
        by_bucket[row.sample.bucket].append(row)
        by_session[row.sample.session_id].append(row)

    buckets = {bucket: _bucket_metrics(by_bucket.get(bucket, [])) for bucket in BUCKETS}
    all_metrics = _bucket_metrics(rows)

    chains = [session_rows for session_rows in by_session.values() if any(r.sample.bucket == "B_multi_turn" for r in session_rows)]
    if chains:
        chain_answer_hit = 0
        chain_answer_hit_in_two = 0
        third_turn_force_answer = 0
        third_turn_total = 0
        max_streak = 0
        for chain in chains:
            chain_sorted = sorted(chain, key=lambda r: (r.sample.turn_index, r.sample.sample_id))
            max_streak = max(max_streak, _max_clarify_streak(chain_sorted))
            if any(_answer_with_citation(r) for r in chain_sorted):
                chain_answer_hit += 1
            if any(_answer_with_citation(r) for r in chain_sorted if r.sample.turn_index <= 2):
                chain_answer_hit_in_two += 1
            turn3 = [r for r in chain_sorted if r.sample.turn_index == 3]
            for r in turn3:
                third_turn_total += 1
                if r.decision == "answer":
                    third_turn_force_answer += 1
        all_metrics.update(
            {
                "chain_total": len(chains),
                "chain_has_answer_with_citation": chain_answer_hit,
                "chain_has_answer_with_citation_rate": chain_answer_hit / len(chains),
                "chain_has_answer_with_citation_in_two": chain_answer_hit_in_two,
                "chain_has_answer_with_citation_in_two_rate": chain_answer_hit_in_two / len(chains),
                "max_consecutive_clarify": max_streak,
                "third_turn_force_answer_total": third_turn_total,
                "third_turn_force_answer": third_turn_force_answer,
                "third_turn_force_answer_rate": (third_turn_force_answer / third_turn_total) if third_turn_total else 1.0,
            }
        )

    control_rows = by_bucket.get("C_control_mixed", [])
    if control_rows:
        misroute = sum(1 for r in control_rows if r.intent_type != "retrieval_query" and r.topic_query_source == "user_query")
        recover = sum(1 for r in control_rows if r.intent_type == "retrieval_query")
        all_metrics["control_misroute_rate"] = misroute / len(control_rows)
        all_metrics["control_recovery_rate"] = recover / len(control_rows)

    return StrategyMetrics(totals=all_metrics, buckets=buckets, by_session=by_session)


def evaluate_gates(legacy: StrategyMetrics, growth: StrategyMetrics) -> tuple[bool, list[str]]:
    errors: list[str] = []

    g_a = growth.buckets.get("A_open_summary", {})
    if g_a.get("answer_with_citation_rate", 0.0) < GATE["a_answer_with_citation_min"]:
        errors.append("A_open_summary answer_with_citation_rate below growth threshold")
    if g_a.get("refuse_rate", 1.0) > GATE["a_refuse_max"]:
        errors.append("A_open_summary refuse_rate above growth threshold")

    g_tot = growth.totals
    if g_tot.get("chain_has_answer_with_citation_in_two_rate", 0.0) < GATE["b_chain_has_answer_with_citation_min"]:
        errors.append("B_multi_turn chain_has_answer_with_citation_in_two_rate below threshold")
    if g_tot.get("max_consecutive_clarify", 99) > GATE["b_max_clarify_streak"]:
        errors.append("B_multi_turn max_consecutive_clarify exceeds threshold")
    if g_tot.get("third_turn_force_answer_rate", 0.0) < GATE["b_third_turn_force_answer_min"]:
        errors.append("B_multi_turn third_turn_force_answer_rate below threshold")

    if g_tot.get("control_misroute_rate", 1.0) > GATE["c_control_misroute_max"]:
        errors.append("C_control_mixed control_misroute_rate above threshold")
    if g_tot.get("control_recovery_rate", 0.0) < GATE["c_control_recovery_min"]:
        errors.append("C_control_mixed control_recovery_rate below threshold")

    g_d = growth.buckets.get("D_ooc", {})
    if g_d.get("answer_rate", 1.0) > GATE["d_answer_rate_max"]:
        errors.append("D_ooc answer_rate above threshold")
    if g_d.get("unsafe_ooc_answer_rate", 1.0) > GATE["d_unsafe_answer_max"]:
        errors.append("D_ooc unsafe_ooc_answer_rate above threshold")

    if growth.totals.get("no_citation_answer_rate", 1.0) > GATE["hard_no_citation_assertion_max"]:
        errors.append("hard guard no_citation_answer_rate above threshold")

    delta_answer = growth.totals.get("answer_with_citation_rate", 0.0) - legacy.totals.get("answer_with_citation_rate", 0.0)
    delta_refuse = growth.totals.get("refuse_rate", 1.0) - legacy.totals.get("refuse_rate", 1.0)
    if delta_answer < GATE["delta_answer_with_citation_min"]:
        errors.append("delta answer_with_citation_rate improvement below threshold")
    if delta_refuse > GATE["delta_refuse_max"]:
        errors.append("delta refuse_rate reduction below threshold")

    return (len(errors) == 0, errors)


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def render_report(
    *,
    legacy_cfg: str,
    growth_cfg: str,
    samples_path: str,
    legacy_metrics: StrategyMetrics,
    growth_metrics: StrategyMetrics,
    gate_ok: bool,
    gate_errors: list[str],
    config_errors: list[str],
    spoken_samples_path: str | None = None,
    spoken_legacy_metrics: StrategyMetrics | None = None,
    spoken_growth_metrics: StrategyMetrics | None = None,
    spoken_gate_ok: bool | None = None,
    spoken_gate_errors: list[str] | None = None,
    enforce_spoken_gate: bool = False,
) -> str:
    lines: list[str] = []
    lines.append("# Paper Assistant Growth Eval")
    lines.append("")
    lines.append("## 输入")
    lines.append(f"- 问题集: `{samples_path}`")
    if spoken_samples_path:
        lines.append(f"- 口语问题集: `{spoken_samples_path}`")
    lines.append(f"- 旧策略配置: `{legacy_cfg}`")
    lines.append(f"- 新策略配置: `{growth_cfg}`")
    lines.append("")
    lines.append("## 总体对比")
    lines.append("")
    lines.append("| 指标 | 旧策略 | 新策略 | 变化 |")
    lines.append("|---|---:|---:|---:|")
    for key in ("refuse_rate", "clarify_rate", "answer_with_citation_rate"):
        lv = float(legacy_metrics.totals.get(key, 0.0))
        gv = float(growth_metrics.totals.get(key, 0.0))
        lines.append(f"| {key} | {_fmt_pct(lv)} | {_fmt_pct(gv)} | {_fmt_pct(gv - lv)} |")

    if spoken_legacy_metrics is not None and spoken_growth_metrics is not None and spoken_samples_path:
        lines.append("")
        lines.append("## 口语问题集对比")
        lines.append("")
        lines.append("| 指标 | 旧策略 | 新策略 | 变化 |")
        lines.append("|---|---:|---:|---:|")
        for key in ("refuse_rate", "clarify_rate", "answer_with_citation_rate"):
            lv = float(spoken_legacy_metrics.totals.get(key, 0.0))
            gv = float(spoken_growth_metrics.totals.get(key, 0.0))
            lines.append(f"| {key} | {_fmt_pct(lv)} | {_fmt_pct(gv)} | {_fmt_pct(gv - lv)} |")

    lines.append("")
    lines.append("## 分桶结果")
    lines.append("")
    lines.append("| Bucket | Strategy | total | refuse | clarify | answer+citation |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for bucket in BUCKETS:
        l = legacy_metrics.buckets.get(bucket, {"total": 0})
        g = growth_metrics.buckets.get(bucket, {"total": 0})
        lines.append(f"| {bucket} | legacy | {l.get('total', 0)} | {_fmt_pct(float(l.get('refuse_rate', 0.0)))} | {_fmt_pct(float(l.get('clarify_rate', 0.0)))} | {_fmt_pct(float(l.get('answer_with_citation_rate', 0.0)))} |")
        lines.append(f"| {bucket} | growth | {g.get('total', 0)} | {_fmt_pct(float(g.get('refuse_rate', 0.0)))} | {_fmt_pct(float(g.get('clarify_rate', 0.0)))} | {_fmt_pct(float(g.get('answer_with_citation_rate', 0.0)))} |")

    lines.append("")
    lines.append("## 配置一致性")
    if config_errors:
        lines.append("- FAIL")
        for err in config_errors:
            lines.append(f"- {err}")
    else:
        lines.append("- PASS")

    lines.append("")
    lines.append("## 发布门禁")
    primary_ok = gate_ok and not config_errors
    lines.append(f"- 主问题集: {'PASS' if primary_ok else 'FAIL'}")
    if gate_errors:
        lines.append("- 主问题集不通过项:")
        for err in gate_errors:
            lines.append(f"- {err}")
    if spoken_gate_ok is not None:
        lines.append(f"- 口语问题集: {'PASS' if spoken_gate_ok else 'FAIL'}")
        lines.append(f"- 口语门禁是否阻断发布: {'是' if enforce_spoken_gate else '否（观测项）'}")
    if spoken_gate_errors:
        lines.append("- 口语问题集不通过项:")
        for err in spoken_gate_errors:
            lines.append(f"- {err}")
    release_ok = primary_ok and (spoken_gate_ok if (spoken_gate_ok is not None and enforce_spoken_gate) else True)
    lines.append(f"- 结果: {'PASS' if release_ok else 'FAIL'}")

    lines.append("")
    lines.append("## 回滚建议")
    if release_ok:
        lines.append("- 当前评测通过，无需回滚。")
    else:
        lines.append("- 建议将 `assistant_mode_force_legacy_gate=true` 作为临时回滚。")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate paper-assistant growth release gate.")
    parser.add_argument("--samples", default="reports/paper_assistant_questions_v1.jsonl")
    parser.add_argument("--spoken-samples", default="reports/paper_assistant_questions_spoken_v1.jsonl")
    parser.add_argument("--legacy-config", default="configs/paper_assistant_growth_legacy.yaml")
    parser.add_argument("--growth-config", default="configs/paper_assistant_growth.yaml")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--mode", default="hybrid", choices=["bm25", "dense", "hybrid"])
    parser.add_argument("--chunks", default="data/processed/chunks_clean.jsonl")
    parser.add_argument("--bm25-index", default="data/indexes/bm25_index.json")
    parser.add_argument("--vec-index", default="data/indexes/vec_index.json")
    parser.add_argument("--embed-index", default="data/indexes/vec_index_embed.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--top-evidence", type=int, default=5)
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--out-json", default="reports/paper_assistant_growth_eval.json")
    parser.add_argument("--out-md", default="reports/paper_assistant_growth_eval.md")
    parser.add_argument("--enforce-spoken-gate", action="store_true", help="Treat spoken sample gate as release-blocking")
    parser.add_argument("--skip-run", action="store_true", help="Only validate inputs/config; no qa replay")
    args = parser.parse_args(argv)

    repo_root = Path(".").resolve()
    samples_path = (repo_root / args.samples).resolve()
    spoken_samples_path = (repo_root / args.spoken_samples).resolve() if str(args.spoken_samples).strip() else None
    legacy_cfg = (repo_root / args.legacy_config).resolve()
    growth_cfg = (repo_root / args.growth_config).resolve()
    runs_dir = (repo_root / args.runs_dir).resolve()

    samples = _load_samples(samples_path)
    spoken_samples: list[EvalSample] = []
    has_spoken_samples = bool(spoken_samples_path and spoken_samples_path.exists())
    if has_spoken_samples and spoken_samples_path is not None:
        spoken_samples = _load_samples(spoken_samples_path)
    comparable, config_errors, legacy_snapshot, growth_snapshot = validate_comparable_configs(legacy_cfg, growth_cfg)

    rows_legacy: list[RunRow] = []
    rows_growth: list[RunRow] = []
    spoken_rows_legacy: list[RunRow] = []
    spoken_rows_growth: list[RunRow] = []

    if not args.skip_run:
        runs_dir.mkdir(parents=True, exist_ok=True)
        for sample in samples:
            rows_legacy.append(
                _run_one(
                    python_bin=args.python,
                    repo_root=repo_root,
                    runs_dir=runs_dir,
                    sample=sample,
                    strategy="legacy",
                    config_path=str(legacy_cfg),
                    mode=args.mode,
                    chunks=args.chunks,
                    bm25_index=args.bm25_index,
                    vec_index=args.vec_index,
                    embed_index=args.embed_index,
                    top_k=args.top_k,
                    top_evidence=args.top_evidence,
                )
            )
        for sample in samples:
            rows_growth.append(
                _run_one(
                    python_bin=args.python,
                    repo_root=repo_root,
                    runs_dir=runs_dir,
                    sample=sample,
                    strategy="growth",
                    config_path=str(growth_cfg),
                    mode=args.mode,
                    chunks=args.chunks,
                    bm25_index=args.bm25_index,
                    vec_index=args.vec_index,
                    embed_index=args.embed_index,
                    top_k=args.top_k,
                    top_evidence=args.top_evidence,
                )
            )
        for sample in spoken_samples:
            spoken_rows_legacy.append(
                _run_one(
                    python_bin=args.python,
                    repo_root=repo_root,
                    runs_dir=runs_dir,
                    sample=sample,
                    strategy="legacy",
                    config_path=str(legacy_cfg),
                    mode=args.mode,
                    chunks=args.chunks,
                    bm25_index=args.bm25_index,
                    vec_index=args.vec_index,
                    embed_index=args.embed_index,
                    top_k=args.top_k,
                    top_evidence=args.top_evidence,
                )
            )
        for sample in spoken_samples:
            spoken_rows_growth.append(
                _run_one(
                    python_bin=args.python,
                    repo_root=repo_root,
                    runs_dir=runs_dir,
                    sample=sample,
                    strategy="growth",
                    config_path=str(growth_cfg),
                    mode=args.mode,
                    chunks=args.chunks,
                    bm25_index=args.bm25_index,
                    vec_index=args.vec_index,
                    embed_index=args.embed_index,
                    top_k=args.top_k,
                    top_evidence=args.top_evidence,
                )
            )

    legacy_metrics = summarize(rows_legacy)
    growth_metrics = summarize(rows_growth)
    spoken_legacy_metrics = summarize(spoken_rows_legacy) if has_spoken_samples else None
    spoken_growth_metrics = summarize(spoken_rows_growth) if has_spoken_samples else None

    gate_ok, gate_errors = evaluate_gates(legacy_metrics, growth_metrics)
    spoken_gate_ok: bool | None = None
    spoken_gate_errors: list[str] = []
    if spoken_legacy_metrics is not None and spoken_growth_metrics is not None:
        spoken_gate_ok, spoken_gate_errors = evaluate_gates(spoken_legacy_metrics, spoken_growth_metrics)

    primary_passed = comparable and gate_ok and (len(rows_legacy) == len(samples) == len(rows_growth) or args.skip_run)
    spoken_passed = True
    if args.enforce_spoken_gate and spoken_gate_ok is not None:
        spoken_passed = spoken_gate_ok and (len(spoken_rows_legacy) == len(spoken_samples) == len(spoken_rows_growth) or args.skip_run)
    passed = primary_passed and spoken_passed

    out = {
        "samples": str(samples_path.relative_to(repo_root)),
        "spoken_samples": (str(spoken_samples_path.relative_to(repo_root)) if has_spoken_samples and spoken_samples_path else None),
        "legacy_config": str(legacy_cfg.relative_to(repo_root)),
        "growth_config": str(growth_cfg.relative_to(repo_root)),
        "config_comparable": comparable,
        "config_errors": config_errors,
        "legacy_config_snapshot": legacy_snapshot,
        "growth_config_snapshot": growth_snapshot,
        "gate_ok": gate_ok,
        "gate_errors": gate_errors,
        "spoken_gate_ok": spoken_gate_ok,
        "spoken_gate_errors": spoken_gate_errors,
        "enforce_spoken_gate": bool(args.enforce_spoken_gate),
        "passed": passed,
        "legacy": legacy_metrics.totals,
        "growth": growth_metrics.totals,
        "legacy_bucket": legacy_metrics.buckets,
        "growth_bucket": growth_metrics.buckets,
        "spoken_legacy": (spoken_legacy_metrics.totals if spoken_legacy_metrics else {}),
        "spoken_growth": (spoken_growth_metrics.totals if spoken_growth_metrics else {}),
        "spoken_legacy_bucket": (spoken_legacy_metrics.buckets if spoken_legacy_metrics else {}),
        "spoken_growth_bucket": (spoken_growth_metrics.buckets if spoken_growth_metrics else {}),
        "legacy_rows": [r.__dict__ for r in rows_legacy],
        "growth_rows": [r.__dict__ for r in rows_growth],
        "spoken_legacy_rows": [r.__dict__ for r in spoken_rows_legacy],
        "spoken_growth_rows": [r.__dict__ for r in spoken_rows_growth],
    }

    out_json = (repo_root / args.out_json).resolve()
    out_md = (repo_root / args.out_md).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(
        render_report(
            legacy_cfg=str(legacy_cfg.relative_to(repo_root)),
            growth_cfg=str(growth_cfg.relative_to(repo_root)),
            samples_path=str(samples_path.relative_to(repo_root)),
            legacy_metrics=legacy_metrics,
            growth_metrics=growth_metrics,
            gate_ok=gate_ok,
            gate_errors=gate_errors,
            config_errors=config_errors,
            spoken_samples_path=(str(spoken_samples_path.relative_to(repo_root)) if has_spoken_samples and spoken_samples_path else None),
            spoken_legacy_metrics=spoken_legacy_metrics,
            spoken_growth_metrics=spoken_growth_metrics,
            spoken_gate_ok=spoken_gate_ok,
            spoken_gate_errors=spoken_gate_errors,
            enforce_spoken_gate=bool(args.enforce_spoken_gate),
        ),
        encoding="utf-8",
    )

    if not passed:
        print(f"[FAIL] growth gate failed. details: {out_json}", file=sys.stderr)
        return 1
    print(f"[OK] growth gate passed. details: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
