import { describe, expect, it } from 'vitest';

import {
  buildConversationQaRequest,
  buildQaSelectedNodePayload,
  type RightPanelQaAnchorInput,
} from './right-panel-qa-request';
import type {
  CreateGraphConversationReplyRequest,
  CreateGraphConversationSessionStartRequest,
} from '../services/create-graph-extensions';

describe('right-panel qa request anchors', () => {
  const anchorInput: RightPanelQaAnchorInput = {
    partitionId: 'partition-metrics',
    selectedNode: {
      id: 'node-metrics-run',
      label: 'Method',
      properties: {
        name: 'run',
        filePath: 'src/metrics.py',
        startLine: 21,
        endLine: 48,
      },
    },
    selectedMethodKey: 'pkg.metrics.Metrics.run',
    selectedPathAnalysis: {
      id: 'ui-path-1',
      pathId: 'path-1',
      pathName: 'metrics main flow',
      pathDescription: 'entry -> prepare -> run',
      methods: [
        'pkg.entry.main',
        'pkg.metrics.Metrics.prepare',
        'pkg.metrics.Metrics.run',
      ],
      leafNode: 'pkg.metrics.Metrics.run',
      mainMethod: 'pkg.entry.main',
      intermediateMethods: ['pkg.metrics.Metrics.prepare'],
      callChainType: 'entry_to_leaf',
      callChainExplanation: '主入口最终调用 Metrics.run',
    },
    partitionAnalysis: {
      fqns: [
        {
          method_signature: 'pkg.metrics.Metrics.run',
          fqn: 'pkg.metrics.Metrics.run',
          full_name: 'pkg.metrics.Metrics.run',
        },
      ],
    },
  };

  it('builds a richer selected_node anchor payload from UI state', () => {
    expect(buildQaSelectedNodePayload(anchorInput)).toMatchObject({
      id: 'node-metrics-run',
      name: 'run',
      type: 'Method',
      file_path: 'src/metrics.py',
      start_line: 21,
      end_line: 48,
      partition_id: 'partition-metrics',
      method_signature: 'pkg.metrics.Metrics.run',
      signature: 'pkg.metrics.Metrics.run',
      fqmn: 'pkg.metrics.Metrics.run',
      fqn: 'pkg.metrics.Metrics.run',
      leaf_node: 'pkg.metrics.Metrics.run',
      main_method: 'pkg.entry.main',
      intermediate_methods: ['pkg.metrics.Metrics.prepare'],
      path_methods: [
        'pkg.entry.main',
        'pkg.metrics.Metrics.prepare',
        'pkg.metrics.Metrics.run',
      ],
      function_chain: [
        'pkg.entry.main',
        'pkg.metrics.Metrics.prepare',
        'pkg.metrics.Metrics.run',
      ],
      call_chain_type: 'entry_to_leaf',
    });
  });

  it('attaches selected_node and partition_id to both start and reply requests', () => {
    const startPayload: CreateGraphConversationSessionStartRequest = {
      query: '谁调用了 Metrics.run？',
      project_path: 'D:/repo',
    };
    const replyPayload: CreateGraphConversationReplyRequest = {
      answer: '继续追问 caller/callee',
      project_path: 'D:/repo',
    };

    const startRequest = buildConversationQaRequest(
      startPayload,
      anchorInput,
    );
    const replyRequest = buildConversationQaRequest(
      replyPayload,
      anchorInput,
    );

    expect(startRequest.partition_id).toBe('partition-metrics');
    expect(replyRequest.partition_id).toBe('partition-metrics');
    expect(startRequest.selected_node).toMatchObject({
      method_signature: 'pkg.metrics.Metrics.run',
      main_method: 'pkg.entry.main',
    });
    expect(replyRequest.selected_node).toMatchObject({
      fqmn: 'pkg.metrics.Metrics.run',
      path_methods: [
        'pkg.entry.main',
        'pkg.metrics.Metrics.prepare',
        'pkg.metrics.Metrics.run',
      ],
    });
  });
});
