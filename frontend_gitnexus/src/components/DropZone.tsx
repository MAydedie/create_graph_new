import { useState, useCallback, useEffect, useRef, type DragEvent } from 'react';
import { ArrowRight, Eye, EyeOff, FileArchive, FolderOpen, Github, Globe, Key, Loader2, Upload, X } from 'lucide-react';
import { cloneRepository, parseGitHubUrl } from '../services/git-clone';
import { connectToServer, fetchRepos, normalizeServerUrl, type ConnectToServerResult, type RepoSummary } from '../services/server-connection';
import { createGraphExtensionsApi, type CreateGraphWorkbenchSessionStatusResponse } from '../services/create-graph-extensions';
import type { FileEntry } from '../services/zip';

const LOCAL_PATH_ANALYSIS_POLL_INTERVAL_MS = 1000;
const LOCAL_PATH_ANALYSIS_TIMEOUT_MS = 60 * 60 * 1000;
const HIDE_REDUNDANT_ENTRY_TABS = true;
const EXPERIENCE_OUTPUT_ROOT_STORAGE_KEY = 'create-graph.experience-output-root';

function mapWorkbenchStatusToProgress(status: CreateGraphWorkbenchSessionStatusResponse): { phase: string; progress: number; message: string } {
  const phase = String(status.phase || 'running');
  const rawProgress = Math.max(0, Math.min(100, Number(status.progress || 0)));
  const stageLabel = String((status as { stageLabel?: string }).stageLabel || '').trim();
  const stageDetail = String((status as { stageDetail?: string }).stageDetail || '').trim();
  const messageRaw = String(status.message || '').trim();

  let mappedProgress = rawProgress;
  if (phase === 'main_running') {
    mappedProgress = Math.max(3, Math.min(18, Math.round((rawProgress / 50) * 15 + 3)));
  } else if (phase === 'hierarchy_running') {
    if (rawProgress <= 0) {
      mappedProgress = 22;
    } else {
      const normalized = Math.max(0, Math.min(1, (rawProgress - 55) / 40));
      mappedProgress = Math.max(18, Math.min(92, Math.round(18 + normalized * 74)));
    }

    const lower = `${stageLabel} ${stageDetail} ${messageRaw}`.toLowerCase();
    if (lower.includes('分区')) mappedProgress = Math.max(mappedProgress, 38);
    if (lower.includes('路径')) mappedProgress = Math.max(mappedProgress, 65);
    if (lower.includes('索引') || lower.includes('缓存') || lower.includes('保存')) mappedProgress = Math.max(mappedProgress, 85);
  } else if (phase === 'bootstrap_ready' || phase === 'completed') {
    mappedProgress = Math.max(96, rawProgress);
  }

  const stageMessage = stageLabel || messageRaw || '正在分析...';
  const finalMessage = stageDetail ? `${stageMessage} · ${stageDetail}` : stageMessage;

  return {
    phase,
    progress: Math.max(1, Math.min(99, mappedProgress)),
    message: finalMessage,
  };
}

function buildLocalPathTimeoutMessage(status?: CreateGraphWorkbenchSessionStatusResponse): string {
  const segments = ['分析超时，请稍后重试。'];
  if (status?.phase) {
    segments.push(`当前阶段：${status.phase}`);
  }
  if (status?.message) {
    segments.push(`上下文：${status.message}`);
  }
  return segments.join(' ');
}

