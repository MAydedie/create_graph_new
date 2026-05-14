import type { GraphNode } from "../core/graph/types";
import type {
	CreateGraphConversationReplyRequest,
	CreateGraphConversationSessionStartRequest,
	CreateGraphPartitionAnalysisResponse,
} from "../services/create-graph-extensions";

type ConversationQaRequest =
	| CreateGraphConversationReplyRequest
	| CreateGraphConversationSessionStartRequest;

export interface RightPanelQaPathSelection {
	id?: string;
	pathId?: string;
	pathName?: string;
	pathDescription?: string;
	methods?: string[];
	leafNode?: string;
	mainMethod?: string;
	intermediateMethods?: string[];
	callChainType?: string;
	callChainExplanation?: string;
}

export interface RightPanelQaAnchorInput {
	partitionId?: string | null;
	selectedNode?: GraphNode | null;
	selectedMethodKey?: string | null;
	selectedPathAnalysis?: RightPanelQaPathSelection | null;
	partitionAnalysis?: CreateGraphPartitionAnalysisResponse | null;
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
	return typeof value === "object" && value !== null;
};

const toOptionalString = (value: unknown): string | undefined => {
	return typeof value === "string" && value.trim() ? value.trim() : undefined;
};

const toOptionalNumber = (value: unknown): number | undefined => {
	return typeof value === "number" && Number.isFinite(value)
		? value
		: undefined;
};

const toStringArray = (value: unknown): string[] => {
	if (!Array.isArray(value)) return [];
	return value
		.filter((item): item is string => typeof item === "string")
		.map((item) => item.trim())
		.filter(Boolean);
};

const dedupeStrings = (values: Array<string | undefined>): string[] => {
	const seen = new Set<string>();
	const result: string[] = [];
	for (const value of values) {
		if (!value || seen.has(value)) continue;
		seen.add(value);
		result.push(value);
	}
	return result;
};

const compactRecord = (
	payload: Record<string, unknown>,
): Record<string, unknown> => {
	const compacted: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(payload)) {
		if (value == null) continue;
		if (typeof value === "string" && !value.trim()) continue;
		if (Array.isArray(value) && value.length === 0) continue;
		if (isRecord(value) && Object.keys(value).length === 0) continue;
		compacted[key] = value;
	}
	return compacted;
};

const resolveMethodIdentity = (
	partitionAnalysis: CreateGraphPartitionAnalysisResponse | null | undefined,
	candidates: string[],
): Record<string, string | undefined> => {
	const normalizedCandidates = dedupeStrings(candidates);
	const fqns = Array.isArray(partitionAnalysis?.fqns) ? partitionAnalysis.fqns : [];

	for (const rawEntry of fqns) {
		if (!isRecord(rawEntry)) continue;
		const methodSignature = toOptionalString(rawEntry.method_signature);
		const fqn = toOptionalString(rawEntry.fqn);
		const signature = toOptionalString(rawEntry.signature) ?? methodSignature;
		const fullName =
			toOptionalString(rawEntry.full_name) ??
			toOptionalString(rawEntry.display_name) ??
			fqn ??
			signature;
		const haystacks = [methodSignature, fqn, signature, fullName].filter(
			(item): item is string => Boolean(item),
		);
		const matched = normalizedCandidates.some((candidate) =>
			haystacks.some(
				(item) =>
					item === candidate ||
					item.endsWith(`.${candidate}`) ||
					candidate.endsWith(`.${item}`),
			),
		);
		if (!matched) continue;
		return {
			method_signature: methodSignature,
			signature,
			fqn,
			fqmn: fqn ?? methodSignature,
			full_name: fullName,
		};
	}

	const fallback = normalizedCandidates[0];
	if (!fallback) return {};
	return {
		method_signature: fallback,
		signature: fallback,
		fqmn: fallback,
		full_name: fallback,
	};
};

export const buildQaSelectedNodePayload = (
	input: RightPanelQaAnchorInput,
): Record<string, unknown> | undefined => {
	const { partitionId, selectedNode, selectedMethodKey, selectedPathAnalysis } = input;
	const selectedNodeName = toOptionalString(selectedNode?.properties?.name);
	const selectedNodeId = toOptionalString(selectedNode?.id);
	const methodCandidates = dedupeStrings([
		toOptionalString(selectedMethodKey),
		toOptionalString(selectedPathAnalysis?.leafNode),
		toOptionalString(selectedPathAnalysis?.mainMethod),
		selectedNodeName,
		selectedNodeId,
		...toStringArray(selectedPathAnalysis?.methods),
	]);
	const methodIdentity = resolveMethodIdentity(
		input.partitionAnalysis,
		methodCandidates,
	);
	const pathMethods = dedupeStrings(toStringArray(selectedPathAnalysis?.methods));
	const intermediateMethods = dedupeStrings(
		toStringArray(selectedPathAnalysis?.intermediateMethods),
	);

	const payload = compactRecord({
		id: selectedNodeId,
		name: selectedNodeName,
		label: selectedNodeName,
		display_name: selectedNodeName,
		type: toOptionalString(selectedNode?.label),
		file_path: toOptionalString(selectedNode?.properties?.filePath),
		start_line: toOptionalNumber(selectedNode?.properties?.startLine),
		end_line: toOptionalNumber(selectedNode?.properties?.endLine),
		partition_id: toOptionalString(partitionId),
		method_signature: methodIdentity.method_signature,
		signature: methodIdentity.signature,
		fqn: methodIdentity.fqn,
		fqmn: methodIdentity.fqmn,
		full_name: methodIdentity.full_name,
		path_id:
			toOptionalString(selectedPathAnalysis?.pathId) ??
			toOptionalString(selectedPathAnalysis?.id),
		path_name: toOptionalString(selectedPathAnalysis?.pathName),
		path_description: toOptionalString(selectedPathAnalysis?.pathDescription),
		leaf_node: toOptionalString(selectedPathAnalysis?.leafNode),
		main_method: toOptionalString(selectedPathAnalysis?.mainMethod),
		intermediate_methods: intermediateMethods,
		path_methods: pathMethods,
		function_chain: pathMethods,
		call_chain_type: toOptionalString(selectedPathAnalysis?.callChainType),
		call_chain_explanation: toOptionalString(
			selectedPathAnalysis?.callChainExplanation,
		),
	});

	return Object.keys(payload).length > 0 ? payload : undefined;
};

export const buildConversationQaRequest = <T extends ConversationQaRequest>(
	basePayload: T,
	input: RightPanelQaAnchorInput,
): T => {
	const payload: T = { ...basePayload };
	const selectedNodePayload = buildQaSelectedNodePayload(input);
	const partitionId = toOptionalString(input.partitionId);
	if (selectedNodePayload) {
		payload.selected_node = selectedNodePayload;
	}
	if (partitionId) {
		payload.partition_id = partitionId;
	}
	return payload;
};
