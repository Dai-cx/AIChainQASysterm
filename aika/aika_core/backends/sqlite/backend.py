"""The SQLite research backend: the backend the lightweight track ships."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable
from aika.aika_core.models import ClaimRecord, CompanyComparison, CompanyProfile, EvidenceCard, EvidenceGap, GraphEdge, ResearchBackend, ResearchBrief

from aika.aika_core.backends.sqlite.util import _dedupe, _limit, _text
from aika.aika_core.backends.sqlite.schema import _connect
from aika.aika_core.backends.sqlite.query import _claim_filter_sql, _dedupe_rows, _evidence_filter_sql, _fts_query, _score_rows, _topic_filter_sql
from aika.aika_core.backends.sqlite.rows import _card_citations, _claim_cards_from_records, _dedupe_evidence_cards, _dedupe_gaps, _dossier_card_from_row, _ensure_citations, _evidence_card_from_row, _graph_edge_from_row, _infer_chain_segment, _strongest_exposure, _summarize_cards
from aika.aika_core.backends.sqlite.index import _fallback_claim_rows, _fallback_dossier_rows, _fallback_evidence_rows


DEFAULT_PROFILE = "sample"


AIKA_HOME_ENV = "AIKA_HOME"


def resolve_aika_home(home: str | Path | None = None) -> Path:
    """Resolve the local AIKA home directory without creating it."""
    value = home or os.getenv(AIKA_HOME_ENV) or "~/.aika"
    return Path(value).expanduser().resolve()


def profile_knowledge_dir(home: str | Path | None = None, *, profile: str = DEFAULT_PROFILE) -> Path:
    return resolve_aika_home(home) / "knowledge" / profile


def profile_index_path(home: str | Path | None = None, *, profile: str = DEFAULT_PROFILE) -> Path:
    return resolve_aika_home(home) / "indexes" / f"{profile}.sqlite"


class SQLiteResearchBackend(ResearchBackend):
    """Research backend backed by a single local SQLite FTS5 index."""

    def __init__(self, index_path: str | Path | None = None, *, home: str | Path | None = None, profile: str = DEFAULT_PROFILE) -> None:
        self.index_path = Path(index_path).expanduser().resolve() if index_path else profile_index_path(home, profile=profile)

    @classmethod
    def from_home(cls, home: str | Path | None = None, *, profile: str = DEFAULT_PROFILE) -> "SQLiteResearchBackend":
        return cls(home=home, profile=profile)

    def search_evidence(self, query: str, *, top_k: int = 8, **filters: Any) -> list[EvidenceCard]:
        limit = _limit(top_k)
        if limit == 0 or not self.index_path.exists():
            return []
        try:
            rows = self._search_evidence_rows(query, limit=limit, filters=filters)
        except sqlite3.Error:
            return []
        cards = [_evidence_card_from_row(row, citation_id=f"E{index}") for index, row in enumerate(rows, start=1)]
        return cards[:limit]

    def search_claims(self, query: str, *, top_k: int = 8, **filters: Any) -> list[ClaimRecord]:
        limit = _limit(top_k)
        if limit == 0 or not self.index_path.exists():
            return []
        try:
            rows = self._search_claim_rows(query, limit=limit, filters=filters)
        except sqlite3.Error:
            return []
        return [ClaimRecord.from_row(dict(row), score=float(row["score"] or 0.0)) for row in rows[:limit]]

    def search_dossiers(self, query: str, *, top_k: int = 3, **filters: Any) -> list[EvidenceCard]:
        limit = _limit(top_k)
        if limit == 0 or not self.index_path.exists():
            return []
        try:
            rows = self._search_dossier_rows(query, limit=limit, filters=filters)
        except sqlite3.Error:
            return []
        return [_dossier_card_from_row(row, citation_id=f"D{index}") for index, row in enumerate(rows, start=1)]

    def query_graph(
        self,
        *,
        company: str = "",
        technology: str = "",
        relation_type: str = "",
        limit: int = 80,
    ) -> list[GraphEdge]:
        row_limit = _limit(limit)
        if row_limit == 0 or not self.index_path.exists():
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if company:
            clauses.append("(head_name LIKE ? OR tail_name LIKE ?)")
            params.extend([f"%{company}%", f"%{company}%"])
        if technology:
            clauses.append("(head_name LIKE ? OR tail_name LIKE ? OR evidence LIKE ?)")
            params.extend([f"%{technology}%", f"%{technology}%", f"%{technology}%"])
        if relation_type:
            clauses.append("relation = ?")
            params.append(relation_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with _connect(self.index_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT * FROM relations
                    {where}
                    ORDER BY relation_id
                    LIMIT ?
                    """,
                    [*params, row_limit],
                ).fetchall()
        except sqlite3.Error:
            return []
        return [_graph_edge_from_row(row) for row in rows]

    def get_company_profile(self, company: str, *, topic: str = "") -> CompanyProfile:
        query = f"{company} {topic}".strip()
        evidence_cards = self.search_evidence(query, top_k=8, company=company, topic=topic or None)
        claims = self.search_claims(query, top_k=5, company=company, topic=topic or None)
        edges = self.query_graph(company=company, technology=topic, limit=12)
        summary = claims[0].claim_text if claims else ""
        return CompanyProfile(
            company=company,
            topic=topic,
            summary=summary,
            evidence_cards=evidence_cards,
            graph_edges=edges,
            research_outputs={
                "claims": [claim.to_dict() for claim in claims],
                "backend": "sqlite",
                "index_path": str(self.index_path),
            },
        )

    def compare_companies(self, companies: Iterable[str], *, topic: str = "") -> CompanyComparison:
        company_list = _dedupe(_text(company) for company in companies if _text(company))
        rows: list[dict[str, Any]] = []
        all_cards: list[EvidenceCard] = []
        all_gaps: list[EvidenceGap] = []
        for company in company_list:
            profile = self.get_company_profile(company, topic=topic)
            all_cards.extend(profile.evidence_cards)
            all_gaps.extend(profile.evidence_gaps)
            rows.append(
                {
                    "company": company,
                    "chain_segment": _infer_chain_segment(profile.graph_edges),
                    "exposure_level": _strongest_exposure(profile.evidence_cards),
                    "business_evidence": _summarize_cards(profile.evidence_cards, {"company_exposure", "mechanism", "supply_chain", ""}),
                    "leading_indicators": _summarize_cards(profile.evidence_cards, {"indicator"}),
                    "risks": _summarize_cards(profile.evidence_cards, {"risk", "bottleneck"}),
                    "citations": "、".join(_card_citations(profile.evidence_cards)[:6]),
                }
            )
            if not profile.evidence_cards:
                all_gaps.append(
                    EvidenceGap(
                        gap=f"{company} 缺少可用于公司对比的证据卡片。",
                        priority="高",
                        suggested_source="补充公司年报、公告、研报或投资者关系记录。",
                    )
                )
        return CompanyComparison(
            companies=company_list,
            topic=topic,
            columns=["company", "chain_segment", "exposure_level", "business_evidence", "leading_indicators", "risks", "citations"],
            rows=rows,
            evidence_cards=_dedupe_evidence_cards(all_cards),
            evidence_gaps=_dedupe_gaps(all_gaps),
            research_outputs={
                "backend": "sqlite",
                "index_path": str(self.index_path),
            },
        )

    def audit_evidence_gaps(
        self,
        query: str,
        *,
        companies: Iterable[str] | None = None,
        topic: str = "",
    ) -> list[EvidenceGap]:
        company_list = _dedupe(_text(company) for company in (companies or []) if _text(company))
        subject = _text(query) or "、".join(company_list) or _text(topic) or "AI算力产业链"
        filters: dict[str, Any] = {}
        if company_list:
            filters["company"] = company_list
        if topic:
            filters["topic"] = topic
        evidence_cards = self.search_evidence(subject, top_k=10, **filters)
        claims = self.search_claims(subject, top_k=10, **filters)
        claim_cards = _claim_cards_from_records(claims, start_index=len(evidence_cards) + 1)
        cards = [*evidence_cards, *claim_cards]
        gaps: list[EvidenceGap] = []
        if not cards:
            gaps.append(
                EvidenceGap(
                    gap="当前问题没有召回可用证据卡片。",
                    priority="高",
                    suggested_source="补充年报、研报原文或行业白皮书后重建本地索引。",
                )
            )
            return gaps
        for company in company_list:
            if not any(company in _card_support_text(card) for card in cards):
                gaps.append(
                    EvidenceGap(
                        gap=f"{company} 缺少直接证据，当前结论可能不完整。",
                        priority="高",
                        suggested_source="补充该公司产品、订单、客户导入或产业链位置证据。",
                    )
                )
        if not any(card.claim_type == "indicator" for card in cards):
            gaps.append(
                EvidenceGap(
                    gap=f"{subject} 缺少订单、收入、产能、客户导入或渗透率等领先指标证据。",
                    priority="高",
                    suggested_source="补充年报财务表、公告、研报指标表或产业数据库。",
                )
            )
        if not any(card.claim_type in {"risk", "bottleneck"} for card in cards):
            gaps.append(
                EvidenceGap(
                    gap=f"{subject} 缺少明确风险、反证或技术瓶颈证据。",
                    priority="中",
                    suggested_source="补充年报风险披露、行业竞争格局和技术路线替代证据。",
                )
            )
        if not any(card.citation_id for card in cards):
            gaps.append(
                EvidenceGap(
                    gap=f"{subject} 召回证据缺少 citation_id。",
                    priority="中",
                    suggested_source="重建 evidence spans 或 claims 索引，确保 citation_id 可追踪。",
                )
            )
        return _dedupe_gaps(gaps)[:12]

    def build_research_brief(self, query: str, *, topic: str = "") -> ResearchBrief:
        # Imported here, not at module level: rendering a report is a presentation
        # concern and pulls in jinja2. Keeping it lazy lets a SQLite-only install import
        # this backend without the report layer.
        from aika.report import build_report_spec, render_html, render_markdown, render_markdown_sections

        subject = _text(query) or (f"{topic}投研简报" if topic else "AI算力产业链投研简报")
        focus_topic = _text(topic)
        evidence_cards = self.search_evidence(subject, top_k=8, topic=focus_topic or None)
        claims = self.search_claims(subject, top_k=8, topic=focus_topic or None)
        claim_cards = _claim_cards_from_records(claims, start_index=len(evidence_cards) + 1)
        dossier_cards = self.search_dossiers(subject, top_k=2, topic=focus_topic or None)
        cards = _dedupe_evidence_cards(_ensure_citations([*dossier_cards, *evidence_cards, *claim_cards]))
        edges = self.query_graph(technology=focus_topic or subject, limit=12)
        gaps = self.audit_evidence_gaps(subject, topic=focus_topic)
        plan = SimpleNamespace(topics=[focus_topic] if focus_topic else [], companies=[])
        spec = build_report_spec(
            question=subject,
            plan=plan,
            evidence_cards=cards,
            graph_records=edges,
            gaps=gaps,
            verification={"status": "not_run", "checks": {}},
        )
        title = spec.title
        sections = render_markdown_sections(spec)
        markdown = render_markdown(spec)
        research_outputs = {
            "report": {
                "title": title,
                "markdown": markdown,
                "html": render_html(spec),
                "sections": sections,
                "report_type": spec.report_type,
                "report_type_label": spec.report_type_label,
                "coverage": spec.coverage.model_dump(),
                "spec": spec.model_dump(),
            },
            "evidence_gaps": [gap.to_dict() for gap in gaps],
            "verification": {"status": "not_run", "checks": {}},
            "meta": {
                "question": subject,
                "topic": focus_topic,
                "evidence_cards": len(cards),
                "coverage": spec.coverage.model_dump(),
                "report_type": spec.report_type,
                "report_type_label": spec.report_type_label,
                "backend": "sqlite",
                "index_path": str(self.index_path),
            },
        }
        return ResearchBrief(
            title=title,
            markdown=markdown,
            sections=sections,
            evidence_cards=cards,
            evidence_gaps=gaps,
            meta=research_outputs["meta"],
            research_outputs=research_outputs,
        )

    def _search_claim_rows(self, query: str, *, limit: int, filters: dict[str, Any]) -> list[sqlite3.Row]:
        match_query = _fts_query(query)
        filter_sql, filter_params = _claim_filter_sql(filters, alias="c")
        with _connect(self.index_path) as connection:
            if match_query:
                try:
                    candidate_limit = max(limit * 20, limit)
                    rows = connection.execute(
                        f"""
                        SELECT c.*, -bm25(claims_fts) AS score
                        FROM claims_fts
                        JOIN claims c ON c.id = claims_fts.rowid
                        WHERE claims_fts MATCH ?
                        {filter_sql}
                        ORDER BY bm25(claims_fts), c.topic, c.claim_type, c.claim_id
                        LIMIT ?
                        """,
                        [match_query, *filter_params, candidate_limit],
                    ).fetchall()
                    if rows:
                        fallback_rows = _fallback_claim_rows(connection, query, limit=candidate_limit, filters=filters)
                        ranked = _score_rows(
                            _dedupe_rows([*rows, *fallback_rows]),
                            query,
                            fields=("claim_text", "evidence_span", "topic", "companies"),
                        )
                        return ranked[:limit] or rows[:limit]
                except sqlite3.OperationalError:
                    pass
            return _fallback_claim_rows(connection, query, limit=limit, filters=filters)

    def _search_evidence_rows(self, query: str, *, limit: int, filters: dict[str, Any]) -> list[sqlite3.Row]:
        match_query = _fts_query(query)
        filter_sql, filter_params = _evidence_filter_sql(filters, alias="e")
        with _connect(self.index_path) as connection:
            if match_query:
                try:
                    candidate_limit = max(limit * 20, limit)
                    rows = connection.execute(
                        f"""
                        SELECT e.*, -bm25(evidence_fts) AS score
                        FROM evidence_fts
                        JOIN evidence_spans e ON e.id = evidence_fts.rowid
                        WHERE evidence_fts MATCH ?
                        {filter_sql}
                        ORDER BY bm25(evidence_fts), e.topic, e.company, e.evidence_id
                        LIMIT ?
                        """,
                        [match_query, *filter_params, candidate_limit],
                    ).fetchall()
                    if rows:
                        fallback_rows = _fallback_evidence_rows(connection, query, limit=candidate_limit, filters=filters)
                        ranked = _score_rows(
                            _dedupe_rows([*rows, *fallback_rows]),
                            query,
                            fields=("evidence", "source_title", "company", "topic"),
                        )
                        return ranked[:limit] or rows[:limit]
                except sqlite3.OperationalError:
                    pass
            return _fallback_evidence_rows(connection, query, limit=limit, filters=filters)

    def _search_dossier_rows(self, query: str, *, limit: int, filters: dict[str, Any]) -> list[sqlite3.Row]:
        match_query = _fts_query(query)
        filter_sql, filter_params = _topic_filter_sql(filters, alias="d")
        with _connect(self.index_path) as connection:
            if match_query:
                try:
                    candidate_limit = max(limit * 20, limit)
                    rows = connection.execute(
                        f"""
                        SELECT d.*, -bm25(dossiers_fts) AS score
                        FROM dossiers_fts
                        JOIN dossiers d ON d.id = dossiers_fts.rowid
                        WHERE dossiers_fts MATCH ?
                        {filter_sql}
                        ORDER BY bm25(dossiers_fts), d.topic
                        LIMIT ?
                        """,
                        [match_query, *filter_params, candidate_limit],
                    ).fetchall()
                    if rows:
                        fallback_rows = _fallback_dossier_rows(connection, query, limit=candidate_limit, filters=filters)
                        ranked = _score_rows(
                            _dedupe_rows([*rows, *fallback_rows]),
                            query,
                            fields=("title", "content", "topic"),
                        )
                        return ranked[:limit] or rows[:limit]
                except sqlite3.OperationalError:
                    pass
            return _fallback_dossier_rows(connection, query, limit=limit, filters=filters)
