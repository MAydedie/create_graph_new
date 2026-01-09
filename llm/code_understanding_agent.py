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
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

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
        
        # 延迟导入到这里以支持不同的配置
        try:
            # 尝试使用 langchain_openai (新版本)
            try:
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    model="deepseek-chat",
                    temperature=0.3,
                    max_tokens=8000
                )
                logger.info("✓ ChatOpenAI客户端初始化成功 (langchain_openai)")
            except ImportError:
                # 回退到 langchain_community (兼容版本)
                try:
                    from langchain_community.chat_models import ChatOpenAI
                    self.llm = ChatOpenAI(
                        openai_api_key=api_key,
                        openai_api_base=base_url,
                        model_name="deepseek-chat",
                        temperature=0.3,
                        max_tokens=8000
                    )
                    logger.info("✓ ChatOpenAI客户端初始化成功 (langchain_community)")
                except ImportError:
                    # 最后回退：直接使用 requests 调用 API
                    logger.warning("⚠️ 未安装 langchain，将使用直接 API 调用")
                    self.llm = None
                    self._use_direct_api = True
        except Exception as e:
            logger.error(f"✗ 初始化LLM客户端失败: {e}")
            logger.warning("⚠️ 将使用直接 API 调用模式")
            self.llm = None
            self._use_direct_api = True
    
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
            
            if self.llm:
                # 使用 LangChain
                response = self.llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ])
                analysis = response.content
            else:
                # 直接 API 调用
                analysis = self._call_api_directly(system_prompt, user_prompt)
            
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
            if self.llm:
                response = self.llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ])
                return response.content
            else:
                return self._call_api_directly(system_prompt, user_prompt)
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
            if self.llm:
                response = self.llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ])
                result_text = response.content
            else:
                result_text = self._call_api_directly(system_prompt, user_prompt)
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
            if self.llm or self._use_direct_api:
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
                    
                    if self.llm:
                        response = self.llm.invoke([
                            SystemMessage(content=system_prompt),
                            HumanMessage(content=user_prompt)
                        ])
                        response_content = response.content
                    else:
                        response_content = self._call_api_directly(system_prompt, user_prompt)
                    
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
            
            if self.llm:
                response = self.llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ])
                response_text = response.content
            else:
                response_text = self._call_api_directly(system_prompt, user_prompt)
            
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


def main():
    """主函数：演示Agent的使用"""
    import sys
    
    # API配置
    api_key = "sk-a7e7d7ee44594ac98c27d64a7496742f"
    base_url = "https://api.deepseek.com/v1"
    
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
