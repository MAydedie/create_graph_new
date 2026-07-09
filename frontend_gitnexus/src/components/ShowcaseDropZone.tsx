import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Brain,
  BookOpen,
  CheckCircle2,
  Clock3,
  FolderOpen,
  Link,
  Loader2,
  Plus,
  Terminal,
  ArrowUpRight,
  Bot,
  Cpu,
  FolderGit2,
  Sparkles,
  ChevronRight,
  Trash2,
  Settings2,
  RotateCcw,
  AlertTriangle,
  HelpCircle,
  Activity,
  Play,
  Check,
} from 'lucide-react';
import { useAppState } from '../hooks/useAppState';
import {
  createGraphExtensionsApi,
  type CreateGraphWorkbenchBootstrapResponse,
  type CreateGraphWorkbenchSessionLogEntry,
  type CreateGraphWorkbenchSessionStatusResponse,
} from '../services/create-graph-extensions';
import {
  connectToServer,
  deleteLearnedRepo,
  fetchRepos,
  normalizeServerUrl,
  type ConnectToServerResult,
  type RepoSummary,
} from '../services/server-connection';
import type { FileEntry } from '../services/zip';
import './showcase-dropzone.css';
import { MarkdownRenderer } from './MarkdownRenderer';
import { buildBackendConversationLLMConfig } from '../core/llm/settings-service';
import {
	BUILTIN_SE_TEAM,
	parseSlashCommand,
	SlashCommandMenu,
	type SlashCommandItem,
	type SlashCommandKind,
} from './SlashCommandMenu';

const EXPERIENCE_OUTPUT_ROOT_STORAGE_KEY = 'create-graph.experience-output-root';
const STATUS_POLL_INTERVAL_MS = 1200;
const PROGRESS_ANIMATION_INTERVAL_MS = 35;
const FALLBACK_COMMUNITY_COUNT = 8;

const THINK_BLOCK_PATTERN = /<think>[\s\S]*?<\/think>\s*/gi;

function sanitizeAssistantText(value: unknown): string {
  return String(value || '').replace(THINK_BLOCK_PATTERN, '').trim();
}

function sanitizeStageCardText(value: unknown): string {
  const text = sanitizeAssistantText(value);
  const lowered = text.toLowerCase();
  const blockedMarkers = [
    'the user wants me to act as',
    'required output structure',
    'input context',
    'let me think about this',
    'carefully parse the requirements',
    'cross-library comparison expert',
    'structured response',
  ];
  if (blockedMarkers.some((marker) => lowered.includes(marker))) {
    return '';
  }
  return text;
}

function buildLocalThinkingMessage(stage: unknown): string {
  const normalized = String(stage || '').trim();
  if (!normalized) return '正在检索并构思回复...';
  if (normalized === 'requirement_analysis') return '正在理解问题...';
  if (normalized === 'experience_retrieval') return '正在检索相关经验...';
  if (normalized === 'per_project_extraction') return '正在提取关键信息...';
  if (normalized === 'cross_project_comparison') return '正在整理对比结果...';
  if (normalized === 'qa_advisor') return '正在规划回答结构...';
  if (normalized === 'qa_evidence_reasoning') return '正在组织回答内容...';
  return '正在检索并构思回复...';
}

type LearningStatus = 'queued' | 'starting' | 'running' | 'completed' | 'failed';

interface DropZoneProps {
  onFileSelect: (file: File) => void;
  onGitClone?: (files: FileEntry[]) => void;
  onServerConnectStart?: (message?: string) => void;
  onServerConnect?: (result: ConnectToServerResult, serverUrl?: string) => void;
}

interface LearningTask {
  sessionId: string;
  projectPath: string;
  status: LearningStatus;
  phase: string;
  progress: number;
  message: string;
  queueAhead: number;
  queuePosition?: number | null;
  updatedAt?: string;
  opened?: boolean;
}

interface TerminalLog {
  seq: number;
  id: string;
  time: string;
  level: 'INFO' | 'SUCCESS' | 'WARN' | 'ERROR';
  source: string;
  message: string;
}

const TERMINAL_STATUSES = new Set(['completed', 'failed']);

const STEPS = [
  { step: 1, agent: "advisor_consultant", stage: "requirement_advisor", display: "需求顾问指导", type: "advisor", icon: "💡" },
  { step: 2, agent: "requirement_analysis", stage: "requirement_analysis", display: "需求分析", type: "standard", icon: "📋" },
  { step: 3, agent: "advisor_consultant", stage: "architecture_advisor", display: "架构顾问指导", type: "advisor", icon: "💡" },
  { step: 4, agent: "architecture_design", stage: "architecture_design", display: "架构设计", type: "standard", icon: "🏗️" },
  { step: 5, agent: "advisor_consultant", stage: "code_advisor", display: "代码顾问指导", type: "advisor", icon: "💡" },
  { step: 6, agent: "code_implementation", stage: "code_implementation", display: "代码实现", type: "standard", icon: "💻" },
  { step: 7, agent: "code_testing", stage: "code_testing", display: "代码测试", type: "standard", icon: "🧪" },
  { step: 8, agent: "requirement_validation", stage: "requirement_validation", display: "需求验证", type: "standard", icon: "✅" }
];

const SIMPLE_QA_STEPS = [
  { step: 1, agent: "requirement_analysis", stage: "requirement_analysis", display: "需求分析", type: "standard", icon: "📋" },
  { step: 2, agent: "experience_retrieval", stage: "experience_retrieval", display: "全局经验检索", type: "advisor", icon: "🗂️" },
  { step: 3, agent: "per_project_extraction", stage: "per_project_extraction", display: "逐经验库提取", type: "standard", icon: "🧩" },
  { step: 4, agent: "cross_project_comparison", stage: "cross_project_comparison", display: "跨经验库对比", type: "standard", icon: "⚖️" },
  { step: 5, agent: "qa_advisor", stage: "qa_advisor", display: "问答策略规划", type: "advisor", icon: "💡" },
  { step: 6, agent: "qa_reasoning", stage: "qa_evidence_reasoning", display: "寻找证据与构思回复", type: "standard", icon: "🔎" },
  { step: 7, agent: "qa_reply", stage: "qa_reply", display: "给出回复", type: "standard", icon: "✅" }
];

const ensureNextStageCard = <T extends { stage: string; display: string; type: 'advisor' | 'standard'; icon: string; status: 'running' | 'completed'; content: string; queryId?: string }>(
  stageCards: T[],
  steps: Array<{ stage: string; display: string; type: string; icon: string }>,
  currentStage: string,
  queryId: string | null,
): T[] => {
  if (!queryId) return stageCards;
  const currentIndex = steps.findIndex((step) => step.stage === currentStage);
  if (currentIndex < 0 || currentIndex >= steps.length - 1) {
    return stageCards;
  }
  const nextStep = steps[currentIndex + 1];
  const existingIndex = stageCards.findIndex((card) => card.stage === nextStep.stage && card.queryId === queryId);
  if (existingIndex >= 0) {
    const existingCard = stageCards[existingIndex];
    if (existingCard.status === 'completed') {
      return stageCards;
    }
    const nextCards = [...stageCards];
    nextCards[existingIndex] = {
      ...existingCard,
      display: nextStep.display,
      type: nextStep.type as 'advisor' | 'standard',
      icon: nextStep.icon,
      status: 'running' as const,
      queryId,
    } as T;
    return nextCards;
  }
  return [
    ...stageCards,
    {
      stage: nextStep.stage,
      display: nextStep.display,
      type: nextStep.type as 'advisor' | 'standard',
      icon: nextStep.icon,
      status: 'running' as const,
      content: '',
      queryId,
    } as T,
  ];
};

function normalizeStatus(input: string): LearningStatus {
  const value = String(input || '').toLowerCase();
  if (value === 'queued') return 'queued';
  if (value === 'starting') return 'starting';
  if (value === 'completed') return 'completed';
  if (value === 'failed') return 'failed';
  return 'running';
}

function toDisplayName(path: string): string {
  const normalized = String(path || '').replace(/\\/g, '/');
  const chunks = normalized.split('/').filter(Boolean);
  return chunks[chunks.length - 1] || path || 'unknown';
}

function toTerminalLog(entry: CreateGraphWorkbenchSessionLogEntry): TerminalLog {
  const rawLevel = String(entry.level || 'INFO').toUpperCase();
  const level: TerminalLog['level'] = rawLevel === 'SUCCESS' || rawLevel === 'WARN' || rawLevel === 'ERROR' ? rawLevel : 'INFO';
  return {
    seq: Math.max(0, Number(entry.seq || 0)),
    id: `${entry.seq}-${entry.timestamp}`,
    time: entry.time,
    level,
    source: entry.source || 'Workbench',
    message: entry.message || '',
  };
}

function mapTaskFromStatus(task: LearningTask, status: CreateGraphWorkbenchSessionStatusResponse): LearningTask {
  return {
    ...task,
    status: normalizeStatus(status.status),
    phase: String(status.phase || task.phase || ''),
    progress: Math.max(0, Math.min(100, Number(status.progress || 0))),
    message: String(status.message || task.message || ''),
    queueAhead: Math.max(0, Number(status.queueAhead || 0)),
    queuePosition: status.queuePosition,
    updatedAt: status.updatedAt || task.updatedAt,
  };
}

function summarizeRepo(repo: RepoSummary): string {
  if (repo.summary) return repo.summary;
  const files = Number(repo.stats?.files || 0);
  const nodes = Number(repo.stats?.nodes || 0);
  const edges = Number(repo.stats?.edges || 0);
  return `项目已沉淀 ${files} 个文件、${nodes} 个图谱节点、${edges} 条关系，支持深度问答与语义检索。`;
}

interface CommunityProgress {
  key: string;
  name: string;
  progress: number;
  status: 'completed' | 'current' | 'pending';
}

interface CommunityMeta {
  key: string;
  name: string;
  aliases: string[];
}

interface CommunityLogGroup {
  name: string;
  logs: TerminalLog[];
}

function normalizeToken(input: string): string {
  return String(input || '').trim().toLowerCase().replace(/\s+/g, '');
}

function toCommunityRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : null;
}

function extractCommunityMetas(bootstrap: CreateGraphWorkbenchBootstrapResponse | null): CommunityMeta[] {
  const payload = toCommunityRecord(bootstrap);
  const hierarchy = toCommunityRecord(payload?.hierarchy);
  const summaries = Array.isArray(hierarchy?.partitionSummaries) ? hierarchy?.partitionSummaries : [];

  const result: CommunityMeta[] = [];
  summaries.forEach((item, index) => {
    const record = toCommunityRecord(item);
    if (!record) return;
    const rawId = String(record.partition_id || record.partitionId || '').trim();
    const rawName = String(record.name || rawId || '').trim();
    const id = rawId || `community-${index + 1}`;
    const name = rawName || `社区${index + 1}`;
    result.push({
      key: id,
      name,
      aliases: [id, name, `社区${index + 1}`, `community${index + 1}`, `partition${index + 1}`],
    });
  });

  return result;
}

function buildFallbackCommunityMetas(count: number): CommunityMeta[] {
  const safeCount = Math.max(1, Math.min(32, Math.floor(count || 0)));
  return Array.from({ length: safeCount }, (_, index) => {
    const n = index + 1;
    return {
      key: `community-${n}`,
      name: `社区${n}`,
      aliases: [`社区${n}`, `community${n}`, `partition${n}`, `community-${n}`, `partition-${n}`],
    };
  });
}

function getVisibleCommunityMetas(bootstrap: CreateGraphWorkbenchBootstrapResponse | null): CommunityMeta[] {
  const metas = extractCommunityMetas(bootstrap);
  return metas;
}

function buildCommunityProgress(task: LearningTask, metas: CommunityMeta[], animatedProgress: Record<string, number>): CommunityProgress[] {
  return metas.map((meta) => {
    const progressKey = `${task.sessionId}::${meta.key}`;
    const currentProgress = Math.max(0, Math.min(100, Number(animatedProgress[progressKey] || 0)));
    const status: CommunityProgress['status'] = currentProgress >= 100 || task.status === 'completed'
      ? 'completed'
      : currentProgress > 0
        ? 'current'
        : 'pending';
    return {
      key: meta.key,
      name: meta.name,
      progress: currentProgress,
      status,
    };
  });
}

