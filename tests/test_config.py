from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tests.test_support import workspace_tempdir, write_prompt

from ragnos.config import (
    DEFAULT_CACHE_TTL,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_TOP_K,
    ConfigError,
    load_config,
)


class ConfigTests(unittest.TestCase):
    def test_load_config_reads_defaults_and_prompt_file(self) -> None:
        with workspace_tempdir() as root:
            prompt_path = write_prompt(root)
            config = load_config(
                docs_dir="documents",
                chroma_dir="chroma_data",
                prompt_path=str(prompt_path),
            )

        self.assertEqual(config.prompt_path, prompt_path)
        self.assertIn("{context}", config.prompt_text)
        self.assertEqual(config.cache_ttl, DEFAULT_CACHE_TTL)
        self.assertEqual(config.chunk_size, DEFAULT_CHUNK_SIZE)
        self.assertEqual(config.chunk_overlap, DEFAULT_CHUNK_OVERLAP)
        self.assertEqual(config.top_k, DEFAULT_TOP_K)
        self.assertEqual(config.embedding_model, DEFAULT_EMBEDDING_MODEL)
        self.assertEqual(config.llm_model, DEFAULT_LLM_MODEL)

    def test_explicit_args_override_environment(self) -> None:
        with workspace_tempdir() as root:
            env_prompt = write_prompt(root, "Contexte env:\n{context}")
            explicit_prompt = write_prompt(root / "explicit", "Contexte explicite:\n{context}")

            with patch.dict(
                os.environ,
                {
                    "DOCS_DIR": "env-docs",
                    "CHROMA_DIR": "env-chroma",
                    "REDIS_URL": "redis://env",
                    "OLLAMA_BASE_URL": "http://env",
                    "CACHE_TTL": "99",
                    "CHUNK_SIZE": "900",
                    "CHUNK_OVERLAP": "90",
                    "TOP_K": "9",
                    "EMBEDDING_MODEL": "env-embed",
                    "LLM_MODEL": "env-llm",
                    "PROMPT_PATH": str(env_prompt),
                },
                clear=False,
            ):
                config = load_config(
                    docs_dir="explicit-docs",
                    chroma_dir="explicit-chroma",
                    cache_ttl=30,
                    llm_model="explicit-llm",
                    prompt_path=str(explicit_prompt),
                )

        self.assertEqual(str(config.docs_dir), "explicit-docs")
        self.assertEqual(str(config.chroma_dir), "explicit-chroma")
        self.assertEqual(config.redis_url, "redis://env")
        self.assertEqual(config.ollama_base_url, "http://env")
        self.assertEqual(config.cache_ttl, 30)
        self.assertEqual(config.chunk_size, 900)
        self.assertEqual(config.chunk_overlap, 90)
        self.assertEqual(config.top_k, 9)
        self.assertEqual(config.embedding_model, "env-embed")
        self.assertEqual(config.llm_model, "explicit-llm")
        self.assertEqual(config.prompt_path, explicit_prompt)
        self.assertIn("explicite", config.prompt_text)

    def test_invalid_numeric_values_raise_config_error(self) -> None:
        with workspace_tempdir() as root:
            prompt_path = write_prompt(root)

            with self.assertRaises(ConfigError):
                load_config(docs_dir="documents", chroma_dir="chroma_data", prompt_path=str(prompt_path), cache_ttl="0")

            with self.assertRaises(ConfigError):
                load_config(
                    docs_dir="documents",
                    chroma_dir="chroma_data",
                    prompt_path=str(prompt_path),
                    chunk_size=100,
                    chunk_overlap=100,
                )

    def test_missing_prompt_path_raises_config_error(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(
                docs_dir="documents",
                chroma_dir="chroma_data",
                prompt_path=".files/test-temp/missing.prompt",
            )

    def test_prompt_without_context_placeholder_raises_config_error(self) -> None:
        with workspace_tempdir() as root:
            prompt_path = write_prompt(root, "Prompt sans placeholder")
            with self.assertRaises(ConfigError):
                load_config(
                    docs_dir="documents",
                    chroma_dir="chroma_data",
                    prompt_path=str(prompt_path),
                )
