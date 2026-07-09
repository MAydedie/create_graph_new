export interface ProjectStatusResponse {
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

export interface WorkbenchSessionStartResponse {
  sessionId: string;
  projectPath: string;
  status: string;
  phase: string;
  message: string;
  experienceOutputRoot?: string | null;
}

export interface WorkbenchSessionStatusResponse {
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

export interface WorkbenchBootstrapResponse extends Record<string, unknown> {}

export interface ProcessItem extends Record<string, unknown> {
  process_id?: string;
  entry?: string;
  entry_node_id?: string;
  partition_id?: string;
  description?: string;
  summary?: string;
  stepCount?: number;
  step_count?: number;
  communities?: string[];
}

export interface ProcessesResponse {
  processes: ProcessItem[];
  count: number;
  project_path: string;
  error?: string;
}

export interface CommunityItem extends Record<string, unknown> {
  community_id?: string;
  name?: string;
  label?: string;
  description?: string;
  summary?: string;
  partition_id?: string;
  methods?: string[];
  members?: string[];
  community_semantics?: Record<string, unknown>;
}

export interface CommunityShadowResponse extends Record<string, unknown> {
  communities?: CommunityItem[];
  stats?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  error?: string;
}

export interface PartitionSummary {
  partition_id: string;
  name: string;
  description?: string;
  methods?: string[];
  path_count?: number;
  selected_path_count?: number;
  rich_path_count?: number;
  available_path_count?: number;
  deferred_path_count?: number;
  selection_policy?: string;
  analysis_status?: string;
  entry_point_count?: number;
  shadow_entry_point_count?: number;
  process_count?: number;
  community_count?: number;
  has_cfg?: boolean;
  has_dfg?: boolean;
  has_io?: boolean;
  supports_process_shadow?: boolean;
  supports_community_shadow?: boolean;
  semantic_label?: string;
  functional_domain?: string;
  key_concepts?: string[];
  top_files?: string[];
  top_dependencies?: string[];
  community_summary_status?: string;
}

export interface ReadContractResponse {
  contract_version: string;
  project_path: string;
  capabilities?: Record<string, boolean>;
  adapters?: {
    partition_summaries?: PartitionSummary[];
  };
  shadow_results?: Record<string, unknown>;
  error?: string;
}

export interface ConversationPendingQuestionOption {
  id?: string;
  label: string;
  description?: string;
  promptFragment?: string;
}

export interface ConversationPendingQuestion {
  questionId: string;
  question: string;
  header?: string;
  options?: ConversationPendingQuestionOption[];
  multiple?: boolean;
  custom?: boolean;
  allowFreeform?: boolean;
  source?: string;
  projectPath?: string;
  reason?: string;
  round?: number;
  maxRounds?: number;
  clarityLevel?: string;
  inferredIntent?: string;
  structuredFields?: Array<Record<string, unknown>>;
  terminal?: boolean;
  originalQuery?: string;
  createdAt?: string;
}

export interface ConversationSessionStartResponse {
  sessionId: string;
  conversationId: string;
  projectPath: string;
  status: string;
  stage: string;
  message: string;
}

export interface ConversationSessionStatusResponse {
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
}

export interface ConversationRetrievalHighlight extends Record<string, unknown> {
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
}

export interface ConversationResultResponse {
  conversationId: string;
  intentGuess?: string;
  nextStep?: 'ask_clarification' | 'send_chat' | 'retrieval_answer' | 'start_multi_agent' | string;
  safeToCodegen?: boolean;
  mode?: string;
  confidence?: string;
  reason?: string;
  taskMode?: string | null;
  projectPath?: string;
  answer?: string;
  pendingQuestion?: ConversationPendingQuestion;
  retrieval?: {
    ok?: boolean;
    error?: string | null;
    highlights?: ConversationRetrievalHighlight[];
    validationCommands?: string[];
    validation_commands?: string[];
  };
  advisor?: Record<string, unknown>;
  team?: Record<string, unknown>;
  result_summary?: Record<string, unknown>;
  output_protocol?: Record<string, unknown>;
  evidence_verdict?: Record<string, unknown>;
  solution_packet?: Record<string, unknown>;
  generation?: Record<string, unknown>;
  opencode_kernel?: Record<string, unknown>;
  swarm_packet?: Record<string, unknown>;
  handoff?: Record<string, unknown>;
  memory?: Record<string, unknown>;
  compaction?: Record<string, unknown> | null;
}

export interface ConversationDetailResponse {
  conversationId: string;
  projectPath?: string;
  status?: string;
  messageCount?: number;
  partCount?: number;
  pendingQuestion?: ConversationPendingQuestion;
  summarySnapshot?: Record<string, unknown>;
  compactionCount?: number;
  keyFactsMemory?: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

export interface ConversationMessagesResponse {
  conversationId: string;
  messages: Array<Record<string, unknown>>;
  parts: Array<Record<string, unknown>>;
  pendingQuestion?: ConversationPendingQuestion;
  questionReplies?: Array<Record<string, unknown>>;
  compactionHistory?: Array<Record<string, unknown>>;
  keyFactsMemory?: Record<string, unknown>;
  updatedAt?: string;
}

export interface ConversationSummaryResponse {
  conversationId: string;
  summarySnapshot?: {
    summary?: string;
    messageCount?: number;
    pendingQuestion?: ConversationPendingQuestion;
    keyFacts?: Record<string, unknown>;
    compaction?: Record<string, unknown>;
    generatedAt?: string;
    strategy?: string;
  };
  updatedAt?: string;
}

export interface ConversationSseBootstrapPayload {
  conversationId: string;
  status?: string;
  pendingQuestion?: ConversationPendingQuestion | null;
  updatedAt?: string;
  cursor?: number;
}

export interface ConversationSseEventFrame {
  seq?: number;
  eventId?: string;
  type: string;
  payload?: Record<string, unknown>;
  createdAt?: string;
}

export interface ConversationSseEvent {
  event: string;
  id?: number;
  data: unknown;
}

export interface MultiAgentSessionStartResponse {
  sessionId: string;
  projectPath: string;
  status: string;
  stage: string;
  message: string;
  swarmEnabled?: boolean;
  advisorEnabled?: boolean;
  opencodeEnabled?: boolean;
  conversationId?: string;
  outputRoot?: string | null;
  autoApplyOutput?: boolean;
}

export interface MultiAgentSessionStatusResponse {
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
  opencode?: Record<string, unknown>;
  swarm?: {
    enabled?: boolean;
    llm_enabled?: boolean;
    model?: string;
    consensus?: Record<string, unknown>;
    agents?: Record<string, unknown>;
    updatedAt?: string;
  };
}

export interface MultiAgentResultResponse {
  intent_packet?: Record<string, unknown>;
  retrieval_bundle?: Record<string, unknown>;
  evidence_verdict?: Record<string, unknown>;
  advisor_packet?: Record<string, unknown>;
  solution_packet?: Record<string, unknown>;
  workbench?: Record<string, unknown>;
  output_protocol?: Record<string, unknown>;
  opencode_kernel?: Record<string, unknown>;
  swarm_packet?: Record<string, unknown>;
}

export type Loadable<T> =
  | { state: 'loading' }
  | { state: 'error'; message: string; status?: number }
  | { state: 'empty'; message: string; status?: number; data?: T }
  | { state: 'success'; data: T; status?: number };

export interface DashboardResources {
  status: Loadable<ProjectStatusResponse>;
  processes: Loadable<ProcessesResponse>;
  community: Loadable<CommunityShadowResponse>;
  readContract: Loadable<ReadContractResponse>;
}
