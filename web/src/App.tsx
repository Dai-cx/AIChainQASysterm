import { Menu, X } from "lucide-react";
import { DetailDrawer } from "./components/DetailDrawer";
import { GeometricBackdrop } from "./components/GeometricBackdrop";
import { useAppState } from "./hooks/useAppState";
import { AgentTasksView } from "./views/AgentTasksView";
import { ChatView } from "./views/ChatView";
import { EvalView } from "./views/EvalView";
import { GraphView } from "./views/GraphView";
import { OverviewView } from "./views/OverviewView";
import { Sidebar } from "./views/Sidebar";

/** Application shell: layout chrome plus view routing. */
export default function App() {
  const {
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
  } = useAppState();

  const shellClassName = `app-shell ${sidebarOpen ? "sidebar-open" : ""}`;

  return (
    <div className={shellClassName}>
      <button className="mobile-menu" type="button" onClick={() => setSidebarOpen(true)} aria-label="打开侧栏">
        <Menu size={20} />
      </button>
      <Sidebar
        conversations={conversations}
        currentId={current?.id ?? ""}
        view={view}
        editingId={editingId}
        editingTitle={editingTitle}
        onClose={() => setSidebarOpen(false)}
        onNewConversation={handleNewConversation}
        onLoadConversation={handleLoadConversation}
        onDeleteConversation={handleDeleteConversation}
        onStartRename={(item) => {
          setEditingId(item.id);
          setEditingTitle(item.title);
        }}
        onRename={handleRename}
        onEditTitle={setEditingTitle}
        onViewChange={(nextView) => {
          setView(nextView);
          setSidebarOpen(false);
        }}
      />
      <main className="workspace">
        <GeometricBackdrop />
        {toast && (
          <div className="toast" role="alert">
            <span>{toast}</span>
            <button type="button" onClick={() => setToast("")} aria-label="关闭提示">
              <X size={16} />
            </button>
          </div>
        )}
        {view === "chat" && (
          <ChatView
            loading={loading}
            conversation={current}
            examples={examples}
            input={input}
            sending={sending}
            streamingTurn={streamingTurn}
            streamingProgress={streamingProgress}
            thinkingEnabled={thinkingEnabled}
            reasoningEffort={reasoningEffort}
            reasoningEfforts={status?.settings.reasoning_efforts ?? ["low", "medium", "high"]}
            onInput={setInput}
            onSubmit={handleSubmit}
            onThinkingChange={setThinkingEnabled}
            onReasoningChange={setReasoningEffort}
            onOpenDetails={(turn) => {
              setSelectedTurn(turn);
              setDetailTab("research");
            }}
            onFeedback={handleFeedback}
            onExample={(example) => setInput(example)}
          />
        )}
        {view === "agents" && (
          <AgentTasksView
            tasks={agentTasks}
            selectedTask={selectedAgentTask}
            goal={agentGoal}
            taskType={agentTaskType}
            running={agentRunning}
            thinkingEnabled={thinkingEnabled}
            reasoningEffort={reasoningEffort}
            reasoningEfforts={status?.settings.reasoning_efforts ?? ["low", "medium", "high"]}
            onGoal={setAgentGoal}
            onTaskType={setAgentTaskType}
            onCreate={handleCreateAgentTask}
            onSelectTask={handleLoadAgentTask}
            onThinkingChange={setThinkingEnabled}
            onReasoningChange={setReasoningEffort}
          />
        )}
        {view === "eval" && (
          <EvalView
            runs={evalRuns}
            selectedRun={selectedEvalRun}
            onSelectRun={handleLoadEvalRun}
            onRefresh={refreshEvalRuns}
          />
        )}
        {view === "overview" && <OverviewView status={status} />}
        {view === "graph" && <GraphView />}
      </main>
      <DetailDrawer
        turn={selectedTurn}
        open={Boolean(selectedTurn) && view === "chat"}
        tab={detailTab}
        onTab={setDetailTab}
        onClose={() => setSelectedTurn(null)}
        onClaimReview={handleClaimReview}
      />
    </div>
  );
}
