// Extracted from App.tsx during the P7b module split.
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { GraphSubgraph, GraphSummary } from "../types";
import { getGraphSubgraph, getGraphSummary } from "../api";
import { DataTable } from "../components/DataTable";
import { GraphCanvas } from "../graph/GraphCanvas";

export function GraphView() {
  const [summary, setSummary] = useState<GraphSummary | null>(null);
  const [subgraph, setSubgraph] = useState<GraphSubgraph | null>(null);
  const [company, setCompany] = useState("");
  const [technology, setTechnology] = useState("");
  const [relation, setRelation] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadSummary() {
      try {
        const payload = await getGraphSummary();
        setSummary(payload);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载图谱摘要失败");
      }
    }
    void loadSummary();
  }, []);

  useEffect(() => {
    async function loadSubgraph() {
      setLoading(true);
      setError("");
      try {
        const payload = await getGraphSubgraph({ company, technology, relation_type: relation });
        setSubgraph(payload);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载子图失败");
      } finally {
        setLoading(false);
      }
    }
    void loadSubgraph();
  }, [company, technology, relation]);

  const relationEntries = Object.entries(summary?.relation_options ?? {});

  return (
    <section className="page-panel graph-page">
      <div className="page-header">
        <span className="eyebrow">Industry Graph</span>
        <h1>产业链图谱</h1>
        <p>按公司、技术或关系筛选局部图谱，用于解释答案背后的结构化证据。</p>
      </div>
      <div className="filter-row">
        <label>
          公司
          <select value={company} onChange={(event) => setCompany(event.target.value)}>
            <option value="">全部公司</option>
            {summary?.companies_options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          技术
          <select value={technology} onChange={(event) => setTechnology(event.target.value)}>
            <option value="">全部技术</option>
            {summary?.technologies_options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          关系
          <select value={relation} onChange={(event) => setRelation(event.target.value)}>
            {relationEntries.length === 0 && <option value="">全部关系</option>}
            {relationEntries.map(([label, value]) => (
              <option key={label} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <div className="warning">{error}</div>}
      <div className="graph-surface">
        {loading ? (
          <div className="center-loading">
            <Loader2 size={18} className="spin" />
            <span>加载图谱中</span>
          </div>
        ) : (
          <GraphCanvas edges={subgraph?.edges ?? []} empty="当前筛选条件下没有可展示的子图" />
        )}
      </div>
      <DataTable rows={subgraph?.rows ?? []} empty="当前筛选条件下没有关系" />
    </section>
  );
}
