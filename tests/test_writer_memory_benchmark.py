from __future__ import annotations

import os
import tempfile
import tracemalloc
import unittest
from pathlib import Path

from app.models import PaperRecord
from app.writer import write_papers_json


@unittest.skipUnless(os.getenv("RUN_SLOW_TESTS") == "1", "slow benchmark; set RUN_SLOW_TESTS=1 to enable")
class WriterMemoryBenchmarkTests(unittest.TestCase):
    def test_write_papers_json_peak_memory_under_threshold(self) -> None:
        # Large synthetic workload to verify streaming writer does not build full list in memory.
        total = 200_000
        memory_threshold_bytes = 128 * 1024 * 1024  # 128 MB

        def _rows():
            for i in range(total):
                yield PaperRecord(
                    paper_id=f"paper-{i}",
                    title=f"title-{i}",
                    path=f"/tmp/{i}.pdf",
                )

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "papers.json"
            tracemalloc.start()
            write_papers_json(_rows(), output)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

        self.assertLess(
            peak,
            memory_threshold_bytes,
            msg=f"peak memory too high: {peak} bytes for {total} rows",
        )


if __name__ == "__main__":
    unittest.main()
