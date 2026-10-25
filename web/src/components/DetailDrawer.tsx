// Extracted from App.tsx during the P7b module split.
import { X } from "lucide-react";
import type { ClaimReviewRequest, ConversationTurn, GraphEdge } from "../types";
import { DetailTab } from "../lib/app";
import { EvidenceCards } from "../evidence/EvidenceCards";
import { GraphCanvas } from "../graph/GraphCanvas";
import { JsonBlock } from "./JsonBlock";
import { ResearchOutputsView } from "../views/ResearchOutputsView";
import { VerificationPanel } from "./VerificationPanel";
import { verificationFromResult } from "../lib/verification";

export function DetailDrawer(props: {
  turn: ConversationTurn | null;
  open: boolean;
  tab: DetailTab;
  onTab: (tab: DetailTab) => void;
  onClose: () => void;
  onClaimReview: (claimId: string, payload: ClaimReviewRequest) => Promise<void>;
}) {
  if (!props.turn || !props.open) return null;
  const result = props.turn.result;
  const evidence = result.evidence_cards?.length ? result.evidence_cards : result.evidence;
  const verification = verificationFromResult(result);

  return (
    <aside className="detail-drawer">
      <div className="drawer-header">
        <div>
          <span className="eyebrow">证据详情</span>
          <h3>{result.answer_type || "问答诊断"}</h3>
        </div>
        <button type="button" onClick={props.onClose} aria-label="关闭详情">
          <X size={18} />
        </button>
      </div>
      {result.contextual_question && result.contextual_question !== result.question && (
        <div className="context-note">上下文改写：{result.contextual_question}</div>
      )}
      <div className="drawer-tabs">
        {[
          ["research", "投研"],
          ["verification", "验证"],
          ["evidence", "证据"],
          ["cypher", "查询"],
          ["diagnostics", "诊断"],
          ["graph", "子图"]
        ].map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={props.tab === key ? "active" : ""}
            onClick={() => props.onTab(key as DetailTab)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="drawer-body">
        {props.tab === "research" && <ResearchOutputsView outputs={result.research_outputs} />}
        {props.tab === "verification" && <VerificationPanel verification={verification} />}
        {props.tab === "evidence" && (
          <EvidenceCards rows={evidence} empty="当前没有证据卡片" onClaimReview={props.onClaimReview} />
        )}
        {props.tab === "cypher" && (
          <div className="code-stack">
            <pre>{result.cypher || "无 Cypher 查询"}</pre>
            <JsonBlock value={result.cypher_params} />
          </div>
        )}
        {props.tab === "diagnostics" && (
          <div className="code-stack">
            <JsonBlock value={result.plan} title="问题规划" />
            <JsonBlock value={result.diagnostics} title="诊断信息" />
            {result.errors?.map((error) => (
              <div className="warning" key={error}>
                {error}
              </div>
            ))}
          </div>
        )}
        {props.tab === "graph" && <SubgraphMini edges={result.subgraph} />}
      </div>
    </aside>
  );
}

export function SubgraphMini(props: { edges: GraphEdge[] }) {
  return <GraphCanvas edges={props.edges} variant="compact" empty="当前答案没有可展示的子图" />;
}