interface DropZoneProps {
  onFileSelect: (file: File) => void;
  onGitClone?: (files: FileEntry[]) => void;
  onServerConnectStart?: (message?: string) => void;
  onServerConnect?: (result: ConnectToServerResult, serverUrl?: string) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const DropZone = ({ onFileSelect, onGitClone, onServerConnectStart, onServerConnect }: DropZoneProps) => { const [isDragging, setIsDragging] = useState(false);
const [activeTab, setActiveTab] = useState<'zip' | 'github' | 'path' | 'server'>(() => {
  if (HIDE_REDUNDANT_ENTRY_TABS) return 'path';
  const tab = new URLSearchParams(window.location.search).get('tab');
  if (tab === 'zip' || tab === 'github' || tab === 'path' || tab === 'server') {
    return tab;
  }
  return 'path';
});
const [githubUrl, setGithubUrl] = useState('');
const [githubToken, setGithubToken] = useState('');
const [showToken, setShowToken] = useState(false);
const [isCloning, setIsCloning] = useState(false);
const [cloneProgress, setCloneProgress] = useState({ phase: '', percent: 0 });
const [error, setError] = useState<string | null>(null);

// Server tab state
const [serverUrl, setServerUrl] = useState(() =>
  localStorage.getItem('create-graph-server-url') || ''
);
const [isConnecting, setIsConnecting] = useState(false);
const [serverProgress, setServerProgress] = useState<{
  phase: string;
  downloaded: number;
  total: number | null;
}>({ phase: '', downloaded: 0, total: null });
const abortControllerRef = useRef<AbortController | null>(null);

// Local path analysis tab state
const [localProjectPath, setLocalProjectPath] = useState('');
const [isPathAnalyzing, setIsPathAnalyzing] = useState(false);
const [pathProgress, setPathProgress] = useState<{
  phase: string;
  progress: number;
  message: string;
}>({ phase: '', progress: 0, message: '' });
const pathCancelRef = useRef(false);
const [analysisMode, setAnalysisMode] = useState<'experience' | 'quick'>('quick');
const [experienceOutputRoot, setExperienceOutputRoot] = useState(() => localStorage.getItem(EXPERIENCE_OUTPUT_ROOT_STORAGE_KEY) || '');
const [historicalRepos, setHistoricalRepos] = useState<RepoSummary[]>([]);
const [historyLoading, setHistoryLoading] = useState(false);
const [openingRepoIdentity, setOpeningRepoIdentity] = useState<string | null>(null);

const sleep = (ms: number) => new Promise<void>((resolve) => {
  window.setTimeout(() => resolve(), ms);
});

useEffect(() => {
  localStorage.setItem(EXPERIENCE_OUTPUT_ROOT_STORAGE_KEY, experienceOutputRoot || '');
}, [experienceOutputRoot]);

useEffect(() => {
  let cancelled = false;
  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const baseApiUrl = normalizeServerUrl(window.location.origin);
      const repos = await fetchRepos(baseApiUrl);
      if (!cancelled) {
        setHistoricalRepos(Array.isArray(repos) ? repos : []);
      }
    } catch {
      if (!cancelled) {
        setHistoricalRepos([]);
      }
    } finally {
      if (!cancelled) {
        setHistoryLoading(false);
      }
    }
  };
  loadHistory();
  return () => {
    cancelled = true;
  };
}, []);

const handleOpenHistoricalRepo = useCallback(async (repo: RepoSummary) => {
    const runtimeServerUrl = window.location.origin;
    setError(null);
    const repoIdentity = repo.path || repo.name;
    setOpeningRepoIdentity(repoIdentity);
    onServerConnectStart?.('正在打开历史经验库项目...');
    try {
      const result = await connectToServer(runtimeServerUrl, undefined, undefined, repoIdentity);
      if (onServerConnect) {
        onServerConnect(result, runtimeServerUrl);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '打开历史项目失败';
      setError(message);
    } finally {
      setOpeningRepoIdentity(null);
    }
  }, [onServerConnect, onServerConnectStart]);

const handleDragOver = useCallback((e: DragEvent<HTMLElement>) => {
  e.preventDefault();
  e.stopPropagation();
  setIsDragging(true);
}, []);

const handleDragLeave = useCallback((e: DragEvent<HTMLElement>) => {
  e.preventDefault();
  e.stopPropagation();
  setIsDragging(false);
}, []);

const handleDrop = useCallback((e: DragEvent<HTMLElement>) => {
  e.preventDefault();
  e.stopPropagation();
  setIsDragging(false);

  const files = e.dataTransfer.files;
  if (files.length > 0) {
    const file = files[0];
    if (file.name.endsWith('.zip')) {
      onFileSelect(file);
    } else {
      setError('请拖入 .zip 文件');
    }
  }
}, [onFileSelect]);

const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
  const files = e.target.files;
  if (files && files.length > 0) {
    const file = files[0];
    if (file.name.endsWith('.zip')) {
      onFileSelect(file);
    } else {
      setError('请选择 .zip 文件');
    }
  }
}, [onFileSelect]);

const handleGitClone = async () => {
  if (!githubUrl.trim()) {
    setError('请输入 GitHub 仓库链接');
    return;
  }

  const parsed = parseGitHubUrl(githubUrl);
  if (!parsed) {
    setError('GitHub 链接无效，请使用：https://github.com/owner/repo');
    return;
  }

  setError(null);
  setIsCloning(true);
  setCloneProgress({ phase: 'starting', percent: 0 });

  try {
    const files = await cloneRepository(
      githubUrl,
      (phase, percent) => setCloneProgress({ phase, percent }),
      githubToken || undefined
    );

    setGithubToken('');

    if (onGitClone) {
      onGitClone(files);
    }
  } catch (err) {
    console.error('Clone failed:', err);
    const message = err instanceof Error ? err.message : 'Failed to clone repository';
    if (message.includes('401') || message.includes('403') || message.includes('Authentication')) {
      if (!githubToken) {
        setError('这似乎是私有仓库，请添加 GitHub PAT（个人访问令牌）后再访问。');
      } else {
        setError('认证失败，请检查令牌权限（需要仓库访问权限）。');
      }
    } else if (message.includes('404') || message.includes('not found')) {
      setError('未找到仓库，请检查链接；如果是私有仓库，需要提供 PAT。');
    } else {
      setError(message);
    }
  } finally {
    setIsCloning(false);
  }
};

