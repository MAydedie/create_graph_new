import { describe, expect, it } from 'vitest';

import {
  extractLatestAssistantAnswer,
  planConversationTerminalRecoveryDelays,
  planRagConversationContinuation,
  toRagResponseFromConversationMessages,
} from './right-panel-conversation-recovery';

describe('right-panel conversation recovery', () => {
  it('prefers the latest assistant_text part when recovering an answer', () => {
    const payload = {
      conversationId: 'conversation-1',
      messages: [
        { role: 'assistant', content: 'older answer' },
      ],
      parts: [
        { type: 'assistant_text', content: 'latest recovered answer' },
      ],
    };

    expect(extractLatestAssistantAnswer(payload)).toBe('latest recovered answer');
    expect(toRagResponseFromConversationMessages('metric.py question', payload)).toMatchObject({
      query: 'metric.py question',
      answer: 'latest recovered answer',
      evidence: [],
    });
  });

  it('falls back to the latest assistant message when parts are unavailable', () => {
    const payload = {
      conversationId: 'conversation-2',
      messages: [
        { role: 'user', content: 'question' },
        { role: 'assistant', content: 'message fallback answer' },
      ],
      parts: [],
    };

    expect(extractLatestAssistantAnswer(payload)).toBe('message fallback answer');
  });

  it('returns null when no assistant answer exists', () => {
    const payload = {
      conversationId: 'conversation-3',
      messages: [{ role: 'user', content: 'question' }],
      parts: [],
    };

    expect(extractLatestAssistantAnswer(payload)).toBeNull();
    expect(toRagResponseFromConversationMessages('query', payload)).toBeNull();
  });

  it('preserves conversation id for normal follow-up asks', () => {
    expect(planRagConversationContinuation({
      ragConversationId: 'conversation-keep',
      hasActiveClarification: false,
      ragEventCursor: 18,
    })).toEqual({
      recoveryConversationId: 'conversation-keep',
      startConversationId: 'conversation-keep',
      latestSeq: 18,
      shouldResetCursor: false,
    });
  });

  it('resets only when no existing conversation is available', () => {
    expect(planRagConversationContinuation({
      ragConversationId: null,
      hasActiveClarification: true,
      ragEventCursor: 9,
    })).toEqual({
      recoveryConversationId: null,
      startConversationId: undefined,
      latestSeq: 0,
      shouldResetCursor: true,
    });
  });

  it('keeps retrying terminal recovery after stream-finished hints while status is still non-terminal', () => {
    expect(planConversationTerminalRecoveryDelays({
      finalStatus: 'running',
      sessionFinishedByStream: true,
    })).toEqual([0, 500, 1000, 2000, 3500, 5000, 7000, 10000, 15000, 20000]);
  });

  it('does a few final checks when polling timed out with no stream signal', () => {
    expect(planConversationTerminalRecoveryDelays({
      finalStatus: 'running',
      sessionFinishedByStream: false,
    })).toEqual([0, 2000, 5000, 10000]);
  });

  it('does not add extra terminal recovery retries once status is completed', () => {
    expect(planConversationTerminalRecoveryDelays({
      finalStatus: 'completed',
      sessionFinishedByStream: true,
    })).toEqual([0]);
  });
});
