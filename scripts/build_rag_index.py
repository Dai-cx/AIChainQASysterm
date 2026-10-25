#!/usr/bin/env python3
"""Build the lightweight local RAG index from chunk JSONL files.

Writes ``data/rag`` so ``aika eval --suite rag --offline`` and the local retriever work
without PostgreSQL. Pass ``--sync-postgres`` to also push the corpus into a database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from aika.llm_client import load_dotenv
from aika.rag_index import DEFAULT_RAG_DIR, build_rag_documents, build_rag_index
from aika.text_cleaner import CHUNKS_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the local BM25 RAG index from data/chunks JSONL files.")
    parser.add_argument("--chunks-dir", type=Path, default=CHUNKS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RAG_DIR)
    parser.add_argument("--sync-postgres", action="store_true", help="Also sync the corpus into PostgreSQL.")
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    if not args.chunks_dir.exists():
        print(f"No chunk corpus at {args.chunks_dir}; parse PDFs first (scripts/parse_pdfs.py).", file=sys.stderr)
        return 2
    metadata = build_rag_index(args.chunks_dir, args.output_dir)
    print(f"Wrote RAG index chunks={metadata.chunk_count} -> {args.output_dir}")
    if args.sync_postgres:
        from aika.postgres_retrieval import PostgresRetrievalStore

        documents = build_rag_documents(args.chunks_dir)
        store = PostgresRetrievalStore.from_env()
        try:
            store.ensure_ready()
            result = store.sync_rag_documents(documents)
        finally:
            store.close()
        print(
            f"Synced RAG chunks={result['record_count']} deleted={result['deleted']} "
            f"corpus_hash={result['corpus_hash']} -> PostgreSQL"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
