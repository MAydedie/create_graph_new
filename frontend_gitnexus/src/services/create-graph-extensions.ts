export interface CreateGraphNodeDetailSource {
  available: boolean;
  language?: string;
  file_path?: string;
  line_start?: number;
  line_end?: number;
  snippet?: string;
}

export interface CreateGraphLegacyApiNotice {
  deprecated?: boolean;
  notice?: string;
  replacement?: {
    start?: string;
    status?: string;
    result?: string;
    reply?: string;
    events?: string;
  };
}

export interface CreateGraphNodeDetailResponse {
  entity_id: string;
  kind: string;
  display_name: string;
  file_path?: string;
  line_start?: number;
  line_end?: number;
  source?: CreateGraphNodeDetailSource;
  cfg?: string | null;
  cfg_json?: unknown;
  dfg?: string | null;
  dfg_json?: unknown;
  io?: {
    inputs?: unknown[];
    outputs?: unknown[];
    global_reads?: unknown[];
    global_writes?: unknown[];
  } | null;
  has_cfg?: boolean;
  has_dfg?: boolean;
  has_io?: boolean;
}

export interface CreateGraphHierarchyContract {
  contract_version: string;
  project_path: string;
  capabilities: Record<string, unknown>;
  adapters?: {
    partition_summaries?: unknown[];
  };
  shadow_results?: Record<string, unknown>;
  hierarchy_result?: Record<string, unknown>;
}

export interface CreateGraphPartitionAnalysisResponse {
  call_graph?: Record<string, unknown>;
  controlflow?: Record<string, unknown>;
  dataflow?: Record<string, unknown>;
  entry_points?: unknown[];
  entry_points_shadow?: Record<string, unknown>;
  fqns?: unknown[];
  hypergraph?: Record<string, unknown>;
  hypergraph_viz?: Record<string, unknown>;
  inputs?: unknown[];
  outputs?: unknown[];
  path_analyses?: unknown[];
  path_analysis_info?: Record<string, unknown>;
  paths_map?: Record<string, unknown>;
}

export interface CreateGraphConversationLLMConfig {
  provider?: string;
  api_key: string;
  base_url: string;
  model: string;
}

export interface CreateGraphRagAskRequest {
  query: string;
  top_k?: number;
  project_path?: string;
  selected_node?: Record<string, unknown>;
  partition_id?: string;
  llm_config?: CreateGraphConversationLLMConfig;
}

export interface CreateGraphRagAskResponse {
  query: string;
  answer: string;
  evidence?: Array<Record<string, unknown>>;
  partition?: Record<string, unknown> | null;
  retrieval_bundle?: Record<string, unknown>;
  output_protocol?: Record<string, unknown>;
  evidence_verdict?: Record<string, unknown>;
  solution_packet?: Record<string, unknown>;
  generation?: Record<string, unknown>;
  search?: Record<string, unknown>;
  index_rebuild_status?: Record<string, unknown>;
  legacy?: CreateGraphLegacyApiNotice;
}

export interface CreateGraphMultiAgentSessionStartRequest {
  query: string;
  project_path?: string;
  task_mode?: string;
  partition_id?: string;
  selected_node?: Record<string, unknown>;
  clarification_context?: Record<string, unknown>;
  output_root?: string;
  auto_apply_output?: boolean;
  opencode_enabled?: boolean;
}

export interface CreateGraphFrontDoorRouteRequest {
  query: string;
  project_path?: string;
  partition_id?: string;
  selected_node?: Record<string, unknown>;
  clarificationContext?: Record<string, unknown>;
}

export interface CreateGraphClarificationOption {
  id: string;
  label: string;
  description?: string;
  promptFragment?: string;
}

export interface CreateGraphClarificationField {
  id: string;
  label: string;
}

export interface CreateGraphClarificationPayload {
  id: string;
  round: number;
  maxRounds: number;
  clarityLevel: string;
  inferredIntent: string;
  prompt: string;
  options?: CreateGraphClarificationOption[];
  allowFreeform?: boolean;
  structuredFields?: CreateGraphClarificationField[];
  terminal?: boolean;
  originalQuery?: string;
}

