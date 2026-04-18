"""
关系增强器 - 为现有关系添加置信度和元数据
解决"问题1"：为什么节点和连线比 GitNexus 少？
原因：缺少置信度系统
"""

from typing import List, Dict, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
import re


@dataclass
class RelationshipWithConfidence:
    """带置信度的关系"""
    source: str
    target: str
    type: str
    confidence: float
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class RelationshipEnhancer:
    """
    关系增强器
    
    功能：
    - 为关系添加置信度
    - 识别关系类型
    - 过滤低质量关系
    """
    
    def __init__(self):
        # 关系类型识别模式
        self.call_patterns = [
            r'^[a-z_][a-z0-9_]*\(',
            r'\.[a-z_][a-z0-9_]*\(',
        ]
        
        self.field_patterns = [
            r'\.([a-z_][a-z0-9_]*)\s*=',
            r'self\.([a-z_][a-z0-9_]*)',
        ]
        
        self.builtin_modules = {
            'os', 'sys', 're', 'json', 'collections', 'itertools',
            'functools', 'operator', 'types', 'copy', 'pickle',
            'datetime', 'time', 'random', 'math', 'statistics',
            'pathlib', 'typing', 'abc', 'enum', 'dataclasses',
        }
    
    def calculate_call_confidence(
        self,
        caller: str,
        callee: str,
        resolution_method: str = ""
    ) -> float:
        """
        计算调用关系的置信度
        
        Args:
            caller: 调用者
            callee: 被调用者
            resolution_method: 解析方法
        """
        base_confidence = {
            'import-resolved': 0.9,
            'same-file': 0.85,
            'fuzzy-global': 0.3,
        }.get(resolution_method, 0.5)
        
        # 调整因素
        # 1. 如果是内置模块，降低置信度
        for module in self.builtin_modules:
            if callee.startswith(module + '.'):
                return base_confidence * 0.5
        
        # 2. 如果名称是 snake_case（更像函数），提高置信度
        if re.match(r'^[a-z_][a-z0-9_]*$', callee):
            base_confidence = min(base_confidence * 1.1, 1.0)
        
        # 3. 如果是类方法调用（包含点号），提高置信度
        if '.' in callee:
            base_confidence = min(base_confidence * 1.05, 1.0)
        
        return base_confidence
    
    def calculate_inheritance_confidence(
        self,
        child: str,
        parent: str,
        has_parent_keyword: bool = True
    ) -> float:
        """计算继承关系的置信度"""
        if has_parent_keyword:
            return 0.95
        return 0.7
    
    def calculate_access_confidence(
        self,
        accessor: str,
        field_name: str,
        is_self_field: bool = True
    ) -> float:
        """计算字段访问的置信度"""
        base = 0.8 if is_self_field else 0.6
        
        # 检查是否是常见属性
        common_attrs = {
            'self', 'cls', 'cls_', '__class__',
            '__dict__', '__name__', '__module__',
        }
        
        if field_name in common_attrs:
            return base * 0.5
        
        return base
    
    def enhance_relationships(
        self,
        relationships: List[Dict]
    ) -> List[RelationshipWithConfidence]:
        """
        增强关系列表，添加置信度
        
        Args:
            relationships: 原始关系列表
            
        Returns:
            带置信度的关系列表
        """
        enhanced = []
        
        for rel in relationships:
            rel_type = rel.get('type', '')
            source = rel.get('source', rel.get('sourceId', ''))
            target = rel.get('target', rel.get('targetId', ''))
            
            # 根据关系类型计算置信度
            if 'call' in rel_type.lower():
                confidence = self.calculate_call_confidence(
                    source, target, rel.get('reason', '')
                )
            elif 'inherit' in rel_type.lower() or 'extend' in rel_type.lower():
                confidence = self.calculate_inheritance_confidence(
                    source, target, bool(rel.get('parent'))
                )
            elif 'access' in rel_type.lower():
                confidence = self.calculate_access_confidence(
                    source, target
                )
            else:
                confidence = rel.get('confidence', 0.8)
            
            enhanced.append(RelationshipWithConfidence(
                source=source,
                target=target,
                type=rel_type,
                confidence=confidence,
                reason=rel.get('reason', ''),
                metadata=rel
            ))
        
        # 按置信度排序
        enhanced.sort(key=lambda x: x.confidence, reverse=True)
        
        return enhanced
    
    def filter_by_confidence(
        self,
        relationships: List[RelationshipWithConfidence],
        min_confidence: float = 0.3
    ) -> List[RelationshipWithConfidence]:
        """过滤低置信度关系"""
        return [r for r in relationships if r.confidence >= min_confidence]


