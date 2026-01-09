#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
四层嵌套数据模型定义
层级：功能层 -> 文件夹层 -> 代码元素图层 -> 代码细节层
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
import json


class ImportanceLevel(Enum):
    """代码重要级别"""
    CRITICAL = "重要-1"      # 核心入口（最重要）
    CORE_LOGIC = "重要-2"    # 核心业务逻辑
    KEY_UTILITY = "重要-3"   # 关键工具类
    SUPPORT = "重要-4"       # 支持性代码


class RelationType(Enum):
    """关系类型"""
    CALLS = "calls"                    # 方法调用
    INHERITS = "inherits"              # 继承关系
    ACCESSES = "accesses"              # 字段访问
    CONTAINS = "contains"              # 包含关系（类包含方法）
    CROSS_FILE_CALL = "cross_file_call"  # 跨文件调用
    PARAMETER_FLOW = "parameter_flow"  # 参数流动


# ==================== 第4层：代码细节 ====================

@dataclass
class CodeDetail:
    """第4层：代码细节（最底层）"""
    entity_id: str                          # 唯一标识：method_ClassName_methodName
    entity_type: str                        # class/method/function/field
    entity_name: str                        # 简单名称
    full_signature: str                     # 完整签名
    file_path: str                          # 源文件路径
    line_start: int = 0                     # 开始行号
    line_end: int = 0                       # 结束行号
    
    source_code: str = ""                   # 完整源代码
    docstring: str = ""                     # 文档字符串
    comments: List[str] = field(default_factory=list)  # 代码中的注释
    
    cfg: Optional[str] = None               # 控制流图（如果有，DOT格式或JSON字符串）
    cfg_paths: List[str] = field(default_factory=list)  # CFG路径列表
    dfg: Optional[str] = None               # 数据流图（如果有，DOT格式或JSON字符串）
    
    # 输入/输出信息
    inputs: List[Dict] = field(default_factory=list)  # 输入列表 [{"name": "x", "type": "str"}]
    outputs: List[Dict] = field(default_factory=list)  # 输出列表 [{"name": "return", "type": "int"}]
    global_reads: List[str] = field(default_factory=list)  # 读取的全局变量
    global_writes: List[str] = field(default_factory=list)  # 写入的全局变量
    
    importance_mark: str = ""               # 重要级别标注（"重要-1"等）
    importance_reason: str = ""             # 为什么重要的解释
    
    llm_explanation: Optional[str] = None   # LLM生成的代码解释（延迟生成）
    explanation_generated_at: Optional[str] = None  # 生成时间戳
    
    call_count: int = 0                     # 被调用次数（用于评分）
    is_entry_point: bool = False            # 是否是入口点（如main）


# ==================== 第3层：代码元素及关系 ====================

@dataclass
class GraphEdge:
    """图的边"""
    source_id: str          # 源节点ID
    target_id: str          # 目标节点ID
    relation: RelationType  # 关系类型
    weight: int = 1         # 权重（如调用次数）
    source_file: str = ""   # 源文件
    target_file: str = ""   # 目标文件
    metadata: Dict = field(default_factory=dict)  # 额外信息


@dataclass
class CodeGraph:
    """第3层：代码元素及其关系图"""
    nodes: Dict[str, Dict]  # entity_id -> node_info
    edges: List[GraphEdge]  # 所有边
    
    # 统计信息
    total_nodes: int = 0
    total_classes: int = 0
    total_methods: int = 0
    total_functions: int = 0
    total_fields: int = 0
    total_edges: int = 0


# ==================== 第2层：文件夹层 ====================

@dataclass
class FolderStats:
    """文件夹的聚合统计"""
    class_count: int = 0
    method_count: int = 0
    function_count: int = 0
    field_count: int = 0
    total_code_elements: int = 0
    total_lines_of_code: int = 0


@dataclass
class FolderRelation:
    """文件夹之间的关系"""
    source_folder: str          # 源文件夹路径
    target_folder: str          # 目标文件夹路径
    call_count: int = 0         # 调用次数
    entity_pairs: List[Tuple[str, str]] = field(default_factory=list)  # 具体的实体对


@dataclass
class FolderNode:
    """第2层：文件夹节点"""
    folder_path: str            # 相对路径，如"analysis"
    parent_function: str        # 属于哪个功能分区
    
    # 包含的资源
    contained_files: List[str] = field(default_factory=list)    # Python文件列表
    contained_code_entities: List[str] = field(default_factory=list)  # 代码元素ID列表
    
    # 聚合统计
    stats: FolderStats = field(default_factory=FolderStats)
    
    # 文件夹间的关系（聚合自第3层）
    outgoing_calls: Dict[str, int] = field(default_factory=dict)  # {target_folder: call_count}
    incoming_calls: Dict[str, int] = field(default_factory=dict)  # {source_folder: call_count}
    folder_relations: List[FolderRelation] = field(default_factory=list)
    
    # 元数据
    description: str = ""
    is_core_folder: bool = False  # 是否是核心文件夹


# ==================== 第1层：功能分区层 ====================

