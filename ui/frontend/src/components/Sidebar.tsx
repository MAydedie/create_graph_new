import React from 'react';
import { MessageSquarePlus, MessageSquare, PanelLeftClose, PanelLeftOpen, Trash2 } from 'lucide-react';

export interface ConversationItem {
  id: string;
  title: string;
}

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  conversations: ConversationItem[];
  currentConversationId: string | null;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation?: (id: string, e: React.MouseEvent) => void;
  width: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  isOpen,
  onToggle,
  conversations,
  currentConversationId,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
  width,
}) => {
  const sidebarStyle: React.CSSProperties = {
    width: isOpen ? width : 0,
    height: '100%',
    flexShrink: 0,
    overflow: 'hidden',
    borderRight: '1px solid #e5e6eb',
    background: '#f2f3f5',
    display: 'flex',
    flexDirection: 'column',
    transition: 'width 0.3s ease',
  };

  return (
    <>
      <aside style={sidebarStyle}>
        {isOpen && (
          <>
            <div
              style={{
                height: 56,
                padding: '0 12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                borderBottom: '1px solid #e5e6eb',
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 15, fontWeight: 500, color: '#1f2329' }}>对话</span>
              <button
                type="button"
                onClick={onToggle}
                style={{
                  padding: 8,
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  color: '#8f959e',
                  borderRadius: 8,
                }}
                title="收起侧边栏"
              >
                <PanelLeftClose size={20} />
              </button>
            </div>
            <div style={{ padding: 12, flexShrink: 0 }}>
              <button
                type="button"
                onClick={onNewChat}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  padding: '10px 16px',
                  borderRadius: 12,
                  background: '#3370ff',
                  color: '#fff',
                  border: 'none',
                  fontSize: 14,
                  fontWeight: 500,
                  cursor: 'pointer',
                }}
              >
                <MessageSquarePlus size={18} />
                新对话
              </button>
            </div>
            <div
              style={{
                flex: 1,
                minHeight: 0,
                overflowY: 'auto',
                padding: '8px 8px 16px',
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 500, color: '#8f959e', padding: '8px 12px' }}>
                历史对话
              </div>
              {conversations.length === 0 ? (
                <div style={{ padding: '16px 12px', fontSize: 13, color: '#8f959e', textAlign: 'center' }}>
                  暂无历史，点击「新对话」开始
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {conversations.map((item) => (
                    <div
                      key={item.id}
                      style={{
                        width: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '6px 12px',
                        borderRadius: 12,
                        border: currentConversationId === item.id ? '1px solid #e5e6eb' : '1px solid transparent',
                        background: currentConversationId === item.id ? '#fff' : 'transparent',
                        boxShadow: currentConversationId === item.id ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => onSelectConversation(item.id)}
                        style={{
                          flex: 1,
                          minWidth: 0,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 12,
                          padding: '4px 0',
                          border: 'none',
                          background: 'none',
                          color: currentConversationId === item.id ? '#3370ff' : '#1f2329',
                          fontSize: 13,
                          textAlign: 'left',
                          cursor: 'pointer',
                          overflow: 'hidden',
                        }}
                      >
                        <MessageSquare size={16} style={{ opacity: 0.8, flexShrink: 0 }} />
                        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {item.title || '未命名对话'}
                        </span>
                      </button>
                      {onDeleteConversation && (
                        <button
                          type="button"
                          onClick={(e) => onDeleteConversation(item.id, e)}
                          title="删除该对话"
                          style={{
                            padding: 4,
                            border: 'none',
                            background: 'none',
                            color: '#8f959e',
                            cursor: 'pointer',
                            borderRadius: 6,
                            flexShrink: 0,
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </aside>

      {!isOpen && (
        <button
          type="button"
          onClick={onToggle}
          style={{
            position: 'fixed',
            left: 12,
            top: 16,
            zIndex: 30,
            padding: 8,
            borderRadius: 8,
            background: '#fff',
            border: '1px solid #e5e6eb',
            color: '#8f959e',
            cursor: 'pointer',
            boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
          }}
          title="展开侧边栏"
        >
          <PanelLeftOpen size={20} />
        </button>
      )}
    </>
  );
};
