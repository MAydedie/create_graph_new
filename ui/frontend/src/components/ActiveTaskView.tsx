import React, { useEffect, useRef, useState } from 'react';
import {
    CheckCircle2,
    Circle,
    Loader2,
    FileText,
    ChevronDown,
    ChevronRight,
    Terminal,
    Play,
    ExternalLink,
    Bot,
    AlertCircle,
    SkipForward
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
// @ts-ignore
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
// @ts-ignore
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';

import { ThoughtProcess } from './ThoughtProcess';
import { api } from '../services/api';

interface ActiveTaskViewProps {
    userGoal: string;
    events: any[];
    status: string;
}

export const ActiveTaskView: React.FC<ActiveTaskViewProps> = ({ userGoal, events, status }) => {
    // State to track expanded steps
    const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
    const scrollRef = useRef<HTMLDivElement>(null);

    // Derived state
    const thoughtEvent = events.find(e => e.type === 'thought' || e.event_type === 'thought');
    const planEvent = events.find(e => e.type === 'plan_created' || e.event_type === 'plan_created');
    const filesEvent = events.find(e => e.type === 'files_generated' || e.event_type === 'files_generated');
    const summaryEvent = events.find(e => e.type === 'final_summary' || e.event_type === 'final_summary');
    const quickAnswerEvent = events.find(e => e.type === 'quick_answer' || e.event_type === 'quick_answer');

    // Group events by step
    const steps = planEvent?.details?.plan?.steps || [];
    const stepEvents = events.filter(e =>
        ['step_start', 'step_complete', 'step_fail', 'retry', 'agent_thought', 'action'].includes(e.type || e.event_type) || e.agent
    );

    // Auto-expand current running step
    useEffect(() => {
        const lastEvent = events[events.length - 1];
        if (!lastEvent) return;
        const type = lastEvent.type || lastEvent.event_type;

        if (type === 'step_start') {
            const stepId = lastEvent.step_id;
            setExpandedSteps(prev => {
                const next = new Set(prev);
                next.add(stepId);
                return next;
            });
        }

        // Auto-scroll
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [events]);

    const toggleStep = (stepId: number) => {
        setExpandedSteps(prev => {
            const next = new Set(prev);
            if (next.has(stepId)) next.delete(stepId);
            else next.add(stepId);
            return next;
        });
    };

    // Helper to open file folder (Mock implementation for now, ideally calls backend)
    const openFolder = async (path: string) => {
        try {
            await api.openPath(path);
        } catch (e) {
            console.error("Failed to open path:", e);
        }
    };

    return (
        <div style={{ maxWidth: 800, margin: '0 auto', padding: '24px 16px', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif' }}>

            {/* 0. Header / User Goal */}
            <div style={{ marginBottom: 32 }}>
                <h1 style={{ fontSize: 24, fontWeight: 600, color: '#1f2329', marginBottom: 8 }}>
                    {userGoal}
                </h1>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                        width: 24, height: 24, borderRadius: '50%', background: '#3370ff',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff'
                    }}>
                        <Bot size={14} />
                    </div>
                    <span style={{ fontSize: 13, color: '#646a73' }}>AI Agent Active</span>
                </div>
            </div>

            {/* Quick Answer Display - 快速问答直接显示回答 */}
            {quickAnswerEvent && !planEvent && (
                <div style={{ marginBottom: 24, padding: 20, background: '#f0f8ff', borderRadius: 12, border: '1px solid #dbeafe' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#3370ff', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#3370ff' }}></div>
                        AI 回答
                    </div>
                    <div style={{ fontSize: 15, lineHeight: 1.6, color: '#1f2329', whiteSpace: 'pre-wrap' }}>
                        {quickAnswerEvent.summary || quickAnswerEvent.content || '正在生成回答...'}
                    </div>
                </div>
            )}

            {/* 1. Thought / Clarification (Original Single Thought) */}
            {thoughtEvent && (
                <div style={{ marginBottom: 24, padding: 20, background: '#f0f4ff', borderRadius: 12, border: '1px solid #dbeafe' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#3370ff', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#3370ff' }}></div>
                        THOUGHT PROCESS
                    </div>
                    <div style={{ fontSize: 15, lineHeight: 1.6, color: '#1f2329' }}>
                        {thoughtEvent.details?.thought || thoughtEvent.summary || thoughtEvent.content || '思考中...'}
                    </div>
                </div>
            )}

            {/* 2. & 3. Plan & Workflow Container */}
            {planEvent && (
                <div style={{ border: '1px solid #e5e6eb', borderRadius: 16, overflow: 'hidden', background: '#fff', boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}>

                    {/* Header with Files */}
                    <div style={{
                        padding: '16px 20px', background: '#f7f8fa', borderBottom: '1px solid #e5e6eb',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                    }}>
                        <div style={{ fontSize: 15, fontWeight: 600, color: '#1f2329' }}>Execution Plan</div>

                        {/* 6. File Links */}
                        {filesEvent && (
                            <div style={{ display: 'flex', gap: 12 }}>
                                {filesEvent.details?.files?.map((f: any, i: number) => (
                                    <button
                                        key={i}
                                        onClick={() => openFolder(f.path)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: 6, fontSize: 12,
                                            padding: '6px 10px', background: '#fff', border: '1px solid #e5e6eb', borderRadius: 6,
                                            cursor: 'pointer', color: '#646a73'
                                        }}>
                                        <FileText size={14} />
                                        {f.name}
                                        <ExternalLink size={12} />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* 4. Dynamic Steps */}
                    <div style={{ padding: '20px' }}>
                        {steps.map((step: any, index: number) => {
                            const stepId = step.step_id ?? index;
                            const eventsForStep = stepEvents.filter(e => e.step_id === stepId);

                            // Determine status
                            const isStarted = eventsForStep.some(e => ['step_start', 'step_complete', 'step_fail', 'step_skipped'].includes(e.type || e.event_type));
                            const isCompleted = eventsForStep.some(e => ['step_complete'].includes(e.type || e.event_type));
                            const isFailed = eventsForStep.some(e => ['step_fail'].includes(e.type || e.event_type));
                            const isSkipped = eventsForStep.some(e => ['step_skipped'].includes(e.type || e.event_type));
                            const isFixing = eventsForStep.some(e => ['error_resolution'].includes(e.type || e.event_type)) && !isCompleted && !isSkipped;

                            const isRunning = isStarted && !isCompleted && !isFailed && !isSkipped;

                            const isExpanded = expandedSteps.has(stepId) || isRunning || isFixing;

                            return (
                                <div key={stepId} style={{ marginBottom: 16 }}>
                                    {/* Step Header */}
                                    <div
                                        onClick={() => toggleStep(stepId)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: 12, padding: '12px',
                                            borderRadius: 8, cursor: 'pointer',
                                            background: isRunning ? '#f0f8ff' : 'transparent',
                                            border: isRunning ? '1px solid #bae6fd' : '1px solid transparent'
                                        }}>

                                        {/* Icon */}
                                        <div style={{ flexShrink: 0 }}>
                                            {isCompleted ? <CheckCircle2 size={20} color="#00c853" /> :
                                                isSkipped ? <SkipForward size={20} color="#faad14" /> :
                                                    isFailed ? <CheckCircle2 size={20} color="#f5222d" /> :
                                                        (isRunning || isFixing) ? <Loader2 size={20} className="animate-spin" color="#3370ff" /> :
                                                            <Circle size={20} color="#dfe1e5" />}
                                        </div>

                                        {/* Title */}
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontSize: 14, fontWeight: 500, color: isCompleted || isRunning ? '#1f2329' : '#8f959e' }}>
                                                Step {stepId + 1}: {step.description}
                                            </div>
                                        </div>

                                        {/* Chevron */}
                                        {isExpanded ? <ChevronDown size={18} color="#8f959e" /> : <ChevronRight size={18} color="#8f959e" />}
                                    </div>

                                    {/* 5. Logs / Actions (Inside plan box) */}
                                    {isExpanded && eventsForStep.length > 0 && (
                                        <div style={{ marginLeft: 44, marginTop: 8, paddingRight: 12 }}>
                                            {eventsForStep.map((evt, evtIdx) => {
                                                const type = evt.type || evt.event_type;

                                                // 1. Robot Dialogue (Planner/Critic/etc.)
                                                if (type === 'agent_thought' || type === 'chat' || evt.agent) {
                                                    return (
                                                        <div key={evtIdx} style={{ marginBottom: 12 }}>
                                                            <ThoughtProcess
                                                                agent={evt.agent || 'Assistant'}
                                                                content={evt.content || evt.details?.thought || evt.summary}
                                                                isStreaming={false}
                                                            />
                                                        </div>
                                                    );
                                                }

                                                if (type === 'error_resolution') {
                                                    return (
                                                        <div key={evtIdx} style={{
                                                            background: '#fff7e6',
                                                            border: '1px solid #ffd591',
                                                            borderRadius: 6,
                                                            padding: '8px 12px',
                                                            marginBottom: 8,
                                                            fontSize: 13,
                                                            color: '#d46b08',
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            gap: 8
                                                        }}>
                                                            <Loader2 size={14} className="animate-spin" />
                                                            <span>{evt.summary}</span>
                                                        </div>
                                                    );
                                                }

                                                if (type === 'step_skipped') {
                                                    return (
                                                        <div key={evtIdx} style={{
                                                            background: '#fffbe6',
                                                            border: '1px solid #ffe58f',
                                                            borderRadius: 6,
                                                            padding: '8px 12px',
                                                            marginBottom: 8,
                                                            fontSize: 13,
                                                            color: '#d48806',
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            gap: 8
                                                        }}>
                                                            <SkipForward size={14} />
                                                            <span>{evt.summary}</span>
                                                        </div>
                                                    );
                                                }

                                                return (
                                                    <div key={evtIdx} style={{ marginBottom: 8, fontSize: 13, fontFamily: 'monospace', color: '#646a73' }}>
                                                        <div style={{ display: 'flex', gap: 8 }}>
                                                            <span style={{ color: '#aaa' }}>[{new Date(evt.timestamp).toLocaleTimeString()}]</span>
                                                            <span>{evt.summary}</span>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* 5. Final Summary */}
            {summaryEvent && (
                <div style={{ marginTop: 32, padding: 24, background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 12 }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: '#389e0d', marginBottom: 12 }}>Task Completed</div>
                    <div style={{ fontSize: 15, lineHeight: 1.6, color: '#1f2329' }}>
                        <ReactMarkdown>{summaryEvent.details?.summary || summaryEvent.summary}</ReactMarkdown>
                    </div>
                </div>
            )}

            {/* Scroll anchor */}
            <div ref={scrollRef} style={{ height: 1 }} />

            <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .animate-spin {
          animation: spin 1s linear infinite;
        }
      `}</style>
        </div>
    );
};
