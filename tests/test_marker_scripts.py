from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class MarkerScriptsTests(unittest.TestCase):
    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        existing = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = "." if not existing else f".:{existing}"
        return subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_validate_marker_gray_release_passes_with_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "cfg.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "marker_enabled: true",
                        "marker_timeout_sec: 30",
                        "title_confidence_threshold: 0.6",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            proc = self._run(["scripts/validate_marker_gray_release.py", "--config", str(config_path)])
            self.assertEqual(proc.returncode, 0)
            self.assertIn("MARKER_GRAY_RELEASE: PASS", proc.stdout)

    def test_validate_marker_gray_release_fails_with_invalid_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "cfg.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "marker_enabled: true",
                        "marker_timeout_sec: 30",
                        "title_confidence_threshold: 1.6",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            proc = self._run(["scripts/validate_marker_gray_release.py", "--config", str(config_path)])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("MARKER_GRAY_RELEASE: FAIL", proc.stdout)

    def test_rebuild_paper_metadata_dry_run_outputs_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            papers_path = base / "papers.json"
            chunks_path = base / "chunks.jsonl"
            papers_path.write_text(
                json.dumps(
                    [
                        {
                            "paper_id": "pdf_abc",
                            "title": "Preprint. Under review.",
                            "path": "/tmp/a.pdf",
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            chunks_path.write_text(
                json.dumps(
                    {
                        "chunk_id": "pdf_abc:00001",
                        "paper_id": "pdf_abc",
                        "page_start": 1,
                        "text": "Real Title\nbody",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            before = papers_path.read_text(encoding="utf-8")
            proc = self._run(
                [
                    "scripts/rebuild_paper_metadata.py",
                    "--papers",
                    str(papers_path),
                    "--chunks",
                    str(chunks_path),
                    "--paper-id",
                    "pdf_abc",
                    "--dry-run",
                ]
            )
            self.assertEqual(proc.returncode, 0)
            payload = json.loads(proc.stdout.strip())
            self.assertEqual(payload.get("target_count"), 1)
            self.assertEqual(payload.get("updated"), 1)
            self.assertTrue(payload.get("dry_run"))
            self.assertEqual(before, papers_path.read_text(encoding="utf-8"))

    def test_gray_batch_script_contains_rollback_and_validation_steps(self) -> None:
        script = Path("scripts/run_marker_gray_batch.sh").read_text(encoding="utf-8")
        self.assertIn("validate_marker_gray_release.py --config", script)
        self.assertIn("rollback by setting marker_enabled=false", script)


if __name__ == "__main__":
    unittest.main()
