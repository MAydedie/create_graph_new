import React, { useState, useRef, useEffect } from 'react';
import { Send, Square, Bot, User, PanelLeftOpen, Paperclip, Mic, Image } from 'lucide-react';
import { ThoughtProcess } from './ThoughtProcess';
import { useAutoScroll } from '../hooks/useAutoScroll';
import ReactMarkdown from 'react-markdown';
// @ts-ignore
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
// @ts-ignore
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { ActiveTaskView } from './ActiveTaskView';
import { StatusIndicator, AgentStatus } from './StatusIndicator';

interface ChatInterfaceProps {
  conversationId: string | null;
  taskId: string | null;
  isTaskStopped?: boolean;
  onStartTask: (goal: string) => void;
  onReset: () => void;
  events: any[];
  isSidebarOpen?: boolean;
  onToggleSidebar?: () => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  taskId,
  isTaskStopped,
  onStartTask,
  onReset,
  events,
  isSidebarOpen,
  onToggleSidebar,
}) => {
  const [input, setInput] = useState('');
  const scrollRef = useAutoScroll(events);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 150) + 'px';
    }
  }, [input]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim()) return;
    onStartTask(input.trim());
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const hasContent = events.length > 0 || taskId;

  const wrapperStyle: React.CSSProperties = {
    flex: 1,
    minHeight: 0,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: '#f7f8fa',
  };

  const scrollAreaStyle: React.CSSProperties = {
    flex: 1,
    minHeight: 0,
    overflowY: 'auto',
    padding: '24px 16px',
  };

  const inputAreaStyle: React.CSSProperties = {
    flexShrink: 0,
    padding: 16,
    borderTop: '1px solid #e5e6eb',
    background: '#f7f8fa',
  };

  return (
    <div style={wrapperStyle}>
      {!isSidebarOpen && onToggleSidebar && (
        <button
          type="button"
          onClick={onToggleSidebar}
          style={{
            position: 'absolute',
            top: 16,
            left: 16,
            zIndex: 30,
            padding: 8,
            borderRadius: 8,
            background: '#fff',
            border: '1px solid #e5e6eb',
            color: '#8f959e',
            cursor: 'pointer',
          }}
          title="展开侧边栏"
        >
          <PanelLeftOpen size={20} />
        </button>
      )}

      {/* Status Indicator */}
      {taskId && (
        <StatusIndicator
          status={
            events.some(e => e.type === 'task_complete' || e.event_type === 'task_complete') ? 'completed' :
              events.some(e => e.type === 'thought') && !events.some(e => e.type === 'plan_created') ? 'thinking' :
                events.some(e => e.type === 'step_start') ? 'executing' :
                  'idle'
          }
        />
      )}

      <div ref={scrollRef} style={scrollAreaStyle}>
        <div style={{ maxWidth: 768, margin: '0 auto', paddingTop: 24, paddingBottom: 160 }}>
          {!hasContent && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: 64 }}>
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: 16,
                  background: '#fff',
                  border: '1px solid #e5e6eb',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: 24,
                }}
              >
                <Bot size={32} style={{ color: '#3370ff' }} />
              </div>
              <h2 style={{ fontSize: 24, fontWeight: 700, color: '#1f2329', marginBottom: 8 }}>你好，我是你的助手</h2>
              <p style={{ fontSize: 14, color: '#8f959e', textAlign: 'center', maxWidth: 400, marginBottom: 40 }}>
                我可以帮你编写代码、分析项目、修复问题。试着问我一些问题吧。
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, width: '100%', maxWidth: 520 }}>
                {[
                  { icon: '📊', text: '创建一个 Python 命令行工具' },
                  { icon: '🛠️', text: '重构当前文件夹下的代码' },
                  { icon: '🐛', text: '分析并修复项目中的 Bug' },
                  { icon: '🧪', text: '为所有函数生成单元测试' },
                ].map((suggestion, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onStartTask(suggestion.text)}
                    style={{
                      padding: 16,
                      background: '#fff',
                      border: '1px solid #e5e6eb',
                      borderRadius: 12,
                      textAlign: 'left',
                      cursor: 'pointer',
                      fontSize: 14,
                      fontWeight: 500,
                      color: '#1f2329',
                    }}
                  >
                    <div style={{ fontSize: 18, marginBottom: 4 }}>{suggestion.icon}</div>
                    <div>{suggestion.text}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 始终使用新的 ActiveTaskView 展示任务与历史 */}
          {hasContent && (
            <ActiveTaskView
              userGoal={events.find(e => e.type === 'user_input' || e.event_type === 'user_input')?.summary || events.find(e => e.type === 'user_input' || e.event_type === 'user_input')?.details?.user_goal as string || '任务执行中'}
              events={events}
              status={taskId ? 'active' : 'stopped'}
            />
          )}
        </div>
      </div>

      <div style={inputAreaStyle}>
        <div style={{ maxWidth: 768, margin: '0 auto' }}>
          <div
            style={{
              background: '#fff',
              borderRadius: 16,
              border: '1px solid #e5e6eb',
              padding: '12px 16px',
              boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
            }}
          >
            <textarea
              ref={textareaRef}
              placeholder="输入你的问题…"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              style={{
                width: '100%',
                minHeight: 44,
                maxHeight: 160,
                padding: '12px 0',
                border: 'none',
                outline: 'none',
                resize: 'none',
                fontSize: 15,
                lineHeight: 1.5,
                color: '#1f2329',
                background: 'transparent',
              }}
            />
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingTop: 0,
                paddingBottom: 8,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <button type="button" style={{ padding: 8, border: 'none', background: 'none', cursor: 'pointer', color: '#8f959e' }} title="上传文件">
                  <Paperclip size={18} />
                </button>
                <button type="button" style={{ padding: 8, border: 'none', background: 'none', cursor: 'pointer', color: '#8f959e' }} title="语音输入">
                  <Mic size={18} />
                </button>
                <button type="button" style={{ padding: 8, border: 'none', background: 'none', cursor: 'pointer', color: '#8f959e' }} title="上传图片">
                  <Image size={18} />
                </button>
              </div>
              {taskId ? (
                <button
                  type="button"
                  onClick={onReset}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 16px',
                    background: '#fff1f0',
                    color: '#f5222d',
                    border: 'none',
                    borderRadius: 12,
                    fontSize: 14,
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  <Square size={16} />
                  停止
                </button>
              ) : (
                <button
                  type="button"
                  onClick={(e) => handleSubmit(e)}
                  disabled={!input.trim()}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 16px',
                    background: input.trim() ? '#3370ff' : '#e5e6eb',
                    color: input.trim() ? '#fff' : '#8f959e',
                    border: 'none',
                    borderRadius: 12,
                    fontSize: 14,
                    fontWeight: 500,
                    cursor: input.trim() ? 'pointer' : 'not-allowed',
                    opacity: input.trim() ? 1 : 0.7,
                  }}
                >
                  <Send size={16} />
                  发送
                </button>
              )}
            </div>
          </div>
          <p style={{ textAlign: 'center', marginTop: 8, fontSize: 11, color: '#8f959e' }}>内容由 AI 生成，请仔细甄别</p>
        </div>
      </div>
    </div>
  );
};
