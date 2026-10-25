// Extracted from App.tsx during the P7b module split.
import { ClipboardList, FileText } from "lucide-react";
import type { ConflictGroup, VerificationResult } from "../types";
import { CLAIM_TYPE_LABELS, CONFLICT_TYPE_LABELS, EXPOSURE_LABELS } from "../lib/labels";
import { ResearchList } from "../views/ResearchOutputsView";
import { arrayRecords } from "../lib/format";
import { verificationStatusLabel } from "../lib/verification";

export function VerificationPanel(props: { verification?: VerificationResult }) {
  const verification = props.verification;
  if (!verification) return <div className="empty-table">当前回答没有生成验证结果</div>;
  const gaps = arrayRecords(verification.evidence_gaps ?? []);
  const conflicts = verification.conflict_groups ?? [];
  return (
    <div className="verification-panel">
      <section className="research-section">
        <div className="research-section-title">
          <ClipboardList size={16} />
          <span>验证状态</span>
        </div>
        <div className={`verification-summary ${verification.status || "unknown"}`}>
          <strong>{verificationStatusLabel(verification.status)}</strong>
          <span>{gaps.length} 个证据缺口</span>
          <span>{conflicts.length} 组冲突证据</span>
        </div>
      </section>
      <section className="research-section">
        <div className="research-section-title">
          <FileText size={16} />
          <span>证据缺口</span>
        </div>
        <ResearchList rows={gaps} primaryKey="gap" secondaryKeys={["priority", "suggested_source"]} empty="验证未发现关键证据缺口" />
      </section>
      <section className="research-section">
        <div className="research-section-title">
          <ClipboardList size={16} />
          <span>冲突证据</span>
        </div>
        <ConflictGroupsView groups={conflicts} />
      </section>
    </div>
  );
}

export function ConflictGroupsView(props: { groups: ConflictGroup[] }) {
  if (!props.groups.length) return <div className="empty-table">当前未识别出冲突证据</div>;
  return (
    <div className="conflict-list">
      {props.groups.slice(0, 8).map((group) => (
        <article className="conflict-card" key={group.conflict_group_id}>
          <div className="conflict-card-head">
            <strong>{CONFLICT_TYPE_LABELS[group.conflict_type] ?? group.conflict_type}</strong>
            <span>{[group.company, group.topic].filter(Boolean).join(" · ") || group.conflict_group_id}</span>
          </div>
          <div className="conflict-claims">
            <ConflictClaimView label="证据 A" claim={group.claim_a} />
            <ConflictClaimView label="证据 B" claim={group.claim_b} />
          </div>
          <p className="conflict-resolution">{group.resolution}</p>
        </article>
      ))}
    </div>
  );
}

export function ConflictClaimView(props: { label: string; claim: ConflictGroup["claim_a"] }) {
  const claim = props.claim ?? {};
  return (
    <div className="conflict-claim">
      <span>{props.label}</span>
      <strong>{claim.citation_id || claim.claim_id || "未编号"}</strong>
      <p>{claim.evidence || claim.title || "无证据文本"}</p>
      <div>
        {claim.source && <em>{claim.source}</em>}
        {claim.page && <em>p.{claim.page}</em>}
        {claim.as_of_date && <em>{claim.as_of_date}</em>}
        {claim.claim_type && <em>{CLAIM_TYPE_LABELS[claim.claim_type] ?? claim.claim_type}</em>}
        {claim.exposure_level && <em>{EXPOSURE_LABELS[claim.exposure_level] ?? claim.exposure_level}</em>}
      </div>
    </div>
  );
}
