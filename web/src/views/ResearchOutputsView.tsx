// Extracted from App.tsx during the P7b module split.
import { BarChart3, Boxes, ClipboardList, FileText, Table2 } from "lucide-react";
import type { ReportCharts, ResearchOutputs } from "../types";
import { CompanyHeatmapChart } from "../evidence/CompanyHeatmapChart";
import { EvidenceStrengthChart } from "../evidence/EvidenceStrengthChart";
import { FlowMapChartView } from "../evidence/FlowMapChart";
import { FreshnessTimelineChartView } from "../evidence/FreshnessTimelineChart";
import { arrayRecords } from "../lib/format";
import { renderAnswerMarkdown } from "../lib/markdown";

export function ResearchOutputsView(props: { outputs?: ResearchOutputs }) {
  const outputs = props.outputs;
  if (!outputs) return <div className="empty-table">当前回答没有生成投研产物</div>;
  const report = outputs.report;
  const charts = report?.spec?.charts;
  const table = outputs.company_compare_table;
  const risks = outputs.risk_checklist ?? [];
  const gaps = outputs.evidence_gaps ?? [];
  return (
    <div className="research-output">
      <TaskOutputsView outputs={outputs.task_outputs} />
      <ReportChartsView charts={charts} />
      <section className="research-section">
        <div className="research-section-title">
          <FileText size={16} />
          <span>{report?.title || "投研简报"}</span>
        </div>
        <div className="research-report">
          {report?.sections?.length ? (
            report.sections.map((section) => (
              <div className="research-report-section" key={section.title}>
                <h4>{section.title}</h4>
                <div>{renderAnswerMarkdown(section.content)}</div>
              </div>
            ))
          ) : (
            <div className="empty-table">当前证据不足以生成报告</div>
          )}
        </div>
      </section>
      <section className="research-section">
        <div className="research-section-title">
          <Table2 size={16} />
          <span>公司对比表</span>
        </div>
        <ResearchTable rows={table?.rows ?? []} empty="当前证据不足以生成公司对比表" />
      </section>
      <section className="research-section">
        <div className="research-section-title">
          <ClipboardList size={16} />
          <span>风险清单</span>
        </div>
        <ResearchList rows={risks} primaryKey="risk" secondaryKeys={["scope", "priority", "follow_up", "citation_id"]} empty="当前证据不足以生成风险清单" />
      </section>
      <section className="research-section">
        <div className="research-section-title">
          <FileText size={16} />
          <span>证据缺口</span>
        </div>
        <ResearchList rows={gaps} primaryKey="gap" secondaryKeys={["priority", "suggested_source"]} empty="当前证据包未识别出关键缺口" />
      </section>
    </div>
  );
}

export function ReportChartsView(props: { charts?: ReportCharts }) {
  const charts = props.charts;
  if (!charts) return null;
  const hasChartData =
    Boolean(charts.company_coverage_heatmap?.cells?.length) ||
    Boolean(charts.evidence_strength_bar?.counts && Object.values(charts.evidence_strength_bar.counts).some(Boolean)) ||
    Boolean(charts.flow_map?.links?.length) ||
    Boolean(charts.source_freshness_timeline?.items?.length);
  if (!hasChartData) return null;
  return (
    <section className="research-section report-chart-section">
      <div className="research-section-title">
        <BarChart3 size={16} />
        <span>证据覆盖图表</span>
      </div>
      <div className="report-chart-grid">
        <EvidenceStrengthChart chart={charts.evidence_strength_bar} />
        <FreshnessTimelineChartView chart={charts.source_freshness_timeline} />
        <CompanyHeatmapChart chart={charts.company_coverage_heatmap} />
        <FlowMapChartView chart={charts.flow_map} />
      </div>
    </section>
  );
}

