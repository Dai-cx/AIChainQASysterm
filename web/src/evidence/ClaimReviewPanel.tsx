// Extracted from App.tsx during the P7b module split.
import { Loader2, Pencil, Save } from "lucide-react";
import { FormEvent, useState } from "react";
import type { ClaimReviewRequest } from "../types";
import { CLAIM_REVIEW_STATUSES, CLAIM_TYPE_LABELS, EXPOSURE_LABELS } from "../lib/labels";
import { fieldText } from "../lib/format";

export function ClaimReviewPanel(props: {
  row: Record<string, unknown>;
  claimId: string;
  onSubmit: (claimId: string, payload: ClaimReviewRequest) => Promise<void>;
}) {
  const [claimText, setClaimText] = useState(fieldText(props.row, "evidence"));
  const [topic, setTopic] = useState(fieldText(props.row, "topic"));
  const [claimType, setClaimType] = useState(fieldText(props.row, "claim_type"));
  const [exposureLevel, setExposureLevel] = useState(fieldText(props.row, "exposure_level"));
  const [evidenceSpan, setEvidenceSpan] = useState(fieldText(props.row, "evidence_span"));
  const [confidence, setConfidence] = useState(fieldText(props.row, "confidence"));
  const [asOfDate, setAsOfDate] = useState(fieldText(props.row, "as_of_date"));
  const [reviewStatus, setReviewStatus] = useState(fieldText(props.row, "review_status") || "revised");
  const [reviewerNote, setReviewerNote] = useState(fieldText(props.row, "reviewer_note"));
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    try {
      await props.onSubmit(props.claimId, {
        claim_text: claimText,
        topic,
        claim_type: claimType,
        exposure_level: exposureLevel,
        evidence_span: evidenceSpan,
        confidence,
        as_of_date: asOfDate,
        review_status: reviewStatus,
        reviewer_note: reviewerNote
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <details className="claim-review">
      <summary>
        <Pencil size={14} />
        <span>修正 Claim</span>
      </summary>
      <form onSubmit={handleSubmit}>
        <label>
          Claim
          <textarea value={claimText} rows={4} onChange={(event) => setClaimText(event.target.value)} />
        </label>
        <div className="review-grid">
          <label>
            主题
            <input value={topic} onChange={(event) => setTopic(event.target.value)} />
          </label>
          <label>
            类型
            <select value={claimType} onChange={(event) => setClaimType(event.target.value)}>
              <option value="">未分类</option>
              {Object.entries(CLAIM_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            敞口
            <select value={exposureLevel} onChange={(event) => setExposureLevel(event.target.value)}>
              <option value="">未分级</option>
              {Object.entries(EXPOSURE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            状态
            <select value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}>
              {CLAIM_REVIEW_STATUSES.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            置信度
            <input value={confidence} onChange={(event) => setConfidence(event.target.value)} />
          </label>
          <label>
            时点
            <input value={asOfDate} onChange={(event) => setAsOfDate(event.target.value)} />
          </label>
        </div>
        <label>
          原文证据
          <textarea value={evidenceSpan} rows={3} onChange={(event) => setEvidenceSpan(event.target.value)} />
        </label>
        <label>
          备注
          <textarea value={reviewerNote} rows={2} onChange={(event) => setReviewerNote(event.target.value)} />
        </label>
        <button type="submit" disabled={saving}>
          {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
          <span>保存修正</span>
        </button>
      </form>
    </details>
  );
}