export interface CreateGraphFrontDoorRouteResponse {
  intentGuess: 'general_chat' | 'modify_existing' | 'write_new_code';
  nextStep: 'send_chat' | 'ask_clarification' | 'start_multi_agent';
  safeToCodegen: boolean;
  confidence: 'high' | 'medium' | 'low';
  reason: string;
  taskMode?: string | null;
  projectPath: string;
  clarification?: CreateGraphClarificationPayload;
  legacy?: CreateGraphLegacyApiNotice;
}

export interface CreateGraphMultiAgentSessionStartResponse {
  sessionId: string;
  projectPath: string;
  status: string;
  stage: string;
  message: string;
}

export interface CreateGraphMultiAgentSessionStatusResponse {
  sessionId: string;
  projectPath: string;
  status: string;
  stage: string;
  message: string;
  stageHistory?: Array<Record<string, unknown>>;
  taskSummary?: Record<string, unknown> | null;
  error?: string;
  startedAt?: string;
  updatedAt?: string;
  completedAt?: string;
  swarmEnabled?: boolean;
  advisorEnabled?: boolean;
  opencodeEnabled?: boolean;
  advisor?: Record<string, unknown>;
  opencode?: CreateGraphOutputProtocolOpenCodeKernel & { enabled?: boolean };
  swarm?: {
    enabled?: boolean;
    llm_enabled?: boolean;
    model?: string;
    consensus?: Record<string, unknown>;
    agents?: Record<string, unknown>;
    updatedAt?: string;
  };
}

export interface CreateGraphSwarmAgentDecision {
  agent?: string;
  summary?: string;
  confidence?: 'high' | 'medium' | 'low' | string;
  risks?: string[];
  actions?: string[];
  status?: string;
}

export interface CreateGraphSwarmConsensus {
  summary?: string;
  confidence?: 'high' | 'medium' | 'low' | string;
  risks?: string[];
  actions?: string[];
}

export interface CreateGraphSwarmPacket {
  enabled?: boolean;
  llm_enabled?: boolean;
  model?: string;
  agents?: Record<string, CreateGraphSwarmAgentDecision>;
  consensus?: CreateGraphSwarmConsensus;
  updatedAt?: string;
}

export interface CreateGraphConversationSessionStartRequest {
  query: string;
  project_path?: string;
  conversation_id?: string;
  selected_node?: Record<string, unknown>;
  partition_id?: string;
  clarification_context?: Record<string, unknown>;
  reply_payload?: Record<string, unknown>;
  llm_config?: CreateGraphConversationLLMConfig;
  auto_start_multi_agent?: boolean;
  force_action?: 'clarify' | 'general_chat' | 'run_retrieval' | 'start_multi_agent';
  force_fallback_clarification?: boolean;
  output_root?: string;
  auto_apply_output?: boolean;
  opencode_enabled?: boolean;
}

export interface CreateGraphConversationPendingQuestionOption {
  label: string;
  description?: string;
}

export interface CreateGraphConversationPendingQuestion {
  questionId: string;
  question: string;
  header?: string;
  options?: CreateGraphConversationPendingQuestionOption[];
  multiple?: boolean;
  custom?: boolean;
  source?: string;
  projectPath?: string;
  reason?: string;
  createdAt?: string;
}

export interface CreateGraphConversationSessionStartResponse {
  sessionId: string;
  conversationId: string;
  projectPath: string;
  status: string;
  stage: string;
  message: string;
}

export interface CreateGraphConversationSessionStatusResponse {
  sessionId: string;
  conversationId?: string;
  projectPath: string;
  status: string;
  stage: string;
  message: string;
  error?: string;
  startedAt?: string;
  updatedAt?: string;
  completedAt?: string;
  swarm?: {
    enabled?: boolean;
    llm_enabled?: boolean;
    model?: string;
    consensus?: Record<string, unknown>;
    agents?: Record<string, unknown>;
    updatedAt?: string;
  };
}

export interface CreateGraphConversationListItem {
  conversationId: string;
  projectPath?: string;
  status?: string;
  messageCount?: number;
  hasPendingQuestion?: boolean;
  compactionCount?: number;
  updatedAt?: string;
  createdAt?: string;
}