export function TaskOutputsView(props: { outputs?: Record<string, unknown> }) {
  const outputs = props.outputs;
  if (!outputs) return null;
  const schemaType = String(outputs.schema_type ?? "");
  const taskLabel = String(outputs.task_label ?? schemaType);
  const cards = taskOutputCards(outputs);
  if (!cards.length) return null;
  return (
    <section className="research-section task-output-section">
      <div className="research-section-title">
        <Boxes size={16} />
        <span>{taskLabel || "任务结构化输出"}</span>
      </div>
      <div className="task-output-grid">
        {cards.map((card) => (
          <article className="task-output-card" key={card.title}>
            <strong>{card.title}</strong>
            <ResearchList rows={card.rows} primaryKey={card.primaryKey} secondaryKeys={card.secondaryKeys} empty="当前证据不足" />
          </article>
        ))}
      </div>
    </section>
  );
}

export function taskOutputCards(outputs: Record<string, unknown>) {
  const specs = [
    { key: "common_drivers", title: "共同驱动", primaryKey: "evidence", secondaryKeys: ["scope", "citation_id"] },
    { key: "differences", title: "差异点", primaryKey: "business_position", secondaryKeys: ["company", "leading_indicators", "citations"] },
    { key: "risk_differences", title: "风险差异", primaryKey: "risks", secondaryKeys: ["company", "citations"] },
    { key: "technology_products", title: "产品/技术", primaryKey: "evidence", secondaryKeys: ["scope", "citation_id"] },
    { key: "indicators", title: "指标证据", primaryKey: "evidence", secondaryKeys: ["scope", "citation_id"] },
    { key: "counter_evidence", title: "反证/边界", primaryKey: "evidence", secondaryKeys: ["scope", "citation_id"] },
    { key: "follow_up_indicators", title: "跟踪指标", primaryKey: "indicator", secondaryKeys: ["scope", "citation_id"] },
    { key: "missing_companies", title: "缺失公司证据", primaryKey: "gap", secondaryKeys: ["priority", "suggested_source"] },
    { key: "missing_metrics", title: "缺失指标证据", primaryKey: "gap", secondaryKeys: ["priority", "suggested_source"] },
    { key: "missing_risks", title: "缺失风险证据", primaryKey: "gap", secondaryKeys: ["priority", "suggested_source"] },
    { key: "evidence_index", title: "证据索引", primaryKey: "title", secondaryKeys: ["citation_id", "source", "page"] }
  ];
  return specs
    .map((spec) => ({
      ...spec,
      rows: arrayRecords(outputs[spec.key])
    }))
    .filter((item) => item.rows.length > 0)
    .slice(0, 4);
}

export function ResearchTable(props: { rows: Record<string, string>[]; empty: string }) {
  if (!props.rows.length) return <div className="empty-table">{props.empty}</div>;
  return (
    <div className="research-table">
      {props.rows.slice(0, 10).map((row) => (
        <article className="research-row" key={row.company}>
          <div>
            <strong>{row.company || "公司"}</strong>
            <span>{row.chain_segment || "未识别"} · {row.exposure_level || "未分级"}</span>
          </div>
          <p>{row.business_evidence || "当前证据不足"}</p>
          <dl>
            <dt>指标</dt>
            <dd>{row.leading_indicators || "当前证据不足"}</dd>
            <dt>风险</dt>
            <dd>{row.risks || "当前证据不足"}</dd>
            <dt>证据</dt>
            <dd>{row.citations || "无"}</dd>
          </dl>
        </article>
      ))}
    </div>
  );
}

export function ResearchList(props: {
  rows: Record<string, string>[];
  primaryKey: string;
  secondaryKeys: string[];
  empty: string;
}) {
  if (!props.rows.length) return <div className="empty-table">{props.empty}</div>;
  return (
    <div className="research-list">
      {props.rows.slice(0, 12).map((row, index) => (
        <article className="research-list-item" key={`${row[props.primaryKey]}-${index}`}>
          <p>{row[props.primaryKey]}</p>
          <div>
            {props.secondaryKeys.map((key) => (
              row[key] ? <span key={key}>{row[key]}</span> : null
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}
