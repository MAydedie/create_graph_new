import {
  Activity,
  ArrowRight,
  Bot,
  Boxes,
  BrainCircuit,
  CircleAlert,
  Component,
  Cpu,
  FolderKanban,
  Gauge,
  GitBranchPlus,
  Layers3,
  type LucideIcon,
  MessageSquareText,
  Network,
  Play,
  RefreshCcw,
  ScrollText,
  Send,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Waypoints,
  Workflow,
} from 'lucide-react';
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createLoadingResources,
  fetchConversationDetail,
  fetchConversationMessages,
  fetchConversationSessionResult,
  fetchConversationSessionStatus,
  fetchConversationSummary,
  fetchMultiAgentSessionResult,
  fetchMultiAgentSessionStatus,
  fetchWorkbenchBootstrap,
  fetchWorkbenchSessionStatus,
  isEventFrame,
  loadDashboardResources,
  replyConversationQuestion,
  startConversationSession,
  startMultiAgentSession,
  startWorkbenchSession,
  streamConversationEvents,
} from './api';
import type {
  CommunityItem,
  ConversationMessagesResponse,
  ConversationPendingQuestion,
  ConversationResultResponse,
  ConversationSessionStatusResponse,
  ConversationSseEventFrame,
  DashboardResources,
  Loadable,
  MultiAgentResultResponse,
  MultiAgentSessionStatusResponse,
  PartitionSummary,
  ProcessItem,
  ProjectStatusResponse,
  ReadContractResponse,
  WorkbenchBootstrapResponse,
  WorkbenchSessionStatusResponse,
} from './types';

const DEFAULT_PROJECT_PATH = 'D:\\代码仓库生图\\create_graph';
const POLL_MS = 2000;
const MAX_TIMELINE_EVENTS = 120;

interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
}

interface MetricCardData {
  label: string;
  value: string;
  detail: string;
  tone: 'accent' | 'success' | 'neutral';
  icon: LucideIcon;
}

interface InsightLine {
  level: 'info' | 'success' | 'warn';
  source: string;
  message: string;
}

interface TimelineEvent {
  key: string;
  seq: number;
  type: string;
  createdAt?: string;
  payload: Record<string, unknown>;
  summary: string;
}

interface StageHistoryItem {
  stage?: string;
  message?: string;
  timestamp?: string;
}

interface WorkflowState {
  workbenchSessionId: string | null;
  workbenchStatus: WorkbenchSessionStatusResponse | null;
  workbenchBootstrap: WorkbenchBootstrapResponse | null;
  workbenchError: string;
  workbenchBusy: boolean;
  conversationId: string | null;
  conversationSessionId: string | null;
  conversationStatus: ConversationSessionStatusResponse | null;
  conversationResult: ConversationResultResponse | null;
  conversationError: string;
  conversationSummary: string;
  conversationMessages: ConversationMessagesResponse | null;
  pendingQuestion: ConversationPendingQuestion | null;
  timeline: TimelineEvent[];
  sseState: 'idle' | 'connecting' | 'live' | 'polling' | 'closed';
  lastEventSeq: number;
  multiAgentQuery: string;
  multiAgentSessionId: string | null;
  multiAgentStatus: MultiAgentSessionStatusResponse | null;
  multiAgentResult: MultiAgentResultResponse | null;
  multiAgentError: string;
  multiAgentBusy: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: Gauge },
  { id: 'live', label: 'Live flow', icon: Workflow },
  { id: 'processes', label: 'Processes', icon: Waypoints },
  { id: 'community', label: 'Community', icon: Network },
  { id: 'contract', label: 'Contract', icon: ScrollText },
];

const INITIAL_WORKFLOW: WorkflowState = {
  workbenchSessionId: null,
  workbenchStatus: null,
  workbenchBootstrap: null,
  workbenchError: '',
  workbenchBusy: false,
  conversationId: null,
  conversationSessionId: null,
  conversationStatus: null,
  conversationResult: null,
  conversationError: '',
  conversationSummary: '',
  conversationMessages: null,
  pendingQuestion: null,
  timeline: [],
  sseState: 'idle',
  lastEventSeq: 0,
  multiAgentQuery: '',
  multiAgentSessionId: null,
  multiAgentStatus: null,
  multiAgentResult: null,
  multiAgentError: '',
  multiAgentBusy: false,
};

