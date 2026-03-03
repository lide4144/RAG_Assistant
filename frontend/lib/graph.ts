import type { SourceItem } from './types';

export interface GraphNode {
  id: string;
  label: string;
  nodeType: 'seed' | 'expanded' | 'evidence';
  sourceId: string;
  citationIndex: number;
  score: number;
  metadata: {
    locator: string;
    sourceType: SourceItem['source_type'];
  };
}

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  edgeType: 'supports' | 'expands';
}

export interface GraphPath {
  pathId: string;
  nodeIds: string[];
  reason: string;
}

export interface GraphSubgraph {
  seedNodeIds: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  paths: GraphPath[];
}

export function buildGraphSubgraph(sources: SourceItem[]): GraphSubgraph {
  const nodes: GraphNode[] = sources.map((source, index) => {
    const isGraphExpanded = source.source_type === 'graph';
    const nodeType: GraphNode['nodeType'] = index === 0 ? 'seed' : isGraphExpanded ? 'expanded' : 'evidence';
    return {
      id: `node-${source.source_id}`,
      label: source.title,
      nodeType,
      sourceId: source.source_id,
      citationIndex: index + 1,
      score: source.score,
      metadata: {
        locator: source.locator,
        sourceType: source.source_type,
      },
    };
  });

  const edges: GraphEdge[] = [];
  for (let i = 1; i < nodes.length; i += 1) {
    edges.push({
      id: `edge-${nodes[i - 1].id}-${nodes[i].id}`,
      from: nodes[i - 1].id,
      to: nodes[i].id,
      edgeType: nodes[i].nodeType === 'expanded' ? 'expands' : 'supports',
    });
  }

  const seedNodeIds = nodes.filter((node) => node.nodeType === 'seed').map((node) => node.id);
  const paths: GraphPath[] = nodes.length >= 2
    ? [
        {
          pathId: 'path-main',
          nodeIds: nodes.map((node) => node.id),
          reason: 'retrieval_chain',
        },
      ]
    : [];

  return {
    seedNodeIds,
    nodes,
    edges,
    paths,
  };
}
