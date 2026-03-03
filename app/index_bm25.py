from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from app.chunks_dataset import ChunkDoc, load_chunks_clean, tokenize


@dataclass
class BM25Doc:
    chunk_id: str
    paper_id: str
    page_start: int
    section: str | None
    text: str
    clean_text: str
    content_type: str


@dataclass
class BM25Index:
    docs: list[BM25Doc]
    avg_doc_len: float
    doc_lens: list[int]
    inverted: dict[str, list[list[int]]]
    idf: dict[str, float]
    k1: float = 1.5
    b: float = 0.75


def _build_index_from_docs(docs: list[ChunkDoc], k1: float = 1.5, b: float = 0.75) -> BM25Index:
    n_docs = len(docs)
    if n_docs == 0:
        return BM25Index(docs=[], avg_doc_len=0.0, doc_lens=[], inverted={}, idf={}, k1=k1, b=b)

    tokenized: list[list[str]] = [tokenize(d.clean_text) for d in docs]
    doc_lens = [len(toks) for toks in tokenized]
    avg_dl = sum(doc_lens) / max(1, n_docs)

    inverted: dict[str, list[list[int]]] = {}
    df: dict[str, int] = {}

    for doc_idx, toks in enumerate(tokenized):
        tf: dict[str, int] = {}
        for tok in toks:
            tf[tok] = tf.get(tok, 0) + 1
        for term, freq in tf.items():
            inverted.setdefault(term, []).append([doc_idx, freq])
            df[term] = df.get(term, 0) + 1

    idf: dict[str, float] = {}
    for term, term_df in df.items():
        idf[term] = math.log((n_docs - term_df + 0.5) / (term_df + 0.5) + 1.0)

    return BM25Index(
        docs=[BM25Doc(**asdict(d)) for d in docs],
        avg_doc_len=avg_dl,
        doc_lens=doc_lens,
        inverted=inverted,
        idf=idf,
        k1=k1,
        b=b,
    )


def build_bm25_index(
    chunks_path: str | Path = "data/processed/chunks_clean.jsonl",
    output_path: str | Path = "data/indexes/bm25_index.json",
) -> BM25Index:
    docs = load_chunks_clean(chunks_path, filter_watermark=True)
    index = _build_index_from_docs(docs)
    save_bm25_index(index, output_path)
    return index


def save_bm25_index(index: BM25Index, output_path: str | Path) -> None:
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "docs": [asdict(d) for d in index.docs],
        "avg_doc_len": index.avg_doc_len,
        "doc_lens": index.doc_lens,
        "inverted": index.inverted,
        "idf": index.idf,
        "k1": index.k1,
        "b": index.b,
    }
    dst.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_bm25_index(index_path: str | Path = "data/indexes/bm25_index.json") -> BM25Index:
    src = Path(index_path)
    if not src.exists():
        raise FileNotFoundError(f"bm25 index not found: {src}")
    payload = json.loads(src.read_text(encoding="utf-8"))
    return BM25Index(
        docs=[BM25Doc(**d) for d in payload.get("docs", [])],
        avg_doc_len=float(payload.get("avg_doc_len", 0.0)),
        doc_lens=[int(x) for x in payload.get("doc_lens", [])],
        inverted={k: [[int(a), int(b)] for a, b in v] for k, v in payload.get("inverted", {}).items()},
        idf={k: float(v) for k, v in payload.get("idf", {}).items()},
        k1=float(payload.get("k1", 1.5)),
        b=float(payload.get("b", 0.75)),
    )


def search_bm25(index: BM25Index, query: str, top_k: int = 20) -> list[tuple[BM25Doc, float]]:
    q_terms = tokenize(query)
    if not q_terms or not index.docs:
        return []

    scores: dict[int, float] = {}
    for term in q_terms:
        postings = index.inverted.get(term)
        if not postings:
            continue
        idf = index.idf.get(term, 0.0)
        for doc_idx, tf in postings:
            dl = index.doc_lens[doc_idx]
            denom = tf + index.k1 * (1 - index.b + index.b * dl / max(1e-9, index.avg_doc_len))
            gain = idf * ((tf * (index.k1 + 1)) / max(1e-9, denom))
            scores[doc_idx] = scores.get(doc_idx, 0.0) + gain

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [(index.docs[i], s) for i, s in ranked]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build BM25 index from chunks_clean.jsonl")
    parser.add_argument("--input", default="data/processed/chunks_clean.jsonl", help="Input chunks_clean.jsonl path")
    parser.add_argument("--out", default="data/indexes/bm25_index.json", help="Output BM25 index path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    index = build_bm25_index(args.input, args.out)
    print(f"BM25 index built: {len(index.docs)} docs")
    print(f"Output: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
