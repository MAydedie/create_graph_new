/** 单条事件（用户消息 / 系统步骤 / 思考流等） */
export interface ChatEvent {
  type: string;
  event_type?: string; // 兼容后端格式
  agent?: string;
  timestamp: string;
  summary?: string; // 改为可选字段
  content?: string; // 添加 content 字段
  details?: Record<string, unknown>;
  step_id?: number; // 添加 step_id 字段
  title?: string; // 添加 title 字段（用于 permission_request）
  description?: string; // 添加 description 字段
}

/** 单个对话会话 */
export interface Conversation {
  id: string;
  /** 历史标题：取该对话的第一条用户问题 */
  title: string;
  events: ChatEvent[];
  taskId: string | null;
  createdAt: number;
}

export const CONVERSATION_STORAGE_KEY = 'doubao_conversations';
export const CURRENT_CONVERSATION_ID_KEY = 'doubao_current_conversation_id';
