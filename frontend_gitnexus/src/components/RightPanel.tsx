import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Send,
  Square,
  Sparkles,
  User,
  BookOpen,
  ChevronDown,
  ChevronRight,
  History,
  PanelRightClose,
  Loader2,
  AlertTriangle,
  GitBranch,
  Layers,
  MessageSquare,
  RefreshCw,
  ExternalLink,
  Clock3,
} from 'lucide-react';
import { useAppState } from '../hooks/useAppState';
import { ToolCallCard } from './ToolCallCard';
import { isProviderConfigured, buildBackendConversationLLMConfig } from '../core/llm/settings-service';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ProcessesPanel } from './ProcessesPanel';
import { GraphVizBlock } from './GraphVizBlock';
import { MermaidDiagram } from './MermaidDiagram';
import { IoGraphBlock, type IoGraphData, type IoGraphEdge, type IoGraphNode } from './IoGraphBlock';
import { ExperienceLibraryManagerPanel } from './ExperienceLibraryManagerPanel';
import {
  createGraphExtensionsApi,
  type CreateGraphClarificationField,
  type CreateGraphClarificationOption,
  type CreateGraphClarificationPayload,
  type CreateGraphConversationPendingQuestion,
  type CreateGraphConversationStreamResult,
  type CreateGraphConversationSessionResultResponse,
  type CreateGraphConversationSessionStatusResponse,
  type CreateGraphConversationListItem,
  type CreateGraphHierarchyContract,
  type CreateGraphRagAskResponse,
  type CreateGraphMultiAgentResultResponse,
  type CreateGraphMultiAgentSessionStatusResponse,
  type CreateGraphPartitionAnalysisResponse,
  type CreateGraphWorkbenchProjectStatusResponse,
} from '../services/create-graph-extensions';

interface PartitionSummaryView {
  partitionId: string;
  name: string;
  description: string;
  pathCount: number;
  processCount: number;
  communityCount: number;
  methodCount: number;
  methods: string[];
  hasCfg: boolean;
  hasDfg: boolean;
  hasIo: boolean;
}

interface RagEvidenceView {
  rank: string;
  label: string;
  nodeId: string;
  filePath: string;
  score: string;
  lineStart?: number;
  lineEnd?: number;
}

interface RagJudgmentView {
  status: string;
  confidence: string;
  reasons: string[];
}

interface RagSwarmConsensusView {
  summary: string;
  confidence: string;
  risks: string[];
  actions: string[];
}

interface RagSwarmAgentView {
  key: string;
  name: string;
  summary: string;
  confidence: string;
  status: string;
  risks: string[];
  actions: string[];
}

interface RagSwarmView {
  enabled: boolean;
  llmEnabled: boolean;
  model: string;
  consensus: RagSwarmConsensusView | null;
  agents: RagSwarmAgentView[];
}

interface RagExecutionCardView {
  id: string;
  title: string;
  summary: string;
  confidence: string;
  steps: string[];
  targets: string[];
  risks: string[];
  preflightChecks: string[];
  rollbackSuggestions: string[];
}

interface RagTimelineItemView {
  id: string;
  title: string;
  detail: string;
  tone: 'info' | 'active' | 'success' | 'warn';
  groupKey: RagTimelineGroupKey;
  stageKey: RagStageKey;
}

type RagStageKey = 'session' | 'retrieval' | 'judgment' | 'swarm' | 'result';
type RagTimelineGroupKey = 'session' | 'retrieval' | 'decision' | 'swarm' | 'clarification' | 'result';

interface RagStageAnchorView {
  key: RagStageKey;
  label: string;
  status: 'idle' | 'active' | 'success' | 'warn';
}

interface RagTimelineGroupView {
  key: RagTimelineGroupKey;
  title: string;
  status: 'idle' | 'active' | 'success' | 'warn';
  items: RagTimelineItemView[];
}

interface RagReplaySnapshot {
  query: string;
  error: string | null;
  response: CreateGraphPanelRagResponse | null;
  sessionStatus: CreateGraphMultiAgentSessionStatusResponse | CreateGraphConversationSessionStatusResponse | null;
  clarification: RagClarificationState | null;
  conversationId: string | null;
  eventCursor: number;
  liveSwarmPayload: Record<string, unknown> | null;
  progressEvents: string[];
  savedRunbookPath: string | null;
}

interface RagReplayEntryView {
  id: string;
  query: string;
  createdAt: number;
  updatedAt: number;
  status: string;
  stage: string;
  snapshot: RagReplaySnapshot;
}

interface RagReplayExportMeta {
  answerSummary: string;
  stageLabel: string;
  statusLabel: string;
}

interface RagRetrievalSummaryView {
  mode: string;
  strategy: string[];
  stats: string[];
  queryPlans: string[];
  decisionTrace: Array<{
    step: string;
    decision: string;
    reason: string;
    confidence?: string;
  }>;
}

interface HierarchyFunctionView {
  partitionId: string;
  name: string;
  description: string;
  folders: string[];
  methods: string[];
  methodCount: number;
  totalClasses: number;
  outgoingCallCount: number;
  incomingCallCount: number;
  functionRelations: Array<{ source: string; target: string; callCount: number }>;
}

interface PartitionMethodDetailView {
  methodKey: string;
  inputs: string[];
  outputs: string[];
  pathDescriptions: string[];
  processLabels: string[];
  communityLabels: string[];
  entryReason: string;
  cfgAvailable: boolean;
  dfgAvailable: boolean;
  ioGraphAvailable: boolean;
}

type HierarchySubview = 'info' | 'entry' | 'hypergraph' | 'paths';
type HierarchyPage = 'list' | 'partition' | 'path';

interface EntryPointView {
  methodSignature: string;
  score: number;
  reasons: string[];
}

interface PathAnalysisView {
  id: string;
  pathName: string;
  pathDescription: string;
  methods: string[];
  leafNode: string;
  worthinessScore: number;
  worthinessReasons: string[];
  explainMarkdown: string;
  dataflowMermaid: string;
  hasDataflowMermaid: boolean;
  ioGraph: IoGraphData | null;
  ioNodeCount: number;
  ioEdgeCount: number;
  cfg: string;
  dfg: string;
  callChainType: string;
  callChainExplanation: string;
  mainMethod: string;
  intermediateMethods: string[];
  cfgAvailable: boolean;
  dfgAvailable: boolean;
  ioGraphAvailable: boolean;
}

type PathDetailView = 'overview' | 'cfg' | 'dfg' | 'dataflow' | 'io';

const SWARM_AGENT_ORDER = ['taizi', 'zhongshu', 'menxia', 'shangshu'];

const SWARM_AGENT_LABELS: Record<string, string> = {
  taizi: '太子',
  zhongshu: '中书',
  menxia: '门下',
  shangshu: '尚书',
};

interface RagClarificationState extends CreateGraphClarificationPayload {
  selectedOptionIds: string[];
  selectedOptionLabels: string[];
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null;
};

const toStringValue = (value: unknown, fallback = ''): string => {
  return typeof value === 'string' ? value : fallback;
};

const toNumberValue = (value: unknown, fallback = 0): number => {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
};

const toOptionalNumberValue = (value: unknown): number | undefined => {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
};

const toStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
};

const toBooleanValue = (value: unknown, fallback = false): boolean => {
  return typeof value === 'boolean' ? value : fallback;
};

const RAG_STAGE_LABELS: Record<RagStageKey, string> = {
  session: '会话启动',
  retrieval: '证据检索',
  judgment: '方案判断',
  swarm: '多代理协同',
  result: '结果产出',
};

const RAG_TIMELINE_GROUP_LABELS: Record<RagTimelineGroupKey, string> = {
  session: '会话阶段',
  retrieval: '证据检索',
  decision: '方案判断',
  swarm: 'Swarm 协同',
  clarification: '澄清补充',
  result: '结果产出',
};

const getRagStageKeyFromText = (text: string): RagStageKey => {
  const lower = text.toLowerCase();
  if (lower.includes('swarm') || lower.includes('multi_agent') || text.includes('多代理')) return 'swarm';
  if (lower.includes('retriev') || text.includes('检索') || text.includes('证据')) return 'retrieval';
  if (lower.includes('decid') || text.includes('决策') || text.includes('判断') || text.includes('澄清')) return 'judgment';
  if (lower.includes('result') || lower.includes('completed') || text.includes('完成') || text.includes('产出') || text.includes('答案')) return 'result';
  return 'session';
};

const getRagTimelineGroupKey = (title: string, detail: string): RagTimelineGroupKey => {
  const merged = `${title} ${detail}`.toLowerCase();
  if (merged.includes('clarification') || title.includes('澄清') || detail.includes('澄清')) return 'clarification';
  if (merged.includes('swarm') || merged.includes('multi_agent') || title.includes('多代理') || detail.includes('多代理')) return 'swarm';
  if (merged.includes('retriev') || title.includes('检索') || detail.includes('检索') || detail.includes('证据')) return 'retrieval';
  if (merged.includes('decid') || title.includes('决策') || detail.includes('判断') || detail.includes('压缩') || detail.includes('路由')) return 'decision';
  if (merged.includes('result') || title.includes('完成') || detail.includes('完成') || detail.includes('结果') || detail.includes('产出')) return 'result';
  return 'session';
};

const getTimelineGroupStatus = (items: RagTimelineItemView[]): RagTimelineGroupView['status'] => {
  if (items.some((item) => item.tone === 'warn')) return 'warn';
  if (items.some((item) => item.tone === 'active')) return 'active';
  if (items.some((item) => item.tone === 'success')) return 'success';
  return 'idle';
};

const getStageDisplayText = (stage: string): string => {
  if (!stage) return '未知阶段';
  const stageKey = getRagStageKeyFromText(stage);
  return RAG_STAGE_LABELS[stageKey];
};

const getReplayStatusDisplayText = (status: string): string => {
  if (status === 'failed') return '失败';
  if (status === 'completed') return '已完成';
  if (status === 'needs_clarification') return '待澄清';
  if (status === 'running') return '运行中';
  return status || '未知';
};

const matchesReplayFilter = (entry: RagReplayEntryView, filterText: string): boolean => {
  const keyword = filterText.trim().toLowerCase();
  if (!keyword) return true;
  const haystacks = [
    entry.id,
    entry.query,
    entry.snapshot.conversationId || '',
    entry.snapshot.sessionStatus?.sessionId || '',
  ].map((item) => item.toLowerCase());
  return haystacks.some((item) => item.includes(keyword));
};

const toReplayExportText = (entry: RagReplayEntryView, meta: RagReplayExportMeta): string => {
  const lines = [
    '# RAG 回看记录',
    '',
    `- 查询：${entry.query}`,
    `- 运行 ID：${entry.id}`,
    `- 时间：${new Date(entry.updatedAt).toLocaleString()}`,
    `- 状态：${meta.statusLabel}`,
    `- 阶段：${meta.stageLabel}`,
    `- Conversation ID：${entry.snapshot.conversationId || '无'}`,
    `- Session ID：${entry.snapshot.sessionStatus?.sessionId || '无'}`,
    '',
    '## 中间时间线',
  ];

  if (entry.snapshot.progressEvents.length > 0) {
    entry.snapshot.progressEvents.forEach((item) => {
      lines.push(`- ${item}`);
    });
  } else {
    lines.push('- 无中间事件');
  }

  lines.push('', '## 结果摘要');
  if (entry.snapshot.error) {
    lines.push(`- 错误：${entry.snapshot.error}`);
  } else {
    lines.push(`- 摘要：${meta.answerSummary || '无结果摘要'}`);
  }

  if (entry.snapshot.savedRunbookPath) {
    lines.push(`- 已保存 Runbook：${entry.snapshot.savedRunbookPath}`);
  }

  return lines.join('\n').trim();
};

const toIoGraphNodeArray = (value: unknown): IoGraphNode[] => {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((item) => ({
      id: toStringValue(item.id),
      label: toStringValue(item.label),
      type: toStringValue(item.type),
    }))
    .filter((item) => item.id);
};

const toIoGraphEdgeArray = (value: unknown): IoGraphEdge[] => {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((item) => ({
      source: toStringValue(item.source),
      target: toStringValue(item.target),
      label: toStringValue(item.label),
    }))
    .filter((item) => item.source && item.target);
};

const getGraphDot = (value: unknown): string => {
  if (typeof value === 'string') return value;
  if (!isRecord(value)) return '';
  const dot = value.dot;
  return typeof dot === 'string' ? dot : '';
};

const hasGraphContent = (value: unknown): boolean => {
  if (typeof value === 'string') return value.trim().length > 0;
  if (!isRecord(value)) return false;
  if (typeof value.dot === 'string' && value.dot.trim().length > 0) return true;
  return Array.isArray(value.nodes) || Array.isArray(value.edges);
};

const normalizeSymbolName = (value: string): string => {
  return value.trim().replace(/\s+/g, '').toLowerCase();
};

const toPartitionSummaries = (
  contract: CreateGraphHierarchyContract | null,
): PartitionSummaryView[] => {
  if (!contract) return [];
  const adapters = isRecord(contract.adapters) ? contract.adapters : {};
  const hierarchy = isRecord(contract.hierarchy_result) && isRecord(contract.hierarchy_result.hierarchy)
    ? contract.hierarchy_result.hierarchy
    : null;
  const layer1Functions = Array.isArray(hierarchy?.layer1_functions) ? hierarchy.layer1_functions : [];
  const partitionMetaMap = new Map<string, { name: string; description: string; methods: string[] }>();
  for (const item of layer1Functions) {
    if (!isRecord(item)) continue;
    const partitionId = toStringValue(item.partition_id);
    if (!partitionId) continue;
    partitionMetaMap.set(partitionId, {
      name: toStringValue(item.name, partitionId),
      description: toStringValue(item.description),
      methods: toStringArray(item.methods),
    });
  }
  const rawSummaries = adapters.partition_summaries;
  if (!Array.isArray(rawSummaries)) return [];

  const result: PartitionSummaryView[] = [];
  for (const item of rawSummaries) {
    if (!isRecord(item)) continue;

    const partitionId = toStringValue(item.partition_id);
    if (!partitionId) continue;

    const partitionMeta = partitionMetaMap.get(partitionId);
    const methods = partitionMeta?.methods?.length ? partitionMeta.methods : toStringArray(item.methods);
    result.push({
      partitionId,
      name: partitionMeta?.name || toStringValue(item.name, partitionId),
      description: partitionMeta?.description || toStringValue(item.description),
      pathCount: toNumberValue(item.path_count),
      processCount: toNumberValue(item.process_count),
      communityCount: toNumberValue(item.community_count),
      methodCount: methods.length,
      methods,
      hasCfg: toBooleanValue(item.has_cfg),
      hasDfg: toBooleanValue(item.has_dfg),
      hasIo: toBooleanValue(item.has_io),
    });
  }

  return result;
};

const toHierarchyFunctions = (
  contract: CreateGraphHierarchyContract | null,
): HierarchyFunctionView[] => {
  if (!contract || !isRecord(contract.hierarchy_result)) return [];
  const hierarchy = isRecord(contract.hierarchy_result.hierarchy) ? contract.hierarchy_result.hierarchy : null;
  const layer1Functions = hierarchy?.layer1_functions;
  if (!Array.isArray(layer1Functions)) return [];

  const result: HierarchyFunctionView[] = [];
  for (const item of layer1Functions) {
    if (!isRecord(item)) continue;
    const partitionId = toStringValue(item.partition_id);
    const outgoingCalls = isRecord(item.outgoing_calls) ? item.outgoing_calls : {};
    const incomingCalls = isRecord(item.incoming_calls) ? item.incoming_calls : {};
    const stats = isRecord(item.stats) ? item.stats : {};
    result.push({
      partitionId,
      name: toStringValue(item.name, partitionId || 'unknown'),
      description: toStringValue(item.description),
      folders: toStringArray(item.folders),
      methods: toStringArray(item.methods),
      methodCount: toNumberValue(item.method_count, toNumberValue(stats.total_methods)),
      totalClasses: toNumberValue(stats.total_classes),
      outgoingCallCount: Object.keys(outgoingCalls).length,
      incomingCallCount: Object.keys(incomingCalls).length,
      functionRelations: Array.isArray(item.function_relations)
        ? item.function_relations.filter(isRecord).map((relation) => ({
          source: toStringValue(relation.source),
          target: toStringValue(relation.target),
          callCount: toNumberValue(relation.call_count),
        })).filter((relation) => relation.source && relation.target)
        : [],
    });
  }
  return result;
};

const getPartitionMethodKeys = (
  partitionAnalysis: CreateGraphPartitionAnalysisResponse | null,
  summary: PartitionSummaryView | null,
  partitionView: HierarchyFunctionView | null,
): string[] => {
  const fqns = Array.isArray(partitionAnalysis?.fqns) ? partitionAnalysis?.fqns : [];
  const fromFqns = fqns
    .filter(isRecord)
    .map((item) => toStringValue(item.fqn, toStringValue(item.method_signature)))
    .filter(Boolean);
  if (fromFqns.length > 0) return fromFqns;
  if (partitionView?.methods?.length) return partitionView.methods;
  return summary?.methods ?? [];
};

const buildPartitionMethodDetail = (
  methodKey: string,
  partitionAnalysis: CreateGraphPartitionAnalysisResponse | null,
  hierarchyContract: CreateGraphHierarchyContract | null,
): PartitionMethodDetailView | null => {
  if (!methodKey) return null;
  const inputs = Array.isArray(partitionAnalysis?.inputs) ? partitionAnalysis?.inputs.filter(isRecord) : [];
  const outputs = Array.isArray(partitionAnalysis?.outputs) ? partitionAnalysis?.outputs.filter(isRecord) : [];
  const pathAnalyses = Array.isArray(partitionAnalysis?.path_analyses) ? partitionAnalysis?.path_analyses.filter(isRecord) : [];
  const entryShadow = isRecord(partitionAnalysis?.entry_points_shadow) && Array.isArray(partitionAnalysis?.entry_points_shadow.effective_entries)
    ? partitionAnalysis?.entry_points_shadow.effective_entries.filter(isRecord)
    : [];
  const processes = isRecord(hierarchyContract?.shadow_results?.process) && Array.isArray(hierarchyContract?.shadow_results?.process.processes)
    ? hierarchyContract?.shadow_results?.process.processes.filter(isRecord)
    : [];
  const communities = isRecord(hierarchyContract?.shadow_results?.community) && Array.isArray(hierarchyContract?.shadow_results?.community.communities)
    ? hierarchyContract?.shadow_results?.community.communities.filter(isRecord)
    : [];

  const matchedInputs = inputs
    .filter((item) => toStringValue(item.method_signature) === methodKey)
    .map((item) => `${toStringValue(item.parameter_name, 'param')}: ${toStringValue(item.parameter_type, 'Any')}`);
  const matchedOutputs = outputs
    .filter((item) => toStringValue(item.method_signature) === methodKey)
    .map((item) => toStringValue(item.return_type, 'Any'));
  const matchedPaths = pathAnalyses.filter((item) => {
    const path = Array.isArray(item.path) ? item.path : [];
    return toStringValue(item.leaf_node) === methodKey || path.some((part) => part === methodKey);
  });
  const matchedProcesses = processes.filter((item) => {
    const steps = Array.isArray(item.steps) ? item.steps.filter(isRecord) : [];
    return steps.some((step) => toStringValue(step.method_signature) === methodKey) || toStringValue(item.entry) === methodKey;
  });
  const matchedCommunities = communities.filter((item) => {
    const methods = toStringArray(item.methods);
    return methods.includes(methodKey);
  });
  const matchedEntry = entryShadow.find((item) => toStringValue(item.method_signature) === methodKey);

  return {
    methodKey,
    inputs: matchedInputs,
    outputs: matchedOutputs,
    pathDescriptions: matchedPaths.map((item) => {
      const description = toStringValue(item.path_description);
      if (description) return description;
      const path = Array.isArray(item.path) ? item.path.filter((part): part is string => typeof part === 'string') : [];
      return path.join(' -> ');
    }).filter(Boolean),
    processLabels: matchedProcesses.map((item) => `${toStringValue(item.entry, toStringValue(item.process_id, '流程'))}（步骤数=${toNumberValue(item.stepCount)}）`),
    communityLabels: matchedCommunities.map((item) => toStringValue(item.label, toStringValue(item.partition_id, 'community'))),
    entryReason: matchedEntry && Array.isArray(matchedEntry.reasons)
      ? matchedEntry.reasons.filter((reason): reason is string => typeof reason === 'string').join(' / ')
      : '',
    cfgAvailable: matchedPaths.some((item) => hasGraphContent(item.cfg)),
    dfgAvailable: matchedPaths.some((item) => hasGraphContent(item.dfg)),
    ioGraphAvailable: matchedPaths.some((item) => Boolean(item.io_graph)),
  };
};

const toEntryPoints = (partitionAnalysis: CreateGraphPartitionAnalysisResponse | null): EntryPointView[] => {
  const entryPoints = Array.isArray(partitionAnalysis?.entry_points) ? partitionAnalysis.entry_points : [];
  return entryPoints
    .filter(isRecord)
    .map((item) => ({
      methodSignature: toStringValue(item.method_signature),
      score: toNumberValue(item.score),
      reasons: Array.isArray(item.reasons) ? item.reasons.filter((reason): reason is string => typeof reason === 'string') : [],
    }))
    .filter((item) => item.methodSignature);
};

