/**
 * Processes Panel
 * 
 * Lists all detected processes grouped by type (cross-community / intra-community).
 * Clicking a process opens the ProcessFlowModal with a flowchart.
 */

import { useState, useMemo, useCallback, useEffect } from 'react';
import { GitBranch, Search, Eye, Zap, Home, ChevronDown, ChevronRight, Sparkles, Lightbulb, Layers } from 'lucide-react';
import { useAppState } from '../hooks/useAppState';
import { ProcessFlowModal } from './ProcessFlowModal';
import type { ProcessData, ProcessStep } from '../lib/mermaid-generator';

const readNumericStepCount = (value: unknown): number | null => {
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const getProcessStepRelsFromGraph = (
    graph: ReturnType<typeof useAppState>['graph'],
    processId: string,
) => {
    if (!graph) return [];
    return graph.relationships.filter((rel) => rel.type === 'STEP_IN_PROCESS' && rel.targetId === processId);
};

const getProcessStepIdsFromGraph = (
    graph: ReturnType<typeof useAppState>['graph'],
    processId: string,
): string[] => {
    return getProcessStepRelsFromGraph(graph, processId).map((rel) => rel.sourceId);
};

const buildProcessStepsFromGraph = (
    graph: ReturnType<typeof useAppState>['graph'],
    processId: string,
): ProcessStep[] => {
    if (!graph) return [];
    const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
    const rels = [...getProcessStepRelsFromGraph(graph, processId)].sort((left, right) => {
        const leftStep = typeof left.step === 'number' ? left.step : Number.MAX_SAFE_INTEGER;
        const rightStep = typeof right.step === 'number' ? right.step : Number.MAX_SAFE_INTEGER;
        return leftStep - rightStep;
    });

    return rels.map((rel, index) => {
        const stepNode = nodeById.get(rel.sourceId);
        return {
            id: rel.sourceId,
            name: stepNode?.properties?.name || rel.sourceId,
            filePath: stepNode?.properties?.filePath,
            stepNumber: typeof rel.step === 'number' ? rel.step : index + 1,
        };
    });
};

export const ProcessesPanel = () => {
    const { graph, runQuery, setHighlightedNodeIds, highlightedNodeIds } = useAppState();
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedProcess, setSelectedProcess] = useState<ProcessData | null>(null);
    const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['cross', 'intra']));
    const [loadingProcess, setLoadingProcess] = useState<string | null>(null);
    const [focusedProcessId, setFocusedProcessId] = useState<string | null>(null);

    // Extract processes from graph
    const processes = useMemo(() => {
        if (!graph) return { cross: [], intra: [] };

        const processNodes = graph.nodes.filter(n => n.label === 'Process');
        const relDerivedStepCount = new Map<string, number>();
        for (const rel of graph.relationships) {
            if (rel.type !== 'STEP_IN_PROCESS') continue;
            relDerivedStepCount.set(rel.targetId, (relDerivedStepCount.get(rel.targetId) || 0) + 1);
        }

        const cross: Array<{ id: string; label: string; stepCount: number; clusters: string[] }> = [];
        const intra: Array<{ id: string; label: string; stepCount: number; clusters: string[] }> = [];

        for (const node of processNodes) {
            const nodeProps = node.properties as Record<string, unknown>;
            const directStepCount = readNumericStepCount(nodeProps.stepCount) ?? readNumericStepCount(nodeProps.step_count);
            const item = {
                id: node.id,
                label: node.properties.heuristicLabel || node.properties.name || node.id,
                stepCount: directStepCount && directStepCount > 0
                    ? directStepCount
                    : (relDerivedStepCount.get(node.id) || 0),
                clusters: node.properties.communities || [],
            };

            if (node.properties.processType === 'cross_community') {
                cross.push(item);
            } else {
                intra.push(item);
            }
        }

        // Sort by step count (most complex first)
        cross.sort((a, b) => b.stepCount - a.stepCount);
        intra.sort((a, b) => b.stepCount - a.stepCount);

        return { cross, intra };
    }, [graph]);

    // Filter by search
    const filteredProcesses = useMemo(() => {
        if (!searchQuery.trim()) return processes;

        const query = searchQuery.toLowerCase();
        return {
            cross: processes.cross.filter(p => p.label.toLowerCase().includes(query)),
            intra: processes.intra.filter(p => p.label.toLowerCase().includes(query)),
        };
    }, [processes, searchQuery]);

    // Toggle section expansion
    const toggleSection = useCallback((section: string) => {
        setExpandedSections(prev => {
            const next = new Set(prev);
            if (next.has(section)) {
                next.delete(section);
            } else {
                next.add(section);
            }
            return next;
        });
    }, []);

    // Load ALL processes and combine into one mega-diagram
    const handleViewAllProcesses = useCallback(async () => {
        setLoadingProcess('all');

        try {
            const allProcessIds = [...processes.cross, ...processes.intra].map(p => p.id);

            if (allProcessIds.length === 0) return;

            // Collect all steps from all processes
            const allStepsMap = new Map<string, ProcessStep>();
            const allEdges: Array<{ from: string; to: string; type: string }> = [];

            // Fetch steps for all processes concurrently in batches if needed, but for now sequentially to be safe
            // Optimization: Fetch all steps in one query if possible
            const allStepsQuery = `
                MATCH (s)-[r:CodeRelation {type: 'STEP_IN_PROCESS'}]->(p:Process)
                WHERE p.id IN [${allProcessIds.map(id => `'${id.replace(/'/g, "''")}'`).join(',')}]
                RETURN s.id AS id, s.name AS name, s.filePath AS filePath, r.step AS stepNumber
            `;

            const stepsResult = await runQuery(allStepsQuery);

            for (const row of stepsResult) {
                const stepId = row.id || row[0];
                if (!allStepsMap.has(stepId)) {
                    allStepsMap.set(stepId, {
                        id: stepId,
                        name: row.name || row[1] || 'Unknown',
                        filePath: row.filePath || row[2],
                        stepNumber: row.stepNumber || row.step || row[3] || 0,
                    });
                }
            }

            const allSteps = Array.from(allStepsMap.values());
            const stepIds = allSteps.map(s => s.id);

            // Query for all CALLS edges between the combined steps
            if (stepIds.length > 0) {
                // Batch query if too many steps
                const edgesQuery = `
                    MATCH (from)-[r:CodeRelation {type: 'CALLS'}]->(to)
                    WHERE from.id IN [${stepIds.map(id => `'${id.replace(/'/g, "''")}'`).join(',')}]
                      AND to.id IN [${stepIds.map(id => `'${id.replace(/'/g, "''")}'`).join(',')}]
                    RETURN from.id AS fromId, to.id AS toId, r.type AS type
                `;

                try {
                    const edgesResult = await runQuery(edgesQuery);
                    allEdges.push(...edgesResult
                        .map((row: any) => ({
                            from: row.fromId || row[0],
                            to: row.toId || row[1],
                            type: row.type || row[2] || 'CALLS',
                        }))
                        .filter(edge => edge.from !== edge.to));
                } catch (err) {
                    console.warn('Could not fetch combined edges:', err);
                }
            }

            const combinedProcessData: ProcessData = {
                id: 'combined-all',
                label: `All Processes (${allProcessIds.length} combined)`,
                processType: 'cross_community', // Treat as cross-community for styling
                steps: allSteps,
                edges: allEdges,
                clusters: [],
            };

            setSelectedProcess(combinedProcessData);
        } catch (error) {
            console.error('Failed to load combined processes:', error);
        } finally {
            setLoadingProcess(null);
        }
    }, [processes, runQuery]);

    // Load process steps and open modal
    const handleViewProcess = useCallback(async (processId: string, label: string, processType: string) => {
        setLoadingProcess(processId);

        try {
            // Query for process steps
            const stepsQuery = `
        MATCH (s)-[r:CodeRelation {type: 'STEP_IN_PROCESS'}]->(p:Process {id: '${processId.replace(/'/g, "''")}'})
        RETURN s.id AS id, s.name AS name, s.filePath AS filePath, r.step AS stepNumber
        ORDER BY r.step
      `;

            let steps: ProcessStep[] = [];
            try {
                const stepsResult = await runQuery(stepsQuery);
                steps = stepsResult.map((row: any) => ({
                    id: row.id || row[0],
                    name: row.name || row[1] || 'Unknown',
                    filePath: row.filePath || row[2],
                    stepNumber: row.stepNumber || row.step || row[3] || 0,
                }));
            } catch (queryError) {
                console.warn('Failed to query process steps, falling back to graph relationships:', queryError);
            }
            if (steps.length === 0) {
                steps = buildProcessStepsFromGraph(graph, processId);
            }

            // Get step IDs for edge query
            const stepIds = steps.map(s => s.id);

            // Query for CALLS edges between the steps in this process
            let edges: Array<{ from: string; to: string; type: string }> = [];
            if (stepIds.length > 0) {
                const edgesQuery = `
          MATCH (from)-[r:CodeRelation {type: 'CALLS'}]->(to)
          WHERE from.id IN [${stepIds.map(id => `'${id.replace(/'/g, "''")}'`).join(',')}]
            AND to.id IN [${stepIds.map(id => `'${id.replace(/'/g, "''")}'`).join(',')}]
          RETURN from.id AS fromId, to.id AS toId, r.type AS type
        `;

                try {
                    const edgesResult = await runQuery(edgesQuery);
                    edges = edgesResult
                        .map((row: any) => ({
                            from: row.fromId || row[0],
                            to: row.toId || row[1],
                            type: row.type || row[2] || 'CALLS',
                        }))
                        .filter(edge => edge.from !== edge.to); // Remove self-loops
                } catch (err) {
                    console.warn('Could not fetch edges from DB query, falling back to graph relationships:', err);
                    if (graph) {
                        const stepIdSet = new Set(stepIds);
                        edges = graph.relationships
                            .filter((rel) => rel.type === 'CALLS' && stepIdSet.has(rel.sourceId) && stepIdSet.has(rel.targetId))
                            .map((rel) => ({ from: rel.sourceId, to: rel.targetId, type: rel.type }))
                            .filter((edge) => edge.from !== edge.to);
                    }
                }
            }

            // Get clusters for this process
            const processNode = graph?.nodes.find(n => n.id === processId);
            const clusters = processNode?.properties.communities || [];

            const processData: ProcessData = {
                id: processId,
                label,
                processType: processType as 'cross_community' | 'intra_community',
                steps,
                edges,
                clusters,
            };

            setSelectedProcess(processData);
        } catch (error) {
            console.error('Failed to load process steps:', error);
        } finally {
            setLoadingProcess(null);
        }
    }, [runQuery, graph]);

    // Cache for process steps (so we don't re-query when toggling focus)
    const [processStepsCache, setProcessStepsCache] = useState<Map<string, string[]>>(new Map());

    // Toggle focus for any process - loads steps on demand
    const handleToggleFocusForProcess = useCallback(async (processId: string) => {
        // If already focused on this process, turn off
        if (focusedProcessId === processId) {
            setHighlightedNodeIds(new Set());
            setFocusedProcessId(null);
            return;
        }

        // Check if we have cached steps
        if (processStepsCache.has(processId)) {
            const stepIds = processStepsCache.get(processId)!;
            setHighlightedNodeIds(new Set(stepIds));
            setFocusedProcessId(processId);
            return;
        }

        // Load steps for this process
        setLoadingProcess(processId);
        try {
            const stepsQuery = `
                MATCH (s)-[r:CodeRelation {type: 'STEP_IN_PROCESS'}]->(p:Process {id: '${processId.replace(/'/g, "''")}'})
                RETURN s.id AS id
            `;
            let stepIds: string[] = [];
            try {
                const stepsResult = await runQuery(stepsQuery);
                stepIds = stepsResult.map((row: any) => row.id || row[0]);
            } catch (error) {
                console.warn('Failed to query process focus steps, falling back to graph relationships:', error);
            }
            if (stepIds.length === 0) {
                stepIds = getProcessStepIdsFromGraph(graph, processId);
            }

            // Cache the result
            setProcessStepsCache(prev => new Map(prev).set(processId, stepIds));

            // Set focus
            setHighlightedNodeIds(new Set(stepIds));
            setFocusedProcessId(processId);
        } catch (error) {
            console.error('Failed to load process steps for focus:', error);
        } finally {
            setLoadingProcess(null);
        }
    }, [focusedProcessId, graph, processStepsCache, runQuery, setHighlightedNodeIds]);

    // Focus in graph callback - toggles highlight (used by modal)
    const handleFocusInGraph = useCallback((nodeIds: string[], processId: string) => {
        // Check if this process is already focused
        if (focusedProcessId === processId) {
            // Clear focus
            setHighlightedNodeIds(new Set());
            setFocusedProcessId(null);
        } else {
            // Set focus and cache
            setHighlightedNodeIds(new Set(nodeIds));
            setFocusedProcessId(processId);
            setProcessStepsCache(prev => new Map(prev).set(processId, nodeIds));
        }
    }, [focusedProcessId, setHighlightedNodeIds]);

    // Clear focused process when highlights are cleared externally
    useEffect(() => {
        if (highlightedNodeIds.size === 0 && focusedProcessId !== null) {
            setFocusedProcessId(null);
        }
    }, [highlightedNodeIds, focusedProcessId]);

    const totalCount = processes.cross.length + processes.intra.length;


    if (totalCount === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full p-6 text-center">
                <div className="w-14 h-14 mb-4 flex items-center justify-center bg-surface rounded-xl">
                    <GitBranch className="w-7 h-7 text-text-muted" />
                </div>
                <h3 className="text-base font-medium text-text-primary mb-2">尚未识别到 Process</h3>
                <p className="text-sm text-text-secondary max-w-xs">
                    Process 表示从入口点推导出的执行流。导入代码后，这里会展示识别到的流程分组。
                </p>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header with search */}
            <div className="p-3 border-b border-border-subtle">
                <div className="flex items-center gap-2 mb-2">
                    <div className="flex-1 flex items-center gap-2 px-3 py-2 bg-elevated border border-border-subtle rounded-lg focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
                        <Search className="w-4 h-4 text-text-muted" />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="按名称筛选 Process…"
                            className="flex-1 bg-transparent border-none outline-none text-sm text-text-primary placeholder:text-text-muted"
                        />
                    </div>
                </div>
                <div className="flex items-center gap-2 text-xs text-text-muted">
                    <span>共识别 {totalCount} 个 Process</span>
                </div>
            </div>

            {/* Process list */}
            <div className="flex-1 overflow-y-auto scrollbar-thin">
                {/* View All Processes Card */}
                <div className="px-4 py-3">
                    <button
                        type="button"
                        onClick={handleViewAllProcesses}
                        disabled={loadingProcess !== null}
                        className="w-full flex items-center gap-3 p-3 bg-elevated/40 hover:bg-elevated/80 border border-border-subtle hover:border-cyan-500/30 rounded-xl transition-all group shadow-sm hover:shadow-cyan-900/10 text-left"
                    >
                        <div className="p-2 bg-cyan-500/10 rounded-lg group-hover:bg-cyan-500/20 transition-colors">
                            <Layers className="w-5 h-5 text-cyan-400" />
                        </div>
                        <div className="flex-1">
                            <h4 className="text-sm font-medium text-text-primary group-hover:text-cyan-200">全量流程地图</h4>
                            <p className="text-xs text-text-muted">合并查看全部 {totalCount} 个 Process 的整体关系</p>
                        </div>
                        {loadingProcess === 'all' ? (
                            <span className="animate-spin mr-1">
                                <Sparkles className="w-4 h-4 text-cyan-400" />
                            </span>
                        ) : (
                            <Eye className="w-4 h-4 text-text-muted group-hover:text-cyan-400" />
                        )}
                    </button>
                </div>

                {/* Cross-Community Section */}
                {filteredProcesses.cross.length > 0 && (
                    <div className="border-b border-border-subtle">
                        <button
                            type="button"
                            onClick={() => toggleSection('cross')}
                            className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-hover transition-colors"
                        >
                            {expandedSections.has('cross') ? (
                                <ChevronDown className="w-4 h-4 text-text-muted" />
                            ) : (
                                <ChevronRight className="w-4 h-4 text-text-muted" />
                            )}
                            <Zap className="w-4 h-4 text-amber-400" />
                            <span className="text-sm font-medium text-text-primary">跨社区流程</span>
                            <span className="ml-auto text-xs text-text-muted bg-surface px-2 py-0.5 rounded-full">
                                {filteredProcesses.cross.length}
                            </span>
                        </button>

                        {expandedSections.has('cross') && (
                            <div className="pb-2">
                                {filteredProcesses.cross.map((process) => (
                                    <ProcessItem
                                        key={process.id}
                                        process={process}
                                        isLoading={loadingProcess === process.id}
                                        isSelected={selectedProcess?.id === process.id}
                                        isFocused={focusedProcessId === process.id}
                                        onView={() => handleViewProcess(process.id, process.label, 'cross_community')}
                                        onToggleFocus={() => handleToggleFocusForProcess(process.id)}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Intra-Community Section */}
                {filteredProcesses.intra.length > 0 && (
                    <div>
                        <button
                            type="button"
                            onClick={() => toggleSection('intra')}
                            className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-hover transition-colors"
                        >
                            {expandedSections.has('intra') ? (
                                <ChevronDown className="w-4 h-4 text-text-muted" />
                            ) : (
                                <ChevronRight className="w-4 h-4 text-text-muted" />
                            )}
                            <Home className="w-4 h-4 text-emerald-400" />
                            <span className="text-sm font-medium text-text-primary">社区内流程</span>
                            <span className="ml-auto text-xs text-text-muted bg-surface px-2 py-0.5 rounded-full">
                                {filteredProcesses.intra.length}
                            </span>
                        </button>

                        {expandedSections.has('intra') && (
                            <div className="pb-2">
                                {filteredProcesses.intra.map((process) => (
                                    <ProcessItem
                                        key={process.id}
                                        process={process}
                                        isLoading={loadingProcess === process.id}
                                        isSelected={selectedProcess?.id === process.id}
                                        isFocused={focusedProcessId === process.id}
                                        onView={() => handleViewProcess(process.id, process.label, 'intra_community')}
                                        onToggleFocus={() => handleToggleFocusForProcess(process.id)}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Modal */}
            <ProcessFlowModal
                process={selectedProcess}
                onClose={() => setSelectedProcess(null)}
                onFocusInGraph={handleFocusInGraph}
                isFullScreen={selectedProcess?.id === 'combined-all'}
            />
        </div>
    );
};

// Individual process item
interface ProcessItemProps {
    process: { id: string; label: string; stepCount: number; clusters: string[] };
    isLoading: boolean;
    isSelected: boolean;
    isFocused: boolean;
    onView: () => void;
    onToggleFocus: () => void;
}

const ProcessItem = ({ process, isLoading, isSelected, isFocused, onView, onToggleFocus }: ProcessItemProps) => {
    // Determine row styling - focused gets special highlight
    const rowClass = isFocused
        ? 'bg-amber-950/40 border border-amber-500/50 ring-1 ring-amber-400/30'
        : isSelected
            ? 'bg-cyan-950/40 border border-cyan-500/50 ring-1 ring-cyan-400/30'
            : '';

    return (
        <div className={`flex items-center gap-2 px-4 py-2 mx-2 rounded-lg hover:bg-hover group transition-all ${rowClass}`}>
            <GitBranch className="w-4 h-4 text-text-muted flex-shrink-0" />
            <div className="flex-1 min-w-0">
                <div className="text-sm text-text-primary truncate">{process.label}</div>
                <div className="flex items-center gap-2 text-xs text-text-muted">
                        <span>{process.stepCount} 个步骤</span>
                    {process.clusters.length > 0 && (
                        <>
                            <span>•</span>
                            <span>{process.clusters.length} 个社区</span>
                        </>
                    )}
                </div>
            </div>
            {/* Lightbulb icon - appears on hover, always visible when focused */}
            <button
                type="button"
                onClick={onToggleFocus}
                className={`p-1.5 rounded-md transition-all ${isFocused
                    ? 'text-amber-400 hover:text-amber-300 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-400/40 animate-pulse opacity-100'
                    : 'text-text-muted hover:text-cyan-400 bg-white/5 hover:bg-cyan-500/20 border border-white/10 hover:border-cyan-400/40 opacity-0 group-hover:opacity-100'
                    }`}
                title={isFocused ? '取消图谱高亮' : '在图谱中高亮'}
            >
                <Lightbulb className="w-4 h-4" />
            </button>
            <button
                type="button"
                onClick={onView}
                disabled={isLoading}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-md transition-all disabled:opacity-50 shadow-sm ${isSelected
                    ? 'text-cyan-300 bg-cyan-900/60 border border-cyan-400/60 opacity-100'
                    : 'text-cyan-400 hover:text-cyan-300 bg-cyan-950/30 hover:bg-cyan-900/50 border border-cyan-500/30 hover:border-cyan-400/50 opacity-0 group-hover:opacity-100 shadow-cyan-900/20'
                    }`}
            >
                {isLoading ? (
                    <span className="animate-pulse">加载中…</span>
                ) : isSelected ? (
                    <>
                        <Eye className="w-3.5 h-3.5" />
                        查看中
                    </>
                ) : (
                    <>
                        <Eye className="w-3.5 h-3.5" />
                        查看
                    </>
                )}
            </button>
        </div>
    );
};
