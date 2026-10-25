// Extracted from App.tsx during the P7b module split.
import { Download, Loader2, Sparkles } from "lucide-react";
import type { Conversation, ConversationTurn, FeedbackCreateRequest } from "../types";
import { Composer } from "../components/Composer";
import { MessagePair } from "../components/MessagePair";

export function ChatView(props: {
  loading: boolean;
  conversation: Conversation | null;
  examples: string[];
  input: string;
  sending: boolean;
  streamingTurn: ConversationTurn | null;
  streamingProgress: string[];
  thinkingEnabled: boolean;
  reasoningEffort: string;
  reasoningEfforts: string[];
  onInput: (value: string) => void;
  onSubmit: (question?: string) => void;
  onThinkingChange: (value: boolean) => void;
  onReasoningChange: (value: string) => void;
  onOpenDetails: (turn: ConversationTurn) => void;
  onFeedback: (payload: FeedbackCreateRequest) => Promise<void>;
  onExample: (value: string) => void;
}) {
  const hasTurns = Boolean(props.conversation?.turns.length || props.streamingTurn);
  return (
    <section className={`chat-page ${hasTurns ? "with-turns" : "empty"}`}>
      {!hasTurns ? (
        <div className="hero-chat">
          <div className="hero-kicker">AI 算力链产业智能问答系统</div>
          <h1>AIKA</h1>
          <p>面向产业链图谱、研报证据与连续追问的专业问答工作台</p>
          <Composer
            value={props.input}
            sending={props.sending}
            thinkingEnabled={props.thinkingEnabled}
            reasoningEffort={props.reasoningEffort}
            reasoningEfforts={props.reasoningEfforts}
            placeholder="请输入你想了解的 AI 算力链产业问题..."
            onChange={props.onInput}
            onSubmit={props.onSubmit}
            onThinkingChange={props.onThinkingChange}
            onReasoningChange={props.onReasoningChange}
          />
          <ExampleRail examples={props.examples} onPick={props.onExample} onSubmit={props.onSubmit} />
          {props.loading && (
            <div className="loading-line">
              <Loader2 size={16} className="spin" />
              <span>正在连接知识图谱与本地证据库</span>
            </div>
          )}
        </div>
      ) : (
        <div className="conversation-layout">
          <div className="conversation-header">
            <div>
              <span className="eyebrow">当前对话</span>
              <h2>{props.conversation?.title}</h2>
            </div>
            {props.conversation && (
              <div className="export-group">
                <a className="export-link" href={`/api/conversations/${props.conversation.id}/export?format=md`}>
                  <Download size={16} />
                  <span>MD</span>
                </a>
                <a className="export-link" href={`/api/conversations/${props.conversation.id}/export?format=json`}>
                  <Download size={16} />
                  <span>JSON</span>
                </a>
              </div>
            )}
          </div>
          <div className="message-list">
            {props.conversation?.turns.map((turn, index) => (
              <MessagePair
                key={`${turn.created_at}-${index}`}
                index={index}
                turn={turn}
                conversationId={props.conversation?.id ?? ""}
                onOpenDetails={props.onOpenDetails}
                onFeedback={props.onFeedback}
              />
            ))}
            {props.streamingTurn && (
              <MessagePair
                index={props.conversation?.turns.length ?? 0}
                turn={props.streamingTurn}
                isStreaming
                progressItems={props.streamingProgress}
                conversationId={props.conversation?.id ?? ""}
                onOpenDetails={props.onOpenDetails}
                onFeedback={props.onFeedback}
              />
            )}
            {props.sending && !props.streamingTurn && (
              <div className="assistant-thinking">
                <Loader2 size={18} className="spin" />
                <span>正在启动问答链路</span>
              </div>
            )}
          </div>
          <Composer
            compact
            value={props.input}
            sending={props.sending}
            thinkingEnabled={props.thinkingEnabled}
            reasoningEffort={props.reasoningEffort}
            reasoningEfforts={props.reasoningEfforts}
            placeholder="继续追问，系统会自动携带当前对话上下文..."
            onChange={props.onInput}
            onSubmit={props.onSubmit}
            onThinkingChange={props.onThinkingChange}
            onReasoningChange={props.onReasoningChange}
          />
        </div>
      )}
    </section>
  );
}

export function ExampleRail(props: { examples: string[]; onPick: (value: string) => void; onSubmit: (value: string) => void }) {
  return (
    <div className="example-rail">
      {props.examples.slice(0, 4).map((example) => (
        <button key={example} type="button" onClick={() => props.onPick(example)} onDoubleClick={() => props.onSubmit(example)}>
          <Sparkles size={14} />
          <span>{example}</span>
        </button>
      ))}
    </div>
  );
}
