from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.test_support import workspace_tempdir

import ragnos.evals as evals_mod
from ragnos.runtime import QueryResult


class EvalsTests(unittest.TestCase):
    def test_eval_runner_passes_dataset(self) -> None:
        with workspace_tempdir() as root:
            dataset = root / "dataset.jsonl"
            dataset.write_text(
                json.dumps(
                    {
                        "id": "ok_case",
                        "question": "Question ?",
                        "must_contain": ["Je ne trouve pas"],
                        "must_not_contain": ["Sources:"],
                        "expect_refusal": True,
                    }
                ),
                encoding="utf-8",
            )

            fake_result = QueryResult(
                answer="Je ne trouve pas cette information dans les documents fournis.",
                docs=[],
                sources=[],
                citations=[],
                chunks_used=0,
                retrieval_ms=1.0,
                first_token_ms=1.0,
                generation_ms=1.0,
                total_ms=1.0,
                cache_hit=False,
            )

            with patch("ragnos.evals.load_config", return_value=object()), patch(
                "ragnos.evals.validate_runtime_readiness",
                return_value=SimpleNamespace(is_ready=True, docs_fingerprint="fp"),
            ), patch("ragnos.evals.build_runtime_state", new=AsyncMock(return_value=object())), patch(
                "ragnos.evals.run_query",
                new=AsyncMock(return_value=fake_result),
            ), patch("ragnos.evals.close_runtime_state", new=AsyncMock()), patch(
                "sys.stdout",
                new_callable=io.StringIO,
            ) as stdout:
                exit_code = evals_mod.main(["--dataset", str(dataset)])

        self.assertEqual(exit_code, 0)
        self.assertIn("PASS ok_case", stdout.getvalue())
        self.assertIn("Summary:", stdout.getvalue())
