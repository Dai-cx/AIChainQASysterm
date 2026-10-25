import { useEffect, useState } from "react";
import {
  createAgentTask,
  createConversation,
  deleteConversation,
  getAgentTask,
  getConversation,
  getEvalRun,
  getExamples,
  getStatus,
  listAgentTasks,
  listConversations,
  listEvalRuns,
  reviewClaim,
  streamMessage,
  submitFeedback,
  updateConversationTitle
} from "../api";
import { EMPTY_ARRAY, type DetailTab, type View } from "../lib/app";
import {
  createPendingTurn,
  nextProgressItems,
  updateConversationClaimReview,
  updateTurnClaimReview
} from "../lib/conversation";
import type {
  AgentTask,
  AgentTaskSummary,
  AgentTaskType,
  ApiStatus,
  ClaimReviewRequest,
  Conversation,
  ConversationSummary,
  ConversationTurn,
  EvalRun,
  EvalRunSummary,
  FeedbackCreateRequest
} from "../types";

/** All application state and data handlers for the AIKA shell. */
export function useAppState() {
  const [view, setView] = useState<View>("chat");
  const [status, setStatus] = useState<ApiStatus | null>(null);
  const [examples, setExamples] = useState<string[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>(EMPTY_ARRAY);
  const [agentTasks, setAgentTasks] = useState<AgentTaskSummary[]>([]);
  const [selectedAgentTask, setSelectedAgentTask] = useState<AgentTask | null>(null);
  const [evalRuns, setEvalRuns] = useState<EvalRunSummary[]>([]);
  const [selectedEvalRun, setSelectedEvalRun] = useState<EvalRun | null>(null);
  const [agentGoal, setAgentGoal] = useState("");
  const [agentTaskType, setAgentTaskType] = useState<AgentTaskType>("research_brief");
  const [agentRunning, setAgentRunning] = useState(false);
  const [current, setCurrent] = useState<Conversation | null>(null);
  const [input, setInput] = useState("");
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState("low");
  const [sending, setSending] = useState(false);
  const [streamingTurn, setStreamingTurn] = useState<ConversationTurn | null>(null);
  const [streamingProgress, setStreamingProgress] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [selectedTurn, setSelectedTurn] = useState<ConversationTurn | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("research");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [editingTitle, setEditingTitle] = useState("");

  async function refreshConversations() {
    const items = await listConversations();
    setConversations(items);
  }

  async function refreshAgentTasks() {
    const items = await listAgentTasks();
    setAgentTasks(items);
  }

  async function refreshEvalRuns() {
    const items = await listEvalRuns();
    setEvalRuns(items);
    return items;
  }

  async function loadInitial() {
    setLoading(true);
    try {
      const [statusPayload, examplePayload, conversationPayload, agentTaskPayload, evalRunPayload] = await Promise.all([
        getStatus(),
        getExamples(),
        listConversations(),
        listAgentTasks(),
        listEvalRuns()
      ]);
      setStatus(statusPayload);
      setExamples(examplePayload);
      setConversations(conversationPayload);
      setAgentTasks(agentTaskPayload);
      setEvalRuns(evalRunPayload);
      setThinkingEnabled(statusPayload.settings.thinking_enabled);
      setReasoningEffort(statusPayload.settings.reasoning_effort);
      if (conversationPayload.length > 0) {
        const latest = await getConversation(conversationPayload[0].id);
        setCurrent(latest);
      }
      if (agentTaskPayload.length > 0) {
        const latestTask = await getAgentTask(agentTaskPayload[0].task_id);
        setSelectedAgentTask(latestTask);
      }
      if (evalRunPayload.length > 0) {
        const latestRun = await getEvalRun(evalRunPayload[0].run_id);
        setSelectedEvalRun(latestRun);
      }
    } catch (error) {
      setToast(error instanceof Error ? error.message : "加载系统状态失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadInitial();
  }, []);

  async function handleNewConversation() {
    try {
      const conversation = await createConversation();
      setCurrent(conversation);
      setSelectedTurn(null);
      setInput("");
      setStreamingTurn(null);
      setStreamingProgress([]);
      setView("chat");
      setSidebarOpen(false);
      await refreshConversations();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "创建对话失败");
    }
  }

  async function handleLoadConversation(id: string) {
    try {
      const conversation = await getConversation(id);
      setCurrent(conversation);
      setSelectedTurn(null);
      setStreamingTurn(null);
      setStreamingProgress([]);
      setView("chat");
      setSidebarOpen(false);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "读取对话失败");
    }
  }

  async function handleLoadAgentTask(id: string) {
    try {
      const task = await getAgentTask(id);
      setSelectedAgentTask(task);
      setView("agents");
      setSidebarOpen(false);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "读取 Agent 任务失败");
    }
  }

  async function handleLoadEvalRun(id: string) {
    try {
      const run = await getEvalRun(id);
      setSelectedEvalRun(run);
      setView("eval");
      setSidebarOpen(false);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "读取评测报告失败");
    }
  }

  async function handleCreateAgentTask(goal = agentGoal) {
    const trimmed = goal.trim();
    if (!trimmed || agentRunning) return;
    setAgentRunning(true);
    setToast("");
    try {
      const task = await createAgentTask({
        task_type: agentTaskType,
        goal: trimmed,
        thinking_enabled: thinkingEnabled,
        reasoning_effort: thinkingEnabled ? reasoningEffort : ""
      });
      setSelectedAgentTask(task);
      setAgentGoal("");
      setView("agents");
      await refreshAgentTasks();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "创建 Agent 任务失败");
    } finally {
      setAgentRunning(false);
    }
  }

  async function handleDeleteConversation(id: string) {
    if (!window.confirm("删除这段对话？")) return;
    try {
      await deleteConversation(id);
      if (current?.id === id) {
        setCurrent(null);
        setSelectedTurn(null);
      }
      await refreshConversations();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "删除失败");
    }
  }

  async function handleRename(id: string) {
    const title = editingTitle.trim();
    if (!title) {
      setEditingId("");
      return;
    }
    try {
      const updated = await updateConversationTitle(id, title);
      if (current?.id === id) setCurrent(updated);
      setEditingId("");
      await refreshConversations();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "重命名失败");
    }
  }

  async function handleSubmit(question = input) {
    const trimmed = question.trim();
    if (!trimmed || sending) return;
    setSending(true);
    setToast("");
    const submittedThinking = thinkingEnabled;
    const submittedReasoningEffort = submittedThinking ? reasoningEffort : "";
    try {
      let conversation = current;
      if (!conversation) {
        conversation = await createConversation();
        setCurrent(conversation);
      }
      const pendingTurn = createPendingTurn(trimmed, submittedThinking, submittedReasoningEffort);
      setStreamingTurn(pendingTurn);
      setStreamingProgress([]);
      setSelectedTurn(null);
      setInput("");
      setView("chat");
      const updated = await streamMessage(
        conversation.id,
        trimmed,
        submittedThinking,
        submittedReasoningEffort,
        (event) => {
          if (event.type === "progress") {
            setStreamingProgress((items) => nextProgressItems(items, event.message));
          } else if (event.type === "answer_delta") {
            setStreamingTurn((turn) => {
              if (!turn) return turn;
              const answer = `${turn.answer}${event.content}`;
              return {
                ...turn,
                answer,
                result: {
                  ...turn.result,
                  answer
                }
              };
            });
          } else if (event.type === "final") {
            setCurrent(event.conversation);
            setStreamingTurn(null);
            setStreamingProgress([]);
          } else if (event.type === "error") {
            setToast(event.message);
          }
        }
      );
      setCurrent(updated);
      setStreamingTurn(null);
      setStreamingProgress([]);
      await refreshConversations();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "发送失败");
      setStreamingTurn(null);
      setStreamingProgress([]);
    } finally {
      setSending(false);
    }
  }

  async function handleClaimReview(claimId: string, payload: ClaimReviewRequest) {
    try {
      const response = await reviewClaim(claimId, payload);
      setToast("Claim 修正已保存");
      setSelectedTurn((turn) => updateTurnClaimReview(turn, claimId, response.claim));
      setCurrent((conversation) => updateConversationClaimReview(conversation, claimId, response.claim));
    } catch (error) {
      setToast(error instanceof Error ? error.message : "保存 Claim 修正失败");
    }
  }

  async function handleFeedback(payload: FeedbackCreateRequest) {
    try {
      await submitFeedback(payload);
      setToast("反馈已保存");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "保存反馈失败");
    }
  }

  return {
    view,
    setView,
    status,
    examples,
    conversations,
    agentTasks,
    selectedAgentTask,
    evalRuns,
    selectedEvalRun,
    agentGoal,
    setAgentGoal,
    agentTaskType,
    setAgentTaskType,
    agentRunning,
    current,
    input,
    setInput,
    thinkingEnabled,
    setThinkingEnabled,
    reasoningEffort,
    setReasoningEffort,
    sending,
    streamingTurn,
    streamingProgress,
    loading,
    toast,
    setToast,
    selectedTurn,
    setSelectedTurn,
    detailTab,
    setDetailTab,
    sidebarOpen,
    setSidebarOpen,
    editingId,
    setEditingId,
    editingTitle,
    setEditingTitle,
    refreshEvalRuns,
    handleNewConversation,
    handleLoadConversation,
    handleLoadAgentTask,
    handleLoadEvalRun,
    handleCreateAgentTask,
    handleDeleteConversation,
    handleRename,
    handleSubmit,
    handleClaimReview,
    handleFeedback
  };
}
