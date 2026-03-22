#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
包含关系抽取器 - 抽取所有包含关系
"""

from typing import Dict, List, Set, Tuple
from pathlib import Path
import os
from .code_model import (
    RepositoryInfo, PackageInfo, ClassInfo, MethodInfo, FieldInfo, Parameter,
    ProjectAnalysisReport, RelationType, ElementType
)


class ContainsRelationExtractor:
    """包含关系抽取器"""
    
    def __init__(self):
        self.contains_relations: List[Tuple[str, str, RelationType]] = []  # (source_id, target_id, relation_type)
    
    def extract_all_contains_relations(self, report: ProjectAnalysisReport) -> List[Tuple[str, str, RelationType]]:
        """
        抽取所有包含关系
        
        Returns:
            List of (source_id, target_id, relation_type) tuples
        """
        self.contains_relations = []
        
        # 1. 仓库 → 包/模块的包含关系
        self._extract_repository_contains_package(report)
        
        # 2. 包/模块 → 类的包含关系
        self._extract_package_contains_class(report)
        
        # 3. 文件 → 类的包含关系
        self._extract_file_contains_class(report)
        
        # 4. 类 → 方法/字段的包含关系
        self._extract_class_contains_method_and_field(report)
        
        # 5. 函数/方法 → 参数的包含关系
        self._extract_function_contains_parameter(report)
        
        return self.contains_relations
    
    def _extract_repository_contains_package(self, report: ProjectAnalysisReport):
        """抽取仓库 → 包/模块的包含关系"""
        if not hasattr(report, 'packages') or not report.packages:
            return
        
        repository_id = f"repository_{report.project_name}"
        
        for package in report.packages.values():
            package_id = f"package_{package.name}"
            self.contains_relations.append((
                repository_id,
                package_id,
                RelationType.REPOSITORY_CONTAINS_PACKAGE
            ))
    
    def _extract_package_contains_class(self, report: ProjectAnalysisReport):
        """抽取包/模块 → 类的包含关系"""
        if not hasattr(report, 'packages') or not report.packages:
            return
        
        # 从类的full_name中提取包名
        for class_info in report.classes.values():
            # 假设full_name格式为 "package.ClassName"
            parts = class_info.full_name.split('.')
            if len(parts) > 1:
                package_name = '.'.join(parts[:-1])
                package_id = f"package_{package_name}"
                class_id = f"class_{class_info.full_name}"
                
                self.contains_relations.append((
                    package_id,
                    class_id,
                    RelationType.PACKAGE_CONTAINS_CLASS
                ))
    
    def _extract_file_contains_class(self, report: ProjectAnalysisReport):
        """抽取文件 → 类的包含关系"""
        for class_info in report.classes.values():
            if class_info.source_location:
                file_path = class_info.source_location.file_path
                file_id = f"file_{file_path}"
                class_id = f"class_{class_info.full_name}"
                
                self.contains_relations.append((
                    file_id,
                    class_id,
                    RelationType.FILE_CONTAINS_CLASS
                ))
    
    def _extract_class_contains_method_and_field(self, report: ProjectAnalysisReport):
        """抽取类 → 方法/字段的包含关系"""
        for class_info in report.classes.values():
            class_id = f"class_{class_info.full_name}"
            
            # 类包含方法
            for method in class_info.methods.values():
                method_id = f"method_{method.get_full_name()}"
                self.contains_relations.append((
                    class_id,
                    method_id,
                    RelationType.CLASS_CONTAINS_METHOD
                ))
            
            # 类包含字段
            for field in class_info.fields.values():
                field_id = f"field_{class_info.full_name}.{field.name}"
                self.contains_relations.append((
                    class_id,
                    field_id,
                    RelationType.CLASS_CONTAINS_FIELD
                ))
    
    def _extract_function_contains_parameter(self, report: ProjectAnalysisReport):
        """抽取函数/方法 → 参数的包含关系"""
        # 处理类中的方法
        for class_info in report.classes.values():
            for method in class_info.methods.values():
                method_id = f"method_{method.get_full_name()}"
                
                for param in method.parameters:
                    param_id = f"parameter_{method.get_full_name()}.{param.name}"
                    self.contains_relations.append((
                        method_id,
                        param_id,
                        RelationType.METHOD_CONTAINS_PARAMETER
                    ))
        
        # 处理全局函数
        for function in report.functions:
            function_id = f"function_{function.name}"
            
            for param in function.parameters:
                param_id = f"parameter_{function.name}.{param.name}"
                self.contains_relations.append((
                    function_id,
                    param_id,
                    RelationType.FUNCTION_CONTAINS_PARAMETER
                ))




























































