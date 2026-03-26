from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Sequence

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ragnos.config import ConfigError, load_config
from ragnos.health import build_health_report, format_health_report
from ragnos.telemetry import log_event


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check local RAG dependencies and index readiness.")
    parser.add_argument("--docs-dir", help="Directory containing PDF files.")
    parser.add_argument("--chroma-dir", help="Directory used for the Chroma index.")
    return parser.parse_args(argv)


async def run_healthcheck(docs_dir: str | None, chroma_dir: str | None) -> int:
    try:
        config = load_config(docs_dir=docs_dir, chroma_dir=chroma_dir)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report = await build_health_report(config)
    log_event({"event": "healthcheck_complete", **report.to_dict()})
    print(format_health_report(report))
    return 0 if report.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run_healthcheck(args.docs_dir, args.chroma_dir))


if __name__ == "__main__":
    raise SystemExit(main())
