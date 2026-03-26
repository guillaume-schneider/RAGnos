from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ragnos.config import ConfigError, EVALS_COMMAND, load_config
from ragnos.indexing import validate_runtime_readiness
from ragnos.runtime import build_runtime_state, close_runtime_state, run_query


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    question: str
    must_contain: list[str]
    must_not_contain: list[str]
    expect_refusal: bool = False
    expected_sources: list[str] | None = None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local RAG regression evals against a JSONL dataset.")
    parser.add_argument("--dataset", default="evals/regression.jsonl", help="Path to a JSONL eval dataset.")
    parser.add_argument("--docs-dir", help="Directory containing PDF files.")
    parser.add_argument("--chroma-dir", help="Directory used for the Chroma index.")
    return parser.parse_args(argv)


def load_eval_cases(dataset_path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        cases.append(
            EvalCase(
                case_id=payload["id"],
                question=payload["question"],
                must_contain=list(payload.get("must_contain", [])),
                must_not_contain=list(payload.get("must_not_contain", [])),
                expect_refusal=bool(payload.get("expect_refusal", False)),
                expected_sources=list(payload["expected_sources"]) if payload.get("expected_sources") else None,
            )
        )
    return cases


def evaluate_case(case: EvalCase, answer: str, sources: list[str]) -> tuple[bool, list[str]]:
    failures: list[str] = []

    for snippet in case.must_contain:
        if snippet not in answer:
            failures.append(f"missing required snippet: {snippet}")

    for snippet in case.must_not_contain:
        if snippet in answer:
            failures.append(f"forbidden snippet present: {snippet}")

    if case.expect_refusal and "Je ne trouve pas" not in answer:
        failures.append("expected refusal response")

    if case.expected_sources:
        for expected_source in case.expected_sources:
            if expected_source not in sources:
                failures.append(f"missing expected source: {expected_source}")

    return (not failures), failures


async def run_evals(dataset: str, docs_dir: str | None, chroma_dir: str | None) -> int:
    dataset_path = Path(dataset)
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found: {dataset_path}", file=sys.stderr)
        return 1

    try:
        config = load_config(docs_dir=docs_dir, chroma_dir=chroma_dir)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    validation = validate_runtime_readiness(config)
    if not validation.is_ready or not validation.docs_fingerprint:
        print(f"ERROR: {validation.message}", file=sys.stderr)
        return 1

    cases = load_eval_cases(dataset_path)
    if not cases:
        print(f"ERROR: No eval cases found in {dataset_path}", file=sys.stderr)
        return 1

    state = await build_runtime_state(config, validation.docs_fingerprint)
    failures = 0

    try:
        for case in cases:
            result = await run_query(state, case.question, use_cache=False)
            ok, reasons = evaluate_case(case, result.answer, result.sources)
            if ok:
                print(f"PASS {case.case_id}")
            else:
                failures += 1
                print(f"FAIL {case.case_id}")
                for reason in reasons:
                    print(f"- {reason}")
    finally:
        await close_runtime_state(state)

    print(f"Summary: {len(cases) - failures}/{len(cases)} passed")
    print(f"Command: {EVALS_COMMAND}")
    return 0 if failures == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run_evals(args.dataset, args.docs_dir, args.chroma_dir))


if __name__ == "__main__":
    raise SystemExit(main())
