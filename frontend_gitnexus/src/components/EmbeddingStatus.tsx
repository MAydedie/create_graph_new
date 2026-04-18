import { Brain, Loader2, Check, AlertCircle, Zap, FlaskConical } from 'lucide-react';
import { useAppState } from '../hooks/useAppState';
import { useState } from 'react';
import { WebGPUFallbackDialog } from './WebGPUFallbackDialog';

/**
 * Embedding status indicator and trigger button
 * Shows in header when graph is loaded
 */
export const EmbeddingStatus = () => {
  const {
    embeddingStatus,
    embeddingProgress,
    startEmbeddings,
    graph,
    viewMode,
    serverBaseUrl,
    testArrayParams,
  } = useAppState();

  const [testResult, setTestResult] = useState<string | null>(null);
  const [showFallbackDialog, setShowFallbackDialog] = useState(false);

  // Only show when exploring a loaded graph; hide in backend mode (no WASM DB)
  if (viewMode !== 'exploring' || !graph || serverBaseUrl) return null;

  const nodeCount = graph.nodes.length;

  const handleStartEmbeddings = async (forceDevice?: 'webgpu' | 'wasm') => {
    try {
      await startEmbeddings(forceDevice);
    } catch (error: any) {
      // Check if it's a WebGPU not available error
      if (error?.name === 'WebGPUNotAvailableError' || 
          error?.message?.includes('WebGPU not available')) {
        setShowFallbackDialog(true);
      } else {
        console.error('Embedding failed:', error);
      }
    }
  };

  const handleUseCPU = () => {
    setShowFallbackDialog(false);
    handleStartEmbeddings('wasm');
  };

  const handleSkipEmbeddings = () => {
    setShowFallbackDialog(false);
    // Just close - user can try again later if they want
  };
  
  const handleTestArrayParams = async () => {
      setTestResult('测试中…');
    const result = await testArrayParams();
    if (result.success) {
       setTestResult('✅ 数组参数可用');
      console.log('✅ Array params test passed!');
    } else {
      setTestResult(`❌ ${result.error}`);
      console.error('❌ Array params test failed:', result.error);
    }
  };

  // WebGPU fallback dialog - rendered independently of state
  const fallbackDialog = (
    <WebGPUFallbackDialog
      isOpen={showFallbackDialog}
      onClose={() => setShowFallbackDialog(false)}
      onUseCPU={handleUseCPU}
      onSkip={handleSkipEmbeddings}
      nodeCount={nodeCount}
    />
  );

  // Idle state - show button to start
  if (embeddingStatus === 'idle') {
    return (
      <>
        <div className="flex items-center gap-2">
          {/* Test button (dev only) */}
          {import.meta.env.DEV && (
            <button
              type="button"
              onClick={handleTestArrayParams}
              className="flex items-center gap-1 px-2 py-1.5 bg-surface border border-border-subtle rounded-lg text-xs text-text-muted hover:bg-hover hover:text-text-secondary transition-all"
             title="测试 KuzuDB 是否支持数组参数"
            >
              <FlaskConical className="w-3 h-3" />
               {testResult || '测试'}
            </button>
          )}
          
          <button
            type="button"
            onClick={() => handleStartEmbeddings()}
            className="flex items-center gap-2 px-3 py-1.5 bg-surface border border-border-subtle rounded-lg text-sm text-text-secondary hover:bg-hover hover:text-text-primary hover:border-accent/50 transition-all group"
             title="生成语义检索向量"
          >
            <Brain className="w-4 h-4 text-node-interface group-hover:text-accent transition-colors" />
             <span className="hidden sm:inline">启用语义检索</span>
            <Zap className="w-3 h-3 text-text-muted" />
          </button>
        </div>
        {fallbackDialog}
      </>
    );
  }

  // Loading model
  if (embeddingStatus === 'loading') {
    const downloadPercent = embeddingProgress?.modelDownloadPercent ?? 0;
    return (
      <>
        <div className="flex items-center gap-2.5 px-3 py-1.5 bg-surface border border-accent/30 rounded-lg text-sm">
          <Loader2 className="w-4 h-4 text-accent animate-spin" />
          <div className="flex flex-col gap-0.5">
             <span className="text-text-secondary text-xs">正在加载模型…</span>
            <div className="w-24 h-1 bg-elevated rounded-full overflow-hidden">
              <div 
                className="h-full bg-gradient-to-r from-accent to-node-interface rounded-full transition-all duration-300"
                style={{ width: `${downloadPercent}%` }}
              />
            </div>
          </div>
        </div>
        {fallbackDialog}
      </>
    );
  }

  // Embedding in progress
  if (embeddingStatus === 'embedding') {
    const processed = embeddingProgress?.nodesProcessed ?? 0;
    const total = embeddingProgress?.totalNodes ?? 0;
    const percent = embeddingProgress?.percent ?? 0;
    
    return (
      <div className="flex items-center gap-2.5 px-3 py-1.5 bg-surface border border-node-function/30 rounded-lg text-sm">
        <Loader2 className="w-4 h-4 text-node-function animate-spin" />
        <div className="flex flex-col gap-0.5">
          <span className="text-text-secondary text-xs">
             正在生成向量 {processed}/{total}
          </span>
          <div className="w-24 h-1 bg-elevated rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-node-function to-accent rounded-full transition-all duration-300"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      </div>
    );
  }

  // Indexing
  if (embeddingStatus === 'indexing') {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-surface border border-node-interface/30 rounded-lg text-sm text-text-secondary">
        <Loader2 className="w-4 h-4 text-node-interface animate-spin" />
         <span className="text-xs">正在创建向量索引…</span>
      </div>
    );
  }

  // Ready
  if (embeddingStatus === 'ready') {
    return (
      <div 
        className="flex items-center gap-2 px-3 py-1.5 bg-node-function/10 border border-node-function/30 rounded-lg text-sm text-node-function"
         title="语义检索已就绪，可在 AI 面板中直接使用自然语言提问。"
      >
        <Check className="w-4 h-4" />
         <span className="text-xs font-medium">语义检索已就绪</span>
      </div>
    );
  }

  // Error
  if (embeddingStatus === 'error') {
    return (
      <>
        <button
          type="button"
          onClick={() => handleStartEmbeddings()}
          className="flex items-center gap-2 px-3 py-1.5 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400 hover:bg-red-500/20 transition-colors"
           title={embeddingProgress?.error || '向量生成失败，点击重试。'}
        >
          <AlertCircle className="w-4 h-4" />
           <span className="text-xs">失败，点击重试</span>
        </button>
        {fallbackDialog}
      </>
    );
  }

  return null;
};
