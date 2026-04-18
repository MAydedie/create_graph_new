import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { ChevronDown, ChevronRight, BrainCircuit, Loader2 } from 'lucide-react';
import clsx from 'clsx';

interface ThoughtProcessProps {
  content: string;
  agent: string;
  isStreaming?: boolean;
}

/** 思考步骤面板 - 浅色豆包风格，可折叠，流式时自动展开 */
export const ThoughtProcess: React.FC<ThoughtProcessProps> = ({
  content,
  agent,
  isStreaming,
}) => {
  const [isExpanded, setIsExpanded] = useState(isStreaming);

  useEffect(() => {
    if (isStreaming) setIsExpanded(true);
  }, [isStreaming]);

  return (
    <div className="thought-panel overflow-hidden transition-all duration-200">
      <button
        type="button"
        className="w-full flex items-center px-4 py-3 cursor-pointer hover:bg-[#e5e6eb]/50 transition-colors select-none text-left"
        onClick={() => setIsExpanded((e) => !e)}
      >
        <span className="text-[#8f959e] mr-2">
          {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
        <span className={clsx('mr-2', isStreaming && 'text-[#3370ff]')}>
          {isStreaming ? <Loader2 size={16} className="animate-spin" /> : <BrainCircuit size={16} />}
        </span>
        <span className="text-[13px] font-medium text-[#1f2329]">
          {agent} 思考过程
        </span>
      </button>

      {isExpanded && (
        <div className="px-4 py-3 bg-[#f7f8fa] text-[#1f2329] text-[13px] border-t border-[#e5e6eb] overflow-x-auto font-sans leading-relaxed">
          <ReactMarkdown
            components={{
              code({ node, inline, className, children, ...props }: any) {
                return (
                  <code
                    className={clsx(className, 'bg-[#e5e6eb] px-1 py-0.5 rounded text-[#3370ff]')}
                    {...props}
                  >
                    {children}
                  </code>
                );
              },
            }}
          >
            {content || '思考中…'}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
};
