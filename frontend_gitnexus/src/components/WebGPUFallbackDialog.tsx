import { useState, useEffect } from 'react';
import { X, Snail, Rocket, SkipForward } from 'lucide-react';

interface WebGPUFallbackDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onUseCPU: () => void;
  onSkip: () => void;
  nodeCount: number;
}

/**
 * Fun dialog shown when WebGPU isn't available
 * Lets user choose: CPU fallback (slow) or skip embeddings
 */
export const WebGPUFallbackDialog = ({
  isOpen,
  onClose,
  onUseCPU,
  onSkip,
  nodeCount,
}: WebGPUFallbackDialogProps) => {
  const [isAnimating, setIsAnimating] = useState(true);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (isOpen) {
      // Trigger animation after mount
      requestAnimationFrame(() => setIsVisible(true));
    } else {
      setIsVisible(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Estimate time based on node count (rough: ~50ms per node on CPU)
  const estimatedMinutes = Math.ceil((nodeCount * 50) / 60000);
  const isSmallCodebase = nodeCount < 200;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <button
        type="button"
        className={`absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-200 ${isVisible ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
        aria-label="关闭弹窗"
      />
      
      {/* Dialog */}
      <div 
        className={`relative bg-surface border border-border-subtle rounded-2xl shadow-2xl max-w-md w-full mx-4 overflow-hidden transition-all duration-200 ${isVisible ? 'opacity-100 scale-100' : 'opacity-0 scale-95'}`}
      >
        {/* Header with scratching emoji */}
        <div className="relative bg-gradient-to-r from-amber-500/20 to-orange-500/20 px-6 py-5 border-b border-border-subtle">
          <button
            type="button"
            onClick={onClose}
            className="absolute top-4 right-4 p-1 text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
          
          <div className="flex items-center gap-4">
            {/* Animated emoji */}
            <button
              type="button"
              className={`text-5xl ${isAnimating ? 'animate-bounce' : ''}`}
              onAnimationEnd={() => setIsAnimating(false)}
              onClick={() => setIsAnimating(true)}
              aria-label="重新播放动效"
            >
              🤔
            </button>
            <div>
              <h2 className="text-lg font-semibold text-text-primary">
                当前环境不支持 WebGPU
              </h2>
              <p className="text-sm text-text-muted mt-0.5">
                浏览器暂时无法使用 GPU 加速
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-4">
          <p className="text-sm text-text-secondary leading-relaxed">
            当前无法通过 WebGPU 生成向量，因此语义检索能力会受限；但图谱浏览和结构分析仍可正常使用。
          </p>
          
          <div className="bg-elevated/50 rounded-lg p-4 border border-border-subtle">
            <p className="text-sm text-text-secondary">
                <span className="font-medium text-text-primary">你可以这样处理：</span>
            </p>
            <ul className="mt-2 space-y-1.5 text-sm text-text-muted">
              <li className="flex items-start gap-2">
                <Snail className="w-4 h-4 mt-0.5 text-amber-400 flex-shrink-0" />
                <span>
                  <strong className="text-text-secondary">改用 CPU</strong> — 可以继续运行，但会{isSmallCodebase ? '稍慢一些' : '明显更慢'}
                  {nodeCount > 0 && (
                    <span className="text-text-muted">（约 {estimatedMinutes} 分钟 / {nodeCount} 个节点）</span>
                  )}
                </span>
              </li>
              <li className="flex items-start gap-2">
                <SkipForward className="w-4 h-4 mt-0.5 text-blue-400 flex-shrink-0" />
                <span>
                  <strong className="text-text-secondary">先跳过</strong> — 图谱仍可使用，只是暂时没有语义检索
                </span>
              </li>
            </ul>
          </div>

          {isSmallCodebase && (
            <p className="text-xs text-node-function flex items-center gap-1.5 bg-node-function/10 px-3 py-2 rounded-lg">
              <Rocket className="w-3.5 h-3.5" />
              当前仓库规模较小，改用 CPU 一般也能接受。
            </p>
          )}

          <p className="text-xs text-text-muted">
            💡 建议优先使用 Chrome 或 Edge 以获得更好的 WebGPU 支持
          </p>
        </div>

        {/* Actions */}
        <div className="px-6 py-4 bg-elevated/30 border-t border-border-subtle flex gap-3">
          <button
            type="button"
            onClick={onSkip}
            className="flex-1 px-4 py-2.5 text-sm font-medium text-text-secondary bg-surface border border-border-subtle rounded-lg hover:bg-hover hover:text-text-primary transition-all flex items-center justify-center gap-2"
          >
            <SkipForward className="w-4 h-4" />
            跳过向量生成
          </button>
          <button
            type="button"
            onClick={onUseCPU}
            className={`flex-1 px-4 py-2.5 text-sm font-medium rounded-lg transition-all flex items-center justify-center gap-2 ${
              isSmallCodebase
                ? 'bg-node-function text-white hover:bg-node-function/90'
                : 'bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30'
            }`}
          >
            <Snail className="w-4 h-4" />
            改用 CPU {isSmallCodebase ? '（推荐）' : '（较慢）'}
          </button>
        </div>
      </div>
    </div>
  );
};
