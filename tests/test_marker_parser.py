from __future__ import annotations

import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.marker_parser import _TimeoutGuard, parse_pdf_with_marker


class MarkerParserCompatibilityTests(unittest.TestCase):
    def test_timeout_guard_skips_signal_registration_outside_main_thread(self) -> None:
        called = {"signal": 0, "setitimer": 0}
        errors: list[Exception] = []

        def _run() -> None:
            try:
                with _TimeoutGuard(1.0):
                    return
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(exc)

        with (
            patch("app.marker_parser.signal.signal", side_effect=lambda *args, **kwargs: called.__setitem__("signal", called["signal"] + 1)),
            patch("app.marker_parser.signal.setitimer", side_effect=lambda *args, **kwargs: called.__setitem__("setitimer", called["setitimer"] + 1)),
        ):
            worker = threading.Thread(target=_run)
            worker.start()
            worker.join(timeout=5)

        self.assertFalse(errors)
        self.assertEqual(called["signal"], 0)
        self.assertEqual(called["setitimer"], 0)

    def test_parse_pdf_with_marker_supports_artifact_dict_constructor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")

            class _FakePdfConverter:
                def __init__(self, artifact_dict: dict, **_kwargs: object) -> None:
                    self._artifact_dict = artifact_dict

                def build_document(self, _fpath: str) -> dict:
                    assert "layout_model" in self._artifact_dict
                    return {
                        "markdown": "Attention Is All You Need\nBody",
                        "blocks": [
                            {"page": 1, "text": "Attention Is All You Need", "heading_level": 1},
                            {"page": 1, "text": "Body"},
                        ],
                    }

            converter_module = types.SimpleNamespace(PdfConverter=_FakePdfConverter)
            models_module = types.SimpleNamespace(create_model_dict=lambda: {"layout_model": object()})

            def _fake_import(name: str) -> object:
                if name == "marker.converters.pdf":
                    return converter_module
                if name == "marker.models":
                    return models_module
                raise ImportError(name)

            with (
                patch("app.marker_parser.importlib.import_module", side_effect=_fake_import),
                patch(
                    "app.marker_parser._extract_markdown_and_blocks",
                    return_value=(
                        "Attention Is All You Need\nBody",
                        [
                            {"page": 1, "text": "Attention Is All You Need", "heading_level": 1},
                            {"page": 1, "text": "Body"},
                        ],
                    ),
                ),
            ):
                parsed = parse_pdf_with_marker(pdf_path, timeout_sec=0.0)

        self.assertTrue(parsed.pages)
        self.assertIn("Attention Is All You Need", parsed.pages[0].text)
        self.assertTrue(parsed.title_candidates)

    def test_parse_pdf_with_marker_falls_back_when_signature_probe_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")

            class _FakePdfConverter:
                def __init__(self, artifact_dict: dict, **_kwargs: object) -> None:
                    self._artifact_dict = artifact_dict

                def build_document(self, _fpath: str) -> dict:
                    assert "layout_model" in self._artifact_dict
                    return {
                        "markdown": "Attention Is All You Need\nBody",
                        "blocks": [
                            {"page": 1, "text": "Attention Is All You Need", "heading_level": 1},
                            {"page": 1, "text": "Body"},
                        ],
                    }

            converter_module = types.SimpleNamespace(PdfConverter=_FakePdfConverter)
            models_module = types.SimpleNamespace(create_model_dict=lambda: {"layout_model": object()})

            def _fake_import(name: str) -> object:
                if name == "marker.converters.pdf":
                    return converter_module
                if name == "marker.models":
                    return models_module
                raise ImportError(name)

            with (
                patch("app.marker_parser.importlib.import_module", side_effect=_fake_import),
                patch("app.marker_parser.inspect.signature", side_effect=ValueError("signature unavailable")),
                patch(
                    "app.marker_parser._extract_markdown_and_blocks",
                    return_value=(
                        "Attention Is All You Need\nBody",
                        [
                            {"page": 1, "text": "Attention Is All You Need", "heading_level": 1},
                            {"page": 1, "text": "Body"},
                        ],
                    ),
                ),
            ):
                parsed = parse_pdf_with_marker(pdf_path, timeout_sec=0.0)

        self.assertTrue(parsed.pages)
        self.assertIn("Attention Is All You Need", parsed.pages[0].text)
        self.assertTrue(parsed.title_candidates)


if __name__ == "__main__":
    unittest.main()