const toPathAnalyses = (partitionAnalysis: CreateGraphPartitionAnalysisResponse | null): PathAnalysisView[] => {
  const pathAnalyses = Array.isArray(partitionAnalysis?.path_analyses) ? partitionAnalysis.path_analyses : [];
  const built = pathAnalyses
    .filter(isRecord)
    .map((item) => {
      const path = Array.isArray(item.path) ? item.path.filter((part): part is string => typeof part === 'string') : [];
      const leafNode = toStringValue(item.leaf_node);
      const pathIndex = toNumberValue(item.path_index, 0);
      const ioGraph = isRecord(item.io_graph) ? item.io_graph : null;
      const ioNodes = toIoGraphNodeArray(ioGraph?.nodes);
      const ioEdges = toIoGraphEdgeArray(ioGraph?.edges);
      const highlightConfig = isRecord(item.highlight_config) ? item.highlight_config : null;
      return {
        id: `${leafNode}_${pathIndex}`,
        pathName: toStringValue(item.path_name, `路径 ${pathIndex + 1}`),
        pathDescription: toStringValue(item.path_description, `包含 ${path.length} 个方法的调用链`),
        methods: path,
        leafNode,
        worthinessScore: toNumberValue(item.worthiness_score),
        worthinessReasons: Array.isArray(item.worthiness_reasons) ? item.worthiness_reasons.filter((reason): reason is string => typeof reason === 'string') : [],
        explainMarkdown: toStringValue(item.cfg_dfg_explain_md),
        dataflowMermaid: toStringValue(item.dataflow_mermaid),
        hasDataflowMermaid: Boolean(item.dataflow_mermaid),
        ioGraph: ioGraph ? { nodes: ioNodes, edges: ioEdges } : null,
        ioNodeCount: ioNodes.length,
        ioEdgeCount: ioEdges.length,
        cfg: getGraphDot(item.cfg),
        dfg: getGraphDot(item.dfg),
        callChainType: toStringValue(highlightConfig?.call_chain_type),
        callChainExplanation: toStringValue(highlightConfig?.explanation),
        mainMethod: toStringValue(highlightConfig?.main_method),
        intermediateMethods: Array.isArray(highlightConfig?.intermediate_methods)
          ? highlightConfig.intermediate_methods.filter((method): method is string => typeof method === 'string')
          : [],
        cfgAvailable: hasGraphContent(item.cfg),
        dfgAvailable: hasGraphContent(item.dfg),
        ioGraphAvailable: Boolean(item.io_graph),
      };
    })
    .filter((item) => item.methods.length > 0);
  return built;
};

const getCallGraphMethodKeys = (partitionAnalysis: CreateGraphPartitionAnalysisResponse | null): string[] => {
  const callGraph = isRecord(partitionAnalysis?.call_graph) ? partitionAnalysis.call_graph : null;
  const nodes = Array.isArray(callGraph?.nodes) ? callGraph.nodes : [];
  return nodes
    .filter(isRecord)
    .map((node) => toStringValue(node.method_signature, toStringValue(node.label, toStringValue(node.id))))
    .filter(Boolean);
};

const getPartitionRelatedMethodKeys = (
  partitionAnalysis: CreateGraphPartitionAnalysisResponse | null,
  fallbackMethods: string[],
): string[] => {
  const combined = new Set<string>();
  for (const methodKey of getHypergraphMethodKeys(partitionAnalysis, [])) combined.add(methodKey);
  for (const methodKey of getCallGraphMethodKeys(partitionAnalysis)) combined.add(methodKey);
  for (const path of toPathAnalyses(partitionAnalysis)) {
    for (const methodKey of path.methods) combined.add(methodKey);
  }
  for (const methodKey of fallbackMethods) combined.add(methodKey);
  return [...combined];
};

const formatFqmnMeta = (item: Record<string, unknown>): string => {
  const origin = toStringValue(item.origin);
  const segmentCount = toNumberValue(item.segment_count);
  const meta: string[] = [];
  if (origin) meta.push(origin);
  if (segmentCount > 0) meta.push(`${segmentCount} segments`);
  return meta.join(' · ');
};

const getStage2VisibleSummary = (
  summary: PartitionSummaryView | null,
  partitionAnalysis: CreateGraphPartitionAnalysisResponse | null,
): Array<{ label: string; value: string }> => {
  if (!summary) return [];
  const shadowEntries = isRecord(partitionAnalysis?.entry_points_shadow) && Array.isArray(partitionAnalysis?.entry_points_shadow.effective_entries)
    ? partitionAnalysis.entry_points_shadow.effective_entries.length
    : 0;
  return [
    { label: '路径数', value: String(summary.pathCount) },
    { label: '流程数', value: String(summary.processCount) },
    { label: '社区数', value: String(summary.communityCount) },
    { label: 'Shadow入口点', value: String(shadowEntries) },
  ];
};

const getStage3CompareSummary = (
  summary: PartitionSummaryView | null,
  partitionAnalysis: CreateGraphPartitionAnalysisResponse | null,
  entryPoints: EntryPointView[],
  pathAnalyses: PathAnalysisView[],
): Array<{ label: string; oldValue: string; newValue: string }> => {
  if (!summary) return [];
  const pathInfo = isRecord(partitionAnalysis?.path_analysis_info) ? partitionAnalysis.path_analysis_info : null;
  return [
    { label: '入口点', oldValue: String(entryPoints.length), newValue: String(summary.processCount) },
    { label: '路径', oldValue: String(pathAnalyses.length), newValue: String(summary.pathCount) },
    { label: '社区', oldValue: String(toNumberValue(pathInfo?.partition_limit)), newValue: String(summary.communityCount) },
  ];
};

const getHypergraphMethodKeys = (
  partitionAnalysis: CreateGraphPartitionAnalysisResponse | null,
  fallbackMethods: string[],
): string[] => {
  const hypergraph = isRecord(partitionAnalysis?.hypergraph_viz)
    ? partitionAnalysis?.hypergraph_viz
    : isRecord(partitionAnalysis?.hypergraph)
      ? partitionAnalysis?.hypergraph
      : null;
  const nodes = Array.isArray(hypergraph?.nodes) ? hypergraph.nodes : [];
  const methods = nodes
    .filter(isRecord)
    .map((node) => isRecord(node.data) ? node.data : node)
    .filter(isRecord)
    .filter((node) => {
      const type = toStringValue(node.type).toLowerCase();
      return type.includes('method') || type.includes('function');
    })
    .map((node) => toStringValue(node.label, toStringValue(node.id)))
    .filter(Boolean);
  return methods.length > 0 ? methods : fallbackMethods;
};

type CreateGraphPanelRagResponse = CreateGraphRagAskResponse | CreateGraphMultiAgentResultResponse;

const toRagEvidence = (payload: CreateGraphPanelRagResponse | null): RagEvidenceView[] => {
  const retrievalBundle = isRecord(payload?.retrieval_bundle) ? payload.retrieval_bundle : null;
  const directPayload = isRecord(payload) ? payload : null;
  const rawEvidence = Array.isArray(retrievalBundle?.evidence)
    ? retrievalBundle.evidence
    : Array.isArray(directPayload?.evidence)
      ? directPayload.evidence
      : [];
  if (!rawEvidence.length) return [];

  const evidence: RagEvidenceView[] = [];
  for (const item of rawEvidence) {
    if (!isRecord(item)) continue;
    evidence.push({
      rank: String(item.rank ?? ''),
      label: toStringValue(item.label, 'unknown'),
      nodeId: toStringValue(item.node_id),
      filePath: toStringValue(item.file_path, '未知文件'),
      score: String(item.score ?? ''),
      lineStart: toOptionalNumberValue(item.line_start) ?? toOptionalNumberValue(item.lineStart),
      lineEnd: toOptionalNumberValue(item.line_end) ?? toOptionalNumberValue(item.lineEnd),
    });
  }

  return evidence;
};

const getOutputProtocol = (payload: CreateGraphPanelRagResponse | null): Record<string, unknown> | null => {
  if (isRecord(payload?.output_protocol)) return payload.output_protocol;
  const solutionPacket = isRecord(payload?.solution_packet) ? payload.solution_packet : null;
  return isRecord(solutionPacket?.output_protocol) ? solutionPacket.output_protocol : null;
};

const toRagJudgment = (payload: CreateGraphPanelRagResponse | null): RagJudgmentView | null => {
  const outputProtocol = getOutputProtocol(payload);
  const judgment = isRecord(outputProtocol?.judgment) ? outputProtocol.judgment : null;
  if (judgment) {
    return {
      status: toStringValue(judgment.status, 'needs_refinement'),
      confidence: toStringValue(judgment.confidence, 'low'),
      reasons: toStringArray(judgment.reasons),
    };
  }
  const evidenceVerdict = isRecord(payload?.evidence_verdict) ? payload.evidence_verdict : null;
  if (!evidenceVerdict) return null;
  return {
    status: toBooleanValue(evidenceVerdict.approved) ? 'ready' : 'needs_refinement',
    confidence: toStringValue(evidenceVerdict.confidence, 'low'),
    reasons: toStringArray(evidenceVerdict.reasons),
  };
};

const toRagRisks = (payload: CreateGraphPanelRagResponse | null): string[] => {
  const outputProtocol = getOutputProtocol(payload);
  const risks = toStringArray(outputProtocol?.remaining_risks_constraints);
  if (risks.length > 0) return risks;
  const solutionPacket = isRecord(payload?.solution_packet) ? payload.solution_packet : null;
  const validation = Array.isArray(solutionPacket?.validation)
    ? solutionPacket.validation.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
  const evidenceVerdict = isRecord(payload?.evidence_verdict) ? payload.evidence_verdict : null;
  return [...validation, ...toStringArray(evidenceVerdict?.refinement_needed)].filter((item, index, arr) => arr.indexOf(item) === index);
};

const toRagValidationCommands = (payload: CreateGraphPanelRagResponse | null): string[] => {
  const retrievalBundle = isRecord(payload?.retrieval_bundle) ? payload.retrieval_bundle : null;
  const commandsFromBundle = Array.isArray(retrievalBundle?.validationCommands)
    ? retrievalBundle.validationCommands.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
  const commandsFromBundleSnake = Array.isArray(retrievalBundle?.validation_commands)
    ? retrievalBundle.validation_commands.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];

  const outputProtocol = getOutputProtocol(payload);
  const commandsFromProtocol = Array.isArray(outputProtocol?.validation_commands)
    ? outputProtocol.validation_commands.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];

  const merged = [...commandsFromBundle, ...commandsFromBundleSnake, ...commandsFromProtocol];
  return merged.filter((item, index, arr) => arr.indexOf(item) === index);
};

const toRagRetrievalSummary = (payload: CreateGraphPanelRagResponse | null): RagRetrievalSummaryView | null => {
  const retrievalBundle = isRecord(payload?.retrieval_bundle) ? payload.retrieval_bundle : null;
  const search = isRecord(retrievalBundle?.search) ? retrievalBundle.search : null;
  if (!search) return null;

  const mode = toStringValue(search.mode, 'codebase_first_with_graph_augmentation');
  const strategy = toStringArray(search.strategy);
  const statsRaw = isRecord(search.stats) ? search.stats : null;
  const plansRaw = Array.isArray(search.queryPlans) ? search.queryPlans.filter(isRecord) : [];
  const traceRaw = Array.isArray(search.decisionTrace) ? search.decisionTrace.filter(isRecord) : [];

  const stats: string[] = [];
  if (statsRaw) {
    const scanned = toOptionalNumberValue(statsRaw.scannedFiles);
    const matched = toOptionalNumberValue(statsRaw.matchedFiles);
    const symbolHits = toOptionalNumberValue(statsRaw.symbolHits);
    const astHits = toOptionalNumberValue(statsRaw.astHits);
    const importHits = toOptionalNumberValue(statsRaw.importHits);
    const followupSymbolHits = toOptionalNumberValue(statsRaw.followupSymbolHits);
    const followupImportHits = toOptionalNumberValue(statsRaw.followupImportHits);
    const queryPlanCount = toOptionalNumberValue(statsRaw.queryPlanCount);
    if (typeof scanned === 'number') stats.push(`Scanned: ${scanned}`);
    if (typeof matched === 'number') stats.push(`Matched: ${matched}`);
    if (typeof symbolHits === 'number') stats.push(`Symbol: ${symbolHits}`);
    if (typeof astHits === 'number') stats.push(`AST: ${astHits}`);
    if (typeof importHits === 'number') stats.push(`Import: ${importHits}`);
    if (typeof followupSymbolHits === 'number') stats.push(`Follow-up Symbol: ${followupSymbolHits}`);
    if (typeof followupImportHits === 'number') stats.push(`Follow-up Import: ${followupImportHits}`);
    if (typeof queryPlanCount === 'number') stats.push(`Plans: ${queryPlanCount}`);
    if (typeof statsRaw.graphAvailable === 'boolean') stats.push(`Graph: ${statsRaw.graphAvailable ? 'on' : 'off'}`);
  }

  const queryPlans = plansRaw.slice(0, 4).map((plan) => {
    const planQuery = toStringValue(plan.query, 'query');
    const kind = toStringValue(plan.kind, 'primary');
    const weight = typeof plan.weight === 'number' ? plan.weight : toNumberValue(plan.weight, 1);
    return `${kind}(${weight.toFixed(2)}): ${planQuery}`;
  });

  const decisionTrace = traceRaw.slice(0, 8).map((item) => ({
    step: toStringValue(item.step, 'step'),
    decision: toStringValue(item.decision, 'unknown'),
    reason: toStringValue(item.reason, ''),
    confidence: toStringValue(item.confidence),
  }));

  return { mode, strategy, stats, queryPlans, decisionTrace };
};

const toRagAnswer = (payload: CreateGraphPanelRagResponse | null): string => {
  const outputProtocol = getOutputProtocol(payload);
  const protocolAnalysis = isRecord(outputProtocol?.analysis) ? outputProtocol.analysis : null;
  const protocolSelectedPath = isRecord(protocolAnalysis?.selected_path) ? protocolAnalysis.selected_path : null;
  const protocolFunctionChain = Array.isArray(protocolSelectedPath?.function_chain)
    ? protocolSelectedPath.function_chain.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
  if (protocolAnalysis) {
    const lines: string[] = [];
    const summary = toStringValue(protocolAnalysis.summary);
    const keyReasoning = toStringArray(protocolAnalysis.key_reasoning);
    const selectionMode = toStringValue(protocolAnalysis.selection_mode);
    const selectionReason = toStringValue(protocolAnalysis.selection_reason);
    if (summary) lines.push(summary);
    if (protocolFunctionChain.length > 0) lines.push(`主路径: ${protocolFunctionChain.join(' -> ')}`);
    if (selectionMode) lines.push(`命中模式: ${selectionMode}`);
    if (selectionReason) lines.push(`命中原因: ${selectionReason}`);
    if (keyReasoning.length > 0) lines.push(...keyReasoning);
    return lines.join('\n');
  }
  const solutionPacket = isRecord(payload?.solution_packet) ? payload.solution_packet : null;
  const analysis = isRecord(solutionPacket?.analysis) ? solutionPacket.analysis : null;
  const summary = toStringValue(analysis?.summary);
  const keyReasoning = Array.isArray(analysis?.key_reasoning)
    ? analysis.key_reasoning.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
  const selectedPath = isRecord(analysis?.selected_path) ? analysis.selected_path : null;
  const functionChain = Array.isArray(selectedPath?.function_chain)
    ? selectedPath.function_chain.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
  const selectionMode = toStringValue(analysis?.selection_mode);
  const selectionReason = toStringValue(analysis?.selection_reason);

  const lines: string[] = [];
  if (summary) lines.push(summary);
  if (functionChain.length > 0) lines.push(`主路径: ${functionChain.join(' -> ')}`);
  if (selectionMode) lines.push(`命中模式: ${selectionMode}`);
  if (selectionReason) lines.push(`命中原因: ${selectionReason}`);
  if (keyReasoning.length > 0) lines.push(...keyReasoning);
  const directPayload = isRecord(payload) ? payload : null;
  const directAnswer = toStringValue(directPayload?.answer);
  if (directAnswer) return directAnswer;
  return lines.join('\n');
};

const toRagSnippetBlocks = (payload: CreateGraphPanelRagResponse | null): Array<Record<string, unknown>> => {
  const outputProtocol = getOutputProtocol(payload);
  if (Array.isArray(outputProtocol?.code_snippets)) {
    return outputProtocol.code_snippets.filter(isRecord);
  }
  const solutionPacket = isRecord(payload?.solution_packet) ? payload.solution_packet : null;
  return Array.isArray(solutionPacket?.snippet_blocks)
    ? solutionPacket.snippet_blocks.filter(isRecord)
    : [];
};

const toRagEditPlan = (payload: CreateGraphPanelRagResponse | null): Array<Record<string, unknown>> => {
  const solutionPacket = isRecord(payload?.solution_packet) ? payload.solution_packet : null;
  const editPlan = Array.isArray(solutionPacket?.edit_plan) ? solutionPacket.edit_plan : [];
  return Array.isArray(editPlan)
    ? editPlan.filter(isRecord)
    : [];
};

const toRagSwarmPayloadFromResponse = (payload: CreateGraphPanelRagResponse | null): Record<string, unknown> | null => {
  if (!isRecord(payload)) return null;
  const raw = (payload as Record<string, unknown>).swarm_packet;
  return isRecord(raw) ? raw : null;
};

const toRagSwarmPayloadFromStatus = (
  status: CreateGraphMultiAgentSessionStatusResponse | CreateGraphConversationSessionStatusResponse | null,
): Record<string, unknown> | null => {
  if (!isRecord(status)) return null;
  const raw = (status as Record<string, unknown>).swarm;
  return isRecord(raw) ? raw : null;
};

const toRagSwarmView = (payload: Record<string, unknown> | null): RagSwarmView | null => {
  if (!payload) return null;
  const consensusRaw = isRecord(payload.consensus) ? payload.consensus : null;
  const agentsRaw = isRecord(payload.agents) ? payload.agents : {};

  const consensus: RagSwarmConsensusView | null = consensusRaw
    ? {
      summary: toStringValue(consensusRaw.summary),
      confidence: toStringValue(consensusRaw.confidence, 'medium'),
      risks: toStringArray(consensusRaw.risks),
      actions: toStringArray(consensusRaw.actions),
    }
    : null;

  const agentKeys = [
    ...SWARM_AGENT_ORDER.filter((key) => Object.hasOwn(agentsRaw, key)),
    ...Object.keys(agentsRaw).filter((key) => !SWARM_AGENT_ORDER.includes(key)),
  ];

  const agents: RagSwarmAgentView[] = [];
  for (const key of agentKeys) {
    const agentRaw = agentsRaw[key];
    if (!isRecord(agentRaw)) continue;
    agents.push({
      key,
      name: SWARM_AGENT_LABELS[key] || key,
      summary: toStringValue(agentRaw.summary, '暂无摘要'),
      confidence: toStringValue(agentRaw.confidence, 'medium'),
      status: toStringValue(agentRaw.status, 'unknown'),
      risks: toStringArray(agentRaw.risks),
      actions: toStringArray(agentRaw.actions),
    });
  }

  if (!consensus && agents.length === 0) return null;
  return {
    enabled: toBooleanValue(payload.enabled, true),
    llmEnabled: toBooleanValue(payload.llm_enabled, false),
    model: toStringValue(payload.model),
    consensus,
    agents,
  };
};

const toRagExecutionCards = (
  payload: CreateGraphPanelRagResponse | null,
  swarm: RagSwarmView | null,
): RagExecutionCardView[] => {
  if (!payload) return [];

  const cards: RagExecutionCardView[] = [];
  const outputProtocol = getOutputProtocol(payload);
  const outputAnalysis = isRecord(outputProtocol?.analysis) ? outputProtocol.analysis : null;
  const protocolSummary = toStringValue(outputAnalysis?.summary, '执行摘要待补充');
  const protocolConfidence = toStringValue(isRecord(outputProtocol?.judgment) ? outputProtocol?.judgment?.confidence : undefined, 'medium');
  const protocolReasoning = toStringArray(outputAnalysis?.key_reasoning);
  const protocolImpactedFiles = toStringArray(outputAnalysis?.impacted_files);
  const protocolRisks = toStringArray(outputProtocol?.remaining_risks_constraints);
  const protocolConstraints = toStringArray(outputProtocol?.constraints);
  const basePreflightChecks = [
    ...protocolConstraints,
    '确认当前分支工作区干净（避免混入无关改动）',
    '确认目标文件路径与锚点可定位',
  ].filter((item, index, arr) => item && arr.indexOf(item) === index);
  const baseRollbackSuggestions = [
    '若单文件改动失败：优先回滚该文件并重跑验证',
    '若多文件联动失败：按执行顺序逆序回滚',
    '提交前保留变更快照，便于快速恢复',
  ];

  const editPlan = toRagEditPlan(payload);
  for (let index = 0; index < Math.min(editPlan.length, 8); index += 1) {
    const item = editPlan[index];
    const action = toStringValue(item.action, 'modify_file');
    const anchor = toStringValue(item.anchor, 'target');
    const filePath = toStringValue(item.file_path, '待定位');
    const reason = toStringValue(item.reason, protocolSummary);
    cards.push({
      id: `edit-${index + 1}`,
      title: `步骤 ${index + 1}：${action}`,
      summary: reason,
      confidence: protocolConfidence,
      steps: [`${action} @ ${anchor}`],
      targets: [filePath],
      risks: protocolRisks.slice(0, 3),
      preflightChecks: [
        ...basePreflightChecks,
        filePath.includes('待定位') ? '补全目标文件路径后再执行' : `确认目标文件存在：${filePath}`,
        '执行前先读取目标片段，确认锚点上下文一致',
      ].filter((item, idx, arr) => item && arr.indexOf(item) === idx),
      rollbackSuggestions: [
        filePath.includes('待定位') ? '路径未定位时禁止执行写入' : `回滚目标文件：${filePath}`,
        '若锚点替换失败：恢复原始片段后重新生成方案',
        ...baseRollbackSuggestions,
      ].filter((item, idx, arr) => item && arr.indexOf(item) === idx),
    });
  }

  if (swarm && swarm.agents.length > 0) {
    for (const agent of swarm.agents) {
      const combinedSteps = agent.actions.length > 0 ? agent.actions : [agent.summary];
      cards.push({
        id: `swarm-${agent.key}`,
        title: `${agent.name} 决策`,
        summary: agent.summary,
        confidence: agent.confidence,
        steps: combinedSteps,
        targets: [],
        risks: agent.risks,
        preflightChecks: [
          '确认上游阶段输出已就绪',
          '核对当前阶段输入与用户目标一致',
          ...(agent.actions.length > 0 ? ['逐条检查 agent action 是否可落地'] : []),
        ].filter((item, idx, arr) => item && arr.indexOf(item) === idx),
        rollbackSuggestions: [
          '若本阶段结论不稳定：回退到上一阶段重新审议',
          '保留当前阶段结论快照，避免反复漂移',
        ],
      });
    }
  }

  if (cards.length === 0) {
    cards.push({
      id: 'protocol-fallback',
        title: '执行蓝图',
      summary: protocolSummary,
      confidence: protocolConfidence,
      steps: protocolReasoning.length > 0 ? protocolReasoning : ['等待更多上下文后生成执行步骤'],
      targets: protocolImpactedFiles,
      risks: protocolRisks,
      preflightChecks: basePreflightChecks,
      rollbackSuggestions: baseRollbackSuggestions,
    });
  }

  if (swarm?.consensus) {
    cards.unshift({
      id: 'swarm-consensus',
       title: 'Swarm 共识执行单',
      summary: swarm.consensus.summary || protocolSummary,
      confidence: swarm.consensus.confidence || protocolConfidence,
      steps: swarm.consensus.actions.length > 0 ? swarm.consensus.actions : protocolReasoning,
      targets: protocolImpactedFiles,
      risks: [...swarm.consensus.risks, ...protocolConstraints].filter((item, idx, arr) => arr.indexOf(item) === idx).slice(0, 8),
      preflightChecks: [
        ...basePreflightChecks,
        '确认 Swarm 共识信心等级达到可执行门槛',
        '确认目标范围与 impacted files 一致',
      ].filter((item, idx, arr) => item && arr.indexOf(item) === idx),
      rollbackSuggestions: [
        '若共识与实际代码冲突：回退到 zhongshu/menxia 重新证据审议',
        ...baseRollbackSuggestions,
      ].filter((item, idx, arr) => item && arr.indexOf(item) === idx),
    });
  }

  return cards;
};