class GraphBuilder:
    """
    图构建器 - 使用新的 graph_types 构建图
    
    将现有的分析结果转换为标准化的图格式
    """
    
    def __init__(self):
        self.enhancer = RelationshipEnhancer()
    
    def build_from_analysis_result(
        self,
        classes: Dict[str, Any],
        call_graph: Dict[str, Set[str]],
        inheritance_graph: Dict[str, str],
        cross_file_calls: List[Tuple[str, str, str]],
        source_code: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        从分析结果构建图数据
        
        Args:
            classes: 类信息字典
            call_graph: 调用图
            inheritance_graph: 继承图
            cross_file_calls: 跨文件调用
            source_code: 源代码
            
        Returns:
            标准化的图数据
        """
        from src.analysis.graph_types import (
            NodeLabel, RelationshipType, KnowledgeGraph,
            GraphNode, GraphRelationship, create_node_id
        )
        
        kg = KnowledgeGraph()
        
        # 1. 添加节点
        for class_name, class_info in classes.items():
            node_id = create_node_id('Class', class_name, class_info.get('file_path', ''))
            
            from src.analysis.graph_types import NodeProperties
            props = NodeProperties(
                name=class_name,
                filePath=class_info.get('file_path', ''),
                startLine=class_info.get('line_start'),
                endLine=class_info.get('line_end'),
                code=source_code.get(class_info.get('file_path', ''), '').split('\n')[
                    class_info.get('line_start', 0):class_info.get('line_end', 100)
                ] if class_info.get('line_start') else None
            )
            
            node = GraphNode(
                id=node_id,
                label=NodeLabel.CLASS,
                properties=props
            )
            kg.add_node(node)
        
        # 2. 添加调用关系（带置信度）
        for caller, callees in call_graph.items():
            for callee in callees:
                confidence = self.enhancer.calculate_call_confidence(
                    caller, callee, 'same-file'
                )
                
                rel = GraphRelationship(
                    id=f"CALLS:{caller}:{callee}",
                    sourceId=caller,
                    targetId=callee,
                    type=RelationshipType.CALLS,
                    confidence=confidence,
                    reason='same-file'
                )
                kg.add_relationship(rel)
        
        # 3. 添加继承关系
        for child, parent in inheritance_graph.items():
            confidence = self.enhancer.calculate_inheritance_confidence(child, parent)
            
            rel = GraphRelationship(
                id=f"INHERITS:{child}:{parent}",
                sourceId=child,
                targetId=parent,
                type=RelationshipType.INHERITS,
                confidence=confidence,
                reason='keyword-detected'
            )
            kg.add_relationship(rel)
        
        # 4. 添加跨文件调用（带置信度）
        for caller_file, caller, callee in cross_file_calls:
            confidence = self.enhancer.calculate_call_confidence(
                caller, callee, 'import-resolved'
            )
            
            rel = GraphRelationship(
                id=f"CALLS:{caller}:{callee}",
                sourceId=caller,
                targetId=callee,
                type=RelationshipType.CALLS,
                confidence=confidence,
                reason='cross-file'
            )
            kg.add_relationship(rel)
        
        return kg.to_dict()


# 测试
if __name__ == '__main__':
    enhancer = RelationshipEnhancer()
    
    # 测试置信度计算
    test_rels = [
        {'type': 'calls', 'source': 'ClassA.method_a', 'target': 'helper_func', 'reason': 'import-resolved'},
        {'type': 'calls', 'source': 'ClassA.method_a', 'target': 'os.path.join', 'reason': 'import-resolved'},
        {'type': 'inherits', 'source': 'ChildClass', 'target': 'ParentClass', 'parent': True},
    ]
    
    enhanced = enhancer.enhance_relationships(test_rels)
    
    print("关系增强结果:")
    for rel in enhanced:
        print(f"  {rel.source} --[{rel.type}]--> {rel.target}")
        print(f"    confidence: {rel.confidence:.2f}, reason: {rel.reason}")
