import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { PanelLeftClose, PanelLeft, Trash2, X, Target, FileCode, Sparkles } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useAppState } from '../hooks/useAppState';
import { NODE_COLORS } from '../lib/constants';
import { createGraphExtensionsApi, type CreateGraphNodeDetailResponse } from '../services/create-graph-extensions';
import { GraphVizBlock } from './GraphVizBlock';

// Match the code theme used elsewhere in the app
const customTheme: Record<string, CSSProperties> = {
  ...vscDarkPlus,
  'pre[class*="language-"]': {
    ...vscDarkPlus['pre[class*="language-"]'],
    background: '#0a0a10',
    margin: 0,
    padding: '12px 0',
    fontSize: '13px',
    lineHeight: '1.6',
  },
  'code[class*="language-"]': {
    ...vscDarkPlus['code[class*="language-"]'],
    background: 'transparent',
    fontFamily: '"JetBrains Mono", "Fira Code", monospace',
  },
};

export interface CodeReferencesPanelProps {
  onFocusNode: (nodeId: string) => void;
}

type DetailTabKey = 'snippet' | 'properties' | 'cfg' | 'dfg' | 'io';

type DetailTab = {
  key: DetailTabKey;
  label: string;
};

const ENTITY_TYPE_TEXT: Record<string, string> = {
  class: '类',
  function: '函数',
  method: '方法',
  '函数/方法': '函数/方法',
  variable: '变量',
  interface: '接口',
  file: '文件',
};

const getEntityTypeText = (kind?: string, fallbackLabel?: string): string => {
  const normalizedKind = String(kind || '').trim().toLowerCase();
  if (normalizedKind === 'function' || normalizedKind === 'method') return '函数/方法';
  if (normalizedKind && ENTITY_TYPE_TEXT[normalizedKind]) return ENTITY_TYPE_TEXT[normalizedKind];
  if (fallbackLabel === 'Function' || fallbackLabel === 'Method') return '函数/方法';
  if (fallbackLabel === 'Class') return '类';
  if (fallbackLabel === 'Variable') return '变量';
  if (fallbackLabel === 'Interface') return '接口';
  return kind || fallbackLabel || '未知类型';
};

const isFunctionLikeNode = (kind?: string, fallbackLabel?: string): boolean => {
  const normalizedKind = String(kind || '').trim().toLowerCase();
  if (normalizedKind === 'function' || normalizedKind === 'method') return true;
  return fallbackLabel === 'Function' || fallbackLabel === 'Method';
};

const formatPropertyValue = (value: unknown): string => {
  if (value === null || value === undefined) return '暂无';
  if (Array.isArray(value)) return value.length > 0 ? value.join('、') : '暂无';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return String(value);
};

