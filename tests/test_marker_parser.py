from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.marker_parser import parse_pdf_with_marker


class MarkerParserCompatibilityTests(unittest.TestCase):
    def test_parse_pdf_with_marker_supports_artifact_dict_constructor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")

            class _FakePdfConverter:
                def __init__(self, artifact_dict: dict, **_kwargs: object) -> None:
                    self._artifact_dict = artifact_dict

                def __call__(self, _fpath: str) -> dict:
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

            with patch("app.marker_parser.importlib.import_module", side_effect=_fake_import):
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

                def __call__(self, _fpath: str) -> dict:
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
            ):
                parsed = parse_pdf_with_marker(pdf_path, timeout_sec=0.0)

        self.assertTrue(parsed.pages)
        self.assertIn("Attention Is All You Need", parsed.pages[0].text)
        self.assertTrue(parsed.title_candidates)


if __name__ == "__main__":
    unittest.main()
