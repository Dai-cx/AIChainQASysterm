// Extracted from App.tsx during the P7b module split.
import type { GraphEdge } from "../types";
import { clamp } from "../lib/format";
import { entityOrderIndex, entityStyle, zhCollator } from "../lib/labels";

export const GRAPH_VIEWPORTS = {
  large: { width: 1040, height: 560 },
  compact: { width: 640, height: 360 }
} as const;

export type GraphVariant = keyof typeof GRAPH_VIEWPORTS;

export type GraphTransform = {
  x: number;
  y: number;
  scale: number;
};

export type GraphNodeLayout = {
  id: string;
  type: string;
  degree: number;
  sourceCount: number;
  targetCount: number;
  x: number;
  y: number;
  r: number;
  lane: string;
};

export type GraphColumnLayout = {
  id: string;
  label: string;
  type: string;
  x: number;
  count: number;
};

export type GraphLayoutEdge = GraphEdge & {
  key: string;
};

export type GraphLayout = {
  width: number;
  height: number;
  nodes: GraphNodeLayout[];
  edges: GraphLayoutEdge[];
  columns: GraphColumnLayout[];
  legendTypes: string[];
  showEdgeLabels: boolean;
};

export function graphEdgeKey(edge: GraphEdge, index: number) {
  return `${edge.source}-${edge.label}-${edge.target}-${index}`;
}

export function createGraphLayout(edges: GraphEdge[], variant: GraphVariant): GraphLayout {
  const compact = variant === "compact";
  const viewport = GRAPH_VIEWPORTS[variant];
  const visibleEdges = edges
    .filter((edge) => edge.source?.trim() && edge.target?.trim())
    .slice(0, compact ? 70 : 140)
    .map((edge, index) => ({ ...edge, key: graphEdgeKey(edge, index) }));
  const nodeMap = new Map<string, GraphNodeLayout>();

  function ensureNode(id: string, entityType: string) {
    let node = nodeMap.get(id);
    if (!node) {
      node = {
        id,
        type: entityType,
        degree: 0,
        sourceCount: 0,
        targetCount: 0,
        x: 0,
        y: 0,
        r: compact ? 9 : 11,
        lane: ""
      };
      nodeMap.set(id, node);
    } else if (!node.type && entityType) {
      node.type = entityType;
    }
    return node;
  }

  visibleEdges.forEach((edge) => {
    const source = ensureNode(edge.source, edge.source_type);
    const target = ensureNode(edge.target, edge.target_type);
    source.degree += 1;
    source.sourceCount += 1;
    target.degree += 1;
    target.targetCount += 1;
  });

  const nodes = Array.from(nodeMap.values());
  nodes.forEach((node) => {
    node.r = clamp((compact ? 7 : 8) + Math.sqrt(node.degree) * (compact ? 1.9 : 2.2), compact ? 8 : 9, compact ? 15 : 18);
  });

  function sortNodes(a: GraphNodeLayout, b: GraphNodeLayout) {
    return (
      entityOrderIndex(a.type) - entityOrderIndex(b.type) ||
      b.degree - a.degree ||
      zhCollator.compare(a.id, b.id)
    );
  }

  let sourceNodes = nodes
    .filter((node) => node.type === "Company" || (node.sourceCount > 0 && node.sourceCount >= node.targetCount))
    .sort(sortNodes);
  if (!sourceNodes.length) {
    sourceNodes = nodes.filter((node) => node.sourceCount > 0).sort(sortNodes);
  }
  const sourceSet = new Set(sourceNodes.map((node) => node.id));
  const targetGroups = new Map<string, GraphNodeLayout[]>();
  nodes
    .filter((node) => !sourceSet.has(node.id))
    .sort(sortNodes)
    .forEach((node) => {
      const key = node.type || "Entity";
      const group = targetGroups.get(key) ?? [];
      group.push(node);
      targetGroups.set(key, group);
    });

  const columns: Array<{ id: string; label: string; type: string; nodes: GraphNodeLayout[] }> = [];
  const maxRowsPerColumn = compact ? 12 : 24;

  function pushColumns(id: string, label: string, type: string, columnNodes: GraphNodeLayout[]) {
    for (let start = 0; start < columnNodes.length; start += maxRowsPerColumn) {
      const chunk = columnNodes.slice(start, start + maxRowsPerColumn);
      const suffix = columnNodes.length > maxRowsPerColumn ? ` ${Math.floor(start / maxRowsPerColumn) + 1}` : "";
      columns.push({ id: `${id}-${start}`, label: `${label}${suffix}`, type, nodes: chunk });
    }
  }

  if (sourceNodes.length) {
    pushColumns("source", "起点", "", sourceNodes);
  }
  Array.from(targetGroups.entries())
    .sort(([a], [b]) => entityOrderIndex(a) - entityOrderIndex(b) || zhCollator.compare(entityStyle(a).label, entityStyle(b).label))
    .forEach(([type, group]) => {
      pushColumns(type, entityStyle(type).label, type, group);
    });
  if (!columns.length && nodes.length) {
    columns.push({ id: "entities", label: "实体", type: "", nodes });
  }

  const nodeGap = compact ? 46 : 54;
  const columnGap = compact ? 214 : 282;
  const leftPadding = compact ? 64 : 88;
  const topPadding = compact ? 58 : 68;
  const rightPadding = compact ? 188 : 240;
  const bottomPadding = compact ? 72 : 88;
  const maxRows = Math.max(...columns.map((column) => column.nodes.length), 1);
  const width = Math.max(viewport.width, leftPadding + Math.max(columns.length - 1, 0) * columnGap + rightPadding);
  const height = Math.max(viewport.height, topPadding + Math.max(maxRows - 1, 0) * nodeGap + bottomPadding);
  const columnLayouts: GraphColumnLayout[] = [];

  columns.forEach((column, columnIndex) => {
    const x = leftPadding + columnIndex * columnGap;
    columnLayouts.push({ id: column.id, label: column.label, type: column.type, x, count: column.nodes.length });
    column.nodes.forEach((node, nodeIndex) => {
      node.x = x;
      node.y = topPadding + nodeIndex * nodeGap;
      node.lane = column.id;
    });
  });

  return {
    width,
    height,
    nodes,
    edges: visibleEdges,
    columns: columnLayouts,
    legendTypes: Array.from(new Set(nodes.map((node) => node.type))).sort((a, b) => entityOrderIndex(a) - entityOrderIndex(b)),
    showEdgeLabels: visibleEdges.length <= (compact ? 10 : 18) && nodes.length <= (compact ? 22 : 34)
  };
}