export const CodeReferencesPanel = ({ onFocusNode }: CodeReferencesPanelProps) => {
  const {
    graph,
    fileContents,
    projectName,
    availableRepos,
    selectedNode,
    codeReferences,
    removeCodeReference,
    clearCodeReferences,
    setSelectedNode,
    codeReferenceFocus,
  } = useAppState();

  const [isCollapsed, setIsCollapsed] = useState(false);
  const [glowRefId, setGlowRefId] = useState<string | null>(null);
  const [nodeDetail, setNodeDetail] = useState<CreateGraphNodeDetailResponse | null>(null);
  const [nodeDetailLoading, setNodeDetailLoading] = useState(false);
  const [nodeDetailError, setNodeDetailError] = useState<string | null>(null);
  const [activeDetailTab, setActiveDetailTab] = useState<DetailTabKey>('snippet');
  const panelRef = useRef<HTMLElement | null>(null);
  const resizeRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const refCardEls = useRef<Map<string, HTMLDivElement | null>>(new Map());
  const glowTimerRef = useRef<number | null>(null);

  const activeProjectPath = useMemo(() => {
    if (availableRepos.length === 0) return undefined;
    const matchedPath = projectName
      ? availableRepos.find((repo) => repo.name === projectName)?.path
      : undefined;
    if (matchedPath) return matchedPath;
    if (availableRepos.length === 1) return availableRepos[0].path;
    return undefined;
  }, [availableRepos, projectName]);

  useEffect(() => {
    return () => {
      if (glowTimerRef.current) {
        window.clearTimeout(glowTimerRef.current);
        glowTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    if (!selectedNode) {
      setNodeDetail(null);
      setNodeDetailError(null);
      setNodeDetailLoading(false);
      return;
    }

    setNodeDetailLoading(true);
    setNodeDetailError(null);

    createGraphExtensionsApi
      .fetchNodeDetail('/api', selectedNode.id, activeProjectPath)
      .then((payload) => {
        if (cancelled) return;
        setNodeDetail(payload);
      })
      .catch((error) => {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : String(error);
        setNodeDetail(null);
        setNodeDetailError(message);
      })
      .finally(() => {
        if (cancelled) return;
        setNodeDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeProjectPath, selectedNode]);

  const [panelWidth, setPanelWidth] = useState<number>(() => {
    try {
      const saved = window.localStorage.getItem('create-graph.codePanelWidth');
      const parsed = saved ? parseInt(saved, 10) : NaN;
      if (!Number.isFinite(parsed)) return 560; // increased default
      return Math.max(420, Math.min(parsed, 900));
    } catch {
      return 560;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem('create-graph.codePanelWidth', String(panelWidth));
    } catch {
      // ignore
    }
  }, [panelWidth]);

  const startResize = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    resizeRef.current = { startX: e.clientX, startWidth: panelWidth };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const onMove = (ev: MouseEvent) => {
      const state = resizeRef.current;
      if (!state) return;
      const delta = ev.clientX - state.startX;
      const next = Math.max(420, Math.min(state.startWidth + delta, 900));
      setPanelWidth(next);
    };

    const onUp = () => {
      resizeRef.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [panelWidth]);

  const aiReferences = useMemo(() => codeReferences.filter(r => r.source === 'ai'), [codeReferences]);

  // When the user clicks a citation badge in chat, focus the corresponding snippet card:
  // - expand the panel if collapsed
  // - smooth-scroll the card into view
  // - briefly glow it for discoverability
  useEffect(() => {
    if (!codeReferenceFocus) return;

    // Ensure panel is expanded
    setIsCollapsed(false);

    const { filePath, startLine, endLine } = codeReferenceFocus;
    const target =
      aiReferences.find(r =>
        r.filePath === filePath &&
        r.startLine === startLine &&
        r.endLine === endLine
      ) ??
      aiReferences.find(r => r.filePath === filePath);

    if (!target) return;

    // Double rAF: wait for collapse state + list DOM to render.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = refCardEls.current.get(target.id);
        if (!el) return;

        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setGlowRefId(target.id);

        if (glowTimerRef.current) {
          window.clearTimeout(glowTimerRef.current);
        }
        glowTimerRef.current = window.setTimeout(() => {
          setGlowRefId((prev) => (prev === target.id ? null : prev));
          glowTimerRef.current = null;
        }, 1200);
      });
    });
  }, [codeReferenceFocus, aiReferences]);

  const refsWithSnippets = useMemo(() => {
    return aiReferences.map((ref) => {
      const content = fileContents.get(ref.filePath);
      if (!content) {
        return { ref, content: null as string | null, start: 0, end: 0, highlightStart: 0, highlightEnd: 0, totalLines: 0 };
      }

      const lines = content.split('\n');
      const totalLines = lines.length;

      const startLine = ref.startLine ?? 0;
      const endLine = ref.endLine ?? startLine;

      const contextBefore = 3;
      const contextAfter = 20;
      const start = Math.max(0, startLine - contextBefore);
      const end = Math.min(totalLines - 1, endLine + contextAfter);

      return {
        ref,
        content: lines.slice(start, end + 1).join('\n'),
        start,
        end,
        highlightStart: Math.max(0, startLine - start),
        highlightEnd: Math.max(0, endLine - start),
        totalLines,
      };
    });
  }, [aiReferences, fileContents]);

  const selectedFilePath = selectedNode?.properties?.filePath;
  const showSelectedViewer = !!selectedNode;
  const showCitations = aiReferences.length > 0;
  const detailLanguage =
    nodeDetail?.source?.language ||
    (selectedFilePath?.endsWith('.py') ? 'python' :
      selectedFilePath?.endsWith('.js') || selectedFilePath?.endsWith('.jsx') ? 'javascript' :
        selectedFilePath?.endsWith('.ts') || selectedFilePath?.endsWith('.tsx') ? 'typescript' :
          'text');

  const resolvedAbsolutePath = nodeDetail?.source?.file_path
    || nodeDetail?.file_path
    || selectedNode?.properties?.filePath
    || '';

  const propertyItems = useMemo(() => {
    if (!selectedNode) return [] as Array<{ label: string; value: string }>;
    const props = selectedNode.properties;
    const detailProps = (nodeDetail?.properties && typeof nodeDetail.properties === 'object')
      ? nodeDetail.properties as Record<string, unknown>
      : {};
    const rows: Array<{ label: string; value: string }> = [];
    const pushIfPresent = (label: string, value: unknown, predicate?: boolean) => {
      if (predicate === false) return;
      if (value === undefined || value === null) return;
      if (Array.isArray(value) && value.length === 0) return;
      if (typeof value === 'string' && value.trim() === '') return;
      rows.push({ label, value: formatPropertyValue(value) });
    };

    pushIfPresent('语言', props.language);
    pushIfPresent('起始行', typeof props.startLine === 'number' ? props.startLine + 1 : undefined);
    pushIfPresent('结束行', typeof props.endLine === 'number' ? props.endLine + 1 : undefined);
    pushIfPresent('是否导出', props.isExported, typeof props.isExported === 'boolean');
    pushIfPresent('启发式标签', props.heuristicLabel);
    pushIfPresent('内聚度', props.cohesion);
    pushIfPresent('符号数量', props.symbolCount);
    pushIfPresent('关键词', props.keywords);
    pushIfPresent('描述', props.description);
    pushIfPresent('增强来源', props.enrichedBy);
    pushIfPresent('流程类型', props.processType);
    pushIfPresent('步骤数', props.stepCount);
    pushIfPresent('关联社区', props.communities);
    pushIfPresent('入口点 ID', props.entryPointId);
    pushIfPresent('终点 ID', props.terminalId);
    pushIfPresent('入口评分', props.entryPointScore);
    pushIfPresent('入口原因', props.entryPointReason);

    Object.entries(detailProps).forEach(([key, value]) => {
      if (['owner', 'owner_method', 'owner_function', 'signature', 'return_type', 'class_name', 'variable_kind', 'owner_kind', 'owner_signature', 'owner_parameters', 'modifiers', 'decorators', 'parent_class', 'interfaces', 'docstring', 'method_names', 'fields', 'source'].includes(key)) {
        const labelMap: Record<string, string> = {
          owner: '所属对象',
          owner_method: '所属方法',
          owner_function: '所属函数',
          signature: '签名',
          return_type: '返回类型',
          class_name: '所属类',
          variable_kind: '变量类型',
          owner_kind: '所属对象类型',
          owner_signature: '所属对象签名',
          owner_parameters: '所属对象参数',
          modifiers: '修饰符',
          decorators: '装饰器',
          parent_class: '父类',
          interfaces: '接口',
          docstring: '说明',
          method_names: '方法列表',
          fields: '字段列表',
          source: '来源',
        };
        pushIfPresent(labelMap[key] || key, value);
      }
    });
    return rows;
  }, [nodeDetail?.properties, selectedNode]);

  const variablePropertyItems = useMemo(() => {
    if (selectedNode?.label !== 'Variable') return [] as Array<{ label: string; value: string }>;
    const detailProps = (nodeDetail?.properties && typeof nodeDetail.properties === 'object')
      ? nodeDetail.properties as Record<string, unknown>
      : {};
    return [
      { label: '变量名', value: selectedNode.properties.name || nodeDetail?.display_name || '暂无' },
      { label: '变量类别', value: formatPropertyValue(detailProps.variable_kind || '暂无') },
      { label: '所属函数/方法', value: formatPropertyValue(detailProps.owner || detailProps.owner_method || detailProps.owner_function || '暂无') },
      { label: '所属函数签名', value: formatPropertyValue(detailProps.owner_signature || detailProps.signature || '暂无') },
      { label: '文件绝对路径', value: resolvedAbsolutePath || '暂无绝对路径' },
      {
        label: '行号',
        value: nodeDetail?.line_start
          ? `${nodeDetail.line_start}${nodeDetail.line_end && nodeDetail.line_end !== nodeDetail.line_start ? ` - ${nodeDetail.line_end}` : ''}`
          : '暂无',
      },
    ];
  }, [nodeDetail, resolvedAbsolutePath, selectedNode]);

  const supportsPropertiesTab = selectedNode?.label === 'Class'
    || selectedNode?.label === 'Variable'
    || selectedNode?.label === 'Interface'
    || propertyItems.length > 0;

  const isFunctionLikeDetail = useMemo(
    () => isFunctionLikeNode(nodeDetail?.kind, selectedNode?.label),
    [nodeDetail?.kind, selectedNode?.label]
  );

  const hasIoData = useMemo(() => {
    const io = nodeDetail?.io;
    if (!io) return false;
    return Boolean(
      (io.inputs && io.inputs.length > 0)
      || (io.outputs && io.outputs.length > 0)
      || (io.global_reads && io.global_reads.length > 0)
      || (io.global_writes && io.global_writes.length > 0)
    );
  }, [nodeDetail]);

  const availableDetailTabs = useMemo<DetailTab[]>(() => {
    const tabs: DetailTab[] = [];
    if (isFunctionLikeDetail) {
      tabs.push({ key: 'snippet', label: '源码片段' });
      tabs.push({ key: 'cfg', label: '控制流图' });
      tabs.push({ key: 'dfg', label: '数据流图' });
      tabs.push({ key: 'io', label: '输入输出' });
      return tabs;
    }

    if (nodeDetail?.source?.snippet) tabs.push({ key: 'snippet', label: '源码片段' });
    if (supportsPropertiesTab) tabs.push({ key: 'properties', label: '属性信息' });
    if (nodeDetail?.cfg) tabs.push({ key: 'cfg', label: '控制流图' });
    if (nodeDetail?.dfg) tabs.push({ key: 'dfg', label: '数据流图' });
    if (hasIoData) tabs.push({ key: 'io', label: '输入输出' });
    return tabs;
  }, [hasIoData, isFunctionLikeDetail, nodeDetail, supportsPropertiesTab]);

  const firstAvailableDetailTab = availableDetailTabs[0]?.key;

  useEffect(() => {
    setActiveDetailTab(firstAvailableDetailTab || 'snippet');
  }, [firstAvailableDetailTab]);

  useEffect(() => {
    if (!firstAvailableDetailTab) {
      setActiveDetailTab('snippet');
      return;
    }
    setActiveDetailTab((prev) => (availableDetailTabs.some((tab) => tab.key === prev) ? prev : firstAvailableDetailTab));
  }, [availableDetailTabs, firstAvailableDetailTab]);

  if (isCollapsed) {
    return (
      <aside className="h-full w-12 bg-surface border-r border-border-subtle flex flex-col items-center py-3 gap-2 flex-shrink-0">
        <button
          type="button"
          onClick={() => setIsCollapsed(false)}
          className="p-2 text-text-secondary hover:text-cyan-400 hover:bg-cyan-500/10 rounded transition-colors"
          title="展开代码面板"
        >
          <PanelLeft className="w-5 h-5" />
        </button>
        <div className="w-6 h-px bg-border-subtle my-1" />
        {showSelectedViewer && (
          <div className="text-[9px] text-amber-400 rotate-90 whitespace-nowrap font-medium tracking-wide">
            当前节点
          </div>
        )}
        {showCitations && (
          <div className="text-[9px] text-cyan-400 rotate-90 whitespace-nowrap font-medium tracking-wide mt-4">
            AI 引用 · {aiReferences.length}
          </div>
        )}
      </aside>
    );
  }

  return (
    <aside
      ref={(el) => { panelRef.current = el; }}
      className="h-full bg-surface/95 backdrop-blur-md border-r border-border-subtle flex flex-col animate-slide-in relative shadow-2xl"
      style={{ width: panelWidth }}
    >
      {/* Resize handle */}
      <button
        type="button"
        onMouseDown={startResize}
        className="absolute top-0 right-0 h-full w-2 cursor-col-resize bg-transparent hover:bg-cyan-500/25 transition-colors"
         title="拖动调整宽度"
         aria-label="调整代码面板宽度"
      />
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-border-subtle bg-gradient-to-r from-elevated/60 to-surface/60">
        <div className="flex items-center gap-2">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-text-primary">
              {selectedNode?.properties?.name || nodeDetail?.display_name || '节点详情'}
            </div>
            {showSelectedViewer && (
              <div className="mt-1 space-y-1 text-[11px] text-text-secondary">
                <div>
                  <span className="text-text-muted">实体类型：</span>
                  <span className="text-text-primary">{getEntityTypeText(nodeDetail?.kind, selectedNode?.label)}</span>
                </div>
                <div className="whitespace-normal break-all leading-5 text-text-primary/90 font-mono">
                  <span className="text-text-muted font-sans">绝对路径：</span>{resolvedAbsolutePath || '暂无绝对路径'}
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {showCitations && (
            <button
              type="button"
              onClick={() => clearCodeReferences()}
              className="p-1.5 text-text-muted hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
               title="清空 AI 引用"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setIsCollapsed(true)}
            className="p-1.5 text-text-muted hover:text-text-primary hover:bg-hover rounded transition-colors"
             title="收起面板"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        {/* Top: Selected file viewer (when a node is selected) */}
        {showSelectedViewer && (
          <div className={`${showCitations ? 'h-[48%]' : 'flex-1'} min-h-0 flex flex-col`}>
            <div className="px-3 py-2 bg-gradient-to-r from-amber-500/8 to-orange-500/5 border-b border-amber-500/20 flex items-start gap-2">
              <FileCode className="w-3.5 h-3.5 text-amber-400/70 mt-0.5" />
              <div className="min-w-0 flex-1 space-y-1">
                <div className="text-sm font-medium text-text-primary break-all">
                  {nodeDetail?.display_name || selectedNode?.properties?.name || selectedNode?.id}
                </div>
                <div className="text-[11px] text-text-secondary">
                  实体类型：<span className="text-text-primary">{getEntityTypeText(nodeDetail?.kind, selectedNode?.label)}</span>
                </div>
                <div className="text-[11px] text-text-secondary whitespace-normal break-all leading-5 font-mono">
                  {resolvedAbsolutePath || '暂无绝对路径'}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedNode(null)}
                className="p-1 text-text-muted hover:text-amber-400 hover:bg-amber-500/10 rounded transition-colors"
                title="清除选择"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Node Deep Analysis — independently scrollable section */}
            {(nodeDetailLoading || nodeDetailError || nodeDetail || supportsPropertiesTab) && (
              <div className="flex-1 min-h-0 flex flex-col border-b border-border-subtle bg-elevated/40">
                {availableDetailTabs.length > 0 && (
                  <div className="px-3 py-2 border-b border-border-subtle flex flex-wrap gap-2">
                    {availableDetailTabs.map((tab) => (
                      <button
                        key={tab.key}
                        type="button"
                        onClick={() => setActiveDetailTab(tab.key)}
                        className={[
                          'px-2.5 py-1 text-xs rounded-md border transition-colors',
                          activeDetailTab === tab.key
                            ? 'border-cyan-400/60 text-cyan-200 bg-cyan-500/15'
                            : 'border-border-subtle text-text-secondary hover:text-text-primary hover:bg-hover',
                        ].join(' ')}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                )}

                <div className="min-h-0 overflow-y-auto scrollbar-thin">
                  {nodeDetailLoading && (
                     <div className="px-3 py-3 text-xs text-text-muted">正在加载节点详情…</div>
                  )}

                  {nodeDetailError && (
                    <div className="px-3 py-3 text-xs text-rose-300">{nodeDetailError}</div>
                  )}

                  {!nodeDetailLoading && !nodeDetailError && (
                    <div className="px-3 py-3 space-y-2">
                      {activeDetailTab === 'snippet' && (
                        nodeDetail?.source?.snippet ? (
                          <div className="rounded-lg border border-border-subtle overflow-hidden">
                            <SyntaxHighlighter
                              language={detailLanguage}
                              style={customTheme}
                              showLineNumbers
                              startingLineNumber={(nodeDetail.source.line_start ?? nodeDetail.line_start ?? 1)}
                              lineNumberStyle={{
                                minWidth: '3em',
                                paddingRight: '1em',
                                color: '#5a5a70',
                                textAlign: 'right',
                                userSelect: 'none',
                              }}
                              wrapLines
                            >
                              {nodeDetail.source.snippet}
                            </SyntaxHighlighter>
                          </div>
                        ) : isFunctionLikeDetail ? (
                          <div className="rounded border border-border-subtle bg-surface/40 p-3 text-[11px] text-text-muted">
                            当前函数暂无源码片段。
                          </div>
                        ) : null
                      )}

                      {activeDetailTab === 'properties' && (
                        <div className="rounded-lg border border-border-subtle overflow-hidden">
                          <div className="px-3 py-3 space-y-2 text-[12px] text-text-secondary">
                            {(selectedNode?.label === 'Variable' ? variablePropertyItems : propertyItems).length > 0 ? (selectedNode?.label === 'Variable' ? variablePropertyItems : propertyItems).map((item) => (
                              <div key={item.label} className="grid grid-cols-[100px_minmax(0,1fr)] gap-3 items-start">
                                <span className="text-text-muted">{item.label}</span>
                                <span className="text-text-primary whitespace-pre-wrap break-all">{item.value}</span>
                              </div>
                            )) : (
                              <div className="text-text-muted">当前节点暂无额外属性信息。</div>
                            )}
                          </div>
                        </div>
                      )}

                      {activeDetailTab === 'cfg' && (
                        nodeDetail?.cfg ? (
                          <GraphVizBlock dotString={nodeDetail.cfg} color="violet" />
                        ) : (
                          <div className="rounded border border-border-subtle bg-surface/40 p-3 text-[11px] text-text-muted">
                            当前节点暂无 CFG。
                          </div>
                        )
                      )}

                      {activeDetailTab === 'dfg' && (
                        nodeDetail?.dfg ? (
                          <GraphVizBlock dotString={nodeDetail.dfg} color="fuchsia" />
                        ) : (
                          <div className="rounded border border-border-subtle bg-surface/40 p-3 text-[11px] text-text-muted">
                            当前节点暂无 DFG。
                          </div>
                        )
                      )}

                      {activeDetailTab === 'io' && (
                        hasIoData && nodeDetail?.io ? (
                          <div className="rounded-lg border border-border-subtle overflow-hidden">
                            <div className="px-3 py-2 space-y-1 text-[11px] text-text-secondary">
                              <div>
                                <span className="text-emerald-300">输入：</span>{' '}
                                <span>{JSON.stringify(nodeDetail.io.inputs ?? [])}</span>
                              </div>
                              <div>
                                <span className="text-emerald-300">输出：</span>{' '}
                                <span>{JSON.stringify(nodeDetail.io.outputs ?? [])}</span>
                              </div>
                              <div>
                                <span className="text-emerald-300">全局读取：</span>{' '}
                                <span>{JSON.stringify(nodeDetail.io.global_reads ?? [])}</span>
                              </div>
                              <div>
                                <span className="text-emerald-300">全局写入：</span>{' '}
                                <span>{JSON.stringify(nodeDetail.io.global_writes ?? [])}</span>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="rounded border border-border-subtle bg-surface/40 p-3 text-[11px] text-text-muted">
                            当前节点暂无输入输出信息。
                          </div>
                        )
                      )}

                      {!nodeDetailLoading && !nodeDetailError && availableDetailTabs.length === 0 && (
                        <div className="text-sm text-text-muted">当前节点暂无可展示的详细内容。</div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Divider between Selected viewer and AI refs (more visible) */}
        {showSelectedViewer && showCitations && (
          <div className="h-1.5 bg-gradient-to-r from-transparent via-border-subtle to-transparent" />
        )}

        {/* Bottom: AI citations list */}
        {showCitations && (
          <div className="flex-1 min-h-0 flex flex-col">
            {/* AI Citations Section Header */}
            <div className="px-3 py-2 bg-gradient-to-r from-cyan-500/8 to-teal-500/5 border-b border-cyan-500/20 flex items-center gap-2">
              <div className="flex items-center gap-1.5 px-2 py-0.5 bg-cyan-500/15 rounded-md border border-cyan-500/25">
                <Sparkles className="w-3 h-3 text-cyan-400" />
                 <span className="text-[10px] text-cyan-300 font-semibold uppercase tracking-wide">AI 引用片段</span>
              </div>
               <span className="text-xs text-text-muted ml-1">共 {aiReferences.length} 条引用</span>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin p-3 space-y-3">
            {refsWithSnippets.map(({ ref, content, start, highlightStart, highlightEnd, totalLines }) => {
          const nodeColor = ref.label ? (NODE_COLORS[ref.label as keyof typeof NODE_COLORS] ?? '#6b7280') : '#6b7280';
          const hasRange = typeof ref.startLine === 'number';
          const startDisplay = hasRange ? (ref.startLine ?? 0) + 1 : undefined;
          const endDisplay = hasRange ? (ref.endLine ?? ref.startLine ?? 0) + 1 : undefined;
          const language =
            ref.filePath.endsWith('.py') ? 'python' :
            ref.filePath.endsWith('.js') || ref.filePath.endsWith('.jsx') ? 'javascript' :
            ref.filePath.endsWith('.ts') || ref.filePath.endsWith('.tsx') ? 'typescript' :
            'text';

          const isGlowing = glowRefId === ref.id;

          return (
            <div
              key={ref.id}
              ref={(el) => { refCardEls.current.set(ref.id, el); }}
              className={[
                'bg-elevated border border-border-subtle rounded-xl overflow-hidden transition-all',
                isGlowing ? 'ring-2 ring-cyan-300/70 shadow-[0_0_0_6px_rgba(34,211,238,0.14)] animate-pulse' : '',
              ].join(' ')}
            >
              <div className="px-3 py-2 border-b border-border-subtle bg-surface/40 flex items-start gap-2">
                <span
                  className="mt-0.5 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide flex-shrink-0"
                  style={{ backgroundColor: nodeColor, color: '#06060a' }}
                  title={ref.label ?? '代码'}
                >
                  {ref.label ?? '代码'}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-text-primary font-medium truncate">
                    {ref.name ?? ref.filePath.split('/').pop() ?? ref.filePath}
                  </div>
                  <div className="text-[11px] text-text-muted font-mono truncate">
                    {ref.filePath}
                    {startDisplay !== undefined && (
                      <span className="text-text-secondary">
                        {' '}
                        • L{startDisplay}
                        {endDisplay !== startDisplay ? `–${endDisplay}` : ''}
                      </span>
                    )}
                    {totalLines > 0 && <span className="text-text-muted"> • {totalLines} 行</span>}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {ref.nodeId && (
                    <button
                      type="button"
                      onClick={() => {
                        const nodeId = ref.nodeId;
                        if (!nodeId) return;
                        // Sync selection + focus graph
                        if (graph) {
                          const node = graph.nodes.find((n) => n.id === nodeId);
                          if (node) setSelectedNode(node);
                        }
                        onFocusNode(nodeId);
                      }}
                      className="p-1.5 text-text-muted hover:text-text-primary hover:bg-hover rounded transition-colors"
                       title="在图谱中聚焦"
                    >
                      <Target className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => removeCodeReference(ref.id)}
                    className="p-1.5 text-text-muted hover:text-text-primary hover:bg-hover rounded transition-colors"
                     title="移除"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                {content ? (
                  <SyntaxHighlighter
                    language={language}
                    style={customTheme}
                    showLineNumbers
                    startingLineNumber={start + 1}
                    lineNumberStyle={{
                      minWidth: '3em',
                      paddingRight: '1em',
                      color: '#5a5a70',
                      textAlign: 'right',
                      userSelect: 'none',
                    }}
                    lineProps={(lineNumber) => {
                      const isHighlighted =
                        hasRange &&
                        lineNumber >= start + highlightStart + 1 &&
                        lineNumber <= start + highlightEnd + 1;
                      return {
                        style: {
                          display: 'block',
                          backgroundColor: isHighlighted ? 'rgba(6, 182, 212, 0.14)' : 'transparent',
                          borderLeft: isHighlighted ? '3px solid #06b6d4' : '3px solid transparent',
                          paddingLeft: '12px',
                          paddingRight: '16px',
                        },
                      };
                    }}
                    wrapLines
                  >
                    {content}
                  </SyntaxHighlighter>
                ) : (
                  <div className="px-3 py-3 text-sm text-text-muted">
                     内存中暂无 <span className="font-mono">{ref.filePath}</span> 的代码内容
                  </div>
                )}
              </div>
            </div>
          );
            })}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
