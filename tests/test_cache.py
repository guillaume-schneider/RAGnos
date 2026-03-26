from __future__ import annotations

import unittest
from dataclasses import replace

from tests.test_support import workspace_tempdir, write_prompt

from ragnos.cache import build_cache_key, build_cache_namespace
from ragnos.config import load_config


class CacheNamespaceTests(unittest.TestCase):
    def test_cache_namespace_changes_with_runtime_inputs(self) -> None:
        with workspace_tempdir() as root:
            prompt_path = write_prompt(root)
            config = load_config(docs_dir="documents", chroma_dir="chroma_data", prompt_path=str(prompt_path))

        base_namespace = build_cache_namespace(config, "fingerprint-a")
        other_fingerprint = build_cache_namespace(config, "fingerprint-b")
        other_prompt = build_cache_namespace(replace(config, prompt_text="another prompt"), "fingerprint-a")
        other_model = build_cache_namespace(replace(config, llm_model="other-model"), "fingerprint-a")
        other_retrieval = build_cache_namespace(replace(config, top_k=config.top_k + 1), "fingerprint-a")

        self.assertNotEqual(base_namespace, other_fingerprint)
        self.assertNotEqual(base_namespace, other_prompt)
        self.assertNotEqual(base_namespace, other_model)
        self.assertNotEqual(base_namespace, other_retrieval)
        self.assertNotEqual(
            build_cache_key("Question", base_namespace),
            build_cache_key("Question", other_prompt),
        )