const toExecutionRunbookText = (cards: RagExecutionCardView[]): string => {
  if (cards.length === 0) return '';
  const lines: string[] = [];
  cards.forEach((card, index) => {
    lines.push(`${index + 1}. ${card.title}`);
    lines.push(`摘要：${card.summary}`);
    lines.push(`置信度：${card.confidence}`);
    if (card.targets.length > 0) {
        lines.push(`目标：${card.targets.join(', ')}`);
    }
    if (card.steps.length > 0) {
        lines.push('步骤：');
      card.steps.forEach((step, stepIndex) => {
        lines.push(`  ${index + 1}.${stepIndex + 1} ${step}`);
      });
    }
    if (card.risks.length > 0) {
        lines.push(`风险：${card.risks.join(' | ')}`);
    }
    if (card.preflightChecks.length > 0) {
        lines.push('执行前检查：');
      card.preflightChecks.forEach((item, preflightIndex) => {
        lines.push(`  P${index + 1}.${preflightIndex + 1} ${item}`);
      });
    }
    if (card.rollbackSuggestions.length > 0) {
        lines.push('回滚建议：');
      card.rollbackSuggestions.forEach((item, rollbackIndex) => {
        lines.push(`  R${index + 1}.${rollbackIndex + 1} ${item}`);
      });
    }
    lines.push('');
  });
  return lines.join('\n').trim();
};

const toSafeFileSegment = (value: string): string => {
  const normalized = value.trim().replace(/[^\w\u4e00-\u9fff-]+/g, '_').replace(/_+/g, '_');
  return normalized.replace(/^_+|_+$/g, '').slice(0, 40) || 'runbook';
};

