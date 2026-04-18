import { ArrowLeft, BookOpen, ChevronDown, HelpCircle, Layers, RefreshCw, Search, Settings, Sparkles } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { GraphNode } from '../core/graph/types';
import { useAppState } from '../hooks/useAppState';
import { createGraphExtensionsApi, type CreateGraphWorkbenchProjectStatusResponse } from '../services/create-graph-extensions';
import type { RepoSummary } from '../services/server-connection';
import { EmbeddingStatus } from './EmbeddingStatus';

// Color mapping for node types in search results
const NODE_TYPE_COLORS: Record<string, string> = {
  Folder: '#6366f1',
  File: '#3b82f6',
  Function: '#10b981',
  Class: '#f59e0b',
  Method: '#14b8a6',
  Interface: '#ec4899',
  Variable: '#64748b',
  Import: '#475569',
  Type: '#a78bfa',
};

interface HeaderProps {
  onFocusNode?: (nodeId: string) => void;
  availableRepos?: RepoSummary[];
  onSwitchRepo?: (repoName: string) => void;
}

export const Header = ({ onFocusNode, availableRepos = [], onSwitchRepo }: HeaderProps) => {
  const {
    projectName,
    graph,
    openChatPanel,
    openHierarchyPanel,
    openExperiencePanel,
    isRightPanelOpen,
    rightPanelTab,
    setSettingsPanelOpen,
    returnToOnboarding,
  } = useAppState();
  const [hierarchyStatus, setHierarchyStatus] = useState<'checking' | 'ready' | 'missing' | 'error'>('checking');
  const [hierarchyStatusMessage, setHierarchyStatusMessage] = useState('正在检查层级...');
  const [experienceStatus, setExperienceStatus] = useState<CreateGraphWorkbenchProjectStatusResponse | null>(null);
  const [isRepoDropdownOpen, setIsRepoDropdownOpen] = useState(false);
  const repoDropdownRef = useRef<HTMLDivElement>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const nodeCount = graph?.nodes.length ?? 0;
  const edgeCount = graph?.relationships.length ?? 0;
  const activeProjectPath = useMemo(() => {
    if (availableRepos.length === 0) return undefined;
    const matchedPath = projectName
      ? availableRepos.find((repo) => repo.name === projectName)?.path
      : undefined;
    if (matchedPath) return matchedPath;
    if (availableRepos.length === 1) return availableRepos[0].path;
    return undefined;
  }, [availableRepos, projectName]);

  const refreshHierarchyStatus = useCallback(async () => {
    if (!projectName) {
      setHierarchyStatus('missing');
      setHierarchyStatusMessage('未加载项目');
      return;
    }

    if (!activeProjectPath) {
      setHierarchyStatus('checking');
      setHierarchyStatusMessage('正在解析项目路径...');
      return;
    }

    setHierarchyStatus('checking');
    setHierarchyStatusMessage('正在检查层级...');

    try {
      const payload = await createGraphExtensionsApi.fetchHierarchyContract('/api', activeProjectPath);
      const summaries = Array.isArray(payload.adapters?.partition_summaries) ? payload.adapters?.partition_summaries : [];
      if (summaries.length > 0) {
        setHierarchyStatus('ready');
        setHierarchyStatusMessage(`层级已就绪（${summaries.length} 个分区）`);
      } else {
        setHierarchyStatus('missing');
        setHierarchyStatusMessage('层级结果为空');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('未找到可用于 Stage1 读契约的功能层级结果') || message.toLowerCase().includes('404')) {
        setHierarchyStatus('missing');
        setHierarchyStatusMessage('尚未生成层级');
      } else {
        setHierarchyStatus('error');
        setHierarchyStatusMessage(message);
      }
    }
  }, [activeProjectPath, projectName]);

  useEffect(() => {
    refreshHierarchyStatus();
  }, [refreshHierarchyStatus]);

  useEffect(() => {
    if (!activeProjectPath) {
      setExperienceStatus(null);
      return;
    }

    let cancelled = false;
    const syncStatus = async () => {
      try {
        const payload = await createGraphExtensionsApi.fetchWorkbenchProjectStatus('/api', activeProjectPath);
        if (!cancelled) {
          setExperienceStatus(payload);
        }
      } catch {
        if (!cancelled) {
          setExperienceStatus(null);
        }
      }
    };

    syncStatus();
    const timer = window.setInterval(syncStatus, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeProjectPath]);

  // Search results - filter nodes by name
  const searchResults = useMemo(() => {
    if (!graph || !searchQuery.trim()) return [];

    const query = searchQuery.toLowerCase();
    return graph.nodes
      .filter(node => node.properties.name.toLowerCase().includes(query))
      .slice(0, 10); // Limit to 10 results
  }, [graph, searchQuery]);

  // Handle clicking outside to close dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setIsSearchOpen(false);
      }
      if (repoDropdownRef.current && !repoDropdownRef.current.contains(e.target as Node)) {
        setIsRepoDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Keyboard shortcut (Cmd+K / Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setIsSearchOpen(true);
      }
      if (e.key === 'Escape') {
        setIsSearchOpen(false);
        inputRef.current?.blur();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Handle keyboard navigation in results
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isSearchOpen || searchResults.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(i => Math.min(i + 1, searchResults.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const selected = searchResults[selectedIndex];
      if (selected) {
        handleSelectNode(selected);
      }
    }
  };

  const handleSelectNode = (node: GraphNode) => {
    // onFocusNode handles both camera focus AND selection in useSigma
    onFocusNode?.(node.id);
    setSearchQuery('');
    setIsSearchOpen(false);
    setSelectedIndex(0);
  };

  return (
    <header className="flex items-center justify-between px-5 py-3 bg-deep border-b border-dashed border-border-subtle">
      {/* Left section */}
      <div className="flex items-center gap-4">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 flex items-center justify-center bg-gradient-to-br from-accent to-node-interface rounded-md shadow-glow text-white text-sm font-bold">
            ◇
          </div>
          <span className="font-semibold text-[15px] tracking-tight">create_graph</span>
        </div>

        {/* Project badge / Repo selector dropdown */}
        {projectName && (
          <div className="relative" ref={repoDropdownRef}>
            <button
              type="button"
              onClick={() => availableRepos.length >= 2 && setIsRepoDropdownOpen(prev => !prev)}
              className={`flex items-center gap-2 px-3 py-1.5 bg-surface border border-border-subtle rounded-lg text-sm text-text-secondary transition-colors ${availableRepos.length >= 2 ? 'hover:bg-hover cursor-pointer' : ''}`}
            >
              <span className="w-1.5 h-1.5 bg-node-function rounded-full animate-pulse" />
              <span className="truncate max-w-[200px]">{projectName}</span>
              {availableRepos.length >= 2 && (
                <ChevronDown className={`w-3.5 h-3.5 text-text-muted transition-transform ${isRepoDropdownOpen ? 'rotate-180' : ''}`} />
              )}
            </button>

            {/* Repo dropdown */}
            {isRepoDropdownOpen && availableRepos.length >= 2 && (
              <div className="absolute top-full left-0 mt-1 w-72 bg-surface border border-border-subtle rounded-lg shadow-xl overflow-hidden z-50">
                {availableRepos.map((repo) => {
                  const isCurrent = repo.name === projectName;
                  return (
                    <button
                      key={repo.name}
                      type="button"
                      onClick={() => {
                        if (!isCurrent && onSwitchRepo) {
                          onSwitchRepo(repo.name);
                        }
                        setIsRepoDropdownOpen(false);
                      }}
                      className={`w-full px-4 py-3 flex items-center gap-3 text-left transition-colors ${isCurrent ? 'bg-accent/10 border-l-2 border-accent' : 'hover:bg-hover border-l-2 border-transparent'}`}
                    >
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${isCurrent ? 'bg-node-function animate-pulse' : 'bg-text-muted'}`} />
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-medium truncate ${isCurrent ? 'text-accent' : 'text-text-primary'}`}>
                          {repo.name}
                        </div>
                        <div className="text-xs text-text-muted mt-0.5">
                          {repo.stats?.nodes ?? '?'} 节点 &middot; {repo.stats?.files ?? '?'} 文件
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Center - Search */}
      <div className="flex-1 max-w-md mx-6 relative" ref={searchRef}>
        <div className="flex items-center gap-2.5 px-3.5 py-2 bg-surface border border-border-subtle rounded-lg transition-all focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
          <Search className="w-4 h-4 text-text-muted flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            placeholder="搜索节点..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setIsSearchOpen(true);
              setSelectedIndex(0);
            }}
            onFocus={() => setIsSearchOpen(true)}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent border-none outline-none text-sm text-text-primary placeholder:text-text-muted"
          />
          <kbd className="px-1.5 py-0.5 bg-elevated border border-border-subtle rounded text-[10px] text-text-muted font-mono">
            ⌘K
          </kbd>
        </div>

        {/* Search Results Dropdown */}
        {isSearchOpen && searchQuery.trim() && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-surface border border-border-subtle rounded-lg shadow-xl overflow-hidden z-50">
            {searchResults.length === 0 ? (
              <div className="px-4 py-3 text-sm text-text-muted">
                未找到“{searchQuery}”相关节点
              </div>
            ) : (
              <div className="max-h-80 overflow-y-auto">
                {searchResults.map((node, index) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => handleSelectNode(node)}
                    className={`w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors ${index === selectedIndex
                      ? 'bg-accent/20 text-text-primary'
                      : 'hover:bg-hover text-text-secondary'
                      }`}
                  >
                    {/* Node type indicator */}
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: NODE_TYPE_COLORS[node.label] || '#6b7280' }}
                    />
                    {/* Node name */}
                    <span className="flex-1 truncate text-sm font-medium">
                      {node.properties.name}
                    </span>
                    {/* Node type badge */}
                    <span className="text-xs text-text-muted px-2 py-0.5 bg-elevated rounded">
                      {node.label}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right section */}
      <div className="flex items-center gap-2">
        {/* Stats */}
        {graph && (
          <div className="flex items-center gap-4 mr-2 text-xs text-text-muted">
            <span>{nodeCount} 节点</span>
            <span>{edgeCount} 连线</span>
          </div>
        )}

        {/* Embedding Status */}
        <EmbeddingStatus />

        {experienceStatus && (
          <div className="hidden xl:flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-amber-300/30 bg-amber-200/10 max-w-[360px]">
            <div className="min-w-0">
              <div className="text-[11px] text-amber-100 truncate">
                经验库 {Math.max(0, Math.min(100, Number(experienceStatus.progress || 0)))}% · {experienceStatus.phase}
              </div>
              <div className="text-[10px] text-text-muted truncate">{experienceStatus.qualityHint}</div>
            </div>
            <div className="w-20 h-1.5 rounded-full bg-elevated overflow-hidden">
              <div
                className="h-full bg-amber-300 transition-all duration-300"
                style={{ width: `${Math.max(0, Math.min(100, Number(experienceStatus.progress || 0)))}%` }}
              />
            </div>
          </div>
        )}

        {/* Icon buttons */}
        <button
          type="button"
          onClick={() => returnToOnboarding('path')}
          className="hidden lg:flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium bg-surface border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-hover transition-colors"
          title="返回入口并重新选择项目/经验库"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>返回入口</span>
        </button>
        <button
          type="button"
          onClick={() => setSettingsPanelOpen(true)}
          className="w-9 h-9 flex items-center justify-center rounded-md text-text-secondary hover:bg-hover hover:text-text-primary transition-colors"
          title="AI 设置"
        >
          <Settings className="w-[18px] h-[18px]" />
        </button>
        <button type="button" className="w-9 h-9 flex items-center justify-center rounded-md text-text-secondary hover:bg-hover hover:text-text-primary transition-colors">
          <HelpCircle className="w-[18px] h-[18px]" />
        </button>

        {/* AI Button */}
        <button
          type="button"
          onClick={openHierarchyPanel}
          className={`
            flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all border
            ${isRightPanelOpen && rightPanelTab === 'hierarchy'
              ? 'bg-cyan-500/20 border-cyan-400/40 text-cyan-200 shadow-[0_0_0_1px_rgba(34,211,238,0.35)]'
              : 'bg-surface border-border-subtle text-text-secondary hover:text-text-primary hover:bg-hover'
            }
          `}
          title={hierarchyStatusMessage}
        >
          <Layers className="w-4 h-4" />
          <span>层级</span>
          <span
            className={`w-2 h-2 rounded-full ${hierarchyStatus === 'ready'
              ? 'bg-emerald-400'
              : hierarchyStatus === 'checking'
                ? 'bg-amber-300 animate-pulse'
                : hierarchyStatus === 'missing'
                  ? 'bg-orange-400'
                  : 'bg-rose-400'
              }`}
          />
        </button>
        <button
          type="button"
          onClick={refreshHierarchyStatus}
          className="w-8 h-8 flex items-center justify-center rounded-md text-text-muted hover:text-text-primary hover:bg-hover transition-colors"
          title="刷新层级状态"
        >
          <RefreshCw className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={openExperiencePanel}
          className={`
            flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all border
            ${isRightPanelOpen && rightPanelTab === 'experience'
              ? 'bg-amber-500/20 border-amber-400/40 text-amber-100 shadow-[0_0_0_1px_rgba(251,191,36,0.25)]'
              : 'bg-surface border-border-subtle text-text-secondary hover:text-text-primary hover:bg-hover'
            }
          `}
          title="打开经验库管理器"
        >
          <BookOpen className="w-4 h-4" />
          <span>经验库</span>
        </button>

        <button
          type="button"
          onClick={openChatPanel}
          className={`
            flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium transition-all
            ${isRightPanelOpen && rightPanelTab === 'chat'
              ? 'bg-accent text-white shadow-glow'
              : 'bg-gradient-to-r from-accent to-accent-dim text-white shadow-glow hover:shadow-lg hover:-translate-y-0.5'
            }
          `}
        >
          <Sparkles className="w-4 h-4" />
          <span>AI 助手</span>
        </button>
      </div>
    </header>
  );
};
