#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LangChain Agent - 用于智能理解项目结构和识别功能分区
使用DeepSeek API
"""

import json
import os
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
import logging

# Phase 0 / Task 0.2: 统一LLM调用封装
from llm.llm_helper import get_llm_helper

# 可选导入 LangChain（如果可用）
try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.callbacks import CallbackManager, StreamingStdOutCallbackHandler
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.warning("LangChain 未安装，将使用直接 API 调用")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 导入 hierarchy_model 中的 FunctionPartition（统一使用，避免重复定义）
try:
    from analysis.hierarchy_model import FunctionPartition, FunctionStats
except ImportError:
    # 如果导入失败，定义完整版本（向后兼容）
    from dataclasses import field
    
    @dataclass
    class FunctionStats:
        total_classes: int = 0
        total_methods: int = 0
        total_functions: int = 0
        total_lines_of_code: int = 0
        total_critical_codes: int = 0
    
    @dataclass
    class FunctionPartition:
        """功能分区定义"""
        name: str
        description: str
        folders: List[str] = field(default_factory=list)
        keywords: List[str] = field(default_factory=list)
        stats: FunctionStats = field(default_factory=FunctionStats)
        contained_code_entities: List[str] = field(default_factory=list)
        important_codes: Dict[str, List[str]] = field(default_factory=dict)
        outgoing_calls: Dict[str, int] = field(default_factory=dict)
        incoming_calls: Dict[str, int] = field(default_factory=dict)
        function_relations: List = field(default_factory=list)
        is_core_function: bool = False


@dataclass
class ImportantCode:
    """重要代码标注"""
    file_path: str
    entity_type: str  # class/function/method
    entity_name: str
    full_signature: str
    importance_mark: str  # "重要-1", "重要-2" 等
    reason: str  # 为什么重要


class CodeUnderstandingAgent:
    """使用LLM理解项目的Agent"""
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1"):
        """
        初始化Agent
        
        Args:
            api_key: DeepSeek API密钥
            base_url: DeepSeek API基础URL
        """
        self.api_key = api_key
        self.base_url = base_url
        self.project_path = None
        self.readme_content = None
        self.all_comments = {}  # {file_path: {code_element: comment}}
        self.function_partitions: List[FunctionPartition] = []
        self.important_codes: List[ImportantCode] = []
        
        logger.info(f"初始化CodeUnderstandingAgent，base_url: {base_url}")

        # 统一使用全局 LLMHelper（内部自动选择 LangChain 或 requests，并带重试）
        self.llm_helper = get_llm_helper()
        # 向后兼容：保留旧字段，避免历史逻辑/日志引用时报错
        self.llm = None
        self._use_direct_api = False
    
    def load_project(self, project_path: str) -> Dict[str, Any]:
        """
        加载项目信息
        
        Args:
            project_path: 项目路径
            
        Returns:
            项目基本信息字典
        """
        self.project_path = project_path
        logger.info(f"加载项目: {project_path}")
        
        project_info = {
            "path": project_path,
            "name": os.path.basename(project_path),
            "structure": self._get_project_structure(),
            "readme": self._load_readme(),
            "files_count": 0,
            "total_lines": 0
        }
        
        # 统计Python文件
        py_files = list(Path(project_path).rglob("*.py"))
        project_info["files_count"] = len(py_files)
        
        logger.info(f"✓ 项目加载完成: {len(py_files)} 个Python文件")
        return project_info
    
    def _load_readme(self) -> str:
        """加载README文件"""
        readme_paths = [
            os.path.join(self.project_path, "README.md"),
            os.path.join(self.project_path, "readme.md"),
            os.path.join(self.project_path, "README.txt"),
        ]
        
        for readme_path in readme_paths:
            if os.path.exists(readme_path):
                try:
                    with open(readme_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.readme_content = content
                    logger.info(f"✓ 读取README: {readme_path} ({len(content)} 字符)")
                    return content
                except Exception as e:
                    logger.warning(f"读取README失败: {e}")
        
        logger.warning("⚠️ 未找到README文件")
        return ""
    
    def _get_project_structure(self) -> Dict[str, List[str]]:
        """获取项目结构"""
        structure = {}
        try:
            for root, dirs, files in os.walk(self.project_path):
                # 跳过常见的非代码目录
                dirs[:] = [d for d in dirs if d not in [
                    '.git', '__pycache__', '.venv', 'venv', 'node_modules', 
                    '.idea', '.pytest_cache', 'build', 'dist', '*.egg-info'
                ]]
                
                py_files = [f for f in files if f.endswith('.py')]
                if py_files:
                    rel_path = os.path.relpath(root, self.project_path)
                    structure[rel_path] = py_files
        
        except Exception as e:
            logger.error(f"获取项目结构失败: {e}")
        
        return structure
    
    def analyze_project_overview(self) -> str:
        """
        第一步：分析项目概览（从README）
        用LLM理解项目的整体架构和功能
        
        Returns:
            项目概览分析结果
        """
        logger.info("\n" + "="*50)
        logger.info("📖 阶段1：项目概览分析")
        logger.info("="*50)
        
        if not self.readme_content:
            logger.warning("⚠️ 无README文件，将基于文件结构推断")
            return self._infer_from_structure()
        
        # 调用LLM分析README
        system_prompt = """你是一个专业的代码分析专家。
你需要根据给定的README文件和项目结构，分析该项目的：
1. 项目的核心功能是什么？
2. 项目的主要模块有哪些？
3. 项目分为几层或几个主要功能分区？请明确指出。
4. 各个功能分区的职责是什么？
5. README中是否已经描述了功能分区？

请用结构化的方式回答，便于后续解析。"""
        
        user_prompt = f"""请分析以下项目的README和结构：

# 项目结构
{json.dumps(self._get_project_structure(), indent=2, ensure_ascii=False)[:2000]}

# README内容
{self.readme_content[:3000]}

请给出项目的概览分析。"""
        
        try:
            logger.info("🤖 调用DeepSeek API分析项目...")

            analysis = self.llm_helper.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                cache_key=f"overview::{self.project_path}",
                use_cache=True,
            )
            
            logger.info("✓ 项目分析完成")
            logger.info(f"\n分析结果：\n{analysis}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"✗ LLM调用失败: {e}")
            raise
    
    def _infer_from_structure(self) -> str:
        """基于文件结构推断项目功能"""
        logger.info("📁 基于文件结构推断项目功能...")
        
        structure = self._get_project_structure()
        structure_text = json.dumps(structure, indent=2, ensure_ascii=False)
        
        system_prompt = """你是一个代码分析专家。
根据项目的文件夹结构，推断该项目的主要功能和模块划分。
请指出可能存在的功能分层。"""
        
        user_prompt = f"""项目结构如下：

{structure_text}

请根据这个结构推断项目的功能分区和模块划分。"""
        
        try:
            return self.llm_helper.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                cache_key=f"infer_from_structure::{self.project_path}",
                use_cache=True,
            )
        except Exception as e:
            logger.error(f"✗ 推断失败: {e}")
            return "无法推断项目结构"
    
    def identify_important_codes(self, code_symbols: Dict[str, Any]) -> List[ImportantCode]:
        """
        第二步：识别重要代码
        基于代码符号表（AST）和README的理解，找出主干代码
        
        Args:
            code_symbols: 代码符号表，包含所有类、方法、函数等
                        格式: {file -> {entities}}
        
        Returns:
            重要代码列表
        """
        logger.info("\n" + "="*50)
        logger.info("🎯 阶段2：识别重要代码")
        logger.info("="*50)
        
        # 构建符号摘要（不发送完整代码，只发送签名和调用关系）
        symbol_summary = self._build_symbol_summary(code_symbols)
        
        system_prompt = """你是代码分析专家，你的任务是从代码符号表中识别"主干代码"。
