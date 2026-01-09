#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代码解释生成链 - 为重要代码生成LLM解释
使用LangChain构建的链式处理
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
import json

logger = logging.getLogger(__name__)


class CodeExplanationChain:
    """
    代码解释生成链
    用于为重要代码（标注为"重要-1"）生成LLM解释
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1"):
        """
        初始化代码解释链
        
        Args:
            api_key: DeepSeek API密钥
            base_url: DeepSeek API基础URL
        """
        self.api_key = api_key
        self.base_url = base_url
        
        logger.info(f"初始化CodeExplanationChain，base_url: {base_url}")
        
        try:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model="deepseek-chat",
                temperature=0.2,  # 降低温度以获得更稳定的解释
                max_tokens=1000
            )
            logger.info("✓ ChatOpenAI客户端初始化成功")
        except Exception as e:
            logger.error(f"✗ 初始化ChatOpenAI失败: {e}")
            raise
    
    def explain_code(self, 
                    source_code: str, 
                    docstring: str = "", 
                    comments: str = "",
                    code_context: str = "") -> str:
        """
        为代码生成解释
        
        Args:
            source_code: 源代码
            docstring: 已有的文档字符串
            comments: 代码中的注释
            code_context: 代码上下文（如所在的类、方法等）
        
        Returns:
            LLM生成的解释（100-200字）
        """
        system_prompt = """你是一个资深的代码分析专家。
你的任务是用简洁清晰的语言解释给定的代码的功能和设计意图。

解释应该：
1. 简洁（不超过200字）
2. 清楚明了（避免过度技术术语）
3. 突出关键逻辑和设计决策
4. 指出该代码与系统其他部分的关系（如果有）

格式：
- 主要功能是什么？（1-2句）
- 关键算法或逻辑是什么？（1-2句）
- 与系统的关系？（1句）"""
        
        # 构建用户提示
        user_prompt = f"""请解释以下代码的功能和设计意图：

【代码上下文】
{code_context if code_context else "（无上下文）"}

【源代码】
```python
{source_code}
```"""
        
        # 添加已有的文档信息
        if docstring or comments:
            user_prompt += "\n\n【已有的文档】\n"
            if docstring:
                user_prompt += f"文档字符串：{docstring}\n"
            if comments:
                user_prompt += f"代码注释：{comments}\n"
        
        user_prompt += "\n请简洁地解释这个代码。"
        
        try:
            logger.debug("🤖 调用DeepSeek API生成代码解释...")
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            explanation = response.content
            logger.debug(f"✓ 代码解释生成完成，长度: {len(explanation)}")
            return explanation
            
        except Exception as e:
            logger.error(f"✗ 代码解释生成失败: {e}")
            return f"无法生成解释: {str(e)}"
    
    def explain_batch(self, code_details_list: list, batch_size: int = 5) -> Dict[str, str]:
        """
        批量生成代码解释
        为了节省token，使用批处理
        
        Args:
            code_details_list: CodeDetail对象列表
            batch_size: 批处理大小
        
        Returns:
            {entity_id: explanation} 字典
        """
        explanations = {}
        total = len(code_details_list)
        
        logger.info(f"开始批量生成代码解释，共 {total} 个代码")
        
        for i, code_detail in enumerate(code_details_list, 1):
            # 如果已经有解释，跳过
            if code_detail.llm_explanation:
                logger.debug(f"[{i}/{total}] {code_detail.entity_name} 已有缓存解释，跳过")
                explanations[code_detail.entity_id] = code_detail.llm_explanation
                continue
            
            try:
                logger.info(f"[{i}/{total}] 生成解释: {code_detail.entity_name}")
                
                # 获取代码上下文
                context = f"所在文件：{code_detail.file_path}\n"
                if code_detail.entity_type == "method":
                    context += f"所在类中的方法"
                elif code_detail.entity_type == "class":
                    context += f"类定义"
                else:
                    context += f"文件级别的{code_detail.entity_type}"
                
                # 合并注释
                comments_str = "\n".join(code_detail.comments) if code_detail.comments else ""
                
                # 生成解释
                explanation = self.explain_code(
                    source_code=code_detail.source_code,
                    docstring=code_detail.docstring,
                    comments=comments_str,
                    code_context=context
                )
                
                explanations[code_detail.entity_id] = explanation
                code_detail.llm_explanation = explanation
                code_detail.explanation_generated_at = datetime.now().isoformat()
                
            except Exception as e:
                logger.error(f"生成解释失败 ({code_detail.entity_name}): {e}")
                explanations[code_detail.entity_id] = f"生成失败: {str(e)}"
        
        logger.info(f"✓ 批量生成完成，共 {len(explanations)} 个解释")
        return explanations
    
    def explain_control_flow(self, cfg: str, method_name: str = "") -> str:
        """
        解释控制流图（CFG）
        用于说明方法的执行路径和分支逻辑
        
        Args:
            cfg: 控制流图（DOT格式或文本格式）
            method_name: 方法名称
        
        Returns:
            CFG的解释
        """
        system_prompt = """你是一个CFG（控制流图）分析专家。
根据给定的CFG，用简洁的语言解释该方法的执行流程。

解释应该：
1. 描述主要的执行路径
2. 指出关键的分支点（if/else等）
3. 说明循环结构（如果有）
4. 总结所有可能的执行路径"""
        
        user_prompt = f"""请分析以下控制流图，说明方法的执行流程：

【方法】{method_name if method_name else "未命名"}

【CFG】
{cfg}

