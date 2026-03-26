from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ragnos.core import IngestError, ingest_corpus, load_config, log_event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or refresh the local RAG index.")
    parser.add_argument("--docs-dir", help="Directory containing PDF files.")
    parser.add_argument("--chroma-dir", help="Directory used for the Chroma index.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(
        docs_dir=args.docs_dir,
        chroma_dir=args.chroma_dir,
    )

    try:
        result = ingest_corpus(config)
    except IngestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Failed to build the index: {exc}", file=sys.stderr)
        return 1

    log_event(
        {
            "event": "ingest_complete",
            "status": result.status,
            "documents_count": result.pdf_count,
            "pages_count": result.page_count,
            "chunks_count": result.chunk_count,
            "chroma_dir": str(config.chroma_dir),
        }
    )

    if result.status == "up_to_date":
        print(f"Index already up to date for {result.pdf_count} PDF(s).")
    else:
        print(
            "Index rebuilt successfully "
            f"for {result.pdf_count} PDF(s), {result.page_count} page(s), {result.chunk_count} chunk(s)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
