// Extracted from App.tsx during the P7b module split.
import { CheckCircle2, CircleSlash, FileText, Loader2, Save, ThumbsDown, ThumbsUp } from "lucide-react";
import { FormEvent, useState } from "react";
import type { ConversationTurn, FeedbackCreateRequest } from "../types";
import { citationIdsFromTurn, hashText } from "../lib/format";

export function FeedbackControls(props: {
  conversationId: string;
  turnIndex: number;
  turn: ConversationTurn;
  onFeedback: (payload: FeedbackCreateRequest) => Promise<void>;
}) {
  const [helpful, setHelpful] = useState<boolean | null>(null);
  const [evidenceSupported, setEvidenceSupported] = useState<boolean | null>(null);
  const [missingAnswer, setMissingAnswer] = useState<boolean | null>(null);
  const [humanScore, setHumanScore] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await props.onFeedback({
        conversation_id: props.conversationId,
        turn_index: props.turnIndex,
        question: props.turn.question,
        answer_hash: hashText(props.turn.answer),
        helpful,
        evidence_supported: evidenceSupported,
        missing_answer: missingAnswer,
        human_score: humanScore ? Number(humanScore) : null,
        note,
        citation_ids: citationIdsFromTurn(props.turn)
      });
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="feedback-panel" onSubmit={submit}>
      <div className="feedback-toggles">
        <button className={helpful === true ? "active" : ""} type="button" onClick={() => setHelpful(helpful === true ? null : true)}>
          <ThumbsUp size={14} />
          <span>有帮助</span>
        </button>
        <button className={helpful === false ? "active negative" : ""} type="button" onClick={() => setHelpful(helpful === false ? null : false)}>
          <ThumbsDown size={14} />
          <span>无帮助</span>
        </button>
        <button
          className={evidenceSupported === true ? "active" : ""}
          type="button"
          onClick={() => setEvidenceSupported(evidenceSupported === true ? null : true)}
        >
          <CheckCircle2 size={14} />
          <span>证据支持</span>
        </button>
        <button
          className={evidenceSupported === false ? "active negative" : ""}
          type="button"
          onClick={() => setEvidenceSupported(evidenceSupported === false ? null : false)}
        >
          <CircleSlash size={14} />
          <span>证据不足</span>
        </button>
        <button
          className={missingAnswer === true ? "active negative" : ""}
          type="button"
          onClick={() => setMissingAnswer(missingAnswer === true ? null : true)}
        >
          <FileText size={14} />
          <span>有遗漏</span>
        </button>
      </div>
      <div className="feedback-note-row">
        <select value={humanScore} onChange={(event) => setHumanScore(event.target.value)} aria-label="人工评分">
          <option value="">人工评分</option>
          {[5, 4, 3, 2, 1].map((score) => (
            <option key={score} value={score}>
              {score} 分
            </option>
          ))}
        </select>
        <input value={note} placeholder="补充反馈" onChange={(event) => setNote(event.target.value)} />
        <button type="submit" disabled={saving || saved}>
          {saving ? <Loader2 size={14} className="spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
          <span>{saved ? "已保存" : "保存反馈"}</span>
        </button>
      </div>
    </form>
  );
}
