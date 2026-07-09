/**
 * SlashCommandMenu
 *
 * 仿 opencode CLI 反斜框风格的命令选择器。
 * 当用户在 chat textarea 中输入 `/` 时立刻浮出，呈现 skills 二级菜单：
 *   - 输入 `/` 或 `/<任何非空字符>` → 列出已导入的具体 Skill（huangqing / jinzhi / se-team 等）
 *   - 不再提供 `/models` 一级命令入口
 *
 * 设计原则：
 *  - 选中的项以纯文本形式插入到 textarea 中（替换用户已经输入的 `/xxx`），
 *    这样用户能在对话框里看到自己选了哪个 skill，
 *    不需要后端做特殊 token 解析。
 *  - skill 列表来自后端 GET /api/skills/persona/list
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Brain, Loader2, Sparkles, Wand2, X } from 'lucide-react';

export type SlashCommandKind = 'skill';

export interface SlashCommandItem {
  id: string;
  label: string;
  description?: string;
}

export interface SlashCommandMenuProps {
  /** 触发检测：当前是哪种命令（null = 不显示） */
  activeKind: SlashCommandKind | null;
  /** 当前输入的命令前缀（用于过滤列表），比如 /huang */
  activeQuery: string;
  /** 选中某项后回调，外部负责替换 textarea 内容 */
  onSelect: (kind: SlashCommandKind, item: SlashCommandItem) => void;
  /** 关闭弹窗 */
  onClose: () => void;
}

interface SkillApiItem {
  personaId: string;
  name: string;
  description?: string;
  active?: boolean;
}

/** 内置项：与已导入 skill 并列显示的"SE-Team 顾问智能体工作流" */
export const BUILTIN_SE_TEAM: SlashCommandItem = {
  id: 'se-team',
  label: 'SE-Team 顾问智能体工作流',
  description: '内置增强：需求顾问 + 架构顾问 + 代码顾问多智能体协作',
};

const NOOP: SlashCommandItem[] = [];

const getKindIcon = (_kind: SlashCommandKind) => {
  return <Sparkles className="w-3.5 h-3.5" />;
};

const getKindTitle = (_kind: SlashCommandKind) => {
  return 'Skills（角色 / 人设）';
};

