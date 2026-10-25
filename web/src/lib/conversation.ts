// Extracted from App.tsx during the P7b module split.
import type { Conversation, ConversationTurn } from "../types";

export function createPendingTurn(question: string, thinkingEnabled: boolean, reasoningEffort: string): ConversationTurn {
  return {
    created_at: new Date().toISOString(),
    question,
    answer: "",
    thinking_enabled: thinkingEnabled,
    reasoning_effort: thinkingEnabled ? reasoningEffort : "",
    result: {
      question,
      contextual_question: question,
      answer: "",
      reasoning_content: "",
      answer_type: "streaming",
      plan: {},
      cypher: "",
      cypher_params: {},
      cypher_source: "",
      graph_records: [],
      rag_hits: [],
      evidence_cards: [],
      evidence: [],
      research_outputs: {
        report: { title: "", markdown: "", sections: [] },
        company_compare_table: { columns: [], rows: [] },
        risk_checklist: [],
        evidence_gaps: []
      },
      subgraph: [],
      diagnostics: { streaming: true },
      errors: []
    }
  };
}

export function nextProgressItems(items: string[], message: string): string[] {
  const text = message.trim();
  if (!text || items[items.length - 1] === text) return items;
  return [...items, text].slice(-5);
}

export function updateConversationClaimReview(
  conversation: Conversation | null,
  claimId: string,
  claim: Record<string, unknown>
): Conversation | null {
  if (!conversation) return conversation;
  return {
    ...conversation,
    turns: conversation.turns.map((turn) => updateTurnClaimReview(turn, claimId, claim) ?? turn)
  };
}

export function updateTurnClaimReview(
  turn: ConversationTurn | null,
  claimId: string,
  claim: Record<string, unknown>
): ConversationTurn | null {
  if (!turn) return turn;
  const updateRows = (rows: Record<string, unknown>[] = []) =>
    rows.map((row) => {
      if (String(row.claim_id ?? "") !== claimId) return row;
      return {
        ...row,
        evidence: String(claim.claim_text ?? row.evidence ?? ""),
        text: String(claim.claim_text ?? row.text ?? ""),
        topic: String(claim.topic ?? row.topic ?? ""),
        claim_type: String(claim.claim_type ?? row.claim_type ?? ""),
        exposure_level: String(claim.exposure_level ?? row.exposure_level ?? ""),
        confidence: String(claim.confidence ?? row.confidence ?? ""),
        as_of_date: String(claim.as_of_date ?? row.as_of_date ?? ""),
        evidence_span: String(claim.evidence_span ?? row.evidence_span ?? ""),
        review_status: String(claim.review_status ?? row.review_status ?? ""),
        reviewer_note: String(claim.reviewer_note ?? row.reviewer_note ?? "")
      };
    });
  return {
    ...turn,
    result: {
      ...turn.result,
      evidence_cards: updateRows(turn.result.evidence_cards),
      evidence: updateRows(turn.result.evidence)
    }
  };
}
