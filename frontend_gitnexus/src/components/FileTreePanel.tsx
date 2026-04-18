import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  Braces,
  ChevronDown,
  ChevronRight,
  FileCode,
  Filter,
  Folder,
  FolderOpen,
  Hash,
  PanelLeft,
  PanelLeftClose,
  Search,
  Target,
  Variable,
} from 'lucide-react';
import type { GraphNode, NodeLabel } from '../core/graph/types';
import { useAppState } from '../hooks/useAppState';
import { ALL_EDGE_TYPES, EDGE_INFO, FILTERABLE_LABELS, NODE_COLORS, type EdgeType } from '../lib/constants';

const NODE_LABEL_TEXT: Partial<Record<NodeLabel, string>> = {
  Folder: '文件夹',
  File: '文件',
  Class: '类',
  Function: '函数',
  Method: '方法',
  Variable: '变量',
  Interface: '接口',
  Import: '导入',
};

const EDGE_LABEL_TEXT: Record<EdgeType, string> = {
  CONTAINS: '包含',
  DEFINES: '定义',
  IMPORTS: '导入',
  CALLS: '调用',
  EXTENDS: '继承',
  IMPLEMENTS: '实现',
};

// Tree node structure
interface TreeNode {
  id: string;
  name: string;
  type: 'folder' | 'file';
  path: string;
  children: TreeNode[];
  graphNode?: GraphNode;
}

// Build tree from graph nodes
const buildFileTree = (nodes: GraphNode[]): TreeNode[] => {
  const root: TreeNode[] = [];
  const pathMap = new Map<string, TreeNode>();

  // Filter to only folders and files
  const fileNodes = nodes.filter(n => n.label === 'Folder' || n.label === 'File');

  // Sort by path to ensure parents come before children
  fileNodes.sort((a, b) => a.properties.filePath.localeCompare(b.properties.filePath));

  fileNodes.forEach(node => {
    const parts = node.properties.filePath.split('/').filter(Boolean);
    let currentPath = '';
    let currentLevel = root;

    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;

      let existing = pathMap.get(currentPath);

      if (!existing) {
        const isLastPart = index === parts.length - 1;
        const isFile = isLastPart && node.label === 'File';

        existing = {
          id: isLastPart ? node.id : currentPath,
          name: part,
          type: isFile ? 'file' : 'folder',
          path: currentPath,
          children: [],
          graphNode: isLastPart ? node : undefined,
        };

        pathMap.set(currentPath, existing);
        currentLevel.push(existing);
      }

      currentLevel = existing.children;
    });
  });

  return root;
};

// Tree item component
interface TreeItemProps {
  node: TreeNode;
  depth: number;
  searchQuery: string;
  onNodeClick: (node: TreeNode) => void;
  expandedPaths: Set<string>;
  toggleExpanded: (path: string) => void;
  selectedPath: string | null;
}

