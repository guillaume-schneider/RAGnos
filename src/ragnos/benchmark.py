from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Sequence

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ragnos.config import BENCHMARK_COMMAND, ConfigError, load_config
from ragnos.indexing import validate_runtime_readiness
from ragnos.runtime import build_runtime_state, close_runtime_state, run_query
from ragnos.telemetry import log_event


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark local RAG startup and query latency.")
    parser.add_argument("--question", required=True, help="Question to send through the RAG pipeline.")
    parser.add_argument("--repetitions", type=int, default=1, help="Number of uncached query runs to execute.")
    parser.add_argument("--docs-dir", help="Directory containing PDF and JSON corpus files.")
    parser.add_argument("--chroma-dir", help="Directory used for the Chroma index.")
    return parser.parse_args(argv)


async def run_benchmark(question: str, repetitions: int, docs_dir: str | None, chroma_dir: str | None) -> int:
    if repetitions < 1:
        print("ERROR: --repetitions must be greater than 0.", file=sys.stderr)
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

    startup_start = time.perf_counter()
    state = await build_runtime_state(config, validation.docs_fingerprint)
    startup_ms = (time.perf_counter() - startup_start) * 1000

    try:
        results = []
        for _ in range(repetitions):
            results.append(await run_query(state, question, use_cache=False))
    finally:
        await close_runtime_state(state)

    retrieval_values = [result.retrieval_ms for result in results]
    first_token_values = [result.first_token_ms for result in results]
    generation_values = [result.generation_ms for result in results]
    total_values = [result.total_ms for result in results]

    summary = {
        "event": "benchmark_complete",
        "question": question,
        "repetitions": repetitions,
        "startup_ms": round(startup_ms, 2),
        "retrieval_ms": round(mean(retrieval_values), 2),
        "first_token_ms": round(mean(first_token_values), 2),
        "generation_ms": round(mean(generation_values), 2),
        "total_ms": round(mean(total_values), 2),
        "chunks_used": results[-1].chunks_used,
    }
    log_event(summary)

    print("Benchmark summary")
    print(f"- startup_ms: {summary['startup_ms']}")
    print(f"- retrieval_ms: {summary['retrieval_ms']}")
    print(f"- first_token_ms: {summary['first_token_ms']}")
    print(f"- generation_ms: {summary['generation_ms']}")
    print(f"- total_ms: {summary['total_ms']}")
    print(f"- chunks_used: {summary['chunks_used']}")
    print(f"- repetitions: {repetitions}")
    print(f"- command: {BENCHMARK_COMMAND}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run_benchmark(args.question, args.repetitions, args.docs_dir, args.chroma_dir))


if __name__ == "__main__":
    raise SystemExit(main())