function matchCommunityIndex(log: TerminalLog, metas: CommunityMeta[]): number | null {
  const rawText = `${log.source} ${log.message}`;
  const normalized = normalizeToken(rawText);
  const byNumber = rawText.match(/(?:社区|community|partition|分区)\s*[-_#:：]?\s*(\d{1,2})/i);
  if (byNumber) {
    const index = Number(byNumber[1]) - 1;
    if (index >= 0 && index < metas.length) return index;
  }
  for (let index = 0; index < metas.length; index += 1) {
    const aliases = metas[index].aliases || [];
    const matched = aliases.some((alias) => {
      const token = normalizeToken(alias);
      return token.length > 0 && normalized.includes(token);
    });
    if (matched) return index;
  }
  return null;
}

function buildCommunityLogGroups(logs: TerminalLog[], metas: CommunityMeta[]): CommunityLogGroup[] {
  const groups: CommunityLogGroup[] = metas.map((meta) => ({
    name: meta.name,
    logs: [],
  }));
  const globalLogs: TerminalLog[] = [];
  const shadowLogs: TerminalLog[] = [];

  logs.forEach((log) => {
    const logText = `${log.source} ${log.message}`;
    if (logText.includes('影子归档')) {
      shadowLogs.push(log);
      return;
    }
    const index = matchCommunityIndex(log, metas);
    if (index === null) {
      globalLogs.push(log);
    } else {
      groups[index].logs.push(log);
    }
  });

  if (globalLogs.length > 0) {
    groups.unshift({ name: '全局流水', logs: globalLogs });
  }
  if (shadowLogs.length > 0) {
    groups.push({ name: '影子归档', logs: shadowLogs });
  }
  return groups;
}

function getCurrentCommunityIndex(task: LearningTask, metas: CommunityMeta[], animatedProgress: Record<string, number>): number {
  let currentIndex = -1;
  metas.forEach((meta, index) => {
    const key = `${task.sessionId}::${meta.key}`;
    const progress = Math.max(0, Math.min(100, Math.round(animatedProgress[key] || 0)));
    if (progress > 0) {
      currentIndex = index;
    }
  });
  return currentIndex;
}

export const ShowcaseDropZone = ({
  onFileSelect: _onFileSelect,
  onGitClone: _onGitClone,
  onServerConnectStart,
  onServerConnect,
}: DropZoneProps) => {
  const { setSettingsPanelOpen } = useAppState();
  const [pageMode, setPageMode] = useState<'home' | 'learn' | 'skills'>('home');
  const [localProjectPath, setLocalProjectPath] = useState('');
  const [experienceOutputRoot, setExperienceOutputRoot] = useState(() => localStorage.getItem(EXPERIENCE_OUTPUT_ROOT_STORAGE_KEY) || '');
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<LearningTask[]>([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [sessionLogs, setSessionLogs] = useState<Record<string, TerminalLog[]>>({});
  const [sessionBootstraps, setSessionBootstraps] = useState<Record<string, CreateGraphWorkbenchBootstrapResponse | null>>({});
  const [animatedProgress, setAnimatedProgress] = useState<Record<string, number>>({});
  const [historicalRepos, setHistoricalRepos] = useState<RepoSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [openingRepoIdentity, setOpeningRepoIdentity] = useState<string | null>(null);
  const [deletingRepoIdentity, setDeletingRepoIdentity] = useState<string | null>(null);
  const [uptime, setUptime] = useState('00:00:00');

  // Chat panel (placeholder for right-side DeepSeek-style chat)
  // 历史对话仅在当前页面生命周期内保留：新打开页面 = 空会话
  const [chatMode, setChatMode] = useState<'local' | 'se-team'>('local');
  const [localChatMessages, setLocalChatMessages] = useState<Array<{ role: 'user' | 'assistant' | 'system' | 'stage'; content: string; stage?: string; thinkingContent?: string; isThinking?: boolean; thinkingCollapsed?: boolean }>>([]);

  const [seTeamChatMessages, setSeTeamChatMessages] = useState<Array<{ role: 'user' | 'assistant' | 'system' | 'stage'; content: string; stage?: string; queryId?: string }>>([]);

  const toggleThinking = useCallback((messageIndex: number) => {
    setLocalChatMessages((prev) =>
      prev.map((msg, i) =>
        i === messageIndex ? { ...msg, thinkingCollapsed: !msg.thinkingCollapsed } : msg
      )
    );
  }, []);

  const chatMessages = chatMode === 'local' ? localChatMessages : seTeamChatMessages;
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const chatTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  // /skill 和 /models 反斜框状态
  const [slashState, setSlashState] = useState<{
    kind: SlashCommandKind;
    query: string;
    start: number;
    end: number;
  } | null>(null);
  const handleSlashClose = useCallback(() => setSlashState(null), []);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [seTeamSessionId, setSeTeamSessionId] = useState<string | null>(null);
  const [seTeamBackendPending, setSeTeamBackendPending] = useState(false);
  const [seTeamTaskExplorationByQuery, setSeTeamTaskExplorationByQuery] = useState<Record<string, {
    status: string;
    phase: string;
    message: string;
    waitSeconds?: number;
    elapsedMs?: number;
    sessionId?: string;
    model?: string;
    agent?: string;
  }>>({});
  const [seTeamOutputWriteByQuery, setSeTeamOutputWriteByQuery] = useState<Record<string, {
    outputRoot: string;
    materializationMode: string;
    generatedProjectRoot: string;
    writtenCount: number;
    failedCount: number;
    modifiedFiles: Array<Record<string, unknown>>;
    diffBlocks: Array<Record<string, unknown>>;
  }>>({});

  // SE-Team advanced state variables
  const [personaSkillPath, setPersonaSkillPath] = useState('D:/代码仓库生图/借鉴项目/huangqing-perspective');
  const [personaSkillStatus, setPersonaSkillStatus] = useState('当前未启用 Skill');
  const [importingSkill, setImportingSkill] = useState(false);
  const [deactivatingSkill, setDeactivatingSkill] = useState(false);
  const [learningPersonaPanelOpen, setLearningPersonaPanelOpen] = useState(false);
  const [personaSkillItems, setPersonaSkillItems] = useState<any[]>([]);
  const [activePersonaSkill, setActivePersonaSkill] = useState<any | null>(null);
  const [seTeamTab, setSeTeamTab] = useState<'chat' | 'progress' | 'experiences'>('chat');
  const [activeStepsConfig, setActiveStepsConfig] = useState<any[]>(() => {
    try {
      const saved = localStorage.getItem('gitnexus_showcase_seteam_active_steps_config');
      return saved ? JSON.parse(saved) : STEPS;
    } catch {
      return STEPS;
    }
  });
  const [seTeamStepStatus, setSeTeamStepStatus] = useState<Record<string, 'pending' | 'running' | 'completed'>>(() => {
    try {
      const saved = localStorage.getItem('gitnexus_showcase_seteam_step_status');
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });
  const [matchedExperiences, setMatchedExperiences] = useState<any[]>(() => {
    try {
      const saved = localStorage.getItem('gitnexus_showcase_seteam_matched_experiences');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [suspendedQuestions, setSuspendedQuestions] = useState<string[]>([]);
  const [clarificationAnswers, setClarificationAnswers] = useState<string[]>([]);
  const [workflowCompleted, setWorkflowCompleted] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('gitnexus_showcase_seteam_workflow_completed');
      return saved ? JSON.parse(saved) === true : false;
    } catch {
      return false;
    }
  });
  const [rollbacks, setRollbacks] = useState<Array<{ from: number; to: number; reason: string }>>(() => {
    try {
      const saved = localStorage.getItem('gitnexus_showcase_seteam_rollbacks');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [expandedExps, setExpandedExps] = useState<Record<string, boolean>>({});
  const toggleExpCollapse = useCallback((expId: string) => {
    setExpandedExps((prev) => ({ ...prev, [expId]: !prev[expId] }));
  }, []);
  const [seTeamStageCards, setSeTeamStageCards] = useState<Array<{
    stage: string;
    display: string;
    type: 'advisor' | 'standard';
    icon: string;
    status: 'running' | 'completed';
    content: string;
    artifactFiles?: string[];
    experiences?: any[];
    queryId?: string;
  }>>(() => {
    try {
      const saved = localStorage.getItem('gitnexus_showcase_seteam_stage_cards');
      if (saved) {
        const parsed = JSON.parse(saved);
        return parsed.map((c: any) => {
          if (!c.queryId) {
            c.queryId = 'legacy';
          }
          return c;
        });
      }
      return [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    localStorage.setItem('gitnexus_showcase_seteam_active_steps_config', JSON.stringify(activeStepsConfig));
  }, [activeStepsConfig]);

  useEffect(() => {
    localStorage.setItem('gitnexus_showcase_seteam_step_status', JSON.stringify(seTeamStepStatus));
  }, [seTeamStepStatus]);

  useEffect(() => {
    localStorage.setItem('gitnexus_showcase_seteam_matched_experiences', JSON.stringify(matchedExperiences));
  }, [matchedExperiences]);

  useEffect(() => {
    localStorage.setItem('gitnexus_showcase_seteam_workflow_completed', JSON.stringify(workflowCompleted));
  }, [workflowCompleted]);

  useEffect(() => {
    localStorage.setItem('gitnexus_showcase_seteam_rollbacks', JSON.stringify(rollbacks));
  }, [rollbacks]);

  useEffect(() => {
    localStorage.setItem('gitnexus_showcase_seteam_stage_cards', JSON.stringify(seTeamStageCards));
  }, [seTeamStageCards]);

  const refreshPersonaSkillStatus = useCallback(async () => {
    try {
      const [listResp, activeResp] = await Promise.all([
        fetch('/api/skills/persona/list'),
        fetch('/api/skills/persona/active'),
      ]);
      if (listResp.ok) {
        const items = await listResp.json().catch(() => []);
        setPersonaSkillItems(items);
      }
      if (activeResp.ok) {
        const active = await activeResp.json().catch(() => ({}));
        setActivePersonaSkill(active.persona || null);
        const personaName = active.persona?.name || active.persona?.personaId || '';
        if (personaName) {
          setPersonaSkillStatus(`当前已启用 Skill：${personaName}`);
        } else {
          setPersonaSkillStatus('当前未启用 Skill');
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const handleImportSkill = useCallback(async () => {
    if (!personaSkillPath.trim()) {
      setPersonaSkillStatus('请先输入 skill 绝对路径');
      return;
    }
    setImportingSkill(true);
    setPersonaSkillStatus('正在导入 skill ...');
    try {
      const importResp = await fetch('/api/skills/persona/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_path: personaSkillPath.trim() }),
      });
      const importPayload = await importResp.json().catch(() => ({}));
      if (!importResp.ok) {
        throw new Error(importPayload.error || `导入失败（${importResp.status}）`);
      }

      const personaName = importPayload?.persona?.name || importPayload?.persona?.personaId || 'skill';
      setPersonaSkillStatus(`导入成功：${personaName}。如需启用，请在聊天框输入 / 选择`);
      await refreshPersonaSkillStatus();
    } catch (error) {
      setPersonaSkillStatus(`导入失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setImportingSkill(false);
    }
  }, [personaSkillPath, refreshPersonaSkillStatus]);

  const handleRemoveSkill = useCallback(async () => {
    setDeactivatingSkill(true);
    setPersonaSkillStatus('正在去除 skill ...');
    try {
      const resp = await fetch('/api/skills/persona/deactivate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(payload.error || `去除失败（${resp.status}）`);
      }
      setPersonaSkillStatus('已清除所有激活，后续回复将使用默认普通问答视角');
      setChatMode('local');
      await refreshPersonaSkillStatus();
    } catch (error) {
      setPersonaSkillStatus(`去除失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setDeactivatingSkill(false);
    }
  }, [refreshPersonaSkillStatus]);

  const handleActivatePersonaSkill = useCallback(async (personaId: string) => {
    setImportingSkill(true);
    setPersonaSkillStatus('正在激活 skill ...');
    try {
      const resp = await fetch('/api/skills/persona/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona_id: personaId }),
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(payload.error || `激活失败（${resp.status}）`);
      }
      setPersonaSkillStatus(`激活成功：${payload?.persona?.name || personaId}`);
      setChatMode('local');
      await refreshPersonaSkillStatus();
    } catch (error) {
      setPersonaSkillStatus(`激活失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setImportingSkill(false);
    }
  }, [refreshPersonaSkillStatus]);

  const handleActivateSETeamSkill = useCallback(async () => {
    setDeactivatingSkill(true);
    setPersonaSkillStatus('正在激活 SE-Team 增强工作流...');
    try {
      // Deactivate any active persona skill on the backend so they are mutually exclusive
      const resp = await fetch('/api/skills/persona/deactivate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      await resp.json().catch(() => ({}));

      setChatMode('se-team');
      setPersonaSkillStatus('已成功激活并切换至 SE-Team 智能体工作流增强模式');
      await refreshPersonaSkillStatus();
    } catch (error) {
      setPersonaSkillStatus(`启用失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setDeactivatingSkill(false);
    }
  }, [refreshPersonaSkillStatus]);

  const handleSlashSelect = useCallback(
    (kind: SlashCommandKind, item: SlashCommandItem) => {
      if (!slashState) return;
      // 把整段 `/xxx` 从 textarea 中剥掉，**不在对话框中残留 `/...` 前缀**；
      // 只把光标之后用户真正输入的问题文本保留下来。
      const newText =
        chatInput.slice(0, slashState.start) + chatInput.slice(slashState.end);
      setChatInput(newText);
      setSlashState(null);
      requestAnimationFrame(() => {
        const ta = chatTextareaRef.current;
        if (ta) {
          ta.focus();
          ta.setSelectionRange(slashState.start, slashState.start);
        }
      });

      // 反斜框选择后：真正触发与"点击 skill 关键"相同的激活效果
      // - persona skill：调用 /api/skills/persona/activate，并刷新状态
      // - 内置 se-team：先清掉现有 persona，再切到 SE-Team 模式
      if (item.id === BUILTIN_SE_TEAM.id) {
        void handleActivateSETeamSkill();
      } else {
        void handleActivatePersonaSkill(item.id);
      }
    },
    [slashState, chatInput, handleActivatePersonaSkill, handleActivateSETeamSkill]
  );

  const handleDeletePersonaSkill = useCallback(async (personaId: string) => {
    const confirmed = window.confirm(`确定要删除 ${personaId} 这个 skill 吗？`);
    if (!confirmed) return;
    setDeactivatingSkill(true);
    setPersonaSkillStatus('正在删除 skill ...');
    try {
      const resp = await fetch(`/api/skills/persona/${personaId}`, {
        method: 'DELETE',
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(payload.error || `删除失败（${resp.status}）`);
      }
      setPersonaSkillStatus(`删除成功：${personaId}`);
      await refreshPersonaSkillStatus();
    } catch (error) {
      setPersonaSkillStatus(`删除失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setDeactivatingSkill(false);
    }
  }, [refreshPersonaSkillStatus]);

  useEffect(() => {
    if (chatMode === 'se-team' || pageMode === 'skills') {
      void refreshPersonaSkillStatus();
    }
  }, [chatMode, pageMode, refreshPersonaSkillStatus]);

  const projectPathInputRef = useRef<HTMLInputElement>(null);
  const tasksRef = useRef<LearningTask[]>([]);
  const activeSessionRef = useRef('');
  const logCursorRef = useRef<Record<string, number>>({});
  const bootstrapLoadingRef = useRef<Record<string, boolean>>({});
  const startTimeRef = useRef(Date.now());
  const scheduledOpenRef = useRef<Set<string>>(new Set());
  const chatAbortRef = useRef<AbortController | null>(null);
  const currentQueryIdRef = useRef<string>('');
  const seTeamBackendPendingRef = useRef(false);

  useEffect(() => {
    if (seTeamChatMessages && seTeamChatMessages.length > 0) {
      const lastUserMsg = [...seTeamChatMessages].reverse().find((m) => m.role === 'user');
      if (lastUserMsg && lastUserMsg.queryId) {
        currentQueryIdRef.current = lastUserMsg.queryId;
      }
    }
  }, [seTeamChatMessages]);

  useEffect(() => {
    seTeamBackendPendingRef.current = seTeamBackendPending;
  }, [seTeamBackendPending]);

  const updateSeTeamTaskExploration = useCallback((queryId: string, payload: any) => {
    if (!queryId || !payload || typeof payload !== 'object') return;
    setSeTeamTaskExplorationByQuery((prev) => ({
      ...prev,
      [queryId]: {
        status: typeof payload.status === 'string' ? payload.status : 'pending',
        phase: typeof payload.phase === 'string' ? payload.phase : 'queued',
        message: typeof payload.message === 'string' ? payload.message : '等待 OpenCode 返回',
        waitSeconds: typeof payload.waitSeconds === 'number' ? payload.waitSeconds : undefined,
        elapsedMs: typeof payload.elapsedMs === 'number' ? payload.elapsedMs : undefined,
        sessionId: typeof payload.sessionId === 'string' ? payload.sessionId : undefined,
        model: typeof payload.model === 'string' ? payload.model : undefined,
        agent: typeof payload.agent === 'string' ? payload.agent : undefined,
      },
    }));
  }, []);

  const updateSeTeamOutputWrite = useCallback((queryId: string, payload: any) => {
    if (!queryId || !payload || typeof payload !== 'object') return;
    setSeTeamOutputWriteByQuery((prev) => ({
      ...prev,
      [queryId]: {
        outputRoot: typeof payload.outputRoot === 'string' ? payload.outputRoot : '',
        materializationMode: typeof payload.materializationMode === 'string' ? payload.materializationMode : 'in_place',
        generatedProjectRoot: typeof payload.generatedProjectRoot === 'string' ? payload.generatedProjectRoot : '',
        writtenCount: typeof payload.writtenCount === 'number' ? payload.writtenCount : 0,
        failedCount: typeof payload.failedCount === 'number' ? payload.failedCount : 0,
        modifiedFiles: Array.isArray(payload.modifiedFiles) ? payload.modifiedFiles.filter((item: unknown) => item && typeof item === 'object') as Array<Record<string, unknown>> : [],
        diffBlocks: Array.isArray(payload.diffBlocks) ? payload.diffBlocks.filter((item: unknown) => item && typeof item === 'object') as Array<Record<string, unknown>> : [],
      },
    }));
  }, []);

  useEffect(() => {
    if (!seTeamSessionId || !seTeamBackendPending) {
      return;
    }
    let cancelled = false;
    const pollStatus = async () => {
      try {
        const response = await fetch(`/api/session/${encodeURIComponent(seTeamSessionId)}`);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || cancelled || !payload || typeof payload !== 'object') {
          return;
        }
        const queryId = currentQueryIdRef.current;
        if (queryId) {
          updateSeTeamTaskExploration(queryId, (payload as any).task_exploration);
          updateSeTeamOutputWrite(queryId, (payload as any).output_write);
        }
        const status = typeof (payload as any).status === 'string' ? (payload as any).status : 'running';
        if (status === 'completed') {
          setWorkflowCompleted(true);
          setSeTeamBackendPending(false);
          setChatLoading(false);
        } else if (status === 'failed') {
          setChatError(typeof (payload as any).error === 'string' ? (payload as any).error : 'SE-Team 执行失败');
          setSeTeamBackendPending(false);
          setChatLoading(false);
        }
      } catch {
        return;
      }
    };
    void pollStatus();
    const intervalId = window.setInterval(() => {
      void pollStatus();
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [seTeamBackendPending, seTeamSessionId, updateSeTeamOutputWrite, updateSeTeamTaskExploration]);

  useEffect(() => {
    const timer = setInterval(() => {
      const diff = Math.floor((Date.now() - startTimeRef.current) / 1000);
      const h = Math.floor(diff / 3600).toString().padStart(2, '0');
      const m = Math.floor((diff % 3600) / 60).toString().padStart(2, '0');
      const s = (diff % 60).toString().padStart(2, '0');
      setUptime(`${h}:${m}:${s}`);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const stopChatStream = useCallback(() => {
    try {
      chatAbortRef.current?.abort();
    } catch (_e) {
      // ignore
    }
    chatAbortRef.current = null;
  }, []);

  const handleSendChat = useCallback(async () => {
    const normalizeText = (value: any): string => {
      if (value === null || value === undefined) return '';
      if (typeof value === 'string') return value.trim();
      if (Array.isArray(value)) return value.map((v) => normalizeText(v)).filter(Boolean).join('\n');
      if (typeof value === 'object') {
        if (typeof (value as any).content === 'string') return (value as any).content.trim();
        if (typeof (value as any).answer === 'string') return (value as any).answer.trim();
        if (typeof (value as any).message === 'string') return (value as any).message.trim();
        if (typeof (value as any).text === 'string') return (value as any).text.trim();
        if (typeof (value as any).stage === 'string') return (value as any).stage.trim();
        try {
          return JSON.stringify(value);
        } catch (_e) {
          return String(value);
        }
      }
      return String(value);
    };

    if (!chatInput.trim()) return;
    const message = chatInput.trim();
    setChatLoading(true);
    setChatError(null);
    setChatInput('');
    setSlashState(null);
    stopChatStream();
    if (chatMode === 'se-team') {
      const qId = Date.now().toString();
      currentQueryIdRef.current = qId;
      setSeTeamChatMessages((prev) => [...prev, { role: 'user', content: message, queryId: qId }]);
      setSeTeamTaskExplorationByQuery((prev) => {
        const next = { ...prev };
        delete next[qId];
        return next;
      });
      setSeTeamOutputWriteByQuery((prev) => {
        const next = { ...prev };
        delete next[qId];
        return next;
      });
    } else {
      setLocalChatMessages((prev) => [...prev, { role: 'user', content: message }]);
    }

    try {
      if (chatMode === 'se-team') {
        // Reset SE-Team states for new query
        setRollbacks([]);
        setWorkflowCompleted(false);
        setSuspendedQuestions([]);

        const controller = new AbortController();
        chatAbortRef.current = controller;
        const response = await fetch('/api/session/start-stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            requirement: message,
            session_id: seTeamSessionId || undefined,
            session_mode: localProjectPath.trim() ? 'single_project' : 'global',
            project_path: localProjectPath.trim() || undefined,
            // 用户在前端 Settings 里配的 key/base_url/model 一并传给后端，
            // 否则 SE-Team 会回退到环境变量默认值。
            llm_config: buildBackendConversationLLMConfig() || undefined,
          }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          throw new Error('SE-Team 流式响应失败');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split(/\n\n/);
          buffer = blocks.pop() || '';
          for (const block of blocks) {
            if (!block.trim()) continue;
            let event = 'message';
            let dataText = '';
            block.split(/\n/).forEach((line) => {
              if (line.startsWith('event:')) event = line.slice(6).trim();
              else if (line.startsWith('data:')) dataText += `${line.slice(5).trimStart()}\n`;
            });
            if (!dataText.trim()) continue;
            let parsed: any = dataText.trim();
            try { parsed = JSON.parse(dataText); } catch (_e) { /* text fallback */ }
            if (parsed?.session_id && !seTeamSessionId) setSeTeamSessionId(String(parsed.session_id));

            const sseEvent = { ...parsed, type: parsed.type || parsed.event || event, event: parsed.event || parsed.type || event };
            const eventType = sseEvent.type || sseEvent.event;

            if (eventType === 'route_decision') {
              const isSimpleQa = Number(sseEvent.route_code) === 2 || sseEvent.mode === 'simple_qa';
              setSeTeamBackendPending(!isSimpleQa);
              const steps = isSimpleQa ? SIMPLE_QA_STEPS : STEPS;
              setActiveStepsConfig(steps);
              const initialStatuses: Record<string, 'pending' | 'running' | 'completed'> = {};
              steps.forEach((s) => {
                initialStatuses[s.stage] = 'pending';
              });
              setSeTeamStepStatus(initialStatuses);
            } else if (eventType === 'workflow_start') {
              const isSimpleQa = sseEvent.mode === 'simple_qa';
              setSeTeamBackendPending(!isSimpleQa);
              const steps = isSimpleQa ? SIMPLE_QA_STEPS : STEPS;
              setActiveStepsConfig(steps);
              const initialStatuses: Record<string, 'pending' | 'running' | 'completed'> = {};
              steps.forEach((s) => {
                initialStatuses[s.stage] = 'pending';
              });
              setSeTeamStepStatus(initialStatuses);
              setWorkflowCompleted(false);
            } else if (eventType === 'stage_start') {
              const stepInfo = (sseEvent.mode === 'simple_qa' ? SIMPLE_QA_STEPS : STEPS).find((s) => s.stage === sseEvent.stage) || {
                step: Number(sseEvent.step) || 0,
                stage: sseEvent.stage,
                display: sseEvent.display_name || sseEvent.stage || '阶段',
                type: sseEvent.agent_type === 'advisor' ? 'advisor' : 'standard',
                icon: sseEvent.icon || '🧩',
              };
              setSeTeamStepStatus((prev) => ({ ...prev, [sseEvent.stage]: 'running' }));
              setSeTeamStageCards((prev) => {
                const idx = prev.findIndex((c) => c.stage === sseEvent.stage && c.queryId === currentQueryIdRef.current);
                if (idx >= 0) {
                  const next = [...prev];
                  next[idx] = {
                    stage: sseEvent.stage,
                    display: stepInfo.display,
                    type: stepInfo.type as 'advisor' | 'standard',
                    icon: stepInfo.icon,
                    status: 'running',
                    content: '',
                    queryId: currentQueryIdRef.current,
                  };
                  return next;
                } else {
                  return [
                    ...prev,
                    {
                      stage: sseEvent.stage,
                      display: stepInfo.display,
                      type: stepInfo.type as 'advisor' | 'standard',
                      icon: stepInfo.icon,
                      status: 'running',
                      content: '',
                      queryId: currentQueryIdRef.current,
                    },
                  ];
                }
              });
            } else if (eventType === 'experience_matched') {
              const exps = sseEvent.experiences || [];
              setMatchedExperiences(exps);
              if (sseEvent.stage) {
                setSeTeamStageCards((prev) =>
                  prev.map((c) => (c.stage === sseEvent.stage && c.queryId === currentQueryIdRef.current ? { ...c, experiences: exps } : c))
                );
              }
            } else if (eventType === 'stream_chunk' || event === 'stream_chunk') {
              if (sseEvent.stage) {
                const cleanedContent = sanitizeStageCardText(sseEvent.content);
                if (!cleanedContent) {
                  continue;
                }
                setSeTeamStageCards((prev) =>
                  prev.map((c) => (c.stage === sseEvent.stage && c.queryId === currentQueryIdRef.current ? { ...c, content: (c.content || '') + cleanedContent } : c))
                );
              }
            } else if (eventType === 'task_exploration') {
              updateSeTeamTaskExploration(currentQueryIdRef.current, sseEvent.task_exploration);
            } else if (eventType === 'output_write') {
              updateSeTeamOutputWrite(currentQueryIdRef.current, sseEvent.output_write);
            } else if (eventType === 'stage_complete') {
              setSeTeamStepStatus((prev) => ({ ...prev, [sseEvent.stage]: 'completed' }));
              setSeTeamStageCards((prev) => {
                const updated = prev.map((c) => (c.stage === sseEvent.stage && c.queryId === currentQueryIdRef.current ? { ...c, status: 'completed' as const, content: typeof sseEvent.output === 'string' ? sseEvent.output : c.content, artifactFiles: sseEvent.artifact_files || sseEvent.artifact_paths || [] } : c));
                return ensureNextStageCard(updated, activeStepsConfig, String(sseEvent.stage || ''), currentQueryIdRef.current);
              });
            } else if (eventType === 'stage_suspended' || sseEvent.event === 'stage_suspended' || sseEvent.event === 'workflow_suspend') {
              const stage = sseEvent.stage || 'clarification';
              setSeTeamStepStatus((prev) => ({ ...prev, [stage]: 'completed' }));
              setSuspendedQuestions(sseEvent.questions || []);
              setClarificationAnswers(new Array((sseEvent.questions || []).length).fill(''));
              setChatLoading(false);
            } else if (eventType === 'rollback') {
              setRollbacks((prev) => [...prev, { from: sseEvent.from_step, to: sseEvent.to_step, reason: sseEvent.reason }]);
            } else if (eventType === 'workflow_complete') {
              setWorkflowCompleted(true);
              setSeTeamBackendPending(false);
            } else if (eventType === 'workflow_error' || eventType === 'stage_error' || eventType === 'error') {
              setChatError(sseEvent.reason || sseEvent.error || sseEvent.message || 'SE-Team 执行失败');
              setSeTeamBackendPending(false);
            }
          }
        }
      } else {
        const controller = new AbortController();
        chatAbortRef.current = controller;
        const response = await fetch('/api/session/start-stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            requirement: message,
            session_mode: localProjectPath ? 'single_project' : 'global',
            project_path: localProjectPath || '',
            mode: 'simple_qa',
            // local 模式也走 SE-Team 后端，依然需要带用户配置
            llm_config: buildBackendConversationLLMConfig() || undefined,
          }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          throw new Error('流式问答响应失败');
        }
        setLocalChatMessages((prev) => [...prev, { role: 'assistant', content: '', thinkingContent: '', isThinking: true, thinkingCollapsed: false }]);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split(/\n\n/);
          buffer = blocks.pop() || '';
          for (const block of blocks) {
            if (!block.trim()) continue;
            let event = 'message';
            let dataText = '';
            block.split(/\n/).forEach((line) => {
              if (line.startsWith('event:')) event = line.slice(6).trim();
              else if (line.startsWith('data:')) dataText += `${line.slice(5).trimStart()}\n`;
            });
            if (!dataText.trim()) continue;
            let parsed: any = dataText.trim();
            try { parsed = JSON.parse(dataText); } catch (_e) { /* text fallback */ }
            const sseEvent = { ...parsed, type: parsed.type || parsed.event || event, event: parsed.event || parsed.type || event };
            const eventType = sseEvent.type || sseEvent.event;
            if (eventType === 'stream_chunk') {
              if (sseEvent.stage === 'qa_reply') {
                if (sseEvent.content) {
                  const cleanedContent = sanitizeAssistantText(sseEvent.content);
                  if (!cleanedContent) {
                    continue;
                  }
                  setLocalChatMessages((prev) => {
                    const copy = [...prev];
                    const lastIdx = copy.length - 1;
                    if (lastIdx >= 0 && copy[lastIdx].role === 'assistant') {
                      copy[lastIdx] = {
                        ...copy[lastIdx],
                        content: (copy[lastIdx].content || '') + cleanedContent,
                        isThinking: false,
                        thinkingCollapsed: true,
                      };
                    }
                    return copy;
                  });
                }
              } else {
                const thinkingMessage = buildLocalThinkingMessage(sseEvent.stage);
                setLocalChatMessages((prev) => {
                  const copy = [...prev];
                  const lastIdx = copy.length - 1;
                  if (lastIdx >= 0 && copy[lastIdx].role === 'assistant') {
                    copy[lastIdx] = {
                      ...copy[lastIdx],
                      thinkingContent: thinkingMessage,
                    };
                  }
                  return copy;
                });
              }
            } else if (eventType === 'simple_qa_answer') {
              const cleanedContent = sanitizeAssistantText(sseEvent.content);
              if (cleanedContent) {
                setLocalChatMessages((prev) => {
                  const copy = [...prev];
                  const lastIdx = copy.length - 1;
                  if (lastIdx >= 0 && copy[lastIdx].role === 'assistant') {
                    copy[lastIdx] = {
                      ...copy[lastIdx],
                      content: cleanedContent,
                      thinkingContent: '',
                      isThinking: false,
                      thinkingCollapsed: true,
                    };
                  }
                  return copy;
                });
              }
            } else if (eventType === 'workflow_complete') {
              setLocalChatMessages((prev) => {
                const copy = [...prev];
                const lastIdx = copy.length - 1;
                if (lastIdx >= 0 && copy[lastIdx].role === 'assistant') {
                  copy[lastIdx] = {
                    ...copy[lastIdx],
                    isThinking: false,
                    thinkingCollapsed: true,
                  };
                }
                return copy;
              });
            }
          }
        }
      }
    } catch (err) {
      setChatError(err instanceof Error ? err.message : '发送失败');
    } finally {
      setChatLoading(seTeamBackendPendingRef.current);
      stopChatStream();
    }
  }, [activeStepsConfig, chatInput, chatMode, localProjectPath, seTeamSessionId, stopChatStream, updateSeTeamOutputWrite, updateSeTeamTaskExploration]);

  const handleResumeClarification = useCallback(async () => {
    if (!seTeamSessionId || chatLoading) return;
    const answers = [...clarificationAnswers];
    if (answers.some((ans) => !ans.trim())) {
      setChatError('请填写所有问题的回答');
      return;
    }

    setSuspendedQuestions([]);
    setChatLoading(true);
    setChatError(null);
    stopChatStream();

    try {
      const controller = new AbortController();
      chatAbortRef.current = controller;
      const response = await fetch('/api/session/resume-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: seTeamSessionId,
          answers: answers,
        }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error('SE-Team 流式恢复失败');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\n\n/);
        buffer = blocks.pop() || '';
        for (const block of blocks) {
          if (!block.trim()) continue;
          let event = 'message';
          let dataText = '';
          block.split(/\n/).forEach((line) => {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) dataText += `${line.slice(5).trimStart()}\n`;
          });
          if (!dataText.trim()) continue;
          let parsed: any = dataText.trim();
          try { parsed = JSON.parse(dataText); } catch (_e) { }

          const sseEvent = { ...parsed, type: parsed.type || parsed.event || event, event: parsed.event || parsed.type || event };
          const eventType = sseEvent.type || sseEvent.event;

          if (eventType === 'route_decision') {
            const isSimpleQa = Number(sseEvent.route_code) === 2 || sseEvent.mode === 'simple_qa';
            setSeTeamBackendPending(!isSimpleQa);
          } else if (eventType === 'workflow_start') {
            const isSimpleQa = sseEvent.mode === 'simple_qa';
            setSeTeamBackendPending(!isSimpleQa);
          } else if (eventType === 'experience_matched') {
            const exps = sseEvent.experiences || [];
            setMatchedExperiences(exps);
            if (sseEvent.stage) {
              setSeTeamStageCards((prev) =>
                prev.map((c) => (c.stage === sseEvent.stage && c.queryId === currentQueryIdRef.current ? { ...c, experiences: exps } : c))
              );
            }
          } else if (eventType === 'stream_chunk' || event === 'stream_chunk') {
            if (sseEvent.stage) {
              const cleanedContent = sanitizeStageCardText(sseEvent.content);
              if (!cleanedContent) {
                continue;
              }
              setSeTeamStageCards((prev) =>
                prev.map((c) => (c.stage === sseEvent.stage && c.queryId === currentQueryIdRef.current ? { ...c, content: (c.content || '') + cleanedContent } : c))
              );
            }
          } else if (eventType === 'task_exploration') {
            updateSeTeamTaskExploration(currentQueryIdRef.current, sseEvent.task_exploration);
          } else if (eventType === 'output_write') {
            updateSeTeamOutputWrite(currentQueryIdRef.current, sseEvent.output_write);
          } else if (eventType === 'stage_complete') {
            setSeTeamStepStatus((prev) => ({ ...prev, [sseEvent.stage]: 'completed' }));
            setSeTeamStageCards((prev) => {
              const updated = prev.map((c) => (c.stage === sseEvent.stage && c.queryId === currentQueryIdRef.current ? { ...c, status: 'completed' as const, content: typeof sseEvent.output === 'string' ? sseEvent.output : c.content, artifactFiles: sseEvent.artifact_files || sseEvent.artifact_paths || [] } : c));
              return ensureNextStageCard(updated, activeStepsConfig, String(sseEvent.stage || ''), currentQueryIdRef.current);
            });
          } else if (eventType === 'stage_suspended') {
            setSeTeamStepStatus((prev) => ({ ...prev, [sseEvent.stage]: 'completed' }));
            setSuspendedQuestions(sseEvent.questions || []);
            setClarificationAnswers(new Array((sseEvent.questions || []).length).fill(''));
          } else if (eventType === 'rollback') {
            setRollbacks((prev) => [...prev, { from: sseEvent.from_step, to: sseEvent.to_step, reason: sseEvent.reason }]);
          } else if (eventType === 'workflow_complete') {
            setWorkflowCompleted(true);
            setSeTeamBackendPending(false);
          } else if (eventType === 'workflow_error' || eventType === 'stage_error' || eventType === 'error') {
            setChatError(sseEvent.reason || sseEvent.error || sseEvent.message || 'SE-Team 执行失败');
            setSeTeamBackendPending(false);
          }
        }
      }
    } catch (err) {
      setChatError(err instanceof Error ? err.message : '恢复失败');
    } finally {
      setChatLoading(seTeamBackendPendingRef.current);
      stopChatStream();
    }
  }, [activeStepsConfig, seTeamSessionId, chatLoading, clarificationAnswers, stopChatStream, updateSeTeamOutputWrite, updateSeTeamTaskExploration]);

  const renderHistoryTable = () => (
    <>
      <h2 className="showcase-section-title" style={{ marginTop: 12 }}>已学习项目表格</h2>
      <div className="home-table-hint">点击项目行可切换右侧问答上下文，“查看详情”仍会直接打开工作区。</div>
      <div className="table-container">
        <div className="table-header">
          <div className="table-header-text" style={{ gridColumn: 'span 2' }}>项目名称</div>
          <div className="table-header-text" style={{ gridColumn: 'span 7' }}>项目功能摘要</div>
          <div className="table-header-text" style={{ gridColumn: 'span 3', textAlign: 'right' }}>操作</div>
        </div>

        {historyLoading ? (
          <div className="table-row"><div style={{ gridColumn: 'span 12', color: 'var(--muted-foreground)' }}>正在加载历史项目...</div></div>
        ) : historicalRepos.length === 0 ? (
          <div className="table-row"><div style={{ gridColumn: 'span 12', color: 'var(--muted-foreground)' }}>暂无历史项目</div></div>
        ) : historicalRepos.map((repo) => {
          const identity = repo.path || repo.name;
          const isSelected = Boolean(localProjectPath.trim()) && (repo.path || repo.name) === localProjectPath.trim();
          return (
            <div
              key={`${repo.name}-${repo.path}`}
              className={`table-row selectable${isSelected ? ' selected' : ''}`}
            >
              <button
                type="button"
                className="table-row-select"
                aria-pressed={isSelected}
                onClick={() => setLocalProjectPath(repo.path || repo.name || '')}
              >
                <div style={{ gridColumn: 'span 2' }}>
                  <div className="project-name">{repo.displayName || repo.name}</div>
                  {isSelected ? <span className="project-context-badge">问答上下文</span> : null}
                </div>
                <div style={{ gridColumn: 'span 7' }}>
                  <span className="summary-text">{summarizeRepo(repo)}</span>
                </div>
              </button>
              <div style={{ gridColumn: 'span 3', display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button
                  type="button"
                  className="detail-btn"
                  disabled={openingRepoIdentity === identity || deletingRepoIdentity === identity}
                  onClick={() => void handleOpenHistoricalRepo(repo)}
                >
                  {openingRepoIdentity === identity ? <Loader2 size={14} className="animate-spin" /> : null}
                  查看详情
                </button>
                <button
                  type="button"
                  className="detail-btn danger"
                  disabled={openingRepoIdentity === identity || deletingRepoIdentity === identity}
                  onClick={() => void handleDeleteHistoricalRepo(repo)}
                >
                  {deletingRepoIdentity === identity ? <Loader2 size={14} className="animate-spin" /> : null}
                  删除
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );

  useEffect(() => {
    tasksRef.current = tasks;
  }, [tasks]);

  useEffect(() => {
    activeSessionRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    localStorage.setItem(EXPERIENCE_OUTPUT_ROOT_STORAGE_KEY, experienceOutputRoot || '');
  }, [experienceOutputRoot]);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const repos = await fetchRepos(normalizeServerUrl(window.location.origin));
      const sorted = [...repos].sort((a, b) => String(b.indexedAt || '').localeCompare(String(a.indexedAt || '')));
      setHistoricalRepos(sorted);
    } catch {
      setHistoricalRepos([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const openWorkspace = useCallback(async (task: LearningTask) => {
    if (task.opened) return;

    try {
      onServerConnectStart?.('经验库训练完成，正在载入工作区...');
      await createGraphExtensionsApi.fetchWorkbenchSessionBootstrap('/api', task.sessionId);
      const runtimeServerUrl = window.location.origin;
      const runtimeBaseApiUrl = normalizeServerUrl(runtimeServerUrl);
      const normalizedPath = task.projectPath.replace(/\\/g, '/');
      let repoNameToLoad = toDisplayName(task.projectPath);

      try {
        const repos = await fetchRepos(runtimeBaseApiUrl);
        const matched = repos.find((repo) => (repo.path || '').replace(/\\/g, '/') === normalizedPath);
        if (matched?.name) repoNameToLoad = matched.name;
      } catch {
        // fallback
      }

      const result = await connectToServer(runtimeServerUrl, undefined, undefined, repoNameToLoad);
      onServerConnect?.(result, runtimeServerUrl);
      setTasks((prev) => prev.map((item) => (item.sessionId === task.sessionId ? { ...item, opened: true } : item)));
    } catch {
      // ignore
    }
  }, [onServerConnect, onServerConnectStart]);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      const pending = tasksRef.current.filter((task) => !TERMINAL_STATUSES.has(task.status));
      if (pending.length === 0) return;

      const statuses = await Promise.all(
        pending.map(async (task) => {
          try {
            const status = await createGraphExtensionsApi.fetchWorkbenchSessionStatus('/api', task.sessionId);
            return { sessionId: task.sessionId, status };
          } catch {
            return null;
          }
        }),
      );

      const updates = statuses.filter((item): item is { sessionId: string; status: CreateGraphWorkbenchSessionStatusResponse } => item !== null);
      if (updates.length === 0) return;

      setTasks((prev) => prev.map((task) => {
        const matched = updates.find((item) => item.sessionId === task.sessionId);
        return matched ? mapTaskFromStatus(task, matched.status) : task;
      }));

      const active = activeSessionRef.current;
      if (!active) return;
      const matchedActive = updates.find((item) => item.sessionId === active);
      if (matchedActive?.status.status === 'completed' && !scheduledOpenRef.current.has(active)) {
        scheduledOpenRef.current.add(active);
        setTimeout(() => {
          const task = tasksRef.current.find((item) => item.sessionId === active);
          if (task) {
            void openWorkspace({ ...task, status: 'completed' });
          }
        }, 800);
      }
    }, STATUS_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [openWorkspace]);

  useEffect(() => {
    const candidates = tasksRef.current.filter((task) =>
      task.phase === 'hierarchy_running' || task.phase === 'bootstrap_ready' || task.status === 'completed',
    );
    candidates.forEach((task) => {
      const existing = sessionBootstraps[task.sessionId] || null;
      const existingMetas = getVisibleCommunityMetas(existing);
      if (existing && existingMetas.length > 0) return;
      if (bootstrapLoadingRef.current[task.sessionId]) return;
      bootstrapLoadingRef.current[task.sessionId] = true;
      void createGraphExtensionsApi.fetchWorkbenchSessionBootstrap('/api', task.sessionId)
        .then((payload) => {
          setSessionBootstraps((prev) => {
            const previousPayload = prev[task.sessionId] || null;
            const previousCount = getVisibleCommunityMetas(previousPayload).length;
            const nextCount = getVisibleCommunityMetas(payload).length;
            if (previousCount > 0 && nextCount === 0) {
              return prev;
            }
            return { ...prev, [task.sessionId]: payload };
          });
        })
        .catch(() => {
          bootstrapLoadingRef.current[task.sessionId] = false;
        })
        .finally(() => {
          bootstrapLoadingRef.current[task.sessionId] = false;
        });
    });
  }, [sessionBootstraps]);

  useEffect(() => {
    if (!activeSessionId) return;
    const timer = window.setInterval(async () => {
      let since = logCursorRef.current[activeSessionId] || 0;
      try {
        const collected: TerminalLog[] = [];
        for (let round = 0; round < 5; round += 1) {
          const payload = await createGraphExtensionsApi.fetchWorkbenchSessionLogs('/api', activeSessionId, since, 300);
          logCursorRef.current[activeSessionId] = payload.cursor;
          since = payload.cursor;
          if (Array.isArray(payload.logs) && payload.logs.length > 0) {
            collected.push(...payload.logs.map(toTerminalLog));
          }
          if (!payload.hasMore) break;
        }
        if (collected.length === 0) return;
        setSessionLogs((prev) => {
          const current = prev[activeSessionId] || [];
          const seen = new Set(current.map((item) => item.id));
          const appended = collected.filter((item) => !seen.has(item.id));
          const merged = [...current, ...appended].sort((a, b) => {
            if (a.seq !== b.seq) return a.seq - b.seq;
            return a.id.localeCompare(b.id);
          });
          return { ...prev, [activeSessionId]: merged };
        });
      } catch {
        // ignore
      }
    }, STATUS_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [activeSessionId]);

  const taskCommunityMetas = useMemo(() => {
    const result: Record<string, CommunityMeta[]> = {};
    tasks.forEach((task) => {
      const metas = getVisibleCommunityMetas(sessionBootstraps[task.sessionId] || null);
      if (metas.length > 0) {
        result[task.sessionId] = metas;
        return;
      }

      const shouldShowCommunities = task.phase === 'hierarchy_running'
        || task.phase === 'bootstrap_ready'
        || task.status === 'completed';
      result[task.sessionId] = shouldShowCommunities
        ? buildFallbackCommunityMetas(FALLBACK_COMMUNITY_COUNT)
        : [];
    });
    return result;
  }, [sessionBootstraps, tasks]);

  const communityTargets = useMemo(() => {
    const result: Record<string, number> = {};
    tasks.forEach((task) => {
      const metas = taskCommunityMetas[task.sessionId] || [];
      const n = metas.length;
      if (n === 0) {
        return;
      }
      if (task.status === 'completed') {
        metas.forEach((meta) => { result[`${task.sessionId}::${meta.key}`] = 100; });
        return;
      }
      const progress = Math.max(0, Math.min(100, Math.round(task.progress || 0)));
      if (progress < 55) {
        metas.forEach((meta) => { result[`${task.sessionId}::${meta.key}`] = 0; });
      } else if (progress >= 100) {
        metas.forEach((meta) => { result[`${task.sessionId}::${meta.key}`] = 100; });
      } else if (progress >= 95) {
        metas.forEach((meta) => { result[`${task.sessionId}::${meta.key}`] = 100; });
      } else {
        const span = progress - 55;
        const communitySpan = 40;
        const activeIndex = Math.min(n - 1, Math.floor((span / communitySpan) * n));
        const unit = communitySpan / n;
        const activeProgress = n === 1
          ? Math.round((span / communitySpan) * 100)
          : Math.round(((span - (activeIndex * unit)) / unit) * 100);
        metas.forEach((meta, index) => {
          if (index < activeIndex) {
            result[`${task.sessionId}::${meta.key}`] = 100;
          } else if (index > activeIndex) {
            result[`${task.sessionId}::${meta.key}`] = 0;
          } else {
            result[`${task.sessionId}::${meta.key}`] = Math.max(0, Math.min(100, activeProgress));
          }
        });
      }
    });
    return result;
  }, [taskCommunityMetas, tasks]);

  const shadowArchiveStepCounts = useMemo(() => {
    const result: Record<string, number> = {};
    Object.entries(sessionLogs).forEach(([sessionId, logs]) => {
      result[sessionId] = logs.reduce((count, log) => {
        const text = `${log.source} ${log.message}`;
        return text.includes('影子归档') ? count + 1 : count;
      }, 0);
    });
    return result;
  }, [sessionLogs]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setAnimatedProgress((prev) => {
        const next: Record<string, number> = { ...prev };
        let changed = false;
        tasks.forEach((task) => {
          const metas = taskCommunityMetas[task.sessionId] || [];
          if (metas.length === 0) return;
          if (task.status === 'completed') {
            metas.forEach((meta) => {
              const key = `${task.sessionId}::${meta.key}`;
              const cur = Math.round(next[key] || 0);
              if (cur < 100) { next[key] = Math.min(100, cur + 5); changed = true; }
            });
            return;
          }
          const isHierarchy = task.phase === 'hierarchy_running' || task.phase === 'bootstrap_ready';
          if (!isHierarchy) return;
          for (let i = 0; i < metas.length; i++) {
            const key = `${task.sessionId}::${metas[i].key}`;
            const target = Math.max(0, Math.min(100, Math.round(communityTargets[key] ?? 0)));
            const cur = Math.round(next[key] || 0);
            if (cur < target) { next[key] = Math.min(target, cur + 1); changed = true; break; }
            if (cur > target) { next[key] = Math.max(0, cur - 1); changed = true; break; }
          }
        });
        if (!changed) return prev;
        return next;
      });
    }, PROGRESS_ANIMATION_INTERVAL_MS);
    return () => { window.clearInterval(timer); };
  }, [communityTargets, taskCommunityMetas, tasks]);

  const handleStartLearning = useCallback(async () => {
    const projectPath = localProjectPath.trim();
    if (!projectPath) {
      setError('请输入本地路径');
      return;
    }

    setError(null);
    setStarting(true);
    try {
      const started = await createGraphExtensionsApi.startWorkbenchSession('/api', {
        project_path: projectPath,
        experience_output_root: experienceOutputRoot.trim() || undefined,
      });

      const nextTask: LearningTask = {
        sessionId: started.sessionId,
        projectPath: started.projectPath,
        status: normalizeStatus(started.status),
        phase: started.phase || 'starting',
        progress: 0,
        message: started.message || '会话已创建',
        queueAhead: Math.max(0, Number(started.queueAhead || 0)),
        queuePosition: started.queuePosition,
        opened: false,
      };

      setTasks((prev) => [nextTask, ...prev.filter((item) => item.sessionId !== nextTask.sessionId)]);
      setActiveSessionId(nextTask.sessionId);
      logCursorRef.current[nextTask.sessionId] = 0;
      setSessionLogs((prev) => ({ ...prev, [nextTask.sessionId]: [] }));
      void loadHistory();
    } catch (startError) {
      setError(startError instanceof Error ? startError.message : String(startError));
    } finally {
      setStarting(false);
    }
  }, [experienceOutputRoot, loadHistory, localProjectPath]);

  const handleOpenHistoricalRepo = useCallback(async (repo: RepoSummary) => {
    const runtimeServerUrl = window.location.origin;
    setError(null);
    const identity = repo.path || repo.name;
    setOpeningRepoIdentity(identity);
    onServerConnectStart?.('正在打开历史经验库项目...');

    try {
      const result = await connectToServer(runtimeServerUrl, undefined, undefined, identity);
      onServerConnect?.(result, runtimeServerUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : '打开历史项目失败');
    } finally {
      setOpeningRepoIdentity(null);
    }
  }, [onServerConnect, onServerConnectStart]);

  const handleDeleteHistoricalRepo = useCallback(async (repo: RepoSummary) => {
    const projectPath = String(repo.path || '').trim();
    if (!projectPath) {
      setError('缺少项目路径，无法删除');
      return;
    }

    const displayName = repo.displayName || repo.name || projectPath;
    const confirmed = window.confirm(`确认删除已学习项目「${displayName}」吗？该操作会移除经验库产物。`);
    if (!confirmed) return;

    const identity = repo.path || repo.name;
    setError(null);
    setDeletingRepoIdentity(identity);
    try {
      await deleteLearnedRepo(normalizeServerUrl(window.location.origin), projectPath);
      setHistoricalRepos((prev) => prev.filter((item) => (item.path || item.name) !== identity));
      void loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除已学习项目失败');
    } finally {
      setDeletingRepoIdentity(null);
    }
  }, [loadHistory]);

  const modelCards = useMemo<LearningTask[]>(() => tasks, [tasks]);

  const activeTask = useMemo(
    () => tasks.find((task) => task.sessionId === activeSessionId) || tasks[0] || null,
    [activeSessionId, tasks],
  );

  const terminalLogs = useMemo(() => {
    if (!activeTask) return [];
    return [...(sessionLogs[activeTask.sessionId] || [])].sort((a, b) => {
      if (a.seq !== b.seq) return a.seq - b.seq;
      return a.id.localeCompare(b.id);
    });
  }, [activeTask, sessionLogs]);

  const communityLogGroups = useMemo(() => {
    if (!activeTask) return [];
    const metas = taskCommunityMetas[activeTask.sessionId] || [];
    return buildCommunityLogGroups(terminalLogs, metas);
  }, [activeTask, taskCommunityMetas, terminalLogs]);

  const communityDisplayCounts = useMemo(() => {
    const result: Record<string, number> = {};
    tasks.forEach((task) => {
      const metas = taskCommunityMetas[task.sessionId] || [];
      if (task.status === 'completed') { result[task.sessionId] = metas.length + 1; return; }
      const isHierarchy = task.phase === 'hierarchy_running' || task.phase === 'bootstrap_ready';
      if (!isHierarchy || metas.length === 0) { result[task.sessionId] = 0; return; }
      let count = 1;
      for (let i = 0; i < metas.length - 1; i++) {
        const key = `${task.sessionId}::${metas[i].key}`;
        if (Math.round(animatedProgress[key] || 0) >= 100) { count = i + 2; } else { break; }
      }
      const allCommunityDone = metas.every((meta) => {
        const key = `${task.sessionId}::${meta.key}`;
        return Math.round(animatedProgress[key] || 0) >= 100;
      });
      const shadowSteps = shadowArchiveStepCounts[task.sessionId] || 0;
      const shouldShowShadow = allCommunityDone && (task.progress >= 95 || shadowSteps > 0);
      result[task.sessionId] = shouldShowShadow ? metas.length + 1 : Math.min(count, metas.length);
    });
    return result;
  }, [animatedProgress, shadowArchiveStepCounts, taskCommunityMetas, tasks]);

  const visibleCommunityLogGroups = useMemo(() => {
    if (!activeTask) return [];
    const displayCount = communityDisplayCounts[activeTask.sessionId] || 0;
    const metas = taskCommunityMetas[activeTask.sessionId] || [];
    const visibleCommunityCount = Math.min(displayCount, metas.length);
    const shadowVisible = displayCount > metas.length;
    const globalGroup = communityLogGroups.find((g) => g.name === '全局流水');
    const shadowGroup = communityLogGroups.find((g) => g.name === '影子归档');
    const communityGroups = communityLogGroups.filter((g) => g.name !== '全局流水' && g.name !== '影子归档');
    const result: CommunityLogGroup[] = [];
    if (globalGroup) result.push(globalGroup);
    if (visibleCommunityCount > 0) {
      result.push(...communityGroups.slice(0, visibleCommunityCount));
    }
    if (shadowVisible && shadowGroup) {
      result.push(shadowGroup);
    }
    return result;
  }, [activeTask, communityDisplayCounts, communityLogGroups, taskCommunityMetas]);

  const selectedHistoricalRepo = useMemo(
    () => historicalRepos.find((repo) => (repo.path || repo.name) === localProjectPath.trim()) || null,
    [historicalRepos, localProjectPath],
  );

  const qaPanel = (
    <div className="qa-panel-shell">
      <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--foreground)' }}>问答端</div>

      {pageMode === 'home' ? (
        <div className="qa-context-card">
          <div className="qa-context-label">当前问答上下文</div>
          <div className="qa-context-value">{selectedHistoricalRepo ? (selectedHistoricalRepo.displayName || selectedHistoricalRepo.name) : '全局经验库'}</div>
          <div className="qa-context-meta">
            {selectedHistoricalRepo
              ? summarizeRepo(selectedHistoricalRepo)
              : '未选择具体项目时，将基于全局经验库进行问答。点击左侧项目行可切换到单项目上下文。'}
          </div>
        </div>
      ) : null}


      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', gap: 10, border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 12, background: 'var(--surface)' }}>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12, paddingRight: 4 }}>
            {chatMode === 'local' ? (
              chatMessages.length === 0 ? (
                <div style={{ color: 'var(--muted-foreground)', fontSize: '0.9rem', textAlign: 'center', padding: '40px 0' }}>暂无对话，输入问题开始</div>
              ) : (
                chatMessages.map((msg, idx) => {
                  const isStage = msg.role === 'stage';
                  const content = typeof msg.content === 'string' ? msg.content.trim() : '';
                  const messageKey = `${msg.role}-${msg.stage || 'chat'}-${content || 'empty'}-${(msg as any).thinkingContent || ''}`;
                  if (isStage && !content && !msg.stage) return null;
                  return (
                    <div
                      key={messageKey}
                      style={{
                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '85%',
                        background: isStage ? 'transparent' : msg.role === 'user' ? 'oklch(0.2 0.03 260)' : 'var(--card)',
                        color: isStage ? 'var(--muted-foreground)' : 'var(--foreground)',
                        border: isStage ? '1px solid transparent' : '1px solid var(--border)',
                        borderRadius: 'var(--radius)',
                        padding: isStage ? '4px 8px' : '10px 12px',
                        boxShadow: isStage ? 'none' : '0 8px 24px rgba(0,0,0,0.25)',
                        whiteSpace: 'pre-wrap',
                        fontSize: isStage ? '0.85rem' : '0.95rem',
                      }}
                    >
                      {msg.stage ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--muted-foreground)', marginBottom: content ? 4 : 0, fontWeight: 600 }}>
                          {msg.stage}
                        </div>
                      ) : null}
                      {((msg as any).thinkingContent || (msg as any).isThinking) ? (
                        <div style={{ marginBottom: 12, borderLeft: '3px solid var(--border)', paddingLeft: 10 }}>
                          <button
                            type="button"
                            onClick={() => toggleThinking(idx)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 6,
                              fontSize: '0.8rem',
                              color: 'var(--muted-foreground)',
                              cursor: 'pointer',
                              userSelect: 'none',
                              fontWeight: 600,
                              marginBottom: (msg as any).thinkingCollapsed ? 0 : 6,
                              border: 'none',
                              background: 'transparent',
                              padding: 0,
                            }}
                          >
                            <span>🧠 {(msg as any).isThinking ? '正在思考' : '思考过程'}</span>
                            <span style={{ fontSize: '0.7rem' }}>
                              {(msg as any).thinkingCollapsed ? '【点击展开】' : '【点击收起】'}
                            </span>
                            {(msg as any).isThinking && <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" style={{ marginLeft: 4 }} />}
                          </button>
                          {!(msg as any).thinkingCollapsed && (
                            <div style={{ fontSize: '0.8rem', color: '#9ca3af', lineHeight: 1.4, whiteSpace: 'pre-wrap', maxHeight: 200, overflowY: 'auto' }}>
                              {(msg as any).thinkingContent || '正在检索并构思回复...'}
                            </div>
                          )}
                        </div>
                      ) : null}
                      {content ? (
                        msg.role === 'assistant' || msg.role === 'system' ? (
                          <MarkdownRenderer content={content} showCopyButton />
                        ) : (
                          <div style={{ lineHeight: 1.5 }}>{content}</div>
                        )
                      ) : null}
                    </div>
                  );
                })
              )
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                {chatMessages.filter(m => m.role === 'user').length === 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 10px', textAlign: 'center' }}>
                    <Bot size={36} style={{ color: 'var(--muted-foreground)', marginBottom: 12, opacity: 0.6 }} />
                    <div style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--foreground)' }}>智能体团队待命</div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--muted-foreground)', marginTop: 4, maxWidth: 300 }}>
                      输入开发需求，AI 顾问与实现专家将开启协同分析、设计与测试
                    </div>
                  </div>
                ) : (
                  chatMessages.filter(m => m.role === 'user').map((msg, qIdx) => {
                    const qId = (msg as any).queryId;
                    const cardsForThisQuery = seTeamStageCards.filter(c => c.queryId === qId);
                    const queryTaskExploration = qId ? seTeamTaskExplorationByQuery[qId] : undefined;
                    const queryOutputWrite = qId ? seTeamOutputWriteByQuery[qId] : undefined;
                    const isLatestQuery = qIdx === chatMessages.filter(m => m.role === 'user').length - 1;

                    return (
                      <div key={qId || `${msg.role}-${msg.content}`} style={{ display: 'flex', flexDirection: 'column', gap: 16, borderBottom: !isLatestQuery ? '1px dashed var(--border)' : 'none', paddingBottom: !isLatestQuery ? 24 : 0 }}>
                        <div style={{ alignSelf: 'flex-end', maxWidth: '85%', background: 'var(--primary)', color: 'var(--primary-foreground)', borderRadius: '12px 12px 0 12px', padding: '10px 14px', fontSize: '0.9rem', boxShadow: '0 4px 12px rgba(0,0,0,0.15)', whiteSpace: 'pre-wrap' }}>
                          {msg.content}
                        </div>

                        <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, padding: 14 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                            <Bot size={16} style={{ color: 'var(--primary)' }} />
                            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--foreground)' }}>SE-Team 接收并拆解需求</span>
                          </div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
                            {msg.content}
                          </div>
                        </div>

                        {cardsForThisQuery.length === 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '20px 10px', textAlign: 'center' }}>
                            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" style={{ marginBottom: 8 }} />
                            <div style={{ fontSize: '0.8rem', color: 'var(--muted-foreground)' }}>智能体正在拆解与执行，请稍候...</div>
                          </div>
                        ) : (
                          <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 14 }}>
                            <div style={{ position: 'absolute', left: 15, top: 16, bottom: 16, width: 2, background: 'var(--border)', zIndex: 1 }} />

                            {cardsForThisQuery.map((card) => {
                              const isAdvisor = card.type === 'advisor';
                              const isRunning = card.status === 'running';

                              return (
                                <div key={card.stage} style={{ position: 'relative', paddingLeft: 40, zIndex: 2 }}>
                                  <div style={{
                                    position: 'absolute',
                                    left: 0,
                                    top: 0,
                                    width: 32,
                                    height: 32,
                                    borderRadius: '50%',
                                    background: isRunning
                                      ? (isAdvisor ? 'rgba(250, 204, 21, 0.15)' : 'oklch(0.72 0.17 200 / 0.15)')
                                      : (isAdvisor ? 'rgba(250, 204, 21, 0.25)' : 'rgba(74, 222, 128, 0.2)'),
                                    border: `2px solid ${isRunning
                                      ? (isAdvisor ? 'rgb(250, 204, 21)' : 'var(--primary)')
                                      : (isAdvisor ? 'rgb(250, 204, 21)' : 'rgb(74, 222, 128)')}`,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    boxShadow: isRunning ? '0 0 12px var(--primary-glow)' : 'none',
                                  }}>
                                    {isRunning ? (
                                      <Loader2 size={14} className="animate-spin" style={{ color: isAdvisor ? 'rgb(250, 204, 21)' : 'var(--primary)' }} />
                                    ) : (
                                      <Check size={14} style={{ color: isAdvisor ? 'rgb(250, 204, 21)' : 'rgb(74, 222, 128)' }} />
                                    )}
                                  </div>

                                  <div style={{
                                    background: 'var(--card)',
                                    border: `1px solid ${isRunning
                                      ? (isAdvisor ? 'rgba(250, 204, 21, 0.5)' : 'oklch(0.72 0.17 200 / 0.5)')
                                      : (isAdvisor ? 'rgba(250, 204, 21, 0.2)' : 'rgba(74, 222, 128, 0.2)')}`,
                                    borderRadius: 8,
                                    overflow: 'hidden',
                                  }}>
                                    <div style={{
                                      display: 'flex',
                                      alignItems: 'center',
                                      justifyContent: 'space-between',
                                      padding: '10px 12px',
                                      background: 'rgba(0,0,0,0.15)',
                                      borderBottom: '1px solid var(--border)',
                                    }}>
                                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        {isAdvisor ? (
                                          <span style={{ fontSize: '0.7rem', color: 'rgb(250, 204, 21)', fontWeight: 600, background: 'rgba(250, 204, 21, 0.1)', padding: '2px 6px', borderRadius: 4 }}>专家</span>
                                        ) : (
                                          <span style={{ fontSize: '0.7rem', color: 'var(--primary)', fontWeight: 600, background: 'oklch(0.72 0.17 200 / 0.1)', padding: '2px 6px', borderRadius: 4 }}>模块</span>
                                        )}
                                        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: isAdvisor ? 'rgb(253, 224, 71)' : 'var(--foreground)' }}>
                                          {card.icon} {card.display}
                                        </span>
                                      </div>
                                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                        {isRunning ? (
                                          <span style={{ fontSize: '0.72rem', color: 'var(--primary)', fontWeight: 500 }}>运行中...</span>
                                        ) : (
                                          <span style={{ fontSize: '0.72rem', color: isAdvisor ? 'rgb(250, 204, 21)' : 'rgb(74, 222, 128)', fontWeight: 500, display: 'flex', alignItems: 'center', gap: 2 }}>
                                            已完成
                                          </span>
                                        )}
                                      </div>
                                    </div>

                                    <div style={{ padding: 12 }}>
                                      <div style={{ fontSize: '0.85rem', color: isAdvisor ? 'rgba(254, 240, 138, 0.9)' : 'var(--foreground)', lineHeight: 1.6 }}>
                                        <MarkdownRenderer content={card.content || ''} />
                                      </div>

                                      {card.artifactFiles && card.artifactFiles.length > 0 && (
                                        <div style={{ marginTop: 10, background: 'rgba(0,0,0,0.2)', borderRadius: 6, padding: '8px 10px', border: '1px solid var(--border)' }}>
                                          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--primary)', marginBottom: 4 }}>📁 已产出文件:</div>
                                          {card.artifactFiles.map((file) => {
                                            const parts = file.split(/[/\\]/);
                                            const shortName = parts.slice(-2).join('/');
                                            return (
                                              <div key={file} style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', fontFamily: 'var(--font-mono)' }}>
                                                {shortName}
                                              </div>
                                            );
                                          })}
                                        </div>
                                      )}

                                      {card.experiences && card.experiences.length > 0 && (
                                        <div style={{ marginTop: 8 }}>
                                          {card.experiences.map((exp, expIdx) => {
                                            const expId = `${card.stage}-${expIdx}`;
                                            const isExpExpanded = !!expandedExps[expId];
                                            const projectName = exp.project_name || '参考经验';
                                            const pathCount = (exp.partitions || []).reduce((sum: number, p: any) => sum + (p.paths || []).length, 0);

                                            if (pathCount === 0) return null;

                                            return (
                                              <div key={expId} style={{ marginTop: 6, border: '1px solid rgba(250, 204, 21, 0.2)', borderRadius: 6, background: 'rgba(250, 204, 21, 0.03)', overflow: 'hidden' }}>
                                                <button
                                                  type="button"
                                                  onClick={() => toggleExpCollapse(expId)}
                                                  style={{
                                                    width: '100%',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'space-between',
                                                    padding: '6px 10px',
                                                    border: 'none',
                                                    background: 'transparent',
                                                    cursor: 'pointer',
                                                    textAlign: 'left',
                                                  }}
                                                >
                                                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                    <FolderGit2 size={12} style={{ color: 'rgb(250, 204, 21)' }} />
                                                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgb(253, 224, 71)' }}>经验参考</span>
                                                    <span style={{ fontSize: '0.7rem', color: 'rgba(250, 204, 21, 0.6)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                      【{projectName}】{pathCount}条路径
                                                    </span>
                                                  </div>
                                                  <ChevronRight size={12} style={{ color: 'rgba(250, 204, 21, 0.6)', transform: isExpExpanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s' }} />
                                                </button>

                                                {isExpExpanded && (
                                                  <div style={{ padding: '8px 10px', borderTop: '1px solid rgba(250, 204, 21, 0.1)', background: 'rgba(0,0,0,0.1)' }}>
                                                    {(exp.partitions || []).map((part: any) =>
                                                      (part.paths || []).map((pathItem: any) => (
                                                        <div key={`${part.partition_name || part.name || 'partition'}-${pathItem.path_name || pathItem.path_description || 'path'}`} style={{ marginBottom: 8, paddingBottom: 6, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                                          <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--primary)' }}>
                                                            {pathItem.path_name}
                                                          </div>
                                                          <div style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', marginTop: 2 }}>
                                                            {pathItem.path_description}
                                                          </div>
                                                          {pathItem.cfg_summary && (
                                                            <pre style={{ margin: '4px 0 0', fontSize: '0.65rem', background: 'rgba(0,0,0,0.2)', padding: 4, borderRadius: 4, fontFamily: 'var(--font-mono)', overflowX: 'auto', color: 'rgba(250,204,21,0.7)' }}>
                                                              {pathItem.cfg_summary}
                                                            </pre>
                                                          )}
                                                        </div>
                                                      ))
                                                    )}
                                                  </div>
                                                )}
                                              </div>
                                            );
                                          })}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {isLatestQuery && queryTaskExploration && (
                          <div style={{ background: 'rgba(14, 165, 233, 0.10)', border: '1px solid rgba(14, 165, 233, 0.30)', borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                              <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'rgb(186, 230, 253)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>任务勘探 · OpenCode</div>
                              <div style={{ fontSize: '0.7rem', padding: '2px 8px', borderRadius: 999, border: '1px solid rgba(56, 189, 248, 0.4)', color: 'rgb(224, 242, 254)' }}>{queryTaskExploration.status}</div>
                            </div>
                            <div style={{ fontSize: '0.82rem', color: 'var(--foreground)', lineHeight: 1.6 }}>
                              <MarkdownRenderer content={queryTaskExploration.message} />
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8, fontSize: '0.72rem', color: 'var(--muted-foreground)' }}>
                              <div>阶段：{queryTaskExploration.phase}</div>
                              <div>等待秒数：{typeof queryTaskExploration.waitSeconds === 'number' ? queryTaskExploration.waitSeconds : '-'}</div>
                              {queryTaskExploration.sessionId ? <div style={{ gridColumn: '1 / -1', wordBreak: 'break-all' }}>OpenCode Session：{queryTaskExploration.sessionId}</div> : null}
                              {queryTaskExploration.model ? <div>模型：{queryTaskExploration.model}</div> : null}
                            </div>
                          </div>
                        )}

                        {isLatestQuery && queryOutputWrite && (
                          <div style={{ background: 'rgba(16, 185, 129, 0.10)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: 12, padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
                            <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'rgb(167, 243, 208)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>输出落盘与文件变更</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--muted-foreground)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                              <div>落盘模式：{queryOutputWrite.materializationMode}</div>
                              <div>成功：{queryOutputWrite.writtenCount}，失败：{queryOutputWrite.failedCount}</div>
                              {queryOutputWrite.outputRoot ? <div style={{ wordBreak: 'break-all' }}>输出目录：{queryOutputWrite.outputRoot}</div> : null}
                              {queryOutputWrite.generatedProjectRoot ? <div style={{ wordBreak: 'break-all' }}>新项目目录：{queryOutputWrite.generatedProjectRoot}</div> : null}
                            </div>
                            {queryOutputWrite.modifiedFiles.length > 0 && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'rgb(167, 243, 208)' }}>修改文件</div>
                                {queryOutputWrite.modifiedFiles.slice(0, 12).map((item) => {
                                  const relativePath = typeof item.relativePath === 'string' ? item.relativePath : typeof item.path === 'string' ? item.path : '未知文件';
                                  const changeType = typeof item.changeType === 'string' ? item.changeType : 'modify';
                                  return <div key={`${relativePath}-${changeType}`} style={{ fontSize: '0.72rem', color: 'var(--muted-foreground)', wordBreak: 'break-all' }}>• {relativePath} · {changeType}</div>;
                                })}
                              </div>
                            )}
                            {queryOutputWrite.diffBlocks.length > 0 && (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'rgb(167, 243, 208)' }}>修改前后对比</div>
                                {queryOutputWrite.diffBlocks.slice(0, 6).map((diff, index) => {
                                  const relativePath = typeof diff.relativePath === 'string' ? diff.relativePath : typeof diff.path === 'string' ? diff.path : `diff-${index + 1}`;
                                  const unifiedDiff = typeof diff.unifiedDiff === 'string' ? diff.unifiedDiff : '';
                                  return (
                                    <div key={`${relativePath}-${index}`} style={{ borderRadius: 8, border: '1px solid var(--border)', background: 'rgba(0,0,0,0.18)', padding: 10 }}>
                                      <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--foreground)', marginBottom: 6, wordBreak: 'break-all' }}>{relativePath}</div>
                                      {unifiedDiff ? <pre style={{ margin: 0, overflowX: 'auto', fontSize: '0.68rem', lineHeight: 1.5, color: 'rgb(167, 243, 208)', background: 'rgba(0,0,0,0.22)', padding: 8, borderRadius: 6 }}><code>{unifiedDiff}</code></pre> : null}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}

                        {isLatestQuery && (
                          <>
                            {rollbacks.map((rb) => (
                              <div key={`${rb.from}-${rb.to}-${rb.reason}`} style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 8, padding: '10px 12px', alignSelf: 'stretch', color: 'oklch(0.7 0.15 20)' }}>
                                <RotateCcw size={16} className="animate-pulse" />
                                <span style={{ fontSize: '0.8rem', fontWeight: 500 }}>
                                  {rb.reason}：步骤 {rb.from} → 步骤 {rb.to}
                                </span>
                              </div>
                            ))}

                            {suspendedQuestions.length > 0 && (
                              <div style={{ background: 'rgba(250, 204, 21, 0.05)', border: '1px solid rgba(250, 204, 21, 0.3)', borderRadius: 12, padding: 16 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'rgb(253, 224, 71)', fontWeight: 600, fontSize: '0.9rem', marginBottom: 12 }}>
                                  <AlertTriangle size={18} />
                                  <span>AI 顾问需要您澄清以下问题</span>
                                </div>
                                {suspendedQuestions.map((q, idx) => {
                                  const questionId = `clarification-${q.replace(/[^a-zA-Z0-9\u4e00-\u9fa5]+/g, '-').toLowerCase()}`;
                                  return (
                                  <div key={q} style={{ marginBottom: 10 }}>
                                    <label htmlFor={questionId} style={{ display: 'block', fontSize: '0.8rem', fontWeight: 500, color: 'var(--foreground)', marginBottom: 4 }}>
                                      问题 {idx + 1}: {q}
                                    </label>
                                    <textarea
                                      id={questionId}
                                      value={clarificationAnswers[idx] || ''}
                                      onChange={(e) => {
                                        const newVal = e.target.value;
                                        setClarificationAnswers((prev) => {
                                          const next = [...prev];
                                          next[idx] = newVal;
                                          return next;
                                        });
                                      }}
                                      placeholder="请输入您的回答..."
                                      style={{
                                        width: '100%',
                                        borderRadius: 6,
                                        border: '1px solid var(--border)',
                                        background: 'var(--background)',
                                        color: 'var(--foreground)',
                                        padding: '8px 10px',
                                        fontSize: '0.82rem',
                                        minHeight: 50,
                                        resize: 'vertical',
                                      }}
                                    />
                                  </div>
                                  );
                                })}
                                <button
                                  type="button"
                                  onClick={handleResumeClarification}
                                  style={{
                                    padding: '8px 16px',
                                    borderRadius: 6,
                                    background: 'var(--primary)',
                                    color: 'var(--primary-foreground)',
                                    fontSize: '0.8rem',
                                    fontWeight: 600,
                                    border: 'none',
                                    cursor: 'pointer',
                                    marginTop: 4,
                                  }}
                                >
                                  提交回答并继续
                                </button>
                              </div>
                            )}

                            {workflowCompleted && (
                              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: 'rgba(74, 222, 128, 0.1)', border: '1px solid rgba(74, 222, 128, 0.3)', borderRadius: 12, padding: '20px 10px', textAlign: 'center' }}>
                                <Sparkles size={28} style={{ color: 'rgb(74, 222, 128)', marginBottom: 6 }} />
                                <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'rgb(74, 222, 128)' }}>🎉 AI Team 流程执行完成</h3>
                                <p style={{ fontSize: '0.78rem', color: 'var(--muted-foreground)', marginTop: 2 }}>已成功完成所有分析及知识库提炼阶段</p>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>

        {false && (
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <Cpu size={15} style={{ color: 'var(--primary)' }} />
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--foreground)' }}>角色技能导入 (Persona Skill)</span>
              </div>
              <input
                type="text"
                value={personaSkillPath}
                onChange={(e) => setPersonaSkillPath(e.target.value)}
                placeholder="Skill 目录绝对路径"
                style={{
                  width: '100%',
                  borderRadius: 6,
                  border: '1px solid var(--border)',
                  background: 'var(--background)',
                  color: 'var(--foreground)',
                  padding: '6px 10px',
                  fontSize: '0.75rem',
                  marginBottom: 8,
                  fontFamily: 'var(--font-mono)'
                }}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  onClick={handleImportSkill}
                  disabled={importingSkill || deactivatingSkill}
                  style={{
                    flex: 1,
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    padding: '6px 8px',
                    borderRadius: 6,
                    border: 'none',
                    cursor: 'pointer',
                    background: 'rgba(34, 197, 94, 0.2)',
                    color: '#86efac',
                  }}
                >
                  {importingSkill ? '正在导入...' : '导入Skill'}
                </button>
                <button
                  type="button"
                  onClick={handleRemoveSkill}
                  disabled={importingSkill || deactivatingSkill}
                  style={{
                    flex: 1,
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    padding: '6px 8px',
                    borderRadius: 6,
                    border: 'none',
                    cursor: 'pointer',
                    background: 'rgba(251, 191, 36, 0.15)',
                    color: '#fde047',
                  }}
                >
                  {deactivatingSkill ? '正在去除...' : '去除Skill'}
                </button>
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', marginTop: 8, minHeight: '1.2em', borderTop: '1px solid var(--border)', paddingTop: 6 }}>
                {personaSkillStatus}
              </div>

              <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>已导入的 Skill 列表</div>
                {personaSkillItems.length === 0 ? (
                  <div style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', background: 'var(--surface)', padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border)' }}>暂无已导入 Skill</div>
                ) : (
                  personaSkillItems.map((item) => {
                    const isActive = activePersonaSkill?.personaId === item.personaId;
                    return (
                      <div key={item.personaId} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, background: 'var(--surface)', padding: '6px 8px', borderRadius: 4, border: '1px solid var(--border)' }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--foreground)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name || item.personaId}</div>
                          {item.description && (
                            <div style={{ fontSize: '0.65rem', color: 'var(--muted-foreground)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.description}</div>
                          )}
                        </div>
                        <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                          {isActive ? (
                            <span style={{ fontSize: '0.65rem', fontWeight: 600, padding: '2px 6px', borderRadius: 4, background: 'rgba(34, 197, 94, 0.2)', color: '#86efac', border: '1px solid rgba(34, 197, 94, 0.3)' }}>已激活</span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleActivatePersonaSkill(item.personaId)}
                              disabled={importingSkill || deactivatingSkill}
                              style={{ fontSize: '0.65rem', fontWeight: 600, padding: '2px 6px', borderRadius: 4, background: 'rgba(6, 182, 212, 0.15)', color: '#67e8f9', border: 'none', cursor: 'pointer' }}
                            >
                              激活
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleDeletePersonaSkill(item.personaId)}
                            disabled={importingSkill || deactivatingSkill}
                            style={{ fontSize: '0.65rem', fontWeight: 600, padding: '2px 6px', borderRadius: 4, background: 'rgba(239, 68, 68, 0.15)', color: '#fca5a5', border: 'none', cursor: 'pointer' }}
                          >
                            删除
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--foreground)', display: 'flex', alignItems: 'center', gap: 6, borderBottom: '1px solid var(--border)', paddingBottom: 6 }}>
                <Activity size={14} style={{ color: 'var(--primary)' }} />
                工作流阶段追踪 (静态进度)
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {activeStepsConfig.map((s) => {
                  const status = seTeamStepStatus[s.stage] || 'pending';
                  const isAdvisor = s.type === 'advisor';
                  let dotColor = 'var(--border)';
                  let labelColor = 'var(--muted-foreground)';

                  if (status === 'completed') {
                    dotColor = isAdvisor ? 'rgb(250, 204, 21)' : 'rgb(74, 222, 128)';
                    labelColor = isAdvisor ? 'rgb(250, 204, 21)' : 'rgb(74, 222, 128)';
                  } else if (status === 'running') {
                    dotColor = 'var(--primary)';
                    labelColor = 'var(--foreground)';
                  }

                  return (
                    <div key={s.stage} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: '0.76rem' }}>
                      <div style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: dotColor,
                        boxShadow: status === 'running' ? '0 0 6px var(--primary)' : 'none',
                        animation: status === 'running' ? 'pulse 1.5s infinite' : 'none'
                      }} />
                      <span style={{ color: labelColor, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span>{s.icon}</span>
                        <span style={{ fontWeight: status === 'running' ? 600 : 400 }}>{s.display}</span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {false && (
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {matchedExperiences.length === 0 ? (
              <div style={{ color: 'var(--muted-foreground)', fontSize: '0.78rem', textAlign: 'center', padding: '40px 10px' }}>
                等待流程启动或未匹配到可用的经验项目记录
              </div>
            ) : (
              matchedExperiences.map((exp) => {
                const projectName = exp.project_name || '未命名项目';
                const matchScore = exp.match_score || '0.9';
                const pathCount = (exp.partitions || []).reduce((sum: number, p: any) => sum + (p.paths || []).length, 0);

                return (
                  <div key={exp.project_path || `${projectName}-${matchScore}`} style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--foreground)' }}>📦 {projectName}</span>
                      <span style={{ fontSize: '0.72rem', color: 'rgb(250, 204, 21)', fontWeight: 600 }}>匹配度: {matchScore}</span>
                    </div>
                    {exp.project_path && (
                      <div style={{ fontSize: '0.68rem', color: 'var(--muted-foreground)', wordBreak: 'break-all', fontFamily: 'var(--font-mono)' }}>
                        {exp.project_path}
                      </div>
                    )}
                    <div style={{ fontSize: '0.7rem', color: 'var(--muted-foreground)', marginTop: 2 }}>
                      分区数: {exp.partitions?.length || 0} · 路径数: {pathCount}
                    </div>

                    {pathCount > 0 && (
                      <div style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {(exp.partitions || []).slice(0, 3).map((part: any) =>
                          (part.paths || []).slice(0, 2).map((pathItem: any) => (
                            <div key={`${part.partition_name || part.name || 'partition'}-${pathItem.path_name || pathItem.path_description || 'path'}`}>
                              <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--primary)' }}>{pathItem.path_name}</div>
                              <div style={{ fontSize: '0.68rem', color: 'var(--muted-foreground)' }}>{pathItem.path_description}</div>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {chatError ? <div style={{ color: '#f87171', fontSize: '0.85rem' }}>{chatError}</div> : null}

        {(!chatMode || chatMode === 'local' || chatMode === 'se-team') && (
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10 }}>
            {/* 当前对话模式状态框 - 可点击取消激活 */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => {
                if (activePersonaSkill || chatMode === 'se-team') {
                  void handleRemoveSkill();
                }
              }}
              onKeyDown={(e) => {
                if ((e.key === 'Enter' || e.key === ' ') && (activePersonaSkill || chatMode === 'se-team')) {
                  e.preventDefault();
                  void handleRemoveSkill();
                }
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 14px',
                marginBottom: 8,
                borderRadius: 8,
                cursor: (activePersonaSkill || chatMode === 'se-team') ? 'pointer' : 'default',
                userSelect: 'none',
                fontSize: '0.82rem',
                fontWeight: 600,
                transition: 'all 0.15s',
                border: activePersonaSkill
                  ? '1px solid rgba(34, 197, 94, 0.4)'
                  : chatMode === 'se-team'
                    ? '1px solid rgba(6, 182, 212, 0.4)'
                    : '1px solid var(--border)',
                background: activePersonaSkill
                  ? 'rgba(34, 197, 94, 0.1)'
                  : chatMode === 'se-team'
                    ? 'rgba(6, 182, 212, 0.1)'
                    : 'var(--surface)',
                color: activePersonaSkill
                  ? '#86efac'
                  : chatMode === 'se-team'
                    ? '#67e8f9'
                    : 'var(--muted-foreground)',
              }}
              title={(activePersonaSkill || chatMode === 'se-team') ? '点击取消激活' : '当前对话模式'}
            >
              {activePersonaSkill ? (
                <>
                  <span style={{ fontSize: '0.9rem' }}>🟢</span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    增强型：{activePersonaSkill.name}
                  </span>
                  <span style={{ fontSize: '0.7rem', opacity: 0.75, fontWeight: 500 }}>
                    点击取消
                  </span>
                </>
              ) : chatMode === 'se-team' ? (
                <>
                  <span style={{ fontSize: '0.9rem' }}>🔵</span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    增强型：SE-Team 智能体
                  </span>
                  <span style={{ fontSize: '0.7rem', opacity: 0.75, fontWeight: 500 }}>
                    点击取消
                  </span>
                </>
              ) : (
                <>
                  <span style={{ fontSize: '0.9rem' }}>⚪</span>
                  <span style={{ flex: 1 }}>
                    普通问答模式
                  </span>
                  <span style={{ fontSize: '0.7rem', opacity: 0.7, fontWeight: 500 }}>
                    输入 <kbd style={{ padding: '0 5px', background: 'var(--background)', border: '1px solid var(--border)', borderRadius: 3, fontSize: '0.85em' }}>/</kbd> 切换 Skill
                  </span>
                </>
              )}
            </div>
            <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <textarea
              ref={chatTextareaRef}
              value={chatInput}
              onChange={(e) => {
                const next = e.target.value;
                setChatInput(next);
                const cursor = e.target.selectionStart ?? next.length;
                const parsed = parseSlashCommand(next, cursor);
                if (parsed.kind) {
                  setSlashState({ kind: parsed.kind, query: parsed.query, start: parsed.start, end: parsed.end });
                } else {
                  setSlashState(null);
                }
              }}
              placeholder={chatMode === 'se-team' ? "输入您的开发需求开启顾问辅导工作流... 输入 / 直接选择 Skill" : "提问或描述需求，Enter 发送，Shift+Enter 换行  输入 / 直接选择 Skill"}
              style={{
                flex: 1,
                minHeight: 56,
                maxHeight: 180,
                padding: '8px 12px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
                background: 'var(--background)',
                color: 'var(--foreground)',
                resize: 'none',
                fontSize: '0.88rem'
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  // 弹窗开启时 SlashCommandMenu 的 window-level 监听会先消费 Enter
                  // （通过 capture phase + stopPropagation），所以这里只处理正常发送
                  e.preventDefault();
                  handleSendChat();
                }
              }}
            />
            <button
              type="button"
              onClick={handleSendChat}
              disabled={chatLoading || !chatInput.trim()}
              className="legacy-link"
              style={{
                minHeight: 40,
                padding: '0 14px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
                background: chatLoading ? 'var(--surface-hover)' : 'var(--primary)',
                color: chatLoading ? 'var(--muted-foreground)' : 'var(--primary-foreground)',
                fontWeight: 700,
                fontSize: '0.85rem',
              }}
            >
              {chatLoading ? '执行中...' : '发送'}
            </button>
            <SlashCommandMenu
              activeKind={slashState?.kind ?? null}
              activeQuery={slashState?.query ?? ''}
              onSelect={handleSlashSelect}
              onClose={handleSlashClose}
            />
            </div>
          </div>
        )}
      </div>
    </div>
  );

  if (pageMode === 'home') {
    return (
      <div className="showcase-root">
        <div className="page-layout">
          <aside className="sidebar">
            <div className="sidebar-logo">
              <Brain size={20} />
            </div>
            <nav className="sidebar-nav">
              <div
                className="sidebar-item active"
                onClick={() => setPageMode('home')}
                style={{ cursor: 'pointer' }}
                title="知识库总览"
              >
                <BookOpen size={20} />
              </div>
              <div
                className="sidebar-item"
                onClick={() => setPageMode('learn')}
                style={{ cursor: 'pointer' }}
                title="学习端"
              >
                <Brain size={20} />
              </div>
              <div
                className="sidebar-item"
                onClick={() => setPageMode('skills')}
                style={{ cursor: 'pointer' }}
                title="技能与角色管理"
              >
                <Sparkles size={20} />
              </div>
              <div
                className="sidebar-item"
                onClick={() => setSettingsPanelOpen(true)}
                style={{ cursor: 'pointer' }}
                title="AI 设置"
              >
                <Settings2 size={20} />
              </div>
            </nav>
          </aside>

          <main className="main-content showcase-main showcase-main--home">
            <div className="page-column">
              <div className="page-header" style={{ justifyContent: 'space-between' }}>
                <div>
                  <h1>知识库总览</h1>
                  <p>查看已学习项目，点击右侧按钮开始新的学习</p>
                </div>
                <button
                  type="button"
                  className="submit-btn"
                  style={{ width: 'auto', padding: '10px 14px' }}
                  onClick={() => setPageMode('learn')}
                >
                  学习新项目
                </button>
              </div>

              {renderHistoryTable()}
            </div>

            <div className="showcase-side-panel">
              {qaPanel}
            </div>
          </main>
        </div>
      </div>
    );
  }

  if (pageMode === 'skills') {
    return (
      <div className="showcase-root">
        <div className="page-layout">
          <aside className="sidebar">
            <div className="sidebar-logo">
              <Brain size={20} />
            </div>
            <nav className="sidebar-nav">
              <div
                className="sidebar-item"
                onClick={() => setPageMode('home')}
                style={{ cursor: 'pointer' }}
                title="知识库总览"
              >
                <BookOpen size={20} />
              </div>
              <div
                className="sidebar-item"
                onClick={() => setPageMode('learn')}
                style={{ cursor: 'pointer' }}
                title="学习端"
              >
                <Brain size={20} />
              </div>
              <div
                className="sidebar-item active"
                onClick={() => setPageMode('skills')}
                style={{ cursor: 'pointer' }}
                title="技能与角色管理"
              >
                <Sparkles size={20} />
              </div>
              <div
                className="sidebar-item"
                onClick={() => setSettingsPanelOpen(true)}
                style={{ cursor: 'pointer' }}
                title="AI 设置"
              >
                <Settings2 size={20} />
              </div>
            </nav>
          </aside>

          <main className="main-content showcase-main" style={{ minHeight: 'calc(100vh - 48px)', gridTemplateColumns: '1fr' }}>
            <div className="page-column page-column--learn">
              <div className="page-header" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h1>技能与角色管理</h1>
                  <p>查看已导入的 Skill 库。激活/切换请到聊天输入框输入 <code style={{ background: 'var(--surface)', padding: '1px 6px', borderRadius: 4, fontSize: '0.85em' }}>/</code> 选择。一次仅可启用一个 Skill。</p>
                </div>
                <div className="header-actions" style={{ gap: 10 }}>
                  <button
                    type="button"
                    className="legacy-link"
                    style={{ padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
                    onClick={() => setPageMode('home')}
                  >
                    返回总览
                  </button>
                </div>
              </div>

              {/* Unified panel: 导入 + 技能库 + 状态按钮 */}
              <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 12, padding: 24, display: 'flex', flexDirection: 'column', gap: 18, marginTop: 12 }}>

                {/* 导入新 Skill */}
                <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--foreground)', borderBottom: '1px solid var(--border)', paddingBottom: 10 }}>
                  导入新 Skill
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--muted-foreground)' }}>Skill 绝对路径</label>
                  <input
                    type="text"
                    value={personaSkillPath}
                    onChange={(e) => setPersonaSkillPath(e.target.value)}
                    placeholder="请输入 Skill 目录绝对路径"
                    style={{
                      borderRadius: 6,
                      border: '1px solid var(--border)',
                      background: 'var(--background)',
                      color: 'var(--foreground)',
                      padding: '10px 12px',
                      fontSize: '0.85rem',
                      fontFamily: 'var(--font-mono)'
                    }}
                  />
                </div>

                <div style={{ display: 'flex', gap: 10 }}>
                  <button
                    type="button"
                    onClick={handleImportSkill}
                    disabled={importingSkill || deactivatingSkill}
                    className="submit-btn"
                    style={{
                      flex: 1,
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      padding: '10px 16px',
                      borderRadius: 6,
                      border: 'none',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6
                    }}
                  >
                    {importingSkill ? '正在导入...' : '导入'}
                  </button>
                  <button
                    type="button"
                    onClick={refreshPersonaSkillStatus}
                    disabled={importingSkill || deactivatingSkill}
                    style={{
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      padding: '10px 16px',
                      borderRadius: 6,
                      border: '1px solid var(--border)',
                      cursor: 'pointer',
                      background: 'var(--surface)',
                      color: 'var(--foreground)',
                    }}
                  >
                    刷新列表
                  </button>
                </div>

                {personaSkillStatus && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--foreground)', background: 'var(--surface)', padding: '10px 12px', borderRadius: 6, border: '1px solid var(--border)' }}>
                    <strong>状态提示：</strong>{personaSkillStatus}
                  </div>
                )}

                {/* 技能库 */}
                <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--foreground)', borderBottom: '1px solid var(--border)', paddingBottom: 10, marginTop: 6 }}>
                  技能库
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxHeight: '500px', overflowY: 'auto', paddingRight: 4 }}>
                  {/* Built-in SE-Team Skill Card */}
                  {(() => {
                    const isSETeamActive = chatMode === 'se-team' && !activePersonaSkill;
                    return (
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 10,
                          background: isSETeamActive ? 'rgba(6, 182, 212, 0.08)' : 'var(--surface)',
                          padding: 16,
                          borderRadius: 8,
                          border: isSETeamActive ? '1px solid rgba(6, 182, 212, 0.3)' : '1px solid var(--border)',
                          transition: 'all 0.2s',
                          boxShadow: isSETeamActive ? '0 0 12px rgba(6, 182, 212, 0.1)' : 'none'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ fontSize: '0.65rem', fontWeight: 600, padding: '2px 6px', borderRadius: 4, background: 'rgba(6, 182, 212, 0.15)', color: '#67e8f9', border: '1px solid rgba(6, 182, 212, 0.3)' }}>内置增强</span>
                              <div style={{ fontSize: '0.9rem', fontWeight: 700, color: isSETeamActive ? '#67e8f9' : 'var(--foreground)' }}>
                                SE-Team 顾问智能体工作流
                              </div>
                            </div>
                            <div style={{ fontSize: '0.8rem', color: 'var(--muted-foreground)', marginTop: 4, lineHeight: 1.4 }}>
                              启用由需求顾问、架构顾问和代码顾问组成的软件工程专家多智能体团队，通过全自动化交互规划解决复杂的开发与图谱生成需求。
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                            {isSETeamActive && (
                              <span style={{ fontSize: '0.75rem', fontWeight: 600, padding: '4px 10px', borderRadius: 6, background: 'rgba(6, 182, 212, 0.2)', color: '#67e8f9', border: '1px solid rgba(6, 182, 212, 0.3)' }}>
                                使用中
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })()}

                  {personaSkillItems.length === 0 ? (
                    <div style={{ fontSize: '0.85rem', color: 'var(--muted-foreground)', background: 'var(--surface)', padding: '16px', borderRadius: 6, border: '1px solid var(--border)', textAlign: 'center' }}>
                      暂无已导入 Skill。请在上方指定目录，点击"导入"加载其他 Skill。
                    </div>
                  ) : (
                    personaSkillItems.map((item) => {
                      const isActive = activePersonaSkill?.personaId === item.personaId;
                      return (
                        <div
                          key={item.personaId}
                          style={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: 10,
                            background: isActive ? 'rgba(6, 182, 212, 0.08)' : 'var(--surface)',
                            padding: 16,
                            borderRadius: 8,
                            border: isActive ? '1px solid rgba(6, 182, 212, 0.3)' : '1px solid var(--border)',
                            transition: 'all 0.2s',
                            boxShadow: isActive ? '0 0 12px rgba(6, 182, 212, 0.1)' : 'none'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ fontSize: '0.9rem', fontWeight: 700, color: isActive ? '#67e8f9' : 'var(--foreground)' }}>
                                {item.name || item.personaId}
                              </div>
                              {item.description && (
                                <div style={{ fontSize: '0.8rem', color: 'var(--muted-foreground)', marginTop: 4, lineHeight: 1.4 }}>
                                  {item.description}
                                </div>
                              )}
                            </div>

                            <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                              {isActive && (
                                <span style={{ fontSize: '0.75rem', fontWeight: 600, padding: '4px 10px', borderRadius: 6, background: 'rgba(6, 182, 212, 0.2)', color: '#67e8f9', border: '1px solid rgba(6, 182, 212, 0.3)' }}>
                                  使用中
                                </span>
                              )}

                              <button
                                type="button"
                                onClick={() => handleDeletePersonaSkill(item.personaId)}
                                disabled={importingSkill || deactivatingSkill}
                                style={{
                                  fontSize: '0.75rem',
                                  fontWeight: 600,
                                  padding: '4px 10px',
                                  borderRadius: 6,
                                  background: 'rgba(239, 68, 68, 0.1)',
                                  color: '#fca5a5',
                                  border: '1px solid rgba(239, 68, 68, 0.2)',
                                  cursor: 'pointer',
                                  transition: 'all 0.2s'
                                }}
                              >
                                删除
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

              </div>
            </div>
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="showcase-root">
      <div className="page-layout">
        <aside className="sidebar">
            <div className="sidebar-logo">
              <Brain size={20} />
            </div>
            <nav className="sidebar-nav">
              <div
                className="sidebar-item"
                onClick={() => setPageMode('home')}
                style={{ cursor: 'pointer' }}
                title="知识库总览"
              >
                <BookOpen size={20} />
              </div>
              <div
                className="sidebar-item active"
                onClick={() => setPageMode('learn')}
                style={{ cursor: 'pointer' }}
                title="学习端"
              >
                <Brain size={20} />
              </div>
              <div
                className="sidebar-item"
                onClick={() => setPageMode('skills')}
                style={{ cursor: 'pointer' }}
                title="技能与角色管理"
              >
                <Sparkles size={20} />
              </div>
              <div
                className="sidebar-item"
                onClick={() => setSettingsPanelOpen(true)}
                style={{ cursor: 'pointer' }}
                title="AI 设置"
              >
                <Settings2 size={20} />
              </div>
            </nav>
          </aside>

        <main className="main-content showcase-main showcase-main--learn" style={{ minHeight: 'calc(100vh - 48px)' }}>
          <div className="page-column page-column--learn">
            <div className="page-header" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h1>学习端</h1>
                <p>监控 AI 模型对开源项目的代码学习与分析进程</p>
              </div>
              <div className="header-actions" style={{ gap: 10 }}>
                <div className="info-card">
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{uptime}</span>
                  <span style={{ color: 'var(--muted-foreground)', marginLeft: 4 }}>运行时长</span>
                </div>
                <div className="info-card primary">
                  <div className="pulse-dot"><span className="ping" /><span className="inner" /></div>
                  <span>{tasks.filter((t) => t.status === 'running' || t.status === 'starting').length} 个项目学习中</span>
                </div>
                <button
                  type="button"
                  className="legacy-link"
                  style={{ padding: '8px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}
                  onClick={() => setPageMode('home')}
                >
                  返回历史
                </button>
              </div>
            </div>

            <h2 className="showcase-section-title">GitHub 仓库输入</h2>
            <div className="input-area">
              <div className="input-wrapper">
                <Link className="icon" />
                <input
                  className="input-field"
                  type="text"
                  value={localProjectPath}
                  onChange={(event) => setLocalProjectPath(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !starting) {
                      void handleStartLearning();
                    }
                  }}
                  placeholder="输入本地路径，例如 D:/code/my-project"
                />
              </div>
              <button className="submit-btn" type="button" onClick={() => void handleStartLearning()} disabled={starting}>
                {starting ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                开始学习
              </button>
            </div>
            <div className="input-area" style={{ marginTop: '-8px' }}>
              <div className="input-wrapper">
                <FolderOpen className="icon" />
                <input
                  className="input-field"
                  type="text"
                  value={experienceOutputRoot}
                  onChange={(event) => setExperienceOutputRoot(event.target.value)}
                  placeholder="经验库输出目录（可选）"
                />
              </div>
            </div>
            {error ? <div className="error-text">{error}</div> : null}

            <h2 className="showcase-section-title">模型卡片 ModelCard</h2>
            <div className="model-grid">
              {modelCards.length === 0 ? (
                <div className="model-card queued" style={{ color: 'var(--muted-foreground)' }}>
                  暂无任务，输入本地项目路径后点击“开始学习”。
                </div>
              ) : null}
              {modelCards.map((task) => {
                const status = task.status;
                const isLearning = status === 'running' || status === 'starting';
                const cardClass = status === 'completed' ? 'completed' : status === 'queued' ? 'queued' : 'learning';
                const badgeClass = status === 'completed' ? 'completed' : status === 'queued' ? 'queued' : 'learning';
                const badgeText = status === 'completed' ? '已完成' : status === 'queued' ? '排队中' : '学习中';
                const title = toDisplayName(task.projectPath);
                const queueHint = status === 'queued'
                  ? (task.queueAhead > 0 ? `等待资源分配中... 前方 ${task.queueAhead} 个项目` : '等待资源分配中...')
                  : status === 'failed'
                    ? task.message
                    : null;
                const metas = taskCommunityMetas[task.sessionId] || [];
                const communities = buildCommunityProgress(task, metas, animatedProgress);
                const displayCount = communityDisplayCounts[task.sessionId] || 0;
                const visibleCommunities = communities.slice(0, Math.min(displayCount, communities.length));
                const shadowVisible = displayCount > communities.length;
                const shadowStepsRaw = shadowArchiveStepCounts[task.sessionId] || 0;
                const shadowSteps = shadowVisible ? Math.max(1, shadowStepsRaw) : shadowStepsRaw;

                return (
                  <button
                    key={task.sessionId}
                    type="button"
                    className={`model-card ${cardClass}`}
                    onClick={() => setActiveSessionId(task.sessionId)}
                  >
                    <div className="card-header">
                      <div className="card-header-left">
                        <div className={`card-icon-wrapper ${cardClass}`}>
                          <FolderOpen size={20} />
                        </div>
                        <div>
                          <div className="card-title">{title}</div>
                        </div>
                      </div>
                      <span className={`badge ${badgeClass}`}>
                        {isLearning ? <Loader2 size={12} className="animate-spin" /> : status === 'completed' ? <CheckCircle2 size={12} /> : <Clock3 size={12} />}
                        {badgeText}
                      </span>
                    </div>

                    <div>
                      {(task.phase === 'hierarchy_running' || task.phase === 'bootstrap_ready' || task.status === 'completed') ? (
                        <>
                          {visibleCommunities.length > 0 ? visibleCommunities.map((community, index) => (
                            <div className="stage-row" key={`${task.sessionId}-community-${community.key}`}>
                              {community.status === 'completed'
                                ? <CheckCircle2 className="stage-icon completed" />
                                : <FolderOpen className={`stage-icon ${community.status}`} />}
                              <span className={`stage-name ${community.status}`}>
                                {`构建社区${index + 1}: ${community.name}`}
                              </span>
                              <div className="progress-track">
                                <div
                                  className={`progress-fill ${community.status}`}
                                  style={{ width: `${Math.max(community.status === 'pending' ? 0 : 4, community.progress)}%` }}
                                />
                              </div>
                              <span className={`stage-percent ${community.status}`}>
                                {community.status === 'completed' ? '完成' : `${Math.round(community.progress)}%`}
                              </span>
                            </div>
                          )) : null}
                          {shadowVisible ? (
                            <div className="stage-row" key={`${task.sessionId}-shadow-archive`}>
                              {task.status === 'completed'
                                ? <CheckCircle2 className="stage-icon completed" />
                                : <FolderOpen className="stage-icon current" />}
                              <span className={`stage-name ${task.status === 'completed' ? 'completed' : 'current'}`}>
                                影子归档
                              </span>
                              <span className="stage-percent current" style={{ width: 'auto', minWidth: 92, textAlign: 'left' }}>
                                第 {shadowSteps} 步
                              </span>
                            </div>
                          ) : null}
                          {visibleCommunities.length === 0 && !shadowVisible ? (
                            <div style={{ color: 'var(--muted-foreground)', fontSize: '0.8125rem', padding: '8px 0' }}>
                              社区正在按顺序展开，等待首个社区完成初始化...
                            </div>
                          ) : null}
                        </>
                      ) : (
                        <div style={{ color: 'var(--muted-foreground)', fontSize: '0.8125rem', padding: '8px 0' }}>
                          {status === 'queued' ? '等待资源分配...' : '主分析进行中，社区学习即将开始...'}
                        </div>
                      )}
                    </div>
                    {queueHint ? <div style={{ marginTop: 10, fontSize: '12px', color: 'var(--muted-foreground)' }}>{queueHint}</div> : null}
                  </button>
                );
              })}
            </div>

            <h2 className="showcase-section-title" style={{ marginTop: 28 }}>实时日志终端</h2>
            <div className="log-terminal">
              <div className="log-terminal-header">
                <div className="log-terminal-header-left">
                  <Terminal size={16} style={{ color: 'var(--primary)' }} />
                  <span className="log-terminal-header-title">输出日志</span>
                  <span className="log-terminal-header-count">({terminalLogs.length} 条)</span>
                  <div className="pulse-dot"><span className="ping" /><span className="inner" /></div>
                </div>
              </div>
              <div className="log-terminal-body">
                {!activeTask ? (
                  <div style={{ color: 'var(--muted-foreground)', fontSize: '0.8125rem' }}>暂无日志，开始学习后按社区显示。</div>
                ) : visibleCommunityLogGroups.map((group) => (
                  <div key={group.name} style={{ marginBottom: 12 }}>
                    <div style={{ fontFamily: 'var(--font-sans)', fontSize: '0.75rem', color: 'var(--primary)', marginBottom: 6 }}>
                      {group.name}
                    </div>
                    {group.logs.map((log) => (
                      <div key={log.id} className="log-entry">
                        <span className="log-time">{log.time}</span>
                        <span className={`log-badge ${log.level.toLowerCase()}`}>{log.level}</span>
                        <span className="log-source">[{log.source}]</span>
                        <span className={`log-msg ${log.level.toLowerCase()}`}>{log.message}</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
