import React, { useMemo, useState } from 'react';
import type { GraphEdge, GraphNode } from '../types';

interface DependencyGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const TIERS = ['Entrypoint', 'Presentation', 'Service', 'Repository', 'Utility', 'ExternalDB'] as const;

const TIER_STYLES: Record<string, { border: string; label: string; headerBg: string }> = {
  Entrypoint: { border: '#475569', label: 'Entrypoint', headerBg: '#f1f5f9' },
  Presentation: { border: '#2563eb', label: 'Presentation', headerBg: '#eff6ff' },
  Service: { border: '#0d9488', label: 'Service', headerBg: '#f0fdfa' },
  Repository: { border: '#7c3aed', label: 'Repository', headerBg: '#f5f3ff' },
  Utility: { border: '#d97706', label: 'Utility', headerBg: '#fffbeb' },
  ExternalDB: { border: '#dc2626', label: 'ExternalDB', headerBg: '#fef2f2' },
};

export const DependencyGraph: React.FC<DependencyGraphProps> = ({ nodes, edges }) => {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const layout = useMemo(() => {
    const width = 1080;
    const colW = width / TIERS.length;
    const grouped: Record<string, GraphNode[]> = {};
    TIERS.forEach((t) => {
      grouped[t] = [];
    });

    nodes.forEach((n) => {
      const tier = TIERS.includes(n.layer as (typeof TIERS)[number]) ? n.layer : 'Utility';
      grouped[tier].push(n);
    });

    const maxCount = Math.max(1, ...Object.values(grouped).map((arr) => arr.length));
    const height = Math.max(420, 110 + maxCount * 76);

    const positions: Record<string, { x: number; y: number }> = {};
    TIERS.forEach((tier, tIdx) => {
      const list = grouped[tier];
      const cx = colW * tIdx + colW / 2;
      const usableH = height - 76;
      list.forEach((node, idx) => {
        const cy = 64 + (usableH / (list.length + 1)) * (idx + 1);
        positions[node.id] = { x: cx, y: cy };
      });
    });

    return { width, height, colW, positions };
  }, [nodes]);

  const activeNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId]
  );

  const activeEdges = useMemo(() => {
    if (!selectedNodeId) return { incoming: [], outgoing: [] };
    return {
      incoming: edges.filter((e) => e.target === selectedNodeId),
      outgoing: edges.filter((e) => e.source === selectedNodeId),
    };
  }, [edges, selectedNodeId]);

  if (nodes.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
        No Python modules discovered to visualize.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
      <div className="lg:col-span-3 overflow-x-auto rounded-lg border border-slate-200 bg-white p-3">
        <svg
          width={layout.width}
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          className="block w-full h-auto"
          role="img"
          aria-label="Layered software architecture dependency graph"
        >
          <defs>
            <marker
              id="arrow-valid"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#16a34a" />
            </marker>
            <marker
              id="arrow-violation"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#dc2626" />
            </marker>
          </defs>

          {TIERS.map((tier, tIdx) => {
            const x = layout.colW * tIdx + 6;
            const boxW = layout.colW - 12;
            const style = TIER_STYLES[tier];
            return (
              <g key={tier}>
                <rect
                  x={x}
                  y={10}
                  width={boxW}
                  height={layout.height - 20}
                  rx={8}
                  fill="#f8fafc"
                  stroke="#e2e8f0"
                  strokeWidth={1}
                />
                <rect
                  x={x}
                  y={10}
                  width={boxW}
                  height={30}
                  rx={8}
                  fill={style.headerBg}
                />
                <text
                  x={x + boxW / 2}
                  y={29}
                  textAnchor="middle"
                  fontSize="11"
                  fontWeight={700}
                  fill="#334155"
                >
                  {style.label}
                </text>
              </g>
            );
          })}

          {edges.map((edge, idx) => {
            const p1 = layout.positions[edge.source];
            const p2 = layout.positions[edge.target];
            if (!p1 || !p2) return null;

            const isRelated =
              !selectedNodeId ||
              edge.source === selectedNodeId ||
              edge.target === selectedNodeId;
            const sameColumn = Math.abs(p1.x - p2.x) < 10;
            let pathD: string;
            if (sameColumn) {
              const curveOffset = p1.y < p2.y ? 56 : -56;
              pathD = `M ${p1.x} ${p1.y} C ${p1.x + curveOffset} ${p1.y}, ${p2.x + curveOffset} ${p2.y}, ${p2.x} ${p2.y}`;
            } else {
              const dx = (p2.x - p1.x) * 0.42;
              const arcLift = edge.is_violation ? -28 : -14;
              pathD = `M ${p1.x} ${p1.y} C ${p1.x + dx} ${p1.y + arcLift}, ${p2.x - dx} ${p2.y + arcLift}, ${p2.x} ${p2.y}`;
            }

            if (edge.is_violation) {
              return (
                <path
                  key={`${edge.source}-${edge.target}-${idx}`}
                  d={pathD}
                  fill="none"
                  stroke="#dc2626"
                  strokeOpacity={isRelated ? 0.95 : 0.25}
                  className="violation-edge-pulse"
                  markerEnd="url(#arrow-violation)"
                />
              );
            }

            return (
              <path
                key={`${edge.source}-${edge.target}-${idx}`}
                d={pathD}
                fill="none"
                stroke="#16a34a"
                strokeWidth={isRelated && selectedNodeId ? 2 : 1.4}
                strokeOpacity={isRelated ? 0.65 : 0.14}
                markerEnd="url(#arrow-valid)"
              />
            );
          })}

          {nodes.map((node) => {
            const pos = layout.positions[node.id];
            if (!pos) return null;
            const style = TIER_STYLES[node.layer] || TIER_STYLES.Utility;
            const isSelected = node.id === selectedNodeId;
            const stroke = node.is_cyclic ? '#dc2626' : isSelected ? '#0f172a' : style.border;

            return (
              <g
                key={node.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                onClick={() => setSelectedNodeId(isSelected ? null : node.id)}
                className="cursor-pointer"
              >
                <rect
                  x={-72}
                  y={-21}
                  width={144}
                  height={42}
                  rx={6}
                  fill={isSelected ? '#f1f5f9' : '#ffffff'}
                  stroke={stroke}
                  strokeWidth={node.is_cyclic || isSelected ? 2.2 : 1.3}
                />
                <text
                  x={0}
                  y={-4}
                  textAnchor="middle"
                  fontSize="11"
                  fontWeight={600}
                  fill="#0f172a"
                >
                  {node.label.length > 19 ? `${node.label.slice(0, 17)}..` : node.label}
                </text>
                <text
                  x={0}
                  y={12}
                  textAnchor="middle"
                  fontSize="9.5"
                  fill="#64748b"
                  fontFamily="JetBrains Mono, monospace"
                >
                  Ca:{node.ca} Ce:{node.ce} I:{node.instability.toFixed(2)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Node Inspector
        </div>
        {!activeNode ? (
          <div className="mt-3 text-sm text-slate-600 leading-relaxed">
            Click any module node in the graph to inspect its coupling metrics, cyclomatic complexity, and incoming or outgoing edges.
          </div>
        ) : (
          <div className="mt-3 space-y-4">
            <div>
              <div className="text-sm font-semibold text-slate-900 break-all">
                {activeNode.file_path}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {activeNode.layer} · {activeNode.id}
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-x-3 gap-y-2 border-t border-slate-100 pt-3 text-xs">
              <div>
                <dt className="text-slate-500">Afferent (Ca)</dt>
                <dd className="font-mono tabular-nums font-semibold text-slate-900">{activeNode.ca}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Efferent (Ce)</dt>
                <dd className="font-mono tabular-nums font-semibold text-slate-900">{activeNode.ce}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Instability (I)</dt>
                <dd className="font-mono tabular-nums font-semibold text-slate-900">
                  {activeNode.instability.toFixed(3)}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Max / Avg CC</dt>
                <dd className="font-mono tabular-nums font-semibold text-slate-900">
                  {activeNode.max_complexity} / {activeNode.avg_complexity.toFixed(1)}
                </dd>
              </div>
            </dl>

            <div className="border-t border-slate-100 pt-3">
              <div className="text-xs font-medium text-slate-700 mb-1.5">
                Outgoing Dependencies ({activeEdges.outgoing.length})
              </div>
              {activeEdges.outgoing.length === 0 ? (
                <div className="text-xs text-slate-400">None</div>
              ) : (
                <ul className="space-y-1 text-xs font-mono">
                  {activeEdges.outgoing.map((e) => (
                    <li
                      key={`out-${e.target}`}
                      className={e.is_violation ? 'text-red-600 font-medium' : 'text-slate-600'}
                    >
                      -&gt; {e.target} {e.line_numbers.length ? `(L${e.line_numbers.join(',')})` : ''}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="border-t border-slate-100 pt-3">
              <div className="text-xs font-medium text-slate-700 mb-1.5">
                Incoming Dependents ({activeEdges.incoming.length})
              </div>
              {activeEdges.incoming.length === 0 ? (
                <div className="text-xs text-slate-400">None</div>
              ) : (
                <ul className="space-y-1 text-xs font-mono">
                  {activeEdges.incoming.map((e) => (
                    <li
                      key={`in-${e.source}`}
                      className={e.is_violation ? 'text-red-600 font-medium' : 'text-slate-600'}
                    >
                      &lt;- {e.source}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
