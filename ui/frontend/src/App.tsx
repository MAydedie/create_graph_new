import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatInterface } from './components/ChatInterface';
import { PermissionModal } from './components/PermissionModal';
import { api } from './services/api';
import { Loader2 } from 'lucide-react';
import type { Conversation, ChatEvent } from './types/chat';
import { CONVERSATION_STORAGE_KEY, CURRENT_CONVERSATION_ID_KEY } from './types/chat';

const DEFAULT_WORKSPACE = 'D:\\代码仓库生图\\create_graph\\test_sandbox\\finance_cli';
const SIDEBAR_OPEN_KEY = 'doubao_sidebar_open';
const SIDEBAR_WIDTH = 260;

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(CONVERSATION_STORAGE_KEY);
    const conversations = raw ? JSON.parse(raw) : [];
    // Sanitize: Filter out invalid events - only require type or event_type
    return conversations.map((c: any) => ({
      ...c,
      events: Array.isArray(c.events) ? c.events.filter((e: any) =>
        // 只要有 type 或 event_type 就认为是有效事件
        e && (e.type || e.event_type)
      ) : []
    }));
  } catch (err) {
    console.error('Failed to load conversations:', err);
    // 如果加载失败，清除损坏的数据
    localStorage.removeItem(CONVERSATION_STORAGE_KEY);
    return [];
  }
}

function saveConversations(list: Conversation[]) {
  try {
    localStorage.setItem(CONVERSATION_STORAGE_KEY, JSON.stringify(list));
  } catch (_) { }
}

function generateId() {
  return 'conv_' + Date.now() + '_' + Math.random().toString(36).slice(2, 9);
}

