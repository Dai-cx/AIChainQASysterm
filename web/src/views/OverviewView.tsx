// Extracted from App.tsx during the P7b module split.
import { useMemo } from "react";
import type { ApiStatus } from "../types";

export function OverviewView(props: { status: ApiStatus | null }) {
  const stats = props.status?.stats;
  const researchStats = stats?.research;
  return (
    <section className="page-panel">
      <div className="page-header">
        <span className="eyebrow">Knowledge Base</span>
        <h1>数据概览</h1>
        <p>图谱、RAG、Embedding 和 LLM 状态集中展示，便于演示前快速确认系统健康度。</p>
      </div>
      <div className="metric-grid">
        <MetricCard label="公司" value={stats?.companies ?? 0} />
        <MetricCard label="报告" value={stats?.reports ?? 0} />
        <MetricCard label="实体" value={stats?.entities ?? 0} />
        <MetricCard label="关系" value={stats?.relations ?? 0} />
        <MetricCard label="Claim" value={researchStats?.claims ?? 0} />
        <MetricCard label="Dossier" value={researchStats?.dossiers ?? 0} />
        <MetricCard label="已审校 Claim" value={researchStats?.reviewed_claims ?? 0} />
        <MetricCard label="直接敞口公司" value={researchStats?.direct_exposure_companies ?? 0} />
      </div>
      <div className="status-strip">
        <StatusPill label="图谱后端" value={props.status?.graph_backend?.toUpperCase() ?? "UNKNOWN"} />
        <StatusPill label="Neo4j" value={props.status?.neo4j_enabled ? "可用" : "降级/未启用"} />
        <StatusPill label="本地 RAG" value={props.status?.rag_enabled ? "就绪" : "未构建"} />
        <StatusPill label="投研层" value={props.status?.research_enabled ? "就绪" : "未构建"} />
        <StatusPill label="LLM" value={props.status?.llm_enabled ? "就绪" : "未配置"} />
        <StatusPill label="Embedding" value={props.status?.embedding_enabled ? "就绪" : "未启用"} />
      </div>
      <div className="chart-grid">
        <BarList title="实体分布" data={stats?.entity_counts ?? {}} />
        <BarList title="关系分布" data={stats?.relation_counts ?? {}} />
      </div>
    </section>
  );
}

export function MetricCard(props: { label: string; value: number }) {
  return (
    <div className="metric-card">
      <span>{props.label}</span>
      <strong>{props.value.toLocaleString()}</strong>
    </div>
  );
}

export function StatusPill(props: { label: string; value: string }) {
  return (
    <div className="status-pill">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

export function BarList(props: { title: string; data: Record<string, number> }) {
  const entries = useMemo(() => Object.entries(props.data).sort((a, b) => b[1] - a[1]).slice(0, 10), [props.data]);
  const max = Math.max(...entries.map(([, value]) => value), 1);
  return (
    <div className="bar-card">
      <h3>{props.title}</h3>
      {entries.map(([label, value]) => (
        <div className="bar-row" key={label}>
          <span>{label}</span>
          <div>
            <i style={{ width: `${Math.max((value / max) * 100, 4)}%` }} />
          </div>
          <b>{value}</b>
        </div>
      ))}
    </div>
  );
}
