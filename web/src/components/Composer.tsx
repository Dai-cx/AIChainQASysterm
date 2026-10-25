// Extracted from App.tsx during the P7b module split.
import { Loader2, Send } from "lucide-react";
import { KeyboardEvent } from "react";

export function Composer(props: {
  value: string;
  sending: boolean;
  thinkingEnabled: boolean;
  reasoningEffort: string;
  reasoningEfforts: string[];
  placeholder: string;
  compact?: boolean;
  onChange: (value: string) => void;
  onSubmit: (question?: string) => void;
  onThinkingChange: (value: boolean) => void;
  onReasoningChange: (value: string) => void;
}) {
  const reasoningEfforts = props.reasoningEfforts.length ? props.reasoningEfforts : ["low", "medium", "high"];
  const activeReasoningEffort = reasoningEfforts.includes(props.reasoningEffort)
    ? props.reasoningEffort
    : reasoningEfforts[0];

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      props.onSubmit();
    }
  }

  function toggleThinking() {
    props.onThinkingChange(!props.thinkingEnabled);
  }

  function cycleReasoningEffort() {
    if (!props.thinkingEnabled) {
      props.onReasoningChange(activeReasoningEffort);
      props.onThinkingChange(true);
      return;
    }
    const currentIndex = reasoningEfforts.indexOf(activeReasoningEffort);
    const nextEffort = reasoningEfforts[(currentIndex + 1) % reasoningEfforts.length];
    props.onReasoningChange(nextEffort);
  }

  return (
    <div className={`composer ${props.compact ? "compact" : ""}`}>
      <textarea
        value={props.value}
        rows={3}
        placeholder={props.placeholder}
        onChange={(event) => props.onChange(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="composer-footer">
        <div className="composer-controls">
          <button
            className={props.thinkingEnabled ? "pill active" : "pill"}
            type="button"
            disabled={props.sending}
            aria-pressed={props.thinkingEnabled}
            onClick={toggleThinking}
          >
            思考模式：{props.thinkingEnabled ? "开" : "关"}
          </button>
          <button
            className={props.thinkingEnabled ? "pill active" : "pill"}
            type="button"
            disabled={props.sending}
            aria-pressed={props.thinkingEnabled}
            title={props.thinkingEnabled ? "点击切换思考强度" : "点击开启思考模式"}
            onClick={cycleReasoningEffort}
          >
            强度：{props.thinkingEnabled ? activeReasoningEffort : "关闭"}
          </button>
        </div>
        <button className="send-button" type="button" disabled={!props.value.trim() || props.sending} onClick={() => props.onSubmit()}>
          {props.sending ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
        </button>
      </div>
    </div>
  );
}
