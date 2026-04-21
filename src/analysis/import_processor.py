"""
Import 处理器 - 提取导入关系
移植自 GitNexus import-processor.ts

解决"问题1"：为什么节点和连线比 GitNexus 少？
原因：缺少 IMPORTS 关系的提取
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field

# 尝试导入 tree-sitter，如果不可用则使用备用方案
try:
    import tree_sitter
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


@dataclass
class ExtractedImport:
    """提取的导入信息"""
    name: str  # 导入的名称
    alias: Optional[str] = None  # 别名
    path: Optional[str] = None  # 导入路径
    is_from: bool = False  # 是否是 from ... import
    is_relative: bool = False  # 是否是相对导入
    level: int = 0  # 相对导入级别 (0=绝对导入)


@dataclass
class ImportResolutionResult:
    """导入解析结果"""
    node_id: str  # 解析后的节点 ID
    confidence: float  # 置信度
    reason: str  # 解析原因: 'import-resolved' | 'same-file' | 'fuzzy-global'
    resolved_path: Optional[str] = None  # 解析后的文件路径


class ImportProcessor:
    """
    处理 Import 关系提取
    
    功能：
    - 提取文件中的所有 import 语句
    - 解析相对导入和绝对导入
    - 尝试将导入解析到具体的定义节点
    """
    
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir).resolve()
        self.file_paths: Set[str] = set()
        self.normalized_file_list: List[str] = []
        self.suffix_index: Dict[str, List[str]] = {}
        self.resolve_cache: Dict[str, Optional[str]] = {}
        
        # Python 关键字（不是有效导入）
        self.python_keywords = {
            'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await',
            'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
            'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
            'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try',
            'while', 'with', 'yield'
        }
    
    def build_file_index(self, file_paths: List[str]) -> None:
        """构建文件索引，用于快速查找"""
        self.file_paths = set(file_paths)
        self.normalized_file_list = [self._normalize_path(p) for p in file_paths]
        
        # 构建后缀索引（支持不同扩展名）
        self.suffix_index = {}
        for fp in self.normalized_file_list:
            # 按文件名建立索引（不含扩展名）
            name = Path(fp).stem.lower()
            if name not in self.suffix_index:
                self.suffix_index[name] = []
            self.suffix_index[name].append(fp)
    
    def _normalize_path(self, path: str) -> str:
        """标准化路径"""
        return path.replace('\\', '/')
    
    def extract_imports(self, file_path: str, content: str) -> List[ExtractedImport]:
        """
        从文件中提取所有导入
        
        Args:
            file_path: 文件路径
            content: 文件内容
            
        Returns:
            导入列表
        """
        imports = []
        
        if TREE_SITTER_AVAILABLE:
            imports = self._extract_imports_tree_sitter(content)
        else:
            imports = self._extract_imports_regex(content)
        
        # 过滤关键字
        imports = [imp for imp in imports if imp.name not in self.python_keywords]
        
        return imports
    
    def _extract_imports_tree_sitter(self, content: str) -> List[ExtractedImport]:
        """使用 tree-sitter 提取导入（更准确）"""
        imports = []
        
        try:
            parser = Parser(Language('python'))
            tree = parser.parse(bytes(content, 'utf8'))
            
            # 遍历 AST 查找 import 语句
            # 这里简化处理，使用正则作为后备
        except Exception:
            return self._extract_imports_regex(content)
        
        return imports
    
    def _extract_imports_regex(self, content: str) -> List[ExtractedImport]:
        """使用正则表达式提取导入（备用方案）"""
        imports = []
        
        # from xxx import yyy
        from_pattern = re.compile(
            r'^\s*from\s+([\w.]+)\s+import\s+(.+?)(?:\s*as\s+\w+)?\s*$',
            re.MULTILINE
        )
        
        # import xxx
        import_pattern = re.compile(
            r'^\s*import\s+([\w.]+)(?:\s+as\s+(\w+))?\s*$',
            re.MULTILINE
        )
        
        # 解析 from ... import
        for match in from_pattern.finditer(content):
            module_path = match.group(1)
            imported_items = match.group(2)
            
            # 处理多个导入: from x import a, b, c
            for item in imported_items.split(','):
                item = item.strip()
                # 去除可能的别名
                if ' as ' in item:
                    item = item.split(' as ')[0].strip()
                
                if item and item != '*':
                    imp = ExtractedImport(
                        name=item,
                        path=module_path,
                        is_from=True,
                        is_relative=module_path.startswith('.')
                    )
                    imports.append(imp)
        
        # 解析 import xxx
        for match in import_pattern.finditer(content):
            module_path = match.group(1)
            alias = match.group(2)
            
            # 可能是包或模块
            imp = ExtractedImport(
                name=module_path.split('.')[0],  # 取第一部分作为名称
                alias=alias,
                path=module_path,
                is_from=False,
                is_relative=module_path.startswith('.')
            )
            imports.append(imp)
        
        return imports
    
    def resolve_import(
        self,
        imp: ExtractedImport,
        current_file: str
    ) -> Optional[ImportResolutionResult]:
        """
        解析导入到目标节点
        
        Args:
            imp: 导入信息
            current_file: 当前文件路径
            
        Returns:
            解析结果
        """
        cache_key = f"{current_file}:{imp.path}:{imp.name}"
        if cache_key in self.resolve_cache:
            cached = self.resolve_cache[cache_key]
            if cached:
                return cached
            return None
        
        result = None
        
        # 策略 1: 检查是否是相对导入
        if imp.is_relative:
            result = self._resolve_relative_import(imp, current_file)
        
        # 策略 2: 检查是否在项目中
        if not result:
            result = self._resolve_local_import(imp, current_file)
        
        # 策略 3: 模糊匹配
        if not result:
            result = self._resolve_fuzzy_import(imp)
        
        self.resolve_cache[cache_key] = result
        return result
    
    def _resolve_relative_import(
        self,
        imp: ExtractedImport,
        current_file: str
    ) -> Optional[ImportResolutionResult]:
        """解析相对导入"""
        current_dir = Path(current_file).parent
        
        # 计算目标目录
        if imp.path:
            # from . import xxx 或 from .. import xxx
            parts = imp.path.split('.')
            level = len([p for p in parts if p == '']) or 1
            
            # 计算相对路径
            for _ in range(level):
                current_dir = current_dir.parent
            
            # 添加剩余路径
            remaining = [p for p in parts if p]
            target_dir = current_dir / '/'.join(remaining) if remaining else current_dir
            
            # 查找文件
            for ext in ['.py', '__init__.py']:
                test_file = target_dir / f"{imp.name}{ext}"
                if test_file.exists():
                    return ImportResolutionResult(
                        node_id=f"File:{self._normalize_path(str(test_file))}",
                        confidence=0.95,
                        reason='import-resolved',
                        resolved_path=str(test_file)
                    )
        
        return None
    
    def _resolve_local_import(
        self,
        imp: ExtractedImport,
        current_file: str
    ) -> Optional[ImportResolutionResult]:
        """解析本地导入"""
        # 尝试多种路径组合
        current_dir = Path(current_file).parent
        module_name = imp.path or imp.name
        
        # 1. 同目录下
        for ext in ['', '.py']:
            test_path = current_dir / f"{module_name}{ext}"
            normalized = self._normalize_path(str(test_path))
            if normalized in self.normalized_file_list:
                return ImportResolutionResult(
                    node_id=f"File:{normalized}",
                    confidence=0.9,
                    reason='import-resolved',
                    resolved_path=str(test_path)
                )
        
        # 2. 查找子模块
        for file_path in self.normalized_file_list:
            if module_name in file_path:
                return ImportResolutionResult(
                    node_id=f"File:{file_path}",
                    confidence=0.85,
                    reason='import-resolved',
                    resolved_path=file_path
                )
        
        return None
    
    def _resolve_fuzzy_import(
        self,
        imp: ExtractedImport
    ) -> Optional[ImportResolutionResult]:
        """模糊匹配导入"""
        name_lower = imp.name.lower()
        
        # 查找名称相似的文件
        candidates = []
        for file_path in self.normalized_file_list:
            file_name = Path(file_path).stem.lower()
            if name_lower in file_name or file_name in name_lower:
                candidates.append((file_path, abs(len(name_lower) - len(file_name))))
        
        if candidates:
            # 返回最接近的
            candidates.sort(key=lambda x: x[1])
            best = candidates[0][0]
            
            return ImportResolutionResult(
                node_id=f"File:{best}",
                confidence=0.3,
                reason='fuzzy-global',
                resolved_path=best
            )
        
        return None
    
    def process_file(
        self,
        file_path: str,
        content: str
    ) -> List[Tuple[str, str, float, str]]:
        """
        处理单个文件，返回关系元组
        
        Returns:
            [(source_id, target_id, confidence, reason), ...]
        """
        imports = self.extract_imports(file_path, content)
        relationships = []
        
        source_id = f"File:{self._normalize_path(file_path)}"
        
        for imp in imports:
            result = self.resolve_import(imp, file_path)
            
            if result:
                relationships.append((
                    source_id,
                    result.node_id,
                    result.confidence,
                    result.reason
                ))
        
        return relationships
    
    def process_all(
        self,
        files: List[Tuple[str, str]]
    ) -> List[Tuple[str, str, float, str]]:
        """
        处理所有文件
        
        Args:
            files: [(file_path, content), ...]
            
        Returns:
            所有导入关系
        """
        # 构建文件索引
        file_paths = [f[0] for f in files]
        self.build_file_index(file_paths)
        
        all_relationships = []
        
        for file_path, content in files:
            relationships = self.process_file(file_path, content)
            all_relationships.extend(relationships)
        
        return all_relationships


def create_import_relationships(
    root_dir: str,
    files: List[Tuple[str, str]]
) -> List[Dict]:
    """
    创建导入关系的便捷函数
    
    Args:
        root_dir: 项目根目录
        files: [(file_path, content), ...]
        
    Returns:
        关系字典列表
    """
    from src.analysis.graph_types import (
        RelationshipType, create_relationship_id, calculate_confidence
    )
    
    processor = ImportProcessor(root_dir)
    raw_relationships = processor.process_all(files)
    
    relationships = []
    for source, target, conf, reason in raw_relationships:
        rel_id = create_relationship_id('IMPORTS', source, target)
        relationships.append({
            'id': rel_id,
            'sourceId': source,
            'targetId': target,
            'type': RelationshipType.IMPORTS.value,
            'confidence': conf,
            'reason': reason,
        })
    
    return relationships


# 测试
if __name__ == '__main__':
    # 简单测试
    test_code = """
import os
import sys
from pathlib import Path
from collections import defaultdict
from myapp.utils import helper
from . import local_module
from ..parent import ParentClass
"""
    
    processor = ImportProcessor('.')
    imports = processor._extract_imports_regex(test_code)
    
    print("提取的导入:")
    for imp in imports:
        print(f"  - {imp.name} (from={imp.is_from}, relative={imp.is_relative}, path={imp.path})")