主干代码是指：
1. 被频繁调用的代码（高重要性）
2. 作为入口点的代码（如main、__init__等）
3. 核心业务逻辑代码
4. 关键接口或抽象类

请标注重要代码为：
- 重要-1: 核心入口（最重要）
- 重要-2: 核心业务逻辑
- 重要-3: 关键工具类
- 重要-4: 支持性代码（可选标注）"""
        
        user_prompt = f"""根据以下代码符号表，识别重要的主干代码。

# 项目概览理解
{self.readme_content[:1000] if self.readme_content else "未提供"}

# 代码符号表（仅包含类名、方法名、调用关系，不含完整代码）
{json.dumps(symbol_summary, indent=2, ensure_ascii=False)[:4000]}

请识别重要的主干代码，并为每个标记重要等级。
返回JSON格式的结果，包含file, entity_type, entity_name, importance_mark, reason等字段。"""
        
        try:
            logger.info("🤖 调用DeepSeek API识别重要代码...")
            result_text = self.llm_helper.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                cache_key=f"identify_important_codes::{self.project_path}",
                use_cache=False,
            )
            logger.info("✓ 重要代码识别完成")
            
            # 尝试解析JSON结果
            important_codes = self._parse_important_codes(result_text)
            self.important_codes = important_codes
            
            logger.info(f"✓ 识别出 {len(important_codes)} 个重要代码")
            for code in important_codes[:5]:  # 显示前5个
                logger.info(f"  - {code.importance_mark}: {code.entity_name} ({code.file_path})")
            
            return important_codes
            
        except Exception as e:
            logger.error(f"✗ 重要代码识别失败: {e}")
            return []
    
    def _build_symbol_summary(self, code_symbols: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建代码符号摘要（不包含完整源代码，只包含签名和调用关系）
        这样能大幅减少token消耗
        """
        summary = {}
        
        for file_path, entities in code_symbols.items():
            if not entities:
                continue
            
            file_summary = {
                "classes": [],
                "functions": [],
                "total_methods": 0
            }
            
            # 提取类信息（仅签名）
            for entity in entities:
                if entity.get("type") == "class":
                    class_info = {
                        "name": entity.get("name"),
                        "methods": [m.get("name") for m in entity.get("methods", [])],
                        "call_count": entity.get("call_count", 0)
                    }
                    file_summary["classes"].append(class_info)
                    file_summary["total_methods"] += len(entity.get("methods", []))
                
                elif entity.get("type") == "function":
                    func_info = {
                        "name": entity.get("name"),
                        "call_count": entity.get("call_count", 0)
                    }
                    file_summary["functions"].append(func_info)
            
            summary[file_path] = file_summary
        
        return summary
    
    def _parse_important_codes(self, response_text: str) -> List[ImportantCode]:
        """解析LLM返回的重要代码标注"""
        important_codes = []
        
        # 尝试提取JSON格式的结果
        try:
            # 查找JSON块
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                for item in data:
                    try:
                        code = ImportantCode(
                            file_path=item.get("file_path", item.get("file", "")),
                            entity_type=item.get("entity_type", ""),
                            entity_name=item.get("entity_name", ""),
                            full_signature=item.get("full_signature", item.get("entity_name", "")),
                            importance_mark=item.get("importance_mark", ""),
                            reason=item.get("reason", "")
                        )
                        important_codes.append(code)
                    except Exception as e:
                        logger.warning(f"解析重要代码项失败: {e}")
                
                return important_codes
        except Exception as e:
            logger.warning(f"JSON解析失败: {e}")
        
        # 如果JSON解析失败，尝试正则解析文本
        logger.warning("⚠️ 无法解析JSON，尝试基于文本启发式解析...")
        return important_codes
    
    def identify_function_partitions(self, project_info: Dict[str, Any], 
                                     graph_data: Dict[str, Any] = None,
                                     comments_summary: Dict[str, Any] = None) -> List[FunctionPartition]:
        """
        识别功能分区 - 使用 LLM + 图知识库 + README + 代码注释
        
        Args:
            project_info: 项目基本信息（包含 README）
            graph_data: 图数据（用于生成图知识库摘要）
            comments_summary: 代码注释摘要
        
        Returns:
            功能分区列表
        """
        logger.info("\n" + "="*50)
        logger.info("📦 识别功能分区（使用 LLM + 图知识库）")
        logger.info("="*50)
        
        partitions = []
        
        try:
            # 步骤1：生成图知识库摘要（如果提供了图数据）
            graph_summary_text = ""
            if graph_data:
                try:
                    from llm.graph_knowledge_base import GraphKnowledgeBase
                    graph_kb = GraphKnowledgeBase(graph_data)
                    graph_summary = graph_kb.generate_summary()
                    graph_summary_text = graph_kb.to_text_summary(max_length=1000)
                    logger.info("✓ 图知识库摘要生成完成")
                except Exception as e:
                    logger.warning(f"⚠️ 图知识库摘要生成失败: {e}")
            
            # 步骤2：提取代码注释摘要
            comments_text = ""
            if comments_summary:
                # 只提取关键代码的注释（前20个最重要的）
                key_comments = []
                for entity_id, comment_info in list(comments_summary.items())[:20]:
                    if comment_info.get('comments'):
                        key_comments.append(f"{entity_id}: {comment_info['comments'][0][:100]}")
                comments_text = "\n".join(key_comments[:10])  # 只取前10个
                logger.info(f"✓ 代码注释摘要提取完成（{len(key_comments)} 个关键注释）")
            
            # 步骤3：调用 LLM 识别功能分区
            try:
                logger.info("🤖 调用 LLM API 识别功能分区...")

                system_prompt = """你是一个专业的代码架构分析专家。

你的任务是根据项目的 README、代码注释和图知识库摘要，识别该项目的主要功能分区。

功能分区是指项目的主要功能模块，比如：
- 代码解析层：负责代码的解析和符号提取
- 分析层：负责代码的分析和关系提取
- 可视化层：负责数据的可视化展示
- 业务逻辑层：负责核心业务逻辑
- 工具辅助层：提供工具函数和辅助功能

请识别 2-4 个主要功能分区，每个分区必须包含：
- name: 功能名称（简洁，2-6个字）
- description: 功能描述（详细说明该功能的职责）
- folders: 对应的文件夹列表（使用绝对路径）
- keywords: 关键词列表（用于匹配代码）

返回 JSON 格式的数组。"""

                readme_content = self.readme_content[:2000] if self.readme_content else "无 README 文件"
                structure_text = json.dumps(self._get_project_structure(), indent=2, ensure_ascii=False)[:1000]

                user_prompt = f"""请分析以下项目信息，识别主要功能分区：

# 1. README 内容
{readme_content}

# 2. 项目结构
{structure_text}

# 3. 图知识库摘要
{graph_summary_text if graph_summary_text else "无图数据"}

# 4. 关键代码注释摘要
{comments_text if comments_text else "无注释数据"}

请根据以上信息，识别该项目的主要功能分区。
特别注意：README 中可能已经明确说明了功能分层，请优先参考 README 的描述。
返回 JSON 数组格式，例如：
[
  {{
    "name": "代码解析层",
    "description": "负责 Python 代码的 AST 解析和符号提取",
    "folders": ["D:/project/parsers", "D:/project/analysis"],
    "keywords": ["parser", "ast", "parse", "解析"]
  }},
  ...
]"""

                response_content = self.llm_helper.call(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    cache_key=f"identify_function_partitions::{self.project_path}",
                    use_cache=False,
                )

                logger.info(f"✓ LLM 响应接收完成（{len(response_content)} 字符）")

                # 解析 LLM 返回的功能分区
                llm_partitions = self._parse_function_partitions(response_content)
                if llm_partitions:
                    partitions = llm_partitions
                    logger.info(f"✅ LLM 识别出 {len(partitions)} 个功能分区")
                    for p in partitions:
                        logger.info(f"   - {p.name}: {p.description}")
                        logger.info(f"     文件夹: {p.folders}")
                else:
                    logger.warning("⚠️ LLM 返回了空的功能分区列表，使用启发式规则")

            except Exception as e:
                logger.error(f"❌ LLM 调用失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 步骤4：如果 LLM 失败或未使用，使用启发式规则
            if not partitions:
                logger.info("🔄 使用启发式规则识别功能分区...")
                partitions = self._identify_partitions_heuristic()
            
            # 步骤5：确保每个分区都有 folders（绝对路径）
            for partition in partitions:
                if not partition.folders:
                    # 根据关键词和项目结构匹配文件夹
                    matched_folders = self._match_folders_by_keywords(partition.keywords)
                    partition.folders = matched_folders
                    logger.info(f"   为 {partition.name} 匹配到文件夹: {matched_folders}")
            
            self.function_partitions = partitions
            
            logger.info(f"✅ 最终识别出 {len(partitions)} 个功能分区")
            return partitions
            
        except Exception as e:
            logger.error(f"✗ 功能分区识别失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _identify_partitions_heuristic(self) -> List[FunctionPartition]:
        """使用启发式规则识别功能分区（LLM 失败时的备用方案）"""
        partitions = []
        
        # 从 README 中查找功能分区关键词
        if self.readme_content:
            readme_lower = self.readme_content.lower()
            
            # 常见的功能分区关键词
            layer_patterns = {
                "解析": ("代码解析层", "负责代码的解析和符号提取", ["parser", "parse", "ast"]),
                "分析": ("分析层", "负责代码的分析和关系提取", ["analyzer", "analysis", "analyze"]),
                "可视化": ("可视化层", "负责数据的可视化展示", ["visual", "visualization", "view"]),
                "业务": ("业务逻辑层", "负责核心业务逻辑", ["business", "service", "core"]),
                "工具": ("工具辅助层", "提供工具函数和辅助功能", ["util", "helper", "tool"]),
            }
            
            found_keywords = []
            for keyword, (name, desc, keywords) in layer_patterns.items():
                if keyword in readme_lower:
                    found_keywords.append((name, desc, keywords))
            
            for name, desc, keywords in found_keywords:
                partition = FunctionPartition(
                    name=name,
                    description=desc,
                    keywords=keywords,
                    folders=[]
                )
                partitions.append(partition)
        
        # 如果 README 中没有找到，从项目结构推断
        if not partitions:
            structure = self._get_project_structure()
            for folder_name in sorted(structure.keys()):
                if not folder_name.startswith('.') and folder_name != '.':
                    partition = FunctionPartition(
                        name=folder_name,
                        description=f"模块: {folder_name}",
                        keywords=[folder_name],
                        folders=[]
                    )
                    partitions.append(partition)
        
        return partitions
    
    def _match_folders_by_keywords(self, keywords: List[str]) -> List[str]:
        """根据关键词匹配文件夹（返回绝对路径）"""
        matched_folders = []
        if not self.project_path:
            return matched_folders
        
        structure = self._get_project_structure()
        
        for folder_path, files in structure.items():
            folder_name_lower = folder_path.lower()
            # 检查关键词是否匹配文件夹名
            for keyword in keywords:
                if keyword.lower() in folder_name_lower or folder_name_lower in keyword.lower():
                    # 转换为绝对路径
                    if os.path.isabs(folder_path):
                        abs_path = folder_path
                    else:
                        abs_path = os.path.join(self.project_path, folder_path)
                    abs_path = os.path.normpath(abs_path)
                    if os.path.isdir(abs_path) and abs_path not in matched_folders:
                        matched_folders.append(abs_path)
                    break
        
        return matched_folders
    
    def _parse_function_partitions(self, response_text: str) -> List[FunctionPartition]:
        """解析 LLM 返回的功能分区 JSON"""
        partitions = []
        
        try:
            # 尝试提取 JSON 块
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                for item in data:
                    try:
                        partition = FunctionPartition(
                            name=item.get("name", ""),
                            description=item.get("description", ""),
                            folders=item.get("folders", []),  # 可能是绝对路径或相对路径
                            keywords=item.get("keywords", [])
                        )
                        partitions.append(partition)
                    except Exception as e:
                        logger.warning(f"解析功能分区项失败: {e}")
                        continue
                
                return partitions
        except Exception as e:
            logger.warning(f"JSON 解析失败: {e}")
            logger.debug(f"响应文本: {response_text[:500]}")
        
        return partitions
    
    def _parse_function_partitions(self, response_text: str) -> List[FunctionPartition]:
        """解析 LLM 返回的功能分区 JSON"""
        partitions = []
        
        try:
            # 尝试提取 JSON 块
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                for item in data:
                    try:
                        partition = FunctionPartition(
                            name=item.get("name", ""),
                            description=item.get("description", ""),
                            folders=item.get("folders", []),  # 可能是绝对路径或相对路径
                            keywords=item.get("keywords", [])
                        )
                        partitions.append(partition)
                    except Exception as e:
                        logger.warning(f"解析功能分区项失败: {e}")
                        continue
                
                return partitions
        except Exception as e:
            logger.warning(f"JSON 解析失败: {e}")
            logger.debug(f"响应文本: {response_text[:500]}")
        
        return partitions
    
    def save_analysis_result(self, output_path: str) -> None:
        """保存分析结果为JSON"""
        result = {
            "project": {
                "path": self.project_path,
                "name": os.path.basename(self.project_path) if self.project_path else "unknown"
            },
            "function_partitions": [asdict(p) for p in self.function_partitions],
            "important_codes": [asdict(c) for c in self.important_codes],
            "total_partitions": len(self.function_partitions),
            "total_important_codes": len(self.important_codes)
        }
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ 分析结果已保存到: {output_path}")
    
    def enhance_partition_with_llm(self, 
                                   partition: Dict[str, Any],
                                   analyzer_report,
                                   project_path: str) -> Dict[str, Any]:
        """
        使用LLM为社区检测的分区生成有意义的名字、描述和关键文件夹
        
        Args:
            partition: 分区字典，包含partition_id、methods等
            analyzer_report: 代码分析报告
            project_path: 项目路径
            
        Returns:
            增强后的分区字典，包含name、description、folders、stats等
        """
        partition_id = partition.get("partition_id", "unknown")
        methods = partition.get("methods", [])
        
        logger.info(f"[CodeUnderstandingAgent] 使用LLM增强分区 {partition_id}，方法数: {len(methods)}")
        
        # 提取分区的关键信息
        class_names = set()
        method_names = []
        file_paths = set()
        folder_paths = set()
        
        for method_sig in methods[:50]:  # 限制前50个方法，避免token过多
            if "." in method_sig:
                parts = method_sig.rsplit(".", 1)
                if len(parts) == 2:
                    class_name = parts[0]
                    method_name = parts[1]
                    class_names.add(class_name)
                    method_names.append(method_name)
                    
                    # 从report获取文件路径
                    if analyzer_report and class_name in analyzer_report.classes:
                        class_info = analyzer_report.classes[class_name]
                        if method_name in class_info.methods:
                            method_info = class_info.methods[method_name]
                            if method_info.source_location:
                                file_path = method_info.source_location.file_path
                                file_paths.add(file_path)
                                # 提取文件夹路径
                                folder_path = os.path.dirname(file_path)
                                if os.path.isabs(folder_path):
                                    folder_paths.add(folder_path)
                                else:
                                    abs_folder = os.path.normpath(os.path.join(project_path, folder_path))
                                    folder_paths.add(abs_folder)
        
        # 构建方法摘要（只包含方法名，不包含完整代码）
        method_summary = {
            "class_names": list(class_names)[:20],  # 前20个类
            "method_names": method_names[:30],  # 前30个方法
            "file_count": len(file_paths),
            "folder_paths": list(folder_paths)[:10]  # 前10个文件夹
        }
        
        # 调用LLM生成分区信息
        try:
            system_prompt = """你是一个专业的代码架构分析专家。

你的任务是根据代码分区的方法列表、类名和文件路径，为这个分区生成：
1. 一个有意义的名称（2-6个字，描述该分区的核心功能）
2. 详细的功能描述（说明该分区的作用和职责）
3. 关键文件夹列表（该分区主要涉及的文件夹，使用绝对路径）

请基于方法名、类名和文件路径推断该分区的功能。"""
            
            user_prompt = f"""请分析以下代码分区信息，生成有意义的分区名称、描述和关键文件夹：

# 分区方法摘要
- 类名: {', '.join(method_summary['class_names'])}
- 方法名示例: {', '.join(method_summary['method_names'][:20])}
- 文件数: {method_summary['file_count']}
- 文件夹路径: {', '.join(method_summary['folder_paths'][:5])}

# 项目路径
{project_path}

请返回JSON格式：
{{
    "name": "分区名称（2-6个字）",
    "description": "详细的功能描述，说明该分区的作用、职责和重要性",
    "folders": ["绝对路径1", "绝对路径2"],
    "keywords": ["关键词1", "关键词2"]
}}"""
            
            response_text = self.llm_helper.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                cache_key=f"enhance_partition::{project_path}::{partition_id}",
                use_cache=False,
            )
            
            # 解析LLM返回的JSON
            enhanced_info = self._parse_partition_enhancement(response_text)
            
            # 如果LLM返回了信息，使用它；否则使用启发式规则
            if enhanced_info:
                partition['name'] = enhanced_info.get('name', partition_id)
                partition['description'] = enhanced_info.get('description', f"功能分区，包含 {len(methods)} 个方法")
                partition['folders'] = enhanced_info.get('folders', list(folder_paths)[:5])
                partition['keywords'] = enhanced_info.get('keywords', list(class_names)[:5])
            else:
                # 启发式规则：从类名和方法名推断
                partition['name'] = self._infer_partition_name(class_names, method_names)
                partition['description'] = f"功能分区，包含 {len(methods)} 个方法，主要类: {', '.join(list(class_names)[:3])}"
                partition['folders'] = list(folder_paths)[:5]
                partition['keywords'] = list(class_names)[:5]
            
            logger.info(f"✓ 分区 {partition_id} 增强完成: {partition['name']}")
            
        except Exception as e:
            logger.warning(f"⚠️ LLM增强分区失败: {e}，使用启发式规则")
            # 使用启发式规则
            partition['name'] = self._infer_partition_name(class_names, method_names)
            partition['description'] = f"功能分区，包含 {len(methods)} 个方法"
            partition['folders'] = list(folder_paths)[:5]
            partition['keywords'] = list(class_names)[:5]
        
        return partition
    
    def generate_path_name_and_description(self, 
                                           path: List[str],
                                           analyzer_report,
                                           project_path: str) -> Dict[str, str]:
        """
        为功能路径生成名称和描述
        
        Args:
            path: 路径节点列表（方法签名）
            analyzer_report: 代码分析报告
            project_path: 项目路径
            
        Returns:
            {'name': '路径名称', 'description': '路径描述'}
        """
        try:
            # 收集路径上的方法信息
            method_info_list = []
            for method_sig in path:
                method_info = self._get_method_info(method_sig, analyzer_report)
                if method_info:
                    method_info_list.append(method_info)
            
            # 构建提示词
            system_prompt = """你是一个专业的代码架构分析专家。

你的任务是根据功能路径上的方法调用序列，为这条路径生成：
1. 一个有意义的名称（3-8个字，描述该路径的核心功能）
2. 简洁的功能描述（1-2句话，说明该路径的作用和功能）

请基于方法名、类名和调用关系推断该路径的功能。"""
            
            path_summary = "\n".join([
                f"{i+1}. {info.get('class_name', '')}.{info.get('method_name', method_sig)}" 
                for i, (method_sig, info) in enumerate(zip(path, method_info_list))
            ])
            
            user_prompt = f"""请分析以下功能路径，生成有意义的路径名称和描述：

# 路径方法序列
{path_summary}

# 项目路径
{project_path}

请返回JSON格式：
{{
    "name": "路径名称（3-8个字，描述核心功能）",
    "description": "简洁的功能描述（1-2句话，说明该路径的作用）"
}}"""
            
            response_text = self.llm_helper.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                cache_key=f"path_name_desc::{project_path}::{hash(tuple(path))}",
                use_cache=False,
            )
            
            # 解析LLM返回的JSON
            path_info = self._parse_path_enhancement(response_text)
            
            if path_info:
                return {
                    'name': path_info.get('name', f'路径 {len(path)} 个方法'),
                    'description': path_info.get('description', f'包含 {len(path)} 个方法的调用链')
                }
            else:
                # 启发式规则
                return {
                    'name': self._infer_path_name(path, method_info_list),
                    'description': f'包含 {len(path)} 个方法的调用链，实现特定功能'
                }
                
        except Exception as e:
            logger.warning(f"⚠️ LLM生成路径名称和描述失败: {e}，使用启发式规则")
            return {
                'name': f'路径 {len(path)} 个方法',
                'description': f'包含 {len(path)} 个方法的调用链'
            }
    
    def generate_path_input_output_graph(self,
                                         path: List[str],
                                         analyzer_report,
                                         inputs: List[Dict] = None,
                                         outputs: List[Dict] = None) -> Dict[str, Any]:
        """
        为功能路径生成输入输出图
        
        Args:
            path: 路径节点列表（方法签名）
            analyzer_report: 代码分析报告
            inputs: 输入参数汇总
            outputs: 返回值汇总
            
        Returns:
            输入输出图数据（包含节点和边的图结构）
        """
        logger.info(f"[CodeUnderstandingAgent] generate_path_input_output_graph 开始")
        logger.info(f"[CodeUnderstandingAgent]   - 路径长度: {len(path)}")
        logger.info(f"[CodeUnderstandingAgent]   - 路径: {path[:3]}..." if len(path) > 3 else f"[CodeUnderstandingAgent]   - 路径: {path}")
        logger.info(f"[CodeUnderstandingAgent]   - inputs: {len(inputs) if inputs else 0} 个")
        logger.info(f"[CodeUnderstandingAgent]   - outputs: {len(outputs) if outputs else 0} 个")
        logger.info(f"[CodeUnderstandingAgent]   - llm_helper: {type(self.llm_helper).__name__}")
        logger.info(f"[CodeUnderstandingAgent]   - _use_direct_api: {getattr(self, '_use_direct_api', False)}")
        
        try:
            # 收集路径上每个方法的输入输出信息
            method_io_list = []
            logger.info(f"[CodeUnderstandingAgent]   开始收集方法IO信息...")
            for method_sig in path:
                method_info = self._get_method_info(method_sig, analyzer_report)
                method_inputs = []
                method_outputs = []
                
                # 从inputs和outputs中查找该方法的输入输出
                if inputs:
                    for inp in inputs:
                        if inp.get('method_signature') == method_sig:
                            method_inputs.append({
                                'name': inp.get('parameter_name', 'unknown'),
                                'type': inp.get('parameter_type', 'unknown')
                            })
                
                if outputs:
                    for out in outputs:
                        if out.get('method_signature') == method_sig:
                            method_outputs.append({
                                'type': out.get('return_type', 'unknown')
                            })
                
                # 如果找不到，尝试从方法信息中提取
                if not method_inputs and method_info:
                    if method_info.get('parameters'):
                        for param in method_info['parameters']:
                            method_inputs.append({
                                'name': param.get('name', 'unknown'),
                                'type': param.get('type', 'unknown')
                            })
                
                if not method_outputs and method_info:
                    if method_info.get('return_type'):
                        method_outputs.append({
                            'type': method_info['return_type']
                        })
                
                method_io_list.append({
                    'method_sig': method_sig,
                    'method_name': method_info.get('method_name', method_sig.split('.')[-1]) if method_info else method_sig.split('.')[-1],
                    'inputs': method_inputs,
                    'outputs': method_outputs
                })
            
            logger.info(f"[CodeUnderstandingAgent]   收集完成，method_io_list长度: {len(method_io_list)}")
            if method_io_list:
                logger.info(f"[CodeUnderstandingAgent]   第一个方法: {method_io_list[0].get('method_name')}, inputs: {len(method_io_list[0].get('inputs', []))}, outputs: {len(method_io_list[0].get('outputs', []))}")
            
            # 使用LLM分析输入输出的语义和类型
            logger.info(f"[CodeUnderstandingAgent]   开始构建LLM提示词...")
            system_prompt = """你是一个专业的代码数据流分析专家。

你的任务是根据功能路径上的方法调用序列和输入输出信息，生成输入输出图。

输入输出图应该显示：
1. 路径的初始输入（文件、字典、字符串等）及其类型
2. 经过每个方法操作后的中间输出（文件、字典、字符串等）及其类型
3. 最终输出及其类型

请分析每个方法的输入输出，推断数据在路径上的流动过程。"""
            
            io_summary_lines = []
            for i, io in enumerate(method_io_list):
                input_strs = [f"{inp['name']}:{inp['type']}" for inp in io['inputs']]
                output_strs = [out['type'] for out in io['outputs']]
                io_summary_lines.append(
                    f"{i+1}. {io['method_name']}: "
                    f"输入=[{', '.join(input_strs)}], "
                    f"输出=[{', '.join(output_strs)}]"
                )
            io_summary = "\n".join(io_summary_lines)
            logger.info(f"[CodeUnderstandingAgent]   io_summary长度: {len(io_summary)} 字符")
            
            user_prompt = f"""请分析以下功能路径的输入输出，生成输入输出图：

# 路径方法序列及输入输出
{io_summary}

请返回JSON格式，描述数据在路径上的流动：
{
    "nodes": [
        {"id": "input_1", "label": "输入描述", "type": "输入类型（文件/字典/字符串等）"},
        {"id": "method_1", "label": "方法1操作", "type": "操作节点"},
        {"id": "output_1", "label": "中间输出描述", "type": "输出类型（文件/字典/字符串等）"},
        ...
        {"id": "output_final", "label": "最终输出描述", "type": "最终输出类型"}
    ],
    "edges": [
        {"source": "input_1", "target": "method_1", "label": "数据流动"},
        {"source": "method_1", "target": "output_1", "label": "处理后"},
        ...
    ]
}

**重要提示：**
1. 边的方向必须表示**数据流动方向**：`source` 是数据的产生者/上游，`target` 是数据的接收者/下游。
2. 输入节点 -> 方法节点
3. 方法节点 -> 中间数据节点 -> 方法节点
4. 方法节点 -> 输出节点
5. **绝对不要**生成反向箭头（例如不要从 output 指向 method）。"""
            
            logger.info(f"[CodeUnderstandingAgent]   开始调用LLM...")
            response_text = self.llm_helper.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                cache_key=f"io_graph::{project_path}::{hash(tuple(path))}",
                use_cache=False,
            )
            logger.info(f"[CodeUnderstandingAgent]   LLM响应长度: {len(response_text)} 字符")
            logger.info(f"[CodeUnderstandingAgent]   LLM响应前200字符: {response_text[:200]}")
            
            # 解析LLM返回的JSON
            logger.info(f"[CodeUnderstandingAgent]   开始解析JSON...")
            io_graph = self._parse_io_graph(response_text)
            logger.info(f"[CodeUnderstandingAgent]   解析结果: {type(io_graph)}")
            
            if io_graph:
                logger.info(f"[CodeUnderstandingAgent]   ✓ 解析成功，返回io_graph")
                logger.info(f"[CodeUnderstandingAgent]   - io_graph类型: {type(io_graph)}")
                if isinstance(io_graph, dict):
                    logger.info(f"[CodeUnderstandingAgent]   - io_graph keys: {list(io_graph.keys())}")
                    logger.info(f"[CodeUnderstandingAgent]   - nodes数量: {len(io_graph.get('nodes', []))}")
                    logger.info(f"[CodeUnderstandingAgent]   - edges数量: {len(io_graph.get('edges', []))}")
                return io_graph
            else:
                logger.warning(f"[CodeUnderstandingAgent]   ⚠️ 解析失败，使用启发式规则")
                # 启发式规则：基于方法输入输出构建简单图
                heuristic_result = self._build_io_graph_heuristic(method_io_list)
                logger.info(f"[CodeUnderstandingAgent]   启发式规则结果: {type(heuristic_result)}")
                if isinstance(heuristic_result, dict):
                    logger.info(f"[CodeUnderstandingAgent]   - nodes数量: {len(heuristic_result.get('nodes', []))}")
                    logger.info(f"[CodeUnderstandingAgent]   - edges数量: {len(heuristic_result.get('edges', []))}")
                return heuristic_result
                
        except Exception as e:
            logger.error(f"[CodeUnderstandingAgent]   ❌ 异常: {e}")
            import traceback
            logger.error(f"[CodeUnderstandingAgent]   异常堆栈:\n{traceback.format_exc()}")
            logger.warning(f"[CodeUnderstandingAgent]   ⚠️ 使用启发式规则作为降级方案")
            heuristic_result = self._build_io_graph_heuristic(method_io_list)
            logger.info(f"[CodeUnderstandingAgent]   启发式规则结果: {type(heuristic_result)}")
            return heuristic_result
    
    def _get_method_info(self, method_sig: str, analyzer_report) -> Optional[Dict[str, Any]]:
        """获取方法信息"""
        try:
            if '.' in method_sig:
                class_name, method_name = method_sig.rsplit('.', 1)
                if analyzer_report and class_name in analyzer_report.classes:
                    class_info = analyzer_report.classes[class_name]
                    if method_name in class_info.methods:
                        method_info = class_info.methods[method_name]
                        return {
                            'class_name': class_name,
                            'method_name': method_name,
                            'parameters': [{'name': p.name, 'type': getattr(p, 'param_type', None) or 'unknown'} 
                                         for p in (method_info.parameters or [])],
                            'return_type': getattr(method_info, 'return_type', None) or 'unknown'
                        }
            else:
                # 全局函数
                if analyzer_report:
                    for func_info in analyzer_report.functions:
                        if func_info.name == method_sig:
                            return {
                                'class_name': '',
                                'method_name': method_sig,
                                'parameters': [{'name': p.name, 'type': getattr(p, 'param_type', None) or 'unknown'} 
                                             for p in (func_info.parameters or [])],
                                'return_type': getattr(func_info, 'return_type', None) or 'unknown'
                            }
        except Exception as e:
            logger.debug(f"获取方法信息失败 {method_sig}: {e}")
        return None
    
    def _parse_path_enhancement(self, response_text: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的路径增强信息"""
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                return data
        except Exception as e:
            logger.warning(f"解析路径增强信息失败: {e}")
        return None
    
    def _parse_io_graph(self, response_text: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的输入输出图"""
        logger.info(f"[CodeUnderstandingAgent]   _parse_io_graph 开始解析")
        logger.info(f"[CodeUnderstandingAgent]     - response_text长度: {len(response_text)} 字符")
        logger.info(f"[CodeUnderstandingAgent]     - response_text前500字符: {response_text[:500]}")
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                logger.info(f"[CodeUnderstandingAgent]     ✓ 找到JSON匹配")
                json_str = json_match.group(0)
                logger.info(f"[CodeUnderstandingAgent]     - JSON字符串长度: {len(json_str)} 字符")
                logger.info(f"[CodeUnderstandingAgent]     - JSON字符串前200字符: {json_str[:200]}")
                data = json.loads(json_str)
                logger.info(f"[CodeUnderstandingAgent]     ✓ JSON解析成功")
                logger.info(f"[CodeUnderstandingAgent]     - 解析后数据类型: {type(data)}")
                if isinstance(data, dict):
                    logger.info(f"[CodeUnderstandingAgent]     - 数据keys: {list(data.keys())}")
                    logger.info(f"[CodeUnderstandingAgent]     - nodes: {len(data.get('nodes', []))} 个")
                    logger.info(f"[CodeUnderstandingAgent]     - edges: {len(data.get('edges', []))} 个")
                return data
            else:
                logger.warning(f"[CodeUnderstandingAgent]     ⚠️ 未找到JSON匹配")
        except json.JSONDecodeError as e:
            logger.error(f"[CodeUnderstandingAgent]     ❌ JSON解析失败: {e}")
            logger.error(f"[CodeUnderstandingAgent]     - 错误位置: line {e.lineno}, column {e.colno}")
        except Exception as e:
            logger.error(f"[CodeUnderstandingAgent]     ❌ 解析输入输出图失败: {e}")
            import traceback
            logger.error(f"[CodeUnderstandingAgent]     异常堆栈:\n{traceback.format_exc()}")
        logger.warning(f"[CodeUnderstandingAgent]     ⚠️ 返回None")
        return None
    
    def analyze_path_call_chain_type(self,
                                     path: List[str],
                                     call_graph: Dict[str, Set[str]],
                                     analyzer_report) -> Dict[str, Any]:
        """
        分析方法调用链的类型，识别调用关系模式
        
        Args:
            path: 路径节点列表（方法签名）
            call_graph: 调用图 {caller: {callee1, callee2, ...}}
            analyzer_report: 代码分析报告
            
        Returns:
            调用链分析结果，包含：
            - call_chain_type: 调用链类型（如"顺序调用"、"总方法调用"、"直接调用"等）
            - main_method: 总方法（如果有）
            - intermediate_methods: 中间方法列表
            - direct_calls: 直接调用关系列表
            - explanation: LLM生成的解释说明
        """
        logger.info(f"[CodeUnderstandingAgent] analyze_path_call_chain_type 开始")
        logger.info(f"[CodeUnderstandingAgent]   - 路径长度: {len(path)}")
        logger.info(f"[CodeUnderstandingAgent]   - 路径: {path}")
        
        try:
            # 收集路径上每个方法的信息
            method_info_list = []
            for method_sig in path:
                method_info = self._get_method_info(method_sig, analyzer_report)
                method_info_list.append({
                    'method_sig': method_sig,
                    'method_name': method_info.get('method_name', method_sig.split('.')[-1]) if method_info else method_sig.split('.')[-1],
                    'class_name': method_info.get('class_name', '') if method_info else '',
                    'parameters': method_info.get('parameters', []) if method_info else [],
                    'return_type': method_info.get('return_type', 'unknown') if method_info else 'unknown'
                })
            
            # 分析调用关系
            direct_calls = []
            for i in range(len(path) - 1):
                caller = path[i]
                callee = path[i + 1]
                # 检查call_graph中是否存在直接调用关系
                if caller in call_graph and callee in call_graph[caller]:
                    direct_calls.append((caller, callee))
            
            # 构建LLM提示词
            system_prompt = """你是一个专业的代码调用链分析专家。

你的任务是分析功能路径上的方法调用链类型，识别调用关系模式。

常见的调用链类型包括：
1. **直接顺序调用**：方法A直接调用方法B，方法B直接调用方法C，形成A->B->C的链式调用
2. **总方法顺序调用**：存在一个总方法（如main、execute、process等），该总方法按顺序调用A、B、C，数据流从A到B到C
3. **总方法并行调用**：总方法同时调用多个方法（如A、B、C），但这些方法之间没有直接调用关系
4. **中间方法桥接**：方法A调用中间方法M，中间方法M再调用方法B，形成A->M->B的桥接关系
5. **回调链调用**：方法A调用方法B，方法B通过回调机制调用方法C
6. **事件驱动调用**：方法A触发事件，事件处理器调用方法B，方法B再触发事件调用方法C

请根据路径上的方法调用序列和调用关系，判断调用链类型，并给出详细解释。"""
            
            method_summary_lines = []
            for i, method in enumerate(method_info_list):
                method_summary_lines.append(
                    f"{i+1}. {method['method_sig']} ({method['method_name']})"
                )
            method_summary = "\n".join(method_summary_lines)
            
            call_relation_summary = []
            if direct_calls:
                call_relation_summary.append("直接调用关系：")
                for caller, callee in direct_calls:
                    call_relation_summary.append(f"  - {caller} -> {callee}")
            else:
                call_relation_summary.append("直接调用关系：无（方法之间不是直接调用的）")
            
            # 检查是否存在总方法（调用路径上多个方法的）
            potential_main_methods = []
            for method_sig in call_graph:
                if method_sig not in path:
                    # 检查这个方法是否调用了路径上的多个方法
                    called_path_methods = [m for m in path if m in call_graph.get(method_sig, set())]
                    if len(called_path_methods) >= 2:
                        potential_main_methods.append({
                            'method_sig': method_sig,
                            'called_methods': called_path_methods
                        })
            
            main_method_info = ""
            if potential_main_methods:
                main_method_info = "\n可能存在总方法：\n"
                for main in potential_main_methods[:3]:  # 最多显示3个
                    main_method_info += f"  - {main['method_sig']} 调用了路径上的方法: {', '.join(main['called_methods'])}\n"
            
            user_prompt = f"""请分析以下功能路径的调用链类型：

# 路径方法序列
{method_summary}

# 调用关系
{chr(10).join(call_relation_summary)}
{main_method_info}

请返回JSON格式，包含：
{{
    "call_chain_type": "调用链类型（如：总方法顺序调用、直接顺序调用、中间方法桥接等）",
    "main_method": "总方法签名（如果存在，否则为null）",
    "intermediate_methods": ["中间方法签名列表（如果存在）"],
    "direct_calls": [["调用者", "被调用者"], ...],
    "explanation": "详细解释：调用链类型是什么，具体方法与其他方法之间存在怎样的调用关系，整个功能路径是如何形成的，数据流是如何一步步进行的"
}}"""
            
            logger.info(f"[CodeUnderstandingAgent]   开始调用LLM分析调用链类型...")
            response_text = self.llm_helper.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                cache_key=f"call_chain_type::{hash(tuple(path))}",
                use_cache=False,
            )
            
            # 解析LLM返回的JSON
            result = self._parse_call_chain_analysis(response_text)
            
            if result:
                # 补充直接调用关系
                result['direct_calls'] = direct_calls
                logger.info(f"[CodeUnderstandingAgent]   ✓ 调用链类型分析完成")
                logger.info(f"[CodeUnderstandingAgent]   - 类型: {result.get('call_chain_type')}")
                logger.info(f"[CodeUnderstandingAgent]   - 总方法: {result.get('main_method')}")
                return result
            else:
                logger.warning(f"[CodeUnderstandingAgent]   ⚠️ LLM分析失败，使用启发式规则")
                return self._analyze_call_chain_heuristic(path, call_graph, direct_calls, potential_main_methods)
                
        except Exception as e:
            logger.error(f"[CodeUnderstandingAgent]   ❌ 异常: {e}")
            import traceback
            logger.error(f"[CodeUnderstandingAgent]   异常堆栈:\n{traceback.format_exc()}")
            logger.warning(f"[CodeUnderstandingAgent]   ⚠️ 使用启发式规则作为降级方案")
            return self._analyze_call_chain_heuristic(path, call_graph, direct_calls, [])
    
    def _parse_call_chain_analysis(self, response_text: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的调用链分析结果"""
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                return data
        except Exception as e:
            logger.warning(f"解析调用链分析结果失败: {e}")
        return None
    
    def _analyze_call_chain_heuristic(self,
                                      path: List[str],
                                      call_graph: Dict[str, Set[str]],
                                      direct_calls: List[tuple],
                                      potential_main_methods: List[Dict]) -> Dict[str, Any]:
        """使用启发式规则分析调用链类型"""
        # 如果路径上的方法之间有直接调用关系，判断为直接顺序调用
        if len(direct_calls) == len(path) - 1:
            return {
                'call_chain_type': '直接顺序调用',
                'main_method': None,
                'intermediate_methods': [],
                'direct_calls': direct_calls,
                'explanation': f'路径上的方法形成直接顺序调用链：{" -> ".join(path)}。每个方法直接调用下一个方法。'
            }
        
        # 如果存在总方法，判断为总方法顺序调用
        if potential_main_methods:
            main_method = potential_main_methods[0]['method_sig']
            return {
                'call_chain_type': '总方法顺序调用',
                'main_method': main_method,
                'intermediate_methods': [],
                'direct_calls': direct_calls,
                'explanation': f'存在总方法 {main_method}，该总方法按顺序调用路径上的方法：{" -> ".join(path)}。数据流从第一个方法流向最后一个方法。'
            }
        
        # 其他情况，判断为中间方法桥接
        return {
            'call_chain_type': '中间方法桥接',
            'main_method': None,
            'intermediate_methods': [],
            'direct_calls': direct_calls,
            'explanation': f'路径上的方法通过中间方法建立调用关系：{" -> ".join(path)}。方法之间不是直接调用的，需要通过其他方法桥接。'
        }
    
    def _infer_path_name(self, path: List[str], method_info_list: List[Dict]) -> str:
        """从路径推断名称（启发式规则）"""
        if not method_info_list:
            return f'路径 {len(path)} 个方法'
        
        # 提取方法名的关键词
        method_names = [info.get('method_name', '') for info in method_info_list if info]
        if method_names:
            first_method = method_names[0]
            last_method = method_names[-1]
            # 从方法名提取关键词
            keywords = []
            for name in [first_method, last_method]:
                if '_' in name:
                    keywords.extend(name.split('_')[:2])
                else:
                    keywords.append(name[:4])
            return ''.join(keywords[:2]) if keywords else f'路径 {len(path)} 个方法'
        return f'路径 {len(path)} 个方法'
    
    def _build_io_graph_heuristic(self, method_io_list: List[Dict]) -> Dict[str, Any]:
        """构建输入输出图（启发式规则）"""
        nodes = []
        edges = []
        
        # 第一个方法的输入作为初始输入
        if method_io_list:
            first_method = method_io_list[0]
            if first_method['inputs']:
                input_node = {
                    'id': 'input_0',
                    'label': f"输入: {first_method['inputs'][0].get('name', 'data')}",
                    'type': first_method['inputs'][0].get('type', 'unknown')
                }
                nodes.append(input_node)
                
                # 第一个方法节点
                method_node = {
                    'id': 'method_0',
                    'label': first_method['method_name'],
                    'type': '操作节点'
                }
                nodes.append(method_node)
                edges.append({'source': 'input_0', 'target': 'method_0', 'label': '输入'})
        
        # 中间节点和边
        for i, method_io in enumerate(method_io_list):
            if i > 0:
                # 方法节点
                method_node = {
                    'id': f'method_{i}',
                    'label': method_io['method_name'],
                    'type': '操作节点'
                }
                nodes.append(method_node)
                
                # 从前一个方法的输出到当前方法的输入
                prev_output = method_io_list[i-1]['outputs']
                if prev_output:
                    intermediate_node = {
                        'id': f'intermediate_{i-1}',
                        'label': f"中间数据: {prev_output[0].get('type', 'data')}",
                        'type': prev_output[0].get('type', 'unknown')
                    }
                    nodes.append(intermediate_node)
                    edges.append({'source': f'method_{i-1}', 'target': f'intermediate_{i-1}', 'label': '输出'})
                    edges.append({'source': f'intermediate_{i-1}', 'target': f'method_{i}', 'label': '输入'})
        
        # 最终输出
        if method_io_list:
            last_method = method_io_list[-1]
            if last_method['outputs']:
                output_node = {
                    'id': 'output_final',
                    'label': f"最终输出: {last_method['outputs'][0].get('type', 'result')}",
                    'type': last_method['outputs'][0].get('type', 'unknown')
                }
                nodes.append(output_node)
                edges.append({'source': f'method_{len(method_io_list)-1}', 'target': 'output_final', 'label': '输出'})
        
        return {
            'nodes': nodes,
            'edges': edges
        }
    
    def _parse_partition_enhancement(self, response_text: str) -> Optional[Dict[str, Any]]:
        """解析LLM返回的分区增强信息"""
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                return data
        except Exception as e:
            logger.warning(f"解析分区增强信息失败: {e}")
        return None
    
    def _infer_partition_name(self, class_names: set, method_names: list) -> str:
        """从类名和方法名推断分区名称（启发式规则）"""
        # 分析命名模式
        common_prefixes = {}
        for method_name in method_names[:20]:
            if '_' in method_name:
                prefix = method_name.split('_')[0]
                common_prefixes[prefix] = common_prefixes.get(prefix, 0) + 1
        
        # 常见功能关键词映射
        keyword_map = {
            'parse': '代码解析',
            'analyze': '代码分析',
            'visual': '可视化',
            'graph': '图分析',
            'flow': '流程控制',
            'data': '数据处理',
            'call': '调用管理',
            'entry': '入口管理',
            'community': '社区检测',
            'partition': '分区管理'
        }
        
        # 查找匹配的关键词
        for keyword, name in keyword_map.items():
            if any(keyword in str(class_name).lower() or keyword in str(method_name).lower() 
                   for class_name in class_names for method_name in method_names[:10]):
                return name
        
        # 如果没找到，使用最常见的类名
        if class_names:
            return list(class_names)[0] + "模块"
        
        return "功能模块"
    
    def _call_api_directly(self, system_prompt: str, user_prompt: str) -> str:
        """直接调用 DeepSeek API（不使用 LangChain）"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 8000
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"直接 API 调用失败: {e}")
            raise

    def explain_path_cfg_dfg(
        self,
        path: List[str],
        cfg_dot: str,
        dfg_dot: str,
        analyzer_report=None,
        inputs: List[Dict] = None,
        outputs: List[Dict] = None,
    ) -> Dict[str, str]:
        """
        使用LLM解释一条功能路径的 CFG/DFG，返回可直接前端展示的 Markdown 文本。
        目标：让不熟悉 CFG/DFG 的用户能快速读懂“在这条路径上如何执行/数据如何流动”。 
        """
        system_prompt = """你是资深代码分析专家，擅长用通俗但准确的语言解释 CFG/DFG。
请输出 **Markdown**，内容需要可直接显示在前端面板中。要求：
1) 先用 3-6 行概括这条路径“做了什么”（按执行顺序）
2) 用小标题分别解释 CFG 与 DFG 在这条路径上的含义
3) 明确指出“方法之间的联系”是什么（控制流：调用顺序/返回；数据流：参数/返回值/关键变量）
4) 给出 3-8 条“阅读指南”（例如先看哪些节点/边的颜色/标签）
5) 如果图太大，看不清，给出缩放/定位建议（例如从入口/调用边开始）
不要输出与问题无关的内容。"""

        raw_io_items = os.getenv('FH_CFG_DFG_LLM_IO_MAX_ITEMS', '80')
        raw_io_lines = os.getenv('FH_CFG_DFG_LLM_IO_MAX_LINES', '120')
        raw_dot_max_chars = os.getenv('FH_CFG_DFG_LLM_DOT_MAX_CHARS', '4000')
        try:
            io_max_items = max(10, min(int(raw_io_items), 400))
        except (TypeError, ValueError):
            io_max_items = 80
        try:
            io_max_lines = max(20, min(int(raw_io_lines), 500))
        except (TypeError, ValueError):
            io_max_lines = 120
        try:
            dot_max_chars = max(1200, min(int(raw_dot_max_chars), 20000))
        except (TypeError, ValueError):
            dot_max_chars = 4000

        # 收集IO摘要（可选）
        io_lines: List[str] = []
        if inputs:
            for inp in inputs[:io_max_items]:
                ms = inp.get("method_signature", "")
                if ms in path:
                    io_lines.append(f"- IN  {ms}: {inp.get('parameter_name','')} : {inp.get('parameter_type','')}")
        if outputs:
            for out in outputs[:io_max_items]:
                ms = out.get("method_signature", "")
                if ms in path:
                    io_lines.append(f"- OUT {ms}: return {out.get('return_type','')}")
        io_summary = "\n".join(io_lines[:io_max_lines])

        # 控制 token：DOT 很长时截断
        def _truncate(s: str, n: int) -> str:
            if not s:
                return ""
            return s if len(s) <= n else (s[:n] + "\n... (truncated) ...\n" + s[-min(2000, n//5):])

        user_prompt = f"""请解释下面这条功能路径的 CFG/DFG（图是对路径上多个方法的组合，并包含方法间的调用/参数流动关系）。 

## 方法路径（按执行顺序）
{ " -> ".join([p.split('.')[-1] if '.' in p else p for p in path]) }

## 已提取的输入输出摘要（可能不完整）
{io_summary if io_summary else "(none)"}

## CFG DOT
{_truncate(cfg_dot, dot_max_chars)}

## DFG DOT
{_truncate(dfg_dot, dot_max_chars)}
"""

        try:
            text = self.llm_helper.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                cache_key=f"explain_cfg_dfg::{hash(tuple(path))}",
                use_cache=False,
            )
        except Exception as e:
            logger.error(f"[CodeUnderstandingAgent] explain_path_cfg_dfg 失败: {e}")
            # 失败时返回可展示的降级文本
            text = f"### CFG/DFG 解释生成失败\n\n错误：{e}\n\n你仍然可以先从“调用”边（红色/粗体）开始阅读，再看每个方法内部的 entry/exit 节点。"

        return {"markdown": text}


def main():
    """主函数：演示Agent的使用"""
    import sys
    
    # API配置（从环境变量读取）
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    api_key = os.getenv('MINIMAX_API_KEY') or os.getenv('OPENAI_API_KEY') or os.getenv('DEEPSEEK_API_KEY')
    base_url = os.getenv('MINIMAX_BASE_URL') or os.getenv('OPENAI_BASE_URL') or os.getenv('DEEPSEEK_BASE_URL', 'https://api.minimax.io/v1')
    
    if not api_key:
        print("❌ MINIMAX_API_KEY/OPENAI_API_KEY/DEEPSEEK_API_KEY 未设置，请在 .env 文件中配置")
        print("   请参考 ENV_SETUP.md 了解如何配置环境变量")
        sys.exit(1)
    
    # 项目路径
    project_path = "d:/代码仓库生图/create_graph"
    
    # 初始化Agent
    agent = CodeUnderstandingAgent(api_key=api_key, base_url=base_url)
    
    # 加载项目
    project_info = agent.load_project(project_path)
    print(f"\n✓ 项目加载: {project_info['name']}")
    print(f"  - Python文件数: {project_info['files_count']}")
    
    # 阶段1：项目概览
    overview = agent.analyze_project_overview()
    
    # 阶段2和3需要代码符号表，这里简化演示
    # 实际使用中会从CodeAnalyzer获取符号表
    
    # 保存结果
    agent.save_analysis_result("output/llm_analysis_result.json")


if __name__ == "__main__":
    main()
