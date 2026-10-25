#!/usr/bin/env python3
"""Build the professional curated graph CSVs used by the QA system."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from aika.curated_graph import DEFAULT_CURATED_DIR, build_curated_graph
from aika.frontend_data import DEFAULT_ENTITIES_CSV, DEFAULT_RELATIONS_CSV
from aika.llm_client import load_dotenv
from aika.research_claims import build_research_artifacts
from aika.text_cleaner import CHUNKS_DIR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build curated professional KG CSVs from verified graph CSVs.")
    parser.add_argument("--entities", type=Path, default=DEFAULT_ENTITIES_CSV)
    parser.add_argument("--relations", type=Path, default=DEFAULT_RELATIONS_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_CURATED_DIR)
    parser.add_argument("--chunks-dir", type=Path, default=CHUNKS_DIR)
    parser.add_argument("--no-write", action="store_true", help="Compute the artifacts without writing the files.")
    parser.add_argument("--sync-postgres", action="store_true", help="Also sync the artifacts into PostgreSQL.")
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    entities, relations = build_curated_graph(
        entities_csv=args.entities,
        relations_csv=args.relations,
        output_dir=args.output_dir,
    )
    chunks_dir = args.chunks_dir if args.chunks_dir.exists() else None
    claims, evidence_spans, dossiers = build_research_artifacts(
        relations_csv=args.output_dir / "relations.csv",
        output_dir=args.output_dir,
        chunks_dir=chunks_dir,
        include_direct_claims=chunks_dir is not None,
        write_outputs=not args.no_write,
    )
    print(
        f"Wrote curated entities={len(entities)} relations={len(relations)} "
        f"claims={len(claims)} evidence_spans={len(evidence_spans)} dossiers={len(dossiers)}"
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
