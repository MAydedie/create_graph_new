export interface CreateGraphNodeDetailSource {
  available: boolean;
  language?: string;
  file_path?: string;
  line_start?: number;
  line_end?: number;
  snippet?: string;
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
}

export interface CreateGraphRagAskRequest {
  query: string;
  top_k?: number;
  project_path?: string;
  selected_node?: Record<string, unknown>;
  partition_id?: string;
}

export interface CreateGraphRagAskResponse {
  query: string;
  answer: string;
  evidence?: Array<Record<string, unknown>>;
  partition?: Record<string, unknown> | null;
  search?: Record<string, unknown>;
  index_rebuild_status?: Record<string, unknown>;
}

export interface CreateGraphWorkbenchSessionStartRequest {
  project_path: string;
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
  error?: string;
  bootstrapReady: boolean;
  startedAt?: string;
  updatedAt?: string;
  completedAt?: string;
}

export interface CreateGraphWorkbenchBootstrapResponse {
  contractVersion: string;
  sessionId: string;
  projectPath: string;
  status: Record<string, unknown>;
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

/**
 * Create_graph extension APIs used after GitNexus shell cutover.
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

  askRag(baseApiUrl: string, payload: CreateGraphRagAskRequest): Promise<CreateGraphRagAskResponse> {
    return fetchJson<CreateGraphRagAskResponse>(`${baseApiUrl}/rag/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
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

  fetchWorkbenchSessionBootstrap(
    baseApiUrl: string,
    sessionId: string,
  ): Promise<CreateGraphWorkbenchBootstrapResponse> {
    const encodedSessionId = encodeURIComponent(sessionId);
    return fetchJson<CreateGraphWorkbenchBootstrapResponse>(`${baseApiUrl}/workbench/session/${encodedSessionId}/bootstrap`);
  },
};