@dataclass
class FunctionStats:
    """功能分区的聚合统计"""
    total_classes: int = 0
    total_methods: int = 0
    total_functions: int = 0
    total_lines_of_code: int = 0
    total_critical_codes: int = 0  # 重要-1的代码数


@dataclass
class FunctionRelation:
    """功能之间的关系"""
    source_function: str        # 源功能名称
    target_function: str        # 目标功能名称
    call_count: int = 0         # 聚合调用次数
    call_density: float = 0.0   # 调用密度（调用数/源方法数）
    critical_path_count: int = 0  # 重要-1代码参与的调用数


@dataclass
class FunctionPartition:
    """第1层：功能分区节点"""
    name: str                   # 功能名称，如"代码解析层"
    description: str            # 功能描述
    
    # 包含的资源
    folders: List[str] = field(default_factory=list)           # 文件夹路径列表
    contained_code_entities: List[str] = field(default_factory=list)  # 代码元素ID列表
    
    # 重要代码清单
    important_codes: Dict[str, List[str]] = field(default_factory=dict)  # {importance_level: [entity_ids]}
    
    # 聚合统计
    stats: FunctionStats = field(default_factory=FunctionStats)
    
    # 功能间的关系（聚合自第3层）
    outgoing_calls: Dict[str, int] = field(default_factory=dict)  # {target_function: call_count}
    incoming_calls: Dict[str, int] = field(default_factory=dict)  # {source_function: call_count}
    function_relations: List[FunctionRelation] = field(default_factory=list)
    
    # 元数据
    keywords: List[str] = field(default_factory=list)  # 用于识别属于该功能的代码
    is_core_function: bool = False  # 是否是核心功能


# ==================== 顶层：层级模型容器 ====================

@dataclass
class HierarchyMetadata:
    """元数据"""
    project_name: str
    project_path: str
    analysis_timestamp: str
    total_files: int = 0
    total_functions_in_partition: int = 0  # 第1层的功能数
    total_folders: int = 0  # 第2层的文件夹数
    total_code_entities: int = 0  # 第3层的代码元素数
    total_code_details: int = 0  # 第4层的细节数


@dataclass
class HierarchyModel:
    """四层层级模型"""
    
    # 元数据
    metadata: HierarchyMetadata
    
    # 第1层：功能分区
    layer1_functions: List[FunctionPartition] = field(default_factory=list)
    layer1_functions_map: Dict[str, FunctionPartition] = field(default_factory=dict)  # name -> partition
    
    # 第2层：文件夹
    layer2_folders: List[FolderNode] = field(default_factory=list)
    layer2_folders_map: Dict[str, FolderNode] = field(default_factory=dict)  # path -> folder
    
    # 第3层：代码图
    layer3_code_graph: CodeGraph = None
    
    # 第4层：代码细节
    layer4_details: Dict[str, CodeDetail] = field(default_factory=dict)  # entity_id -> CodeDetail
    
    # 映射关系
    entity_to_function_map: Dict[str, str] = field(default_factory=dict)  # entity_id -> function_name
    entity_to_folder_map: Dict[str, str] = field(default_factory=dict)  # entity_id -> folder_path
    file_to_folder_map: Dict[str, str] = field(default_factory=dict)  # file_path -> folder_path
    folder_to_function_map: Dict[str, str] = field(default_factory=dict)  # folder_path -> function_name
    
    # 跨层关系计算标志
    relations_calculated: bool = False
    
    def to_dict(self) -> Dict:
        """转换为字典（便于JSON序列化）"""
        return {
            "metadata": asdict(self.metadata),
            "layer1": [asdict(f) for f in self.layer1_functions],
            "layer2": [asdict(f) for f in self.layer2_folders],
            "layer3_summary": {
                "total_nodes": self.layer3_code_graph.total_nodes if self.layer3_code_graph else 0,
                "total_edges": self.layer3_code_graph.total_edges if self.layer3_code_graph else 0,
                "class_count": self.layer3_code_graph.total_classes if self.layer3_code_graph else 0,
                "method_count": self.layer3_code_graph.total_methods if self.layer3_code_graph else 0,
            },
            "layer4_summary": {
                "total_details": len(self.layer4_details),
                "critical_codes": sum(1 for d in self.layer4_details.values() if "重要-1" in d.importance_mark)
            }
        }
    
    def to_json(self, filepath: str) -> None:
        """保存为JSON文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, filepath: str) -> 'HierarchyModel':
        """从JSON文件加载（不完全恢复，仅用于查看）"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 实现部分反序列化逻辑
        return cls(metadata=HierarchyMetadata(
            project_name=data['metadata']['project_name'],
            project_path=data['metadata']['project_path'],
            analysis_timestamp=data['metadata']['analysis_timestamp']
        ))


# ==================== 辅助函数 ====================

def create_empty_hierarchy(project_name: str, project_path: str) -> HierarchyModel:
    """创建空的层级模型"""
    metadata = HierarchyMetadata(
        project_name=project_name,
        project_path=project_path,
        analysis_timestamp=""
    )
    return HierarchyModel(metadata=metadata)
