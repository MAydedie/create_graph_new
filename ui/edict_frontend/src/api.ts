import type {
  CommunityShadowResponse,
  ConversationDetailResponse,
  ConversationMessagesResponse,
  ConversationResultResponse,
  ConversationSessionStartResponse,
  ConversationSessionStatusResponse,
  ConversationSseBootstrapPayload,
  ConversationSseEvent,
  ConversationSseEventFrame,
  ConversationSummaryResponse,
  DashboardResources,
  Loadable,
  MultiAgentResultResponse,
  MultiAgentSessionStartResponse,
  MultiAgentSessionStatusResponse,
  ProcessesResponse,
  ProjectStatusResponse,
  ReadContractResponse,
  WorkbenchBootstrapResponse,
  WorkbenchSessionStartResponse,
  WorkbenchSessionStatusResponse,
} from './types';

type GetEndpoint =
  | '/api/workbench/project_status'
  | '/api/processes'
  | '/api/community_shadow'
  | '/api/phase6/read_contract';

interface JsonPayload {
  error?: string;
  message?: string;
  [key: string]: unknown;
}

interface StreamOptions {
  since?: number;
  sessionId?: string;
  finalOnly?: boolean;
  onBootstrap?: (payload: ConversationSseBootstrapPayload) => void;
  onEvent?: (event: ConversationSseEvent) => void;
  onEnd?: (event: ConversationSseEvent) => void;
  onError?: (message: string) => void;
}

const LOADING: Loadable<never> = { state: 'loading' };

const STREAM_EVENTS = [
  'bootstrap',
  'heartbeat',
  'stream_end',
  'turn.state_changed',
  'turn.decided',
  'retrieval.progress',
  'tool.run_hybrid_shadow.completed',
  'clarification.requested',
  'conversation.compacted',
  'task.handoff.auto_started',
  'multi_agent.started',
  'multi_agent.stage',
  'swarm.agent.updated',
  'swarm.consensus.updated',
  'multi_agent.completed',
  'multi_agent.failed',
  'turn.failed',
  'turn.completed',
];

function isRecord(value: unknown): value is JsonPayload {
  return typeof value === 'object' && value !== null;
}

function extractMessage(payload: unknown, fallback: string): string {
  if (typeof payload === 'string' && payload.trim()) {
    return payload;
  }

  if (isRecord(payload)) {
    const errorMessage = typeof payload.error === 'string' ? payload.error.trim() : '';
    if (errorMessage) {
      return errorMessage;
    }

    const message = typeof payload.message === 'string' ? payload.message.trim() : '';
    if (message) {
      return message;
    }
  }

  return fallback;
}

function createProjectUrl(endpoint: GetEndpoint, projectPath: string): string {
  const url = new URL(endpoint, window.location.origin);
  url.searchParams.set('project_path', projectPath);
  return url.toString();
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  const contentType = response.headers.get('content-type') ?? '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    throw new Error(extractMessage(payload, `Request failed with ${response.status}`));
  }

  return payload as T;
}

async function requestLoadable<T>(endpoint: GetEndpoint, projectPath: string, signal: AbortSignal): Promise<Loadable<T>> {
  try {
    const response = await fetch(createProjectUrl(endpoint, projectPath), {
      headers: {
        Accept: 'application/json',
      },
      signal,
    });

    const contentType = response.headers.get('content-type') ?? '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();

    if (!response.ok) {
      const message = extractMessage(payload, `${endpoint} 请求失败`);
      if (response.status === 404) {
        return { state: 'empty', message, status: response.status };
      }
      return { state: 'error', message, status: response.status };
    }

    return {
      state: 'success',
      data: payload as T,
      status: response.status,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }

    return {
      state: 'error',
      message: error instanceof Error ? error.message : `${endpoint} 请求失败`,
    };
  }
}

function normalizeProcesses(loadable: Loadable<ProcessesResponse>): Loadable<ProcessesResponse> {
  if (loadable.state !== 'success') {
    return loadable;
  }

  if (!Array.isArray(loadable.data.processes) || loadable.data.processes.length === 0) {
    return {
      state: 'empty',
      message: '当前项目还没有可展示的流程影子结果。',
      status: loadable.status,
      data: loadable.data,
    };
  }

  return loadable;
}

function normalizeCommunities(loadable: Loadable<CommunityShadowResponse>): Loadable<CommunityShadowResponse> {
  if (loadable.state !== 'success') {
    return loadable;
  }

  const communities = Array.isArray(loadable.data.communities) ? loadable.data.communities : [];
  if (communities.length === 0) {
    return {
      state: 'empty',
      message: '当前项目还没有社区影子结果。',
      status: loadable.status,
      data: loadable.data,
    };
  }

  return loadable;
}

export function createLoadingResources(): DashboardResources {
  return {
    status: LOADING,
    processes: LOADING,
    community: LOADING,
    readContract: LOADING,
  } as DashboardResources;
}

export async function loadDashboardResources(projectPath: string, signal: AbortSignal): Promise<DashboardResources> {
  const [status, processes, community, readContract] = await Promise.all([
    requestLoadable<ProjectStatusResponse>('/api/workbench/project_status', projectPath, signal),
    requestLoadable<ProcessesResponse>('/api/processes', projectPath, signal),
    requestLoadable<CommunityShadowResponse>('/api/community_shadow', projectPath, signal),
    requestLoadable<ReadContractResponse>('/api/phase6/read_contract', projectPath, signal),
  ]);

  return {
    status,
    processes: normalizeProcesses(processes),
    community: normalizeCommunities(community),
    readContract,
  };
}

export async function startWorkbenchSession(projectPath: string): Promise<WorkbenchSessionStartResponse> {
  return requestJson<WorkbenchSessionStartResponse>('/api/workbench/session/start', {
    method: 'POST',
    body: JSON.stringify({ project_path: projectPath }),
  });
}

