"""Synthesis: joining wave results, reviewing them, and summarizing."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from aika.agent_runner import (
    AgentRetrievalState,
    merge_graph_records,
    merge_rag_hits,
    merge_research_hits,
    merge_semantic_hits,
)
from aika.agent_tools import AgentToolCall, cards_from_graphrag_result, cards_from_semantic_hits
from aika.agents.coverage import EvidenceCoverageChecker
from aika.agents.planner import AgentTaskPlan
from aika.aika_core.text import shorten
from aika.graphrag import GraphRagResult, finalize_graphrag
from aika.professional_qa import (
    EvidenceCard,
    assign_citation_ids,
    card_identity,
    cards_from_graph_records,
    cards_from_rag_hits,
    cards_from_research_hits,
    rank_evidence_cards,
)
from aika.question_planner import QuestionPlan

from .models import (
    AgentResult,
    EvidenceCandidate,
    EvidenceCardDraft,
    ReviewReport,
    candidate_id,
    clean_ids,
    clean_strings,
)
from .support import merge_graphrag_results, merge_review_coverage, validate_conflicts, validate_drafts


class SynthesisMixin:

    def join_results(
        self,
        state: AgentRetrievalState,
        results: list[AgentResult],
        *,
        plan: QuestionPlan,
        existing_entries: list[tuple[EvidenceCard, str]],
    ) -> tuple[AgentRetrievalState, list[tuple[EvidenceCard, str]], list[AgentToolCall], list[str]]:
        entries = list(existing_entries)
        calls: list[AgentToolCall] = []
        errors: list[str] = []
        partials: list[GraphRagResult] = []
        for result in results:
            calls.extend(result.tool_calls)
            if result.error:
                errors.append(f"{result.assignment.agent_type} agent failed: {result.error}")
            agent_type = result.assignment.agent_type
            output = result.output
            if agent_type == "graph" and isinstance(output, dict):
                records = list(output.get("records") or [])
                state.graph_records = merge_graph_records(state.graph_records, records)
                generated = output.get("generated")
                if generated is not None:
                    state.generated = generated
                entries.extend((card, "graph") for card in cards_from_graph_records(records, plan))
            elif agent_type == "rag":
                hits = list(output or [])
                state.rag_hits = merge_rag_hits(state.rag_hits, hits)
                entries.extend((card, "rag") for card in cards_from_rag_hits(hits, plan))
            elif agent_type == "research":
                hits = list(output or [])
                state.research_hits = merge_research_hits(state.research_hits, hits)
                entries.extend((card, "research") for card in cards_from_research_hits(hits, plan))
            elif agent_type == "semantic":
                hits = list(output or [])
                state.semantic_hits = merge_semantic_hits(state.semantic_hits, hits)
                entries.extend((card, "semantic") for card in cards_from_semantic_hits(hits, plan))
            elif agent_type == "graphrag" and isinstance(output, GraphRagResult):
                partials.append(output)
                state.research_hits = merge_research_hits(
                    state.research_hits,
                    [*output.global_hits, *output.local_hits],
                )
                entries.extend(
                    (card, "graphrag")
                    for card in cards_from_research_hits([*output.global_hits, *output.local_hits], plan)
                )

        if partials:
            partial = merge_graphrag_results(state.graphrag, partials)
            state.graphrag = finalize_graphrag(
                partial,
                plan=plan,
                graph_records=state.graph_records,
                path_top_k=int(getattr(self.engine, "graph_path_top_k", 6)),
            )
            entries.extend((card, "graphrag") for card in cards_from_graphrag_result(state.graphrag, plan))
        elif state.graphrag is not None:
            state.graphrag = finalize_graphrag(
                state.graphrag,
                plan=plan,
                graph_records=state.graph_records,
                path_top_k=int(getattr(self.engine, "graph_path_top_k", 6)),
            )
        return state, entries, calls, errors

    def build_candidates(
        self,
        entries: list[tuple[EvidenceCard, str]],
        *,
        plan: QuestionPlan,
    ) -> list[EvidenceCandidate]:
        by_identity: dict[tuple[str, str, str, str], tuple[EvidenceCard, str]] = {}
        for card, agent in entries:
            if not card.evidence.strip():
                continue
            by_identity.setdefault(card_identity(card), (card, agent))
        cards = [item[0] for item in by_identity.values()]
        deterministic = rank_evidence_cards(cards, limit=max(len(cards), 1), plan=plan)
        agent_by_identity = {identity: value[1] for identity, value in by_identity.items()}
        return [
            EvidenceCandidate(
                candidate_id=candidate_id(card),
                card=card,
                retrieval_agent=agent_by_identity.get(card_identity(card), ""),
            )
            for card in deterministic
        ]

    def review(
        self,
        *,
        question: str,
        plan: QuestionPlan,
        task_plan: AgentTaskPlan,
        retrieval_state: AgentRetrievalState,
        candidates: list[EvidenceCandidate],
        round_index: int,
    ) -> ReviewReport:
        deterministic_coverage = EvidenceCoverageChecker().check(
            plan,
            task_plan,
            retrieval_state,
            retrieval_round=round_index,
        )
        candidate_ids = {candidate.candidate_id for candidate in candidates}
        fallback_ids = [candidate.candidate_id for candidate in candidates]
        payload = self._safe_json(
            role="reviewer",
            system_prompt=(
                "你是证据审核 Agent。检查相关性、来源质量、冲突和覆盖度。"
                "只能引用候选 ID，只输出严格 JSON，不生成新证据。"
            ),
            user_prompt=json.dumps(
                {
                    "question": question,
                    "question_plan": plan.to_dict(),
                    "required_coverage": task_plan.required_coverage,
                    "deterministic_coverage": deterministic_coverage.to_dict(),
                    "candidates": [candidate.prompt_payload() for candidate in candidates[:40]],
                    "schema": {
                        "accepted_ids": ["candidate_id"],
                        "rejected_ids": ["candidate_id"],
                        "missing_coverage": ["required coverage name"],
                        "conflicts": [{"candidate_ids": ["candidate_id"], "reason": "string"}],
                    },
                },
                ensure_ascii=False,
            ),
        )
        if not isinstance(payload, dict):
            self.llm_budget.note_fallback("reviewer", "invalid review payload")
            return ReviewReport(
                accepted_ids=fallback_ids,
                rejected_ids=[],
                conflicts=[],
                coverage=deterministic_coverage,
                source="deterministic",
                degraded=True,
                error="invalid review payload",
            )
        accepted = clean_ids(payload.get("accepted_ids"), candidate_ids)
        rejected = clean_ids(payload.get("rejected_ids"), candidate_ids)
        if candidates and not accepted:
            self.llm_budget.note_fallback("reviewer", "review rejected every deterministic candidate")
            accepted = fallback_ids
            rejected = []
            source = "deterministic"
            degraded = True
        else:
            accepted = [item for item in accepted if item not in rejected]
            source = "llm"
            degraded = False
        conflicts = validate_conflicts(payload.get("conflicts"), candidate_ids)
        missing = [
            value
            for value in clean_strings(payload.get("missing_coverage"))
            if value in task_plan.required_coverage
        ]
        coverage = merge_review_coverage(deterministic_coverage, missing, plan)
        return ReviewReport(
            accepted_ids=accepted,
            rejected_ids=rejected,
            conflicts=conflicts,
            coverage=coverage,
            source=source,
            degraded=degraded,
        )

    def summarize(
        self,
        *,
        question: str,
        plan: QuestionPlan,
        candidates: list[EvidenceCandidate],
        accepted_ids: list[str],
    ) -> tuple[list[EvidenceCard], list[EvidenceCard], list[EvidenceCardDraft], dict[str, Any]]:
        by_id = {candidate.candidate_id: candidate for candidate in candidates}
        accepted = [by_id[item] for item in accepted_ids if item in by_id]
        raw_cards = [
            replace(
                candidate.card,
                candidate_ids=[candidate.candidate_id],
                retrieval_agent=candidate.retrieval_agent,
            )
            for candidate in candidates
        ]
        payload = self._safe_json(
            role="summarizer",
            system_prompt=(
                "你是证据归纳 Agent。只能选择候选、生成简短标题和选择理由。"
                "不得改写 evidence，不得生成候选之外的事实，只输出严格 JSON。"
            ),
            user_prompt=json.dumps(
                {
                    "question": question,
                    "question_plan": plan.to_dict(),
                    "max_cards": int(getattr(self.engine, "evidence_top_n", 6)),
                    "candidates": [candidate.prompt_payload() for candidate in accepted[:40]],
                    "schema": {
                        "cards": [
                            {
                                "candidate_ids": ["candidate_id"],
                                "title": "short string",
                                "reason": "short string",
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
        )
        drafts = validate_drafts(payload, {candidate.candidate_id for candidate in accepted})
        source = "llm"
        degraded = False
        if not drafts:
            self.llm_budget.note_fallback("summarizer", "invalid or empty summary payload")
            ranked = rank_evidence_cards(
                [candidate.card for candidate in accepted],
                limit=int(getattr(self.engine, "evidence_top_n", 6)),
                plan=plan,
            )
            candidate_by_identity = {card_identity(candidate.card): candidate for candidate in accepted}
            drafts = [
                EvidenceCardDraft(
                    candidate_ids=[candidate_by_identity[card_identity(card)].candidate_id],
                )
                for card in ranked
                if card_identity(card) in candidate_by_identity
            ]
            source = "deterministic"
            degraded = True

        cards: list[EvidenceCard] = []
        seen: set[str] = set()
        for draft in drafts:
            primary_id = next((item for item in draft.candidate_ids if item in by_id), "")
            if not primary_id or primary_id in seen:
                continue
            seen.add(primary_id)
            candidate = by_id[primary_id]
            cards.append(
                replace(
                    candidate.card,
                    title=shorten(draft.title, 160) or candidate.card.title,
                    reason=shorten(draft.reason, 200) or candidate.card.reason,
                    candidate_ids=list(draft.candidate_ids),
                    retrieval_agent=candidate.retrieval_agent,
                )
            )
            if len(cards) >= int(getattr(self.engine, "evidence_top_n", 6)):
                break
        if plan.answer_type == "risk_analysis" and not any(card.relation == "DISCLOSES_RISK" or card.claim_type == "risk" for card in cards):
            risk_candidate = next(
                (
                    candidate
                    for candidate in accepted
                    if candidate.card.relation == "DISCLOSES_RISK" or candidate.card.claim_type == "risk"
                ),
                None,
            )
            if risk_candidate is not None:
                risk_card = replace(
                    risk_candidate.card,
                    candidate_ids=[risk_candidate.candidate_id],
                    retrieval_agent=risk_candidate.retrieval_agent,
                )
                if len(cards) >= int(getattr(self.engine, "evidence_top_n", 6)):
                    cards[-1] = risk_card
                else:
                    cards.append(risk_card)
        return (
            raw_cards,
            assign_citation_ids(cards),
            drafts,
            {"source": source, "degraded": degraded, "drafts": [draft.to_dict() for draft in drafts]},
        )