export function fitGraphTransform(layout: GraphLayout, viewport: { width: number; height: number }): GraphTransform {
  if (!layout.nodes.length) return { x: 0, y: 0, scale: 1 };
  const padding = 42;
  const scale = Math.min(
    (viewport.width - padding * 2) / Math.max(layout.width, 1),
    (viewport.height - padding * 2) / Math.max(layout.height, 1),
    1.18
  );
  const safeScale = clamp(scale, 0.08, 1.18);
  return {
    x: (viewport.width - layout.width * safeScale) / 2,
    y: (viewport.height - layout.height * safeScale) / 2,
    scale: safeScale
  };
}

export function graphPath(source: GraphNodeLayout, target: GraphNodeLayout, index: number) {
  const direction = target.x >= source.x ? 1 : -1;
  const startX = source.x + source.r * direction;
  const endX = target.x - target.r * direction;
  const startY = source.y;
  const endY = target.y;
  const offset = ((index % 9) - 4) * 3.5;
  if (Math.abs(endX - startX) < 28) {
    const loop = 44 + (index % 5) * 10;
    return `M ${startX.toFixed(1)} ${startY.toFixed(1)} C ${(startX + loop).toFixed(1)} ${(startY - 22).toFixed(1)}, ${(endX + loop).toFixed(1)} ${(endY + 22).toFixed(1)}, ${endX.toFixed(1)} ${endY.toFixed(1)}`;
  }
  const curve = Math.max(72, Math.abs(endX - startX) * 0.42);
  return `M ${startX.toFixed(1)} ${startY.toFixed(1)} C ${(startX + curve * direction).toFixed(1)} ${(startY + offset).toFixed(1)}, ${(endX - curve * direction).toFixed(1)} ${(endY - offset).toFixed(1)}, ${endX.toFixed(1)} ${endY.toFixed(1)}`;
}

export function edgeLabelPoint(source: GraphNodeLayout, target: GraphNodeLayout, index: number) {
  return {
    x: (source.x + target.x) / 2,
    y: (source.y + target.y) / 2 - 7 + ((index % 5) - 2) * 4
  };
}
