// Extracted from App.tsx during the P7b module split.
import { Bot, ChevronRight, ClipboardList, Download, FileText, Loader2, Sparkles } from "lucide-react";
import { FormEvent } from "react";
import type { AgentTask, AgentTaskSummary, AgentTaskType } from "../types";
import { exportAgentTaskUrl } from "../api";
import { AGENT_TASK_TYPES, agentStatusLabel, agentTaskTypeLabel } from "../lib/labels";
import { ResearchOutputsView } from "./ResearchOutputsView";
import { StatCard } from "../components/StatCard";
import { VerificationPanel } from "../components/VerificationPanel";
import { renderAnswerMarkdown } from "../lib/markdown";
import { verificationFromTask, verificationStatusLabel } from "../lib/verification";

export function AgentTasksView(props: {
  tasks: AgentTaskSummary[];
  selectedTask: AgentTask | null;
  goal: string;
  taskType: AgentTaskType;
  running: boolean;
  thinkingEnabled: boolean;
  reasoningEffort: string;
  reasoningEfforts: string[];
  onGoal: (value: string) => void;
  onTaskType: (value: AgentTaskType) => void;
  onCreate: (goal?: string) => void;
  onSelectTask: (id: string) => void;
  onThinkingChange: (value: boolean) => void;
  onReasoningChange: (value: string) => void;
}) {
  const reasoningEfforts = props.reasoningEfforts.length ? props.reasoningEfforts : ["low", "medium", "high"];
  const activeReasoningEffort = reasoningEfforts.includes(props.reasoningEffort)
    ? props.reasoningEffort
    : reasoningEfforts[0];
  const task = props.selectedTask;

  function submit(event: FormEvent) {
    event.preventDefault();
    props.onCreate();
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
    props.onReasoningChange(reasoningEfforts[(currentIndex + 1) % reasoningEfforts.length]);
  }

  return (
    <section className="page-panel agent-page">
      <div className="page-heading">
        <span className="eyebrow">Agent Workspace</span>
        <h2>投研任务工作台</h2>
      </div>
      <div className="agent-layout">
        <aside className="agent-list-panel">
          <form className="agent-create" onSubmit={submit}>
            <label htmlFor="agent-task-type">任务类型</label>
            <select
              id="agent-task-type"
              value={props.taskType}
              disabled={props.running}
              onChange={(event) => props.onTaskType(event.target.value as AgentTaskType)}
            >
              {AGENT_TASK_TYPES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            <p className="agent-task-type-hint">
              {AGENT_TASK_TYPES.find((item) => item.value === props.taskType)?.description}
            </p>
            <label htmlFor="agent-goal">研究目标</label>
            <textarea
              id="agent-goal"
              value={props.goal}
              rows={5}
              placeholder="例如：液冷产业链投研简报"
              onChange={(event) => props.onGoal(event.target.value)}
            />
            <div className="agent-controls">
              <button
                className={props.thinkingEnabled ? "pill active" : "pill"}
                type="button"
                disabled={props.running}
                onClick={toggleThinking}
              >
                思考模式：{props.thinkingEnabled ? "开" : "关"}
              </button>
              <button
                className={props.thinkingEnabled ? "pill active" : "pill"}
                type="button"
                disabled={props.running}
                onClick={cycleReasoningEffort}
              >
                强度：{props.thinkingEnabled ? activeReasoningEffort : "关闭"}
              </button>
            </div>
            <button className="agent-run-button" type="submit" disabled={!props.goal.trim() || props.running}>
              {props.running ? <Loader2 size={17} className="spin" /> : <Sparkles size={17} />}
              <span>创建{agentTaskTypeLabel(props.taskType)}任务</span>
            </button>
          </form>

          <div className="agent-task-list">
            <div className="section-title">
              <ClipboardList size={16} />
              <span>任务历史</span>
            </div>
            {props.tasks.length === 0 && <div className="empty-table">暂无 Agent 任务</div>}
            {props.tasks.map((item) => (
              <button
                className={`agent-task-item ${task?.task_id === item.task_id ? "selected" : ""}`}
                key={item.task_id}
                type="button"
                onClick={() => props.onSelectTask(item.task_id)}
              >
                <strong>{item.title}</strong>
                <span>{item.preview || item.goal}</span>
                <em>{agentStatusLabel(item.status)} · {item.evidence_card_count} 证据 · {item.evidence_gap_count} 缺口</em>
              </button>
            ))}
          </div>
        </aside>

        <div className="agent-detail-panel">
          {!task ? (
            <div className="agent-empty">
              <Bot size={34} />
              <span>选择一个历史任务，或创建新的投研简报任务</span>
            </div>
          ) : (
            <>
              <div className="agent-detail-header">
                <div>
                  <span className={`task-status ${task.status}`}>{agentStatusLabel(task.status)}</span>
                  <span className="task-type-label">{task.final_outputs.task_label || agentTaskTypeLabel(task.task_type as AgentTaskType)}</span>
                  <h3>{task.final_outputs.report_title || task.title}</h3>
                  <p>{task.goal}</p>
                </div>
                <div className="export-group">
                  <a className="export-link" href={exportAgentTaskUrl(task.task_id, "md")}>
                    <Download size={16} />
                    <span>MD</span>
                  </a>
                  <a className="export-link" href={exportAgentTaskUrl(task.task_id, "json")}>
                    <Download size={16} />
                    <span>JSON</span>
                  </a>
                </div>
              </div>

              <div className="agent-stat-grid">
                <StatCard label="证据卡" value={String(task.final_outputs.evidence_card_count ?? task.evidence_cards.length)} />
                <StatCard label="证据缺口" value={String(task.final_outputs.evidence_gap_count ?? 0)} />
                <StatCard label="验证状态" value={verificationStatusLabel(task.final_outputs.verification_status)} />
                <StatCard label="冲突证据" value={String(task.final_outputs.conflict_group_count ?? 0)} />
                <StatCard label="执行步骤" value={String(task.steps.length)} />
                <StatCard label="工具调用" value={String(task.tool_calls.length)} />
              </div>

              <VerificationPanel verification={verificationFromTask(task)} />

              <ResearchOutputsView outputs={task.research_outputs} />

              <section className="agent-section">
                <div className="research-section-title">
                  <ClipboardList size={16} />
                  <span>执行轨迹</span>
                </div>
                <div className="agent-step-list">
                  {task.steps.map((step, index) => (
                    <article className="agent-step" key={`${step.phase ?? "step"}-${index}`}>
                      <span>{String(step.step ?? index + 1)}</span>
                      <div>
                        <strong>{String(step.phase ?? "step")}</strong>
                        <p>{String(step.observation ?? step.thought ?? "")}</p>
                      </div>
                      <ChevronRight size={16} />
                    </article>
                  ))}
                </div>
              </section>

              <section className="agent-section">
                <div className="research-section-title">
                  <FileText size={16} />
                  <span>QA 答案摘要</span>
                </div>
                <div className="answer-text">
                  {renderAnswerMarkdown(task.final_outputs.qa_answer || "当前任务没有生成问答摘要")}
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
