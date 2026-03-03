from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


def ndcg_at_k(ideal: list[str], predicted: list[str], k: int = 10) -> float:
    if not ideal:
        return 0.0
    ideal_set = set(ideal)
    dcg = 0.0
    for i, sid in enumerate(predicted[:k], start=1):
        rel = 1.0 if sid in ideal_set else 0.0
        dcg += rel / (1 if i == 1 else __import__('math').log2(i))
    idcg = 0.0
    for i in range(1, min(len(ideal), k) + 1):
        idcg += 1.0 / (1 if i == 1 else __import__('math').log2(i))
    return dcg / idcg if idcg > 0 else 0.0


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description='Evaluate offline metrics dashboard')
    parser.add_argument('--dataset', required=True, help='Path to dataset jsonl')
    parser.add_argument('--predictions', required=True, help='Path to predictions json')
    parser.add_argument('--out', default='reports/offline_metrics_dashboard.md', help='Output markdown path')
    args = parser.parse_args()

    dataset = {row['id']: row for row in load_jsonl(Path(args.dataset))}
    predictions = json.loads(Path(args.predictions).read_text(encoding='utf-8'))

    ndcgs = []
    coverage = []
    clarify_flags = []
    latency = []
    for row in predictions:
        qid = row['id']
        expected = dataset.get(qid, {})
        ideal = expected.get('ideal_source_ids', [])
        predicted = row.get('ranked_source_ids', [])
        ndcgs.append(ndcg_at_k(ideal, predicted, k=10))
        coverage.append(float(row.get('citation_coverage', 0.0)))
        clarify_flags.append(1.0 if bool(row.get('clarify', False)) else 0.0)
        latency.append(float(row.get('first_token_latency_ms', 0.0)))

    summary = {
        'nDCG@10': round(mean(ndcgs), 4) if ndcgs else 0.0,
        'citation_coverage': round(mean(coverage), 4) if coverage else 0.0,
        'clarify_rate': round(mean(clarify_flags), 4) if clarify_flags else 0.0,
        'first_token_latency_ms': round(mean(latency), 2) if latency else 0.0,
        'samples': len(predictions),
    }

    lines = [
        '# Offline Metrics Dashboard',
        '',
        '| Metric | Value |',
        '| --- | ---: |',
        f"| nDCG@10 | {summary['nDCG@10']} |",
        f"| Citation Coverage | {summary['citation_coverage']} |",
        f"| Clarify Rate | {summary['clarify_rate']} |",
        f"| First Token Latency (ms) | {summary['first_token_latency_ms']} |",
        f"| Samples | {summary['samples']} |",
        '',
    ]
    Path(args.out).write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