const handleServerConnect = async () => {
  const urlToUse = serverUrl.trim() || window.location.origin;
  if (!urlToUse) {
    setError('请输入服务地址');
    return;
  }

  // Persist URL to localStorage
  localStorage.setItem('create-graph-server-url', serverUrl);

  setError(null);
  setIsConnecting(true);
  setServerProgress({ phase: 'validating', downloaded: 0, total: null });

  const abortController = new AbortController();
  abortControllerRef.current = abortController;

  try {
    const result = await connectToServer(
      urlToUse,
      (phase, downloaded, total) => {
        setServerProgress({ phase, downloaded, total });
      },
      abortController.signal
    );

    if (onServerConnect) {
      onServerConnect(result, urlToUse);
    }
  } catch (err) {
    if ((err as Error).name === 'AbortError') {
      // User cancelled
      return;
    }
    console.error('Server connect failed:', err);
    const message = err instanceof Error ? err.message : 'Failed to connect to server';
    if (message.includes('Failed to fetch') || message.includes('NetworkError')) {
      setError('无法连接到服务，请检查地址并确认服务已启动。');
    } else {
      setError(message);
    }
  } finally {
    setIsConnecting(false);
    abortControllerRef.current = null;
  }
};

const handleCancelConnect = () => {
  abortControllerRef.current?.abort();
  setIsConnecting(false);
};