const TreeItem = ({
  node,
  depth,
  searchQuery,
  onNodeClick,
  expandedPaths,
  toggleExpanded,
  selectedPath,
}: TreeItemProps) => {
  const isExpanded = expandedPaths.has(node.path);
  const isSelected = selectedPath === node.path;
  const hasChildren = node.children.length > 0;

  // Filter children based on search
  const filteredChildren = useMemo(() => {
    if (!searchQuery) return node.children;
    return node.children.filter(child =>
      child.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      child.children.some(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()))
    );
  }, [node.children, searchQuery]);

  // Check if this node matches search
  const matchesSearch = searchQuery && node.name.toLowerCase().includes(searchQuery.toLowerCase());

  const handleClick = () => {
    if (hasChildren) {
      toggleExpanded(node.path);
    }
    onNodeClick(node);
  };

  return (
    <div>
      <button
        type="button"
        onClick={handleClick}
        className={`
          w-full flex items-center gap-1.5 px-2 py-1 text-left text-sm
          hover:bg-hover transition-colors rounded relative
          ${isSelected ? 'bg-amber-500/15 text-amber-300 border-l-2 border-amber-400' : 'text-text-secondary hover:text-text-primary border-l-2 border-transparent'}
          ${matchesSearch ? 'bg-accent/10' : ''}
        `}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
      >
        {/* Expand/collapse icon */}
        {hasChildren ? (
          isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5 shrink-0 text-text-muted" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 shrink-0 text-text-muted" />
          )
        ) : (
          <span className="w-3.5" />
        )}

        {/* Node icon */}
        {node.type === 'folder' ? (
          isExpanded ? (
            <FolderOpen className="w-4 h-4 shrink-0" style={{ color: NODE_COLORS.Folder }} />
          ) : (
            <Folder className="w-4 h-4 shrink-0" style={{ color: NODE_COLORS.Folder }} />
          )
        ) : (
          <FileCode className="w-4 h-4 shrink-0" style={{ color: NODE_COLORS.File }} />
        )}

        {/* Name */}
        <span className="truncate font-mono text-xs">{node.name}</span>
      </button>

      {/* Children */}
      {isExpanded && filteredChildren.length > 0 && (
        <div>
          {filteredChildren.map(child => (
            <TreeItem
              key={child.id}
              node={child}
              depth={depth + 1}
              searchQuery={searchQuery}
              onNodeClick={onNodeClick}
              expandedPaths={expandedPaths}
              toggleExpanded={toggleExpanded}
              selectedPath={selectedPath}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// Icon for node types
const getNodeTypeIcon = (label: NodeLabel) => {
  switch (label) {
    case 'Folder': return Folder;
    case 'File': return FileCode;
    case 'Class': return Box;
    case 'Function': return Braces;
    case 'Method': return Braces;
    case 'Interface': return Hash;
    case 'Import': return FileCode;
    default: return Variable;
  }
};

const getNodeLabelText = (label: NodeLabel) => NODE_LABEL_TEXT[label] ?? label;

const getEdgeLabelText = (edgeType: EdgeType, fallbackLabel: string) => EDGE_LABEL_TEXT[edgeType] ?? fallbackLabel;

interface FileTreePanelProps {
  onFocusNode: (nodeId: string) => void;
}

export const FileTreePanel = ({ onFocusNode }: FileTreePanelProps) => {
  const { graph, visibleLabels, toggleLabelVisibility, visibleEdgeTypes, toggleEdgeVisibility, selectedNode, setSelectedNode, openCodePanel, depthFilter, setDepthFilter } = useAppState();

  const [isCollapsed, setIsCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState<'files' | 'filters'>('files');

  // Build file tree from graph
  const fileTree = useMemo(() => {
    if (!graph) return [];
    return buildFileTree(graph.nodes);
  }, [graph]);

  const firstLevelPaths = useMemo(() => fileTree.map(node => node.path), [fileTree]);
  const selectedNodePath = selectedNode?.properties?.filePath;

  // Auto-expand first level on initial load
  useEffect(() => {
    if (firstLevelPaths.length > 0 && expandedPaths.size === 0) {
      const firstLevel = new Set(firstLevelPaths);
      setExpandedPaths(firstLevel);
    }
  }, [expandedPaths.size, firstLevelPaths]);

  // Auto-expand to selected file when selectedNode changes (e.g., from graph click)
  useEffect(() => {
    if (!selectedNodePath) return;

    // Expand all parent folders leading to this file
    const parts = selectedNodePath.split('/').filter(Boolean);
    const pathsToExpand: string[] = [];
    let currentPath = '';

    // Build all parent paths (exclude the last part if it's a file)
    for (let i = 0; i < parts.length - 1; i++) {
      currentPath = currentPath ? `${currentPath}/${parts[i]}` : parts[i];
      pathsToExpand.push(currentPath);
    }

    if (pathsToExpand.length > 0) {
      setExpandedPaths(prev => {
        const next = new Set(prev);
        pathsToExpand.forEach((pathToExpand) => {
          next.add(pathToExpand);
        });
        return next;
      });
    }
  }, [selectedNodePath]);

  const toggleExpanded = useCallback((path: string) => {
    setExpandedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleNodeClick = useCallback((treeNode: TreeNode) => {
    if (treeNode.graphNode) {
      // Only focus if selecting a different node
      const isSameNode = selectedNode?.id === treeNode.graphNode.id;
      setSelectedNode(treeNode.graphNode);
      openCodePanel();
      if (!isSameNode) {
        onFocusNode(treeNode.graphNode.id);
      }
    }
  }, [setSelectedNode, openCodePanel, onFocusNode, selectedNode]);

  const selectedPath = selectedNode?.properties.filePath || null;

  if (isCollapsed) {
    return (
      <div className="h-full w-12 bg-surface border-r border-border-subtle flex flex-col items-center py-3 gap-2">
        <button
          type="button"
          onClick={() => setIsCollapsed(false)}
          className="p-2 text-text-secondary hover:text-text-primary hover:bg-hover rounded transition-colors"
          title="展开面板"
        >
          <PanelLeft className="w-5 h-5" />
        </button>
        <div className="w-6 h-px bg-border-subtle my-1" />
        <button
          type="button"
          onClick={() => { setIsCollapsed(false); setActiveTab('files'); }}
          className={`p-2 rounded transition-colors ${activeTab === 'files' ? 'text-accent bg-accent/10' : 'text-text-secondary hover:text-text-primary hover:bg-hover'}`}
          title="文件浏览"
        >
          <Folder className="w-5 h-5" />
        </button>
        <button
          type="button"
          onClick={() => { setIsCollapsed(false); setActiveTab('filters'); }}
          className={`p-2 rounded transition-colors ${activeTab === 'filters' ? 'text-accent bg-accent/10' : 'text-text-secondary hover:text-text-primary hover:bg-hover'}`}
          title="筛选"
        >
          <Filter className="w-5 h-5" />
        </button>
      </div>
    );
  }

  return (
    <div className="h-full w-64 bg-surface border-r border-border-subtle flex flex-col animate-slide-in">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setActiveTab('files')}
            className={`px-2 py-1 text-xs rounded transition-colors ${activeTab === 'files'
              ? 'bg-accent/20 text-accent'
              : 'text-text-secondary hover:text-text-primary hover:bg-hover'
              }`}
          >
            文件
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('filters')}
            className={`px-2 py-1 text-xs rounded transition-colors ${activeTab === 'filters'
              ? 'bg-accent/20 text-accent'
              : 'text-text-secondary hover:text-text-primary hover:bg-hover'
              }`}
          >
            筛选
          </button>
        </div>
        <button
          type="button"
          onClick={() => setIsCollapsed(true)}
          className="p-1 text-text-muted hover:text-text-primary hover:bg-hover rounded transition-colors"
          title="收起面板"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {activeTab === 'files' && (
        <>
          {/* Search */}
          <div className="px-3 py-2 border-b border-border-subtle">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
              <input
                type="text"
                placeholder="搜索文件..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 bg-elevated border border-border-subtle rounded text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent"
              />
            </div>
          </div>

          {/* File tree */}
          <div className="flex-1 overflow-y-auto scrollbar-thin py-2">
            {fileTree.length === 0 ? (
              <div className="px-3 py-4 text-center text-text-muted text-xs">
                暂无文件
              </div>
            ) : (
              fileTree.map(node => (
                <TreeItem
                  key={node.id}
                  node={node}
                  depth={0}
                  searchQuery={searchQuery}
                  onNodeClick={handleNodeClick}
                  expandedPaths={expandedPaths}
                  toggleExpanded={toggleExpanded}
                  selectedPath={selectedPath}
                />
              ))
            )}
          </div>
        </>
      )}

      {activeTab === 'filters' && (
        <div className="flex-1 overflow-y-auto scrollbar-thin p-3">
          <div className="mb-3">
            <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-2">
              节点类型
            </h3>
            <p className="text-[11px] text-text-muted mb-3">
              切换图谱中各类节点的显示
            </p>
          </div>

          <div className="flex flex-col gap-1">
            {FILTERABLE_LABELS.map((label) => {
              const Icon = getNodeTypeIcon(label);
              const isVisible = visibleLabels.includes(label);

              return (
                <button
                  type="button"
                  key={label}
                  onClick={() => toggleLabelVisibility(label)}
                  className={`
                    flex items-center gap-2.5 px-2 py-1.5 rounded text-left transition-colors
                    ${isVisible
                      ? 'bg-elevated text-text-primary'
                      : 'text-text-muted hover:bg-hover hover:text-text-secondary'
                    }
                  `}
                  >
                  <div
                    className={`w-5 h-5 rounded flex items-center justify-center ${isVisible ? '' : 'opacity-40'}`}
                    style={{ backgroundColor: `${NODE_COLORS[label]}20` }}
                  >
                    <Icon className="w-3 h-3" style={{ color: NODE_COLORS[label] }} />
                  </div>
                  <span className="text-xs flex-1">{getNodeLabelText(label)}</span>
                  <div
                    className={`w-2 h-2 rounded-full transition-colors ${isVisible ? 'bg-accent' : 'bg-border-subtle'}`}
                  />
                </button>
              );
            })}
          </div>

          {/* Edge Type Toggles */}
          <div className="mt-6 pt-4 border-t border-border-subtle">
            <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-2">
              关系类型
            </h3>
            <p className="text-[11px] text-text-muted mb-3">
              切换不同关系连线的显示
            </p>

            <div className="flex flex-col gap-1">
              {ALL_EDGE_TYPES.map((edgeType) => {
                const info = EDGE_INFO[edgeType];
                const isVisible = visibleEdgeTypes.includes(edgeType);

                return (
                  <button
                    type="button"
                    key={edgeType}
                    onClick={() => toggleEdgeVisibility(edgeType)}
                    className={`
                      flex items-center gap-2.5 px-2 py-1.5 rounded text-left transition-colors
                      ${isVisible
                        ? 'bg-elevated text-text-primary'
                        : 'text-text-muted hover:bg-hover hover:text-text-secondary'
                      }
                    `}
                  >
                    <div
                      className={`w-6 h-1.5 rounded-full ${isVisible ? '' : 'opacity-40'}`}
                      style={{ backgroundColor: info.color }}
                    />
                    <span className="text-xs flex-1">{getEdgeLabelText(edgeType, info.label)}</span>
                    <div
                      className={`w-2 h-2 rounded-full transition-colors ${isVisible ? 'bg-accent' : 'bg-border-subtle'}`}
                    />
                  </button>
                );
              })}
            </div>
          </div>

          {/* Depth Filter */}
          <div className="mt-6 pt-4 border-t border-border-subtle">
            <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-2">
              <Target className="w-3 h-3 inline mr-1.5" />
              聚焦深度
            </h3>
            <p className="text-[11px] text-text-muted mb-3">
              仅显示距当前选择 N 跳内的节点
            </p>

            <div className="flex flex-wrap gap-1.5">
              {[
                { value: null, label: '全部' },
                { value: 1, label: '1 跳' },
                { value: 2, label: '2 跳' },
                { value: 3, label: '3 跳' },
                { value: 5, label: '5 跳' },
              ].map(({ value, label }) => (
                <button
                  type="button"
                  key={label}
                  onClick={() => setDepthFilter(value)}
                  className={`
                    px-2 py-1 text-xs rounded transition-colors
                    ${depthFilter === value
                      ? 'bg-accent text-white'
                      : 'bg-elevated text-text-secondary hover:bg-hover hover:text-text-primary'
                    }
                  `}
                >
                  {label}
                </button>
              ))}
            </div>

            {depthFilter !== null && !selectedNode && (
              <p className="mt-2 text-[10px] text-amber-400">
                请选择节点后再应用深度筛选
              </p>
            )}
          </div>

          {/* Legend */}
          <div className="mt-6 pt-4 border-t border-border-subtle">
            <h3 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-3">
              颜色说明
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {(['Folder', 'File', 'Class', 'Function', 'Interface', 'Method'] as NodeLabel[]).map(label => (
                <div key={label} className="flex items-center gap-1.5">
                  <div
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: NODE_COLORS[label] }}
                  />
                  <span className="text-[10px] text-text-muted">{getNodeLabelText(label)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Stats footer */}
      {graph && (
        <div className="px-3 py-2 border-t border-border-subtle bg-elevated/50">
          <div className="flex items-center justify-between text-[10px] text-text-muted">
            <span>{graph.nodes.length} 个节点</span>
            <span>{graph.relationships.length} 条连线</span>
          </div>
        </div>
      )}
    </div>
  );
};
