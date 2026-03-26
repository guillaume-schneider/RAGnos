from __future__ import annotations

import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests import test_support  # noqa: F401

import ragnos.benchmark as benchmark_mod
from ragnos.runtime import QueryResult


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_main_prints_summary(self) -> None:
        fake_config = object()
        fake_state = object()
        fake_result = QueryResult(
            answer="ok",
            docs=[],
            sources=["sample.pdf"],
            citations=[],
            chunks_used=2,
            retrieval_ms=12.0,
            first_token_ms=34.0,
            generation_ms=56.0,
            total_ms=78.0,
            cache_hit=False,
        )

        with patch("ragnos.benchmark.load_config", return_value=fake_config), patch(
            "ragnos.benchmark.validate_runtime_readiness",
            return_value=SimpleNamespace(is_ready=True, docs_fingerprint="fp"),
        ), patch("ragnos.benchmark.build_runtime_state", new=AsyncMock(return_value=fake_state)), patch(
            "ragnos.benchmark.run_query",
            new=AsyncMock(return_value=fake_result),
        ) as run_query_mock, patch(
            "ragnos.benchmark.close_runtime_state",
            new=AsyncMock(),
        ), patch(
            "ragnos.benchmark.log_event"
        ) as log_mock, patch("sys.stdout", new_callable=io.StringIO) as stdout:
            exit_code = benchmark_mod.main(["--question", "Hello", "--repetitions", "2"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Benchmark summary", stdout.getvalue())
        self.assertIn("first_token_ms", stdout.getvalue())
        self.assertEqual(run_query_mock.await_count, 2)
        log_mock.assert_called_once()
