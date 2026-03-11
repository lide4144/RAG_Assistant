from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index
from app.qa import _extract_key_claims, run_qa


class SectionStructureRegressionTests(unittest.TestCase):
    def _write_config(self, path: Path) -> None:
        path.write_text(
            "dense_backend: tfidf\n"
            "assistant_mode_enabled: false\n"
            "answer_use_llm: false\n"
            "evidence_policy_enforced: true\n"
            "session_store_backend: file\n"
            "embedding:\n"
            "  enabled: false\n"
            "rerank:\n"
            "  enabled: false\n",
            encoding="utf-8",
        )

    def _write_papers(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                [
                    {"paper_id": "p1", "title": "Structured Paper", "path": "data/papers/p1.pdf"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_chunks(self, path: Path) -> None:
        rows = [
            {
                "chunk_id": "c:1",
                "paper_id": "p1",
                "page_start": 1,
                "text": "Introduction describes the paper structure and motivation.",
                "clean_text": "introduction describes paper structure motivation",
                "content_type": "body",
                "quality_flags": [],
                "section": "Introduction",
                "section_id": "p1:sec:0001",
                "heading_path": ["Introduction"],
            },
            {
                "chunk_id": "c:2",
                "paper_id": "p1",
                "page_start": 2,
                "text": "Section 3 Results reports that the method improves retrieval accuracy.",
                "clean_text": "section 3 results reports method improves retrieval accuracy",
                "content_type": "body",
                "quality_flags": [],
                "section": "Section 3 Results",
                "section_id": "p1:sec:0002",
                "heading_path": ["Section 3 Results"],
            },
        ]
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_structure_index(self, path: Path, *, status: str) -> None:
        payload = {
            "papers": [
                {
                    "paper_id": "p1",
                    "parser_engine": "marker",
                    "structure_parse_status": status,
                    "structure_parse_reason": "" if status == "ready" else "marker_blocks_empty",
                    "section_count": 2,
                    "indexed_section_count": (2 if status == "ready" else 0),
                    "sections": (
                        [
                            {
                                "section_id": "p1:sec:0001",
                                "paper_id": "p1",
                                "section_title": "Introduction",
                                "section_level": 1,
                                "heading_path": ["Introduction"],
                                "start_page": 1,
                                "end_page": 1,
                                "parent_section_id": None,
                                "child_chunk_ids": ["c:1"],
                            },
                            {
                                "section_id": "p1:sec:0002",
                                "paper_id": "p1",
                                "section_title": "Section 3 Results",
                                "section_level": 1,
                                "heading_path": ["Section 3 Results"],
                                "start_page": 2,
                                "end_page": 2,
                                "parent_section_id": None,
                                "child_chunk_ids": ["c:2"],
                            },
                        ]
                        if status == "ready"
                        else []
                    ),
                }
            ]
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _run_once(self, *, base: Path, query: str) -> dict:
        chunks = base / "chunks_clean.jsonl"
        bm25 = base / "bm25.json"
        vec = base / "vec.json"
        cfg = base / "cfg.yaml"
        store = base / "session_store.json"
        global_runs = Path("runs")
        before = {p.name for p in global_runs.iterdir() if p.is_dir()} if global_runs.exists() else set()
        args = Namespace(
            q=query,
            mode="hybrid",
            chunks=str(chunks),
            bm25_index=str(bm25),
            vec_index=str(vec),
            embed_index=str(base / "embed.json"),
            config=str(cfg),
            top_k=6,
            top_evidence=5,
            session_id="s-section",
            session_store=str(store),
            clear_session=False,
            topic_paper_ids="",
            topic_name="",
        )
        code = run_qa(args)
        self.assertEqual(code, 0)
        after_dirs = [p for p in global_runs.iterdir() if p.is_dir()] if global_runs.exists() else []
        created = [p for p in after_dirs if p.name not in before]
        self.assertTrue(created)
        latest = max(created, key=lambda p: p.stat().st_mtime)
        return json.loads((latest / "qa_report.json").read_text(encoding="utf-8"))

    def test_section_route_used_when_structure_index_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._write_chunks(base / "chunks_clean.jsonl")
            self._write_papers(base / "papers.json")
            self._write_config(base / "cfg.yaml")
            self._write_structure_index(base / "structure_index.json", status="ready")
            build_bm25_index(base / "chunks_clean.jsonl", base / "bm25.json")
            build_vec_index(base / "chunks_clean.jsonl", base / "vec.json")

            report = self._run_once(base=base, query="What does section 3 results say?")
            self.assertEqual(report.get("retrieval_route"), "section")
            self.assertTrue(report.get("section_route_used"))
            self.assertGreater(int(report.get("section_candidates_count") or 0), 0)
            evidence = report.get("evidence_grouped", [])[0]["evidence"][0]
            self.assertEqual(evidence.get("section_id"), "p1:sec:0002")

    def test_structure_route_falls_back_when_section_retrieval_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._write_chunks(base / "chunks_clean.jsonl")
            self._write_papers(base / "papers.json")
            self._write_config(base / "cfg.yaml")
            self._write_structure_index(base / "structure_index.json", status="ready")
            payload = json.loads((base / "structure_index.json").read_text(encoding="utf-8"))
            payload["papers"][0]["sections"] = []
            (base / "structure_index.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            build_bm25_index(base / "chunks_clean.jsonl", base / "bm25.json")
            build_vec_index(base / "chunks_clean.jsonl", base / "vec.json")

            report = self._run_once(base=base, query="How many chapters are in the paper?")
            self.assertEqual(report.get("retrieval_route"), "chunk")
            self.assertEqual(report.get("structure_route_fallback"), "section_retrieval_empty")
            self.assertFalse(report.get("section_route_used"))

    def test_structure_route_falls_back_when_structure_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._write_chunks(base / "chunks_clean.jsonl")
            self._write_papers(base / "papers.json")
            self._write_config(base / "cfg.yaml")
            self._write_structure_index(base / "structure_index.json", status="degraded")
            build_bm25_index(base / "chunks_clean.jsonl", base / "bm25.json")
            build_vec_index(base / "chunks_clean.jsonl", base / "vec.json")

            report = self._run_once(base=base, query="What does section 3 results say?")
            self.assertEqual(report.get("retrieval_route"), "chunk")
            self.assertEqual(report.get("structure_route_fallback"), "structure_unavailable")
            self.assertEqual(report.get("structure_parse_status"), "degraded")

    def test_partial_section_coverage_is_explicitly_disclosed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._write_chunks(base / "chunks_clean.jsonl")
            self._write_papers(base / "papers.json")
            self._write_config(base / "cfg.yaml")
            self._write_structure_index(base / "structure_index.json", status="ready")
            build_bm25_index(base / "chunks_clean.jsonl", base / "bm25.json")
            build_vec_index(base / "chunks_clean.jsonl", base / "vec.json")

            report = self._run_once(base=base, query="What does section 3 results say?")
            self.assertEqual(report.get("retrieval_route"), "section")
            self.assertTrue(report.get("structure_coverage_limited"))
            self.assertEqual(report.get("structure_coverage_notice"), "当前仅基于局部章节证据。")
            self.assertIn("当前仅基于局部章节证据。", report.get("answer", ""))

    def test_format_only_numbers_do_not_become_claims(self) -> None:
        claims = _extract_key_claims("1. Overview only. 第 3 章介绍实验设置，详见 p.8。")
        self.assertEqual(claims, [])


if __name__ == "__main__":
    unittest.main()
