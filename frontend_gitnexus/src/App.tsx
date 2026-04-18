import { useCallback, useEffect, useRef } from 'react';
import { AppStateProvider, useAppState } from './hooks/useAppState';
import { DropZone } from './components/DropZone';
import { LoadingOverlay } from './components/LoadingOverlay';
import { Header } from './components/Header';
import { GraphCanvas, GraphCanvasHandle } from './components/GraphCanvas';
import { RightPanel } from './components/RightPanel';
import { SettingsPanel } from './components/SettingsPanel';
import { StatusBar } from './components/StatusBar';
import { FileTreePanel } from './components/FileTreePanel';
import { CodeReferencesPanel } from './components/CodeReferencesPanel';
import { FileEntry } from './services/zip';
import { getActiveProviderConfig } from './core/llm/settings-service';
import { createKnowledgeGraph } from './core/graph/graph';
import { connectToServer, fetchRepos, normalizeServerUrl, type ConnectToServerResult } from './services/server-connection';
import { createGraphExtensionsApi } from './services/create-graph-extensions';

const AppContent = () => {
  const {
    viewMode,
    setViewMode,
    setGraph,
    setFileContents,
    setProgress,
    setProjectName,
    progress,
    isRightPanelOpen,
    runPipeline,
    runPipelineFromFiles,
    isSettingsPanelOpen,
    setSettingsPanelOpen,
    refreshLLMSettings,
    initializeAgent,
    startEmbeddings,
    codeReferences,
    selectedNode,
    isCodePanelOpen,
    setServerBaseUrl,
    availableRepos,
    setAvailableRepos,
    switchRepo,
  } = useAppState();

  const graphCanvasRef = useRef<GraphCanvasHandle>(null);

  const handleFileSelect = useCallback(async (file: File) => {
    const projectName = file.name.replace('.zip', '');
    setProjectName(projectName);
    setProgress({ phase: 'extracting', percent: 0, message: '开始处理…', detail: '正在准备解压文件' });
    setViewMode('loading');

    try {
      const result = await runPipeline(file, (progress) => {
        setProgress(progress);
      });

      setGraph(result.graph);
      setFileContents(result.fileContents);
      setViewMode('exploring');

      // Initialize (or re-initialize) the agent AFTER a repo loads so it captures
      // the current codebase context (file contents + graph tools) in the worker.
      if (getActiveProviderConfig()) {
        initializeAgent(projectName);
      }

      // Auto-start embeddings pipeline in background
      // Uses WebGPU if available, falls back to WASM
      startEmbeddings().catch((err) => {
        if (err?.name === 'WebGPUNotAvailableError' || err?.message?.includes('WebGPU')) {
          startEmbeddings('wasm').catch(console.warn);
        } else {
         console.warn('Embeddings auto-start failed:', err);
        }
      });
    } catch (error) {
      console.error('Pipeline error:', error);
      setProgress({
        phase: 'error',
        percent: 0,
        message: '文件处理失败',
        detail: error instanceof Error ? error.message : '未知错误',
      });
      setTimeout(() => {
        setViewMode('onboarding');
        setProgress(null);
      }, 3000);
    }
  }, [setViewMode, setGraph, setFileContents, setProgress, setProjectName, runPipeline, startEmbeddings, initializeAgent]);

  const handleGitClone = useCallback(async (files: FileEntry[]) => {
    const firstPath = files[0]?.path || 'repository';
    const projectName = firstPath.split('/')[0].replace(/-\d+$/, '') || 'repository';

    setProjectName(projectName);
    setProgress({ phase: 'extracting', percent: 0, message: '开始处理…', detail: '正在准备仓库文件' });
    setViewMode('loading');

    try {
      const result = await runPipelineFromFiles(files, (progress) => {
        setProgress(progress);
      });

      setGraph(result.graph);
      setFileContents(result.fileContents);
      setViewMode('exploring');

      if (getActiveProviderConfig()) {
        initializeAgent(projectName);
      }

      startEmbeddings().catch((err) => {
        if (err?.name === 'WebGPUNotAvailableError' || err?.message?.includes('WebGPU')) {
          startEmbeddings('wasm').catch(console.warn);
        } else {
          console.warn('Embeddings auto-start failed:', err);
        }
      });
    } catch (error) {
      console.error('Pipeline error:', error);
      setProgress({
        phase: 'error',
        percent: 0,
        message: '仓库处理失败',
        detail: error instanceof Error ? error.message : '未知错误',
      });
      setTimeout(() => {
        setViewMode('onboarding');
        setProgress(null);
      }, 3000);
    }
  }, [setViewMode, setGraph, setFileContents, setProgress, setProjectName, runPipelineFromFiles, startEmbeddings, initializeAgent]);

  const handleServerConnect = useCallback((result: ConnectToServerResult) => {
    // Extract project name from repoPath
    const repoPath = result.repoInfo.repoPath;
    const normalizedRepoPath = repoPath.replace(/\\/g, '/');
    const projectName = result.repoInfo.name || normalizedRepoPath.split('/').filter(Boolean).pop() || 'server-project';
    setProjectName(projectName);

    // Build KnowledgeGraph from server data (bypasses WASM pipeline entirely)
    const graph = createKnowledgeGraph();
    for (const node of result.nodes) {
      graph.addNode(node);
    }
    for (const rel of result.relationships) {
      graph.addRelationship(rel);
    }
    setGraph(graph);

    // Set file contents from extracted File node content
    const fileMap = new Map<string, string>();
    for (const [path, content] of Object.entries(result.fileContents)) {
      fileMap.set(path, content);
    }
    setFileContents(fileMap);

    // Transition directly to exploring view
    setViewMode('exploring');

    // Initialize agent if LLM is configured
    if (getActiveProviderConfig()) {
      initializeAgent(projectName);
    }

    // Auto-start embeddings
    startEmbeddings().catch((err) => {
      if (err?.name === 'WebGPUNotAvailableError' || err?.message?.includes('WebGPU')) {
        startEmbeddings('wasm').catch(console.warn);
      } else {
        console.warn('Embeddings auto-start failed:', err);
      }
    });

    // Only start a new workbench session when experience library is not ready.
    // This avoids regressing historical completed projects to a transient running state.
    createGraphExtensionsApi.fetchWorkbenchProjectStatus('/api', repoPath)
      .then((status) => {
        const alreadyReady = status.experienceReady || status.status === 'completed';
        const alreadyRunning = status.status === 'running' || status.status === 'starting';
        if (alreadyReady || alreadyRunning) {
          return;
        }
        return createGraphExtensionsApi.startWorkbenchSession('/api', { project_path: repoPath });
      })
      .catch(() => {
        // If status lookup fails, keep best-effort behavior and attempt background bootstrap.
        return createGraphExtensionsApi.startWorkbenchSession('/api', { project_path: repoPath });
      })
      .catch(() => {
        // Silently ignore — hierarchy data is best-effort, graph is already loaded.
      });
  }, [setViewMode, setGraph, setFileContents, setProjectName, initializeAgent, startEmbeddings]);

  // Auto-connect when ?server query param is present (bookmarkable shortcut)
  const autoConnectRan = useRef(false);
  useEffect(() => {
    if (autoConnectRan.current) return;
    const params = new URLSearchParams(window.location.search);
    if (!params.has('server')) return;
    autoConnectRan.current = true;

    // Clean the URL so a refresh won't re-trigger
    const cleanUrl = window.location.pathname + window.location.hash;
    window.history.replaceState(null, '', cleanUrl);

    setProgress({ phase: 'extracting', percent: 0, message: '正在连接服务…', detail: '正在校验服务可用性' });
    setViewMode('loading');

    const serverUrl = params.get('server') || window.location.origin;

    const baseUrl = normalizeServerUrl(serverUrl);

    connectToServer(serverUrl, (phase, downloaded, total) => {
      if (phase === 'validating') {
          setProgress({ phase: 'extracting', percent: 5, message: '正在连接服务…', detail: '正在校验服务可用性' });
      } else if (phase === 'downloading') {
        const pct = total ? Math.round((downloaded / total) * 90) + 5 : 50;
        const mb = (downloaded / (1024 * 1024)).toFixed(1);
          setProgress({ phase: 'extracting', percent: pct, message: '正在下载图谱…', detail: `已下载 ${mb} MB` });
      } else if (phase === 'extracting') {
          setProgress({ phase: 'extracting', percent: 97, message: '正在整理数据…', detail: '正在提取文件内容' });
      }
    }).then(async (result) => {
      // Ensure server context is ready before app initialization logic.
      setServerBaseUrl(baseUrl);
      try {
        const repos = await fetchRepos(baseUrl);
        setAvailableRepos(repos);
      } catch (e) {
        console.warn('Failed to fetch repo list:', e);
      }

      handleServerConnect(result);
    }).catch((err) => {
      console.error('Auto-connect failed:', err);
      setProgress({
        phase: 'error',
        percent: 0,
        message: '连接服务失败',
        detail: err instanceof Error ? err.message : '未知错误',
      });
      setTimeout(() => {
        setViewMode('onboarding');
        setProgress(null);
      }, 3000);
    });
  }, [handleServerConnect, setProgress, setViewMode, setServerBaseUrl, setAvailableRepos]);

  const handleFocusNode = useCallback((nodeId: string) => {
    graphCanvasRef.current?.focusNode(nodeId);
  }, []);

  // Handle settings saved - refresh and reinitialize agent
  // NOTE: Must be defined BEFORE any conditional returns (React hooks rule)
  const handleSettingsSaved = useCallback(() => {
    refreshLLMSettings();
    initializeAgent();
  }, [refreshLLMSettings, initializeAgent]);

  // Render based on view mode
  if (viewMode === 'onboarding') {
    return (
            <DropZone
              onFileSelect={handleFileSelect}
              onGitClone={handleGitClone}
              onServerConnectStart={(message) => {
                setProgress({
                  phase: 'extracting',
                  percent: 5,
                  message: message || '正在连接服务…',
                  detail: '正在校验服务可用性',
                });
                setViewMode('loading');
              }}
              onServerConnect={async (result, serverUrl) => {
                if (serverUrl) {
                  const baseUrl = normalizeServerUrl(serverUrl);
                  setServerBaseUrl(baseUrl);
                  try {
                    const repos = await fetchRepos(baseUrl);
                    setAvailableRepos(repos);
                  } catch (e) {
                    console.warn('Failed to fetch repo list:', e);
                  }
                }
                handleServerConnect(result);
              }}
            />
    );
  }

  if (viewMode === 'loading' && progress) {
    return <LoadingOverlay progress={progress} />;
  }

  // Exploring view
  return (
    <div className="flex flex-col h-screen bg-void overflow-hidden">
      <Header onFocusNode={handleFocusNode} availableRepos={availableRepos} onSwitchRepo={switchRepo} />

      <main className="flex-1 flex min-h-0">
        {/* Left Panel - File Tree */}
        <FileTreePanel onFocusNode={handleFocusNode} />

        {/* Graph area - takes remaining space */}
        <div className="flex-1 relative min-w-0">
          <GraphCanvas ref={graphCanvasRef} />

          {/* Code References Panel (overlay) - does NOT resize the graph, it overlaps on top */}
          {isCodePanelOpen && (codeReferences.length > 0 || !!selectedNode) && (
            <div className="absolute inset-y-0 left-0 z-30 pointer-events-auto">
              <CodeReferencesPanel onFocusNode={handleFocusNode} />
            </div>
          )}
        </div>

        {/* Right Panel - Code & Chat (tabbed) */}
        {isRightPanelOpen && <RightPanel />}
      </main>

      <StatusBar />

      {/* Settings Panel (modal) */}
      <SettingsPanel
        isOpen={isSettingsPanelOpen}
        onClose={() => setSettingsPanelOpen(false)}
        onSettingsSaved={handleSettingsSaved}
      />

    </div>
  );
};

function App() {
  return (
    <AppStateProvider>
      <AppContent />
    </AppStateProvider>
  );
}

export default App;
