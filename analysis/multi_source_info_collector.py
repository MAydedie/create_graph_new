#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
多源信息收集器 - 收集代码规范、README、文件结构等信息
用于功能分区识别的信息融合
"""

import os
import re
from typing import Dict, List, Set, Optional, Any, Tuple
from pathlib import Path
import logging

from parsers.comment_extractor import CommentExtractor
from analysis.code_model import ProjectAnalysisReport, MethodInfo, ClassInfo

logger = logging.getLogger(__name__)


class MultiSourceInfoCollector:
    """多源信息收集器"""
    
    def __init__(self, project_path: str, report: ProjectAnalysisReport):
        self.project_path = project_path
        self.report = report
        self.readme_content = ""
        self.comments_summary = {}
        self.path_info = {}
        self.naming_patterns = {}
        self.data_flow_dependencies = {}
        self.method_similarities = {}
    
    def collect_all(self) -> Dict[str, Any]:
        """
        收集所有多源信息
        
        Returns:
            包含所有收集信息的字典
        """
        logger.info("[MultiSourceInfoCollector] 开始收集多源信息...")
        
        # 1. README解析和关键词提取
        self._collect_readme()
        
        # 2. 代码注释和docstring提取
        self._collect_comments()
        
        # 3. 文件路径信息收集
        self._collect_path_info()
        
        # 4. 命名模式识别
        self._collect_naming_patterns()
        
        # 5. 数据流依赖分析
        self._collect_data_flow_dependencies()
        
        # 6. 方法相似度计算
        self._calculate_method_similarities()
        
        logger.info("[MultiSourceInfoCollector] ✓ 多源信息收集完成")
        
        return {
            "readme": {
                "content": self.readme_content,
                "keywords": self._extract_readme_keywords()
            },
            "comments": self.comments_summary,
            "path_info": self.path_info,
            "naming_patterns": self.naming_patterns,
            "data_flow": self.data_flow_dependencies,
            "method_similarities": self.method_similarities
        }
    
    def _collect_readme(self):
        """收集README内容"""
        readme_paths = [
            os.path.join(self.project_path, "README.md"),
            os.path.join(self.project_path, "readme.md"),
            os.path.join(self.project_path, "README.txt"),
            os.path.join(self.project_path, "README.rst"),
        ]
        
        for readme_path in readme_paths:
            if os.path.exists(readme_path):
                try:
                    with open(readme_path, 'r', encoding='utf-8', errors='ignore') as f:
                        self.readme_content = f.read()
                    logger.info(f"[MultiSourceInfoCollector] ✓ 读取README: {readme_path}")
                    return
                except Exception as e:
                    logger.warning(f"[MultiSourceInfoCollector] 读取README失败: {e}")
        
        logger.warning("[MultiSourceInfoCollector] ⚠️ 未找到README文件")
    
    def _extract_readme_keywords(self) -> List[str]:
        """从README提取关键词"""
        if not self.readme_content:
            return []
        
        # 提取标题和功能描述关键词
        keywords = []
        
        # 提取Markdown标题
        title_pattern = r'^#+\s+(.+)$'
        for line in self.readme_content.split('\n'):
            match = re.match(title_pattern, line)
            if match:
                keywords.append(match.group(1).strip())
        
        # 提取功能模块关键词（如"## 功能模块"下的内容）
        section_pattern = r'##\s+(功能|模块|Features|Modules?)\s*\n(.*?)(?=\n##|\Z)'
        matches = re.findall(section_pattern, self.readme_content, re.DOTALL | re.IGNORECASE)
        for _, content in matches:
            # 提取列表项
            list_items = re.findall(r'[-*]\s+(.+)', content)
            keywords.extend(list_items)
        
        return list(set(keywords))
    
    def _collect_comments(self):
        """收集代码注释和docstring"""
        logger.info("[MultiSourceInfoCollector] 提取代码注释...")
        
        # 获取所有Python文件
        python_files = []
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules']]
            for file in files:
                if file.endswith('.py'):
                    python_files.append(os.path.join(root, file))
        
        total_comments = 0
        for file_path in python_files[:100]:  # 限制前100个文件，避免太慢
            try:
                extractor = CommentExtractor(file_path)
                comments = extractor.extract_all_comments()
                
                # 保存docstring
                for entity_id, docstring in comments.get('docstrings', {}).items():
                    self.comments_summary[entity_id] = {
                        'docstring': docstring,
                        'file': file_path,
                        'inline_comments': []
                    }
                    total_comments += 1
                
                # 保存行内注释（关联到最近的代码元素）
                for line_num, comment_text in comments.get('inline_comments', {}).items():
                    # 简化处理：保存到文件级别
                    file_key = f"file_{os.path.basename(file_path)}"
                    if file_key not in self.comments_summary:
                        self.comments_summary[file_key] = {
                            'docstring': '',
                            'file': file_path,
                            'inline_comments': []
                        }
                    self.comments_summary[file_key]['inline_comments'].append({
                        'line': line_num,
                        'text': comment_text
                    })
            except Exception as e:
                logger.debug(f"[MultiSourceInfoCollector] 提取注释失败 {file_path}: {e}")
        
        logger.info(f"[MultiSourceInfoCollector] ✓ 提取了 {total_comments} 个代码元素的注释")
    
    def _collect_path_info(self):
        """收集文件路径信息（基础信息，不含语义分析）"""
        logger.info("[MultiSourceInfoCollector] 收集文件路径信息...")
        
        # 为每个方法收集文件路径信息
        for class_name, class_info in self.report.classes.items():
            for method_name, method_info in class_info.methods.items():
                if method_info.source_location:
                    file_path = method_info.source_location.file_path
                    method_sig = f"{class_name}.{method_name}"
                    
                    # 提取路径信息
                    rel_path = os.path.relpath(file_path, self.project_path)
                    path_parts = rel_path.replace('\\', '/').split('/')
                    folder_path = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else ''
                    
                    self.path_info[method_sig] = {
                        "file_path": file_path,
                        "relative_path": rel_path,
                        "folder_path": folder_path,
                        "file_name": os.path.basename(file_path),
                        "path_depth": len(path_parts) - 1,
                        "path_parts": path_parts
                    }
        
        # 为函数收集路径信息
        for func_info in self.report.functions:
            if func_info.source_location:
                file_path = func_info.source_location.file_path
                method_sig = func_info.name
                
                rel_path = os.path.relpath(file_path, self.project_path)
                path_parts = rel_path.replace('\\', '/').split('/')
                folder_path = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else ''
                
                self.path_info[method_sig] = {
                    "file_path": file_path,
                    "relative_path": rel_path,
                    "folder_path": folder_path,
                    "file_name": os.path.basename(file_path),
                    "path_depth": len(path_parts) - 1,
                    "path_parts": path_parts
                }
        
        logger.info(f"[MultiSourceInfoCollector] ✓ 收集了 {len(self.path_info)} 个方法的路径信息")
    
    def _collect_naming_patterns(self):
        """识别命名模式"""
        logger.info("[MultiSourceInfoCollector] 识别命名模式...")
        
        method_patterns = {}
        class_patterns = {}
        
        # 分析方法名模式
        for class_name, class_info in self.report.classes.items():
            for method_name, method_info in class_info.methods.items():
                method_sig = f"{class_name}.{method_name}"
                
                # 提取方法名前缀（如 parse_, analyze_, get_）
                prefix = self._extract_prefix(method_name)
                if prefix:
                    if prefix not in method_patterns:
                        method_patterns[prefix] = []
                    method_patterns[prefix].append(method_sig)
        
        # 分析类名模式
        for class_name, class_info in self.report.classes.items():
            # 提取类名后缀（如 Parser, Analyzer, Generator）
            suffix = self._extract_suffix(class_name)
            if suffix:
                if suffix not in class_patterns:
                    class_patterns[suffix] = []
                class_patterns[suffix].append(class_name)
        
        self.naming_patterns = {
            "method_prefixes": method_patterns,
            "class_suffixes": class_patterns
        }
        
        logger.info(f"[MultiSourceInfoCollector] ✓ 识别了 {len(method_patterns)} 个方法名前缀模式")
        logger.info(f"[MultiSourceInfoCollector] ✓ 识别了 {len(class_patterns)} 个类名后缀模式")
    
    def _extract_prefix(self, name: str) -> Optional[str]:
        """提取方法名前缀"""
        # 下划线命名：parse_file -> parse
        if '_' in name:
            parts = name.split('_')
            if len(parts) > 1:
                return parts[0] + '_'
        
        # 驼峰命名：parseFile -> parse（简化处理）
        match = re.match(r'^([a-z]+)', name)
        if match:
            return match.group(1) + '_'
        
        return None
    
    def _extract_suffix(self, name: str) -> Optional[str]:
        """提取类名后缀"""
        # 驼峰命名：PythonParser -> Parser
        match = re.match(r'^[A-Z][a-z]*(.+)$', name)
        if match:
            suffix = match.group(1)
            if len(suffix) > 2:  # 至少3个字符
                return suffix
        
        return None
    
    def _collect_data_flow_dependencies(self):
        """收集数据流依赖"""
        logger.info("[MultiSourceInfoCollector] 分析数据流依赖...")
        
        # 从report中提取已有的数据流信息
        # 这里简化处理，实际应该从DataFlowAnalyzer获取
        
        parameter_flows = {}
        shared_parameters = {}
        
        # 分析参数传递链
        for class_name, class_info in self.report.classes.items():
            for method_name, method_info in class_info.methods.items():
                method_sig = f"{class_name}.{method_name}"
                
                # 收集方法的参数
                param_names = [p.name for p in method_info.parameters]
                if param_names:
                    parameter_flows[method_sig] = param_names
                    
                    # 统计共享参数
                    for param_name in param_names:
                        if param_name not in shared_parameters:
                            shared_parameters[param_name] = []
                        shared_parameters[param_name].append(method_sig)
        
        self.data_flow_dependencies = {
            "parameter_flows": parameter_flows,
            "shared_parameters": {k: v for k, v in shared_parameters.items() if len(v) > 1}
        }
        
        logger.info(f"[MultiSourceInfoCollector] ✓ 分析了 {len(parameter_flows)} 个方法的参数")
        logger.info(f"[MultiSourceInfoCollector] ✓ 发现 {len(self.data_flow_dependencies['shared_parameters'])} 个共享参数")
    
    def _calculate_method_similarities(self):
        """计算方法相似度"""
        logger.info("[MultiSourceInfoCollector] 计算方法相似度...")
        
        all_methods = list(self.path_info.keys())
        
        for i, method1 in enumerate(all_methods):
            for method2 in all_methods[i+1:]:
                similarity = self._calculate_similarity(method1, method2)
                if similarity > 0:
                    key = tuple(sorted([method1, method2]))
                    self.method_similarities[key] = similarity
        
        logger.info(f"[MultiSourceInfoCollector] ✓ 计算了 {len(self.method_similarities)} 个方法对的相似度")
    
    def _calculate_similarity(self, method1: str, method2: str) -> float:
        """
        计算两个方法的相似度
        
        融合策略：
        - 调用关系权重（40%）
        - 文件路径相似度（20%）
        - 命名模式相似度（15%）
        - 数据流依赖（15%）
        - 继承关系（10%）
        """
        score = 0.0
        
        # 1. 调用关系权重（40%）
        # 这里简化处理，实际应该从call_graph获取
        # 假设如果两个方法在同一个类中，有调用关系
        class1 = method1.split('.')[0] if '.' in method1 else None
        class2 = method2.split('.')[0] if '.' in method2 else None
        if class1 and class2 and class1 == class2:
            score += 0.2  # 同类方法，部分权重
        
        # 2. 文件路径相似度（20%）
        if method1 in self.path_info and method2 in self.path_info:
            path1 = self.path_info[method1]
            path2 = self.path_info[method2]
            
            if path1['folder_path'] == path2['folder_path']:
                score += 0.2
        
        # 3. 命名模式相似度（15%）
        name1 = method1.split('.')[-1] if '.' in method1 else method1
        name2 = method2.split('.')[-1] if '.' in method2 else method2
        
        prefix1 = self._extract_prefix(name1)
        prefix2 = self._extract_prefix(name2)
        if prefix1 and prefix2 and prefix1 == prefix2:
            score += 0.15
        
        # 4. 数据流依赖（15%）
        if method1 in self.data_flow_dependencies.get('parameter_flows', {}) and \
           method2 in self.data_flow_dependencies.get('parameter_flows', {}):
            params1 = set(self.data_flow_dependencies['parameter_flows'][method1])
            params2 = set(self.data_flow_dependencies['parameter_flows'][method2])
            
            if params1 & params2:  # 有共同参数
                score += 0.15
        
        # 5. 继承关系（10%）
        # 简化处理：如果两个方法在同一个类中，已经在上面的调用关系中考虑了
        # 这里可以进一步检查继承关系
        
        return score
    
    def get_method_info_summary(self, method_sig: str) -> Dict[str, Any]:
        """获取方法的综合信息摘要"""
        summary = {
            "method": method_sig,
            "path_info": self.path_info.get(method_sig, {}),
            "comments": self.comments_summary.get(f"method_{method_sig}", {}),
            "naming_pattern": None,
            "data_flow": {}
        }
        
        # 命名模式
        name = method_sig.split('.')[-1] if '.' in method_sig else method_sig
        prefix = self._extract_prefix(name)
        if prefix:
            summary["naming_pattern"] = prefix
        
        # 数据流
        if method_sig in self.data_flow_dependencies.get('parameter_flows', {}):
            summary["data_flow"]["parameters"] = self.data_flow_dependencies['parameter_flows'][method_sig]
        
        return summary
    
    def get_similar_methods(self, method_sig: str, threshold: float = 0.3) -> List[Tuple[str, float]]:
        """获取相似方法列表"""
        similar = []
        
        for (m1, m2), similarity in self.method_similarities.items():
            if similarity >= threshold:
                if m1 == method_sig:
                    similar.append((m2, similarity))
                elif m2 == method_sig:
                    similar.append((m1, similarity))
        
        # 按相似度排序
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar






















