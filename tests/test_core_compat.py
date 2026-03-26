from __future__ import annotations

import unittest
from pathlib import Path

from tests import test_support  # noqa: F401

import rag_core
import ragnos.core as core


class CoreCompatibilityTests(unittest.TestCase):
    def test_core_facade_exports_expected_symbols(self) -> None:
        for symbol in [
            "AppConfig",
            "ConfigError",
            "SYSTEM_PROMPT_TEXT",
            "build_prompt",
            "ingest_corpus",
            "load_config",
            "validate_runtime_readiness",
        ]:
            self.assertTrue(hasattr(core, symbol))

    def test_root_rag_core_wrapper_exposes_core_api(self) -> None:
        self.assertTrue(hasattr(rag_core, "load_config"))
        self.assertTrue(hasattr(rag_core, "build_cache_namespace"))

    def test_default_system_prompt_text_matches_prompt_file(self) -> None:
        prompt_text = core.load_prompt_text(Path(core.DEFAULT_PROMPT_PATH))
        self.assertEqual(core.SYSTEM_PROMPT_TEXT, prompt_text)