请简洁地描述该方法的执行流程和关键分支。"""
        
        try:
            logger.debug("🤖 调用DeepSeek API分析CFG...")
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            explanation = response.content
            logger.debug(f"✓ CFG分析完成，长度: {len(explanation)}")
            return explanation
            
        except Exception as e:
            logger.error(f"✗ CFG分析失败: {e}")
            return f"无法分析CFG: {str(e)}"
    
    def compare_implementations(self, code1: str, code2: str, 
                              name1: str = "实现1", name2: str = "实现2") -> str:
        """
        比较两个代码实现的差异和相似性
        用于理解重载方法或不同实现的差异
        
        Args:
            code1: 第一段代码
            code2: 第二段代码
            name1: 第一段代码的名称
            name2: 第二段代码的名称
        
        Returns:
            比较分析
        """
        system_prompt = """你是一个代码对比分析专家。
比较两段代码的差异、相似性和设计意图的区别。

分析应该：
1. 指出主要差异
2. 说明为什么会有这些差异
3. 指出相似之处
4. 总结两个实现的不同适用场景"""
        
        user_prompt = f"""请比较以下两段代码的差异和相似性：

【{name1}】
```python
{code1}
```

【{name2}】
```python
{code2}
```

请指出主要差异、原因和设计意图。"""
        
        try:
            logger.debug("🤖 调用DeepSeek API进行代码比较...")
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            comparison = response.content
            logger.debug(f"✓ 代码比较完成，长度: {len(comparison)}")
            return comparison
            
        except Exception as e:
            logger.error(f"✗ 代码比较失败: {e}")
            return f"无法进行比较: {str(e)}"
    
    def summarize_critical_path(self, call_chain: list, code_details_map: dict) -> str:
        """
        为关键路径生成摘要解释
        用于理解重要功能的执行流程
        
        Args:
            call_chain: 调用链，如[entity_id1, entity_id2, entity_id3]
            code_details_map: {entity_id: CodeDetail} 字典
        
        Returns:
            关键路径的摘要解释
        """
        # 构建调用链的描述
        chain_description = []
        for i, entity_id in enumerate(call_chain, 1):
            detail = code_details_map.get(entity_id)
            if detail:
                chain_description.append(f"{i}. {detail.entity_name} ({detail.entity_type})")
        
        system_prompt = """你是一个系统架构分析专家。
根据给定的调用链，总结这个关键路径的整体目的和流程。

摘要应该：
1. 说明这条路径的整体目的
2. 描述关键步骤
3. 指出关键操作和状态变化
4. 总结这个路径的重要性"""
        
        user_prompt = f"""请根据以下调用链生成摘要说明：

调用链：
{chr(10).join(chain_description)}

每个步骤的具体功能：
{self._get_chain_details(code_details_map, call_chain)}

请简洁地总结这个关键路径的目的和流程。"""
        
        try:
            logger.debug("🤖 调用DeepSeek API生成路径摘要...")
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            summary = response.content
            logger.debug(f"✓ 路径摘要生成完成，长度: {len(summary)}")
            return summary
            
        except Exception as e:
            logger.error(f"✗ 路径摘要生成失败: {e}")
            return f"无法生成摘要: {str(e)}"
    
    def _get_chain_details(self, code_details_map: dict, call_chain: list) -> str:
        """获取调用链的详细信息"""
        details = []
        for i, entity_id in enumerate(call_chain, 1):
            detail = code_details_map.get(entity_id)
            if detail:
                # 提取前50个字符的代码摘要
                code_snippet = detail.source_code.split('\n')[0][:100]
                if detail.docstring:
                    doc_snippet = detail.docstring[:100]
                    details.append(f"{i}. {detail.entity_name}: {doc_snippet}")
                else:
                    details.append(f"{i}. {detail.entity_name}: {code_snippet}")
        return "\n".join(details)


def generate_explanations_for_hierarchy(hierarchy_model, api_key: str, base_url: str) -> None:
    """
    为层级模型中的重要代码生成解释
    这个函数作为后端异步任务调用
    
    Args:
        hierarchy_model: HierarchyModel实例
        api_key: DeepSeek API密钥
        base_url: DeepSeek API基础URL
    """
    logger.info("\n" + "="*50)
    logger.info("📝 开始为重要代码生成LLM解释")
    logger.info("="*50)
    
    # 初始化链
    chain = CodeExplanationChain(api_key=api_key, base_url=base_url)
    
    # 收集所有需要解释的代码（"重要-1"）
    critical_codes = [
        detail for detail in hierarchy_model.layer4_details.values()
        if "重要-1" in detail.importance_mark and not detail.llm_explanation
    ]
    
    logger.info(f"需要生成解释的重要代码: {len(critical_codes)} 个")
    
    if critical_codes:
        # 批量生成解释
        explanations = chain.explain_batch(critical_codes)
        logger.info(f"✓ 已生成 {len(explanations)} 个代码解释")
    
    # 为关键路径生成摘要
    logger.info("生成关键路径摘要...")
    from .aggregation_calculator import AggregationCalculator
    calculator = AggregationCalculator(hierarchy_model)
    critical_paths = calculator.get_critical_paths()
    
    for i, path in enumerate(critical_paths[:3], 1):  # 只生成前3条关键路径的摘要
        try:
            logger.info(f"  生成第{i}条路径的摘要...")
            summary = chain.summarize_critical_path(path, hierarchy_model.layer4_details)
            logger.info(f"  ✓ 第{i}条路径摘要生成完成")
        except Exception as e:
            logger.warning(f"  ⚠️ 第{i}条路径摘要生成失败: {e}")
    
    logger.info("✓ 所有代码解释生成完成！\n")