export async function fetchWorkbenchSessionStatus(sessionId: string): Promise<WorkbenchSessionStatusResponse> {
  return requestJson<WorkbenchSessionStatusResponse>(`/api/workbench/session/${encodeURIComponent(sessionId)}/status`);
}

export async function fetchWorkbenchBootstrap(sessionId: string): Promise<WorkbenchBootstrapResponse> {
  return requestJson<WorkbenchBootstrapResponse>(`/api/workbench/session/${encodeURIComponent(sessionId)}/bootstrap`);
}

export async function startConversationSession(projectPath: string, query: string): Promise<ConversationSessionStartResponse> {
  return requestJson<ConversationSessionStartResponse>('/api/conversations/session/start', {
    method: 'POST',
    body: JSON.stringify({
      project_path: projectPath,
      query,
      auto_start_multi_agent: false,
    }),
  });
}

export async function fetchConversationSessionStatus(sessionId: string): Promise<ConversationSessionStatusResponse> {
  return requestJson<ConversationSessionStatusResponse>(`/api/conversations/session/${encodeURIComponent(sessionId)}/status`);
}

export async function fetchConversationSessionResult(sessionId: string): Promise<ConversationResultResponse> {
  return requestJson<ConversationResultResponse>(`/api/conversations/session/${encodeURIComponent(sessionId)}/result`);
}

export async function fetchConversationDetail(conversationId: string): Promise<ConversationDetailResponse> {
  return requestJson<ConversationDetailResponse>(`/api/conversations/${encodeURIComponent(conversationId)}`);
}

export async function fetchConversationMessages(conversationId: string): Promise<ConversationMessagesResponse> {
  return requestJson<ConversationMessagesResponse>(`/api/conversations/${encodeURIComponent(conversationId)}/messages`);
}

export async function fetchConversationSummary(conversationId: string): Promise<ConversationSummaryResponse> {
  return requestJson<ConversationSummaryResponse>(`/api/conversations/${encodeURIComponent(conversationId)}/summary`);
}

export async function replyConversationQuestion(params: {
  conversationId: string;
  projectPath: string;
  answer?: string;
  selectedOptionLabels?: string[];
}): Promise<ConversationSessionStartResponse> {
  return requestJson<ConversationSessionStartResponse>(`/api/conversations/${encodeURIComponent(params.conversationId)}/reply`, {
    method: 'POST',
    body: JSON.stringify({
      project_path: params.projectPath,
      answer: params.answer,
      selectedOptionLabels: params.selectedOptionLabels,
      auto_start_multi_agent: false,
    }),
  });
}

export async function startMultiAgentSession(params: {
  projectPath: string;
  query: string;
  taskMode?: string | null;
  conversationId?: string;
}): Promise<MultiAgentSessionStartResponse> {
  return requestJson<MultiAgentSessionStartResponse>('/api/multi_agent/session/start', {
    method: 'POST',
    body: JSON.stringify({
      project_path: params.projectPath,
      query: params.query,
      task_mode: params.taskMode ?? 'modify_existing',
      conversation_id: params.conversationId,
      swarm_enabled: true,
    }),
  });
}

export async function fetchMultiAgentSessionStatus(sessionId: string): Promise<MultiAgentSessionStatusResponse> {
  return requestJson<MultiAgentSessionStatusResponse>(`/api/multi_agent/session/${encodeURIComponent(sessionId)}/status`);
}

export async function fetchMultiAgentSessionResult(sessionId: string): Promise<MultiAgentResultResponse> {
  return requestJson<MultiAgentResultResponse>(`/api/multi_agent/session/${encodeURIComponent(sessionId)}/result`);
}

function parseEventData(event: MessageEvent<string>): unknown {
  try {
    return JSON.parse(event.data);
  } catch {
    return event.data;
  }
}

function coerceEvent(name: string, event: MessageEvent<string>): ConversationSseEvent {
  const data = parseEventData(event);
  const id = event.lastEventId ? Number(event.lastEventId) : undefined;
  return {
    event: name,
    id: Number.isFinite(id) ? id : undefined,
    data,
  };
}

export function streamConversationEvents(conversationId: string, options: StreamOptions): () => void {
  const url = new URL(`/api/conversations/${encodeURIComponent(conversationId)}/events`, window.location.origin);
  if (options.since !== undefined) {
    url.searchParams.set('since', String(options.since));
  }
  if (options.sessionId) {
    url.searchParams.set('session_id', options.sessionId);
  }
  if (options.finalOnly !== false) {
    url.searchParams.set('final_only', '1');
  }
  url.searchParams.set('timeout', '600');
  url.searchParams.set('intervalMs', '700');

  const source = new EventSource(url.toString());

  source.addEventListener('bootstrap', (event) => {
    const typed = coerceEvent('bootstrap', event as MessageEvent<string>);
    options.onBootstrap?.((typed.data ?? {}) as ConversationSseBootstrapPayload);
    options.onEvent?.(typed);
  });

  for (const eventName of STREAM_EVENTS.filter((value) => value !== 'bootstrap')) {
    source.addEventListener(eventName, (event) => {
      const typed = coerceEvent(eventName, event as MessageEvent<string>);
      options.onEvent?.(typed);
      if (eventName === 'stream_end') {
        options.onEnd?.(typed);
      }
    });
  }

  source.onerror = () => {
    options.onError?.('SSE 连接中断，前端将依赖状态轮询继续同步。');
  };

  return () => {
    source.close();
  };
}

export function isEventFrame(value: unknown): value is ConversationSseEventFrame {
  return !!value && typeof value === 'object' && typeof (value as ConversationSseEventFrame).type === 'string';
}