function App() {
  const [draftPath, setDraftPath] = useState(DEFAULT_PROJECT_PATH);
  const [projectPath, setProjectPath] = useState(DEFAULT_PROJECT_PATH);
  const [refreshTick, setRefreshTick] = useState(0);
  const [lastUpdated, setLastUpdated] = useState('');
  const [resources, setResources] = useState<DashboardResources>(createLoadingResources());
  const [workflow, setWorkflow] = useState<WorkflowState>(INITIAL_WORKFLOW);
  const [chatInput, setChatInput] = useState('请概述当前项目的主问答链路，并展示中间检索过程。');
  const [replyInput, setReplyInput] = useState('');
  const [selectedReplyOptions, setSelectedReplyOptions] = useState<string[]>([]);
  const [multiAgentQuery, setMultiAgentQuery] = useState('');
  const [multiAgentTaskMode, setMultiAgentTaskMode] = useState('modify_existing');
  const eventSourceRef = useRef<null | (() => void)>(null);

  useEffect(() => {
    const controller = new AbortController();
    const marker = refreshTick;
    setResources(createLoadingResources());
    if (marker < 0) {
      return () => controller.abort();
    }
    loadDashboardResources(projectPath, controller.signal)
      .then((nextResources) => {
        setResources(nextResources);
        setLastUpdated(new Date().toLocaleString('zh-CN', { hour12: false }));
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return;
        }
        const message = toErrorMessage(error, '仪表盘请求失败');
        setResources({
          status: { state: 'error', message },
          processes: { state: 'error', message },
          community: { state: 'error', message },
          readContract: { state: 'error', message },
        });
      });
    return () => controller.abort();
  }, [projectPath, refreshTick]);

  const hydrateConversation = useCallback(async (conversationId: string, pollFallback = false) => {
    try {
      const [conversation, messages, summary] = await Promise.all([
        fetchConversationDetail(conversationId),
        fetchConversationMessages(conversationId),
        fetchConversationSummary(conversationId),
      ]);
      setWorkflow((current) => ({
        ...current,
        conversationMessages: messages,
        pendingQuestion: messages.pendingQuestion ?? conversation.pendingQuestion ?? current.pendingQuestion,
        conversationSummary: summary.summarySnapshot?.summary ?? '',
        sseState: pollFallback ? 'polling' : current.sseState,
      }));
    } catch (error) {
      setWorkflow((current) => ({ ...current, conversationError: toErrorMessage(error, '会话详情刷新失败') }));
    }
  }, []);

  useEffect(() => {
    const sessionId = workflow.workbenchSessionId;
    if (!sessionId) {
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const status = await fetchWorkbenchSessionStatus(sessionId);
        if (cancelled) {
          return;
        }
        setWorkflow((current) => ({ ...current, workbenchStatus: status, workbenchBusy: !isTerminal(status.status), workbenchError: status.error ?? '' }));
        if (status.bootstrapReady) {
          try {
            const bootstrap = await fetchWorkbenchBootstrap(sessionId);
            if (!cancelled) {
              setWorkflow((current) => ({ ...current, workbenchBootstrap: bootstrap }));
            }
          } catch {
            return;
          }
        }
      } catch (error) {
        if (!cancelled) {
          setWorkflow((current) => ({ ...current, workbenchBusy: false, workbenchError: toErrorMessage(error, 'workbench 状态刷新失败') }));
        }
      }
    };
    void tick();
    const timer = window.setInterval(() => { void tick(); }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [workflow.workbenchSessionId]);

  useEffect(() => {
    const sessionId = workflow.conversationSessionId;
    const conversationId = workflow.conversationId;
    if (!sessionId) {
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const status = await fetchConversationSessionStatus(sessionId);
        if (cancelled) {
          return;
        }
        setWorkflow((current) => ({ ...current, conversationStatus: status, conversationError: status.error ?? current.conversationError }));
        if (conversationId) {
          await hydrateConversation(conversationId);
        }
        if (isTerminal(status.status)) {
          const result = await fetchConversationSessionResult(sessionId);
          if (!cancelled) {
            setWorkflow((current) => ({
              ...current,
        conversationResult: result,
        pendingQuestion: result.pendingQuestion ?? current.pendingQuestion,
        multiAgentQuery: current.multiAgentQuery || deriveMultiAgentPrompt(result),
            }));
          }
        }
      } catch (error) {
        if (!cancelled) {
          setWorkflow((current) => ({ ...current, conversationError: toErrorMessage(error, '会话状态刷新失败') }));
        }
      }
    };
    void tick();
    const timer = window.setInterval(() => {
      if (!isTerminal(workflow.conversationStatus?.status)) {
        void tick();
      }
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [hydrateConversation, workflow.conversationId, workflow.conversationSessionId, workflow.conversationStatus?.status]);

  useEffect(() => {
    const sessionId = workflow.multiAgentSessionId;
    if (!sessionId) {
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const status = await fetchMultiAgentSessionStatus(sessionId);
        if (cancelled) {
          return;
        }
        setWorkflow((current) => ({ ...current, multiAgentStatus: status, multiAgentBusy: !isTerminal(status.status), multiAgentError: status.error ?? '' }));
        if (isTerminal(status.status)) {
          const result = await fetchMultiAgentSessionResult(sessionId);
          if (!cancelled) {
            setWorkflow((current) => ({ ...current, multiAgentResult: result, multiAgentBusy: false }));
          }
        }
      } catch (error) {
        if (!cancelled) {
          setWorkflow((current) => ({ ...current, multiAgentError: toErrorMessage(error, 'multi-agent 状态刷新失败'), multiAgentBusy: false }));
        }
      }
    };
    void tick();
    const timer = window.setInterval(() => {
      if (!isTerminal(workflow.multiAgentStatus?.status)) {
        void tick();
      }
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [workflow.multiAgentSessionId, workflow.multiAgentStatus?.status]);

  useEffect(() => {
    const conversationId = workflow.conversationId;
    const sessionId = workflow.conversationSessionId;
    const since = workflow.lastEventSeq;
    if (!conversationId || !sessionId) {
      disconnectStream(eventSourceRef);
      return;
    }
    disconnectStream(eventSourceRef);
    setWorkflow((current) => ({ ...current, sseState: 'connecting' }));
    eventSourceRef.current = streamConversationEvents(conversationId, {
      since,
      sessionId,
      onBootstrap: () => {
        setWorkflow((current) => ({ ...current, sseState: 'live' }));
      },
      onEvent: (event) => {
        if (!isEventFrame(event.data)) {
          return;
        }
        const frame = event.data as ConversationSseEventFrame;
        const seq = typeof frame.seq === 'number' ? frame.seq : since + 1;
        const payload = toRecord(frame.payload);
        const next: TimelineEvent = {
          key: `${seq}-${frame.type}-${frame.createdAt ?? ''}`,
          seq,
          type: frame.type,
          createdAt: frame.createdAt,
          payload,
          summary: summarizeEvent(frame.type, payload),
        };
        setWorkflow((current) => ({
          ...current,
          sseState: 'live',
          timeline: appendTimelineEvent(current.timeline, next),
          lastEventSeq: Math.max(current.lastEventSeq, seq),
        }));
      },
      onEnd: () => {
        setWorkflow((current) => ({ ...current, sseState: 'closed' }));
      },
      onError: async () => {
        setWorkflow((current) => ({ ...current, sseState: 'polling' }));
        await hydrateConversation(conversationId, true);
      },
    });
    return () => disconnectStream(eventSourceRef);
  }, [hydrateConversation, workflow.conversationId, workflow.conversationSessionId, workflow.lastEventSeq]);

  useEffect(() => () => disconnectStream(eventSourceRef), []);

  const statusData = getSuccessData(resources.status);
  const readContract = getSuccessData(resources.readContract);
  const processItems = getProcessItems(resources.processes);
  const communityItems = getCommunities(resources.community);
  const bootstrapHierarchy = toRecord(workflow.workbenchBootstrap?.hierarchy);
  const partitions = getPartitionSummaries(bootstrapHierarchy.partitionSummaries) ?? readContract?.adapters?.partition_summaries ?? [];
  const capabilities = getCapabilities(readContract?.capabilities ?? bootstrapHierarchy.capabilities);

  const metricCards = useMemo<MetricCardData[]>(() => [
    {
      label: 'Workbench status',
      value: formatStatusValue(statusData),
      detail: workflow.workbenchStatus?.message ?? statusData?.message ?? '等待工作台状态。',
      tone: statusData?.experienceReady ? 'success' : 'accent',
      icon: Activity,
    },
    {
      label: 'Live events',
      value: formatNumber(workflow.timeline.length),
      detail: workflow.sseState === 'live' ? 'SSE 正在推送中间事件。' : 'SSE 不可用时自动切换 polling。',
      tone: workflow.timeline.length > 0 ? 'success' : 'neutral',
      icon: TerminalSquare,
    },
    {
      label: 'Conversation',
      value: workflow.conversationStatus?.status ?? '--',
      detail: workflow.conversationResult?.nextStep ?? workflow.conversationStatus?.message ?? '等待真实会话启动。',
      tone: workflow.conversationResult?.answer ? 'success' : 'accent',
      icon: MessageSquareText,
    },
    {
      label: 'Multi-agent',
      value: workflow.multiAgentStatus?.stage ?? '--',
      detail: workflow.multiAgentStatus?.message ?? '可在合适时 handoff 到多智能体。',
      tone: workflow.multiAgentResult ? 'success' : 'neutral',
      icon: BrainCircuit,
    },
  ], [statusData, workflow]);

  const insights = useMemo<InsightLine[]>(() => [
    {
      level: statusData?.experienceReady ? 'success' : 'info',
      source: 'status',
      message: statusData ? `${statusData.displayName ?? '当前项目'} · ${statusData.phase} · ${statusData.progress}%` : formatLoadableMessage(resources.status, '等待工作台状态返回。'),
    },
    {
      level: workflow.sseState === 'polling' ? 'warn' : 'info',
      source: 'conversation',
      message: workflow.conversationSessionId ? `session=${workflow.conversationSessionId} · ${workflow.conversationStatus?.status ?? 'running'} · stream=${workflow.sseState}` : '尚未启动真实 conversation session。',
    },
    {
      level: workflow.pendingQuestion ? 'warn' : workflow.conversationResult?.answer ? 'success' : 'info',
      source: 'reply',
      message: workflow.pendingQuestion?.question ?? workflow.conversationResult?.answer?.slice(0, 88) ?? '等待回答或澄清。',
    },
    {
      level: workflow.multiAgentStatus?.status === 'failed' ? 'warn' : workflow.multiAgentResult ? 'success' : 'info',
      source: 'multi_agent',
      message: workflow.multiAgentSessionId ? `${workflow.multiAgentStatus?.stage ?? 'starting'} · ${workflow.multiAgentStatus?.message ?? '执行中'}` : '多智能体未启动。',
    },
    {
      level: 'info',
      source: 'overview',
      message: `processes=${processItems.length} · communities=${communityItems.length} · partitions=${partitions.length}`,
    },
    {
      level: 'info',
      source: 'mount',
      message: `Edict 独立挂载于 /edict；根路由与 /se_team 保持不变。${lastUpdated ? ` 最近刷新 ${lastUpdated}。` : ''}`,
    },
  ], [communityItems.length, lastUpdated, partitions.length, processItems.length, resources.status, statusData, workflow]);

  async function handleStartWorkbench(): Promise<void> {
    setWorkflow((current) => ({ ...current, workbenchBusy: true, workbenchError: '' }));
    try {
      const started = await startWorkbenchSession(projectPath);
      setWorkflow((current) => ({
        ...current,
        workbenchSessionId: started.sessionId,
        workbenchBusy: true,
        workbenchStatus: {
          sessionId: started.sessionId,
          projectPath: started.projectPath,
          status: started.status,
          phase: started.phase,
          progress: 0,
          message: started.message,
          bootstrapReady: false,
        },
      }));
    } catch (error) {
      setWorkflow((current) => ({ ...current, workbenchBusy: false, workbenchError: toErrorMessage(error, '启动 workbench 失败') }));
    }
  }

  async function handleStartConversation(): Promise<void> {
    if (!chatInput.trim()) {
      return;
    }
    disconnectStream(eventSourceRef);
    setWorkflow((current) => ({
      ...current,
      conversationError: '',
      conversationResult: null,
      conversationMessages: null,
      pendingQuestion: null,
      timeline: [],
      lastEventSeq: 0,
      sseState: 'idle',
    }));
    try {
      const started = await startConversationSession(projectPath, chatInput.trim());
      setWorkflow((current) => ({
        ...current,
        conversationId: started.conversationId,
        conversationSessionId: started.sessionId,
        conversationStatus: {
          sessionId: started.sessionId,
          conversationId: started.conversationId,
          projectPath: started.projectPath,
          status: started.status,
          stage: started.stage,
          message: started.message,
        },
      }));
      await hydrateConversation(started.conversationId);
    } catch (error) {
      setWorkflow((current) => ({ ...current, conversationError: toErrorMessage(error, '启动 conversation 失败') }));
    }
  }

  async function handleReply(): Promise<void> {
    const conversationId = workflow.conversationId;
    if (!conversationId || (!replyInput.trim() && selectedReplyOptions.length === 0)) {
      return;
    }
    try {
      const started = await replyConversationQuestion({
        conversationId,
        projectPath: projectPath,
        answer: replyInput.trim() || undefined,
        selectedOptionLabels: selectedReplyOptions,
      });
      setReplyInput('');
      setSelectedReplyOptions([]);
      setWorkflow((current) => ({
        ...current,
        conversationSessionId: started.sessionId,
        conversationStatus: {
          sessionId: started.sessionId,
          conversationId: started.conversationId,
          projectPath: started.projectPath,
          status: started.status,
          stage: started.stage,
          message: started.message,
        },
      }));
    } catch (error) {
      setWorkflow((current) => ({ ...current, conversationError: toErrorMessage(error, '提交澄清回复失败') }));
    }
  }

  async function handleStartMultiAgent(prefillFromResult: boolean): Promise<void> {
    const query = (prefillFromResult ? deriveMultiAgentPrompt(workflow.conversationResult) : multiAgentQuery).trim();
    if (!query) {
      return;
    }
    setWorkflow((current) => ({ ...current, multiAgentBusy: true, multiAgentError: '' }));
    try {
      const started = await startMultiAgentSession({
        projectPath,
        query,
        taskMode: multiAgentTaskMode,
        conversationId: workflow.conversationId ?? undefined,
      });
      setWorkflow((current) => ({
        ...current,
        multiAgentSessionId: started.sessionId,
        multiAgentBusy: true,
        multiAgentStatus: {
          sessionId: started.sessionId,
          projectPath: started.projectPath,
          status: started.status,
          stage: started.stage,
          message: started.message,
        },
      }));
    } catch (error) {
      setWorkflow((current) => ({ ...current, multiAgentBusy: false, multiAgentError: toErrorMessage(error, '启动 multi-agent 失败') }));
    }
  }

  return (
    <div className="shell">
      <aside className="rail" aria-label="Edict primary navigation">
        <div className="rail-mark"><Cpu className="rail-mark-icon" /><span>EDICT</span></div>
        <nav className="rail-nav">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return <a key={item.id} className="rail-link" href={`#${item.id}`}><Icon className="rail-link-icon" /><span>{item.label}</span></a>;
          })}
        </nav>
        <div className="rail-footnote">live frontend<br />same-origin</div>
      </aside>
      <div className="shell-main">
        <header className="topbar">
          <div className="topbar-copy">
            <span className="eyebrow">Borrowed-style isolated mount</span>
            <h1>Edict runnable orchestration console</h1>
            <p>保留既有仪表盘气质，但把 /edict 升级成可直接驱动 workbench、conversation、multi-agent 的真实前端。</p>
          </div>
          <form className="topbar-controls" onSubmit={(event) => { event.preventDefault(); setProjectPath(draftPath.trim() || DEFAULT_PROJECT_PATH); }}>
            <label className="field-label" htmlFor="project-path-input">Project path</label>
            <div className="field-row">
              <input id="project-path-input" className="path-input" type="text" value={draftPath} onChange={(event) => setDraftPath(event.target.value)} spellCheck={false} />
              <button className="action-button action-button-primary" type="submit"><ArrowRight className="button-icon" />应用路径</button>
              <button className="action-button" type="button" onClick={() => setRefreshTick((value) => value + 1)}><RefreshCcw className="button-icon" />刷新</button>
            </div>
          </form>
        </header>
        <main className="dashboard">
          <section className="hero-panel" id="overview">
            <div className="hero-copy">
              <span className="eyebrow">Shell intent</span>
              <h2>Real end-to-end backend workflow visibility</h2>
              <p>项目路径、就绪检测、真实 conversation 会话、SSE 中间事件、澄清回复、多智能体 handoff 全部落到同一张暗色操作台里。</p>
            </div>
            <div className="hero-stack"><HeroBadge icon={ShieldCheck} label="Flask static mount at /edict" /><HeroBadge icon={Bot} label="No gitnexus code imports" /><HeroBadge icon={Boxes} label="Existing same-origin APIs only" /></div>
            <div className="hero-highlight-grid"><HighlightCard title={statusData?.displayName ?? 'Project scope'} detail={projectPath} meta={getString(toRecord(workflow.workbenchBootstrap?.status).hint) ?? statusData?.qualityHint ?? '默认路径可直接替换。'} /><HighlightCard title="Live session posture" detail={workflow.conversationId ?? 'no conversation yet'} meta={workflow.sseState === 'live' ? 'SSE 已接入真实事件流。' : '优先 SSE，异常时轮询回退。'} /></div>
          </section>
          <section className="metric-grid">{metricCards.map((card) => <MetricCard key={card.label} card={card} />)}</section>
          <section className="content-grid content-grid-live" id="live">
            <div className="content-main">
              <Panel eyebrow="Workbench" title="Project readiness / session control" description="读取 project_status；未就绪时可直接启动真实 workbench session，并显示 bootstrap / stage 状态。"><WorkbenchPanel projectPath={projectPath} status={statusData} sessionStatus={workflow.workbenchStatus} bootstrap={workflow.workbenchBootstrap} busy={workflow.workbenchBusy} error={workflow.workbenchError} onStart={handleStartWorkbench} /></Panel>
              <Panel eyebrow="Conversation" title="Runnable chat / clarification loop" description="启动 /api/conversations/session/start；渲染真实 session 状态、最终结果、澄清问题与回复动作。"><ConversationPanel chatInput={chatInput} setChatInput={setChatInput} onStartConversation={handleStartConversation} conversationStatus={workflow.conversationStatus} conversationResult={workflow.conversationResult} conversationSummary={workflow.conversationSummary} conversationMessages={workflow.conversationMessages} pendingQuestion={workflow.pendingQuestion} replyInput={replyInput} setReplyInput={setReplyInput} selectedReplyOptions={selectedReplyOptions} setSelectedReplyOptions={setSelectedReplyOptions} onReply={handleReply} error={workflow.conversationError} /></Panel>
              <Panel eyebrow="Execution" title="Optional multi-agent handoff" description="当 conversation 结果允许继续执行时，直接触发 /api/multi_agent/session/start，并展示真实 stage history / advisor / swarm / opencode 结果。"><MultiAgentPanel query={multiAgentQuery} setQuery={setMultiAgentQuery} taskMode={multiAgentTaskMode} setTaskMode={setMultiAgentTaskMode} onStart={handleStartMultiAgent} canQuickStart={Boolean(workflow.conversationResult?.safeToCodegen || workflow.conversationResult?.handoff)} status={workflow.multiAgentStatus} result={workflow.multiAgentResult} busy={workflow.multiAgentBusy} error={workflow.multiAgentError} /></Panel>
              <Panel id="processes" eyebrow="Process shadow" title="Process list panel" description="只读流程列表仍保留，作为 runnable flow 的结构背景。"><ProcessPanel loadable={resources.processes} /></Panel>
              <Panel id="community" eyebrow="Community shadow" title="Community summary panel" description="汇总社区聚类结果，保留方法簇和摘要式审阅。"><CommunityPanel loadable={resources.community} /></Panel>
            </div>
            <aside className="content-side">
              <Panel eyebrow="Live reading" title="Intermediate backend event timeline" description="直接展示 conversation / multi-agent 的真实中间事件，不再只是静态 shell。"><TimelinePanel timeline={workflow.timeline} sseState={workflow.sseState} /></Panel>
              <Panel id="contract" eyebrow="Phase6 contract" title="Partition summary / read contract" description="读取分区摘要与能力开关，同时优先展示 workbench bootstrap 中的真实摘要。"><ContractPanel loadable={resources.readContract} partitions={partitions} capabilities={capabilities} projectPath={projectPath} /></Panel>
              <Panel eyebrow="Live reading" title="Insight stream" description="终端风格状态读数，聚焦 runnable frontend 当前状态。"><InsightPanel insights={insights} /></Panel>
            </aside>
          </section>
        </main>
      </div>
    </div>
  );
}

function WorkbenchPanel(props: { projectPath: string; status: ProjectStatusResponse | null; sessionStatus: WorkbenchSessionStatusResponse | null; bootstrap: WorkbenchBootstrapResponse | null; busy: boolean; error: string; onStart: () => void; }) {
  const percent = Math.max(0, Math.min(100, props.status?.progress ?? props.sessionStatus?.progress ?? 0));
  const partitions = getPartitionSummaries(toRecord(props.bootstrap?.hierarchy).partitionSummaries) ?? [];
  return <div className="status-layout"><div className="status-callout"><div className="status-callout-row"><span className={`tone-pill tone-pill-${props.status?.experienceReady ? 'success' : 'accent'}`}>{props.status?.status ?? 'unknown'}</span><span className="status-progress">{percent}%</span></div><div className="progress-track" aria-hidden="true"><span className="progress-fill" style={{ width: `${percent}%` }} /></div><p>{props.sessionStatus?.message ?? props.status?.message ?? '等待工作台信号。'}</p><div className="status-note"><Sparkles className="status-note-icon" /><span>{getString(toRecord(props.bootstrap?.status).hint) ?? props.status?.qualityHint ?? '经验库完成后即可获得更强上下文。'}</span></div><div className="workflow-actions"><button className="action-button action-button-primary" type="button" onClick={props.onStart} disabled={props.busy || props.status?.experienceReady}><Play className="button-icon" />{props.status?.experienceReady ? 'Workbench ready' : props.busy ? '启动中...' : 'Start workbench'}</button><span className="meta-inline">{props.projectPath}</span></div>{props.error ? <InlineError message={props.error} /> : null}</div><div className="status-grid"><StatusTile label="Session" value={props.sessionStatus?.sessionId ?? props.status?.activeSessionId ?? 'none'} /><StatusTile label="Phase" value={props.sessionStatus?.phase ?? props.status?.phase ?? '--'} /><StatusTile label="Bootstrap" value={props.sessionStatus?.bootstrapReady || props.status?.bootstrapReady ? 'ready' : 'pending'} /><StatusTile label="Partitions" value={formatNumber(partitions.length)} /></div></div>;
}

function ConversationPanel(props: { chatInput: string; setChatInput: (value: string) => void; onStartConversation: () => void; conversationStatus: ConversationSessionStatusResponse | null; conversationResult: ConversationResultResponse | null; conversationSummary: string; conversationMessages: ConversationMessagesResponse | null; pendingQuestion: ConversationPendingQuestion | null; replyInput: string; setReplyInput: (value: string) => void; selectedReplyOptions: string[]; setSelectedReplyOptions: (value: string[]) => void; onReply: () => void; error: string; }) {
  const options = props.pendingQuestion?.options ?? [];
  return <div className="flow-stack"><div className="input-stack"><label className="field-label" htmlFor="conversation-query">Chat / query</label><textarea id="conversation-query" className="editor-input" rows={4} value={props.chatInput} onChange={(event) => props.setChatInput(event.target.value)} /><div className="workflow-actions"><button className="action-button action-button-primary" type="button" onClick={props.onStartConversation}><Send className="button-icon" />Start conversation</button><span className="meta-inline">status: {props.conversationStatus?.status ?? 'idle'} · stage: {props.conversationStatus?.stage ?? '--'}</span></div></div><div className="info-grid two-up"><InfoCard title="Session status" body={props.conversationStatus?.message ?? '尚未启动会话。'} meta={props.conversationStatus?.sessionId ?? 'session pending'} /><InfoCard title="Result summary" body={(props.conversationResult?.answer ?? props.conversationSummary) || '完成后会在这里展示最终回答摘要。'} meta={props.conversationResult?.nextStep ?? 'next step pending'} /></div>{props.pendingQuestion ? <div className="clarification-panel"><div className="list-card-header"><div><h4>{props.pendingQuestion.header ?? 'Pending clarification'}</h4><p>{props.pendingQuestion.question ?? '请补充更多信息。'}</p></div><span className="tone-pill tone-pill-accent">round {props.pendingQuestion.round ?? 1}</span></div>{options.length > 0 ? <div className="option-grid">{options.map((option) => { const active = props.selectedReplyOptions.includes(option.label); return <button key={option.id ?? option.label} type="button" className={`option-chip${active ? ' is-active' : ''}`} onClick={() => props.setSelectedReplyOptions(active ? props.selectedReplyOptions.filter((item) => item !== option.label) : props.pendingQuestion?.multiple ? [...props.selectedReplyOptions, option.label] : [option.label])}><strong>{option.label}</strong><span>{option.description ?? option.promptFragment ?? option.label}</span></button>; })}</div> : null}<textarea className="editor-input" rows={3} value={props.replyInput} onChange={(event) => props.setReplyInput(event.target.value)} placeholder="补充说明，或只选择上面的选项后直接提交。" /><div className="workflow-actions"><button className="action-button action-button-primary" type="button" onClick={props.onReply}><ArrowRight className="button-icon" />Submit reply</button><span className="meta-inline">selected: {props.selectedReplyOptions.length}</span></div></div> : null}<div className="message-pane"><div className="list-card-header"><div><h4>Conversation transcript</h4><p>真实 messages / parts 回读，方便确认问答与 handoff 状态。</p></div><span className="tone-pill tone-pill-neutral">{props.conversationMessages?.messages.length ?? 0} msgs</span></div><div className="stack-list compact-scroll">{(props.conversationMessages?.messages ?? []).slice(-6).map((message) => { const record = toRecord(message); const role = getString(record.role) ?? 'message'; const content = getString(record.content) ?? ''; const createdAt = getString(record.createdAt); const messageId = getString(record.messageId) ?? `${role}-${createdAt ?? content.slice(0, 16)}`; return <article className="list-card list-card-compact" key={messageId}><div className="list-card-header"><div><h4>{role}</h4><p>{content}</p></div><span className="tone-pill tone-pill-neutral">{formatTime(createdAt)}</span></div></article>; })}</div></div>{props.error ? <InlineError message={props.error} /> : null}</div>;
}

function MultiAgentPanel(props: { query: string; setQuery: (value: string) => void; taskMode: string; setTaskMode: (value: string) => void; onStart: (prefillFromResult: boolean) => void; canQuickStart: boolean; status: MultiAgentSessionStatusResponse | null; result: MultiAgentResultResponse | null; busy: boolean; error: string; }) {
  const stageHistory = getStageHistory(props.status?.stageHistory);
  return <div className="flow-stack"><div className="input-stack"><label className="field-label" htmlFor="multi-agent-query">Multi-agent handoff query</label><textarea id="multi-agent-query" className="editor-input" rows={4} value={props.query} onChange={(event) => props.setQuery(event.target.value)} placeholder="例如：基于当前会话证据，给出可执行修改方案与代码片段。" /><div className="workflow-actions workflow-actions-wrap"><select className="select-input" value={props.taskMode} onChange={(event) => props.setTaskMode(event.target.value)}><option value="modify_existing">modify_existing</option><option value="write_new_code">write_new_code</option></select><button className="action-button action-button-primary" type="button" onClick={() => void props.onStart(false)} disabled={props.busy}><GitBranchPlus className="button-icon" />{props.busy ? 'Running...' : 'Start multi-agent'}</button><button className="action-button" type="button" onClick={() => void props.onStart(true)} disabled={!props.canQuickStart || props.busy}><Workflow className="button-icon" />Quick start from conversation</button></div></div><div className="status-grid two-columns"><StatusTile label="Session" value={props.status?.sessionId ?? 'none'} /><StatusTile label="Stage" value={props.status?.stage ?? '--'} /><StatusTile label="Advisor" value={getString(toRecord(props.status?.advisor).status) ?? '--'} /><StatusTile label="Swarm" value={String(toRecord(props.status?.swarm).enabled ?? '--')} /></div><div className="info-grid two-up"><InfoCard title="Stage history" body={stageHistory.map(formatStageLine).join('\n') || '尚无 stage history。'} mono /><InfoCard title="Execution result" body={stringifyStructured(props.result?.solution_packet ?? props.result?.output_protocol ?? {}) || '完成后会展示 solution / output protocol。'} mono /></div><div className="info-grid two-up"><InfoCard title="Advisor summary" body={stringifyStructured(props.result?.advisor_packet ?? props.status?.advisor ?? {}) || '暂无 advisor 摘要。'} mono /><InfoCard title="Swarm / opencode summary" body={[stringifyStructured(props.result?.swarm_packet ?? props.status?.swarm ?? {}), stringifyStructured(props.result?.opencode_kernel ?? props.status?.opencode ?? {})].filter(Boolean).join('\n\n') || '暂无 swarm / opencode 摘要。'} mono /></div>{props.error ? <InlineError message={props.error} /> : null}</div>;
}

function TimelinePanel(props: { timeline: TimelineEvent[]; sseState: WorkflowState['sseState'] }) {
  return <div className="terminal-panel"><div className="terminal-header"><div className="terminal-title"><TerminalSquare className="terminal-title-icon" /><div><strong>Backend event stream</strong><span>{props.timeline.length} lines · {props.sseState}</span></div></div><span className={`tone-pill ${props.sseState === 'live' ? 'tone-pill-success' : 'tone-pill-accent'}`}>{props.sseState}</span></div><div className="terminal-body">{props.timeline.length === 0 ? <div className="terminal-row terminal-row-static"><span className="terminal-level">idle</span><span className="terminal-source">[events]</span><span className="terminal-message">启动 conversation 后，这里会连续出现 retrieval / clarification / handoff / multi-agent 中间事件。</span></div> : null}{props.timeline.map((item) => <div className="terminal-row" key={item.key}><span className="terminal-level">{item.seq}</span><span className="terminal-source">[{item.type}]</span><span className="terminal-message">{item.summary}</span></div>)}</div></div>;
}

function HeroBadge(props: { icon: LucideIcon; label: string }) { const Icon = props.icon; return <span className="hero-badge"><Icon className="hero-badge-icon" />{props.label}</span>; }
function HighlightCard(props: { title: string; detail: string; meta: string }) { return <article className="highlight-card"><span className="highlight-label">{props.title}</span><strong>{props.detail}</strong><p>{props.meta}</p></article>; }
function MetricCard(props: { card: MetricCardData }) { const Icon = props.card.icon; return <article className={`metric-card metric-card-${props.card.tone}`}><div className="metric-card-header"><span>{props.card.label}</span><Icon className="metric-card-icon" /></div><strong>{props.card.value}</strong><p>{props.card.detail}</p></article>; }
function Panel(props: { id?: string; title: string; eyebrow: string; description: string; children: ReactNode }) { return <section className="panel" id={props.id}><div className="panel-header"><span className="eyebrow">{props.eyebrow}</span><h3>{props.title}</h3><p>{props.description}</p></div>{props.children}</section>; }
function StatusTile(props: { label: string; value: string }) { return <article className="status-tile"><span>{props.label}</span><strong>{props.value}</strong></article>; }
function InlineError(props: { message: string }) { return <div className="resource-state resource-state-error is-compact"><CircleAlert className="resource-state-icon" /><div><strong>Action failed</strong><p>{props.message}</p></div></div>; }
function InfoCard(props: { title: string; body: string; meta?: string; mono?: boolean }) { return <article className={`list-card${props.mono ? ' is-mono-card' : ''}`}><div className="list-card-header"><div><h4>{props.title}</h4><p className={props.mono ? 'mono-text' : ''}>{props.body}</p></div>{props.meta ? <span className="tone-pill tone-pill-neutral">{props.meta}</span> : null}</div></article>; }
function ResourceState(props: { title: string; message: string; tone?: 'loading' | 'error' | 'empty'; compact?: boolean }) { return <div className={`resource-state resource-state-${props.tone ?? 'loading'}${props.compact ? ' is-compact' : ''}`}><CircleAlert className="resource-state-icon" /><div><strong>{props.title}</strong><p>{props.message}</p></div></div>; }
function MetaChip(props: { icon: LucideIcon; label: string }) { const Icon = props.icon; return <span className="meta-chip"><Icon className="meta-chip-icon" />{props.label}</span>; }
function SummaryStat(props: { label: string; value: string }) { return <div className="summary-stat"><span>{props.label}</span><strong>{props.value}</strong></div>; }

function ProcessPanel(props: { loadable: DashboardResources['processes'] }) {
  if (props.loadable.state === 'loading') return <ResourceState title="Loading processes" message="正在读取流程列表。" />;
  if (props.loadable.state === 'error') return <ResourceState title="Process list unavailable" message={props.loadable.message} tone="error" />;
  if (props.loadable.state === 'empty') return <ResourceState title="No processes yet" message={props.loadable.message} tone="empty" />;
  return <div className="stack-list">{props.loadable.data.processes.slice(0, 8).map((process, index) => <article className="list-card" key={buildProcessKey(process, index)}><div className="list-card-header"><div><h4>{getProcessLabel(process, index)}</h4><p>{getProcessDescription(process)}</p></div><span className="tone-pill tone-pill-neutral">#{index + 1}</span></div><div className="chip-row"><MetaChip icon={FolderKanban} label={process.partition_id || 'unassigned partition'} /><MetaChip icon={Component} label={`${getProcessStepCount(process)} steps`} /><MetaChip icon={Network} label={`${getStringArray(process.communities).length} communities`} /></div></article>)}</div>;
}

function CommunityPanel(props: { loadable: DashboardResources['community'] }) {
  if (props.loadable.state === 'loading') return <ResourceState title="Loading communities" message="正在读取社区聚类结果。" />;
  if (props.loadable.state === 'error') return <ResourceState title="Community summary unavailable" message={props.loadable.message} tone="error" />;
  const communities = props.loadable.state === 'success' ? getCommunities(props.loadable) : getCommunities(props.loadable.data ?? null);
  const totalMethods = communities.reduce((sum, item) => sum + getCommunityMethods(item).length, 0);
  if (props.loadable.state === 'empty') return <div className="community-layout"><div className="summary-strip"><SummaryStat label="Communities" value="00" /><SummaryStat label="Methods tagged" value="00" /><SummaryStat label="Mode" value="read-only" /></div><ResourceState title="Community shadow empty" message={props.loadable.message} tone="empty" compact /></div>;
  return <div className="community-layout"><div className="summary-strip"><SummaryStat label="Communities" value={formatNumber(communities.length)} /><SummaryStat label="Methods tagged" value={formatNumber(totalMethods)} /><SummaryStat label="Mode" value="read-only" /></div><div className="stack-list">{communities.slice(0, 6).map((community, index) => <article className="list-card" key={buildCommunityKey(community, index)}><div className="list-card-header"><div><h4>{getCommunityLabel(community, index)}</h4><p>{getCommunityDescription(community)}</p></div><span className="tone-pill tone-pill-accent">{getCommunityMethods(community).length} methods</span></div><div className="method-ribbon">{getCommunityMethods(community).slice(0, 4).map((method) => <span className="method-token" key={method}>{method}</span>)}</div></article>)}</div></div>;
}

function ContractPanel(props: { loadable: Loadable<ReadContractResponse>; partitions: PartitionSummary[]; capabilities: Array<[string, boolean]>; projectPath: string }) {
  if (props.loadable.state === 'loading' && props.partitions.length === 0) return <ResourceState title="Loading contract" message="正在读取 Phase6 读契约。" />;
  if (props.loadable.state === 'error' && props.partitions.length === 0) return <ResourceState title="Contract unavailable" message={props.loadable.message} tone="error" />;
  const version = props.loadable.state === 'success' ? props.loadable.data.contract_version : 'workbench bootstrap';
  return <div className="contract-layout"><div className="contract-callout"><div className="list-card-header"><div><h4>{version}</h4><p>{props.projectPath}</p></div><span className="tone-pill tone-pill-success">read-only</span></div><div className="chip-row">{props.capabilities.map(([key, enabled]) => <span className={`capability-chip${enabled ? ' is-enabled' : ''}`} key={key}>{key}</span>)}</div></div>{props.partitions.length === 0 ? <ResourceState title="No partition summaries yet" message="当前没有可展示的 partition_summaries。" tone="empty" compact /> : <div className="stack-list">{props.partitions.slice(0, 6).map((partition) => <PartitionCard key={partition.partition_id} partition={partition} />)}</div>}</div>;
}

function PartitionCard(props: { partition: PartitionSummary }) {
  const supports = [props.partition.has_cfg ? 'CFG' : '', props.partition.has_dfg ? 'DFG' : '', props.partition.has_io ? 'IO' : ''].filter(Boolean);
  return <article className="partition-card"><div className="list-card-header"><div><h4>{props.partition.name}</h4><p>{props.partition.description || '该分区已接入 Phase6 读契约摘要。'}</p></div><span className="tone-pill tone-pill-neutral">{props.partition.analysis_status || 'unknown'}</span></div><div className="summary-strip summary-strip-dense"><SummaryStat label="Paths" value={formatNumber(props.partition.path_count || 0)} /><SummaryStat label="Processes" value={formatNumber(props.partition.process_count || 0)} /><SummaryStat label="Communities" value={formatNumber(props.partition.community_count || 0)} /></div><div className="chip-row"><MetaChip icon={Layers3} label={`${props.partition.entry_point_count || 0} entries`} /><MetaChip icon={Activity} label={`${props.partition.rich_path_count || 0} rich paths`} /><MetaChip icon={TerminalSquare} label={supports.length > 0 ? supports.join(' · ') : 'lightweight'} /></div></article>;
}

function InsightPanel(props: { insights: InsightLine[] }) {
  return <div className="terminal-panel"><div className="terminal-header"><div className="terminal-title"><TerminalSquare className="terminal-title-icon" /><div><strong>Edict stream</strong><span>{props.insights.length} lines</span></div></div><span className="tone-pill tone-pill-accent">same-origin</span></div><div className="terminal-body">{props.insights.map((insight) => <div className="terminal-row" key={`${insight.source}-${insight.message}`}><span className="terminal-level">{insight.level}</span><span className="terminal-source">[{insight.source}]</span><span className="terminal-message">{insight.message}</span></div>)}<div className="terminal-row terminal-row-static"><span className="terminal-level">lock</span><span className="terminal-source">[scope]</span><span className="terminal-message">Root / and /se_team remain untouched.</span></div></div></div>;
}

function getSuccessData<T>(loadable: Loadable<T>): T | null { return loadable.state === 'success' ? loadable.data : null; }
function getProcessItems(loadable: DashboardResources['processes'] | null): ProcessItem[] { if (!loadable) return []; if (loadable.state === 'success') return Array.isArray(loadable.data.processes) ? loadable.data.processes : []; if (loadable.state === 'empty') return Array.isArray(loadable.data?.processes) ? loadable.data.processes : []; return []; }
function getCommunities(loadable: DashboardResources['community'] | { communities?: CommunityItem[] } | null): CommunityItem[] { if (!loadable) return []; if ('state' in loadable) { if (loadable.state === 'success') return Array.isArray(loadable.data.communities) ? loadable.data.communities : []; if (loadable.state === 'empty') return Array.isArray(loadable.data?.communities) ? loadable.data.communities : []; return []; } return Array.isArray(loadable.communities) ? loadable.communities : []; }
function formatLoadableMessage<T>(loadable: Loadable<T>, fallback: string): string { if (loadable.state === 'loading') return fallback; if (loadable.state === 'error' || loadable.state === 'empty') return loadable.message; return fallback; }
function formatNumber(value: number): string { return value.toString().padStart(2, '0'); }
function formatStatusValue(status: ProjectStatusResponse | null): string { return status ? `${Math.max(0, Math.min(100, status.progress))}%` : '--'; }
function getProcessLabel(process: ProcessItem, index: number): string { return String(process.entry || process.process_id || process.entry_node_id || `Process ${index + 1}`); }
function getProcessDescription(process: ProcessItem): string { const description = String(process.description || process.summary || '').trim(); return description || '来自 process shadow 的流程节点聚合结果。'; }
function getProcessStepCount(process: ProcessItem): number { const stepCount = process.stepCount ?? process.step_count; return typeof stepCount === 'number' && Number.isFinite(stepCount) ? stepCount : 0; }
function buildProcessKey(process: ProcessItem, index: number): string { return String(process.process_id || process.entry || process.entry_node_id || index); }
function getStringArray(value: unknown): string[] { return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : []; }
function buildCommunityKey(community: CommunityItem, index: number): string { return String(community.community_id || community.name || community.label || index); }
function getCommunityLabel(community: CommunityItem, index: number): string { return String(community.name || community.label || community.community_id || `Community ${index + 1}`); }
function getCommunityDescription(community: CommunityItem): string { const description = String(community.summary || community.description || '').trim(); return description || '社区摘要缺失，当前仅展示聚类与方法数量。'; }
function getCommunityMethods(community: CommunityItem): string[] { const methods = getStringArray(community.methods); return methods.length > 0 ? methods : getStringArray(community.members); }
function getString(value: unknown): string | null { return typeof value === 'string' && value.trim() ? value : null; }
function toRecord(value: unknown): Record<string, unknown> { return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}; }
function isTerminal(status?: string | null): boolean { return status === 'completed' || status === 'failed'; }
function disconnectStream(ref: React.MutableRefObject<null | (() => void)>): void { if (ref.current) { ref.current(); ref.current = null; } }
function toErrorMessage(error: unknown, fallback: string): string { return error instanceof Error ? error.message : fallback; }
function appendTimelineEvent(current: TimelineEvent[], next: TimelineEvent): TimelineEvent[] { if (current.some((item) => item.key === next.key)) return current; return [...current, next].slice(-MAX_TIMELINE_EVENTS); }
function summarizeEvent(type: string, payload: Record<string, unknown>): string { for (const key of ['message', 'reason', 'action', 'taskMode', 'phase', 'stage', 'status', 'error']) { const value = payload[key]; if (typeof value === 'string' && value.trim()) return `${type} · ${value}`; } const steps = payload.steps; if (Array.isArray(steps)) return `${type} · ${steps.length} decision steps`; return type; }
function deriveMultiAgentPrompt(result: ConversationResultResponse | null): string { if (!result) return ''; if (typeof result.answer === 'string' && result.answer.trim()) return `基于当前 conversation 结果继续执行：\n${result.answer}`; const handoff = toRecord(result.handoff); return getString(handoff.query) ?? '基于当前会话证据给出可执行方案、受影响文件与验证步骤。'; }
function stringifyStructured(value: unknown): string { if (!value) return ''; try { return JSON.stringify(value, null, 2); } catch { return String(value); } }
function formatTime(value?: string | null): string { return value ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false }) : '--:--:--'; }
function getPartitionSummaries(value: unknown): PartitionSummary[] | null { return Array.isArray(value) ? value as PartitionSummary[] : null; }
function getCapabilities(value: unknown): Array<[string, boolean]> { if (!value || typeof value !== 'object') return []; return Object.entries(value).map(([key, enabled]) => [key, Boolean(enabled)]); }
function getStageHistory(value: unknown): StageHistoryItem[] { return Array.isArray(value) ? value.map((item) => toRecord(item)).map((item) => ({ stage: getString(item.stage) ?? undefined, message: getString(item.message) ?? getString(item.summary) ?? undefined, timestamp: getString(item.timestamp) ?? undefined })) : []; }
function formatStageLine(item: StageHistoryItem): string { return `${item.timestamp ? formatTime(item.timestamp) : '--'} · ${item.stage ?? '--'} · ${item.message ?? ''}`; }

export default App;