const handleLocalPathAnalyze = async () => {
  const normalizedPath = localProjectPath.trim();
  if (!normalizedPath) {
    setError('请输入本地项目路径');
    return;
  }

  setError(null);
  setIsPathAnalyzing(true);
  pathCancelRef.current = false;
  setPathProgress({
    phase: 'starting',
    progress: 1,
      message: analysisMode === 'experience' ? '正在启动经验库训练会话...' : '正在启动快速代码分析会话...',
  });

  try {
    const normalizedExperienceOutputRoot = experienceOutputRoot.trim();
    const started = await createGraphExtensionsApi.startWorkbenchSession('/api', {
      project_path: normalizedPath,
      experience_output_root: normalizedExperienceOutputRoot || undefined,
    });

    const sessionId = started.sessionId;
    let completed = false;
    const startedAt = Date.now();
    let lastStatus: CreateGraphWorkbenchSessionStatusResponse | undefined;

    while (Date.now() - startedAt < LOCAL_PATH_ANALYSIS_TIMEOUT_MS) {
      if (pathCancelRef.current) {
        throw new Error('cancelled_by_user');
      }

      await sleep(LOCAL_PATH_ANALYSIS_POLL_INTERVAL_MS);

      const status = await createGraphExtensionsApi.fetchWorkbenchSessionStatus('/api', sessionId);
      lastStatus = status;
      setPathProgress(mapWorkbenchStatusToProgress(status));

      if (status.status === 'failed') {
        throw new Error(status.error || status.message || 'Analysis failed');
      }

      const reachedTarget = analysisMode === 'experience'
        ? status.status === 'completed'
        : (status.bootstrapReady || status.status === 'completed');

      if (reachedTarget) {
        completed = true;
        break;
      }
    }

    if (!completed) {
      throw new Error(buildLocalPathTimeoutMessage(lastStatus));
    }

    setPathProgress({
      phase: 'bootstrap_ready',
      progress: 99,
      message: analysisMode === 'experience' ? '经验库训练已完成，正在载入工作区...' : '正在载入分析结果...',
    });

    await createGraphExtensionsApi.fetchWorkbenchSessionBootstrap('/api', sessionId);

    const runtimeServerUrl = window.location.origin;
    const runtimeBaseApiUrl = normalizeServerUrl(runtimeServerUrl);
    const normalizedAnalyzedPath = started.projectPath.replace(/\\/g, '/');
    const analyzedRepoName = normalizedAnalyzedPath.split('/').filter(Boolean).pop();

    let repoNameToLoad: string | undefined = analyzedRepoName;
    try {
      const repos = await fetchRepos(runtimeBaseApiUrl);
      const matchedRepo = repos.find((repo) => {
        const repoPath = (repo.path || '').replace(/\\/g, '/');
        return repoPath === normalizedAnalyzedPath;
      });
      if (matchedRepo?.name) {
        repoNameToLoad = matchedRepo.name;
      }
    } catch {
      // keep fallback `analyzedRepoName`
    }

    const result = await connectToServer(
      runtimeServerUrl,
      (phase, downloaded, total) => {
        if (phase === 'downloading') {
          const percent = total ? Math.min(100, Math.round((downloaded / total) * 100)) : 99;
          setPathProgress({
            phase: 'downloading_graph',
            progress: Math.max(percent, 90),
            message: total
              ? `正在下载图谱 ${percent}%`
              : `正在下载图谱 ${formatBytes(downloaded)}`,
          });
          return;
        }

        if (phase === 'extracting') {
          setPathProgress({
            phase: 'extracting_graph',
            progress: 99,
              message: '正在准备图谱视图...',
          });
        }
      },
      undefined,
      repoNameToLoad,
    );

    if (onServerConnect) {
      onServerConnect(result, runtimeServerUrl);
    }

    setPathProgress({
      phase: 'completed',
      progress: 100,
      message: '分析完成',
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : '本地路径分析失败';
    if (message === 'cancelled_by_user') {
      return;
    }
    setError(message);
  } finally {
    setIsPathAnalyzing(false);
    pathCancelRef.current = false;
  }
};

const handleCancelPathAnalyze = () => {
  pathCancelRef.current = true;
  setIsPathAnalyzing(false);
};

const serverProgressPercent = serverProgress.total
  ? Math.round((serverProgress.downloaded / serverProgress.total) * 100)
  : null;

const entryOptions = [
  { key: 'zip', title: '上传压缩包', desc: '适合已有代码快照，最快进入图谱。' },
  { key: 'github', title: '拉取 GitHub 仓库', desc: '适合公开仓库或带 PAT 的私有仓库。' },
  { key: 'server', title: '连接已运行服务', desc: '直接加载后端已构建好的图谱与文件内容。' },
  { key: 'path', title: '分析本地路径', desc: '由本机后端执行统一分析，再回到工作区。' },
] as const;

return (
  <div className="flex items-center justify-center min-h-screen p-8 bg-void">
    {/* Background gradient effects */}
    <div className="fixed inset-0 pointer-events-none">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-accent/6 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-node-interface/6 rounded-full blur-3xl" />
    </div>

    <div className="relative w-full max-w-6xl">
      <section className="hidden rounded-[28px] border border-border-default bg-surface/92 p-8 shadow-2xl">
        <div className="max-w-2xl">
          <div className="inline-flex items-center rounded-full border border-border-subtle bg-elevated px-3 py-1 text-xs text-text-secondary">
            create_graph 前端工作台
          </div>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-text-primary">
            用更清晰的入口，把代码仓带入可浏览、可提问、可定位的知识图谱。
          </h1>
          <p className="mt-3 text-sm leading-7 text-text-secondary">
            先选择导入方式，进入主工作区后可依次查看：左侧文件树、中央图谱、右侧功能分区 / Process / RAG 问答。
          </p>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {entryOptions.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => { setActiveTab(option.key); setError(null); }}
              className={`rounded-2xl border p-4 text-left transition-colors ${activeTab === option.key
                ? 'border-accent bg-accent/10'
                : 'border-border-subtle bg-elevated/35 hover:bg-elevated/60'
              }`}
            >
              <div className="text-sm font-medium text-text-primary">{option.title}</div>
              <div className="mt-1 text-xs leading-6 text-text-secondary">{option.desc}</div>
            </button>
          ))}
        </div>

        <div className="mt-6 rounded-2xl border border-border-subtle bg-elevated/25 p-5">
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">使用路径</div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-border-subtle bg-surface/55 p-4">
              <div className="text-xs text-text-muted">01 导入代码</div>
              <div className="mt-1 text-sm text-text-primary">选择 ZIP、GitHub、服务或本地路径</div>
            </div>
            <div className="rounded-xl border border-border-subtle bg-surface/55 p-4">
              <div className="text-xs text-text-muted">02 浏览结构</div>
              <div className="mt-1 text-sm text-text-primary">查看文件树、图谱高亮、功能分区与 Process</div>
            </div>
            <div className="rounded-xl border border-border-subtle bg-surface/55 p-4">
              <div className="text-xs text-text-muted">03 发起问题</div>
              <div className="mt-1 text-sm text-text-primary">在 RAG 面板按时间线查看检索、判断与答案生成过程</div>
            </div>
          </div>
        </div>
      </section>

      <div className="relative w-full max-w-5xl mx-auto">
        <div className="mb-5 rounded-2xl border border-border-default bg-surface/85 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-text-muted">create_graph 工作台入口</div>
          <h1 className="mt-2 text-2xl font-semibold text-text-primary">先选模式：快速代码分析 / 训练专属经验库</h1>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            经验库训练会在后台同步执行主图谱与功能层级，耗时较长；快速模式可先进入图谱，但经验库未完成时问答/代码生成效果会偏弱。
          </p>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <button
              type="button"
              onClick={() => { setAnalysisMode('experience'); setActiveTab('path'); setError(null); }}
              className={`rounded-xl border p-4 text-left transition-colors ${analysisMode === 'experience' ? 'border-accent bg-accent/10' : 'border-border-subtle bg-elevated/30 hover:bg-elevated/50'}`}
            >
              <div className="text-sm font-semibold text-text-primary">训练专属经验库</div>
              <div className="mt-1 text-xs leading-6 text-text-secondary">完整分析（主图谱 + 功能层级 + 功能路径），耗时较长但后续问答更强。</div>
            </button>
            <button
              type="button"
              onClick={() => { setAnalysisMode('quick'); setActiveTab('path'); setError(null); }}
              className={`rounded-xl border p-4 text-left transition-colors ${analysisMode === 'quick' ? 'border-accent bg-accent/10' : 'border-border-subtle bg-elevated/30 hover:bg-elevated/50'}`}
            >
              <div className="text-sm font-semibold text-text-primary">快速代码分析</div>
              <div className="mt-1 text-xs leading-6 text-text-secondary">优先快速进入图谱，经验库在后台继续构建；未完成时问答/代码生成会弱化。</div>
            </button>
          </div>

          <div className="mt-4 rounded-xl border border-amber-300/30 bg-amber-200/10 px-3 py-2 text-xs text-amber-100">
            {analysisMode === 'experience'
              ? '当前为经验库训练模式：将等待完整训练完成后进入工作区。'
              : '当前为快速模式：达到主图谱就绪即进入工作区，经验库会继续在后台构建。'}
          </div>
        </div>

        <div className="mb-5 rounded-2xl border border-border-default bg-surface/75 p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">历史经验库项目</div>
              <div className="mt-1 text-xs text-text-secondary">点击可直接快速打开；展示名为“LLM语义名 · 路径”。</div>
            </div>
            <button
              type="button"
              onClick={async () => {
                setHistoryLoading(true);
                try {
                  const repos = await fetchRepos(normalizeServerUrl(window.location.origin));
                  setHistoricalRepos(Array.isArray(repos) ? repos : []);
                } catch {
                  setHistoricalRepos([]);
                } finally {
                  setHistoryLoading(false);
                }
              }}
              className="px-3 py-1.5 rounded-md border border-border-subtle text-xs text-text-secondary hover:text-text-primary hover:bg-elevated"
            >
              刷新列表
            </button>
          </div>

          <div className="mt-3 grid gap-2">
            {historyLoading ? (
              <div className="text-xs text-text-muted">正在加载历史项目...</div>
            ) : historicalRepos.length === 0 ? (
              <div className="text-xs text-text-muted">暂无历史经验库项目。</div>
            ) : (
              historicalRepos.slice(0, 8).map((repo) => (
                <button
                  key={`${repo.name}-${repo.path}`}
                  type="button"
                  onClick={() => handleOpenHistoricalRepo(repo)}
                  disabled={openingRepoIdentity === (repo.path || repo.name)}
                  className="w-full rounded-lg border border-border-subtle bg-elevated/25 px-3 py-2 text-left hover:bg-elevated/55 disabled:opacity-60"
                >
                  <div className="text-sm text-text-primary truncate">{repo.displayName || `${repo.name} · ${repo.path}`}</div>
                  <div className="mt-1 text-[11px] text-text-muted truncate">{repo.path}</div>
                </button>
              ))
            )}
          </div>
        </div>

      {/* Tab Switcher */}
      {!HIDE_REDUNDANT_ENTRY_TABS && (
      <div className="flex mb-4 bg-surface border border-border-default rounded-xl p-1 shadow-sm">
        <button
          type="button"
          onClick={() => { setActiveTab('zip'); setError(null); }}
          className={`
            flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg
            text-sm font-medium transition-all duration-200
            ${activeTab === 'zip'
               ? 'bg-accent text-white shadow-sm'
              : 'text-text-secondary hover:text-text-primary hover:bg-elevated'
            }
          `}
        >
          <FileArchive className="w-4 h-4" />
          ZIP 上传
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('github'); setError(null); }}
          className={`
            flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg
            text-sm font-medium transition-all duration-200
            ${activeTab === 'github'
               ? 'bg-accent text-white shadow-sm'
              : 'text-text-secondary hover:text-text-primary hover:bg-elevated'
            }
          `}
        >
          <Github className="w-4 h-4" />
          GitHub 仓库
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('server'); setError(null); }}
          className={`
            flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg
            text-sm font-medium transition-all duration-200
            ${activeTab === 'server'
               ? 'bg-accent text-white shadow-sm'
              : 'text-text-secondary hover:text-text-primary hover:bg-elevated'
            }
          `}
        >
          <Globe className="w-4 h-4" />
          服务连接
        </button>
        <button
          type="button"
          onClick={() => { setActiveTab('path'); setError(null); }}
          className={`
            flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg
            text-sm font-medium transition-all duration-200
            ${activeTab === 'path'
               ? 'bg-accent text-white shadow-sm'
              : 'text-text-secondary hover:text-text-primary hover:bg-elevated'
            }
          `}
        >
          <FolderOpen className="w-4 h-4" />
          本地路径
        </button>
      </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm text-center">
          {error}
        </div>
      )}

      {/* ZIP Upload Tab */}
      {activeTab === 'zip' && (
        <>
          <input
            id="file-input"
            type="file"
            accept=".zip"
            className="hidden"
            onChange={handleFileInput}
          />
          <button
            type="button"
            className={`
              relative p-12
              bg-surface border-2 border-dashed rounded-3xl
              transition-all duration-300 cursor-pointer
              ${isDragging
                ? 'border-accent bg-elevated scale-[1.01] shadow-lg'
                : 'border-border-default hover:border-accent/50 hover:bg-elevated/50'
               }
            `}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => document.getElementById('file-input')?.click()}
          >
            {/* Icon */}
            <div className={`
              mx-auto w-20 h-20 mb-6
              flex items-center justify-center
               bg-accent
               rounded-2xl shadow-sm
               transition-transform duration-300
              ${isDragging ? 'scale-110' : ''}
            `}>
              {isDragging ? (
                <Upload className="w-10 h-10 text-white" />
              ) : (
                <FileArchive className="w-10 h-10 text-white" />
              )}
            </div>

            {/* Text */}
            <h2 className="text-xl font-semibold text-text-primary text-center mb-2">
               {isDragging ? '松手即可开始导入' : '导入代码压缩包'}
             </h2>
             <p className="text-sm text-text-secondary text-center mb-6">
               支持直接拖拽或点击选择 `.zip` 文件，适合最快速进入工作区。
             </p>

            {/* Hints */}
            <div className="flex items-center justify-center gap-3 text-xs text-text-muted">
              <span className="px-3 py-1.5 bg-elevated border border-border-subtle rounded-md">
                .zip
              </span>
            </div>
          </button>

        </>
      )}

      {/* GitHub URL Tab */}
      {activeTab === 'github' && (
        <div className="p-8 bg-surface border border-border-default rounded-3xl">
          {/* Icon */}
             <div className="mx-auto w-20 h-20 mb-6 flex items-center justify-center bg-[#24292e] rounded-2xl shadow-sm">
            <Github className="w-10 h-10 text-white" />
          </div>

          {/* Text */}
          <h2 className="text-xl font-semibold text-text-primary text-center mb-2">
            从 GitHub 导入
          </h2>
          <p className="text-sm text-text-secondary text-center mb-6">
             输入仓库地址后直接拉取代码；私有仓库可附带 GitHub PAT。
          </p>

          {/* Inputs - wrapped in div to prevent form autofill */}
          <div className="space-y-3" data-form-type="other">
            <input
              type="url"
              name="github-repo-url-input"
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !isCloning && handleGitClone()}
              placeholder="https://github.com/owner/repo"
              disabled={isCloning}
              autoComplete="off"
              data-lpignore="true"
              data-1p-ignore="true"
              data-form-type="other"
              className="
                w-full px-4 py-3
                bg-elevated border border-border-default rounded-xl
                text-text-primary placeholder-text-muted
                focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-all duration-200
              "
            />

            {/* Token input for private repos */}
            <div className="relative">
              <div className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted">
                <Key className="w-4 h-4" />
              </div>
              <input
                type={showToken ? 'text' : 'password'}
                name="github-pat-token-input"
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
                placeholder="GitHub PAT（可选，用于私有仓库）"
                disabled={isCloning}
                autoComplete="new-password"
                data-lpignore="true"
                data-1p-ignore="true"
                data-form-type="other"
                className="
                  w-full pl-10 pr-10 py-3
                  bg-elevated border border-border-default rounded-xl
                  text-text-primary placeholder-text-muted
                  focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-all duration-200
                "
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
              >
                {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>

            <button
              type="button"
              onClick={handleGitClone}
              disabled={isCloning || !githubUrl.trim()}
              className="
                w-full flex items-center justify-center gap-2
                px-4 py-3
                bg-accent hover:bg-accent/90
                text-white font-medium rounded-xl
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-all duration-200
              "
            >
              {isCloning ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  {cloneProgress.phase === 'cloning'
                    ? `正在克隆... ${cloneProgress.percent}%`
                    : cloneProgress.phase === 'reading'
                      ? '正在读取文件...'
                      : '正在启动...'
                  }
                </>
              ) : (
                <>
                  导入仓库
                  <ArrowRight className="w-5 h-5" />
                </>
              )}
            </button>
          </div>

          {/* Progress bar */}
          {isCloning && (
            <div className="mt-4">
              <div className="h-2 bg-elevated rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent transition-all duration-300 ease-out"
                  style={{ width: `${cloneProgress.percent}%` }}
                />
              </div>
            </div>
          )}

          {/* Security note */}
          {githubToken && (
            <p className="mt-3 text-xs text-text-muted text-center">
              令牌仅保存在当前浏览器，不会发送到其他服务器
            </p>
          )}

          {/* Hints */}
          <div className="mt-4 flex items-center justify-center gap-3 text-xs text-text-muted">
            <span className="px-3 py-1.5 bg-elevated border border-border-subtle rounded-md">
                {githubToken ? '私有 / 公开仓库' : '公开仓库'}
            </span>
            <span className="px-3 py-1.5 bg-elevated border border-border-subtle rounded-md">
              浅克隆
            </span>
          </div>
        </div>
      )}

      {/* Local Path Tab */}
      {activeTab === 'path' && (
        <div className="p-8 bg-surface border border-border-default rounded-3xl">
          <div className="mx-auto w-20 h-20 mb-6 flex items-center justify-center bg-gradient-to-br from-indigo-500 to-cyan-600 rounded-2xl shadow-lg">
            <FolderOpen className="w-10 h-10 text-white" />
          </div>

          <h2 className="text-xl font-semibold text-text-primary text-center mb-2">
            {analysisMode === 'experience' ? '训练专属经验库（本地路径）' : '快速代码分析（本地路径）'}
          </h2>
          <p className="text-sm text-text-secondary text-center mb-6">
            {analysisMode === 'experience'
              ? '输入项目绝对路径后，后台会执行主图谱 + 功能层级 + 功能路径的完整训练，耗时较长。'
              : '输入项目绝对路径后优先进入可浏览图谱，经验库训练会继续在后台执行。'}
          </p>

          <div className="space-y-3" data-form-type="other">
            <input
              type="text"
              name="local-project-path-input"
              value={localProjectPath}
              onChange={(e) => setLocalProjectPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !isPathAnalyzing && handleLocalPathAnalyze()}
              placeholder="例如：D:/code/my-project"
              disabled={isPathAnalyzing}
              autoComplete="off"
              data-lpignore="true"
              data-1p-ignore="true"
              data-form-type="other"
              className="
                w-full px-4 py-3
                bg-elevated border border-border-default rounded-xl
                text-text-primary placeholder-text-muted
                focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-all duration-200
              "
            />

            <div className="rounded-xl border border-border-subtle bg-elevated/25 p-3">
              <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-text-muted">
                经验库管理（用户自管）
              </div>
              <div className="mt-2 flex gap-2">
                <input
                  type="text"
                  value={experienceOutputRoot}
                  onChange={(e) => setExperienceOutputRoot(e.target.value)}
                  placeholder="经验库落地目录（绝对路径，留空使用默认 output_analysis）"
                  disabled={isPathAnalyzing}
                  autoComplete="off"
                  className="
                    flex-1 px-4 py-2.5
                    bg-surface border border-border-default rounded-lg
                    text-text-primary placeholder-text-muted
                    focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent
                    disabled:opacity-50 disabled:cursor-not-allowed
                    transition-all duration-200
                  "
                />
                <button
                  type="button"
                  onClick={async () => {
                    const targetPath = experienceOutputRoot.trim();
                    if (!targetPath) {
                      setError('请先填写经验库落地目录，再点击打开文件夹');
                      return;
                    }
                    try {
                      await createGraphExtensionsApi.openFileSystemPath('/api', targetPath);
                    } catch (err) {
                      const message = err instanceof Error ? err.message : '打开经验库文件夹失败';
                      setError(message);
                    }
                  }}
                  disabled={isPathAnalyzing}
                  className="px-3 py-2 text-xs rounded-lg border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-elevated disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  打开文件夹
                </button>
              </div>
              <p className="mt-2 text-[11px] text-text-muted">
                提示：该目录由你自行管理，快速模式与训练模式都可提前配置。
              </p>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleLocalPathAnalyze}
                disabled={isPathAnalyzing || !localProjectPath.trim()}
                className="
                  flex-1 flex items-center justify-center gap-2
                  px-4 py-3
                  bg-accent hover:bg-accent/90
                  text-white font-medium rounded-xl
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-all duration-200
                "
              >
                {isPathAnalyzing ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    {pathProgress.message || '正在分析...'}
                  </>
                ) : (
                  <>
                    {analysisMode === 'experience' ? '开始训练经验库' : '快速进入分析'}
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>

              {isPathAnalyzing && (
                <button
                  type="button"
                  onClick={handleCancelPathAnalyze}
                  className="
                    flex items-center justify-center
                    px-4 py-3
                    bg-red-500/20 hover:bg-red-500/30
                    text-red-400 font-medium rounded-xl
                    transition-all duration-200
                  "
                >
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>
          </div>

          {isPathAnalyzing && (
            <div className="mt-4">
              <div className="h-2 bg-elevated rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent transition-all duration-300 ease-out"
                  style={{ width: `${Math.max(1, Math.min(100, pathProgress.progress || 1))}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-text-muted text-center">
                {pathProgress.message || '正在分析...'} • {Math.max(1, Math.min(100, pathProgress.progress || 1))}%
              </p>
              <p className="mt-1 text-[11px] text-amber-100 text-center">
                {analysisMode === 'experience'
                  ? '经验库训练中，完成后问答/代码生成能力最强。'
                  : '快速模式已启用：若经验库未完成，问答/代码生成效果会偏弱。'}
              </p>
            </div>
          )}


          <div className="mt-4 flex items-center justify-center gap-3 text-xs text-text-muted">
            <span className="px-3 py-1.5 bg-elevated border border-border-subtle rounded-md">
              create_graph 后端
            </span>
            <span className="px-3 py-1.5 bg-elevated border border-border-subtle rounded-md">
              统一分析会话
            </span>
          </div>
        </div>
      )}

      {/* Server Tab */}
      {activeTab === 'server' && (
        <div className="p-8 bg-surface border border-border-default rounded-3xl">
          {/* Icon */}
           <div className="mx-auto w-20 h-20 mb-6 flex items-center justify-center bg-accent rounded-2xl shadow-sm">
            <Globe className="w-10 h-10 text-white" />
          </div>

          {/* Text */}
          <h2 className="text-xl font-semibold text-text-primary text-center mb-2">
            连接到服务
          </h2>
          <p className="text-sm text-text-secondary text-center mb-6">
             从已运行服务加载预构建图谱，适合已有后端索引的场景。
          </p>

          {/* Inputs */}
          <div className="space-y-3" data-form-type="other">
            <input
              type="url"
              name="server-url-input"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !isConnecting && handleServerConnect()}
              placeholder={window.location.origin}
              disabled={isConnecting}
              autoComplete="off"
              data-lpignore="true"
              data-1p-ignore="true"
              data-form-type="other"
              className="
                w-full px-4 py-3
                bg-elevated border border-border-default rounded-xl
                text-text-primary placeholder-text-muted
                focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-all duration-200
              "
            />

            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleServerConnect}
                disabled={isConnecting}
                className="
                  flex-1 flex items-center justify-center gap-2
                  px-4 py-3
                  bg-accent hover:bg-accent/90
                  text-white font-medium rounded-xl
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-all duration-200
                "
              >
                {isConnecting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    {serverProgress.phase === 'validating'
                      ? '正在校验...'
                      : serverProgress.phase === 'downloading'
                        ? serverProgressPercent !== null
                          ? `正在下载... ${serverProgressPercent}%`
                          : `正在下载... ${formatBytes(serverProgress.downloaded)}`
                        : serverProgress.phase === 'extracting'
                          ? '正在处理中...'
                          : '正在连接...'
                    }
                  </>
                ) : (
                  <>
                    连接
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>

              {isConnecting && (
                <button
                  type="button"
                  onClick={handleCancelConnect}
                  className="
                    flex items-center justify-center
                    px-4 py-3
                    bg-red-500/20 hover:bg-red-500/30
                    text-red-400 font-medium rounded-xl
                    transition-all duration-200
                  "
                >
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>
          </div>

          {/* Progress bar */}
          {isConnecting && serverProgress.phase === 'downloading' && (
            <div className="mt-4">
              <div className="h-2 bg-elevated rounded-full overflow-hidden">
                <div
                  className={`h-full bg-accent transition-all duration-300 ease-out ${
                    serverProgressPercent === null ? 'animate-pulse' : ''
                  }`}
                  style={{
                    width: serverProgressPercent !== null
                      ? `${serverProgressPercent}%`
                      : '100%',
                  }}
                />
              </div>
              {serverProgress.total && (
                <p className="mt-1 text-xs text-text-muted text-center">
                  {formatBytes(serverProgress.downloaded)} / {formatBytes(serverProgress.total)}
                </p>
              )}
            </div>
          )}

          {/* Hints */}
          <div className="mt-4 flex items-center justify-center gap-3 text-xs text-text-muted">
            <span className="px-3 py-1.5 bg-elevated border border-border-subtle rounded-md">
              已预建索引
            </span>
            <span className="px-3 py-1.5 bg-elevated border border-border-subtle rounded-md">
              无需 WASM
            </span>
          </div>
        </div>
      )}
      </div>
    </div>
  </div>
); };
