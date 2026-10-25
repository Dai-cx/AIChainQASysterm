// Extracted from App.tsx during the P7b module split.
import { Bot, ChevronRight, FileText, Loader2 } from "lucide-react";
import type { ConversationTurn, FeedbackCreateRequest } from "../types";
import { FeedbackControls } from "./FeedbackControls";
import { renderAnswerMarkdown } from "../lib/markdown";

export function MessagePair(props: {
  index: number;
  turn: ConversationTurn;
  conversationId: string;
  isStreaming?: boolean;
  progressItems?: string[];
  onOpenDetails: (turn: ConversationTurn) => void;
  onFeedback: (payload: FeedbackCreateRequest) => Promise<void>;
}) {
  return (
    <article className="turn">
      <div className="message user-message">
        <div className="avatar">U</div>
        <div className="bubble">
          <p>{props.turn.question}</p>
        </div>
      </div>
      <div className="message assistant-message">
        <div className="avatar">
          <Bot size={18} />
        </div>
        <div className="bubble answer">
          <div className="answer-meta">
            <span>第 {props.index + 1} 轮</span>
            <span>{props.turn.thinking_enabled ? `思考 ${props.turn.reasoning_effort}` : "快速回答"}</span>
            {props.isStreaming && <span>生成中</span>}
          </div>
          {props.turn.thinking_enabled && Boolean(props.progressItems?.length) && (
            <ThoughtProgress items={props.progressItems ?? []} />
          )}
          <div className="answer-text">
            {props.turn.answer ? (
              <>
                {renderAnswerMarkdown(props.turn.answer)}
                {props.isStreaming && <span className="stream-caret" />}
              </>
            ) : (
              <div className="stream-placeholder">
                <Loader2 size={16} className="spin" />
                <span>正在生成答案</span>
              </div>
            )}
          </div>
          {!props.isStreaming && (
            <>
              <div className="answer-action-row">
                <button className="details-button" type="button" onClick={() => props.onOpenDetails(props.turn)}>
                  <FileText size={15} />
                  <span>查看证据与诊断</span>
                  <ChevronRight size={15} />
                </button>
              </div>
              <FeedbackControls
                conversationId={props.conversationId}
                turnIndex={props.index}
                turn={props.turn}
                onFeedback={props.onFeedback}
              />
            </>
          )}
        </div>
      </div>
    </article>
  );
}

export function ThoughtProgress(props: { items: string[] }) {
  return (
    <div className="thought-progress" aria-live="polite">
      {props.items.map((item, index) => (
        <div className="thought-step" key={`${item}-${index}`}>
          <span>{index + 1}</span>
          <p>{item}</p>
        </div>
      ))}
    </div>
  );
}
