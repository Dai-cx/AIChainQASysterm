// Extracted from App.tsx during the P7b module split.
import { Maximize2, Move, ZoomIn, ZoomOut } from "lucide-react";
import { PointerEvent, WheelEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import type { GraphEdge } from "../types";
import {
  GRAPH_VIEWPORTS,
  GraphTransform,
  GraphVariant,
  createGraphLayout,
  edgeLabelPoint,
  fitGraphTransform,
  graphPath
} from "./layout";
import { clamp, splitSvgLabel } from "../lib/format";
import { entityStyle } from "../lib/labels";

export function GraphCanvas(props: { edges: GraphEdge[]; variant?: GraphVariant; empty: string }) {
  const variant = props.variant ?? "large";
  const viewport = GRAPH_VIEWPORTS[variant];
  const layout = useMemo(() => createGraphLayout(props.edges, variant), [props.edges, variant]);
  const [transform, setTransform] = useState<GraphTransform>({ x: 0, y: 0, scale: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    unitX: number;
    unitY: number;
  } | null>(null);
  const reactId = useId();
  const arrowId = useMemo(() => `graph-arrow-${reactId.replace(/:/g, "")}`, [reactId]);
  const nodeById = useMemo(() => new Map(layout.nodes.map((node) => [node.id, node])), [layout.nodes]);

  useEffect(() => {
    setTransform(fitGraphTransform(layout, viewport));
  }, [layout, viewport.height, viewport.width]);

  if (!layout.edges.length) return <div className="empty-table">{props.empty}</div>;

  function zoomAt(point: { x: number; y: number }, scale: number) {
    setTransform((current) => {
      const nextScale = clamp(scale, 0.08, 4.5);
      const localX = (point.x - current.x) / current.scale;
      const localY = (point.y - current.y) / current.scale;
      return {
        scale: nextScale,
        x: point.x - localX * nextScale,
        y: point.y - localY * nextScale
      };
    });
  }

  function zoomBy(factor: number) {
    setTransform((current) => {
      const point = { x: viewport.width / 2, y: viewport.height / 2 };
      const nextScale = clamp(current.scale * factor, 0.08, 4.5);
      const localX = (point.x - current.x) / current.scale;
      const localY = (point.y - current.y) / current.scale;
      return {
        scale: nextScale,
        x: point.x - localX * nextScale,
        y: point.y - localY * nextScale
      };
    });
  }

  function fitGraph() {
    setTransform(fitGraphTransform(layout, viewport));
  }

  function eventPoint(event: WheelEvent<SVGSVGElement> | PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * viewport.width,
      y: ((event.clientY - rect.top) / rect.height) * viewport.height
    };
  }

  function onWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.16 : 0.86;
    zoomAt(eventPoint(event), transform.scale * factor);
  }

  function onPointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: transform.x,
      originY: transform.y,
      unitX: viewport.width / rect.width,
      unitY: viewport.height / rect.height
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setIsPanning(true);
  }

  function onPointerMove(event: PointerEvent<SVGSVGElement>) {
    const drag = dragRef.current;
    if (!drag) return;
    setTransform((current) => ({
      ...current,
      x: drag.originX + (event.clientX - drag.startX) * drag.unitX,
      y: drag.originY + (event.clientY - drag.startY) * drag.unitY
    }));
  }

  function stopPanning(event: PointerEvent<SVGSVGElement>) {
    const drag = dragRef.current;
    if (!drag) return;
    if (event.currentTarget.hasPointerCapture(drag.pointerId)) {
      event.currentTarget.releasePointerCapture(drag.pointerId);
    }
    dragRef.current = null;
    setIsPanning(false);
  }

  return (
    <div className={`graph-canvas ${variant}`}>
      <div className="graph-toolbar">
        <span className="graph-count">{layout.nodes.length} 节点 · {layout.edges.length} 关系 · {Math.round(transform.scale * 100)}%</span>
        <div className="graph-actions" aria-label="图谱控制">
          <span className="graph-tool-hint" title="拖拽画布可平移" aria-label="拖拽画布可平移">
            <Move size={16} />
          </span>
          <button type="button" title="缩小" aria-label="缩小" onClick={() => zoomBy(0.78)}>
            <ZoomOut size={16} />
          </button>
          <button type="button" title="放大" aria-label="放大" onClick={() => zoomBy(1.28)}>
            <ZoomIn size={16} />
          </button>
          <button type="button" title="适配窗口" aria-label="适配窗口" onClick={fitGraph}>
            <Maximize2 size={16} />
          </button>
        </div>
      </div>
      <svg
        className={isPanning ? "is-panning" : ""}
        viewBox={`0 0 ${viewport.width} ${viewport.height}`}
        role="img"
        aria-label="产业链知识图谱"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={stopPanning}
        onPointerCancel={stopPanning}
      >
        <rect width={viewport.width} height={viewport.height} fill="#f8fafc" />
        <defs>
          <marker id={arrowId} markerWidth="8" markerHeight="8" refX="7" refY="3.5" orient="auto">
            <path d="M0,0 L0,7 L7,3.5 z" fill="#94a3b8" />
          </marker>
        </defs>
        <g transform={`translate(${transform.x.toFixed(2)} ${transform.y.toFixed(2)}) scale(${transform.scale.toFixed(4)})`}>
          {layout.columns.map((column) => (
            <g className="graph-column-label" key={column.id}>
              <text x={column.x} y="32" textAnchor="middle">
                {column.label}
              </text>
              <text x={column.x} y="49" textAnchor="middle">
                {column.count}
              </text>
            </g>
          ))}
          {layout.edges.map((edge, index) => {
            const source = nodeById.get(edge.source);
            const target = nodeById.get(edge.target);
            if (!source || !target) return null;
            const labelPoint = edgeLabelPoint(source, target, index);
            return (
              <g className="graph-edge-group" key={edge.key}>
                <path className="graph-edge" d={graphPath(source, target, index)} markerEnd={`url(#${arrowId})`}>
                  <title>
                    {edge.source} - {edge.label} - {edge.target}
                    {edge.citation_id ? ` · ${edge.citation_id}` : ""}
                  </title>
                </path>
                {layout.showEdgeLabels && (
                  <text className="graph-edge-label" x={labelPoint.x} y={labelPoint.y} textAnchor="middle">
                    {edge.label}
                  </text>
                )}
              </g>
            );
          })}
          {layout.nodes.map((node) => {
            const style = entityStyle(node.type);
            const lines = splitSvgLabel(node.id, variant === "compact" ? 8 : 10);
            return (
              <g className="graph-node" key={node.id}>
                <circle cx={node.x} cy={node.y} r={node.r} fill={style.color}>
                  <title>
                    {node.id} · {style.label}
                  </title>
                </circle>
                <text className="graph-node-label" x={node.x + node.r + 8} y={node.y - (lines.length - 1) * 7 + 4}>
                  {lines.map((line, index) => (
                    <tspan key={line} x={node.x + node.r + 8} dy={index === 0 ? 0 : 14}>
                      {line}
                    </tspan>
                  ))}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <div className="graph-legend">
        {layout.legendTypes.map((type) => {
          const style = entityStyle(type);
          return (
            <span key={type}>
              <i style={{ background: style.color }} />
              {style.label}
            </span>
          );
        })}
      </div>
    </div>
  );
}
