"""
图数据类型定义 - 对齐 GitNexus
基于 gitnexus/src/core/graph/types.ts
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


class NodeLabel(Enum):
    """节点类型 - 对齐 GitNexus"""
    PROJECT = "Project"
    PACKAGE = "Package"
    MODULE = "Module"
    FOLDER = "Folder"
    FILE = "File"
    CLASS = "Class"
    FUNCTION = "Function"
    METHOD = "Method"
    VARIABLE = "Variable"
    INTERFACE = "Interface"
    ENUM = "Enum"
    DECORATOR = "Decorator"
    IMPORT = "Import"
    TYPE = "Type"
    CODE_ELEMENT = "CodeElement"
    COMMUNITY = "Community"
    PROCESS = "Process"
    # 多语言支持
    STRUCT = "Struct"
    MACRO = "Macro"
    TYPEDEF = "Typedef"
    UNION = "Union"
    NAMESPACE = "Namespace"
    TRAIT = "Trait"
    IMPL = "Impl"


class RelationshipType(Enum):
    """关系类型 - 对齐 GitNexus"""
    CONTAINS = "CONTAINS"
    CALLS = "CALLS"
    INHERITS = "INHERITS"
    OVERRIDES = "OVERRIDES"
    IMPORTS = "IMPORTS"
    USES = "USES"
    DEFINES = "DEFINES"
    DECORATES = "DECORATES"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"
    MEMBER_OF = "MEMBER_OF"
    STEP_IN_PROCESS = "STEP_IN_PROCESS"


@dataclass
class NodeProperties:
    """节点属性 - 对齐 GitNexus NodeProperties"""
    name: str
    filePath: str
    startLine: Optional[int] = None
    endLine: Optional[int] = None
    language: Optional[str] = None
    isExported: Optional[bool] = None
    
    # 框架加成
    astFrameworkMultiplier: Optional[float] = None
    astFrameworkReason: Optional[str] = None
    
    # 社区属性
    heuristicLabel: Optional[str] = None
    cohesion: Optional[float] = None
    symbolCount: Optional[int] = None
    keywords: List[str] = field(default_factory=list)
    description: Optional[str] = None
    enrichedBy: Optional[str] = None  # 'heuristic' | 'llm'
    
    # Process 属性
    processType: Optional[str] = None  # 'intra_community' | 'cross_community'
    stepCount: Optional[int] = None
    communities: List[str] = field(default_factory=list)
    entryPointId: Optional[str] = None
    terminalId: Optional[str] = None
    
    # 入口点评分
    entryPointScore: Optional[float] = None
    entryPointReason: Optional[str] = None
    
    # ← NEW → CFG/DFG 数据（你的核心优势）
    cfg: Optional[Dict[str, Any]] = None
    dfg: Optional[Dict[str, Any]] = None
    
    # ← NEW → 输入输出
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    returns: List[Dict[str, Any]] = field(default_factory=list)
    
    # ← NEW → 调用关系
    callers: List[str] = field(default_factory=list)
    callees: List[str] = field(default_factory=list)
    
    # ← NEW → 源代码
    code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'filePath': self.filePath,
            'startLine': self.startLine,
            'endLine': self.endLine,
            'language': self.language,
            'isExported': self.isExported,
            'astFrameworkMultiplier': self.astFrameworkMultiplier,
            'astFrameworkReason': self.astFrameworkReason,
            'heuristicLabel': self.heuristicLabel,
            'cohesion': self.cohesion,
            'symbolCount': self.symbolCount,
            'keywords': self.keywords,
            'description': self.description,
            'enrichedBy': self.enrichedBy,
            'processType': self.processType,
            'stepCount': self.stepCount,
            'communities': self.communities,
            'entryPointId': self.entryPointId,
            'terminalId': self.terminalId,
            'entryPointScore': self.entryPointScore,
            'entryPointReason': self.entryPointReason,
            'cfg': self.cfg,
            'dfg': self.dfg,
            'parameters': self.parameters,
            'returns': self.returns,
            'callers': self.callers,
            'callees': self.callees,
            'code': self.code,
        }


@dataclass
class GraphNode:
    """图节点"""
    id: str
    label: NodeLabel
    properties: NodeProperties
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'label': self.label.value,
            'properties': self.properties.to_dict(),
        }


@dataclass
class GraphRelationship:
    """图关系"""
    id: str
    sourceId: str
    targetId: str
    type: RelationshipType
    confidence: float = 1.0  # 置信度 0-1
    reason: str = ""  # 解析原因: 'import-resolved' | 'same-file' | 'fuzzy-global'
    step: Optional[int] = None  # STEP_IN_PROCESS 的步骤序号 (1-indexed)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'sourceId': self.sourceId,
            'targetId': self.targetId,
            'type': self.type.value,
            'confidence': self.confidence,
            'reason': self.reason,
            'step': self.step,
        }


@dataclass
class KnowledgeGraph:
    """知识图谱"""
    nodes: List[GraphNode] = field(default_factory=list)
    relationships: List[GraphRelationship] = field(default_factory=list)
    
    def add_node(self, node: GraphNode):
        """添加节点"""
        self.nodes.append(node)
    
    def add_relationship(self, rel: GraphRelationship):
        """添加关系"""
        self.relationships.append(rel)
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """根据 ID 获取节点"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_node_by_name(self, name: str) -> Optional[GraphNode]:
        """根据名称获取节点"""
        for node in self.nodes:
            if node.properties.name == name:
                return node
        return None
    
    def get_relationships(self, node_id: str, direction: str = "both") -> List[GraphRelationship]:
        """获取节点的关系"""
        results = []
        for rel in self.relationships:
            if direction == "outgoing" and rel.sourceId == node_id:
                results.append(rel)
            elif direction == "incoming" and rel.targetId == node_id:
                results.append(rel)
            elif direction == "both" and (rel.sourceId == node_id or rel.targetId == node_id):
                results.append(rel)
        return results
    
    @property
    def node_count(self) -> int:
        return len(self.nodes)
    
    @property
    def relationship_count(self) -> int:
        return len(self.relationships)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 JSON 序列化）"""
        return {
            'nodes': [node.to_dict() for node in self.nodes],
            'relationships': [rel.to_dict() for rel in self.relationships],
            'nodeCount': self.node_count,
            'relationshipCount': self.relationship_count,
        }


def create_node_id(label: str, name: str, file_path: str = "") -> str:
    """创建节点 ID - 对齐 GitNexus generateId"""
    if file_path:
        return f"{label}:{file_path}:{name}"
    return f"{label}:{name}"


def create_relationship_id(type: str, source: str, target: str) -> str:
    """创建关系 ID"""
    return f"{type}:{source}:{target}"


def calculate_confidence(relationship_type: RelationshipType, resolution_method: str = "") -> float:
    """
    计算关系置信度 - 对齐 GitNexus
    
    Args:
        relationship_type: 关系类型
        resolution_method: 解析方法 ('import-resolved' | 'same-file' | 'fuzzy-global')
    
    Returns:
        置信度 0-1
    """
    # 基于解析方法的置信度
    method_confidence = {
        'import-resolved': 0.9,
        'same-file': 0.85,
        'fuzzy-global': 0.3,
    }
    
    base_confidence = method_confidence.get(resolution_method, 0.5)
    
    # 基于关系类型的调整
    type_multiplier = {
        RelationshipType.CALLS: 1.0,
        RelationshipType.IMPORTS: 1.0,
        RelationshipType.INHERITS: 0.95,
        RelationshipType.IMPLEMENTS: 0.95,
        RelationshipType.EXTENDS: 0.95,
        RelationshipType.MEMBER_OF: 0.9,
        RelationshipType.STEP_IN_PROCESS: 0.95,
        RelationshipType.CONTAINS: 1.0,
    }
    
    multiplier = type_multiplier.get(relationship_type, 0.8)
    
    return min(base_confidence * multiplier, 1.0)


# 便于导入
__all__ = [
    'NodeLabel',
    'RelationshipType', 
    'NodeProperties',
    'GraphNode',
    'GraphRelationship',
    'KnowledgeGraph',
    'create_node_id',
    'create_relationship_id',
    'calculate_confidence',
]
