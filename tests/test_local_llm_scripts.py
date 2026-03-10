from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class LocalLlmScriptsTests(unittest.TestCase):
    def _run_bash(self, cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_bootstrap_script_pulls_embedding_and_rewrite_models_by_default(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        script = repo / "scripts" / "bootstrap_local_llm_ollama.sh"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            pull_log = tmp_path / "pull.log"

            (bin_dir / "curl").write_text(
                "#!/usr/bin/env bash\n"
                "echo '{\"models\":[]}'\n",
                encoding="utf-8",
            )
            (bin_dir / "ollama").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == \"pull\" ]]; then\n"
                f"  echo \"$2\" >> {pull_log}\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"serve\" ]]; then\n"
                "  exit 0\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            os.chmod(bin_dir / "curl", 0o755)
            os.chmod(bin_dir / "ollama", 0o755)

            env = dict(os.environ)
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            proc = self._run_bash(["bash", str(script)], cwd=tmp_path, env=env)

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            pulled = pull_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                pulled,
                [
                    "bge-m3",
                    "qwen2.5:3b",
                ],
            )

    def test_health_check_script_validates_models_and_kernel_health(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        script = repo / "scripts" / "check_local_llm_health.sh"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)

            (bin_dir / "curl").write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "url=\"${@: -1}\"\n"
                "if [[ \"$url\" == *\"/api/tags\" ]]; then\n"
                "  echo '{\"models\":[{\"name\":\"bge-m3\"},{\"name\":\"qwen2.5:3b\"}]}'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$url\" == *\"/health/deps\" ]]; then\n"
                "  echo '{\"answer\":{\"status\":\"ok\"},\"embedding\":{\"status\":\"ok\"},\"rerank\":{\"status\":\"ok\"}}'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$url\" == *\"/api/embed\" ]]; then\n"
                "  echo '{\"embeddings\":[[0.1,0.2,0.3]]}'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"$url\" == *\"/v1/chat/completions\" ]]; then\n"
                "  echo '{\"choices\":[{\"message\":{\"content\":\"ok\"}}]}'\n"
                "  exit 0\n"
                "fi\n"
                "exit 1\n",
                encoding="utf-8",
            )
            os.chmod(bin_dir / "curl", 0o755)

            env = dict(os.environ)
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            proc = self._run_bash(["bash", str(script)], cwd=tmp_path, env=env)

            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)
            self.assertIn("[DONE] health check passed", proc.stdout)

    def test_rollback_script_writes_full_stage_runtime_payload(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        script = repo / "scripts" / "rollback_to_external_api.sh"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env = dict(os.environ)
            env["ANSWER_API_BASE"] = "https://api.example.com/v1"
            env["ANSWER_API_KEY"] = "sk-test"
            env["ANSWER_MODEL"] = "gpt-4.1-mini"

            proc = self._run_bash(["bash", str(script)], cwd=tmp_path, env=env)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)

            payload_path = tmp_path / "configs" / "llm_runtime_config.json"
            self.assertTrue(payload_path.exists())
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            for stage in ("answer", "embedding", "rerank", "rewrite", "graph_entity"):
                self.assertIn(stage, payload)
                self.assertIn("provider", payload[stage])
                self.assertIn("api_base", payload[stage])
                self.assertIn("api_key", payload[stage])
                self.assertIn("model", payload[stage])


if __name__ == "__main__":
    unittest.main()