export const SlashCommandMenu = ({
  activeKind,
  activeQuery,
  onSelect,
  onClose,
}: SlashCommandMenuProps) => {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [skills, setSkills] = useState<SkillApiItem[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // 拉取 skill 列表
  useEffect(() => {
    if (activeKind !== 'skill') return;
    if (skills.length > 0) return;
    let cancelled = false;
    const load = async () => {
      setSkillsLoading(true);
      setSkillsError(null);
      try {
        const res = await fetch('/api/skills/persona/list', { method: 'GET' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        const list: SkillApiItem[] = Array.isArray(data)
          ? data
          : Array.isArray((data as any)?.items)
            ? (data as any).items
            : [];
        setSkills(list);
      } catch (e) {
        if (cancelled) return;
        setSkillsError(e instanceof Error ? e.message : '加载 Skill 失败');
      } finally {
        if (!cancelled) setSkillsLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [activeKind, skills.length]);

  // 把 active 列表 + 过滤后的 items 计算出来
  // 内置项（se-team）始终在最前，与用户已导入的 skill 并列展示
  const filteredItems = useMemo<SlashCommandItem[]>(() => {
    if (!activeKind) return NOOP;
    const q = activeQuery.trim().toLowerCase();
    const builtin: SlashCommandItem[] = (() => {
      if (!q) return [BUILTIN_SE_TEAM];
      const hay =
        BUILTIN_SE_TEAM.id.toLowerCase() +
        ' ' +
        BUILTIN_SE_TEAM.label.toLowerCase() +
        ' ' +
        (BUILTIN_SE_TEAM.description || '').toLowerCase();
      return hay.includes(q) ? [BUILTIN_SE_TEAM] : [];
    })();
    const userItems: SlashCommandItem[] = skills
      .map((s) => ({
        id: s.personaId,
        label: s.name || s.personaId,
        description: s.description,
      }))
      .filter((it) => {
        if (!q) return true;
        return (
          it.id.toLowerCase().includes(q) ||
          it.label.toLowerCase().includes(q) ||
          (it.description || '').toLowerCase().includes(q)
        );
      });
    return [...builtin, ...userItems].slice(0, 12);
  }, [activeKind, activeQuery, skills]);

  // 切换 kind / query 时重置选中索引
  // biome-ignore lint/correctness/useExhaustiveDependencies: setSelectedIndex 引用稳定，且 effect 内只用到 activeKind/activeQuery
  useEffect(() => {
    setSelectedIndex(0);
  }, [activeKind, activeQuery]);

  // 键盘 ↑↓ Enter Escape 处理
  useEffect(() => {
    if (!activeKind) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        e.stopPropagation();
        setSelectedIndex((i) => Math.min(i + 1, Math.max(0, filteredItems.length - 1)));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        setSelectedIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === 'Enter') {
        // 这里我们故意不 preventDefault —— 让 Enter 也能继续走"发送"
        // 但如果确实有高亮项且不是空 query，则消费事件，插入选中项
        if (filteredItems.length > 0) {
          e.preventDefault();
          e.stopPropagation();
          const item = filteredItems[selectedIndex];
          if (item) onSelect(activeKind, item);
        }
      }
    };
    // 捕获阶段，防止父组件先吃掉 Enter
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [activeKind, filteredItems, selectedIndex, onSelect, onClose]);

  if (!activeKind) return null;

  const titleIcon = getKindIcon(activeKind);
  const titleText = getKindTitle(activeKind);
  const isLoading = skillsLoading;
  const errorText = skillsError;

  return (
    <div
      ref={menuRef}
      role="listbox"
      aria-label={titleText}
      className="absolute z-50 left-0 right-0 bottom-full mb-2 mx-3 rounded-xl border border-border-subtle bg-elevated/95 backdrop-blur shadow-2xl overflow-hidden"
      style={{ minWidth: 280, maxHeight: 320 }}
      onMouseDown={(e) => {
        // 防止点击菜单时 textarea 失焦
        e.preventDefault();
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle bg-surface/60">
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <span className="text-accent">{titleIcon}</span>
          <span className="font-medium">{titleText}</span>
          {activeQuery ? (
            <span className="text-[10px] text-text-muted">
              · 过滤 "{activeQuery.replace(/^\//, '')}"
            </span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="w-5 h-5 flex items-center justify-center text-text-muted hover:text-text-primary"
          title="关闭 (Esc)"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* List */}
      <div className="max-h-64 overflow-y-auto py-1">
        {isLoading ? (
          <div className="px-4 py-6 text-sm text-text-muted flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> 正在加载…
          </div>
        ) : errorText ? (
          <div className="px-4 py-4 text-sm text-rose-300">{errorText}</div>
        ) : filteredItems.length === 0 ? (
          <div className="px-4 py-6 text-sm text-text-muted text-center">
            还没有可用的 Skill，先去左下角「技能与角色管理」导入。
          </div>
        ) : (
          filteredItems.map((item, idx) => {
            const isSelected = idx === selectedIndex;
            const isBuiltin = item.id === BUILTIN_SE_TEAM.id;
            return (
              <button
                type="button"
                key={item.id}
                onMouseEnter={() => setSelectedIndex(idx)}
                onClick={() => onSelect(activeKind, item)}
                className={`w-full px-3 py-2 flex items-center gap-2 text-left transition-colors ${
                  isSelected
                    ? 'bg-accent/15 text-text-primary'
                    : 'hover:bg-hover text-text-secondary'
                }`}
              >
                {isBuiltin ? (
                  <Wand2 className="w-3.5 h-3.5 text-cyan-300 flex-shrink-0" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5 text-violet-300 flex-shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate flex items-center gap-1.5">
                    <span className="truncate">{item.label}</span>
                    {isBuiltin ? (
                      <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded border border-cyan-400/40 text-cyan-200 bg-cyan-500/15 flex-shrink-0 leading-tight">
                        内置增强
                      </span>
                    ) : null}
                  </div>
                  {item.description ? (
                    <div className="text-[11px] text-text-muted truncate">
                      {item.description}
                    </div>
                  ) : null}
                </div>
                <div className="text-[10px] text-text-muted font-mono flex-shrink-0 max-w-[40%] truncate">
                  {item.id}
                </div>
              </button>
            );
          })
        )}
      </div>

      {/* Footer hint */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t border-border-subtle bg-surface/40 text-[10px] text-text-muted">
        <div className="flex items-center gap-3">
          <span>
            <kbd className="px-1 py-0.5 bg-elevated border border-border-subtle rounded text-[9px]">↑</kbd>{' '}
            <kbd className="px-1 py-0.5 bg-elevated border border-border-subtle rounded text-[9px]">↓</kbd>{' '}
            浏览
          </span>
          <span>
            <kbd className="px-1 py-0.5 bg-elevated border border-border-subtle rounded text-[9px]">Enter</kbd>{' '}
            选择
          </span>
          <span>
            <kbd className="px-1 py-0.5 bg-elevated border border-border-subtle rounded text-[9px]">Esc</kbd>{' '}
            关闭
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Brain className="w-3 h-3" />
          {filteredItems.length} 项
        </div>
      </div>
    </div>
  );
};

/**
 * 解析 textarea 当前文本，提取出正在进行的 slash 命令。
 *
 * 单一模式：当前行是 `/xxx`（无空格或带空格）→ 进入 skill 二级菜单，
 *          列出后端已导入的所有具体 Skill。
 *
 * 规则：
 *  - 必须以 `/` 开头
 *  - 只在当前行（光标所在行）匹配
 *
 * 返回：
 *  - kind: 'skill' | null
 *  - query: 当前输入的过滤词（光标之前，去掉前导 / 和 skill 关键字）
 *  - start / end: 该命令在 textarea 中的字符区间（用于替换）
 */
export interface SlashParseResult {
  kind: SlashCommandKind | null;
  query: string;
  /** 命令在原文中的起始位置（含 /） */
  start: number;
  /** 命令在原文中的结束位置（不含） */
  end: number;
}

export const parseSlashCommand = (text: string, cursor: number): SlashParseResult => {
  const before = text.slice(0, cursor);
  // 找当前行：从上一个换行之后到光标
  const lineStart = before.lastIndexOf('\n') + 1;
  const linePrefix = before.slice(lineStart);

  // 单一模式：当前行是 `/xxx`（可以有空格后面带 query，也可以没有空格）
  // 例如：/, /h, /huangqing, /skill hu, /skill huangqing
  // 匹配规则：行首是 `/`，后面是非空字符（不含换行）直到光标
  const match = linePrefix.match(/^\/(\S*)$/);
  if (match) {
    let raw = match[1] || '';
    // 如果用户敲了 /skill / /models 这种历史前缀，剥掉它再作为 query
    if (/^skill$/i.test(raw)) {
      raw = '';
    } else if (/^skill\s+(.*)$/i.test(raw)) {
      // /skill hu → "hu"
      raw = raw.replace(/^skill\s+/i, '');
    } else if (/^models?$/i.test(raw)) {
      raw = '';
    }
    return {
      kind: 'skill',
      query: raw,
      start: lineStart,
      end: cursor,
    };
  }

  return { kind: null, query: '', start: -1, end: -1 };
};

/**
 * 把选中的项插入到 textarea 中。
 *  把整段 `/xxx` 替换为 `/<id>` —— 用户继续输入问题
 */
export const buildInsertedCommand = (
  _kind: SlashCommandKind,
  item: SlashCommandItem,
): string => {
  return `/${item.id}`;
};
