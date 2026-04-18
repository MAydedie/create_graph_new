import { instance } from '@viz-js/viz';
import { useEffect, useRef, useState } from 'react';

interface GraphVizBlockProps {
  dotString: string;
  color: 'violet' | 'fuchsia' | 'emerald';
}

type GraphVizViewMode = 'diagram' | 'dot';

const VIZ_COLOR_MAP = {
  violet: { label: 'CFG', textClass: 'text-violet-300', bgClass: 'bg-violet-500/10', borderClass: 'border-violet-500/20' },
  fuchsia: { label: 'DFG', textClass: 'text-fuchsia-300', bgClass: 'bg-fuchsia-500/10', borderClass: 'border-fuchsia-500/20' },
  emerald: { label: 'IO', textClass: 'text-emerald-300', bgClass: 'bg-emerald-500/10', borderClass: 'border-emerald-500/20' },
};

type VizInstance = {
  render: (src: string, options?: { format?: string; engine?: string }) => { status: string; output?: string; errors: Array<{ message?: string }> };
};

let vizPromise: Promise<VizInstance> | null = null;

function getVizInstance() {
  if (!vizPromise) {
    vizPromise = instance().then((viz) => viz as unknown as VizInstance);
  }
  return vizPromise;
}

export function GraphVizBlock({ dotString, color }: GraphVizBlockProps) {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<GraphVizViewMode>('diagram');
  const [isRendering, setIsRendering] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const svgRef = useRef<HTMLDivElement>(null);
  const fsRef = useRef<HTMLDivElement>(null);
  const colorMap = VIZ_COLOR_MAP[color];

  useEffect(() => {
    let cancelled = false;
    setSvg('');
    setError(null);
    setIsRendering(true);
    setFullscreen(false);

    getVizInstance()
      .then((viz) => {
        if (cancelled) return;
        try {
          const result = viz.render(dotString, { format: 'svg', engine: 'dot' });
          if (result.status === 'success' && result.output && result.output.trim() !== '') {
            setSvg(result.output);
          } else {
            const errorMessages = (result.errors || [])
              .map((item: { message?: string }) => item.message || 'Unknown error')
              .join('; ');
            setError(errorMessages || 'Graphviz rendered empty output');
          }
        } catch (renderError) {
          if (!cancelled) setError(renderError instanceof Error ? renderError.message : String(renderError));
        } finally {
          if (!cancelled) setIsRendering(false);
        }
      })
      .catch((renderError) => {
        if (!cancelled) setError(renderError instanceof Error ? renderError.message : String(renderError));
        if (!cancelled) setIsRendering(false);
      });

    return () => {
      cancelled = true;
    };
  }, [dotString]);

  useEffect(() => {
    const element = svgRef.current;
    if (!element) return;
    element.innerHTML = svg;
    return () => {
      element.innerHTML = '';
    };
  }, [svg]);

  useEffect(() => {
    const element = fsRef.current;
    if (!element) return;
    element.innerHTML = svg;
    return () => {
      element.innerHTML = '';
    };
  }, [svg]);

  const showDiagram = viewMode === 'diagram';

  return (
    <div className="rounded-lg border border-border-subtle overflow-hidden">
      <div className={`px-2 py-1 text-[10px] uppercase tracking-wide ${colorMap.textClass} ${colorMap.bgClass} border-b ${colorMap.borderClass} flex items-center justify-between gap-2`}>
        <span>{colorMap.label}</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setViewMode('diagram')}
            className={`px-1.5 py-0.5 rounded border text-[9px] ${showDiagram
              ? 'border-cyan-400/60 text-cyan-200 bg-cyan-500/15'
              : 'border-border-subtle text-text-muted hover:text-text-primary hover:bg-elevated/60'
              }`}
          >
            Diagram
          </button>
          <button
            type="button"
            onClick={() => setViewMode('dot')}
            className={`px-1.5 py-0.5 rounded border text-[9px] ${!showDiagram
              ? 'border-cyan-400/60 text-cyan-200 bg-cyan-500/15'
              : 'border-border-subtle text-text-muted hover:text-text-primary hover:bg-elevated/60'
              }`}
          >
            DOT
          </button>
        </div>
      </div>

      <button
        type="button"
        className={`${fullscreen ? 'fixed inset-0 z-50 overflow-auto bg-black/95 cursor-zoom-out' : 'hidden'} border-0 p-0 m-0`}
        onDoubleClick={() => setFullscreen(false)}
        title="Double-click to exit fullscreen"
      >
        <div className="flex min-h-full min-w-full items-start justify-start p-6">
          <div
            className="h-max w-max [&>svg]:max-w-none [&>svg]:h-auto"
            ref={fsRef}
          />
        </div>
      </button>

      <div
        className="block w-full overflow-auto bg-[#0a0a10]"
        style={{ maxHeight: fullscreen ? 0 : 256 }}
      >
        {showDiagram ? (
          isRendering ? (
            <div className="px-3 py-2 text-[11px] text-text-muted">Rendering graph…</div>
          ) : error ? (
            <div className="px-3 py-2 space-y-2">
              <div className="text-[11px] text-rose-300">Graph render failed: {error}</div>
              <button
                type="button"
                onClick={() => setViewMode('dot')}
                className="px-2 py-1 text-[10px] rounded border border-rose-400/40 text-rose-200 bg-rose-500/15"
              >
                View DOT text
              </button>
            </div>
          ) : svg ? (
            <button
              type="button"
              className="block w-full cursor-zoom-in border-0 bg-transparent p-2 text-left [&>div>svg]:w-full [&>div>svg]:h-auto"
              onDoubleClick={() => setFullscreen(true)}
              title="Double-click to expand"
            >
              <div ref={svgRef} />
            </button>
          ) : (
            <div className="px-3 py-2 text-[11px] text-text-muted">No graph available</div>
          )
        ) : (
          <pre className="px-3 py-2 text-[11px] text-text-secondary overflow-x-auto whitespace-pre-wrap">{dotString}</pre>
        )}
      </div>
    </div>
  );
}
