from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from app.generate import format_evidence
from app.index_bm25 import build_bm25_index
from app.index_vec import build_vec_index
from app.qa import is_summary_shell, resolve_scope_policy, run_qa, summary_shell_ratio
from app.retrieve import load_indexes_and_config, retrieve_candidates


class M2RetrievalQATests(unittest.TestCase):
    def _write_test_config(self, path: Path) -> None:
        path.write_text(
            "dense_backend: tfidf\n"
            "rerank:\n"
            "  enabled: true\n"
            "  provider: mock\n"
            "  top_n: 8\n"
            "embedding:\n"
            "  enabled: false\n",
            encoding="utf-8",
        )

    def _write_chunks_clean(self, path: Path) -> None:
        rows = [
            {
                "chunk_id": "c:00001",
                "paper_id": "p1",
                "page_start": 1,
                "text": "RAW ORIGINAL TOKEN about gameplay loop and experiment settings for reproducibility.",
                "clean_text": "normalized gameplay loop experiment settings",
                "content_type": "body",
                "quality_flags": [],
                "section": "Intro",
            },
            {
                "chunk_id": "c:00002",
                "paper_id": "p1",
                "page_start": 1,
                "text": "table row python pygame",
                "clean_text": "python pygame",
                "content_type": "table_list",
                "quality_flags": ["short_fragment_merged"],
                "section": None,
            },
            {
                "chunk_id": "c:00003",
                "paper_id": "p1",
                "page_start": 2,
                "text": "body python pygame detailed with benchmark and coding setup details for replication.",
                "clean_text": "python pygame detailed benchmark coding setup",
                "content_type": "body",
                "quality_flags": [],
                "section": None,
            },
            {
                "chunk_id": "c:00004",
                "paper_id": "p1",
                "page_start": 3,
                "text": "Downloaded on 2026 IEEE Xplore",
                "clean_text": "downloaded on ieee xplore",
                "content_type": "watermark",
                "quality_flags": [],
                "section": None,
            },
            {
                "chunk_id": "c:00005",
                "paper_id": "p2",
                "page_start": 1,
                "text": "Author: Alice, email: alice@example.edu, University of Games and Interactive AI Lab, contactblock.",
                "clean_text": "author alice email alice example edu university games interactive ai lab contactblock",
                "content_type": "front_matter",
                "quality_flags": ["has_email"],
                "section": "Header",
            },
            {
                "chunk_id": "c:00006",
                "paper_id": "p2",
                "page_start": 8,
                "text": "Reference list includes validated scale and questionnaire citations for evaluation, bibblock.",
                "clean_text": "reference validated scale questionnaire citations evaluation bibblock",
                "content_type": "reference",
                "quality_flags": [],
                "section": "References",
            },
        ]
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_papers(self, path: Path) -> None:
        rows = [
            {"paper_id": "p1", "title": "Paper One", "path": "data/papers/p1.pdf"},
            {"paper_id": "p2", "title": "Paper Two", "path": "data/papers/p2.pdf"},
        ]
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def test_retrieval_modes_filter_and_downweight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_test_config(cfg)

            bm25 = build_bm25_index(chunks, bm25_idx)
            vec = build_vec_index(chunks, vec_idx)

            # watermark should not be indexed
            self.assertNotIn("c:00004", {d.chunk_id for d in bm25.docs})
            self.assertNotIn("c:00004", {d.chunk_id for d in vec.docs})

            bm25_loaded, vec_loaded, config, warnings = load_indexes_and_config(
                bm25_index_path=str(bm25_idx),
                vec_index_path=str(vec_idx),
                config_path=str(cfg),
            )
            self.assertEqual(warnings, [])

            for mode in ("bm25", "dense", "hybrid"):
                results = retrieve_candidates(
                    "python pygame",
                    mode=mode,
                    top_k=6,
                    bm25_index=bm25_loaded,
                    vec_index=vec_loaded,
                    config=config,
                )
                self.assertGreaterEqual(len(results), 1)

            hybrid = retrieve_candidates(
                "python pygame",
                mode="hybrid",
                top_k=6,
                bm25_index=bm25_loaded,
                vec_index=vec_loaded,
                config=config,
            )
            scores = {r.chunk_id: r.score for r in hybrid}
            self.assertIn("c:00002", scores)  # table_list kept
            self.assertGreater(scores["c:00002"], 0.0)
            self.assertLessEqual(scores["c:00002"], config.table_list_downweight)
            for row in hybrid:
                self.assertEqual((row.payload or {}).get("dense_backend"), "tfidf")
                self.assertEqual((row.payload or {}).get("retrieval_mode"), "hybrid")
                self.assertIn((row.payload or {}).get("source"), {"bm25", "dense", "hybrid"})

    def test_front_matter_and_reference_conditional_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_test_config(cfg)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)

            bm25_loaded, vec_loaded, config, _ = load_indexes_and_config(
                bm25_index_path=str(bm25_idx),
                vec_index_path=str(vec_idx),
                config_path=str(cfg),
            )

            generic = retrieve_candidates(
                "contactblock bibblock",
                mode="hybrid",
                top_k=6,
                bm25_index=bm25_loaded,
                vec_index=vec_loaded,
                config=config,
            )
            author_query = retrieve_candidates(
                "author affiliation email",
                mode="hybrid",
                top_k=6,
                bm25_index=bm25_loaded,
                vec_index=vec_loaded,
                config=config,
            )
            ref_query = retrieve_candidates(
                "reference citation validate questionnaire",
                mode="hybrid",
                top_k=6,
                bm25_index=bm25_loaded,
                vec_index=vec_loaded,
                config=config,
            )

            g = {c.chunk_id: c.score for c in generic}
            a = {c.chunk_id: c.score for c in author_query}
            r = {c.chunk_id: c.score for c in ref_query}

            self.assertIn("c:00005", g)
            self.assertIn("c:00005", a)
            self.assertIn("c:00006", g)
            self.assertIn("c:00006", r)
            self.assertGreater(a["c:00005"], g["c:00005"])
            self.assertGreater(r["c:00006"], g["c:00006"])

    def test_scope_policy_rewrite_and_clarify(self) -> None:
        mode, query_used, reason = resolve_scope_policy("What does this paper propose?")
        self.assertEqual(mode, "rewrite_scope")
        self.assertEqual(query_used, "What does this paper propose?")
        self.assertIn("rule", reason)

        mode, query_used, reason = resolve_scope_policy("What is the corresponding author email in this paper?")
        self.assertEqual(mode, "clarify_scope")
        self.assertEqual(query_used, "What is the corresponding author email in this paper?")
        self.assertIn("author", reason.get("matched_clarify_terms", []))

        mode, query_used, reason = resolve_scope_policy('In paper "A Survey on X", what is proposed?')
        self.assertEqual(mode, "open")
        self.assertIn("A Survey on X", query_used)
        self.assertTrue(reason.get("has_paper_clue"))

    def test_quote_is_taken_from_original_text_not_clean_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_test_config(cfg)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)

            bm25_loaded, vec_loaded, config, _ = load_indexes_and_config(
                bm25_index_path=str(bm25_idx),
                vec_index_path=str(vec_idx),
                config_path=str(cfg),
            )
            results = retrieve_candidates(
                "normalized gameplay",
                mode="hybrid",
                top_k=6,
                bm25_index=bm25_loaded,
                vec_index=vec_loaded,
                config=config,
            )
            evidence = format_evidence(results, top_n=1)
            self.assertTrue(evidence)
            self.assertIn("RAW ORIGINAL TOKEN", evidence[0]["quote"])

    def test_run_qa_cli_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            papers = base / "papers.json"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_papers(papers)
            self._write_test_config(cfg)

            args = Namespace(
                q="What does this paper propose for gameplay agents?",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=6,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            code = run_qa(args)
            self.assertEqual(code, 0)
            self.assertTrue(bm25_idx.exists())
            self.assertTrue(vec_idx.exists())

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            self.assertTrue(run_dirs)
            latest = run_dirs[-1]
            report = json.loads((latest / "qa_report.json").read_text(encoding="utf-8"))
            self.assertIn(report.get("scope_mode"), {"rewrite_scope", "open", "clarify_scope"})
            self.assertIn("query_used", report)
            self.assertIn("calibrated_query", report)
            self.assertIn("calibration_reason", report)
            self.assertIn("query_retry_used", report)
            self.assertIn("query_retry_reason", report)
            self.assertIn("rewrite_rule_query", report)
            self.assertIn("rewrite_llm_query", report)
            self.assertIsInstance(report.get("scope_reason"), dict)
            self.assertIsInstance(report.get("keywords_entities"), dict)
            self.assertIsInstance(report.get("strategy_hits"), list)
            self.assertIsInstance(report.get("papers_ranked"), list)
            self.assertIsInstance(report.get("evidence_grouped"), list)
            self.assertIsInstance(report.get("answer_citations"), list)
            self.assertIsInstance(report.get("output_warnings"), list)
            for group in report.get("evidence_grouped", []):
                for item in group.get("evidence", []):
                    quote = item.get("quote", "")
                    self.assertGreaterEqual(len(quote), 1)
                    self.assertLessEqual(len(quote), 120)
            citation_ids = {c["chunk_id"] for c in report.get("answer_citations", [])}
            evidence_ids = {
                item["chunk_id"]
                for group in report.get("evidence_grouped", [])
                for item in group.get("evidence", [])
            }
            self.assertTrue(citation_ids.issubset(evidence_ids))

    def test_summary_shell_ratio(self) -> None:
        rows = [
            {"chunk_id": "a", "score": 1.0, "text": "In summary, this work ..."},
            {"chunk_id": "b", "score": 0.9, "text": "Reporting summary details"},
            {"chunk_id": "c", "score": 0.8, "text": "SUMMARY OF contributions"},
            {"chunk_id": "d", "score": 0.7, "text": "body evidence chunk"},
            {"chunk_id": "e", "score": 0.6, "text": "body evidence chunk 2"},
        ]
        from app.retrieve import RetrievalCandidate

        cands = [RetrievalCandidate(chunk_id=r["chunk_id"], score=r["score"], text=r["text"]) for r in rows]
        ratio = summary_shell_ratio(cands, top_n=5)
        self.assertGreater(ratio, 0.5)

    def test_summary_shell_additional_patterns(self) -> None:
        self.assertTrue(is_summary_shell("This paper: • introduces a new architecture"))
        self.assertTrue(is_summary_shell("In this survey paper, we compare methods."))

    def test_retry_triggered_once_when_shell_ratio_high(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_test_config(cfg)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)

            args = Namespace(
                q="What are the limitations of this work?",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            first = [
                RetrievalCandidate(chunk_id=f"s:{i}", score=1.0 - i * 0.01, text="In summary, shell text", clean_text="summary shell")
                for i in range(5)
            ]
            second = [
                RetrievalCandidate(
                    chunk_id="b:1",
                    score=0.9,
                    text="This section discusses limitations and future work in detail with concrete threats to validity and weaknesses.",
                    clean_text="limitations future work threats validity weaknesses",
                    paper_id="p1",
                    page_start=2,
                )
            ]

            with patch("app.qa.retrieve_candidates", side_effect=[first, second]) as mocked:
                code = run_qa(args)
                self.assertEqual(code, 0)
                self.assertEqual(mocked.call_count, 2)

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            latest = run_dirs[-1]
            report = json.loads((latest / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("query_retry_used"))
            self.assertIsNotNone(report.get("query_retry_reason"))

    def test_top_ranked_papers_have_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            papers = base / "papers.json"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_papers(papers)
            self._write_test_config(cfg)

            args = Namespace(
                q="this work 的主要贡献是什么",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=6,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            code = run_qa(args)
            self.assertEqual(code, 0)

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            top_papers = [row["paper_id"] for row in report.get("papers_ranked", [])[:5]]
            evidence_papers = {group["paper_id"] for group in report.get("evidence_grouped", []) if group.get("evidence")}
            for pid in top_papers:
                self.assertIn(pid, evidence_papers)

    def test_rewrite_scope_answer_is_aggregated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            papers = base / "papers.json"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_papers(papers)
            self._write_test_config(cfg)

            args = Namespace(
                q="this work 有哪些局限？",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=6,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(
                    chunk_id="p1:001",
                    score=0.9,
                    text="This section explains limitations and future work with sufficient details for reliable synthesis.",
                    clean_text="limitations future work reliable synthesis",
                    paper_id="p1",
                    page_start=2,
                ),
                RetrievalCandidate(
                    chunk_id="p2:001",
                    score=0.8,
                    text="The paper reports contribution and methodological novelty with explicit comparative evidence.",
                    clean_text="contribution novelty comparative evidence",
                    paper_id="p2",
                    page_start=3,
                ),
            ]
            with patch("app.qa.retrieve_candidates", return_value=cands):
                code = run_qa(args)
            self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            if report.get("scope_mode") == "rewrite_scope":
                self.assertIn("综合证据", report.get("answer", ""))
                self.assertNotIn("最相关内容见", report.get("answer", ""))

    def test_insufficient_evidence_adds_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_test_config(cfg)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)

            args = Namespace(
                q="this work 的方法是什么",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            only_one = [
                RetrievalCandidate(
                    chunk_id="p1:1",
                    score=0.9,
                    text="single short evidence",
                    clean_text="single short evidence",
                    paper_id="p1",
                    page_start=1,
                )
            ]
            with patch("app.qa.retrieve_candidates", return_value=only_one):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertIn("insufficient_evidence_for_answer", report.get("output_warnings", []))

    def test_open_mode_with_paper_clue_keeps_single_paper_citations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            papers = base / "papers.json"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_papers(papers)
            self._write_test_config(cfg)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q='In paper "Paper One", what is proposed?',
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=6,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            code = run_qa(args)
            self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            if report.get("scope_mode") == "open":
                pids = {c["paper_id"] for c in report.get("answer_citations", [])}
                self.assertLessEqual(len(pids), 1)

    def test_summary_shell_still_dominant_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_test_config(cfg)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="What are the limitations of this work?",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            first = [
                RetrievalCandidate(chunk_id=f"s1:{i}", score=1.0 - i * 0.01, text="In summary, shell text", clean_text="summary shell")
                for i in range(5)
            ]
            second = [
                RetrievalCandidate(chunk_id=f"s2:{i}", score=0.9 - i * 0.01, text="Reporting summary shell text", clean_text="summary shell")
                for i in range(5)
            ]
            with patch("app.qa.retrieve_candidates", side_effect=[first, second]):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertIn("summary_shell_still_dominant", report.get("output_warnings", []))

    def test_qa_merges_graph_expansion_and_keeps_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            papers = base / "papers.json"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            graph_path = base / "graph.json"
            cfg_path = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_papers(papers)

            from app.graph_build import ChunkGraph, GraphBuildStats, GraphNode, save_graph

            graph = ChunkGraph(
                nodes={
                    "c:00001": GraphNode("c:00001", "p1", 1, "Intro", "body", []),
                    "c:00003": GraphNode("c:00003", "p1", 2, None, "body", []),
                },
                adjacent={"c:00001": ["c:00003"], "c:00003": ["c:00001"]},
                entity={"c:00001": [], "c:00003": []},
                stats=GraphBuildStats(),
                config={},
            )
            save_graph(graph, graph_path)
            cfg_path.write_text(
                "dense_backend: tfidf\n"
                "embedding:\n"
                "  enabled: false\n"
                "graph_path: \"" + str(graph_path) + "\"\n"
                "graph_expand_alpha: 2.0\n"
                "graph_expand_max_candidates: 200\n",
                encoding="utf-8",
            )

            args = Namespace(
                q='In paper "Paper One", what is proposed?',
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg_path),
                top_k=1,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            seed = [
                RetrievalCandidate(
                    chunk_id="c:00001",
                    score=1.0,
                    text="RAW ORIGINAL TOKEN about gameplay loop and experiment settings for reproducibility.",
                    clean_text="normalized gameplay loop experiment settings",
                    content_type="body",
                    paper_id="p1",
                    page_start=1,
                    section="Intro",
                )
            ]
            with patch("app.qa.retrieve_candidates", return_value=seed):
                code = run_qa(args)
                self.assertEqual(code, 0)

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            ids = [row["chunk_id"] for row in trace.get("retrieval_top_k", [])]
            self.assertIn("c:00001", ids)
            self.assertIn("c:00003", ids)
            self.assertGreaterEqual(report.get("graph_expansion_stats", {}).get("added", 0), 1)
            self.assertEqual(report.get("dense_backend"), "tfidf")
            self.assertIn("graph_expand_alpha", report)
            self.assertIn("expansion_budget", report)
            self.assertEqual(trace.get("dense_backend"), "tfidf")
            self.assertIn("graph_expand_alpha", trace)
            self.assertIn("expansion_budget", trace)
            expanded = [row for row in trace.get("expansion_added_chunks", []) if row.get("chunk_id") == "c:00003"]
            self.assertTrue(expanded)
            self.assertEqual(expanded[0].get("dense_backend"), "tfidf")
            self.assertEqual(expanded[0].get("retrieval_mode"), "hybrid")

    def test_qa_expansion_added_chunks_carries_embedding_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            papers = base / "papers.json"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            graph_path = base / "graph.json"
            cfg_path = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_papers(papers)

            from app.graph_build import ChunkGraph, GraphBuildStats, GraphNode, save_graph

            graph = ChunkGraph(
                nodes={
                    "c:00001": GraphNode("c:00001", "p1", 1, "Intro", "body", []),
                    "c:00003": GraphNode("c:00003", "p1", 2, None, "body", []),
                },
                adjacent={"c:00001": ["c:00003"], "c:00003": ["c:00001"]},
                entity={"c:00001": [], "c:00003": []},
                stats=GraphBuildStats(),
                config={},
            )
            save_graph(graph, graph_path)
            cfg_path.write_text(
                "dense_backend: embedding\n"
                "embedding:\n"
                "  enabled: false\n"
                "  provider: siliconflow\n"
                "  model: fake-embed-model\n"
                "graph_path: \"" + str(graph_path) + "\"\n"
                "graph_expand_alpha: 2.0\n"
                "graph_expand_max_candidates: 200\n",
                encoding="utf-8",
            )

            args = Namespace(
                q='In paper "Paper One", what is proposed?',
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg_path),
                top_k=1,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            seed = [
                RetrievalCandidate(
                    chunk_id="c:00001",
                    score=1.0,
                    text="RAW ORIGINAL TOKEN about gameplay loop and experiment settings for reproducibility.",
                    clean_text="normalized gameplay loop experiment settings",
                    content_type="body",
                    paper_id="p1",
                    page_start=1,
                    section="Intro",
                    payload={
                        "source": "hybrid",
                        "dense_backend": "embedding",
                        "retrieval_mode": "hybrid",
                        "embedding_provider": "siliconflow",
                        "embedding_model": "fake-embed-model",
                        "embedding_version": "v-test",
                    },
                )
            ]
            with patch("app.qa.retrieve_candidates", return_value=seed):
                code = run_qa(args)
                self.assertEqual(code, 0)

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            expanded = [row for row in trace.get("expansion_added_chunks", []) if row.get("chunk_id") == "c:00003"]
            self.assertTrue(expanded)
            self.assertEqual(expanded[0].get("dense_backend"), "embedding")
            self.assertEqual(expanded[0].get("retrieval_mode"), "hybrid")
            self.assertEqual(expanded[0].get("embedding_provider"), "siliconflow")
            self.assertEqual(expanded[0].get("embedding_model"), "fake-embed-model")
            self.assertEqual(expanded[0].get("embedding_version"), "v-test")

    def test_run_trace_includes_embedding_batch_failure_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            self._write_test_config(cfg)
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)

            args = Namespace(
                q="What does this paper propose?",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=3,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            fake_metrics = {
                "embedding_build_time_ms": 123,
                "embedding_failed_count": 0,
                "embedding_failed_chunk_ids": [],
                "embedding_batch_failures": [
                    {
                        "batch_index": 1,
                        "batch_total": 2,
                        "count": 32,
                        "status_code": 429,
                        "trace_id": "trace-x",
                        "response_body": "rate limited",
                        "error_category": "rate_limit",
                    }
                ],
                "rate_limited_count": 1,
                "backoff_total_ms": 500,
                "truncated_count": 0,
                "skipped_over_limit_count": 0,
                "skipped_empty": 0,
                "skipped_empty_chunk_ids": [],
            }
            seed = [
                RetrievalCandidate(
                    chunk_id="c:00001",
                    score=1.0,
                    text="RAW ORIGINAL TOKEN about gameplay loop and experiment settings for reproducibility.",
                    clean_text="normalized gameplay loop experiment settings",
                    content_type="body",
                    paper_id="p1",
                    page_start=1,
                    section="Intro",
                )
            ]
            with patch("app.qa.ensure_indexes", return_value=fake_metrics), patch(
                "app.qa.retrieve_candidates", return_value=seed
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)

            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            trace = json.loads((run_dirs[-1] / "run_trace.json").read_text(encoding="utf-8"))
            failures = trace.get("embedding_batch_failures", [])
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["trace_id"], "trace-x")
            self.assertEqual(failures[0]["response_body"], "rate limited")

    def test_llm_answer_uses_evidence_when_sufficient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "rewrite_use_llm: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(
                    chunk_id="p1:1",
                    score=0.9,
                    text="Method A improves accuracy to 92.1 with benchmark evidence.",
                    clean_text="method improves accuracy 92.1 benchmark evidence",
                    paper_id="p1",
                    page_start=1,
                ),
                RetrievalCandidate(
                    chunk_id="p1:2",
                    score=0.8,
                    text="The method design explains benchmark setup and result interpretation.",
                    clean_text="method design benchmark setup result interpretation",
                    paper_id="p1",
                    page_start=2,
                ),
            ]
            llm_payload = json.dumps(
                {
                    "answer": "Evidence shows Method A reaches 92.1 accuracy.",
                    "answer_citations": [{"chunk_id": "p1:1", "paper_id": "p1", "section_page": "p.1"}],
                },
                ensure_ascii=False,
            )
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion",
                    return_value=type("R", (), {"ok": True, "content": llm_payload, "reason": None})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("answer_llm_used"))
            self.assertFalse(report.get("answer_llm_fallback"))
            self.assertIn("Evidence Policy Gate", report.get("answer", ""))
            self.assertIn("claim_binding_insufficient", report.get("output_warnings", []))

    def test_llm_answer_timeout_falls_back_to_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion",
                    return_value=type("R", (), {"ok": False, "content": None, "reason": "timeout"})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_timeout_fallback_to_template", report.get("output_warnings", []))
            diag = report.get("answer_llm_diagnostics")
            self.assertIsInstance(diag, dict)
            self.assertEqual(diag.get("stage"), "answer")
            self.assertEqual(diag.get("reason"), "timeout")
            self.assertEqual(diag.get("fallback_warning"), "llm_answer_timeout_fallback_to_template")
            for forbidden in ("api_key", "prompt", "system_prompt", "user_prompt", "response_body"):
                self.assertNotIn(forbidden, diag)

    def test_llm_answer_rate_limit_falls_back_to_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion",
                    return_value=type("R", (), {"ok": False, "content": None, "reason": "rate_limit"})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_rate_limit_fallback_to_template", report.get("output_warnings", []))

    def test_llm_answer_empty_response_falls_back_to_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion",
                    return_value=type("R", (), {"ok": False, "content": None, "reason": "empty_response"})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_empty_response_fallback_to_template", report.get("output_warnings", []))

    def test_llm_answer_invalid_json_falls_back_to_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion",
                    return_value=type("R", (), {"ok": True, "content": "{invalid json", "reason": None})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_invalid_json_fallback_to_template", report.get("output_warnings", []))

    def test_llm_answer_stream_success_records_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "answer_stream_enabled: true\n"
                "answer_llm_timeout_ms: 21000\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            llm_payload = json.dumps(
                {
                    "answer": "Method A is supported by streamed evidence.",
                    "answer_citations": [{"chunk_id": "p1:1", "paper_id": "p1", "section_page": "p.1"}],
                },
                ensure_ascii=False,
            )
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch("app.qa.call_chat_completion") as mocked_sync,
                patch(
                    "app.qa.call_chat_completion_stream",
                    autospec=True,
                    return_value=type(
                        "R",
                        (),
                        {
                            "ok": True,
                            "content": llm_payload,
                            "reason": None,
                            "first_token_latency_ms": 88,
                            "stream_events": [
                                {"event_index": 0, "t_ms": 32, "delta_chars": 20, "cumulative_chars": 20},
                                {"event_index": 1, "t_ms": 45, "delta_chars": 18, "cumulative_chars": 38},
                            ],
                        },
                    )(),
                ) as mocked_stream,
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
                mocked_sync.assert_not_called()
                self.assertEqual(mocked_stream.call_args.kwargs.get("timeout_ms"), 21000)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("answer_llm_used"))
            self.assertFalse(report.get("answer_llm_fallback"))
            self.assertTrue(report.get("answer_stream_enabled"))
            self.assertTrue(report.get("answer_stream_used"))
            self.assertEqual(report.get("answer_stream_first_token_ms"), 88)
            self.assertIsNone(report.get("answer_stream_fallback_reason"))
            self.assertIsInstance(report.get("answer_stream_events"), list)
            self.assertEqual(len(report.get("answer_stream_events")), 2)
            self.assertEqual(report["answer_stream_events"][0]["event_index"], 0)
            self.assertEqual(report["answer_stream_events"][1]["cumulative_chars"], 38)

    def test_llm_answer_non_stream_uses_answer_timeout_ms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "answer_stream_enabled: false\n"
                "llm_timeout_ms: 12000\n"
                "answer_llm_timeout_ms: 23000\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            llm_payload = json.dumps(
                {
                    "answer": "Method A is supported by evidence.",
                    "answer_citations": [{"chunk_id": "p1:1", "paper_id": "p1", "section_page": "p.1"}],
                },
                ensure_ascii=False,
            )
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion",
                    autospec=True,
                    return_value=type("R", (), {"ok": True, "content": llm_payload, "reason": None})(),
                ) as mocked_sync,
                patch("app.qa.call_chat_completion_stream") as mocked_stream,
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
                mocked_stream.assert_not_called()
                self.assertEqual(mocked_sync.call_args.kwargs.get("timeout_ms"), 23000)

    def test_llm_answer_stream_cli_prints_incremental_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "answer_stream_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]

            def _stream_call(**kwargs):
                on_delta = kwargs.get("on_delta")
                if callable(on_delta):
                    on_delta('{"answer":"Method A')
                    on_delta(' is streamed.","answer_citations":[{"chunk_id":"p1:1","paper_id":"p1","section_page":"p.1"}]}')
                return type(
                    "R",
                    (),
                    {
                        "ok": True,
                        "content": '{"answer":"Method A is streamed.","answer_citations":[{"chunk_id":"p1:1","paper_id":"p1","section_page":"p.1"}]}',
                        "reason": None,
                        "first_token_latency_ms": 10,
                        "stream_events": [{"event_index": 0, "t_ms": 10, "delta_chars": 18, "cumulative_chars": 18}],
                    },
                )()

            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch("app.qa.call_chat_completion_stream", side_effect=_stream_call),
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
                cli_output = stdout.getvalue()
            self.assertIn("Answer (streaming): ", cli_output)
            self.assertIn('Method A is streamed.","answer_citations"', cli_output)
            self.assertIn("Evidence Policy Gate", cli_output)

    def test_llm_answer_stream_first_token_timeout_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "answer_stream_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion_stream",
                    return_value=type("R", (), {"ok": False, "content": None, "reason": "stream_first_token_timeout"})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_first_token_timeout_fallback_to_template", report.get("output_warnings", []))
            self.assertEqual(
                report.get("answer_stream_fallback_reason"),
                "llm_answer_first_token_timeout_fallback_to_template",
            )

    def test_llm_answer_stream_interrupted_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "answer_stream_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion_stream",
                    return_value=type(
                        "R",
                        (),
                        {
                            "ok": False,
                            "content": None,
                            "reason": "stream_interrupted",
                            "first_token_latency_ms": 120,
                        },
                    )(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_stream_interrupted_fallback_to_template", report.get("output_warnings", []))
            self.assertEqual(report.get("answer_stream_first_token_ms"), 120)

    def test_llm_answer_stream_empty_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "answer_stream_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion_stream",
                    return_value=type("R", (), {"ok": False, "content": None, "reason": "stream_empty"})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_stream_empty_response_fallback_to_template", report.get("output_warnings", []))
            self.assertEqual(
                report.get("answer_stream_fallback_reason"),
                "llm_answer_stream_empty_response_fallback_to_template",
            )

    def test_llm_answer_stream_parse_failure_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "answer_stream_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion_stream",
                    return_value=type("R", (), {"ok": True, "content": "{invalid json", "reason": None})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_invalid_json_fallback_to_template", report.get("output_warnings", []))
            self.assertEqual(
                report.get("answer_stream_fallback_reason"),
                "llm_answer_invalid_json_fallback_to_template",
            )

    def test_llm_answer_stream_cli_interrupted_still_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "answer_stream_enabled: true\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]

            def _stream_call(**kwargs):
                on_delta = kwargs.get("on_delta")
                if callable(on_delta):
                    on_delta("partial-stream ")
                return type(
                    "R",
                    (),
                    {
                        "ok": False,
                        "content": None,
                        "reason": "stream_interrupted",
                        "first_token_latency_ms": 20,
                        "stream_events": [{"event_index": 0, "t_ms": 20, "delta_chars": 15, "cumulative_chars": 15}],
                    },
                )()

            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch("app.qa.call_chat_completion_stream", side_effect=_stream_call),
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
                cli_output = stdout.getvalue()
            self.assertIn("Answer (streaming): partial-stream ", cli_output)
            self.assertIn("Answer: ", cli_output)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertIn("llm_answer_stream_interrupted_fallback_to_template", report.get("output_warnings", []))

    def test_llm_answer_citation_outside_evidence_forces_weak_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            llm_payload = json.dumps(
                {
                    "answer": "Unsupported claim 95.0 accuracy.",
                    "answer_citations": [{"chunk_id": "p9:99", "paper_id": "p9", "section_page": "p.9"}],
                },
                ensure_ascii=False,
            )
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.qa.call_chat_completion",
                    return_value=type("R", (), {"ok": True, "content": llm_payload, "reason": None})(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertIn("Evidence Policy Gate", report.get("answer", ""))
            self.assertEqual(report.get("answer_citations"), [])
            self.assertIn("insufficient_evidence_for_answer", report.get("output_warnings", []))

    def test_llm_fallback_disabled_skips_llm_answer_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "answer_use_llm: true\n"
                "assistant_mode_enabled: false\n"
                "llm_fallback_enabled: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch("app.qa.call_chat_completion") as mocked_llm,
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
                mocked_llm.assert_not_called()
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertFalse(report.get("answer_llm_used"))
            self.assertTrue(report.get("answer_llm_fallback"))
            self.assertEqual(report.get("final_decision"), "answer_with_evidence")
            self.assertIn("llm_fallback_disabled_skip_llm_answer", report.get("output_warnings", []))
            diag = report.get("answer_llm_diagnostics")
            self.assertIsInstance(diag, dict)
            self.assertEqual(diag.get("reason"), "fallback_disabled")

    def test_rewrite_llm_missing_key_records_diagnostics_and_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "rewrite_use_llm: true\n"
                "answer_use_llm: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("rewrite_llm_fallback"))
            self.assertIn("llm_missing_api_key_fallback_to_rules", report.get("output_warnings", []))
            diag = report.get("rewrite_llm_diagnostics")
            self.assertIsInstance(diag, dict)
            self.assertEqual(diag.get("stage"), "rewrite")
            self.assertEqual(diag.get("reason"), "missing_api_key")
            self.assertEqual(diag.get("fallback_warning"), "llm_missing_api_key_fallback_to_rules")
            for forbidden in ("api_key", "prompt", "system_prompt", "user_prompt", "response_body"):
                self.assertNotIn(forbidden, diag)

    def test_rewrite_llm_rate_limit_records_status_code_429(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            chunks = base / "chunks_clean.jsonl"
            bm25_idx = base / "bm25.json"
            vec_idx = base / "vec.json"
            cfg = base / "cfg.yaml"
            self._write_chunks_clean(chunks)
            cfg.write_text(
                "dense_backend: tfidf\n"
                "rewrite_use_llm: true\n"
                "answer_use_llm: false\n"
                "embedding:\n"
                "  enabled: false\n",
                encoding="utf-8",
            )
            build_bm25_index(chunks, bm25_idx)
            build_vec_index(chunks, vec_idx)
            args = Namespace(
                q="what method is proposed",
                mode="hybrid",
                chunks=str(chunks),
                bm25_index=str(bm25_idx),
                vec_index=str(vec_idx),
                config=str(cfg),
                top_k=5,
                top_evidence=5,
                embed_index=str(base / "embed.json"),
            )
            from app.retrieve import RetrievalCandidate

            cands = [
                RetrievalCandidate(chunk_id="p1:1", score=0.9, text="method evidence one", clean_text="method evidence one", paper_id="p1", page_start=1),
                RetrievalCandidate(chunk_id="p1:2", score=0.8, text="method evidence two", clean_text="method evidence two", paper_id="p1", page_start=2),
            ]
            with (
                patch.dict("os.environ", {"SILICONFLOW_API_KEY": "k"}, clear=True),
                patch("app.qa.retrieve_candidates", return_value=cands),
                patch(
                    "app.rewrite.call_chat_completion",
                    return_value=type(
                        "R",
                        (),
                        {"ok": False, "content": None, "reason": "rate_limit", "status_code": 429},
                    )(),
                ),
            ):
                code = run_qa(args)
                self.assertEqual(code, 0)
            run_dirs = sorted(Path("runs").glob("*"), key=lambda p: p.stat().st_mtime)
            report = json.loads((run_dirs[-1] / "qa_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report.get("rewrite_llm_fallback"))
            self.assertIn("llm_rate_limit_fallback_to_rules", report.get("output_warnings", []))
            diag = report.get("rewrite_llm_diagnostics")
            self.assertIsInstance(diag, dict)
            self.assertEqual(diag.get("stage"), "rewrite")
            self.assertEqual(diag.get("reason"), "rate_limit")
            self.assertEqual(diag.get("status_code"), 429)


if __name__ == "__main__":
    unittest.main()