export interface CreateGraphConversationDetailResponse {
  conversationId: string;
  projectPath?: string;
  status?: string;
  messageCount?: number;
  partCount?: number;
  pendingQuestion?: CreateGraphConversationPendingQuestion;
  summarySnapshot?: Record<string, unknown>;
  compactionCount?: number;
  keyFactsMemory?: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

export interface CreateGraphConversationMessagesResponse {
  conversationId: string;
  messages: Array<Record<string, unknown>>;
  parts: Array<Record<string, unknown>>;
  pendingQuestion?: CreateGraphConversationPendingQuestion;
  questionReplies?: Array<Record<string, unknown>>;
  compactionHistory?: Array<Record<string, unknown>>;
  keyFactsMemory?: Record<string, unknown>;
  updatedAt?: string;
}

export interface CreateGraphConversationSessionResultResponse {
  conversationId: string;
  intentGuess?: string;
  nextStep: 'ask_clarification' | 'send_chat' | 'retrieval_answer' | 'start_multi_agent';
  safeToCodegen: boolean;
  confidence?: string;
  reason?: string;
  taskMode?: string | null;
  projectPath?: string;
  answer?: string;
  pendingQuestion?: CreateGraphConversationPendingQuestion;
  retrieval?: CreateGraphConversationRetrievalPayload;
  handoff?: Record<string, unknown>;
  memory?: Record<string, unknown>;
  compaction?: Record<string, unknown> | null;
}

export interface CreateGraphConversationRetrievalHighlight {
  id?: string;
  label?: string;
  file?: string;
  file_path?: string;
  score?: number;
  sources?: string[];
  snippet?: string;
  lineStart?: number;
  lineEnd?: number;
  line_start?: number;
  line_end?: number;
  graph_context?: unknown[];
}

export interface CreateGraphConversationRetrievalPayload {
  ok?: boolean;
  error?: string | null;
  highlights?: CreateGraphConversationRetrievalHighlight[];
  validationCommands?: string[];
  validation_commands?: string[];
  mode?: string;
  search?: Record<string, unknown>;
}

export interface CreateGraphConversationReplyRequest {
  project_path?: string;
  answer?: string;
  query?: string;
  selectedOptionLabels?: string[];
  clarification_context?: Record<string, unknown>;
  llm_config?: CreateGraphConversationLLMConfig;
  auto_start_multi_agent?: boolean;
  force_action?: 'clarify' | 'general_chat' | 'run_retrieval' | 'start_multi_agent';
  force_fallback_clarification?: boolean;
  output_root?: string;
  auto_apply_output?: boolean;
  opencode_enabled?: boolean;
}

export interface CreateGraphConversationSseBootstrapPayload {
  conversationId: string;
  status?: string;
  pendingQuestion?: CreateGraphConversationPendingQuestion | null;
  updatedAt?: string;
  cursor?: number;
}

export interface CreateGraphConversationSseEventFrame {
  seq?: number;
  eventId?: string;
  type: string;
  payload?: Record<string, unknown>;
  createdAt?: string;
}

export interface CreateGraphConversationSseEvent {
  event: string;
  id?: number;
  data: unknown;
}

export interface CreateGraphConversationStreamOptions {
  since?: number;
  sessionId?: string;
  timeoutSeconds?: number;
  intervalMs?: number;
  signal?: AbortSignal;
  onBootstrap?: (payload: CreateGraphConversationSseBootstrapPayload) => void;
  onEvent?: (event: CreateGraphConversationSseEvent) => boolean | Promise<boolean> | undefined;
}

export interface CreateGraphConversationStreamResult {
  lastSeq: number;
  streamEnded: boolean;
  endReason?: string;
}

export interface CreateGraphConversationExportRunbookRequest {
  markdown: string;
  runbook_text?: string;
  report_dir?: string;
  include_messages?: boolean;
  include_events?: boolean;
  metadata?: Record<string, unknown>;
}

export interface CreateGraphConversationExportRunbookResponse {
  conversationId: string;
  reportDir: string;
  markdownPath: string;
  executionRecordPath: string;
  generatedAt: string;
}

export interface CreateGraphOutputProtocolJudgment {
  status: 'ready' | 'needs_refinement';
  confidence: string;
  reasons: string[];
}

export interface CreateGraphOutputProtocolPathCandidate extends Record<string, unknown> {
  path_id?: string;
  partition_id?: string;
  path_name?: string;
  path_description?: string;
  function_chain?: string[];
  leaf_node?: string;
  selection_score?: number;
  worthiness_score?: number;
  selection_reason?: string;
  source?: string;
}

export interface CreateGraphOutputProtocolAdvisor extends Record<string, unknown> {
  status?: string;
  enabled?: boolean;
  mode?: string;
  recommended?: Record<string, unknown>;
  analysis?: Record<string, unknown>;
  constraint_types?: string[];
  constraints?: Record<string, unknown>;
  source_targets?: string[];
  followup_advisors?: string[];
}

export interface CreateGraphOutputProtocolAnalysis {
  summary: string;
  key_reasoning: string[];
  impacted_files: string[];
  selected_path?: CreateGraphOutputProtocolPathCandidate;
  candidate_paths?: CreateGraphOutputProtocolPathCandidate[];
  selection_mode?: string;
  selection_reason?: string;
  advisor?: CreateGraphOutputProtocolAdvisor;
}

export interface CreateGraphOutputProtocolOpenCodeKernel {
  status?: string;
  reason?: string;
  duration_ms?: number;
  model?: string;
  agent?: string;
  session_id?: string;
}

export interface CreateGraphOutputProtocol {
  version: string;
  task_mode: string;
  judgment: CreateGraphOutputProtocolJudgment;
  analysis: CreateGraphOutputProtocolAnalysis;
  advisor?: CreateGraphOutputProtocolAdvisor;
  opencode?: Record<string, unknown>;
  opencode_kernel?: CreateGraphOutputProtocolOpenCodeKernel;
  code_snippets: Array<Record<string, unknown>>;
  validation_commands?: string[];
  remaining_risks_constraints: string[];
  constraints: string[];
}

export interface CreateGraphSolutionPacket {
  analysis?: Record<string, unknown>;
  advisor_packet?: Record<string, unknown>;
  edit_plan?: Array<Record<string, unknown>>;
  snippet_blocks?: Array<Record<string, unknown>>;
  validation?: string[];
  opencode_kernel?: CreateGraphOutputProtocolOpenCodeKernel;
  output_protocol?: CreateGraphOutputProtocol;
}

export interface CreateGraphMultiAgentResultResponse {
  intent_packet?: Record<string, unknown>;
  retrieval_bundle?: Record<string, unknown>;
  evidence_verdict?: Record<string, unknown>;
  advisor_packet?: Record<string, unknown>;
  solution_packet?: CreateGraphSolutionPacket;
  workbench?: Record<string, unknown>;
  output_protocol?: CreateGraphOutputProtocol;
  opencode_kernel?: CreateGraphOutputProtocolOpenCodeKernel;
  swarm_packet?: CreateGraphSwarmPacket;
}

export interface CreateGraphWorkbenchSessionStartRequest {
  project_path: string;
  experience_output_root?: string;
}

export interface CreateGraphWorkbenchSessionStartResponse {
  sessionId: string;
  projectPath: string;
  status: string;
  phase: string;
  message: string;
}

export interface CreateGraphWorkbenchSessionStatusResponse {
  sessionId: string;
  projectPath: string;
  status: string;
  phase: string;
  progress: number;
  message: string;
  stageLabel?: string;
  stageDetail?: string;
  error?: string;
  bootstrapReady: boolean;
  startedAt?: string;
  updatedAt?: string;
  completedAt?: string;
}

export interface CreateGraphWorkbenchProjectStatusResponse {
  projectPath: string;
  displayName?: string;
  status: string;
  phase: string;
  progress: number;
  message: string;
  qualityHint: string;
  experienceReady: boolean;
  bootstrapReady: boolean;
  activeSessionId?: string | null;
  updatedAt?: string;
}

export interface CreateGraphWorkbenchBootstrapResponse {
  contractVersion: string;
  sessionId: string;
  projectPath: string;
  status: Record<string, unknown>;
}

export interface CreateGraphExperienceLibraryEntry {
  relativePath: string;
  absolutePath: string;
  filename: string;
  type: 'generated' | 'imported';
  projectName?: string;
  analysisTimestamp?: string | null;
  updatedAt: string;
  day: string;
  size: number;
  etag: string;
}

export interface CreateGraphExperienceLibrarySummary {
  totalFiles: number;
  generatedFiles: number;
  importedFiles: number;
  experienceDays: number;
}

export interface CreateGraphExperienceLibraryOverviewResponse {
  projectPath: string;
  experienceOutputRoot: string;
  experiencePathsDir: string;
  entries: CreateGraphExperienceLibraryEntry[];
  summary: CreateGraphExperienceLibrarySummary;
}

export interface CreateGraphExperienceLibraryFileResponse {
  projectPath: string;
  relativePath: string;
  absolutePath: string;
  filename: string;
  content: string;
  etag: string;
  updatedAt: string;
  size: number;
}

export interface CreateGraphExperienceLibrarySaveRequest {
  project_path: string;
  relative_path: string;
  content: string;
  etag?: string;
}

export interface CreateGraphExperienceLibrarySaveResponse {
  ok: boolean;
  relativePath: string;
  absolutePath: string;
  etag: string;
  updatedAt: string;
  size: number;
}

export interface CreateGraphExperienceLibraryImportItem {
  sourceName: string;
  storedRelativePath: string;
  storedAbsolutePath: string;
  type: 'json' | 'md';
}

export interface CreateGraphExperienceLibraryImportResponse {
  ok: boolean;
  imported: CreateGraphExperienceLibraryImportItem[];
}

export interface CreateGraphFixedScenarioBenchmarkStartRequest {
  project_path?: string;
  report_dir?: string;
}

export interface CreateGraphFixedScenarioBenchmarkStartResponse {
  sessionId: string;
  status: string;
  phase: string;
  projectPath: string;
  reportDir: string;
  message: string;
}

export interface CreateGraphFixedScenarioBenchmarkStatusResponse {
  sessionId: string;
  status: string;
  phase: string;
  progress: number;
  message: string;
  error?: string;
  projectPath: string;
  reportDir: string;
  startedAt?: string;
  updatedAt?: string;
  completedAt?: string;
}

export interface CreateGraphFixedScenarioBenchmarkResultResponse {
  generatedAt: string;
  projectPath: string;
  conversationId: string;
  summary: Record<string, unknown>;
  scenarios: Array<Record<string, unknown>>;
  artifacts?: {
    jsonPath?: string;
    markdownPath?: string;
  };
  comparison?: Record<string, unknown>;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json();
  if (!response.ok) {
    const errorMessage = (payload as { error?: string })?.error || `Request failed: ${response.status}`;
    throw new Error(errorMessage);
  }
  return payload as T;
}

async function parseErrorResponse(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { error?: unknown; message?: unknown };
    if (typeof payload.error === 'string' && payload.error.trim()) return payload.error;
    if (typeof payload.message === 'string' && payload.message.trim()) return payload.message;
  } catch {
    try {
      const text = await response.text();
      if (text.trim()) return text.trim();
    } catch {
      // Ignore response parsing errors.
    }
  }
  return `Request failed: ${response.status}`;
}

