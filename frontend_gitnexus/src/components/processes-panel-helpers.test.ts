import { describe, expect, it } from 'vitest';
import type { KnowledgeGraph } from '../core/graph/types';
import { buildProcessStepsFromGraph, deriveProcessesFromGraph, getProcessStepIdsFromGraph } from './processes-panel-helpers';

const graph: Pick<KnowledgeGraph, 'nodes' | 'relationships'> = {
  nodes: [
    {
      id: 'process-a',
      label: 'Process',
      properties: {
        name: 'Process A',
        filePath: 'src/a.ts',
        processType: 'intra_community',
        stepCount: 0,
        communities: ['community-a'],
      },
    },
    {
      id: 'process-b',
      label: 'Process',
      properties: {
        name: 'Process B',
        filePath: 'src/b.ts',
        processType: 'cross_community',
        stepCount: 5,
        communities: ['community-a', 'community-b'],
      },
    },
    {
      id: 'step-1',
      label: 'Method',
      properties: { name: 'stepOne', filePath: 'src/a.ts' },
    },
    {
      id: 'step-2',
      label: 'Method',
      properties: { name: 'stepTwo', filePath: 'src/a.ts' },
    },
  ],
  relationships: [
    {
      id: 'rel-2',
      sourceId: 'step-2',
      targetId: 'process-a',
      type: 'STEP_IN_PROCESS',
      confidence: 1,
      reason: '',
      step: 2,
    },
    {
      id: 'rel-1',
      sourceId: 'step-1',
      targetId: 'process-a',
      type: 'STEP_IN_PROCESS',
      confidence: 1,
      reason: '',
      step: 1,
    },
  ],
};

describe('processes-panel helpers', () => {
  it('derives stepCount from STEP_IN_PROCESS relationships when direct count is missing or zero', () => {
    const processes = deriveProcessesFromGraph(graph);
    expect(processes.intra).toHaveLength(1);
    expect(processes.intra[0]).toMatchObject({ id: 'process-a', stepCount: 2 });
    expect(processes.cross[0]).toMatchObject({ id: 'process-b', stepCount: 5 });
  });

  it('returns ordered step ids and detailed steps from graph relationships', () => {
    expect(getProcessStepIdsFromGraph(graph, 'process-a')).toEqual(['step-2', 'step-1']);
    expect(buildProcessStepsFromGraph(graph, 'process-a')).toEqual([
      { id: 'step-1', name: 'stepOne', filePath: 'src/a.ts', stepNumber: 1 },
      { id: 'step-2', name: 'stepTwo', filePath: 'src/a.ts', stepNumber: 2 },
    ]);
  });
});
