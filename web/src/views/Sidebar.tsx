// Extracted from App.tsx during the P7b module split.
import { BarChart3, Bot, Boxes, ClipboardList, History, MessageSquareText, Pencil, Plus, Trash2, X } from "lucide-react";
import type { ConversationSummary } from "../types";
import { View } from "../lib/app";

export function Sidebar(props: {
  conversations: ConversationSummary[];
  currentId: string;
  view: View;
  editingId: string;
  editingTitle: string;
  onClose: () => void;
  onNewConversation: () => void;
  onLoadConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onStartRename: (item: ConversationSummary) => void;
  onRename: (id: string) => void;
  onEditTitle: (title: string) => void;
  onViewChange: (view: View) => void;
}) {
  return (
    <aside className="sidebar">
      <button className="mobile-close" type="button" onClick={props.onClose} aria-label="关闭侧栏">
        <X size={18} />
      </button>
      <div className="brand">
        <div className="brand-mark">
          <span />
          <span />
        </div>
        <div className="brand-text">AIKA</div>
      </div>

      <button className="new-chat" type="button" onClick={props.onNewConversation}>
        <Plus size={19} />
        <span>新对话</span>
      </button>

      <nav className="nav-list" aria-label="主导航">
        <button className={props.view === "chat" ? "active" : ""} type="button" onClick={() => props.onViewChange("chat")}>
          <MessageSquareText size={20} />
          <span>智能问答</span>
        </button>
        <button
          className={props.view === "agents" ? "active" : ""}
          type="button"
          onClick={() => props.onViewChange("agents")}
        >
          <Bot size={20} />
          <span>Agent 任务</span>
        </button>
        <button
          className={props.view === "eval" ? "active" : ""}
          type="button"
          onClick={() => props.onViewChange("eval")}
        >
          <ClipboardList size={20} />
          <span>评测报告</span>
        </button>
        <button
          className={props.view === "overview" ? "active" : ""}
          type="button"
          onClick={() => props.onViewChange("overview")}
        >
          <BarChart3 size={20} />
          <span>数据概览</span>
        </button>
        <button className={props.view === "graph" ? "active" : ""} type="button" onClick={() => props.onViewChange("graph")}>
          <Boxes size={20} />
          <span>产业链图谱</span>
        </button>
      </nav>

      <section className="history-panel">
        <div className="section-title">
          <History size={16} />
          <span>问答历史</span>
        </div>
        <div className="history-list">
          {props.conversations.length === 0 && <div className="empty-history">暂无历史对话</div>}
          {props.conversations.map((item) => (
            <article className={`history-item ${props.currentId === item.id ? "selected" : ""}`} key={item.id}>
              {props.editingId === item.id ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    props.onRename(item.id);
                  }}
                >
                  <input
                    value={props.editingTitle}
                    autoFocus
                    onChange={(event) => props.onEditTitle(event.target.value)}
                    onBlur={() => props.onRename(item.id)}
                  />
                </form>
              ) : (
                <button className="history-open" type="button" onClick={() => props.onLoadConversation(item.id)}>
                  <strong>{item.title}</strong>
                  <span>{item.preview}</span>
                </button>
              )}
              <div className="history-actions">
                <button type="button" onClick={() => props.onStartRename(item)} aria-label="重命名">
                  <Pencil size={14} />
                </button>
                <button type="button" onClick={() => props.onDeleteConversation(item.id)} aria-label="删除">
                  <Trash2 size={14} />
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </aside>
  );
}