const parseSseEventBlock = (block: string): { event: string; id?: number; dataText: string } | null => {
  const lines = block.split('\n').map((line) => line.trimEnd());
  if (lines.length === 0) return null;

  let eventName = 'message';
  let eventId: number | undefined;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue;
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim() || 'message';
      continue;
    }
    if (line.startsWith('id:')) {
      const rawId = Number(line.slice('id:'.length).trim());
      if (Number.isFinite(rawId)) {
        eventId = rawId;
      }
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart());
    }
  }

  if (dataLines.length === 0) return null;
  return {
    event: eventName,
    id: eventId,
    dataText: dataLines.join('\n'),
  };
};

async function streamConversationEventsInternal(
  baseApiUrl: string,
  conversationId: string,
  options: CreateGraphConversationStreamOptions = {},
): Promise<CreateGraphConversationStreamResult> {
  const encodedConversationId = encodeURIComponent(conversationId);
  const params = new URLSearchParams();
  if (typeof options.since === 'number' && Number.isFinite(options.since)) {
    params.set('since', String(Math.max(0, Math.floor(options.since))));
  }
  if (typeof options.sessionId === 'string' && options.sessionId.trim()) {
    params.set('session_id', options.sessionId.trim());
  }
  if (typeof options.timeoutSeconds === 'number' && Number.isFinite(options.timeoutSeconds)) {
    params.set('timeout', String(Math.max(10, Math.floor(options.timeoutSeconds))));
  }
  if (typeof options.intervalMs === 'number' && Number.isFinite(options.intervalMs)) {
    params.set('intervalMs', String(Math.max(100, Math.floor(options.intervalMs))));
  }

  const suffix = params.toString() ? `?${params.toString()}` : '';
  const response = await fetch(`${baseApiUrl}/conversations/${encodedConversationId}/events${suffix}`, {
    method: 'GET',
    headers: {
      Accept: 'text/event-stream',
      'Cache-Control': 'no-cache',
    },
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`SSE stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let lastSeq = typeof options.since === 'number' && Number.isFinite(options.since) ? options.since : 0;
  let streamEnded = false;
  let endReason = '';
  let shouldStop = false;

  while (true) {
    if (shouldStop) {
      break;
    }
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      const parsed = parseSseEventBlock(block);
      if (!parsed) continue;

      let data: unknown = parsed.dataText;
      try {
        data = JSON.parse(parsed.dataText);
      } catch (_error) {
        data = parsed.dataText;
      }

      if (parsed.event === 'bootstrap' && typeof data === 'object' && data !== null) {
        options.onBootstrap?.(data as CreateGraphConversationSseBootstrapPayload);
      } else {
        const callbackResult = await options.onEvent?.({
          event: parsed.event,
          id: parsed.id,
          data,
        });
        if (callbackResult === true) {
          shouldStop = true;
        }
      }

      if (typeof parsed.id === 'number' && Number.isFinite(parsed.id)) {
        lastSeq = Math.max(lastSeq, parsed.id);
      }
      if (typeof data === 'object' && data !== null) {
        const seqValue = (data as { seq?: unknown }).seq;
        if (typeof seqValue === 'number' && Number.isFinite(seqValue)) {
          lastSeq = Math.max(lastSeq, seqValue);
        }
      }

      if (parsed.event === 'stream_end') {
        streamEnded = true;
        if (typeof data === 'object' && data !== null) {
          const reason = (data as { reason?: unknown }).reason;
          if (typeof reason === 'string') {
            endReason = reason;
          }
        }
      }

      if (shouldStop) {
        break;
      }
    }
  }

  try {
    await reader.cancel();
  } catch (_error) {
    // Ignore cancel errors for non-cancelable streams.
  }

  return {
    lastSeq,
    streamEnded,
    endReason: endReason || undefined,
  };
}

/**
 * Create_graph extension APIs used after frontend shell cutover.
 *
 * NOTE:
 * - This file is intentionally side-effect free for staged migration.
 * - Wiring into panels happens in the next implementation batch.
 */
export const createGraphExtensionsApi = {
  fetchNodeDetail(baseApiUrl: string, entityId: string, projectPath?: string): Promise<CreateGraphNodeDetailResponse> {
    const encodedEntity = encodeURIComponent(entityId);
    const query = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : '';
    return fetchJson<CreateGraphNodeDetailResponse>(`${baseApiUrl}/node_detail/${encodedEntity}${query}`);
  },

  fetchHierarchyContract(baseApiUrl: string, projectPath?: string): Promise<CreateGraphHierarchyContract> {
    const query = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : '';
    return fetchJson<CreateGraphHierarchyContract>(`${baseApiUrl}/phase6/read_contract${query}`);
  },

  fetchPartitionAnalysis(
    baseApiUrl: string,
    partitionId: string,
    projectPath?: string,
  ): Promise<CreateGraphPartitionAnalysisResponse> {
    const encodedPartitionId = encodeURIComponent(partitionId);
    const query = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : '';
    return fetchJson<CreateGraphPartitionAnalysisResponse>(`${baseApiUrl}/partition/${encodedPartitionId}/analysis${query}`);
  },

  askRag(baseApiUrl: string, payload: CreateGraphRagAskRequest): Promise<CreateGraphRagAskResponse> {
    return fetchJson<CreateGraphRagAskResponse>(`${baseApiUrl}/rag/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  routeFrontDoorRequest(
    baseApiUrl: string,
    payload: CreateGraphFrontDoorRouteRequest,
  ): Promise<CreateGraphFrontDoorRouteResponse> {
    return fetchJson<CreateGraphFrontDoorRouteResponse>(`${baseApiUrl}/front_door/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  startMultiAgentSession(
    baseApiUrl: string,
    payload: CreateGraphMultiAgentSessionStartRequest,
  ): Promise<CreateGraphMultiAgentSessionStartResponse> {
    return fetchJson<CreateGraphMultiAgentSessionStartResponse>(`${baseApiUrl}/multi_agent/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  fetchMultiAgentSessionStatus(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphMultiAgentSessionStatusResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphMultiAgentSessionStatusResponse>(`${baseApiUrl}/multi_agent/session/${encodedSessionId}/status`);
  },

  fetchMultiAgentSessionResult(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphMultiAgentResultResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphMultiAgentResultResponse>(`${baseApiUrl}/multi_agent/session/${encodedSessionId}/result`);
  },

  startConversationSession(
    baseApiUrl: string,
    payload: CreateGraphConversationSessionStartRequest,
  ): Promise<CreateGraphConversationSessionStartResponse> {
    return fetchJson<CreateGraphConversationSessionStartResponse>(`${baseApiUrl}/conversations/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  fetchConversationSessionStatus(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphConversationSessionStatusResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphConversationSessionStatusResponse>(`${baseApiUrl}/conversations/session/${encodedSessionId}/status`);
  },

  fetchConversationSessionResult(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphConversationSessionResultResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphConversationSessionResultResponse>(`${baseApiUrl}/conversations/session/${encodedSessionId}/result`);
  },

  listConversations(
    baseApiUrl: string,
    projectPath?: string,
  ): Promise<CreateGraphConversationListItem[]> {
    const query = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : '';
    return fetchJson<CreateGraphConversationListItem[]>(`${baseApiUrl}/conversations${query}`);
  },

  fetchConversation(
    baseApiUrl: string,
    conversationId: string,
  ): Promise<CreateGraphConversationDetailResponse> {
    const encodedConversationId = encodeURIComponent(conversationId);
    return fetchJson<CreateGraphConversationDetailResponse>(`${baseApiUrl}/conversations/${encodedConversationId}`);
  },

  fetchConversationMessages(
    baseApiUrl: string,
    conversationId: string,
  ): Promise<CreateGraphConversationMessagesResponse> {
    const encodedConversationId = encodeURIComponent(conversationId);
    return fetchJson<CreateGraphConversationMessagesResponse>(`${baseApiUrl}/conversations/${encodedConversationId}/messages`);
  },

  replyConversation(
    baseApiUrl: string,
    conversationId: string,
    payload: CreateGraphConversationReplyRequest,
  ): Promise<CreateGraphConversationSessionStartResponse> {
    const encodedConversationId = encodeURIComponent(conversationId);
    return fetchJson<CreateGraphConversationSessionStartResponse>(`${baseApiUrl}/conversations/${encodedConversationId}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  streamConversationEvents(
    baseApiUrl: string,
    conversationId: string,
    options?: CreateGraphConversationStreamOptions,
  ): Promise<CreateGraphConversationStreamResult> {
    return streamConversationEventsInternal(baseApiUrl, conversationId, options);
  },

  exportConversationRunbook(
    baseApiUrl: string,
    conversationId: string,
    payload: CreateGraphConversationExportRunbookRequest,
  ): Promise<CreateGraphConversationExportRunbookResponse> {
    const encodedConversationId = encodeURIComponent(conversationId);
    return fetchJson<CreateGraphConversationExportRunbookResponse>(
      `${baseApiUrl}/conversations/${encodedConversationId}/export_runbook`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    );
  },

  startWorkbenchSession(
    baseApiUrl: string,
    payload: CreateGraphWorkbenchSessionStartRequest,
  ): Promise<CreateGraphWorkbenchSessionStartResponse> {
    return fetchJson<CreateGraphWorkbenchSessionStartResponse>(`${baseApiUrl}/workbench/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  fetchWorkbenchSessionStatus(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphWorkbenchSessionStatusResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphWorkbenchSessionStatusResponse>(`${baseApiUrl}/workbench/session/${encodedSessionId}/status`);
  },

  fetchWorkbenchProjectStatus(
    baseApiUrl: string,
    projectPath?: string,
  ): Promise<CreateGraphWorkbenchProjectStatusResponse> {
    const query = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : '';
    return fetchJson<CreateGraphWorkbenchProjectStatusResponse>(`${baseApiUrl}/workbench/project_status${query}`);
  },

  fetchWorkbenchSessionBootstrap(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphWorkbenchBootstrapResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphWorkbenchBootstrapResponse>(`${baseApiUrl}/workbench/session/${encodedSessionId}/bootstrap`);
  },

  openFileSystemPath(
    baseApiUrl: string,
    path: string,
  ): Promise<{ ok: boolean; path: string; action: string }> {
    return fetchJson<{ ok: boolean; path: string; action: string }>(`${baseApiUrl}/fs/open`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
  },

  fetchExperienceLibrary(
    baseApiUrl: string,
    projectPath: string,
  ): Promise<CreateGraphExperienceLibraryOverviewResponse> {
    const query = `?project_path=${encodeURIComponent(projectPath)}`;
    return fetchJson<CreateGraphExperienceLibraryOverviewResponse>(`${baseApiUrl}/experience/library${query}`);
  },

  readExperienceLibraryFile(
    baseApiUrl: string,
    projectPath: string,
    relativePath: string,
  ): Promise<CreateGraphExperienceLibraryFileResponse> {
    const query = new URLSearchParams({
      project_path: projectPath,
      relative_path: relativePath,
    });
    return fetchJson<CreateGraphExperienceLibraryFileResponse>(`${baseApiUrl}/experience/library/file?${query.toString()}`);
  },

  saveExperienceLibraryFile(
    baseApiUrl: string,
    payload: CreateGraphExperienceLibrarySaveRequest,
  ): Promise<CreateGraphExperienceLibrarySaveResponse> {
    return fetchJson<CreateGraphExperienceLibrarySaveResponse>(`${baseApiUrl}/experience/library/file/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  async importExperienceLibraryFiles(
    baseApiUrl: string,
    projectPath: string,
    files: File[],
  ): Promise<CreateGraphExperienceLibraryImportResponse> {
    const formData = new FormData();
    formData.append('project_path', projectPath);
    for (const file of files) {
      formData.append('files', file);
    }

    const response = await fetch(`${baseApiUrl}/experience/library/import`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(await parseErrorResponse(response));
    }

    return await response.json() as CreateGraphExperienceLibraryImportResponse;
  },

  startFixedScenarioBenchmark(
    baseApiUrl: string,
    payload: CreateGraphFixedScenarioBenchmarkStartRequest,
  ): Promise<CreateGraphFixedScenarioBenchmarkStartResponse> {
    return fetchJson<CreateGraphFixedScenarioBenchmarkStartResponse>(`${baseApiUrl}/benchmark/fixed_scenario/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  fetchFixedScenarioBenchmarkStatus(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphFixedScenarioBenchmarkStatusResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphFixedScenarioBenchmarkStatusResponse>(`${baseApiUrl}/benchmark/fixed_scenario/${encodedSessionId}/status`);
  },

  fetchFixedScenarioBenchmarkResult(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphFixedScenarioBenchmarkResultResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphFixedScenarioBenchmarkResultResponse>(`${baseApiUrl}/benchmark/fixed_scenario/${encodedSessionId}/result`);
  },
};
