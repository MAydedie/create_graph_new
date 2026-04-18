import { GraphVizBlock } from './GraphVizBlock';

export interface IoGraphNode {
  id: string;
  label?: string;
  type?: string;
}

export interface IoGraphEdge {
  source: string;
  target: string;
  label?: string;
}

export interface IoGraphData {
  nodes: IoGraphNode[];
  edges: IoGraphEdge[];
}

const sanitizeId = (raw: string): string => raw.replace(/[^a-zA-Z0-9_]/g, '_') || 'node';
const escapeDot = (raw: string): string => raw.replace(/\\/g, '\\\\').replace(/"/g, '\\"');

const getNodeColor = (nodeType: string): string => {
  const type = nodeType || 'unknown';
  if (type.includes('输入') || type.includes('文件')) return '#4caf50';
  if (type.includes('字典')) return '#2196f3';
  if (type.includes('字符串')) return '#9c27b0';
  if (type.includes('操作节点')) return '#667eea';
  if (type.includes('输出')) return '#ff9800';
  return '#999999';
};

const buildIoGraphDot = (ioGraph: IoGraphData): string => {
  const lines = [
    'digraph PathIO {',
    '  rankdir=LR;',
    '  graph [pad="0.3", nodesep="0.6", ranksep="0.9"];',
    '  node [style="filled,rounded", fontname="Arial"];',
    '  edge [fontname="Arial", color="#94a3b8", arrowsize="0.8"];',
  ];

  for (const node of ioGraph.nodes) {
    const nodeType = node.type || 'unknown';
    const shape = nodeType === '操作节点' ? 'box' : 'parallelogram';
    const color = getNodeColor(nodeType);
    const id = sanitizeId(node.id);
    const label = escapeDot(node.label || node.id);
    lines.push(`  "${id}" [label="${label}", shape=${shape}, fillcolor="${color}", color="#475569", fontcolor="#ffffff"];`);
  }

  for (const edge of ioGraph.edges) {
    const source = sanitizeId(edge.source);
    const target = sanitizeId(edge.target);
    const label = escapeDot(edge.label || '');
    const labelPart = label ? ` [label="${label}"]` : '';
    lines.push(`  "${source}" -> "${target}"${labelPart};`);
  }

  lines.push('}');
  return lines.join('\n');
};

export function IoGraphBlock({ ioGraph }: { ioGraph: IoGraphData }) {
  return <GraphVizBlock dotString={buildIoGraphDot(ioGraph)} color="emerald" />;
}
