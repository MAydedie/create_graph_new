#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
方法功能画像构建器 - 整合路径语义和代码线索，构建方法的功能画像
用于LLM优化功能分区的语义信息整合
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
import os
import logging

from analysis.code_model import MethodInfo, ClassInfo, ProjectAnalysisReport
from analysis.path_semantic_analyzer import PathSemanticAnalyzer
from analysis.code_semantic_clue_extractor import CodeSemanticClueExtractor

logger = logging.getLogger(__name__)


@dataclass
class MethodFunctionProfile:
    """方法功能画像"""
    method_signature: str              # 方法签名 (ClassName.methodName)
    file_path: str                     # 文件路径
    path_semantics: Dict[str, Any]     # 路径语义信息
    code_clues: Dict[str, Any]         # 代码线索信息
    inferred_functions: List[str]      # LLM推断的功能列表（初始为空，由LLM填充）
    confidence: float = 0.0            # 功能推断的置信度（0.0-1.0）
    
    # 元数据
    class_name: str = ""
    method_name: str = ""
    docstring: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于JSON序列化）"""
        return asdict(self)


class MethodFunctionProfileBuilder:
    """方法功能画像构建器"""
    
    def __init__(self, project_path: str, report: ProjectAnalysisReport):
        """
        初始化构建器
        
        Args:
            project_path: 项目根路径
            report: 项目分析报告
        """
        self.project_path = project_path
        self.report = report
        self.path_analyzer = PathSemanticAnalyzer(project_path=project_path)
        self.clue_extractor = CodeSemanticClueExtractor()
        
        # 缓存：避免重复提取
        self._profile_cache: Dict[str, MethodFunctionProfile] = {}
        self._file_content_cache: Dict[str, str] = {}
    
    def build_profile(self, method_signature: str) -> Optional[MethodFunctionProfile]:
        """
        为指定方法构建功能画像
        
        Args:
            method_signature: 方法签名 (ClassName.methodName)
        
        Returns:
            方法功能画像，如果方法不存在则返回None
        """
        # 检查缓存
        if method_signature in self._profile_cache:
            return self._profile_cache[method_signature]
        
        # 查找方法信息
        method_info, class_info = self._find_method(method_signature)
        if not method_info:
            logger.warning(f"未找到方法: {method_signature}")
            return None
        
        # 获取文件路径
        file_path = self._get_file_path(method_info, class_info)
        if not file_path:
            logger.warning(f"无法确定文件路径: {method_signature}")
            return None
        
        # 1. 提取路径语义
        path_semantics = self.path_analyzer.extract_path_semantics(file_path)
        
        # 2. 提取代码线索
        file_content = self._get_file_content(file_path)
        code_clues = self.clue_extractor.extract_clues(
            method_info=method_info,
            class_info=class_info,
            file_content=file_content
        )
        
        # 3. 构建功能画像
        profile = MethodFunctionProfile(
            method_signature=method_signature,
            file_path=file_path,
            path_semantics=path_semantics,
            code_clues=code_clues,
            inferred_functions=[],  # 由LLM填充
            confidence=0.0,
            class_name=method_info.class_name,
            method_name=method_info.name,
            docstring=method_info.docstring or "",
        )
        
        # 4. 计算初始置信度（基于路径语义的推断）
        if path_semantics.get("suggested_functions"):
            # 如果路径语义能推断出功能，设置较低的初始置信度
            profile.confidence = 0.3
        
        # 5. 缓存结果
        self._profile_cache[method_signature] = profile
        
        return profile
    
    def build_profiles_batch(self, method_signatures: List[str]) -> Dict[str, MethodFunctionProfile]:
        """
        批量构建功能画像
        
        Args:
            method_signatures: 方法签名列表
        
        Returns:
            {method_signature: MethodFunctionProfile}
        """
        profiles = {}
        
        for method_sig in method_signatures:
            try:
                profile = self.build_profile(method_sig)
                if profile:
                    profiles[method_sig] = profile
            except Exception as e:
                logger.warning(f"构建功能画像失败 {method_sig}: {e}")
        
        logger.info(f"[MethodFunctionProfileBuilder] 批量构建完成: {len(profiles)}/{len(method_signatures)}")
        return profiles
    
    def _find_method(self, method_signature: str) -> Tuple[Optional[MethodInfo], Optional[ClassInfo]]:
        """
        查找方法信息和类信息
        
        Returns:
            (MethodInfo, ClassInfo) 或 (None, None)
        """
        # 解析方法签名: "ClassName.methodName" 或 "functionName"
        if '.' in method_signature:
            class_name, method_name = method_signature.rsplit('.', 1)
            # 查找类
            for full_class_name, class_info in self.report.classes.items():
                if class_info.name == class_name or full_class_name == class_name:
                    # 查找方法
                    if method_name in class_info.methods:
                        return class_info.methods[method_name], class_info
        else:
            # 查找全局函数
            for func_info in self.report.functions:
                if func_info.name == method_signature:
                    return func_info, None
        
        # 如果通过名称找不到，尝试通过签名查找
        for full_class_name, class_info in self.report.classes.items():
            for method_info in class_info.methods.values():
                if method_info.signature == method_signature:
                    return method_info, class_info
        
        for func_info in self.report.functions:
            if func_info.signature == method_signature:
                return func_info, None
        
        return None, None
    
    def _get_file_path(self, method_info: MethodInfo, 
                      class_info: Optional[ClassInfo]) -> Optional[str]:
        """
        获取文件路径
        
        Returns:
            文件路径（绝对路径），如果无法确定则返回None
        """
        # 优先使用 source_location
        if method_info.source_location:
            file_path = method_info.source_location.file_path
            # 如果是相对路径，转换为绝对路径
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.project_path, file_path)
            return os.path.normpath(file_path)
        
        # 如果类信息有 source_location
        if class_info and class_info.source_location:
            file_path = class_info.source_location.file_path
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.project_path, file_path)
            return os.path.normpath(file_path)
        
        # 如果report中有package信息，可以从包路径推断
        # 这里简化处理，返回None表示无法确定
        return None
    
    def _get_file_content(self, file_path: str) -> Optional[str]:
        """
        获取文件内容（带缓存）
        
        Args:
            file_path: 文件路径
        
        Returns:
            文件内容，如果读取失败则返回None
        """
        # 检查缓存
        if file_path in self._file_content_cache:
            return self._file_content_cache[file_path]
        
        # 读取文件
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            self._file_content_cache[file_path] = content
            return content
        except Exception as e:
            logger.warning(f"读取文件失败 {file_path}: {e}")
            return None
    
    def clear_cache(self):
        """清空缓存"""
        self._profile_cache.clear()
        self._file_content_cache.clear()
        logger.info("[MethodFunctionProfileBuilder] 缓存已清空")
    
    def format_profiles_for_llm(self, profiles: Dict[str, MethodFunctionProfile]) -> str:
        """
        将功能画像格式化为LLM可读的文本
        
        Args:
            profiles: 功能画像字典
        
        Returns:
            格式化的文本
        """
        lines = []
        lines.append("# 方法功能画像")
        lines.append("")
        
        for method_sig, profile in profiles.items():
            lines.append(f"## {method_sig}")
            lines.append(f"- 文件路径: {profile.file_path}")
            
            # 路径语义
            path_sem = profile.path_semantics
            if path_sem.get("suggested_functions"):
                lines.append(f"- 路径推断功能: {', '.join(path_sem['suggested_functions'])}")
            lines.append(f"- 路径token: {', '.join(path_sem.get('path_tokens', []))}")
            lines.append(f"- 命名风格: {path_sem.get('naming_style', 'unknown')}")
            
            # 代码线索
            clues = profile.code_clues
            if clues.get("decorators"):
                lines.append(f"- 装饰器: {', '.join(clues['decorators'])}")
            if clues.get("inheritance"):
                lines.append(f"- 继承: {', '.join(clues['inheritance'])}")
            if clues.get("imports"):
                # 只显示前5个导入
                imports_preview = clues['imports'][:5]
                lines.append(f"- 导入: {', '.join(imports_preview)}")
            if profile.docstring:
                lines.append(f"- Docstring: {profile.docstring[:100]}...")
            if clues.get("comments"):
                # 只显示前3个注释
                comments_preview = clues['comments'][:3]
                lines.append(f"- 注释: {', '.join(comments_preview)}")
            
            lines.append("")
        
        return "\n".join(lines)


def main():
    """测试代码"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # 这里需要实际的report对象，测试时简化
    from analysis.code_model import ProjectAnalysisReport, MethodInfo, ClassInfo, SourceLocation
    
    # 创建测试数据
    report = ProjectAnalysisReport(
        project_name="test",
        project_path="D:/代码仓库生图/create_graph",
        analysis_timestamp="2024-12-30"
    )
    
    # 创建测试方法
    source_loc = SourceLocation(
        file_path="parsers/python_parser.py",
        line_start=10,
        line_end=50
    )
    
    class_info = ClassInfo(
        name="PythonParser",
        full_name="PythonParser",
        source_location=source_loc
    )
    
    method_info = MethodInfo(
        name="parse",
        class_name="PythonParser",
        signature="PythonParser.parse(code: str) -> dict",
        return_type="dict",
        source_location=source_loc,
        docstring="解析Python代码"
    )
    
    class_info.add_method(method_info)
    report.add_class(class_info)
    
    # 构建功能画像
    builder = MethodFunctionProfileBuilder(
        project_path="D:/代码仓库生图/create_graph",
        report=report
    )
    
    profile = builder.build_profile("PythonParser.parse")
    
    if profile:
        print("=" * 60)
        print("方法功能画像构建测试")
        print("=" * 60)
        print(f"方法签名: {profile.method_signature}")
        print(f"文件路径: {profile.file_path}")
        print(f"路径推断功能: {profile.path_semantics.get('suggested_functions')}")
        print(f"代码线索装饰器: {profile.code_clues.get('decorators')}")
    else:
        print("构建功能画像失败")


if __name__ == "__main__":
    main()

