// Extracted from App.tsx during the P7b module split.
import type { AgentTask, AgentTaskType } from "../types";

// Entity types mirrored from aika/frontend_data.py (ENTITY_ORDER / ENTITY_COLORS).
export const ENTITY_ORDER: string[] = [
  "Company",
  "IndustryChain",
  "ValueChainSegment",
  "IndustryConcept",
  "Technology",
  "Product",
  "Metric",
  "Risk",
  "Workload",
  "Architecture",
  "Bottleneck",
  "LeadingIndicator",
  "DemandDriver",
  "SupplyConstraint",
  "CompanyExposure",
  "Policy",
  "Standard",
  "Report"
];
export const ENTITY_STYLES: Record<string, { label: string; color: string }> = {
  Company: { label: "公司", color: "#1f6f70" },
  IndustryChain: { label: "产业链", color: "#b86519" },
  ValueChainSegment: { label: "环节", color: "#c2410c" },
  IndustryConcept: { label: "概念", color: "#0e7490" },
  Technology: { label: "技术", color: "#2563eb" },
  Product: { label: "产品", color: "#7a4cc2" },
  Metric: { label: "指标", color: "#477148" },
  Risk: { label: "风险", color: "#c43c39" },
  Workload: { label: "负载", color: "#0369a1" },
  Architecture: { label: "架构", color: "#4f46e5" },
  Bottleneck: { label: "瓶颈", color: "#b91c1c" },
  LeadingIndicator: { label: "领先指标", color: "#15803d" },
  DemandDriver: { label: "需求驱动", color: "#a16207" },
  SupplyConstraint: { label: "供给约束", color: "#be123c" },
  CompanyExposure: { label: "公司敞口", color: "#0f766e" },
  Policy: { label: "政策", color: "#4f5f9f" },
  Standard: { label: "标准", color: "#8a4f9f" },
  Report: { label: "报告", color: "#64748b" }
};
export const FALLBACK_ENTITY_STYLE = { label: "实体", color: "#334155" };
export const zhCollator = new Intl.Collator("zh-Hans-CN");

export const AGENT_TASK_TYPES: Array<{ value: AgentTaskType; label: string; description: string }> = [
  { value: "research_brief", label: "投研简报", description: "主题研究、公司排序、指标、风险与缺口" },
  { value: "company_compare", label: "公司对比", description: "业务卡位、差异点、指标和风险差异" },
  { value: "company_profile", label: "公司画像", description: "公司业务、产品技术、产业链位置和风险" },
  { value: "risk_review", label: "风险审查", description: "主要风险、反证、不确定性和跟踪指标" },
  { value: "evidence_gap_audit", label: "证据缺口", description: "缺失公司、指标、风险和建议数据源" }
];

export function metricLabel(key: string) {
  const labels: Record<string, string> = {
    "claim_recall@k": "Claim Recall",
    "evidence_precision@k": "Evidence Precision",
    citation_validity: "Citation Validity",
    answer_groundedness: "Groundedness",
    unsupported_claim_rate: "Unsupported Rate",
    human_score: "Human Score"
  };
  return labels[key] ?? key;
}

export function categoryLabel(category: string) {
  const labels: Record<string, string> = {
    company_compare: "公司对比",
    supply_chain: "产业传导",
    risk: "风险/反证",
    metric: "指标",
    refusal: "拒答"
  };
  return labels[category] ?? category;
}

export function agentStatusLabel(status: AgentTask["status"]) {
  const labels = {
    pending: "等待中",
    running: "执行中",
    completed: "已完成",
    failed: "失败"
  };
  return labels[status] ?? status;
}

export function agentTaskTypeLabel(taskType: AgentTaskType | string) {
  return AGENT_TASK_TYPES.find((item) => item.value === taskType)?.label ?? String(taskType || "Agent");
}

export function entityStyle(entityType: string) {
  return ENTITY_STYLES[entityType] ?? FALLBACK_ENTITY_STYLE;
}

export function entityOrderIndex(entityType: string) {
  const index = ENTITY_ORDER.indexOf(entityType);
  return index >= 0 ? index : ENTITY_ORDER.length;
}

export const CONFLICT_TYPE_LABELS: Record<string, string> = {
  optimistic_vs_risk: "乐观判断 vs 风险披露",
  old_vs_new: "新旧证据冲突",
  exposure_level_conflict: "敞口等级冲突",
  technical_route_conflict: "技术路线冲突"
};

export const EVIDENCE_KIND_LABELS: Record<string, string> = {
  dossier: "Dossier",
  claim: "Claim",
  graph: "Graph",
  rag: "RAG"
};

export const CLAIM_TYPE_LABELS: Record<string, string> = {
  company_exposure: "公司敞口",
  mechanism: "技术机理",
  bottleneck: "瓶颈",
  indicator: "领先指标",
  risk: "风险",
  supply_chain: "产业传导",
  trend: "趋势",
  policy: "政策"
};

export const EXPOSURE_LABELS: Record<string, string> = {
  core: "核心敞口",
  direct: "直接敞口",
  indirect: "间接敞口",
  mentioned: "仅提及"
};

export const CLAIM_REVIEW_STATUSES = [
  ["revised", "已修正"],
  ["approved", "已确认"],
  ["needs_review", "待复核"],
  ["rejected", "噪声/弃用"]
];
