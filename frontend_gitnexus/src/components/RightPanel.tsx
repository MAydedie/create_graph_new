import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Send,
  Square,
  Sparkles,
  User,
  PanelRightClose,
  Loader2,
  AlertTriangle,
  GitBranch,
  Layers,
  MessageSquare,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import { useAppState } from '../hooks/useAppState';
import { ToolCallCard } from './ToolCallCard';
import { isProviderConfigured } from '../core/llm/settings-service';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ProcessesPanel } from './ProcessesPanel';
import {
  createGraphExtensionsApi,
  type CreateGraphHierarchyContract,
  type CreateGraphRagAskResponse,
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

const normalizeSymbolName = (value: string): string => {
  return value.trim().replace(/\s+/g, '').toLowerCase();
};

const toPartitionSummaries = (
  contract: CreateGraphHierarchyContract | null,
): PartitionSummaryView[] => {
  if (!contract) return [];
  const adapters = isRecord(contract.adapters) ? contract.adapters : {};
  const rawSummaries = adapters.partition_summaries;
  if (!Array.isArray(rawSummaries)) return [];

  const result: PartitionSummaryView[] = [];
  for (const item of rawSummaries) {
    if (!isRecord(item)) continue;

    const partitionId = toStringValue(item.partition_id);
    if (!partitionId) continue;

    const methods = toStringArray(item.methods);
    result.push({
      partitionId,
      name: toStringValue(item.name, partitionId),
      description: toStringValue(item.description),
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

const toRagEvidence = (payload: CreateGraphRagAskResponse | null): RagEvidenceView[] => {
  if (!payload?.evidence || !Array.isArray(payload.evidence)) return [];

  const evidence: RagEvidenceView[] = [];
  for (const item of payload.evidence) {
    if (!isRecord(item)) continue;
    evidence.push({
      rank: String(item.rank ?? ''),
      label: toStringValue(item.label, 'unknown'),
      nodeId: toStringValue(item.node_id),
      filePath: toStringValue(item.file_path, '未知文件'),
      score: String(item.score ?? ''),
      lineStart: toOptionalNumberValue(item.line_start),
      lineEnd: toOptionalNumberValue(item.line_end),
    });
  }

  return evidence;
};

export const RightPanel = () => {
  const {
    isRightPanelOpen,
    setRightPanelOpen,
    rightPanelTab,
    setRightPanelTab,
    projectName,
    availableRepos,
    setHighlightedNodeIds,
    fileContents,
    graph,
    selectedNode,
    setSelectedNode,
    setViewMode,
    addCodeReference,
    // LLM / chat state
    chatMessages,
    isChatLoading,
    agentError,
    isAgentReady,
    isAgentInitializing,
    sendChatMessage,
    stopChatResponse,
    clearChat,
  } = useAppState();

  const [chatInput, setChatInput] = useState('');

  const [hierarchyContract, setHierarchyContract] = useState<CreateGraphHierarchyContract | null>(null);
  const [hierarchyLoading, setHierarchyLoading] = useState(false);
  const [hierarchyError, setHierarchyError] = useState<string | null>(null);
  const [selectedPartitionId, setSelectedPartitionId] = useState<string>('');

  const [ragInput, setRagInput] = useState('');
  const [ragLoading, setRagLoading] = useState(false);
  const [ragError, setRagError] = useState<string | null>(null);
  const [ragResponse, setRagResponse] = useState<CreateGraphRagAskResponse | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const partitionSummaries = useMemo(
    () => toPartitionSummaries(hierarchyContract),
    [hierarchyContract],
  );

  const ragEvidence = useMemo(() => toRagEvidence(ragResponse), [ragResponse]);
  const activeTab = rightPanelTab;
  const setActiveTab = setRightPanelTab;
  const activeProjectPath = useMemo(() => {
    if (!projectName || availableRepos.length === 0) return undefined;
    return availableRepos.find((repo) => repo.name === projectName)?.path;
  }, [availableRepos, projectName]);

  // Auto-scroll to bottom when messages update or while streaming
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  });

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

  const handleOpenLocalPathAnalysis = useCallback(() => {
    const nextUrl = `${window.location.pathname}?tab=path`;
    window.history.replaceState(null, '', nextUrl);
    setRightPanelOpen(false);
    setViewMode('onboarding');
  }, [setRightPanelOpen, setViewMode]);

  const focusPartitionInWorkspace = useCallback((summary: PartitionSummaryView) => {
    if (!graph) return;

    const normalizedMethods = new Set(summary.methods.map(normalizeSymbolName));
    if (normalizedMethods.size === 0) return;

    const candidateNodes = graph.nodes.filter((node) => {
      if (node.label !== 'Method' && node.label !== 'Function') return false;
      const methodName = normalizeSymbolName(node.properties.name ?? '');
      if (!methodName) return false;

      if (normalizedMethods.has(methodName)) return true;
      for (const symbol of normalizedMethods) {
        if (methodName.endsWith(symbol) || symbol.endsWith(methodName)) {
          return true;
        }
      }
      return false;
    });

    if (candidateNodes.length === 0) return;

    const candidateIds = new Set(candidateNodes.map((node) => node.id));
    setHighlightedNodeIds(candidateIds);

    const primaryNode = candidateNodes[0];
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
  }, [addCodeReference, graph, resolveFilePathForUI, setHighlightedNodeIds, setSelectedNode]);

  useEffect(() => {
    if ((activeTab === 'hierarchy' || activeTab === 'rag') && !hierarchyContract && !hierarchyLoading) {
      loadHierarchyContract();
    }
  }, [activeTab, hierarchyContract, hierarchyLoading, loadHierarchyContract]);

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
    await sendChatMessage(text);
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

    setRagLoading(true);
    setRagError(null);

    try {
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

      const response = await createGraphExtensionsApi.askRag('/api', {
        query,
        top_k: 8,
        project_path: activeProjectPath,
        selected_node: selectedNodePayload,
        partition_id: selectedPartitionId || undefined,
      });

      setRagResponse(response);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRagError(message);
    } finally {
      setRagLoading(false);
    }
  }, [activeProjectPath, ragInput, selectedNode, selectedPartitionId]);

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
    'Explain the project architecture',
    'What does this project do?',
    'Show me the most important files',
    'Find all API handlers',
  ];

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
            <span>Nexus AI</span>
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
            <span>Processes</span>
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
            <span>Hierarchy</span>
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
            <span>RAG</span>
          </button>
        </div>

        {/* Close button */}
        <button
          type="button"
          onClick={() => setRightPanelOpen(false)}
          className="p-1.5 text-text-muted hover:text-text-primary hover:bg-hover rounded transition-colors"
          title="Close Panel"
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
              <div className="text-sm font-semibold text-cyan-200">Function Hierarchy Drawer</div>
              <div className="text-xs text-text-muted">Partition / Process / Community summaries from create_graph</div>
            </div>
            <button
              type="button"
              onClick={loadHierarchyContract}
              className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-hover"
              title="Refresh hierarchy contract"
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
              Loading hierarchy contract...
            </div>
          )}

          {!hierarchyLoading && partitionSummaries.length === 0 && !hierarchyError && (
            <div className="px-4 py-4 text-sm text-text-muted space-y-3">
              <div>No partition summaries available yet. Run hierarchy analysis first.</div>
              <button
                type="button"
                onClick={handleOpenLocalPathAnalysis}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-cyan-400/40 bg-cyan-500/15 text-cyan-100 hover:bg-cyan-500/25"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Open Local Path Analysis
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
                Generate Hierarchy via Local Path
              </button>
            </div>
          )}

          {!hierarchyLoading && partitionSummaries.length > 0 && (
            <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-2 scrollbar-thin">
              {partitionSummaries.map((summary) => {
                const isActive = selectedPartitionId === summary.partitionId;
                return (
                  <button
                    key={summary.partitionId}
                    type="button"
                    onClick={() => {
                      setSelectedPartitionId(summary.partitionId);
                      focusPartitionInWorkspace(summary);
                    }}
                    className={`w-full text-left rounded-lg border p-3 transition-colors ${isActive
                      ? 'border-cyan-400/60 bg-cyan-500/10'
                      : 'border-border-subtle bg-elevated/30 hover:bg-elevated/60'
                      }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-medium text-text-primary truncate">{summary.name}</div>
                      <div className="text-[10px] text-cyan-200 border border-cyan-500/40 rounded px-1.5 py-0.5">
                        {summary.partitionId}
                      </div>
                    </div>
                    {summary.description && (
                      <div className="text-xs text-text-secondary mt-1 line-clamp-2">{summary.description}</div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-muted">
                      <span className="px-2 py-0.5 rounded bg-surface border border-border-subtle">Path {summary.pathCount}</span>
                      <span className="px-2 py-0.5 rounded bg-surface border border-border-subtle">Process {summary.processCount}</span>
                      <span className="px-2 py-0.5 rounded bg-surface border border-border-subtle">Community {summary.communityCount}</span>
                      <span className="px-2 py-0.5 rounded bg-surface border border-border-subtle">Methods {summary.methodCount}</span>
                      {summary.hasCfg && <span className="px-2 py-0.5 rounded bg-violet-500/10 border border-violet-500/30 text-violet-200">CFG</span>}
                      {summary.hasDfg && <span className="px-2 py-0.5 rounded bg-fuchsia-500/10 border border-fuchsia-500/30 text-fuchsia-200">DFG</span>}
                      {summary.hasIo && <span className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-200">IO</span>}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* RAG Tab */}
      {activeTab === 'rag' && (
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="px-4 py-3 border-b border-border-subtle bg-elevated/40">
            <div className="text-sm font-semibold text-violet-200">RAG Drawer</div>
            <div className="text-xs text-text-muted mt-1">
              Uses current node + selected hierarchy partition as question context.
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              <span className="px-2 py-0.5 rounded border border-violet-500/30 bg-violet-500/10 text-violet-200">
                Node: {selectedNode?.properties?.name ?? selectedNode?.id ?? 'None'}
              </span>
              <span className="px-2 py-0.5 rounded border border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
                Partition: {selectedPartitionId || 'None'}
              </span>
            </div>
          </div>

          <div className="px-4 pt-3 pb-2 border-b border-border-subtle">
            <textarea
              value={ragInput}
              onChange={(e) => setRagInput(e.target.value)}
              placeholder="Ask with code context..."
              rows={3}
              className="w-full bg-elevated border border-border-subtle rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted resize-y min-h-[88px]"
            />
            <div className="mt-2 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setRagInput('')}
                className="px-2 py-1 text-xs text-text-muted hover:text-text-primary"
              >
                Clear
              </button>
              <button
                type="button"
                onClick={handleAskRag}
                disabled={!ragInput.trim() || ragLoading}
                className="px-3 py-1.5 text-xs rounded bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {ragLoading ? 'Asking...' : 'Ask RAG'}
              </button>
            </div>
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
                Open Local Path Analysis
              </button>
            </div>
          )}

          <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin p-4 space-y-3">
            {ragLoading && (
              <div className="text-sm text-text-muted flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Retrieving evidence and generating answer...
              </div>
            )}

            {!ragLoading && !ragResponse && !ragError && (
              <div className="text-sm text-text-muted">
                Submit a question to get an answer with graph-aware evidence.
              </div>
            )}

            {ragResponse && (
              <>
                <div className="rounded-lg border border-border-subtle bg-elevated/40 p-3">
                  <div className="text-xs uppercase tracking-wide text-violet-300 mb-1">Answer</div>
                  <div className="text-sm text-text-primary whitespace-pre-wrap">{ragResponse.answer}</div>
                </div>

                {ragEvidence.length > 0 && (
                  <div className="rounded-lg border border-border-subtle bg-elevated/20 p-3">
                    <div className="text-xs uppercase tracking-wide text-cyan-300 mb-2 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" />
                      Evidence Hits
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
                          {item.score && <div className="text-[11px] text-cyan-200 mt-1">score: {item.score}</div>}
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

      {/* Chat Content - only show when chat tab is active */}
      {activeTab === 'chat' && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Status bar */}
          <div className="flex items-center gap-2.5 px-4 py-3 bg-elevated/50 border-b border-border-subtle">
            <div className="ml-auto flex items-center gap-2">
              {!isAgentReady && (
                <span className="text-[11px] px-2 py-1 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                  Configure AI
                </span>
              )}
              {isAgentInitializing && (
                <span className="text-[11px] px-2 py-1 rounded-full bg-surface border border-border-subtle flex items-center gap-1 text-text-muted">
                  <Loader2 className="w-3 h-3 animate-spin" /> Connecting
                </span>
              )}
            </div>
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
                  Ask me anything
                </h3>
                <p className="text-sm text-text-secondary leading-relaxed mb-5">
                  I can help you understand the architecture, find functions, or explain connections.
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
                          <span className="text-xs font-medium text-text-muted uppercase tracking-wide">You</span>
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
                          <span className="text-xs font-medium text-text-muted uppercase tracking-wide">Nexus AI</span>
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
                placeholder="Ask about the codebase..."
                rows={1}
                className="flex-1 bg-transparent border-none outline-none text-sm text-text-primary placeholder:text-text-muted resize-none min-h-[36px] scrollbar-thin"
                style={{ height: '36px', overflowY: 'hidden' }}
              />
              <button
                type="button"
                onClick={clearChat}
                className="px-2 py-1 text-xs text-text-muted hover:text-text-primary transition-colors"
                title="Clear chat"
              >
                Clear
              </button>
              {isChatLoading ? (
                <button
                  type="button"
                  onClick={stopChatResponse}
                  className="w-9 h-9 flex items-center justify-center bg-red-500/80 rounded-md text-white transition-all hover:bg-red-500"
                  title="Stop response"
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
                    ? 'Initializing AI agent...'
                    : 'Configure an LLM provider to enable chat.'}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
};
