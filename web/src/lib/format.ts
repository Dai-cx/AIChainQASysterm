// Extracted from App.tsx during the P7b module split.
import type { ConversationTurn } from "../types";

export function formatMetricValue(key: string, value: number | null) {
  if (value === null || value === undefined) return "未评分";
  if (key === "human_score") return `${Number(value).toFixed(1)}/5`;
  return formatPercent(Number(value));
}

export function formatPercent(value: number) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

export function citationIdsFromTurn(turn: ConversationTurn) {
  const rows = turn.result.evidence_cards?.length ? turn.result.evidence_cards : turn.result.evidence;
  return rows.map((row) => String(row.citation_id ?? "")).filter(Boolean);
}

export function hashText(text: string) {
  let hash = 5381;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) + hash) ^ text.charCodeAt(index);
  }
  return (hash >>> 0).toString(16);
}

export function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function splitSvgLabel(value: string, length: number) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= length) return [text];
  const second = text.slice(length, length * 2);
  return [text.slice(0, length), text.length > length * 2 ? `${second}...` : second];
}

export function freshnessLabel(value: string) {
  return { fresh: "新鲜", aging: "较旧", stale: "过期", unknown: "未知" }[value] ?? value;
}

export function clampNumber(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.round(value)));
}

export function flowNodes(links: Array<{ source: string; target: string }>) {
  const sources = Array.from(new Set(links.map((link) => link.source)));
  const targets = Array.from(new Set(links.map((link) => link.target).filter((target) => !sources.includes(target))));
  const nodes = new Map<string, { x: number; y: number }>();
  const sourceStep = 200 / Math.max(sources.length, 1);
  sources.forEach((source, index) => nodes.set(source, { x: 26, y: 40 + sourceStep * index }));
  const targetStep = 200 / Math.max(targets.length, 1);
  targets.forEach((target, index) => nodes.set(target, { x: 596, y: 40 + targetStep * index }));
  if (!targets.length && sources.length) {
    Array.from(new Set(links.map((link) => link.target))).forEach((target, index) => nodes.set(target, { x: 596, y: 40 + targetStep * index }));
  }
  return nodes;
}

export function shortSvgLabel(value: string) {
  const text = String(value || "");
  return text.length > 12 ? `${text.slice(0, 11)}…` : text;
}

export function arrayRecords(value: unknown): Record<string, string>[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (item && typeof item === "object" && !Array.isArray(item)) {
        return Object.fromEntries(Object.entries(item as Record<string, unknown>).map(([key, val]) => [key, String(val ?? "")]));
      }
      return { value: String(item ?? "") };
    })
    .filter((row) => Object.values(row).some(Boolean));
}

export function fieldText(row: Record<string, unknown>, key: string) {
  const value = row[key];
  if (value === null || value === undefined) return "";
  return String(value);
}
