// Extracted from App.tsx during the P7b module split.
import type { ClaimReviewRequest } from "../types";
import { CLAIM_TYPE_LABELS, EXPOSURE_LABELS } from "../lib/labels";
import { ClaimReviewPanel } from "./ClaimReviewPanel";
import { fieldText } from "../lib/format";

export function EvidenceCardView(props: {
  row: Record<string, unknown>;
  onClaimReview: (claimId: string, payload: ClaimReviewRequest) => Promise<void>;
}) {
  const row = props.row;
  const citationId = fieldText(row, "citation_id");
  const claimId = fieldText(row, "claim_id");
  const title = fieldText(row, "title") || fieldText(row, "source") || "证据";
  const evidence = fieldText(row, "evidence");
  const evidenceSpan = fieldText(row, "evidence_span");
  const source = fieldText(row, "source");
  const page = fieldText(row, "page");
  const section = fieldText(row, "section");
  const claimType = fieldText(row, "claim_type");
  const exposureLevel = fieldText(row, "exposure_level");
  const confidence = fieldText(row, "confidence");
  const score = fieldText(row, "score");
  const semanticScore = fieldText(row, "semantic_score");
  const semanticRefId = fieldText(row, "semantic_ref_id");
  const reviewStatus = fieldText(row, "review_status");
  const reviewerNote = fieldText(row, "reviewer_note");
  return (
    <article className="evidence-card">
      <div className="evidence-card-head">
        <div>
          <span className="citation-pill">{citationId || "E?"}</span>
          <strong>{title}</strong>
        </div>
        <div className="evidence-tags">
          {claimType && <span>{CLAIM_TYPE_LABELS[claimType] ?? claimType}</span>}
          {exposureLevel && <span>{EXPOSURE_LABELS[exposureLevel] ?? exposureLevel}</span>}
          {reviewStatus && <span>{reviewStatus}</span>}
        </div>
      </div>
      <p>{evidence || "无证据文本"}</p>
      {evidenceSpan && evidenceSpan !== evidence && <p className="evidence-span">原文：{evidenceSpan}</p>}
      <div className="evidence-meta">
        {source && <span>{source}</span>}
        {page && <span>p.{page}</span>}
        {section && <span>{section}</span>}
        {confidence && <span>置信度 {confidence}</span>}
        {semanticScore && semanticScore !== "0" && <span>semantic {semanticScore}</span>}
        {semanticRefId && <span>{semanticRefId}</span>}
        {score && <span>score {score}</span>}
      </div>
      {reviewerNote && <div className="review-note">审校备注：{reviewerNote}</div>}
      {fieldText(row, "kind") === "claim" && claimId && (
        <ClaimReviewPanel row={row} claimId={claimId} onSubmit={props.onClaimReview} />
      )}
    </article>
  );
}
