'use client';

import type { GraphSubgraph } from '../lib/graph';

interface GraphSubgraphProps {
  graph: GraphSubgraph;
  selectedCitation: number | null;
  expanded: boolean;
  onToggleExpanded: () => void;
  onSelectCitation: (citationIndex: number) => void;
  showMetadata: boolean;
}

const TOP_N = 6;

export function GraphSubgraphPanel({
  graph,
  selectedCitation,
  expanded,
  onToggleExpanded,
  onSelectCitation,
  showMetadata,
}: GraphSubgraphProps) {
  const visibleNodes = expanded ? graph.nodes : graph.nodes.slice(0, TOP_N);
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const visibleEdges = graph.edges.filter((edge) => visibleIds.has(edge.from) && visibleIds.has(edge.to));

  if (graph.nodes.length === 0) {
    return null;
  }

  return (
    <section className="mt-3 rounded-xl border border-black/10 bg-white p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-black/60">GraphRAG Subgraph</h4>
        {graph.nodes.length > TOP_N ? (
          <button
            type="button"
            onClick={onToggleExpanded}
            className="rounded border border-black/20 px-2 py-1 text-[10px]"
          >
            {expanded ? 'Collapse' : `Expand (${graph.nodes.length})`}
          </button>
        ) : null}
      </div>

      <svg viewBox="0 0 640 120" className="h-28 w-full rounded-lg bg-paper/60">
        {visibleEdges.map((edge) => {
          const fromIndex = visibleNodes.findIndex((node) => node.id === edge.from);
          const toIndex = visibleNodes.findIndex((node) => node.id === edge.to);
          if (fromIndex === -1 || toIndex === -1) {
            return null;
          }
          const x1 = 40 + fromIndex * 96;
          const x2 = 40 + toIndex * 96;
          return (
            <line
              key={edge.id}
              x1={x1}
              y1={60}
              x2={x2}
              y2={60}
              stroke={edge.edgeType === 'expands' ? '#0d9488' : '#1f2937'}
              strokeDasharray={edge.edgeType === 'expands' ? '4 4' : '0'}
              strokeWidth={2}
            />
          );
        })}

        {visibleNodes.map((node, index) => {
          const x = 40 + index * 96;
          const isSelected = selectedCitation === node.citationIndex;
          const fill =
            node.nodeType === 'seed' ? '#0f766e' : node.nodeType === 'expanded' ? '#14b8a6' : '#1f2937';
          return (
            <g key={node.id}>
              <circle
                cx={x}
                cy={60}
                r={isSelected ? 14 : 11}
                fill={fill}
                opacity={isSelected ? 1 : 0.8}
                onClick={() => onSelectCitation(node.citationIndex)}
                style={{ cursor: 'pointer' }}
              />
              <text x={x} y={92} textAnchor="middle" fontSize="10" fill="#111827">
                [{node.citationIndex}]
              </text>
            </g>
          );
        })}
      </svg>

      {showMetadata ? (
        <div className="mt-2 space-y-1 text-[11px] text-black/70">
          {visibleNodes.map((node) => (
            <div key={`meta-${node.id}`}>
              [{node.citationIndex}] {node.nodeType} · {node.metadata.sourceType} · {node.metadata.locator} · score{' '}
              {node.score.toFixed(3)}
            </div>
          ))}
          {graph.paths.map((path) => (
            <div key={path.pathId} className="text-[10px] text-black/50">
              path: {path.nodeIds.join(' -> ')} ({path.reason})
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