const formatRunbookTimestamp = (): string => {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  const hh = String(now.getHours()).padStart(2, '0');
  const mi = String(now.getMinutes()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
};

const toExecutionRunbookMarkdown = (
  cards: RagExecutionCardView[],
  options: {
    conversationId?: string;
    stage?: string;
    judgmentStatus?: string;
    judgmentConfidence?: string;
    swarmSummary?: string;
    analysis?: string;
  },
): string => {
  const lines: string[] = [];
   lines.push('# 可执行 Runbook');
  lines.push('');
   lines.push(`- 生成时间：${formatRunbookTimestamp()}`);
   if (options.conversationId) lines.push(`- 会话 ID：${options.conversationId}`);
   if (options.stage) lines.push(`- 阶段：${options.stage}`);
  if (options.judgmentStatus || options.judgmentConfidence) {
     lines.push(`- 任务判断：${options.judgmentStatus || 'unknown'} (${options.judgmentConfidence || 'medium'})`);
  }
  lines.push('');

  if (options.swarmSummary) {
     lines.push('## Swarm 共识');
    lines.push(options.swarmSummary);
    lines.push('');
  }

  if (options.analysis) {
     lines.push('## 分析摘要');
    lines.push(options.analysis);
    lines.push('');
  }

   lines.push('## 执行卡片');
  lines.push('');

  cards.forEach((card, index) => {
    lines.push(`### ${index + 1}. ${card.title}`);
     lines.push(`- 置信度：${card.confidence}`);
     lines.push(`- 摘要：${card.summary}`);

    if (card.targets.length > 0) {
       lines.push('- 目标：');
      card.targets.forEach((target) => {
        lines.push(`  - ${target}`);
      });
    }

    if (card.steps.length > 0) {
       lines.push('- 步骤：');
      card.steps.forEach((step) => {
        lines.push(`  - ${step}`);
      });
    }

    if (card.preflightChecks.length > 0) {
       lines.push('- 执行前检查：');
      card.preflightChecks.forEach((item) => {
        lines.push(`  - ${item}`);
      });
    }

    if (card.rollbackSuggestions.length > 0) {
       lines.push('- 回滚建议：');
      card.rollbackSuggestions.forEach((item) => {
        lines.push(`  - ${item}`);
      });
    }

    if (card.risks.length > 0) {
       lines.push('- 风险：');
      card.risks.forEach((risk) => {
        lines.push(`  - ${risk}`);
      });
    }

    lines.push('');
  });

  return lines.join('\n').trim();
};

const toRagClarificationFromPendingQuestion = (
  pendingQuestion: CreateGraphConversationPendingQuestion,
  fallbackQuery: string,
  previousClarification: RagClarificationState | null,
): RagClarificationState => {
  const options = Array.isArray(pendingQuestion.options)
    ? pendingQuestion.options.map((item, index) => ({
      id: `opt-${index + 1}`,
      label: toStringValue(item?.label, `Option ${index + 1}`),
      description: toStringValue(item?.description),
      promptFragment: toStringValue(item?.label),
    }))
    : [];

  const round = typeof previousClarification?.round === 'number'
    ? previousClarification.round + 1
    : 1;
  return {
    id: toStringValue(pendingQuestion.questionId, `clarification-${Date.now()}`),
    round,
    maxRounds: Math.max(4, round),
    clarityLevel: toStringValue(pendingQuestion.source, 'needs_clarification'),
    inferredIntent: toStringValue(pendingQuestion.reason, '需要补充更多需求信息'),
    prompt: toStringValue(pendingQuestion.question, '请补充需求细节。'),
    options,
    allowFreeform: pendingQuestion.custom !== false,
    structuredFields: [],
    terminal: false,
    originalQuery: previousClarification?.originalQuery || fallbackQuery,
    selectedOptionIds: [],
    selectedOptionLabels: [],
  };
};

const toRagResponseFromConversationResult = (
  query: string,
  result: CreateGraphConversationSessionResultResponse,
): CreateGraphRagAskResponse => {
  const retrieval = isRecord(result.retrieval) ? result.retrieval : null;
  const highlights = Array.isArray(retrieval?.highlights) ? retrieval.highlights.filter(isRecord) : [];
  const evidence = highlights.map((item, index) => {
    const mappedLineStart = toOptionalNumberValue(item.lineStart) ?? toOptionalNumberValue(item.line_start);
    const mappedLineEnd = toOptionalNumberValue(item.lineEnd) ?? toOptionalNumberValue(item.line_end);
    return {
      rank: index + 1,
      label: toStringValue(item.label, toStringValue(item.id, `hit-${index + 1}`)),
      node_id: toStringValue(item.id),
      file_path: toStringValue(item.file, toStringValue(item.file_path, '未知文件')),
      score: typeof item.score === 'number' ? item.score : toNumberValue(item.score, 0),
      line_start: mappedLineStart,
      line_end: mappedLineEnd,
      lineStart: mappedLineStart,
      lineEnd: mappedLineEnd,
    };
  });
  return {
    query,
    answer: toStringValue(result.answer, toStringValue(result.reason, '已完成会话处理。')),
    evidence,
    retrieval_bundle: retrieval || undefined,
  };
};

export const RightPanel = () => {
  const {
    isRightPanelOpen,
    setRightPanelOpen,
    rightPanelTab,
    setRightPanelTab,
    projectName,
    availableRepos,
    serverBaseUrl,
    setHighlightedNodeIds,
    setSecondaryHighlightedNodeIds,
    fileContents,
    graph,
    selectedNode,
    setSelectedNode,
    returnToOnboarding,
    addCodeReference,
    // LLM / chat state
    chatMessages,
    isChatLoading,
    agentError,
    isAgentReady,
    isAgentInitializing,
    chatConversationId,
    chatConversationList,
    chatOutputRootPath,
    setChatOutputRootPath,
    refreshChatConversations,
    loadChatConversation,
    startNewChatConversation,
    sendChatMessage,
    stopChatResponse,
    clearChat,
  } = useAppState();

  const [chatInput, setChatInput] = useState('');

  const [advisorPriorityInput, setAdvisorPriorityInput] = useState('');

  const [hierarchyContract, setHierarchyContract] = useState<CreateGraphHierarchyContract | null>(null);
  const [hierarchyLoading, setHierarchyLoading] = useState(false);
  const [hierarchyError, setHierarchyError] = useState<string | null>(null);
  const [selectedPartitionId, setSelectedPartitionId] = useState<string>('');
  const [partitionAnalysis, setPartitionAnalysis] = useState<CreateGraphPartitionAnalysisResponse | null>(null);
  const [partitionAnalysisLoading, setPartitionAnalysisLoading] = useState(false);
  const [partitionAnalysisError, setPartitionAnalysisError] = useState<string | null>(null);
  const [selectedMethodKey, setSelectedMethodKey] = useState<string>('');
  const [hierarchyPage, setHierarchyPage] = useState<HierarchyPage>('list');
  const [hierarchySubview, setHierarchySubview] = useState<HierarchySubview>('info');
  const [selectedPathId, setSelectedPathId] = useState<string>('');
  const [pathDetailView, setPathDetailView] = useState<PathDetailView>('overview');

  const [ragInput, setRagInput] = useState('');
  const [experienceProjectStatus, setExperienceProjectStatus] = useState<CreateGraphWorkbenchProjectStatusResponse | null>(null);
  const [ragLoading, setRagLoading] = useState(false);
  const [ragError, setRagError] = useState<string | null>(null);
  const [ragResponse, setRagResponse] = useState<CreateGraphPanelRagResponse | null>(null);
  const [ragSessionStatus, setRagSessionStatus] = useState<
    CreateGraphMultiAgentSessionStatusResponse | CreateGraphConversationSessionStatusResponse | null
  >(null);
  const [ragClarification, setRagClarification] = useState<RagClarificationState | null>(null);
  const [ragConversationId, setRagConversationId] = useState<string | null>(null);
  const [ragEventCursor, setRagEventCursor] = useState<number>(0);
  const [ragLiveSwarmPayload, setRagLiveSwarmPayload] = useState<Record<string, unknown> | null>(null);
  const [ragProgressEvents, setRagProgressEvents] = useState<string[]>([]);
  const [ragTimelineCollapsed, setRagTimelineCollapsed] = useState<Partial<Record<RagTimelineGroupKey, boolean>>>({});
  const [ragReplayEntries, setRagReplayEntries] = useState<RagReplayEntryView[]>([]);
  const [ragReplayFilter, setRagReplayFilter] = useState('');
  const [activeRagReplayId, setActiveRagReplayId] = useState<string | null>(null);
  const [currentRagRunId, setCurrentRagRunId] = useState<string | null>(null);
  const [currentRagRunStartedAt, setCurrentRagRunStartedAt] = useState<number | null>(null);
  const [currentRagRunQuery, setCurrentRagRunQuery] = useState<string>('');
  const [copiedSnippetKey, setCopiedSnippetKey] = useState<string | null>(null);
  const [copiedExecutionCardKey, setCopiedExecutionCardKey] = useState<string | null>(null);
  const [savingRunbook, setSavingRunbook] = useState(false);
  const [savedRunbookPath, setSavedRunbookPath] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const partitionSummaries = useMemo(
    () => toPartitionSummaries(hierarchyContract),
    [hierarchyContract],
  );
  const hierarchyFunctions = useMemo(
    () => toHierarchyFunctions(hierarchyContract),
    [hierarchyContract],
  );

  const ragEvidence = useMemo(() => toRagEvidence(ragResponse), [ragResponse]);
  const ragJudgment = useMemo(() => toRagJudgment(ragResponse), [ragResponse]);
  const ragAnswer = useMemo(() => toRagAnswer(ragResponse), [ragResponse]);
  const ragSnippetBlocks = useMemo(() => toRagSnippetBlocks(ragResponse), [ragResponse]);
  const ragEditPlan = useMemo(() => toRagEditPlan(ragResponse), [ragResponse]);
  const ragRisks = useMemo(() => toRagRisks(ragResponse), [ragResponse]);
  const ragValidationCommands = useMemo(() => toRagValidationCommands(ragResponse), [ragResponse]);
  const ragRetrievalSummary = useMemo(() => toRagRetrievalSummary(ragResponse), [ragResponse]);
  const ragCandidatePaths = useMemo(() => {
    const outputProtocol = getOutputProtocol(ragResponse);
    const protocolAnalysis = isRecord(outputProtocol?.analysis) ? outputProtocol.analysis : null;
    const protocolCandidates = Array.isArray(protocolAnalysis?.candidate_paths)
      ? protocolAnalysis.candidate_paths.filter(isRecord)
      : [];
    const protocolSelectedPath = isRecord(protocolAnalysis?.selected_path) ? protocolAnalysis.selected_path : null;
  
    const solutionPacket = isRecord(ragResponse?.solution_packet) ? ragResponse.solution_packet : null;
    const solutionAnalysis = isRecord(solutionPacket?.analysis) ? solutionPacket.analysis : null;
    const solutionCandidates = Array.isArray(solutionAnalysis?.candidate_paths)
      ? solutionAnalysis.candidate_paths.filter(isRecord)
      : [];
    const solutionSelectedPath = isRecord(solutionAnalysis?.selected_path) ? solutionAnalysis.selected_path : null;
  
    const selectedPath = protocolSelectedPath || solutionSelectedPath;
    const selectedPathId = toStringValue(selectedPath?.path_id);
  
    const source = protocolCandidates.length > 0 ? protocolCandidates : solutionCandidates;
    const views = source.slice(0, 24).map((item, index) => {
      const pathId = toStringValue(item.path_id, `candidate_${index + 1}`);
      const functionChain = Array.isArray(item.function_chain)
        ? item.function_chain.filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
        : [];
      return {
        pathId,
        pathName: toStringValue(item.path_name, pathId),
        pathDescription: toStringValue(item.path_description),
        selectionScore: toOptionalNumberValue(item.selection_score),
        worthinessScore: toOptionalNumberValue(item.worthiness_score),
        selectionReason: toStringValue(item.selection_reason),
        source: toStringValue(item.source),
        functionChain,
        isSelected: selectedPathId ? pathId === selectedPathId : index === 0,
      };
    });
  
    if (views.length > 0) return views;
    if (!selectedPath) return [];
  
    const fallbackChain = Array.isArray(selectedPath.function_chain)
      ? selectedPath.function_chain.filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
      : [];
    return [{
      pathId: toStringValue(selectedPath.path_id, 'selected_path'),
      pathName: toStringValue(selectedPath.path_name, '主路径'),
      pathDescription: toStringValue(selectedPath.path_description),
      selectionScore: toOptionalNumberValue(selectedPath.selection_score),
      worthinessScore: toOptionalNumberValue(selectedPath.worthiness_score),
      selectionReason: toStringValue(selectedPath.selection_reason),
      source: toStringValue(selectedPath.source),
      functionChain: fallbackChain,
      isSelected: true,
    }];
  }, [ragResponse]);
  const ragAdvisor = useMemo(() => {
    const outputProtocol = getOutputProtocol(ragResponse);
    const protocolAnalysis = isRecord(outputProtocol?.analysis) ? outputProtocol.analysis : null;
    const analysisAdvisor = isRecord(protocolAnalysis?.advisor) ? protocolAnalysis.advisor : null;
    const protocolAdvisor = isRecord(outputProtocol?.advisor) ? outputProtocol.advisor : null;
  
    const solutionPacket = isRecord(ragResponse?.solution_packet) ? ragResponse.solution_packet : null;
    const solutionAnalysis = isRecord(solutionPacket?.analysis) ? solutionPacket.analysis : null;
    const solutionAdvisor = isRecord(solutionAnalysis?.advisor) ? solutionAnalysis.advisor : null;
  
    const advisor = analysisAdvisor || protocolAdvisor || solutionAdvisor;
    if (!advisor) return null;
  
    const analysis = isRecord(advisor.analysis) ? advisor.analysis : {};
    const constraints = isRecord(advisor.constraints) ? advisor.constraints : {};
    const structuredSummary = isRecord(constraints.structured_summary) ? constraints.structured_summary : {};
    const constraintTypes = toStringArray((advisor as Record<string, unknown>).constraint_types);
  
    return {
      status: toStringValue(advisor.status, 'disabled'),
      what: toStringValue(analysis.what),
      how: toStringValue(analysis.how),
      nextStep: toStringValue(analysis.next_step),
      constraintTypes: constraintTypes.length > 0 ? constraintTypes : toStringArray(constraints.types),
      plainConstraints: toStringArray(constraints.plain),
      sourceTargets: toStringArray((advisor as Record<string, unknown>).source_targets),
      followupAdvisors: toStringArray((advisor as Record<string, unknown>).followup_advisors),
      structuredSummaryLines: Object.entries(structuredSummary)
        .slice(0, 8)
        .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`),
    };
  }, [ragResponse]);
  const ragOpencodeKernel = useMemo(() => {
    const outputProtocol = getOutputProtocol(ragResponse);
    const protocolKernel = isRecord(outputProtocol?.opencode_kernel) ? outputProtocol.opencode_kernel : null;
    const solutionPacket = isRecord(ragResponse?.solution_packet) ? ragResponse.solution_packet : null;
    const packetKernel = isRecord(solutionPacket?.opencode_kernel) ? solutionPacket.opencode_kernel : null;
    const kernel = protocolKernel || packetKernel;
    if (!kernel) return null;
    return {
      status: toStringValue(kernel.status, 'disabled'),
      reason: toStringValue(kernel.reason),
      durationMs: toOptionalNumberValue(kernel.duration_ms),
      model: toStringValue(kernel.model),
      agent: toStringValue(kernel.agent),
      sessionId: toStringValue(kernel.session_id),
    };
  }, [ragResponse]);
  const ragSwarmLive = useMemo(
    () => toRagSwarmView(ragLiveSwarmPayload || toRagSwarmPayloadFromStatus(ragSessionStatus)),
    [ragLiveSwarmPayload, ragSessionStatus],
  );
  const ragSwarmFinal = useMemo(
    () => toRagSwarmView(toRagSwarmPayloadFromResponse(ragResponse)),
    [ragResponse],
  );
  const ragExecutionCards = useMemo(
    () => toRagExecutionCards(ragResponse, ragSwarmFinal),
    [ragResponse, ragSwarmFinal],
  );
  const ragExecutionRunbookText = useMemo(
    () => toExecutionRunbookText(ragExecutionCards),
    [ragExecutionCards],
  );
  const ragExecutionRunbookMarkdown = useMemo(
    () => toExecutionRunbookMarkdown(ragExecutionCards, {
      conversationId: ragConversationId || undefined,
      stage: toStringValue(ragSessionStatus?.stage),
      judgmentStatus: ragJudgment?.status,
      judgmentConfidence: ragJudgment?.confidence,
      swarmSummary: ragSwarmFinal?.consensus?.summary,
      analysis: ragAnswer,
    }),
    [
      ragExecutionCards,
      ragConversationId,
      ragJudgment?.confidence,
      ragJudgment?.status,
      ragSessionStatus?.stage,
      ragSwarmFinal?.consensus?.summary,
      ragAnswer,
    ],
  );
  const activeTab = rightPanelTab;
  const setActiveTab = setRightPanelTab;
  const ragTimelineItems = useMemo<RagTimelineItemView[]>(() => {
    const items: RagTimelineItemView[] = [];
    if (ragSessionStatus) {
      const stageKey = getRagStageKeyFromText(`${ragSessionStatus.stage} ${ragSessionStatus.message}`);
      items.push({
        id: `status-${ragSessionStatus.stage}-${ragSessionStatus.status}`,
        title: `阶段：${getStageDisplayText(ragSessionStatus.stage)}`,
        detail: ragSessionStatus.message,
        tone: ragSessionStatus.status === 'failed' ? 'warn' : ragSessionStatus.status === 'completed' ? 'success' : 'active',
        groupKey: stageKey === 'result' ? 'result' : 'session',
        stageKey,
      });
    }
    ragProgressEvents.forEach((event, index) => {
      const lower = event.toLowerCase();
      const [title, ...rest] = event.split('｜');
      const detail = rest.join('｜') || event;
      const stageKey = getRagStageKeyFromText(`${title} ${detail}`);
      items.push({
        id: `${index}-${event}`,
        title,
        detail,
        tone: lower.includes('失败') || lower.includes('failed')
          ? 'warn'
          : lower.includes('完成') || lower.includes('consensus')
            ? 'success'
            : lower.includes('启动') || lower.includes('阶段') || lower.includes('检索')
              ? 'active'
              : 'info',
        groupKey: getRagTimelineGroupKey(title, detail),
        stageKey,
      });
    });
    return items;
  }, [ragProgressEvents, ragSessionStatus]);
  const ragTimelineGroups = useMemo<RagTimelineGroupView[]>(() => {
    const order: RagTimelineGroupKey[] = ['session', 'retrieval', 'decision', 'swarm', 'clarification', 'result'];
    return order
      .map((groupKey) => {
        const items = ragTimelineItems.filter((item) => item.groupKey === groupKey);
        return {
          key: groupKey,
          title: RAG_TIMELINE_GROUP_LABELS[groupKey],
          status: getTimelineGroupStatus(items),
          items,
        };
      })
      .filter((group) => group.items.length > 0);
  }, [ragTimelineItems]);
  const ragCurrentStageKey = useMemo<RagStageKey>(() => {
    if (ragSessionStatus) return getRagStageKeyFromText(`${ragSessionStatus.stage} ${ragSessionStatus.message}`);
    if (ragResponse) return 'result';
    if (ragClarification) return 'judgment';
    return 'session';
  }, [ragClarification, ragResponse, ragSessionStatus]);
  const ragStageAnchors = useMemo<RagStageAnchorView[]>(() => {
    const stageOrder: RagStageKey[] = ['session', 'retrieval', 'judgment', 'swarm', 'result'];
    return stageOrder.map((stageKey) => {
      const items = ragTimelineItems.filter((item) => item.stageKey === stageKey);
      const baseStatus = items.some((item) => item.tone === 'warn')
        ? 'warn'
        : items.some((item) => item.tone === 'success')
          ? 'success'
          : items.length > 0
            ? 'active'
            : 'idle';
      const derivedStatus = stageKey === 'result' && ragResponse
        ? 'success'
        : stageKey === 'judgment' && (ragJudgment || ragClarification)
          ? ragClarification ? 'active' : 'success'
          : stageKey === 'retrieval' && (ragRetrievalSummary || ragEvidence.length > 0)
            ? 'success'
            : stageKey === 'swarm' && (ragSwarmFinal || ragSwarmLive?.agents.length)
              ? (ragSwarmFinal ? 'success' : 'active')
              : stageKey === 'session' && (currentRagRunId || ragSessionStatus)
                ? (ragLoading ? 'active' : 'success')
                : baseStatus;
      const status = ragLoading && ragCurrentStageKey === stageKey
        ? 'active'
        : derivedStatus;
      return {
        key: stageKey,
        label: RAG_STAGE_LABELS[stageKey],
        status,
      };
    });
  }, [
    currentRagRunId,
    ragClarification,
    ragCurrentStageKey,
    ragEvidence.length,
    ragJudgment,
    ragLoading,
    ragResponse,
    ragRetrievalSummary,
    ragSessionStatus,
    ragSwarmFinal,
    ragSwarmLive?.agents.length,
    ragTimelineItems,
  ]);
  const filteredRagReplayEntries = useMemo(
    () => ragReplayEntries.filter((entry) => matchesReplayFilter(entry, ragReplayFilter)),
    [ragReplayEntries, ragReplayFilter],
  );
  const activeProjectPath = useMemo(() => {
    if (availableRepos.length === 0) return undefined;
    const matchedPath = projectName
      ? availableRepos.find((repo) => repo.name === projectName)?.path
      : undefined;
    if (matchedPath) return matchedPath;
    if (availableRepos.length === 1) return availableRepos[0].path;
    return undefined;
  }, [availableRepos, projectName]);

  const prioritizedExperienceLibraries = useMemo(() => {
    const rawItems = advisorPriorityInput
      .split(/[,\n]+/)
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
    const deduped: string[] = [];
    for (const item of rawItems) {
      if (!deduped.includes(item)) deduped.push(item);
    }
    return deduped;
  }, [advisorPriorityInput]);

  const selectedPartitionSummary = useMemo(
    () => partitionSummaries.find((item) => item.partitionId === selectedPartitionId) ?? null,
    [partitionSummaries, selectedPartitionId],
  );

  const selectedHierarchyFunction = useMemo(
    () => hierarchyFunctions.find((item) => item.partitionId === selectedPartitionId) ?? null,
    [hierarchyFunctions, selectedPartitionId],
  );

  const partitionMethodKeys = useMemo(
    () => getPartitionMethodKeys(partitionAnalysis, selectedPartitionSummary, selectedHierarchyFunction),
    [partitionAnalysis, selectedPartitionSummary, selectedHierarchyFunction],
  );

  const selectedMethodDetail = useMemo(
    () => buildPartitionMethodDetail(selectedMethodKey, partitionAnalysis, hierarchyContract),
    [selectedMethodKey, partitionAnalysis, hierarchyContract],
  );
  const entryPoints = useMemo(() => toEntryPoints(partitionAnalysis), [partitionAnalysis]);
  const pathAnalyses = useMemo(() => toPathAnalyses(partitionAnalysis), [partitionAnalysis]);
  const hypergraphMethodKeys = useMemo(
    () => getHypergraphMethodKeys(partitionAnalysis, partitionMethodKeys),
    [partitionAnalysis, partitionMethodKeys],
  );
  const partitionRelatedMethodKeys = useMemo(
    () => getPartitionRelatedMethodKeys(partitionAnalysis, partitionMethodKeys),
    [partitionAnalysis, partitionMethodKeys],
  );
  const selectedPathAnalysis = useMemo(
    () => pathAnalyses.find((item) => item.id === selectedPathId) ?? null,
    [pathAnalyses, selectedPathId],
  );

  // Auto-scroll to bottom when messages update or while streaming
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  });

  const pushRagProgressEvent = useCallback((entry: string) => {
    if (!entry.trim()) return;
    setRagProgressEvents((current) => {
      const next = [...current, entry.trim()];
      return next.slice(-30);
    });
  }, []);

  const resolveFilePathForUI = useCallback((requestedPath: string): string | null => {
    const req = requestedPath.replace(/\\/g, '/').replace(/^\.?\//, '').toLowerCase();
    if (!req) return null;

    // Exact match first (case-insensitive)
    for (const key of fileContents.keys()) {
      const norm = key.replace(/\\/g, '/').replace(/^\.?\//, '').toLowerCase();
      if (norm === req) return key;
    }

    // Ends-with match (best for partial paths)
    let best: { path: string; score: number } | null = null;
    for (const key of fileContents.keys()) {
      const norm = key.replace(/\\/g, '/').replace(/^\.?\//, '').toLowerCase();
      if (norm.endsWith(req)) {
        const score = 1000 - norm.length;
        if (!best || score > best.score) best = { path: key, score };
      }
    }
    return best?.path ?? null;
  }, [fileContents]);

  const findFileNodeIdForUI = useCallback((filePath: string): string | undefined => {
    if (!graph) return undefined;
    const target = filePath.replace(/\\/g, '/').replace(/^\.?\//, '');
    const node = graph.nodes.find(
      (n) => n.label === 'File' && n.properties.filePath.replace(/\\/g, '/').replace(/^\.?\//, '') === target,
    );
    return node?.id;
  }, [graph]);

  const loadHierarchyContract = useCallback(async () => {
    if (!activeProjectPath) {
      setHierarchyLoading(false);
      setHierarchyError(null);
      return;
    }

    setHierarchyLoading(true);
    setHierarchyError(null);
    try {
      const payload = await createGraphExtensionsApi.fetchHierarchyContract('/api', activeProjectPath);
      setHierarchyContract(payload);
      const summaries = toPartitionSummaries(payload);
      if (!selectedPartitionId && summaries.length > 0) {
        setSelectedPartitionId(summaries[0].partitionId);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setHierarchyError(message);
    } finally {
      setHierarchyLoading(false);
    }
  }, [activeProjectPath, selectedPartitionId]);

  useEffect(() => {
    if (!activeProjectPath) {
      setExperienceProjectStatus(null);
      return;
    }
    let cancelled = false;
    const syncProjectStatus = async () => {
      try {
        const payload = await createGraphExtensionsApi.fetchWorkbenchProjectStatus('/api', activeProjectPath);
        if (!cancelled) {
          setExperienceProjectStatus(payload);
        }
      } catch {
        if (!cancelled) {
          setExperienceProjectStatus(null);
        }
      }
    };
    syncProjectStatus();
    const timer = window.setInterval(syncProjectStatus, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeProjectPath]);

  const loadPartitionAnalysis = useCallback(async (partitionId: string) => {
    if (!partitionId) {
      setPartitionAnalysis(null);
      setPartitionAnalysisError(null);
      setPartitionAnalysisLoading(false);
      return;
    }

    if (!activeProjectPath) {
      setPartitionAnalysis(null);
      setPartitionAnalysisError(null);
      setPartitionAnalysisLoading(false);
      return;
    }

    setPartitionAnalysisLoading(true);
    setPartitionAnalysisError(null);
    try {
      const payload = await createGraphExtensionsApi.fetchPartitionAnalysis('/api', partitionId, activeProjectPath);
      setPartitionAnalysis(payload);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setPartitionAnalysis(null);
      setPartitionAnalysisError(message);
    } finally {
      setPartitionAnalysisLoading(false);
    }
  }, [activeProjectPath]);

  const handleOpenLocalPathAnalysis = useCallback(() => {
    setRightPanelOpen(false);
    returnToOnboarding('path');
  }, [returnToOnboarding, setRightPanelOpen]);

  const highlightMethodCollectionInWorkspace = useCallback((methodKeys: string[], preferredMethodKey?: string) => {
    if (!graph || methodKeys.length === 0) return;

    const normalizedTargets = methodKeys.map((methodKey) => normalizeSymbolName(methodKey.split('.').pop() ?? methodKey)).filter(Boolean);
    const targetSet = new Set(normalizedTargets);
    const methodNodes = graph.nodes.filter((node) => {
      if (node.label !== 'Method' && node.label !== 'Function') return false;
      const methodName = normalizeSymbolName(node.properties.name ?? '');
      if (!methodName) return false;
      if (targetSet.has(methodName)) return true;
      for (const target of targetSet) {
        if (methodName.endsWith(target) || target.endsWith(methodName)) return true;
      }
      return false;
    });

    if (methodNodes.length === 0) return;

    const primaryIds = new Set(methodNodes.map((node) => node.id));
    const secondaryIds = new Set<string>();
    const relationByNode = graph.relationships.filter((rel) => primaryIds.has(rel.sourceId) || primaryIds.has(rel.targetId));
    for (const rel of relationByNode) {
      const neighborId = primaryIds.has(rel.sourceId) ? rel.targetId : rel.sourceId;
      if (primaryIds.has(neighborId)) continue;
      const neighborNode = graph.nodes.find((node) => node.id === neighborId);
      if (!neighborNode) continue;
      if (neighborNode.label === 'Class' || neighborNode.label === 'Interface' || neighborNode.label === 'File' || neighborNode.label === 'Module') {
        secondaryIds.add(neighborId);
      }
    }

    setHighlightedNodeIds(primaryIds);
    setSecondaryHighlightedNodeIds(secondaryIds);

    const preferredNormalized = preferredMethodKey ? normalizeSymbolName(preferredMethodKey.split('.').pop() ?? preferredMethodKey) : '';
    const primaryNode = methodNodes.find((node) => normalizeSymbolName(node.properties.name ?? '') === preferredNormalized) ?? methodNodes[0];
    setSelectedNode(primaryNode);

    if (primaryNode.properties.filePath) {
      const resolvedPath = resolveFilePathForUI(primaryNode.properties.filePath);
      if (resolvedPath) {
        addCodeReference({
          filePath: resolvedPath,
          startLine: typeof primaryNode.properties.startLine === 'number' ? primaryNode.properties.startLine - 1 : undefined,
          endLine: typeof primaryNode.properties.endLine === 'number' ? primaryNode.properties.endLine - 1 : undefined,
          nodeId: primaryNode.id,
          label: primaryNode.label,
          name: primaryNode.properties.name,
          source: 'user',
        });
      }
    }
  }, [addCodeReference, graph, resolveFilePathForUI, setHighlightedNodeIds, setSecondaryHighlightedNodeIds, setSelectedNode]);

  const focusPartitionInWorkspace = useCallback((summary: PartitionSummaryView) => {
    highlightMethodCollectionInWorkspace(summary.methods);
  }, [highlightMethodCollectionInWorkspace]);

  const focusMethodInWorkspace = useCallback((methodKey: string) => {
    highlightMethodCollectionInWorkspace([methodKey], methodKey);
  }, [highlightMethodCollectionInWorkspace]);

  useEffect(() => {
    if ((activeTab === 'hierarchy' || activeTab === 'rag') && !hierarchyContract && !hierarchyLoading) {
      loadHierarchyContract();
    }
  }, [activeTab, hierarchyContract, hierarchyLoading, loadHierarchyContract]);

  useEffect(() => {
    if (activeTab !== 'hierarchy') return;
    if (!selectedPartitionId) {
      setHierarchyPage('list');
      return;
    }
    if (hierarchyPage === 'list') return;
  }, [activeTab, hierarchyPage, selectedPartitionId]);

  useEffect(() => {
    if (activeTab !== 'hierarchy') return;
    if (!selectedPartitionId) {
      setPartitionAnalysis(null);
      setPartitionAnalysisError(null);
      setSelectedMethodKey('');
      setSelectedPathId('');
      setHierarchyPage('list');
      return;
    }
    loadPartitionAnalysis(selectedPartitionId);
  }, [activeTab, loadPartitionAnalysis, selectedPartitionId]);

  useEffect(() => {
    if (!selectedPartitionId) {
      setSelectedMethodKey('');
      return;
    }
    if (partitionMethodKeys.length === 0) {
      setSelectedMethodKey('');
      return;
    }
    if (!selectedMethodKey || !partitionMethodKeys.includes(selectedMethodKey)) {
      setSelectedMethodKey(partitionMethodKeys[0]);
    }
  }, [partitionMethodKeys, selectedMethodKey, selectedPartitionId]);

  useEffect(() => {
    if (pathAnalyses.length === 0) {
      setSelectedPathId('');
      setPathDetailView('overview');
      return;
    }
    if (!selectedPathId || !pathAnalyses.some((item) => item.id === selectedPathId)) {
      setSelectedPathId(pathAnalyses[0].id);
      setPathDetailView('overview');
    }
  }, [pathAnalyses, selectedPathId]);

  useEffect(() => {
    if (activeTab !== 'hierarchy' || !selectedPartitionId || partitionAnalysisLoading) return;
    if (hierarchyPage === 'path' && selectedPathAnalysis) {
      highlightMethodCollectionInWorkspace(selectedPathAnalysis.methods, selectedPathAnalysis.methods[0]);
      return;
    }
    if (partitionRelatedMethodKeys.length > 0) {
      highlightMethodCollectionInWorkspace(partitionRelatedMethodKeys, selectedMethodKey || partitionRelatedMethodKeys[0]);
    }
  }, [activeTab, hierarchyPage, selectedMethodKey, selectedPartitionId, selectedPathAnalysis, partitionAnalysisLoading, partitionRelatedMethodKeys, highlightMethodCollectionInWorkspace]);

  const handleGroundingClick = useCallback((inner: string) => {
    const raw = inner.trim();
    if (!raw) return;

    let rawPath = raw;
    let startLine1: number | undefined;
    let endLine1: number | undefined;

    // Match line:num or line:num-num (supports both hyphen - and en dash –)
    const lineMatch = raw.match(/^(.*):(\d+)(?:[-–](\d+))?$/);
    if (lineMatch) {
      rawPath = lineMatch[1].trim();
      startLine1 = parseInt(lineMatch[2], 10);
      endLine1 = parseInt(lineMatch[3] || lineMatch[2], 10);
    }

    const resolvedPath = resolveFilePathForUI(rawPath);
    if (!resolvedPath) return;

    const nodeId = findFileNodeIdForUI(resolvedPath);

    addCodeReference({
      filePath: resolvedPath,
      startLine: startLine1 ? Math.max(0, startLine1 - 1) : undefined,
      endLine: endLine1
        ? Math.max(0, endLine1 - 1)
        : (startLine1 ? Math.max(0, startLine1 - 1) : undefined),
      nodeId,
      label: 'File',
      name: resolvedPath.split('/').pop() ?? resolvedPath,
      source: 'ai',
    });
  }, [addCodeReference, findFileNodeIdForUI, resolveFilePathForUI]);

  // Handler for node grounding: [[Class:View]], [[Function:trigger]], etc.
  const handleNodeGroundingClick = useCallback((nodeTypeAndName: string) => {
    const raw = nodeTypeAndName.trim();
    if (!raw || !graph) return;

    // Parse Type:Name format
    const match = raw.match(/^(Class|Function|Method|Interface|File|Folder|Variable|Enum|Type|CodeElement):(.+)$/);
    if (!match) return;

    const [, nodeType, nodeName] = match;
    const trimmedName = nodeName.trim();

    // Find node in graph by type + name
    const node = graph.nodes.find(
      (n) => n.label === nodeType && n.properties.name === trimmedName,
    );

    if (!node) {
      console.warn(`Node not found: ${nodeType}:${trimmedName}`);
      return;
    }

    // Add to Code Panel (if node has file/line info)
    if (node.properties.filePath) {
      const resolvedPath = resolveFilePathForUI(node.properties.filePath);
      if (resolvedPath) {
        addCodeReference({
          filePath: resolvedPath,
          startLine: node.properties.startLine ? node.properties.startLine - 1 : undefined,
          endLine: node.properties.endLine ? node.properties.endLine - 1 : undefined,
          nodeId: node.id,
          label: node.label,
          name: node.properties.name,
          source: 'ai',
        });
      }
    }
  }, [graph, resolveFilePathForUI, addCodeReference]);

  const handleLinkClick = useCallback((href: string) => {
    if (href.startsWith('code-ref:')) {
      const inner = decodeURIComponent(href.slice('code-ref:'.length));
      handleGroundingClick(inner);
    } else if (href.startsWith('node-ref:')) {
      const inner = decodeURIComponent(href.slice('node-ref:'.length));
      handleNodeGroundingClick(inner);
    }
  }, [handleGroundingClick, handleNodeGroundingClick]);

  // Auto-resize textarea as user types
  const adjustTextareaHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = 'auto';
    const maxHeight = 160; // ~6 lines
    const newHeight = Math.min(textarea.scrollHeight, maxHeight);
    textarea.style.height = `${newHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [adjustTextareaHeight]);

  const buildRagReplaySnapshot = useCallback((query: string): RagReplaySnapshot => ({
    query,
    error: ragError,
    response: ragResponse,
    sessionStatus: ragSessionStatus,
    clarification: ragClarification,
    conversationId: ragConversationId,
    eventCursor: ragEventCursor,
    liveSwarmPayload: ragLiveSwarmPayload,
    progressEvents: [...ragProgressEvents],
    savedRunbookPath: savedRunbookPath,
  }), [
    ragClarification,
    ragConversationId,
    ragError,
    ragEventCursor,
    ragLiveSwarmPayload,
    ragProgressEvents,
    ragResponse,
    ragSessionStatus,
    savedRunbookPath,
  ]);

  useEffect(() => {
    if (!currentRagRunId || !currentRagRunStartedAt || !currentRagRunQuery.trim()) return;
    const status = ragError
      ? 'failed'
      : ragClarification
        ? 'needs_clarification'
        : ragSessionStatus?.status || (ragResponse ? 'completed' : ragLoading ? 'running' : 'idle');
    const stage = ragSessionStatus?.stage || (ragResponse ? 'result' : ragClarification ? 'clarification' : 'session');
    const snapshot = buildRagReplaySnapshot(currentRagRunQuery);
    setRagReplayEntries((current) => {
      const nextEntry: RagReplayEntryView = {
        id: currentRagRunId,
        query: currentRagRunQuery,
        createdAt: currentRagRunStartedAt,
        updatedAt: Date.now(),
        status,
        stage,
        snapshot,
      };
      const filtered = current.filter((item) => item.id !== currentRagRunId);
      return [nextEntry, ...filtered].slice(0, 8);
    });
  }, [
    buildRagReplaySnapshot,
    currentRagRunId,
    currentRagRunQuery,
    currentRagRunStartedAt,
    ragClarification,
    ragError,
    ragLoading,
    ragResponse,
    ragSessionStatus,
  ]);

  const handleRestoreRagReplay = useCallback((entry: RagReplayEntryView) => {
    setActiveRagReplayId(entry.id);
    setCurrentRagRunId(entry.id);
    setCurrentRagRunStartedAt(entry.createdAt);
    setCurrentRagRunQuery(entry.query);
    setRagInput(entry.snapshot.query);
    setRagError(entry.snapshot.error);
    setRagResponse(entry.snapshot.response);
    setRagSessionStatus(entry.snapshot.sessionStatus);
    setRagClarification(entry.snapshot.clarification);
    setRagConversationId(entry.snapshot.conversationId);
    setRagEventCursor(entry.snapshot.eventCursor);
    setRagLiveSwarmPayload(entry.snapshot.liveSwarmPayload);
    setRagProgressEvents(entry.snapshot.progressEvents);
    setSavedRunbookPath(entry.snapshot.savedRunbookPath);
    setRagLoading(false);
  }, []);

  const handleExportRagReplay = useCallback((entry: RagReplayEntryView) => {
    const answerSummary = entry.snapshot.error
      ? ''
      : toRagAnswer(entry.snapshot.response).slice(0, 400);
    const exportText = toReplayExportText(entry, {
      answerSummary,
      stageLabel: getStageDisplayText(entry.stage),
      statusLabel: getReplayStatusDisplayText(entry.status),
    });
    try {
      const fileName = `${toSafeFileSegment(entry.id)}_${new Date(entry.updatedAt).toISOString().replace(/[:T]/g, '-').slice(0, 16)}.md`;
      const blob = new Blob([exportText], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = fileName;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (_error) {
      setRagError('导出回看记录失败，请重试');
    }
  }, []);

  const toggleTimelineGroup = useCallback((groupKey: RagTimelineGroupKey) => {
    setRagTimelineCollapsed((current) => ({
      ...current,
      [groupKey]: !current[groupKey],
    }));
  }, []);

  // Chat handlers
  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;
    const text = chatInput.trim();
    setChatInput('');
    // Reset textarea height after sending
    if (textareaRef.current) {
      textareaRef.current.style.height = '36px';
      textareaRef.current.style.overflowY = 'hidden';
    }
    await sendChatMessage(text, { prioritizedExperienceLibraries });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleAskRag = useCallback(async () => {
    const query = ragInput.trim();
    if (!query) return;
    const runId = `rag-run-${Date.now()}`;

    setRagLoading(true);
    setRagError(null);
    setRagResponse(null);
    setRagSessionStatus(null);
    setRagLiveSwarmPayload(null);
    setRagProgressEvents([]);
    setCopiedExecutionCardKey(null);
    setSavedRunbookPath(null);
    setCurrentRagRunId(runId);
    setCurrentRagRunStartedAt(Date.now());
    setCurrentRagRunQuery(query);
    setActiveRagReplayId(runId);

    try {
      const activeClarification = ragClarification && !ragClarification.terminal
        ? ragClarification
        : null;
      const selectedNodePayload = selectedNode
        ? {
            id: selectedNode.id,
            name: selectedNode.properties.name,
          label: selectedNode.properties.name,
          type: selectedNode.label,
          file_path: selectedNode.properties.filePath,
          start_line: selectedNode.properties.startLine,
            end_line: selectedNode.properties.endLine,
          }
        : undefined;

      const normalizedOutputRoot = chatOutputRootPath.trim();
      const finalClarificationContext = activeClarification ? {
        id: activeClarification.id,
        round: activeClarification.round,
        originalQuery: activeClarification.originalQuery,
        latestUserReply: query,
        selectedOptionIds: activeClarification.selectedOptionIds,
        selectedOptionLabels: activeClarification.selectedOptionLabels,
        inferredIntent: activeClarification.inferredIntent,
        prioritizedExperienceLibraries: prioritizedExperienceLibraries,
      } : {
        prioritizedExperienceLibraries: prioritizedExperienceLibraries,
      };
      const llmConfig = buildBackendConversationLLMConfig();

      const startResponse = activeClarification && ragConversationId
        ? await createGraphExtensionsApi.replyConversation('/api', ragConversationId, {
          project_path: activeProjectPath,
          answer: query,
          selectedOptionLabels: activeClarification.selectedOptionLabels,
          clarification_context: finalClarificationContext,
          llm_config: llmConfig || undefined,
          auto_start_multi_agent: true,
          opencode_enabled: true,
          output_root: normalizedOutputRoot || undefined,
          auto_apply_output: Boolean(normalizedOutputRoot),
        })
        : await createGraphExtensionsApi.startConversationSession('/api', {
          query,
          project_path: activeProjectPath,
          conversation_id: ragConversationId || undefined,
          selected_node: selectedNodePayload,
          partition_id: selectedPartitionId || undefined,
          clarification_context: finalClarificationContext,
          llm_config: llmConfig || undefined,
          auto_start_multi_agent: true,
          opencode_enabled: true,
          output_root: normalizedOutputRoot || undefined,
          auto_apply_output: Boolean(normalizedOutputRoot),
        });

      const sessionId = startResponse.sessionId;
      const conversationId = startResponse.conversationId;
      setRagConversationId(conversationId);
      setRagSessionStatus({
        sessionId,
        conversationId,
        projectPath: startResponse.projectPath,
        status: startResponse.status,
        stage: startResponse.stage,
        message: startResponse.message,
      });
       pushRagProgressEvent(`会话已启动｜${startResponse.stage}`);

      let latestSeq = ragEventCursor;
      let sessionFinishedByStream = false;
      const streamAbortController = new AbortController();
      const streamTimeoutHandle = window.setTimeout(() => {
        streamAbortController.abort();
      }, 130_000);
      const streamPromise = createGraphExtensionsApi.streamConversationEvents('/api', conversationId, {
        since: latestSeq,
        sessionId,
        timeoutSeconds: 120,
        intervalMs: 700,
        signal: streamAbortController.signal,
        onBootstrap: (bootstrap) => {
          if (typeof bootstrap.cursor === 'number' && Number.isFinite(bootstrap.cursor)) {
            latestSeq = Math.max(latestSeq, bootstrap.cursor);
          }
          if (bootstrap.pendingQuestion) {
            pushRagProgressEvent('澄清待补充｜请补充更多上下文');
          }
        },
        onEvent: (event) => {
          if (typeof event.id === 'number' && Number.isFinite(event.id)) {
            latestSeq = Math.max(latestSeq, event.id);
          }
          const payload = isRecord(event.data) ? event.data : {};
          const seq = toNumberValue(payload.seq, 0);
          if (seq > 0) {
            latestSeq = Math.max(latestSeq, seq);
          }

          if (event.event === 'turn.state_changed') {
            const stage = toStringValue(payload.stage, 'running');
            const status = toStringValue(payload.status, 'running');
            const message = toStringValue(payload.message, stage);
            setRagSessionStatus({
              sessionId,
              conversationId,
              projectPath: activeProjectPath || '',
              status,
              stage,
              message,
            });
             pushRagProgressEvent(`${stage}｜${message}`);
            if (status === 'completed' || status === 'failed') {
              sessionFinishedByStream = true;
              return true;
            }
            return false;
          }

          if (event.event === 'turn.decided') {
             pushRagProgressEvent(`路由决策｜${toStringValue(payload.action, 'unknown')}`);
            return false;
          }

          if (event.event === 'retrieval.progress') {
             const message = toStringValue(payload.message, '正在检索证据');
            pushRagProgressEvent(message);
            return false;
          }

          if (event.event === 'tool.run_hybrid_shadow.completed') {
            const hits = toNumberValue(payload.highlightsCount, 0);
             pushRagProgressEvent(`检索完成｜命中 ${hits} 条证据`);
            return false;
          }

          if (event.event === 'clarification.requested') {
             pushRagProgressEvent('需要补充澄清');
            return false;
          }

          if (event.event === 'conversation.compacted') {
            const count = toNumberValue(payload.compressedMessageCount, 0);
             pushRagProgressEvent(`上下文压缩｜已压缩 ${count} 条消息`);
            return false;
          }

          if (event.event === 'task.handoff.auto_started') {
             pushRagProgressEvent('已自动切入多代理流程');
            return false;
          }

          if (event.event === 'multi_agent.started') {
             pushRagProgressEvent('多代理执行已启动');
            return false;
          }

          if (event.event === 'multi_agent.stage') {
            const stage = toStringValue(payload.stage, 'unknown');
            const message = toStringValue(payload.message, stage);
             pushRagProgressEvent(`Swarm 阶段｜${stage}｜${message}`);
            return false;
          }

          if (event.event === 'swarm.agent.updated') {
            const agentKey = toStringValue(payload.agent, 'agent');
            const decision = isRecord(payload.decision) ? payload.decision : {};
            setRagLiveSwarmPayload((current) => {
              const base = isRecord(current) ? current : {};
              const currentAgentsRaw = base.agents;
              const currentAgents = isRecord(currentAgentsRaw) ? currentAgentsRaw : {};
              return {
                ...base,
                enabled: true,
                agents: {
                  ...currentAgents,
                  [agentKey]: decision,
                },
              };
            });
             pushRagProgressEvent(`Swarm 角色｜${agentKey}｜${toStringValue(decision.summary, '已更新')}`);
            return false;
          }

          if (event.event === 'swarm.consensus.updated') {
            const consensus = isRecord(payload.consensus) ? payload.consensus : {};
            setRagLiveSwarmPayload((current) => {
              const base = isRecord(current) ? current : {};
              return {
                ...base,
                enabled: true,
                llm_enabled: toBooleanValue(payload.llm_enabled, toBooleanValue(base.llm_enabled, false)),
                model: toStringValue(payload.model, toStringValue(base.model, '')),
                consensus,
              };
            });
             pushRagProgressEvent(`Swarm 共识｜置信度 ${toStringValue(consensus.confidence, 'medium')}`);
            return false;
          }

          if (event.event === 'multi_agent.completed') {
            sessionFinishedByStream = true;
             pushRagProgressEvent('多代理执行完成');
            return true;
          }

          if (event.event === 'multi_agent.failed') {
            sessionFinishedByStream = true;
             pushRagProgressEvent(`多代理执行失败｜${toStringValue(payload.error, 'unknown error')}`);
            return true;
          }

          if (event.event === 'turn.failed' || event.event === 'turn.completed') {
            sessionFinishedByStream = true;
            return true;
          }

          return false;
        },
      });
      try {
        let finalStatus: CreateGraphConversationSessionStatusResponse | null = null;
        for (let attempt = 0; attempt < 90; attempt += 1) {
        const status = await createGraphExtensionsApi.fetchConversationSessionStatus('/api', sessionId);
        setRagSessionStatus(status);
        finalStatus = status;
        if (status.status === 'completed') {
          break;
        }
        if (status.status === 'failed') {
          throw new Error(status.error || status.message || 'Conversation session failed');
        }
        if (sessionFinishedByStream && attempt > 10) {
          break;
        }
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
        }

        streamAbortController.abort();

        let streamResult: CreateGraphConversationStreamResult | null = null;
        try {
          streamResult = await Promise.race([
            streamPromise,
            new Promise<CreateGraphConversationStreamResult | null>((resolve) => {
              window.setTimeout(() => resolve(null), 1800);
            }),
          ]);
        } catch (streamError) {
          const streamMessage = streamError instanceof Error ? streamError.message : String(streamError);
           pushRagProgressEvent(`流式读取回退｜${streamMessage}`);
        }

        if (streamResult) {
          latestSeq = Math.max(latestSeq, streamResult.lastSeq);
          if (streamResult.streamEnded) {
             pushRagProgressEvent(`流式结束｜${streamResult.endReason || 'timeout'}`);
          }
        }
        setRagEventCursor(latestSeq);

        if (!finalStatus || finalStatus.status !== 'completed') {
          throw new Error('会话处理超时（已停止长轮询）。请重试，或缩小问题范围。');
        }

        const conversationResult = await createGraphExtensionsApi.fetchConversationSessionResult('/api', sessionId);

        if (conversationResult.nextStep === 'ask_clarification' && conversationResult.pendingQuestion) {
        pushRagProgressEvent('结果产出｜需要先补充澄清信息');
        setRagClarification(
          toRagClarificationFromPendingQuestion(
            conversationResult.pendingQuestion,
            activeClarification?.originalQuery || query,
            activeClarification,
          ),
        );
        setRagResponse(null);
        setRagInput('');
        return;
      }

        setRagClarification(null);

        if (conversationResult.nextStep === 'start_multi_agent') {
          const handoff = isRecord(conversationResult.handoff) ? conversationResult.handoff : null;
          const multiAgentSessionId = toStringValue(handoff?.multiAgentSessionId);
          if (multiAgentSessionId) {
            let multiAgentFinalStatus: CreateGraphMultiAgentSessionStatusResponse | null = null;
          for (let attempt = 0; attempt < 90; attempt += 1) {
            const status = await createGraphExtensionsApi.fetchMultiAgentSessionStatus('/api', multiAgentSessionId);
            setRagSessionStatus(status);
            multiAgentFinalStatus = status;
            if (status.status === 'completed') {
              break;
            }
            if (status.status === 'failed') {
              throw new Error(status.error || status.message || 'Multi-agent session failed');
            }
            await new Promise((resolve) => window.setTimeout(resolve, 1000));
          }

          if (!multiAgentFinalStatus || multiAgentFinalStatus.status !== 'completed') {
            throw new Error('Multi-agent 执行超时（已停止长轮询）。请改为手动触发执行。');
          }

          const response = await createGraphExtensionsApi.fetchMultiAgentSessionResult('/api', multiAgentSessionId);
          setRagResponse(response);
          pushRagProgressEvent('结果产出｜多代理结果已返回');
          setRagInput('');
          return;
        }
      }

        const mappedResponse = toRagResponseFromConversationResult(query, conversationResult as CreateGraphConversationSessionResultResponse);
        setRagResponse(mappedResponse);
        pushRagProgressEvent('结果产出｜回答已生成');
        setRagInput('');
      } finally {
        window.clearTimeout(streamTimeoutHandle);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRagError(message);
    } finally {
      setRagLoading(false);
    }
  }, [
    activeProjectPath,
    chatOutputRootPath,
    prioritizedExperienceLibraries,
    ragClarification,
    ragConversationId,
    ragEventCursor,
    ragInput,
    selectedNode,
    selectedPartitionId,
    pushRagProgressEvent,
  ]);

  const handleClarificationOptionSelect = useCallback((option: CreateGraphClarificationOption) => {
    setRagClarification((current) => current ? {
      ...current,
      selectedOptionIds: [option.id],
      selectedOptionLabels: [option.label],
    } : current);
    setRagInput(option.promptFragment || option.label);
  }, []);

  const handleCopySnippet = useCallback(async (snippetKey: string, code: string) => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopiedSnippetKey(snippetKey);
      window.setTimeout(() => setCopiedSnippetKey((current) => current === snippetKey ? null : current), 1600);
    } catch (_error) {
      setRagError('复制代码片段失败，请手动复制');
    }
  }, []);

  const handleCopyExecutionText = useCallback(async (copyKey: string, text: string) => {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedExecutionCardKey(copyKey);
      window.setTimeout(() => {
        setCopiedExecutionCardKey((current) => (current === copyKey ? null : current));
      }, 1800);
    } catch (_error) {
      setRagError('复制执行工单失败，请手动复制');
    }
  }, []);

  const handleDownloadExecutionMarkdown = useCallback((markdown: string) => {
    if (!markdown.trim()) return;
    try {
      const conversationSegment = toSafeFileSegment(ragConversationId || 'conversation');
      const stageSegment = toSafeFileSegment(toStringValue(ragSessionStatus?.stage, 'stage'));
      const timeSegment = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 16);
      const fileName = `${conversationSegment}_${stageSegment}_${timeSegment}.md`;
      const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = fileName;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      setCopiedExecutionCardKey('runbook-md');
      window.setTimeout(() => {
        setCopiedExecutionCardKey((current) => (current === 'runbook-md' ? null : current));
      }, 1800);
    } catch (_error) {
      setRagError('导出 Markdown 失败，请重试');
    }
  }, [ragConversationId, ragSessionStatus?.stage]);

  const handleSaveRunbookToReport = useCallback(async () => {
    if (!ragConversationId) {
      setRagError('当前没有可保存的会话 ID');
      return;
    }
    if (!ragExecutionRunbookMarkdown.trim()) {
      setRagError('当前没有可保存的 Runbook 内容');
      return;
    }
    try {
      setSavingRunbook(true);
      const result = await createGraphExtensionsApi.exportConversationRunbook('/api', ragConversationId, {
        markdown: ragExecutionRunbookMarkdown,
        runbook_text: ragExecutionRunbookText,
        include_messages: true,
        include_events: true,
        metadata: {
          stage: toStringValue(ragSessionStatus?.stage),
          judgment_status: ragJudgment?.status,
          judgment_confidence: ragJudgment?.confidence,
          swarm_summary: ragSwarmFinal?.consensus?.summary,
          project_path: activeProjectPath,
        },
      });
      setSavedRunbookPath(toStringValue(result.markdownPath) || toStringValue(result.executionRecordPath));
      setCopiedExecutionCardKey('runbook-save');
      window.setTimeout(() => {
        setCopiedExecutionCardKey((current) => (current === 'runbook-save' ? null : current));
      }, 1800);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRagError(`保存到汇报目录失败: ${message}`);
    } finally {
      setSavingRunbook(false);
    }
  }, [
    activeProjectPath,
    ragConversationId,
    ragExecutionRunbookMarkdown,
    ragExecutionRunbookText,
    ragJudgment?.confidence,
    ragJudgment?.status,
    ragSessionStatus?.stage,
    ragSwarmFinal?.consensus?.summary,
  ]);

  const handleEvidenceJump = useCallback((item: RagEvidenceView) => {
    if (!graph) return;

    const rawNodeId = item.nodeId.trim();
    let targetNode = graph.nodes.find((node) => node.id === rawNodeId);
    if (!targetNode && rawNodeId) {
      targetNode = graph.nodes.find((node) => node.id.endsWith(rawNodeId) || node.id.endsWith(`:${rawNodeId}`));
    }

    const rawEvidencePath = item.filePath.trim();
    const resolvedPath = rawEvidencePath ? resolveFilePathForUI(rawEvidencePath) : null;

    if (!targetNode && resolvedPath) {
      const nodeId = findFileNodeIdForUI(resolvedPath);
      if (nodeId) {
        targetNode = graph.nodes.find((node) => node.id === nodeId);
      }
    }

    if (targetNode) {
      setSelectedNode(targetNode);
      setHighlightedNodeIds(new Set([targetNode.id]));
    }

    const referencePath = resolvedPath || (targetNode?.properties.filePath ? resolveFilePathForUI(targetNode.properties.filePath) : null);
    if (referencePath) {
      const startLine1 = item.lineStart ?? targetNode?.properties.startLine;
      const endLine1 = item.lineEnd ?? targetNode?.properties.endLine ?? startLine1;

      addCodeReference({
        filePath: referencePath,
        startLine: typeof startLine1 === 'number' ? Math.max(0, startLine1 - 1) : undefined,
        endLine: typeof endLine1 === 'number' ? Math.max(0, endLine1 - 1) : undefined,
        nodeId: targetNode?.id,
        label: targetNode?.label ?? 'File',
        name: targetNode?.properties.name ?? referencePath.split('/').pop() ?? referencePath,
        source: 'user',
      });
    }
  }, [addCodeReference, findFileNodeIdForUI, graph, resolveFilePathForUI, setHighlightedNodeIds, setSelectedNode]);

  const chatSuggestions = [
    '请解释这个项目的整体架构',
    '这个项目主要解决什么问题？',
    '请列出最关键的文件与入口',
    '帮我找出所有 API 处理函数',
  ];

  const formatConversationOptionLabel = useCallback((item: CreateGraphConversationListItem): string => {
    const shortId = item.conversationId.length > 10
      ? `${item.conversationId.slice(0, 8)}…`
      : item.conversationId;
    const updatedText = typeof item.updatedAt === 'string' && item.updatedAt
      ? new Date(item.updatedAt).toLocaleString()
      : '未知时间';
    const messageCount = typeof item.messageCount === 'number' ? item.messageCount : 0;
    return `${shortId} · ${messageCount} 条消息 · ${updatedText}`;
  }, []);

  if (!isRightPanelOpen) return null;

  return (
    <aside className="w-[40%] min-w-[400px] max-w-[620px] flex flex-col bg-deep border-l border-border-subtle animate-slide-in relative z-30 flex-shrink-0">
      {/* Header with Tabs */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface border-b border-border-subtle">
        <div className="flex items-center gap-1">
          {/* Chat Tab */}
          <button
            type="button"
            onClick={() => setActiveTab('chat')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'chat'
              ? 'bg-accent/15 text-accent'
              : 'text-text-muted hover:text-text-primary hover:bg-hover'
              }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
          <span>AI 问答</span>
          </button>

          {/* Processes Tab */}
          <button
            type="button"
            onClick={() => setActiveTab('processes')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'processes'
              ? 'bg-accent/15 text-accent'
              : 'text-text-muted hover:text-text-primary hover:bg-hover'
              }`}
          >
            <GitBranch className="w-3.5 h-3.5" />
            <span>流程</span>
          </button>

          {/* Hierarchy Tab */}
          <button
            type="button"
            onClick={() => setActiveTab('hierarchy')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'hierarchy'
              ? 'bg-cyan-500/15 text-cyan-300'
              : 'text-text-muted hover:text-text-primary hover:bg-hover'
              }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>功能分区</span>
          </button>

          {/* RAG Tab */}
          <button
            type="button"
            onClick={() => setActiveTab('rag')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'rag'
              ? 'bg-violet-500/15 text-violet-300'
              : 'text-text-muted hover:text-text-primary hover:bg-hover'
              }`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>问答</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('experience')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'experience'
              ? 'bg-amber-500/15 text-amber-200'
              : 'text-text-muted hover:text-text-primary hover:bg-hover'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>经验库</span>
          </button>
        </div>

        {/* Close button */}
        <button
          type="button"
          onClick={() => setRightPanelOpen(false)}
          className="p-1.5 text-text-muted hover:text-text-primary hover:bg-hover rounded transition-colors"
           title="关闭面板"
        >
          <PanelRightClose className="w-4 h-4" />
        </button>
      </div>

      {/* Processes Tab */}
      {activeTab === 'processes' && (
        <div className="flex-1 flex flex-col overflow-hidden">
          <ProcessesPanel />
        </div>
      )}

      {/* Hierarchy Tab */}
      {activeTab === 'hierarchy' && (
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="px-4 py-3 border-b border-border-subtle bg-elevated/40 flex items-center justify-between">
            <div>
               <div className="text-sm font-semibold text-cyan-200">功能分区视图</div>
               <div className="text-xs text-text-muted">帮助理解 Partition、Process、社区 的结构入口与功能边界。</div>
            </div>
            <button
              type="button"
              onClick={loadHierarchyContract}
              className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-hover"
               title="刷新功能分区数据"
              disabled={hierarchyLoading}
            >
              <RefreshCw className={`w-4 h-4 ${hierarchyLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {hierarchyError && (
            <div className="px-4 py-3 text-sm text-rose-300 border-b border-rose-500/20 bg-rose-500/10">
              {hierarchyError}
            </div>
          )}

          {hierarchyLoading && (
            <div className="px-4 py-4 text-sm text-text-muted flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
               正在加载功能分区数据…
            </div>
          )}

          {!hierarchyLoading && partitionSummaries.length === 0 && !hierarchyError && (
            <div className="px-4 py-4 text-sm text-text-muted space-y-3">
               <div>暂时还没有功能分区摘要，请先执行一次层级分析。</div>
              <button
                type="button"
                onClick={handleOpenLocalPathAnalysis}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-cyan-400/40 bg-cyan-500/15 text-cyan-100 hover:bg-cyan-500/25"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                 打开本地路径分析
              </button>
            </div>
          )}

          {hierarchyError && (
            <div className="px-4 pb-3">
              <button
                type="button"
                onClick={handleOpenLocalPathAnalysis}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-cyan-400/40 bg-cyan-500/15 text-cyan-100 hover:bg-cyan-500/25"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                 通过本地路径生成分区数据
              </button>
            </div>
          )}

          {!hierarchyLoading && partitionSummaries.length > 0 && hierarchyPage === 'list' && (
            <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3 scrollbar-thin">
              <div className="space-y-2">
                {partitionSummaries.map((summary) => (
                  <button
                    key={summary.partitionId}
                    type="button"
                    onClick={() => {
                      setSelectedPartitionId(summary.partitionId);
                      setSelectedPathId('');
                      setHierarchySubview('info');
                      setHierarchyPage('partition');
                      focusPartitionInWorkspace(summary);
                    }}
                    className="w-full text-left rounded-lg border border-border-subtle bg-elevated/30 p-3 transition-colors hover:bg-elevated/60"
                  >
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-medium text-text-primary truncate">{summary.name}</div>
                      </div>
                    {summary.description && (
                      <div className="text-xs text-text-secondary mt-1 line-clamp-2">{summary.description}</div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-muted">
                      <span className="px-2 py-0.5 rounded bg-surface border border-border-subtle">Path {summary.pathCount}</span>
                      <span className="px-2 py-0.5 rounded bg-surface border border-border-subtle">Process {summary.processCount}</span>
                            <span className="px-2 py-0.5 rounded bg-surface border border-border-subtle">社区 {summary.communityCount}</span>
                      <span className="px-2 py-0.5 rounded bg-surface border border-border-subtle">Methods {summary.methodCount}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {!hierarchyLoading && partitionSummaries.length > 0 && hierarchyPage === 'partition' && selectedPartitionSummary && (
            <div className="flex-1 min-h-0 flex flex-col">
              <div className="px-3 py-2 border-b border-border-subtle flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setHierarchyPage('list');
                    setSelectedPathId('');
                    setSecondaryHighlightedNodeIds(new Set());
                  }}
                  className="px-2 py-1 text-xs rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-hover"
                >
                  返回分区列表
                </button>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-text-primary truncate">{selectedHierarchyFunction?.name ?? selectedPartitionSummary.name}</div>
                  <div className="text-[11px] text-text-muted truncate">功能分区详情</div>
                </div>
              </div>

              <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3 scrollbar-thin">
                <div className="text-xs text-text-secondary whitespace-pre-wrap">{selectedHierarchyFunction?.description || selectedPartitionSummary.description || '无描述'}</div>

                <div className="grid grid-cols-2 gap-2 text-[11px] text-text-muted">
                  <div className="rounded border border-border-subtle bg-surface/60 px-2 py-1.5">方法 {selectedHierarchyFunction?.methodCount ?? selectedPartitionSummary.methodCount}</div>
                  <div className="rounded border border-border-subtle bg-surface/60 px-2 py-1.5">类 {selectedHierarchyFunction?.totalClasses ?? 0}</div>
                  <div className="rounded border border-border-subtle bg-surface/60 px-2 py-1.5">出度 {selectedHierarchyFunction?.outgoingCallCount ?? 0}</div>
                  <div className="rounded border border-border-subtle bg-surface/60 px-2 py-1.5">入度 {selectedHierarchyFunction?.incomingCallCount ?? 0}</div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {(['info', 'entry', 'hypergraph', 'paths'] as HierarchySubview[]).map((view) => (
                    <button
                      key={view}
                      type="button"
                      onClick={() => setHierarchySubview(view)}
                      className={`px-2.5 py-1 rounded border text-[11px] transition-colors ${hierarchySubview === view
                        ? 'border-cyan-400/60 bg-cyan-500/10 text-cyan-100'
                        : 'border-border-subtle bg-surface/40 text-text-secondary hover:bg-elevated/70'
                        }`}
                    >
                      {view === 'info' ? '详情' : view === 'entry' ? '入口点' : view === 'hypergraph' ? '超图' : '功能路径'}
                    </button>
                  ))}
                </div>

                {partitionAnalysisLoading ? (
                  <div className="text-xs text-text-muted flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> 正在加载分区分析…</div>
                ) : partitionAnalysisError ? (
                  <div className="text-xs text-rose-300">{partitionAnalysisError}</div>
                ) : hierarchySubview === 'info' ? (
                  <div className="space-y-3">
                    {selectedHierarchyFunction?.folders && selectedHierarchyFunction.folders.length > 0 && (
                      <div>
                        <div className="text-xs uppercase tracking-wide text-cyan-300 mb-1">目录</div>
                        <div className="flex flex-wrap gap-2">
                          {selectedHierarchyFunction.folders.map((folder) => (
                            <span key={folder} className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60 text-[11px] text-text-secondary">{folder}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    <div>
                      <div className="text-xs uppercase tracking-wide text-cyan-300 mb-1">方法</div>
                      {partitionMethodKeys.length > 0 ? (
                        <div className="max-h-40 overflow-y-auto space-y-1 pr-1 scrollbar-thin">
                          {partitionMethodKeys.map((methodKey) => (
                            <button
                              key={methodKey}
                              type="button"
                              onClick={() => {
                                setSelectedMethodKey(methodKey);
                                focusMethodInWorkspace(methodKey);
                              }}
                              className={`w-full rounded border px-2 py-1.5 text-left text-[11px] transition-colors ${selectedMethodKey === methodKey
                                ? 'border-cyan-400/60 bg-cyan-500/10 text-cyan-100'
                                : 'border-border-subtle bg-surface/50 text-text-secondary hover:bg-elevated/70'
                                }`}
                            >
                              {methodKey}
                            </button>
                          ))}
                        </div>
                      ) : <div className="text-xs text-text-muted">当前分区暂无可用方法列表</div>}
                    </div>

                    <div className="rounded-lg border border-border-subtle bg-surface/40 p-3 space-y-2">
                      <div className="text-xs uppercase tracking-wide text-cyan-300">Phase2~5 最小可见层</div>
                      <div className="grid grid-cols-2 gap-2 text-[11px] text-text-secondary">
                        {getStage2VisibleSummary(selectedPartitionSummary, partitionAnalysis).map((item) => (
                          <div key={item.label} className="rounded border border-border-subtle bg-elevated/40 px-2 py-1.5">{item.label}: {item.value}</div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-lg border border-border-subtle bg-surface/40 p-3 space-y-2">
                      <div className="text-xs uppercase tracking-wide text-cyan-300">Stage3 同屏对照</div>
                      <div className="space-y-1 text-[11px] text-text-secondary">
                        {getStage3CompareSummary(selectedPartitionSummary, partitionAnalysis, entryPoints, pathAnalyses).map((item) => (
                          <div key={item.label} className="rounded border border-border-subtle bg-elevated/40 px-2 py-1.5">{item.label}: 旧结果 {item.oldValue} / 新结果 {item.newValue}</div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-lg border border-border-subtle bg-surface/40 p-3 space-y-2">
                      <div className="text-xs uppercase tracking-wide text-cyan-300">功能关系</div>
                      {selectedHierarchyFunction?.functionRelations && selectedHierarchyFunction.functionRelations.length > 0 ? (
                        <div className="space-y-1 text-[11px] text-text-secondary">
                          {selectedHierarchyFunction.functionRelations.slice(0, 8).map((relation) => (
                            <div key={`${relation.source}-${relation.target}`} className="break-all">{relation.source} → {relation.target} ({relation.callCount} 次)</div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-[11px] text-text-muted">当前分区暂无功能关系数据</div>
                      )}
                    </div>

                    {Array.isArray(partitionAnalysis?.fqns) && partitionAnalysis.fqns.length > 0 && (
                      <div className="rounded-lg border border-border-subtle bg-surface/40 p-3 space-y-2">
                        <div className="text-xs uppercase tracking-wide text-cyan-300">FQMN 汇总</div>
                        <div className="max-h-48 overflow-y-auto space-y-1 pr-1 scrollbar-thin text-[11px] text-text-secondary">
                          {partitionAnalysis.fqns.filter(isRecord).map((item) => {
                            const fqmn = toStringValue(item.fqn, toStringValue(item.method_signature));
                            if (!fqmn) return null;
                            return (
                              <div key={fqmn} className="rounded border border-border-subtle bg-elevated/40 px-2 py-1.5">
                                <div className="break-all text-text-primary">{fqmn}</div>
                                <div className="mt-1 text-text-muted">{formatFqmnMeta(item)}</div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {Array.isArray(partitionAnalysis?.inputs) && partitionAnalysis.inputs.length > 0 && (
                      <div className="rounded-lg border border-border-subtle bg-surface/40 p-3 space-y-2">
                        <div className="text-xs uppercase tracking-wide text-cyan-300">输入参数汇总</div>
                        <div className="max-h-40 overflow-y-auto space-y-1 pr-1 scrollbar-thin text-[11px] text-text-secondary">
                          {partitionAnalysis.inputs.filter(isRecord).map((item, index) => {
                            const methodSignature = toStringValue(item.method_signature);
                            const parameterName = toStringValue(item.parameter_name);
                            const parameterType = toStringValue(item.parameter_type);
                            const key = `${methodSignature}-${parameterName}-${index}`;
                            return <div key={key} className="rounded border border-border-subtle bg-elevated/40 px-2 py-1.5 break-all">{methodSignature} → {parameterName}: {parameterType || '未标注'}</div>;
                          })}
                        </div>
                      </div>
                    )}

                    {Array.isArray(partitionAnalysis?.outputs) && partitionAnalysis.outputs.length > 0 && (
                      <div className="rounded-lg border border-border-subtle bg-surface/40 p-3 space-y-2">
                        <div className="text-xs uppercase tracking-wide text-cyan-300">返回值汇总</div>
                        <div className="max-h-40 overflow-y-auto space-y-1 pr-1 scrollbar-thin text-[11px] text-text-secondary">
                          {partitionAnalysis.outputs.filter(isRecord).map((item) => {
                            const methodSignature = toStringValue(item.method_signature);
                            const returnType = toStringValue(item.return_type, '未标注');
                            const stableKey = `${methodSignature}-${returnType || '未标注'}`;
                            return <div key={stableKey} className="rounded border border-border-subtle bg-elevated/40 px-2 py-1.5 break-all">{methodSignature} → 返回: {returnType}</div>;
                          })}
                        </div>
                      </div>
                    )}

                    {selectedMethodDetail && (
                      <div className="space-y-3 rounded-lg border border-border-subtle bg-surface/40 p-3">
                        <div>
                          <div className="text-xs uppercase tracking-wide text-cyan-300">当前方法</div>
                          <div className="mt-1 text-sm text-text-primary break-all">{selectedMethodDetail.methodKey}</div>
                        </div>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                          <div>
                            <div className="text-xs uppercase tracking-wide text-cyan-300 mb-1">所属流程</div>
                            <div className="text-[11px] text-text-secondary space-y-1">
                              {selectedMethodDetail.processLabels.length > 0 ? selectedMethodDetail.processLabels.map((item) => <div key={item}>{item}</div>) : <div>未命中流程</div>}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs uppercase tracking-wide text-cyan-300 mb-1">所属社区</div>
                            <div className="text-[11px] text-text-secondary space-y-1">
                              {selectedMethodDetail.communityLabels.length > 0 ? selectedMethodDetail.communityLabels.map((item) => <div key={item}>{item}</div>) : <div>未命中社区</div>}
                            </div>
                          </div>
                        </div>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                          <div>
                            <div className="text-xs uppercase tracking-wide text-cyan-300 mb-1">输入</div>
                            <div className="text-[11px] text-text-secondary space-y-1">
                              {selectedMethodDetail.inputs.length > 0 ? selectedMethodDetail.inputs.map((item) => <div key={item}>{item}</div>) : <div>暂无输入参数信息</div>}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs uppercase tracking-wide text-cyan-300 mb-1">输出</div>
                            <div className="text-[11px] text-text-secondary space-y-1">
                              {selectedMethodDetail.outputs.length > 0 ? selectedMethodDetail.outputs.map((item) => <div key={item}>{item}</div>) : <div>暂无返回值信息</div>}
                            </div>
                          </div>
                        </div>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                          <div>
                            <div className="text-xs uppercase tracking-wide text-cyan-300 mb-1">路径描述</div>
                            <div className="text-[11px] text-text-secondary space-y-1">
                              {selectedMethodDetail.pathDescriptions.length > 0 ? selectedMethodDetail.pathDescriptions.slice(0, 5).map((item) => <div key={item}>{item}</div>) : <div>暂无路径说明</div>}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs uppercase tracking-wide text-cyan-300 mb-1">入口原因 / 产物</div>
                            <div className="text-[11px] text-text-secondary space-y-1">
                              <div>{selectedMethodDetail.entryReason || '无入口点评分原因'}</div>
                              <div className="flex flex-wrap gap-2 pt-1">
                                {selectedMethodDetail.cfgAvailable && <span className="px-2 py-0.5 rounded bg-violet-500/10 border border-violet-500/30 text-violet-200">CFG</span>}
                                {selectedMethodDetail.dfgAvailable && <span className="px-2 py-0.5 rounded bg-fuchsia-500/10 border border-fuchsia-500/30 text-fuchsia-200">DFG</span>}
                                {selectedMethodDetail.ioGraphAvailable && <span className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-200">IO</span>}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : hierarchySubview === 'entry' ? (
                  <div className="space-y-3">
                    {isRecord(partitionAnalysis?.entry_points_shadow) && Array.isArray(partitionAnalysis?.entry_points_shadow.effective_entries) && partitionAnalysis.entry_points_shadow.effective_entries.length > 0 && (
                      <div className="rounded border border-cyan-500/30 bg-cyan-500/10 p-3 text-[11px] text-text-secondary">
                        <div className="text-cyan-100 font-medium mb-2">Shadow 入口点评分</div>
                        <div className="space-y-1">
                          {partitionAnalysis.entry_points_shadow.effective_entries.slice(0, 3).map((item) => {
                            if (!isRecord(item)) return null;
                            const methodSignature = toStringValue(item.method_signature);
                            const firstReason = Array.isArray(item.reasons) ? item.reasons.filter((reason): reason is string => typeof reason === 'string').slice(0, 1).join(' / ') : '无原因';
                            return <div key={`${methodSignature}-${firstReason}`}>{methodSignature} · 评分={toNumberValue(item.score)} · {firstReason}</div>;
                          })}
                        </div>
                      </div>
                    )}
                    {entryPoints.length > 0 ? entryPoints.map((entry) => (
                      <button
                        key={`${entry.methodSignature}-${entry.score}`}
                        type="button"
                        onClick={() => {
                          setSelectedMethodKey(entry.methodSignature);
                          focusMethodInWorkspace(entry.methodSignature);
                        }}
                        className="w-full rounded border border-border-subtle bg-surface/50 px-3 py-2 text-left hover:bg-elevated/70"
                      >
                        <div className="text-sm text-text-primary break-all">{entry.methodSignature}</div>
                        <div className="mt-1 text-[11px] text-cyan-200">评分：{entry.score}</div>
                        <div className="mt-1 text-[11px] text-text-secondary space-y-1">
                          {entry.reasons.length > 0 ? entry.reasons.map((reason) => <div key={reason}>{reason}</div>) : <div>无识别原因</div>}
                        </div>
                      </button>
                    )) : <div className="text-xs text-text-muted">该功能分区没有识别到入口点</div>}
                  </div>
                ) : hierarchySubview === 'hypergraph' ? (
                  <div className="space-y-3">
                    <div className="flex flex-wrap gap-2 text-[11px] text-text-muted">
                      <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">关联方法 {partitionRelatedMethodKeys.length}</span>
                      <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">超图方法 {hypergraphMethodKeys.length}</span>
                      <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">路径数 {pathAnalyses.length}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => highlightMethodCollectionInWorkspace(partitionRelatedMethodKeys, selectedMethodKey || partitionRelatedMethodKeys[0])}
                      className="inline-flex items-center gap-2 rounded border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-100 hover:bg-cyan-500/20"
                    >
                      在总图显示该功能分区全部关联节点
                    </button>
                    <div className="max-h-56 overflow-y-auto space-y-1 pr-1 scrollbar-thin">
                      {partitionRelatedMethodKeys.map((methodKey) => (
                        <button
                          key={methodKey}
                          type="button"
                          onClick={() => {
                            setSelectedMethodKey(methodKey);
                            focusMethodInWorkspace(methodKey);
                          }}
                          className={`w-full rounded border px-2 py-1.5 text-left text-[11px] transition-colors ${selectedMethodKey === methodKey
                            ? 'border-cyan-400/60 bg-cyan-500/10 text-cyan-100'
                            : 'border-border-subtle bg-surface/50 text-text-secondary hover:bg-elevated/70'
                            }`}
                        >
                          {methodKey}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {pathAnalyses.length > 0 ? pathAnalyses.map((pathItem) => (
                      <button
                        key={pathItem.id}
                        type="button"
                        onClick={() => {
                          setSelectedPathId(pathItem.id);
                          setHierarchyPage('path');
                          setPathDetailView('overview');
                          highlightMethodCollectionInWorkspace(pathItem.methods, pathItem.methods[0]);
                        }}
                        className="w-full rounded border border-border-subtle px-3 py-2 text-left transition-colors hover:bg-elevated/70"
                      >
                        <div className="text-sm text-text-primary">{pathItem.pathName}</div>
                        <div className="mt-1 text-[11px] text-text-secondary">{pathItem.pathDescription}</div>
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-muted">
                          <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">方法数 {pathItem.methods.length}</span>
                          <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">评分 {pathItem.worthinessScore.toFixed(2)}</span>
                          {pathItem.cfgAvailable && <span className="px-2 py-0.5 rounded bg-violet-500/10 border border-violet-500/30 text-violet-200">CFG</span>}
                          {pathItem.dfgAvailable && <span className="px-2 py-0.5 rounded bg-fuchsia-500/10 border border-fuchsia-500/30 text-fuchsia-200">DFG</span>}
                          {pathItem.ioGraphAvailable && <span className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-200">IO</span>}
                        </div>
                      </button>
                    )) : <div className="text-xs text-text-muted">该功能分区没有功能路径</div>}
                  </div>
                )}
              </div>
            </div>
          )}

          {!hierarchyLoading && partitionSummaries.length > 0 && hierarchyPage === 'path' && selectedPathAnalysis && selectedPartitionSummary && (
            <div className="flex-1 min-h-0 flex flex-col">
              <div className="px-3 py-2 border-b border-border-subtle flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setHierarchyPage('partition')}
                  className="px-2 py-1 text-xs rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-hover"
                >
                  返回功能分区
                </button>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-text-primary truncate">{selectedPathAnalysis.pathName}</div>
                  <div className="text-[11px] text-text-muted truncate">{selectedPartitionSummary.name}</div>
                </div>
              </div>

              <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3 scrollbar-thin">
                <div className="rounded border border-border-subtle bg-elevated/30 p-3 space-y-2">
                  <div className="text-sm text-text-primary">{selectedPathAnalysis.pathDescription}</div>
                  <div className="flex flex-wrap gap-2 text-[11px] text-text-muted">
                    <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">方法数 {selectedPathAnalysis.methods.length}</span>
                    <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">评分 {selectedPathAnalysis.worthinessScore.toFixed(2)}</span>
                    <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">叶子节点 {selectedPathAnalysis.leafNode}</span>
                  </div>
                  <div className="flex flex-wrap gap-2 text-[11px] text-text-secondary">
                    {selectedPathAnalysis.callChainType && <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">调用链类型 {selectedPathAnalysis.callChainType}</span>}
                    {selectedPathAnalysis.mainMethod && <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">总方法 {selectedPathAnalysis.mainMethod.split('.').pop()}</span>}
                    {selectedPathAnalysis.intermediateMethods.length > 0 && <span className="px-2 py-0.5 rounded border border-border-subtle bg-surface/60">中间方法 {selectedPathAnalysis.intermediateMethods.map((item) => item.split('.').pop()).join(', ')}</span>}
                  </div>
                  <button
                    type="button"
                    onClick={() => highlightMethodCollectionInWorkspace(selectedPathAnalysis.methods, selectedPathAnalysis.methods[0])}
                    className="inline-flex items-center gap-2 rounded border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-100 hover:bg-cyan-500/20"
                  >
                    在总图只显示这条功能路径的方法调用链
                  </button>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {(['overview', 'cfg', 'dfg', 'dataflow', 'io'] as PathDetailView[]).map((view) => (
                      <button
                        key={view}
                        type="button"
                        onClick={() => setPathDetailView(view)}
                        className={`px-2.5 py-1 rounded border text-[11px] transition-colors ${pathDetailView === view
                          ? 'border-cyan-400/60 bg-cyan-500/10 text-cyan-100'
                          : 'border-border-subtle bg-surface/40 text-text-secondary hover:bg-elevated/70'
                          }`}
                      >
                        {view === 'overview' ? '概览' : view === 'cfg' ? '查看CFG' : view === 'dfg' ? '查看DFG' : view === 'dataflow' ? '查看数据流' : '输入输出'}
                      </button>
                    ))}
                  </div>
                </div>

                {pathDetailView === 'overview' && (
                  <>
                    <div className="rounded border border-border-subtle bg-surface/40 p-3">
                      <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2">路径链路</div>
                      <div className="text-[11px] text-text-secondary break-all">{selectedPathAnalysis.methods.join(' -> ')}</div>
                    </div>

                    {selectedPathAnalysis.callChainExplanation && (
                      <div className="rounded border border-border-subtle bg-surface/40 p-3">
                        <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2">调用链解释</div>
                        <div className="text-[11px] text-text-secondary whitespace-pre-wrap">{selectedPathAnalysis.callChainExplanation}</div>
                      </div>
                    )}

                    {selectedPathAnalysis.worthinessReasons.length > 0 && (
                      <div className="rounded border border-border-subtle bg-surface/40 p-3">
                         <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2">路径命中原因</div>
                        <div className="space-y-1 text-[11px] text-text-secondary">
                          {selectedPathAnalysis.worthinessReasons.map((reason) => <div key={reason}>{reason}</div>)}
                        </div>
                      </div>
                    )}

                    <div className="rounded border border-border-subtle bg-surface/40 p-3">
                       <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2">分析产物</div>
                      <div className="flex flex-wrap gap-2 text-[11px] text-text-muted">
                         {selectedPathAnalysis.cfgAvailable && <span className="px-2 py-0.5 rounded bg-violet-500/10 border border-violet-500/30 text-violet-200">CFG 已生成</span>}
                         {selectedPathAnalysis.dfgAvailable && <span className="px-2 py-0.5 rounded bg-fuchsia-500/10 border border-fuchsia-500/30 text-fuchsia-200">DFG 已生成</span>}
                         {selectedPathAnalysis.ioGraphAvailable && <span className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-200">IO 已生成（{selectedPathAnalysis.ioNodeCount} 个节点 / {selectedPathAnalysis.ioEdgeCount} 条边）</span>}
                      </div>
                    </div>
                  </>
                )}

                {pathDetailView === 'cfg' && (
                  <div className="space-y-3">
                    {selectedPathAnalysis.cfg ? (
                      <GraphVizBlock dotString={selectedPathAnalysis.cfg} color="violet" />
                    ) : <div className="rounded border border-border-subtle bg-surface/40 p-3 text-[11px] text-text-muted">该路径暂无 CFG</div>}
                    {selectedPathAnalysis.explainMarkdown && (
                      <div className="rounded border border-border-subtle bg-surface/40 p-3">
                         <div className="text-xs uppercase tracking-wide text-violet-300 mb-2">CFG 说明</div>
                        <MarkdownRenderer content={selectedPathAnalysis.explainMarkdown} onLinkClick={handleLinkClick} />
                      </div>
                    )}
                  </div>
                )}

                {pathDetailView === 'dfg' && (
                  <div className="space-y-3">
                    {selectedPathAnalysis.dfg ? (
                      <GraphVizBlock dotString={selectedPathAnalysis.dfg} color="fuchsia" />
                    ) : <div className="rounded border border-border-subtle bg-surface/40 p-3 text-[11px] text-text-muted">该路径暂无 DFG</div>}
                    {selectedPathAnalysis.explainMarkdown && (
                      <div className="rounded border border-border-subtle bg-surface/40 p-3">
                         <div className="text-xs uppercase tracking-wide text-fuchsia-300 mb-2">DFG 说明</div>
                        <MarkdownRenderer content={selectedPathAnalysis.explainMarkdown} onLinkClick={handleLinkClick} />
                      </div>
                    )}
                  </div>
                )}

                {pathDetailView === 'dataflow' && (
                  <div className="rounded border border-border-subtle bg-surface/40 p-3">
                    <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2">数据流</div>
                    {selectedPathAnalysis.hasDataflowMermaid ? (
                      <MermaidDiagram code={selectedPathAnalysis.dataflowMermaid} />
                    ) : selectedPathAnalysis.dfg ? (
                      <GraphVizBlock dotString={selectedPathAnalysis.dfg} color="fuchsia" />
                    ) : <div className="text-[11px] text-text-muted">该路径暂无数据流内容</div>}
                  </div>
                )}

                {pathDetailView === 'io' && (
                  <div className="rounded border border-border-subtle bg-surface/40 p-3">
                    <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2">输入输出</div>
                    {selectedPathAnalysis.ioGraphAvailable ? (
                      <div className="space-y-3">
                        {selectedPathAnalysis.ioGraph && <IoGraphBlock ioGraph={selectedPathAnalysis.ioGraph} />}
                        <div className="space-y-1 text-[11px] text-text-secondary">
                          <div>IO 图节点数：{selectedPathAnalysis.ioNodeCount}</div>
                          <div>IO 图边数：{selectedPathAnalysis.ioEdgeCount}</div>
                        </div>
                      </div>
                    ) : <div className="text-[11px] text-text-muted">该路径暂无输入输出图</div>}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* RAG Tab */}
      {activeTab === 'rag' && (
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="px-4 py-3 border-b border-border-subtle bg-elevated/40">
             <div className="text-sm font-semibold text-violet-200">RAG 问答工作台</div>
             <div className="text-xs text-text-muted mt-1">
               会自动复用当前节点与已选功能分区作为上下文，让提问范围更清晰。
             </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              <span className="px-2 py-0.5 rounded border border-violet-500/30 bg-violet-500/10 text-violet-200">
                 节点：{selectedNode?.properties?.name ?? selectedNode?.id ?? '未选择'}
              </span>
                <span className="px-2 py-0.5 rounded border border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
                  分区：{selectedPartitionSummary?.name || selectedPartitionId || '未选择'}
                </span>
            </div>
            {experienceProjectStatus && !experienceProjectStatus.experienceReady && (
              <div className="mt-2 rounded-md border border-amber-400/30 bg-amber-500/10 px-2.5 py-2 text-[11px] text-amber-100">
                经验库进度 {Math.max(0, Math.min(100, Number(experienceProjectStatus.progress || 0)))}% ：{experienceProjectStatus.qualityHint}
              </div>
            )}
          </div>

          <div className="px-4 pt-3 pb-2 border-b border-border-subtle">
            <textarea
              value={ragInput}
              onChange={(e) => setRagInput(e.target.value)}
               placeholder="请输入问题，例如：这个入口最终会调用哪些关键方法？"
              rows={3}
              className="w-full bg-elevated border border-border-subtle rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted resize-y min-h-[88px]"
            />
            <div className="mt-2 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setRagInput('');
                  setRagClarification(null);
                  setRagResponse(null);
                  setRagError(null);
                  setRagSessionStatus(null);
                  setRagConversationId(null);
                  setRagEventCursor(0);
                  setRagLiveSwarmPayload(null);
                  setRagProgressEvents([]);
                  setCopiedExecutionCardKey(null);
                  setSavedRunbookPath(null);
                }}
                className="px-2 py-1 text-xs text-text-muted hover:text-text-primary"
              >
                 清空
              </button>
              <button
                type="button"
                onClick={handleAskRag}
                disabled={!ragInput.trim() || ragLoading}
                className="px-3 py-1.5 text-xs rounded bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                 {ragLoading ? '处理中…' : '开始问答'}
               </button>
             </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-5">
              {ragStageAnchors.map((anchor) => (
                <div
                  key={anchor.key}
                  className={`rounded-lg border px-2.5 py-2 text-[11px] transition-colors ${anchor.status === 'warn'
                    ? 'border-amber-400/40 bg-amber-500/10 text-amber-100'
                    : anchor.status === 'success'
                      ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100'
                      : anchor.status === 'active'
                        ? 'border-violet-400/50 bg-violet-500/15 text-violet-100'
                        : 'border-border-subtle bg-surface/40 text-text-muted'
                  } ${ragCurrentStageKey === anchor.key ? 'ring-1 ring-violet-400/50' : ''}`}
                >
                  <div className="font-medium">{anchor.label}</div>
                  <div className="mt-1 text-[10px] opacity-80">
                    {anchor.status === 'warn' ? '异常' : anchor.status === 'success' ? '已完成' : anchor.status === 'active' ? '进行中' : '待触达'}
                  </div>
                </div>
              ))}
            </div>

            {ragReplayEntries.length > 0 && (
              <div className="mt-3 rounded-lg border border-border-subtle bg-surface/35 p-3 space-y-2">
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-text-muted">
                  <History className="w-3.5 h-3.5" />
                  最近运行回看
                </div>
                <div className="space-y-1.5">
                  <div className="block text-[11px] text-text-muted">
                    按 Conversation ID / 运行 ID 筛选
                  </div>
                  <input
                    type="text"
                    value={ragReplayFilter}
                    onChange={(event) => setRagReplayFilter(event.target.value)}
                    placeholder="输入 conversationId、sessionId 或运行 ID…"
                    className="w-full rounded-lg border border-border-subtle bg-elevated/30 px-3 py-2 text-xs text-text-primary placeholder:text-text-muted"
                  />
                </div>
                <div className="space-y-2 max-h-52 overflow-y-auto scrollbar-thin pr-1">
                  {filteredRagReplayEntries.length > 0 ? filteredRagReplayEntries.map((entry) => (
                    <div
                      key={entry.id}
                      className={`rounded-lg border px-3 py-2 transition-colors ${activeRagReplayId === entry.id
                        ? 'border-violet-400/50 bg-violet-500/10'
                        : 'border-border-subtle bg-elevated/20'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => handleRestoreRagReplay(entry)}
                          className="min-w-0 flex-1 text-left hover:opacity-90"
                        >
                          <div className="flex items-center justify-between gap-2 text-[11px]">
                            <span className="truncate text-text-primary font-medium">{entry.query}</span>
                            <span className="text-text-muted flex items-center gap-1 shrink-0">
                              <Clock3 className="w-3 h-3" />
                              {new Date(entry.updatedAt).toLocaleTimeString()}
                            </span>
                          </div>
                          <div className="mt-1 text-[11px] text-text-secondary">
                            {getStageDisplayText(entry.stage)} · {getReplayStatusDisplayText(entry.status)}
                          </div>
                          <div className="mt-1 text-[10px] text-text-muted break-all">
                            {entry.snapshot.conversationId || entry.snapshot.sessionStatus?.sessionId || entry.id}
                          </div>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleExportRagReplay(entry)}
                          className="shrink-0 rounded border border-cyan-400/35 bg-cyan-500/10 px-2 py-1 text-[11px] text-cyan-100 hover:bg-cyan-500/20"
                          title="导出这次回看记录"
                        >
                          导出
                        </button>
                      </div>
                    </div>
                  )) : (
                    <div className="rounded-lg border border-border-subtle bg-elevated/20 px-3 py-3 text-[11px] text-text-muted">
                      没有匹配当前筛选条件的回看记录。
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {ragError && (
            <div className="px-4 py-3 border-b border-rose-500/20 bg-rose-500/10 space-y-2">
              <div className="text-sm text-rose-300">{ragError}</div>
              <button
                type="button"
                onClick={handleOpenLocalPathAnalysis}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-cyan-400/40 bg-cyan-500/15 text-cyan-100 hover:bg-cyan-500/25"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                打开本地路径分析
              </button>
            </div>
          )}

          <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin p-4 space-y-3">
            {ragLoading && (
              <div className="space-y-2">
                <div className="text-sm text-text-muted flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  正在检索证据并生成回答…
                </div>
                {ragSessionStatus && (
                  <div className="rounded-lg border border-border-subtle bg-elevated/30 p-3 text-xs space-y-1">
                    <div className="text-violet-200">当前阶段：{getStageDisplayText(ragSessionStatus.stage)}</div>
                    <div className="text-text-secondary">{ragSessionStatus.message}</div>
                  </div>
                )}
                {ragSwarmLive && (
                  <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-3 text-xs space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-cyan-200">Swarm 实时状态</div>
                      <div className="text-[11px] text-cyan-100/80">
                        {ragSwarmLive.llmEnabled ? `LLM · ${ragSwarmLive.model || '当前模型'}` : '回退模式'}
                      </div>
                    </div>
                    {ragSwarmLive.consensus?.summary && (
                      <div className="text-text-secondary whitespace-pre-wrap">{ragSwarmLive.consensus.summary}</div>
                    )}
                    {ragSwarmLive.agents.length > 0 && (
                      <div className="space-y-1">
                        {ragSwarmLive.agents.map((agent) => (
                          <div key={agent.key} className="text-text-secondary">
                            • {agent.name}: {agent.summary}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {ragTimelineGroups.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs uppercase tracking-wide text-cyan-200">处理中间轨迹</div>
                {ragTimelineGroups.map((group) => {
                  const isCollapsed = Boolean(ragTimelineCollapsed[group.key]);
                  return (
                    <div key={group.key} className="rounded-lg border border-border-subtle bg-elevated/20 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => toggleTimelineGroup(group.key)}
                        className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left hover:bg-surface/30 transition-colors"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          {isCollapsed ? <ChevronRight className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
                          <span className="text-sm text-text-primary font-medium">{group.title}</span>
                          <span className={`px-2 py-0.5 rounded text-[10px] border ${group.status === 'warn'
                            ? 'border-amber-400/30 bg-amber-500/10 text-amber-200'
                            : group.status === 'success'
                              ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
                              : group.status === 'active'
                                ? 'border-cyan-400/30 bg-cyan-500/10 text-cyan-200'
                                : 'border-border-subtle bg-surface/50 text-text-muted'
                          }`}>
                            {group.status === 'warn' ? '异常' : group.status === 'success' ? '已完成' : group.status === 'active' ? '进行中' : '待触达'}
                          </span>
                        </div>
                        <span className="text-[11px] text-text-muted shrink-0">{group.items.length} 条</span>
                      </button>
                      {!isCollapsed && (
                        <div className="px-3 pb-3 space-y-2">
                          {group.items.map((item, index) => (
                            <div key={item.id} className="flex gap-3 rounded-lg border border-border-subtle bg-surface/35 p-2.5">
                              <div className="flex flex-col items-center pt-0.5">
                                <span className={`h-2.5 w-2.5 rounded-full ${item.tone === 'warn' ? 'bg-amber-300' : item.tone === 'success' ? 'bg-emerald-300' : item.tone === 'active' ? 'bg-cyan-300' : 'bg-text-muted'}`} />
                                {index < group.items.length - 1 && <span className="mt-1 h-full w-px bg-border-subtle" />}
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="text-[11px] font-medium text-text-primary">{item.title}</div>
                                <div className="mt-0.5 text-[11px] text-text-secondary whitespace-pre-wrap">{item.detail}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {ragClarification && !ragLoading && (
              <div className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-amber-300">澄清问题</div>
                    <div className="text-sm text-amber-100 mt-1">第 {ragClarification.round} 轮 / 共 {ragClarification.maxRounds} 轮</div>
                  </div>
                  <div className="text-[11px] px-2 py-0.5 rounded border border-amber-400/30 bg-amber-500/10 text-amber-200">
                    {ragClarification.clarityLevel}
                  </div>
                </div>

                <div className="text-sm text-text-primary whitespace-pre-wrap">{ragClarification.prompt}</div>

                <div className="rounded border border-border-subtle bg-surface/40 p-2.5 text-xs text-text-secondary">
                  <div className="text-[11px] uppercase tracking-wide text-cyan-300 mb-1">推断意图</div>
                  <div className="whitespace-pre-wrap">{ragClarification.inferredIntent}</div>
                </div>

                {ragClarification.options && ragClarification.options.length > 0 && (
                  <div className="space-y-2">
                      <div className="text-[11px] uppercase tracking-wide text-violet-300">可选补充方向</div>
                    <div className="space-y-2">
                      {ragClarification.options.map((option) => {
                        const selected = ragClarification.selectedOptionIds.includes(option.id);
                        return (
                          <button
                            key={option.id}
                            type="button"
                            onClick={() => handleClarificationOptionSelect(option)}
                            className={`w-full text-left rounded border px-3 py-2 transition-colors ${selected ? 'border-violet-400/50 bg-violet-500/15' : 'border-border-subtle bg-elevated/30 hover:bg-elevated/50'}`}
                          >
                            <div className="text-sm text-text-primary">{option.label}</div>
                            {option.description && (
                              <div className="text-[11px] text-text-secondary mt-1">{option.description}</div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {ragClarification.structuredFields && ragClarification.structuredFields.length > 0 && (
                  <div className="space-y-2">
                      <div className="text-[11px] uppercase tracking-wide text-emerald-300">结构化提示</div>
                    <div className="flex flex-wrap gap-2">
                      {ragClarification.structuredFields.map((field: CreateGraphClarificationField) => (
                        <span
                          key={field.id}
                          className="px-2 py-0.5 rounded border border-emerald-400/30 bg-emerald-500/10 text-[11px] text-emerald-100"
                        >
                          {field.label}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="text-[11px] text-text-muted">
                  {ragClarification.terminal
                    ? '自动澄清已到上限。请按上面的结构补充后重新提交新的完整需求。'
                    : '你可以直接补充自己的描述，或先点一个选项再提交。'}
                </div>
              </div>
            )}

            {!ragLoading && !ragResponse && !ragError && !ragClarification && (
              <div className="text-sm text-text-muted">
                 提交问题后，这里会按时间线展示检索、判断、证据和最终回答。
              </div>
            )}

            {ragResponse && (
              <>
                {ragJudgment && (
                  <div className="rounded-lg border border-border-subtle bg-elevated/20 p-3">
                    <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2">任务判断</div>
                    <div className="flex items-center gap-2 text-sm text-text-primary">
                      <span className={`px-2 py-0.5 rounded border ${ragJudgment.status === 'ready' ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200' : 'border-amber-400/30 bg-amber-500/10 text-amber-200'}`}>
                        {ragJudgment.status === 'ready' ? '可继续执行' : '仍需补充'}
                      </span>
                      <span className="text-text-secondary">置信度：{ragJudgment.confidence}</span>
                    </div>
                    {ragJudgment.reasons.length > 0 && (
                      <div className="mt-2 space-y-1 text-xs text-text-secondary">
                        {ragJudgment.reasons.map((reason) => (
                          <div key={reason}>- {reason}</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {ragSwarmFinal && (
                  <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 p-3 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs uppercase tracking-wide text-cyan-200">Swarm 共识</div>
                      <div className="text-[11px] px-2 py-0.5 rounded border border-cyan-400/40 bg-cyan-500/15 text-cyan-100">
                        {ragSwarmFinal.consensus?.confidence || '中'}
                      </div>
                    </div>
                    {ragSwarmFinal.consensus?.summary && (
                      <div className="text-sm text-text-primary whitespace-pre-wrap">{ragSwarmFinal.consensus.summary}</div>
                    )}

                    {ragSwarmFinal.consensus && ragSwarmFinal.consensus.risks.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[11px] uppercase tracking-wide text-amber-200">Swarm 风险</div>
                        {ragSwarmFinal.consensus.risks.map((risk) => (
                          <div key={risk} className="text-[11px] text-text-secondary">• {risk}</div>
                        ))}
                      </div>
                    )}

                    {ragSwarmFinal.consensus && ragSwarmFinal.consensus.actions.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[11px] uppercase tracking-wide text-emerald-200">Swarm 动作建议</div>
                        {ragSwarmFinal.consensus.actions.map((action) => (
                          <div key={action} className="text-[11px] text-text-secondary">• {action}</div>
                        ))}
                      </div>
                    )}

                    {ragSwarmFinal.agents.length > 0 && (
                      <div className="space-y-2">
                        <div className="text-[11px] uppercase tracking-wide text-cyan-200">角色摘要</div>
                        {ragSwarmFinal.agents.map((agent) => (
                          <div key={agent.key} className="rounded border border-border-subtle bg-surface/40 p-2 text-xs space-y-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-text-primary">{agent.name}</span>
                              <span className="text-text-muted">{agent.confidence} · {agent.status}</span>
                            </div>
                            <div className="text-text-secondary whitespace-pre-wrap">{agent.summary}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {ragExecutionCards.length > 0 && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs uppercase tracking-wide text-amber-200">可执行 Runbook</div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleCopyExecutionText('runbook-all', ragExecutionRunbookText)}
                          className="px-2 py-1 text-[11px] rounded border border-amber-400/40 bg-amber-500/15 text-amber-100 hover:bg-amber-500/25"
                        >
                          {copiedExecutionCardKey === 'runbook-all' ? '已复制' : '复制全文'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDownloadExecutionMarkdown(ragExecutionRunbookMarkdown)}
                          className="px-2 py-1 text-[11px] rounded border border-cyan-400/40 bg-cyan-500/15 text-cyan-100 hover:bg-cyan-500/25"
                        >
                          {copiedExecutionCardKey === 'runbook-md' ? '已导出' : '导出 MD'}
                        </button>
                        <button
                          type="button"
                          onClick={() => { void handleSaveRunbookToReport(); }}
                          disabled={savingRunbook}
                          className="px-2 py-1 text-[11px] rounded border border-emerald-400/40 bg-emerald-500/15 text-emerald-100 hover:bg-emerald-500/25 disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {savingRunbook ? '保存中…' : copiedExecutionCardKey === 'runbook-save' ? '已保存' : '保存到汇报/4.6'}
                        </button>
                      </div>
                    </div>

                    {savedRunbookPath && (
                      <div className="text-[11px] text-emerald-100/90 break-all">
                        已保存: {savedRunbookPath}
                      </div>
                    )}

                    <div className="space-y-2">
                      {ragExecutionCards.map((card) => {
                        const cardText = toExecutionRunbookText([card]);
                        return (
                          <div key={card.id} className="rounded border border-border-subtle bg-surface/40 p-2.5 text-xs space-y-2">
                            <div className="flex items-center justify-between gap-2">
                              <div className="text-text-primary font-medium">{card.title}</div>
                              <div className="flex items-center gap-2">
                                <span className="text-text-muted">{card.confidence}</span>
                                <button
                                  type="button"
                                  onClick={() => handleCopyExecutionText(card.id, cardText)}
                                  className="px-2 py-0.5 rounded border border-amber-400/35 bg-amber-500/10 text-[11px] text-amber-100 hover:bg-amber-500/20"
                                >
                                  {copiedExecutionCardKey === card.id ? '已复制' : '复制'}
                                </button>
                              </div>
                            </div>

                            <div className="text-text-secondary whitespace-pre-wrap">{card.summary}</div>

                            {card.targets.length > 0 && (
                              <div className="space-y-1">
                                <div className="text-[11px] uppercase tracking-wide text-cyan-200">目标文件</div>
                                {card.targets.map((target) => (
                                  <div key={`${card.id}-${target}`} className="font-mono text-[11px] text-text-muted break-all">{target}</div>
                                ))}
                              </div>
                            )}

                            {card.steps.length > 0 && (
                              <div className="space-y-1">
                                <div className="text-[11px] uppercase tracking-wide text-emerald-200">执行步骤</div>
                                {card.steps.map((step) => (
                                  <div key={`${card.id}-${step}`} className="text-text-secondary">• {step}</div>
                                ))}
                              </div>
                            )}

                            {card.risks.length > 0 && (
                              <div className="space-y-1">
                                <div className="text-[11px] uppercase tracking-wide text-rose-200">风险</div>
                                {card.risks.map((risk) => (
                                  <div key={`${card.id}-${risk}`} className="text-text-secondary">• {risk}</div>
                                ))}
                              </div>
                            )}

                            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                              <div className="rounded border border-emerald-400/20 bg-emerald-500/5 p-2 space-y-1">
                                <div className="text-[11px] uppercase tracking-wide text-emerald-200">执行前检查</div>
                                {card.preflightChecks.length > 0 ? (
                                  card.preflightChecks.map((item) => (
                                    <div key={`${card.id}-preflight-${item}`} className="text-[11px] text-text-secondary">• {item}</div>
                                  ))
                                ) : (
                                  <div className="text-[11px] text-text-muted">暂无前置检查项</div>
                                )}
                              </div>

                              <div className="rounded border border-rose-400/20 bg-rose-500/5 p-2 space-y-1">
                                <div className="text-[11px] uppercase tracking-wide text-rose-200">回滚建议</div>
                                {card.rollbackSuggestions.length > 0 ? (
                                  card.rollbackSuggestions.map((item) => (
                                    <div key={`${card.id}-rollback-${item}`} className="text-[11px] text-text-secondary">• {item}</div>
                                  ))
                                ) : (
                                  <div className="text-[11px] text-text-muted">暂无回滚建议</div>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <div className="rounded-lg border border-border-subtle bg-elevated/40 p-3">
                  <div className="text-xs uppercase tracking-wide text-violet-300 mb-1">结论摘要</div>
                  <div className="text-sm text-text-primary whitespace-pre-wrap">{ragAnswer}</div>
                </div>
                
                {ragCandidatePaths.length > 0 && (
                  <div className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 p-3 space-y-2">
                    <div className="text-xs uppercase tracking-wide text-cyan-200">候选路径</div>
                    <div className="space-y-2">
                      {ragCandidatePaths.map((item) => (
                        <div
                          key={item.pathId}
                          className={`rounded border p-2 text-xs space-y-1 ${item.isSelected ? 'border-emerald-400/40 bg-emerald-500/10' : 'border-border-subtle bg-surface/40'}`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-text-primary font-medium">{item.pathName}</div>
                            <div className="text-[11px] text-text-muted">
                              {typeof item.selectionScore === 'number' ? `评分 ${item.selectionScore.toFixed(3)}` : '评分暂无'}
                            </div>
                          </div>
                          {item.pathDescription && <div className="text-text-secondary">{item.pathDescription}</div>}
                          {item.functionChain.length > 0 && (
                            <div className="text-[11px] text-cyan-100/90 break-all">{item.functionChain.join(' -> ')}</div>
                          )}
                          <div className="text-[11px] text-text-muted">
                            {item.selectionReason ? `原因：${item.selectionReason}` : '原因：暂无'}
                            {item.source ? ` · 来源：${item.source}` : ''}
                            {typeof item.worthinessScore === 'number' ? ` · 价值评分：${item.worthinessScore.toFixed(3)}` : ''}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {ragAdvisor && (
                  <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 space-y-2">
                    <div className="text-xs uppercase tracking-wide text-amber-200">建议上下文</div>
                    <div className="text-[12px] text-text-secondary">状态：{ragAdvisor.status}</div>
                    {ragAdvisor.what && <div className="text-sm text-text-primary"><span className="text-amber-100">做什么：</span> {ragAdvisor.what}</div>}
                    {ragAdvisor.how && <div className="text-sm text-text-primary"><span className="text-amber-100">怎么做：</span> {ragAdvisor.how}</div>}
                    {ragAdvisor.nextStep && <div className="text-xs text-text-secondary">下一步：{ragAdvisor.nextStep}</div>}
                    {ragAdvisor.constraintTypes.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {ragAdvisor.constraintTypes.map((item) => (
                          <span key={item} className="px-1.5 py-0.5 rounded border border-amber-400/30 bg-amber-500/15 text-[11px] text-amber-100">{item}</span>
                        ))}
                      </div>
                    )}
                    {ragAdvisor.plainConstraints.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[11px] uppercase tracking-wide text-amber-200">约束条件</div>
                        {ragAdvisor.plainConstraints.slice(0, 8).map((item) => (
                          <div key={item} className="text-[11px] text-text-secondary">• {item}</div>
                        ))}
                      </div>
                    )}
                    {ragAdvisor.structuredSummaryLines.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[11px] uppercase tracking-wide text-amber-200">结构化摘要</div>
                        {ragAdvisor.structuredSummaryLines.map((item) => (
                          <div key={item} className="text-[11px] text-text-secondary break-all">• {item}</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                
                {ragOpencodeKernel && (
                  <div className="rounded-lg border border-fuchsia-500/25 bg-fuchsia-500/10 p-3 space-y-1">
                    <div className="text-xs uppercase tracking-wide text-fuchsia-200">OpenCode 内核</div>
                    <div className="text-[12px] text-text-primary">状态：{ragOpencodeKernel.status}</div>
                    {(ragOpencodeKernel.reason || ragOpencodeKernel.sessionId) && (
                      <div className="text-[11px] text-text-secondary break-all">
                        {ragOpencodeKernel.reason ? `原因：${ragOpencodeKernel.reason}` : ''}
                        {ragOpencodeKernel.reason && ragOpencodeKernel.sessionId ? ' · ' : ''}
                        {ragOpencodeKernel.sessionId ? `会话：${ragOpencodeKernel.sessionId}` : ''}
                      </div>
                    )}
                    <div className="text-[11px] text-text-secondary">
                      {typeof ragOpencodeKernel.durationMs === 'number' ? `耗时：${ragOpencodeKernel.durationMs}ms` : '耗时：暂无'}
                      {ragOpencodeKernel.model ? ` · 模型：${ragOpencodeKernel.model}` : ''}
                      {ragOpencodeKernel.agent ? ` · 代理：${ragOpencodeKernel.agent}` : ''}
                    </div>
                  </div>
                )}

                {ragRetrievalSummary && (
                  <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 p-3 space-y-2">
                    <div className="text-xs uppercase tracking-wide text-cyan-200">检索策略</div>
                    <div className="text-[12px] text-text-primary">模式：{ragRetrievalSummary.mode}</div>
                    {ragRetrievalSummary.strategy.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {ragRetrievalSummary.strategy.map((item) => (
                          <span key={item} className="px-1.5 py-0.5 rounded border border-cyan-400/25 bg-cyan-500/10 text-[11px] text-cyan-100">{item}</span>
                        ))}
                      </div>
                    )}
                    {ragRetrievalSummary.stats.length > 0 && (
                      <div className="text-[11px] text-text-secondary">{ragRetrievalSummary.stats.join(' · ')}</div>
                    )}
                    {ragRetrievalSummary.queryPlans.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[11px] uppercase tracking-wide text-cyan-200">查询计划</div>
                        {ragRetrievalSummary.queryPlans.map((plan) => (
                          <div key={plan} className="text-[11px] text-text-secondary break-all">• {plan}</div>
                        ))}
                      </div>
                    )}
                    {ragRetrievalSummary.decisionTrace.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[11px] uppercase tracking-wide text-cyan-200">决策轨迹</div>
                        {ragRetrievalSummary.decisionTrace.map((item) => (
                          <div key={`${item.step}-${item.decision}-${item.reason}`} className="rounded border border-cyan-400/20 bg-cyan-500/5 p-2">
                            <div className="text-[11px] text-cyan-100">{item.step} · {item.decision}{item.confidence ? ` · ${item.confidence}` : ''}</div>
                            {item.reason && <div className="text-[11px] text-text-secondary mt-0.5">{item.reason}</div>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {ragValidationCommands.length > 0 && (
                  <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                        <div className="text-xs uppercase tracking-wide text-emerald-200">建议验证命令</div>
                      <button
                        type="button"
                        onClick={() => handleCopyExecutionText('validation-commands', ragValidationCommands.join('\n'))}
                        className="px-2 py-1 text-[11px] rounded border border-emerald-400/35 bg-emerald-500/15 text-emerald-100 hover:bg-emerald-500/25"
                      >
                        {copiedExecutionCardKey === 'validation-commands' ? '已复制' : '复制'}
                      </button>
                    </div>
                    <div className="space-y-1">
                      {ragValidationCommands.map((command) => (
                        <div key={command} className="text-[12px] text-text-secondary font-mono break-all">$ {command}</div>
                      ))}
                    </div>
                  </div>
                )}

                {ragEditPlan.length > 0 && (
                  <div className="rounded-lg border border-border-subtle bg-elevated/20 p-3">
                        <div className="text-xs uppercase tracking-wide text-amber-300 mb-2">编辑计划</div>
                    <div className="space-y-2">
                      {ragEditPlan.map((item) => (
                        <div key={`${toStringValue(item.file_path)}-${toStringValue(item.anchor)}-${toStringValue(item.action)}`} className="rounded border border-border-subtle px-2.5 py-2 text-xs bg-surface/50">
                          <div className="text-text-primary font-medium">
                            {toStringValue(item.action)} · {toStringValue(item.anchor)}
                          </div>
                          <div className="text-text-muted font-mono break-all mt-0.5">{toStringValue(item.file_path, '待定位')}</div>
                          <div className="text-[11px] text-cyan-200 mt-1">{toStringValue(item.reason)}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {ragSnippetBlocks.length > 0 && (
                  <div className="rounded-lg border border-border-subtle bg-elevated/20 p-3">
                        <div className="text-xs uppercase tracking-wide text-emerald-300 mb-2">可复制代码片段</div>
                    <div className="space-y-3">
                      {ragSnippetBlocks.map((item) => (
                        <div key={`${toStringValue(item.file_path)}-${toStringValue(item.anchor)}-${toStringValue(item.action)}`} className="rounded border border-border-subtle bg-surface/50 p-3 space-y-2">
                          <div className="text-xs text-text-primary font-medium">
                            {toStringValue(item.action)} · {toStringValue(item.anchor)}
                          </div>
                          <div className="text-[11px] text-text-muted font-mono break-all">
                            {toStringValue(item.file_path, '待定位')}
                          </div>
                          <div className="flex justify-end">
                            <button
                              type="button"
                              onClick={() => handleCopySnippet(`${toStringValue(item.file_path)}-${toStringValue(item.anchor)}`, toStringValue(item.code))}
                              className="px-2 py-1 text-[11px] rounded border border-emerald-400/30 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
                            >
                              {copiedSnippetKey === `${toStringValue(item.file_path)}-${toStringValue(item.anchor)}` ? '已复制' : '复制'}
                            </button>
                          </div>
                          <pre className="text-[11px] text-text-secondary whitespace-pre-wrap overflow-x-auto">{toStringValue(item.code)}</pre>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {ragRisks.length > 0 && (
                  <div className="rounded-lg border border-border-subtle bg-elevated/20 p-3">
                      <div className="text-xs uppercase tracking-wide text-amber-300 mb-2">剩余风险 / 约束</div>
                    <div className="space-y-1 text-xs text-text-secondary">
                      {ragRisks.map((item) => (
                        <div key={item}>- {item}</div>
                      ))}
                    </div>
                  </div>
                )}

                {ragEvidence.length > 0 && (
                  <div className="rounded-lg border border-border-subtle bg-elevated/20 p-3">
                    <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" />
                        证据命中
                    </div>
                    <div className="space-y-2">
                      {ragEvidence.map((item) => (
                        <button
                          key={`${item.nodeId || item.filePath}-${item.rank || 'na'}`}
                          type="button"
                          onClick={() => handleEvidenceJump(item)}
                          className="w-full text-left rounded border border-border-subtle px-2.5 py-2 text-xs bg-surface/50 hover:bg-elevated/80 transition-colors"
                        >
                          <div className="text-text-primary font-medium">
                            {item.rank ? `#${item.rank} ` : ''}
                            {item.label}
                          </div>
                          <div className="text-text-muted font-mono break-all mt-0.5">{item.filePath}</div>
                          {item.score && <div className="text-[11px] text-cyan-200 mt-1">评分：{item.score}</div>}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {activeTab === 'experience' && <ExperienceLibraryManagerPanel />}

      {/* Chat Content - only show when chat tab is active */}
      {activeTab === 'chat' && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Status bar */}
          <div className="flex items-center gap-2.5 px-4 py-3 bg-elevated/50 border-b border-border-subtle">
            <div className="ml-auto flex items-center gap-2">
              {!isAgentReady && (
                <span className="text-[11px] px-2 py-1 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                  配置 AI
                </span>
              )}
              {isAgentInitializing && (
                <span className="text-[11px] px-2 py-1 rounded-full bg-surface border border-border-subtle flex items-center gap-1 text-text-muted">
                  <Loader2 className="w-3 h-3 animate-spin" /> 连接中
                </span>
              )}
            </div>
          </div>

          <div className="px-4 py-3 border-b border-border-subtle bg-elevated/30 space-y-2">
            <div className="text-[11px] uppercase tracking-[0.14em] text-text-muted">
              代码输出与经验库优先级
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={chatOutputRootPath}
                onChange={(event) => setChatOutputRootPath(event.target.value)}
                placeholder="输出目录（绝对路径）"
                className="flex-1 bg-surface border border-border-subtle rounded px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-muted"
                disabled={!serverBaseUrl}
              />
              <button
                type="button"
                onClick={() => { void refreshChatConversations(); }}
                className="px-2 py-1 text-xs rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-hover"
                disabled={!serverBaseUrl}
                title="刷新会话列表"
              >
                刷新
              </button>
              <button
                type="button"
                onClick={() => { void startNewChatConversation(); }}
                className="px-2 py-1 text-xs rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-hover"
                disabled={!serverBaseUrl}
                title="新建对话"
              >
                新对话
              </button>
            </div>

            <input
              type="text"
              value={advisorPriorityInput}
              onChange={(event) => setAdvisorPriorityInput(event.target.value)}
              placeholder="Advisor经验库优先级（逗号分隔：库名或项目路径，越靠前优先级越高）"
              className="w-full bg-surface border border-border-subtle rounded px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-muted"
              disabled={!serverBaseUrl}
            />

            <select
              value={chatConversationId || ''}
              onChange={(event) => {
                const selectedConversation = event.target.value;
                if (!selectedConversation) {
                  void startNewChatConversation();
                  return;
                }
                void loadChatConversation(selectedConversation);
              }}
              className="w-full bg-surface border border-border-subtle rounded px-2.5 py-1.5 text-xs text-text-primary"
              disabled={!serverBaseUrl}
            >
              <option value="">当前：新对话</option>
              {chatConversationList.map((item) => (
                <option key={item.conversationId} value={item.conversationId}>
                  {formatConversationOptionLabel(item)}
                </option>
              ))}
            </select>
          </div>

          {/* Status / errors */}
          {agentError && (
            <div className="px-4 py-3 bg-rose-500/10 border-b border-rose-500/30 text-rose-100 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              <span>{agentError}</span>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
            {chatMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="w-14 h-14 mb-4 flex items-center justify-center bg-gradient-to-br from-accent to-node-interface rounded-xl shadow-glow text-2xl">
                  🧠
                </div>
                <h3 className="text-base font-medium mb-2">
                   直接开始提问
                </h3>
                <p className="text-sm text-text-secondary leading-relaxed mb-5">
                   我可以帮你理解架构、定位函数、解释模块关系，或结合代码上下文回答问题。
                </p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {chatSuggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => setChatInput(suggestion)}
                      className="px-3 py-1.5 bg-elevated border border-border-subtle rounded-full text-xs text-text-secondary hover:border-accent hover:text-text-primary transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-6">
                {chatMessages.map((message) => (
                  <div
                    key={message.id}
                    className="animate-fade-in"
                  >
                    {/* User message - compact label style */}
                    {message.role === 'user' && (
                      <div className="mb-4">
                        <div className="flex items-center gap-2 mb-2">
                          <User className="w-4 h-4 text-text-muted" />
                           <span className="text-xs font-medium text-text-muted uppercase tracking-wide">你</span>
                        </div>
                        <div className="pl-6 text-sm text-text-primary">
                          {message.content}
                        </div>
                      </div>
                    )}

                    {/* Assistant message - copilot style */}
                    {message.role === 'assistant' && (
                      <div>
                        <div className="flex items-center gap-2 mb-3">
                          <Sparkles className="w-4 h-4 text-accent" />
                      <span className="text-xs font-medium text-text-muted uppercase tracking-wide">AI 问答</span>
                          {isChatLoading && message === chatMessages[chatMessages.length - 1] && (
                            <Loader2 className="w-3 h-3 animate-spin text-accent" />
                          )}
                        </div>
                        <div className="pl-6 chat-prose">
                          {/* Render steps in order (reasoning, tool calls, content interleaved) */}
                          {message.steps && message.steps.length > 0 ? (
                            <div className="space-y-4">
                              {message.steps.map((step, index) => (
                                <div key={step.id}>
                                  {step.type === 'reasoning' && step.content && (
                                    <div className="text-text-secondary text-sm italic border-l-2 border-text-muted/30 pl-3 mb-3">
                                      <MarkdownRenderer
                                        content={step.content}
                                        onLinkClick={handleLinkClick}
                                      />
                                    </div>
                                  )}
                                  {step.type === 'tool_call' && step.toolCall && (
                                    <div className="mb-3">
                                      <ToolCallCard toolCall={step.toolCall} defaultExpanded={false} />
                                    </div>
                                  )}
                                  {step.type === 'content' && step.content && (
                                    <MarkdownRenderer
                                      content={step.content}
                                      onLinkClick={handleLinkClick}
                                      showCopyButton={index === (message.steps?.length ?? 0) - 1}
                                    />
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            // Fallback: render content + toolCalls separately (old format)
                            <MarkdownRenderer
                              content={message.content}
                              onLinkClick={handleLinkClick}
                              toolCalls={message.toolCalls}
                              showCopyButton={true}
                            />
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {/* Scroll anchor for auto-scroll */}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-3 bg-surface border-t border-border-subtle">
            <div className="flex items-end gap-2 px-3 py-2 bg-elevated border border-border-subtle rounded-xl transition-all focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
              <textarea
                ref={textareaRef}
                value={chatInput}
                onChange={(e) => {
                  setChatInput(e.target.value);
                  requestAnimationFrame(adjustTextareaHeight);
                }}
                onKeyDown={handleKeyDown}
                placeholder="输入你想了解的代码问题…"
                rows={1}
                className="flex-1 bg-transparent border-none outline-none text-sm text-text-primary placeholder:text-text-muted resize-none min-h-[36px] scrollbar-thin"
                style={{ height: '36px', overflowY: 'hidden' }}
              />
              <button
                type="button"
                onClick={clearChat}
                className="px-2 py-1 text-xs text-text-muted hover:text-text-primary transition-colors"
                 title="清空对话"
              >
                 清空
              </button>
              {isChatLoading ? (
                <button
                  type="button"
                  onClick={stopChatResponse}
                  className="w-9 h-9 flex items-center justify-center bg-red-500/80 rounded-md text-white transition-all hover:bg-red-500"
                   title="停止生成"
                >
                  <Square className="w-3.5 h-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSendMessage}
                  disabled={!chatInput.trim() || isAgentInitializing}
                  className="w-9 h-9 flex items-center justify-center bg-accent rounded-md text-white transition-all hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            {!isAgentReady && !isAgentInitializing && (
              <div className="mt-2 text-xs text-amber-200 flex items-center gap-2">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>
                  {isProviderConfigured()
                     ? '正在初始化 AI 助手…'
                     : '请先配置一个 LLM 提供方后再使用聊天。'}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
};