function App() {
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations());
  const [currentId, setCurrentId] = useState<string | null>(() => {
    const id = localStorage.getItem(CURRENT_CONVERSATION_ID_KEY);
    return id && loadConversations().some((c) => c.id === id) ? id : null;
  });
  const [workspace, setWorkspace] = useState(DEFAULT_WORKSPACE);
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => localStorage.getItem(SIDEBAR_OPEN_KEY) !== 'false');
  const [permissionRequest, setPermissionRequest] = useState<{ title: string; description: string } | null>(null);

  useEffect(() => {
    const s = localStorage.getItem('workspace_root');
    if (s) setWorkspace(s);
  }, []);
  useEffect(() => {
    localStorage.setItem(SIDEBAR_OPEN_KEY, String(isSidebarOpen));
  }, [isSidebarOpen]);

  const current = conversations.find((c) => c.id === currentId) ?? null;
  const taskId = current?.taskId ?? null;
  const events = current?.events ?? [];
  const [isTaskStopped, setIsTaskStopped] = useState(false);

  const setCurrentConversation = useCallback((conv: Conversation | null) => {
    if (conv) {
      setCurrentId(conv.id);
      localStorage.setItem(CURRENT_CONVERSATION_ID_KEY, conv.id);
    } else {
      setCurrentId(null);
      localStorage.removeItem(CURRENT_CONVERSATION_ID_KEY);
    }
  }, []);

  const updateConversation = useCallback((id: string, updater: (c: Conversation) => Conversation) => {
    setConversations((prev) => {
      const next = prev.map((c) => (c.id === id ? updater(c) : c));
      saveConversations(next);
      return next;
    });
  }, []);

  const addEvent = useCallback(
    (convId: string, event: ChatEvent) => {
      updateConversation(convId, (c) => ({ ...c, events: [...c.events, event] }));
    },
    [updateConversation]
  );

  const setEvents = useCallback(
    (convId: string, newEvents: ChatEvent[]) => {
      updateConversation(convId, (c) => ({
        ...c,
        events: newEvents,
        title: c.title || newEvents.find((e) => e.type === 'user_input')?.summary?.slice(0, 30) || '未命名对话',
      }));
    },
    [updateConversation]
  );

  const setTaskId = useCallback(
    (convId: string, tid: string | null) => {
      updateConversation(convId, (c) => ({ ...c, taskId: tid }));
    },
    [updateConversation]
  );

  useEffect(() => {
    if (!currentId || !taskId) return;
    const ws = new WebSocket(api.getWebSocketUrl(taskId));
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'event') {
          const data = msg.data;
          if (data?.event_type && !data?.type) data.type = data.event_type;
          addEvent(currentId, data);
          if (data?.type === 'permission_request') {
            setPermissionRequest({
              title: data.title || '请求权限',
              description: data.description || data.summary || '需要您的授权才能继续操作。',
            });
          }
        } else if (msg.type === 'status' && (msg.data === 'completed' || msg.data === 'failed')) {
          // 不再立即清空 taskId/关闭 WebSocket，避免丢失最后的 final_summary 事件
          // 状态展示依赖事件流中的 task_complete / step 状态即可
        }
      } catch (_) { }
    };
    ws.onerror = () => setTaskId(currentId, null);
    return () => ws.close();
  }, [currentId, taskId, addEvent, setTaskId]);

  const handleNewChat = useCallback(() => {
    const conv: Conversation = { id: generateId(), title: '', events: [], taskId: null, createdAt: Date.now() };
    setConversations((prev) => {
      const next = [conv, ...prev];
      saveConversations(next);
      return next;
    });
    setCurrentConversation(conv);
  }, [setCurrentConversation]);

  const handleSelectConversation = useCallback(
    (id: string) => {
      const c = conversations.find((x) => x.id === id);
      if (c) setCurrentConversation(c);
    },
    [conversations, setCurrentConversation]
  );

  const handleDeleteConversation = useCallback(
    (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        saveConversations(next);
        return next;
      });
      if (currentId === id) {
        setCurrentId(null);
        localStorage.removeItem(CURRENT_CONVERSATION_ID_KEY);
      }
    },
    [currentId]
  );

  const handleStartTask = useCallback(
    async (goal: string) => {
      // If task was stopped or completed, create a new conversation
      let conv = current;
      if (!conv || isTaskStopped || (conv.events.some(e => e.type === 'task_complete' || e.event_type === 'task_complete'))) {
        conv = {
          id: generateId(),
          title: goal.slice(0, 50) || '新对话',
          events: [],
          taskId: null,
          createdAt: Date.now(),
        };
        setConversations((prev) => {
          const next = [conv!, ...prev];
          saveConversations(next);
          return next;
        });
        setCurrentConversation(conv);
        setIsTaskStopped(false);
      }
      const userEvent: ChatEvent = {
        type: 'user_input',
        agent: 'user',
        timestamp: new Date().toISOString(),
        summary: goal,
        details: { user_goal: goal },
      };
      setEvents(conv.id, [...conv.events, userEvent]);
      updateConversation(conv.id, (c) => ({ ...c, title: c.title || goal.slice(0, 50) || '未命名对话' }));
      try {
        const res = await api.startChat(goal, workspace);
        setTaskId(conv.id, res.task_id);
      } catch (err) {
        addEvent(conv.id, {
          type: 'step_fail',
          agent: 'system',
          timestamp: new Date().toISOString(),
          summary: `启动失败：${err}`,
        });
        setTaskId(conv.id, null);
      }
    },
    [current, workspace, setEvents, updateConversation, addEvent, setTaskId, setCurrentConversation]
  );

  const handleReset = useCallback(() => {
    if (currentId) {
      setTaskId(currentId, null);
      setIsTaskStopped(true);
    }
  }, [currentId, setTaskId]);

  const sidebarList = conversations.map((c) => ({ id: c.id, title: c.title || '未命名对话' }));

  return (
    <div
      style={{
        display: 'flex',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        background: '#f7f8fa',
      }}
    >
      <Sidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen((o) => !o)}
        conversations={sidebarList}
        currentConversationId={currentId}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        width={SIDEBAR_WIDTH}
      />

      <main
        style={{
          flex: 1,
          minWidth: 0,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: '#fff',
          borderLeft: '1px solid #e5e6eb',
        }}
      >
        {taskId && (
          <div
            style={{
              position: 'absolute',
              top: 16,
              right: 16,
              zIndex: 20,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 12px',
              background: '#fff',
              border: '1px solid #e5e6eb',
              borderRadius: 999,
              fontSize: 12,
              color: '#8f959e',
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#00c853' }} />
            <span>已连接</span>
            <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />
          </div>
        )}
        <ChatInterface
          conversationId={currentId}
          taskId={taskId}
          isTaskStopped={isTaskStopped}
          onStartTask={handleStartTask}
          onReset={handleReset}
          events={events}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen((o) => !o)}
        />
      </main>

      <PermissionModal
        isOpen={!!permissionRequest}
        title={permissionRequest?.title ?? ''}
        description={permissionRequest?.description ?? ''}
        onAllow={() => setPermissionRequest(null)}
        onReject={() => setPermissionRequest(null)}
        onAllowInConversation={() => setPermissionRequest(null)}
      />
    </div>
  );
}

export default App;
