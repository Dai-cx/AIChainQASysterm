#!/usr/bin/env python3
"""Build research claims, evidence spans, and segment dossiers.

The artifacts are written to ``data/curated`` by default, so this pipeline no longer
needs PostgreSQL. Pass ``--sync-postgres`` to also push them into a database.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from aika.curated_graph import CURATED_RELATIONS_CSV, DEFAULT_CURATED_DIR
from aika.llm_client import load_dotenv
from aika.research_claims import build_research_artifacts
from aika.text_cleaner import CHUNKS_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build professional research artifacts from curated KG relations.")
    parser.add_argument("--relations", type=Path, default=CURATED_RELATIONS_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_CURATED_DIR)
    parser.add_argument("--chunks-dir", type=Path, default=CHUNKS_DIR)
    parser.add_argument("--no-direct-claims", action="store_true", help="Only derive claims from curated KG relations.")
    parser.add_argument("--no-write", action="store_true", help="Compute the artifacts without writing the files.")
    parser.add_argument("--sync-postgres", action="store_true", help="Also sync the artifacts into PostgreSQL.")
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    chunks_dir = None if args.no_direct_claims else args.chunks_dir
    if chunks_dir is not None and not chunks_dir.exists():
        chunks_dir = None
    claims, evidence_spans, dossiers = build_research_artifacts(
        relations_csv=args.relations,
        output_dir=args.output_dir,
        chunks_dir=chunks_dir,
        include_direct_claims=chunks_dir is not None,
        write_outputs=not args.no_write,
    )
    if args.no_write:
        print(f"Built claims={len(claims)} evidence_spans={len(evidence_spans)} dossiers={len(dossiers)} (not written)")
    else:
        print(
            f"Wrote claims={len(claims)} evidence_spans={len(evidence_spans)} "
            f"dossiers={len(dossiers)} -> {args.output_dir}"
        )
    if args.sync_postgres:
        from aika.postgres_retrieval import PostgresRetrievalStore

        store = PostgresRetrievalStore.from_env()
        try:
            store.ensure_ready()
            result = store.sync_research(claims, dossiers)
        finally:
            store.close()
        print(f"Synced claims={result['claims']} dossiers={result['dossiers']} -> PostgreSQL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
