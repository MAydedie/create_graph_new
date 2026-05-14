import type { CreateGraphConversationMessagesResponse, CreateGraphRagAskResponse } from '../services/create-graph-extensions';

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const toStringValue = (value: unknown, fallback = ''): string => (typeof value === 'string' ? value : fallback);

export interface RagConversationContinuationInput {
  ragConversationId: string | null;
  hasActiveClarification: boolean;
  ragEventCursor: number;
}

export interface RagConversationContinuationPlan {
  recoveryConversationId: string | null;
  startConversationId?: string;
  latestSeq: number;
  shouldResetCursor: boolean;
}

export interface ConversationTerminalRecoveryPlanInput {
  finalStatus: string | null | undefined;
  sessionFinishedByStream: boolean;
}

export const planRagConversationContinuation = ({
  ragConversationId,
  ragEventCursor,
}: RagConversationContinuationInput): RagConversationContinuationPlan => {
  const preservedConversationId = ragConversationId || null;
  return {
    recoveryConversationId: preservedConversationId,
    startConversationId: preservedConversationId || undefined,
    latestSeq: preservedConversationId ? ragEventCursor : 0,
    shouldResetCursor: !preservedConversationId,
  };
};

export const planConversationTerminalRecoveryDelays = ({
  finalStatus,
  sessionFinishedByStream,
}: ConversationTerminalRecoveryPlanInput): number[] => {
  if (finalStatus === 'completed') {
    return [0];
  }

  if (sessionFinishedByStream) {
    // Stream signalled completion but status poll hasn't caught up yet.
    // Retry aggressively for ~63 seconds total to cover any DB write lag.
    return [0, 500, 1000, 2000, 3500, 5000, 7000, 10000, 15000, 20000];
  }

  // Polling timed out without stream signal - do a few final checks.
  return [0, 2000, 5000, 10000];
};

export const extractLatestAssistantAnswer = (payload: CreateGraphConversationMessagesResponse): string | null => {
  const latestAssistantTextPart = [...payload.parts]
    .filter(isRecord)
    .reverse()
    .find((part) => toStringValue(part.type) === 'assistant_text' && toStringValue(part.content).trim());
  if (latestAssistantTextPart) {
    return toStringValue(latestAssistantTextPart.content).trim();
  }

  const latestAssistantMessage = [...payload.messages]
    .filter(isRecord)
    .reverse()
    .find((message) => toStringValue(message.role) === 'assistant' && toStringValue(message.content).trim());
  if (latestAssistantMessage) {
    return toStringValue(latestAssistantMessage.content).trim();
  }

  return null;
};

export const toRagResponseFromConversationMessages = (
  query: string,
  payload: CreateGraphConversationMessagesResponse,
): CreateGraphRagAskResponse | null => {
  const answer = extractLatestAssistantAnswer(payload);
  if (!answer) {
    return null;
  }

  return {
    query,
    answer,
    evidence: [],
  };
};
