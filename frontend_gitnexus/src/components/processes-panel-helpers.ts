import type { KnowledgeGraph, GraphRelationship } from '../core/graph/types';
import type { ProcessStep } from '../lib/mermaid-generator';

type GraphLike = Pick<KnowledgeGraph, 'nodes' | 'relationships'> | null | undefined;

export interface ProcessListItem {
  id: string;
  label: string;
  stepCount: number;
  clusters: string[];
}

export interface ProcessBuckets {
  cross: ProcessListItem[];
  intra: ProcessListItem[];
}

export const readNumericStepCount = (value: unknown): number | null => {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

export const getProcessStepRelsFromGraph = (
  graph: GraphLike,
  processId: string,
): GraphRelationship[] => {
  if (!graph) return [];
  return graph.relationships.filter((rel) => rel.type === 'STEP_IN_PROCESS' && rel.targetId === processId);
};

export const getProcessStepIdsFromGraph = (
  graph: GraphLike,
  processId: string,
): string[] => {
  return getProcessStepRelsFromGraph(graph, processId).map((rel) => rel.sourceId);
};

export const buildProcessStepsFromGraph = (
  graph: GraphLike,
  processId: string,
): ProcessStep[] => {
  if (!graph) return [];
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const rels = [...getProcessStepRelsFromGraph(graph, processId)].sort((left, right) => {
    const leftStep = typeof left.step === 'number' ? left.step : Number.MAX_SAFE_INTEGER;
    const rightStep = typeof right.step === 'number' ? right.step : Number.MAX_SAFE_INTEGER;
    return leftStep - rightStep;
  });

  return rels.map((rel, index) => {
    const stepNode = nodeById.get(rel.sourceId);
    return {
      id: rel.sourceId,
      name: stepNode?.properties?.name || rel.sourceId,
      filePath: stepNode?.properties?.filePath,
      stepNumber: typeof rel.step === 'number' ? rel.step : index + 1,
    };
  });
};

export const deriveProcessesFromGraph = (graph: GraphLike): ProcessBuckets => {
  if (!graph) return { cross: [], intra: [] };

  const processNodes = graph.nodes.filter((node) => node.label === 'Process');
  const relDerivedStepCount = new Map<string, number>();
  for (const rel of graph.relationships) {
    if (rel.type !== 'STEP_IN_PROCESS') continue;
    relDerivedStepCount.set(rel.targetId, (relDerivedStepCount.get(rel.targetId) || 0) + 1);
  }

  const cross: ProcessListItem[] = [];
  const intra: ProcessListItem[] = [];

  for (const node of processNodes) {
    const nodeProps = node.properties as Record<string, unknown>;
    const directStepCount = readNumericStepCount(nodeProps.stepCount) ?? readNumericStepCount(nodeProps.step_count);
    const item: ProcessListItem = {
      id: node.id,
      label: node.properties.heuristicLabel || node.properties.name || node.id,
      stepCount: directStepCount && directStepCount > 0 ? directStepCount : (relDerivedStepCount.get(node.id) || 0),
      clusters: Array.isArray(node.properties.communities) ? node.properties.communities : [],
    };

    if (node.properties.processType === 'cross_community') {
      cross.push(item);
    } else {
      intra.push(item);
    }
  }

  cross.sort((left, right) => right.stepCount - left.stepCount);
  intra.sort((left, right) => right.stepCount - left.stepCount);

  return { cross, intra };
};
