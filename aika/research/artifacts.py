"""Building the curated claim / evidence-span / dossier artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from aika.extraction_schema import read_csv
from aika.research.claims import claims_from_relation, evidence_span_from_claim
from aika.research.constants import (
    CLAIM_CSV_FIELDS,
    CLAIMS_FILE,
    DEFAULT_RESEARCH_DIR,
    EVIDENCE_SPAN_FIELDS,
    EVIDENCE_SPANS_FILE,
    SEGMENT_DOSSIERS_FILE,
)
from aika.research.dossiers import build_segment_dossiers
from aika.research.technical import claims_from_technical_chunks


def build_research_artifacts(
    *,
    relations_csv: Path,
    output_dir: Path = DEFAULT_RESEARCH_DIR,
    chunks_dir: Path | None = None,
    include_direct_claims: bool = True,
    write_outputs: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build claims, evidence spans, and segment dossiers.

    The base layer is derived from curated KG relations. For professional
    technical sources, we also derive direct original-text claims from chunks so
    roadmap/spec/paper evidence can inform mechanisms and bottlenecks even when
    it is not naturally represented as company-centric triples.
    """
    relations = read_csv(relations_csv)
    claims: list[dict[str, Any]] = []
    evidence_spans: list[dict[str, Any]] = []
    seen_claims: set[str] = set()

    for row in relations:
        for claim in claims_from_relation(row):
            if claim["claim_id"] in seen_claims:
                continue
            seen_claims.add(claim["claim_id"])
            claims.append(claim)
            evidence_spans.append(evidence_span_from_claim(claim))

    if include_direct_claims and chunks_dir is not None:
        for claim in claims_from_technical_chunks(chunks_dir):
            if claim["claim_id"] in seen_claims:
                continue
            seen_claims.add(claim["claim_id"])
            claims.append(claim)
            evidence_spans.append(evidence_span_from_claim(claim))

    dossiers = build_segment_dossiers(claims)
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_csv(output_dir / CLAIMS_FILE, CLAIM_CSV_FIELDS, claims)
        write_csv(output_dir / EVIDENCE_SPANS_FILE, EVIDENCE_SPAN_FIELDS, evidence_spans)
        with (output_dir / SEGMENT_DOSSIERS_FILE).open("w", encoding="utf-8") as file:
            for dossier in dossiers:
                file.write(json.dumps(dossier, ensure_ascii=False, sort_keys=True) + "\n")
    return claims, evidence_spans, dossiers


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: serialize_cell(row.get(field, "")) for field in fields})


def serialize_cell(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "")
