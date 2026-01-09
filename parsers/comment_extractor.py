#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代码注释提取器 - 从 Python 源代码中提取注释
参考 JUnitGenie 的实现思路
"""

import ast
import tokenize
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from io import StringIO


class CommentExtractor:
    """代码注释提取器"""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.source_lines = []
        self.comments_map = {}  # {line_number: comment_text}
        self.docstrings_map = {}  # {entity_id: docstring}
        
    def extract_all_comments(self) -> Dict:
        """
        提取文件中的所有注释
        
        Returns:
            {
                'inline_comments': {line_number: comment_text},
                'docstrings': {entity_id: docstring},
                'block_comments': List[comment_text]
            }
        """
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.source_lines = f.readlines()
                source_code = ''.join(self.source_lines)
        except Exception as e:
            print(f"[CommentExtractor] 读取文件失败: {e}")
            return {'inline_comments': {}, 'docstrings': {}, 'block_comments': []}
        
        # 提取行内注释
        inline_comments = self._extract_inline_comments(source_code)
        
        # 提取 docstring
        docstrings = self._extract_docstrings(source_code)
        
        # 提取块注释（多行字符串，但不是 docstring）
        block_comments = self._extract_block_comments(source_code)
        
        return {
            'inline_comments': inline_comments,
            'docstrings': docstrings,
            'block_comments': block_comments
        }
    
    def _extract_inline_comments(self, source_code: str) -> Dict[int, str]:
        """提取行内注释（# comment）"""
        comments = {}
        
        try:
            # 使用 tokenize 模块提取注释
            tokens = tokenize.generate_tokens(StringIO(source_code).readline)
            
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    line_num = token.start[0]
                    comment_text = token.string.strip()
                    if comment_text.startswith('#'):
                        comment_text = comment_text[1:].strip()
                    if comment_text:
                        comments[line_num] = comment_text
        except Exception as e:
            print(f"[CommentExtractor] 提取行内注释失败: {e}")
        
        return comments
    
    def _extract_docstrings(self, source_code: str) -> Dict[str, str]:
        """提取 docstring（类、函数、方法的文档字符串）"""
        docstrings = {}
        
        try:
            tree = ast.parse(source_code, filename=str(self.file_path))
            
            class DocstringVisitor(ast.NodeVisitor):
                def __init__(self, extractor):
                    self.extractor = extractor
                    self.current_class = None
                
                def visit_ClassDef(self, node):
                    self.current_class = node.name
                    docstring = ast.get_docstring(node)
                    if docstring:
                        entity_id = f"class_{node.name}"
                        docstrings[entity_id] = docstring
                    self.generic_visit(node)
                    self.current_class = None
                
                def visit_FunctionDef(self, node):
                    docstring = ast.get_docstring(node)
                    if docstring:
                        if self.current_class:
                            entity_id = f"method_{self.current_class}_{node.name}"
                        else:
                            entity_id = f"function_{node.name}"
                        docstrings[entity_id] = docstring
                    self.generic_visit(node)
            
            visitor = DocstringVisitor(self)
            visitor.visit(tree)
            
        except Exception as e:
            print(f"[CommentExtractor] 提取 docstring 失败: {e}")
        
        return docstrings
    
    def _extract_block_comments(self, source_code: str) -> List[str]:
        """提取块注释（多行字符串，但不是 docstring）"""
        block_comments = []
        
        try:
            tree = ast.parse(source_code, filename=str(self.file_path))
            
            class BlockCommentVisitor(ast.NodeVisitor):
                def visit_Expr(self, node):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        # 这是一个字符串表达式，可能是注释
                        if not self._is_docstring(node):
                            block_comments.append(node.value.value)
                    self.generic_visit(node)
                
                def _is_docstring(self, node):
                    # 检查是否是 docstring（在类/函数的第一行）
                    # 简化判断：如果字符串很长且包含文档性内容，可能是注释
                    return False
            
            visitor = BlockCommentVisitor()
            visitor.visit(tree)
            
        except Exception as e:
            print(f"[CommentExtractor] 提取块注释失败: {e}")
        
        return block_comments
    
    def get_comments_for_entity(self, entity_type: str, entity_name: str, 
                                class_name: Optional[str] = None,
                                line_start: int = 0, line_end: int = 0) -> List[str]:
        """
        获取特定代码元素的注释
        
        Args:
            entity_type: 'class', 'method', 'function'
            entity_name: 实体名称
            class_name: 类名（如果是方法）
            line_start: 开始行号
            line_end: 结束行号
            
        Returns:
            注释列表
        """
        comments = []
        
        # 构建 entity_id
        if entity_type == 'class':
            entity_id = f"class_{entity_name}"
        elif entity_type == 'method' and class_name:
            entity_id = f"method_{class_name}_{entity_name}"
        else:
            entity_id = f"function_{entity_name}"
        
        # 提取所有注释
        all_comments = self.extract_all_comments()
        
        # 获取 docstring
        if entity_id in all_comments['docstrings']:
            comments.append(all_comments['docstrings'][entity_id])
        
        # 获取行内注释（在代码元素范围内的）
        for line_num, comment_text in all_comments['inline_comments'].items():
            if line_start <= line_num <= line_end:
                comments.append(comment_text)
        
        return comments



























