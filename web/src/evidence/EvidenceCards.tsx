// Extracted from App.tsx during the P7b module split.
import type { ClaimReviewRequest } from "../types";
import { EVIDENCE_KIND_LABELS } from "../lib/labels";
import { EvidenceCardView } from "./EvidenceCardView";
import { fieldText } from "../lib/format";

export function EvidenceCards(props: {
  rows: Record<string, unknown>[];
  empty: string;
  onClaimReview: (claimId: string, payload: ClaimReviewRequest) => Promise<void>;
}) {
  if (!props.rows.length) return <div className="empty-table">{props.empty}</div>;
  const groups = props.rows.reduce<Record<string, Record<string, unknown>[]>>((acc, row) => {
    const kind = fieldText(row, "kind") || "other";
    const label = EVIDENCE_KIND_LABELS[kind] ?? kind;
    acc[label] = acc[label] ?? [];
    acc[label].push(row);
    return acc;
  }, {});
  return (
    <div className="evidence-groups">
      {Object.entries(groups).map(([label, rows]) => (
        <section className="evidence-group" key={label}>
          <div className="evidence-group-title">
            <span>{label}</span>
            <b>{rows.length}</b>
          </div>
          {rows.map((row, index) => (
            <EvidenceCardView
              row={row}
              key={`${fieldText(row, "citation_id") || label}-${index}`}
              onClaimReview={props.onClaimReview}
            />
          ))}
        </section>
      ))}
    </div>
  );
}
