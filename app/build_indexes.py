from __future__ import annotations

import argparse
import sys

from app.config import load_and_validate_config
from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index
from app.vector_backend import resolve_vector_backend


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build BM25 and vector indexes")
    parser.add_argument(
        "--input",
        default="data/processed/chunks_clean.jsonl",
        help="Input chunks_clean.jsonl path",
    )
    parser.add_argument(
        "--bm25-out", default="data/indexes/bm25_index.json", help="BM25 output path"
    )
    parser.add_argument(
        "--vec-out", default="data/indexes/vec_index.json", help="Vector output path"
    )
    parser.add_argument(
        "--embed-out",
        default="data/indexes/vec_index_embed.json",
        help="Embedding vector index path",
    )
    parser.add_argument("--config", default="configs/default.yaml", help="Config path")
    parser.add_argument(
        "--index-mode",
        default="auto",
        choices=["auto", "rebuild", "incremental"],
        help="Index update strategy. incremental is reserved for future staged rollout.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config, warnings = load_and_validate_config(args.config)
    for warning in warnings:
        print(f"[config-warning] {warning}")

    requested_mode = str(args.index_mode).strip()
    if requested_mode == "auto":
        requested_mode = (
            "incremental"
            if bool(getattr(config, "index_incremental_enabled", False))
            else "rebuild"
        )
    if requested_mode == "incremental":
        print(
            "[index] incremental mode is reserved and currently falls back to rebuild strategy "
            f"(configured strategy={getattr(config, 'index_incremental_strategy', 'rebuild')})."
        )
    bm25 = build_bm25_index(args.input, args.bm25_out)
    vec = build_vec_index(args.input, args.vec_out)
    print(f"BM25 docs: {len(bm25.docs)} -> {args.bm25_out}")
    print(f"Vector docs: {len(vec.docs)} -> {args.vec_out}")
    if config.embedding.enabled:
        # Determine vector backend from config (defaults to "file" for backward compatibility)
        vector_backend_name = (
            getattr(config, "vector_store", {}).get("backend", "file")
            if hasattr(config, "vector_store")
            else "file"
        )
        backend = resolve_vector_backend(vector_backend_name)
        last_reported = {"step": -1}

        def _progress(step: int, total: int) -> None:
            total = max(1, int(total))
            step = min(max(0, int(step)), total)
            interval = max(1, total // 100)
            if (
                last_reported["step"] != -1
                and step != total
                and step - last_reported["step"] < interval
            ):
                return
            last_reported["step"] = step
            print(
                f"\rEmbedding progress: {step}/{total}",
                end="",
                file=sys.stderr,
                flush=True,
            )

        def _status(msg: str) -> None:
            print(f"\n[embedding] {msg}", file=sys.stderr, flush=True)

        embed, stats = backend.rebuild(
            chunks_path=args.input,
            output_path=args.embed_out,
            embedding_cfg=config.embedding,
            progress_callback=_progress,
            status_callback=_status,
        )
        print(file=sys.stderr)
        print(f"Embedding docs: {len(embed.docs)} -> {args.embed_out}")
        print(
            "Embedding stats: "
            f"hits={stats.cache_hits}, miss={stats.cache_miss}, api_calls={stats.api_calls}, "
            f"failed={stats.failed_items}, failure_records={stats.failure_records_written}, "
            f"skipped_empty={stats.skipped_empty}, truncated={stats.truncated_count}, "
            f"skipped_over_limit={stats.skipped_over_limit_count}, rate_limited={stats.rate_limited_count}, "
            f"backoff_total_ms={stats.backoff_total_ms}, build_time_ms={stats.build_time_ms}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
