#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PlannerAgent - 规划 Agent - Phase 4

将用户的模糊需求转化为结构化的执行计划。

职责：
- 分析用户目标
- 利用 RAG 知识理解代码结构
- 生成 PlanJSON 格式的执行计划
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# 确保项目路径
def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config" / "config.py").exists():
            return current
        current = current.parent
    return Path.cwd()

PROJECT_ROOT = _find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


logger = logging.getLogger("PlannerAgent")


# Planner 专用 Prompt 模板
PLANNER_SYSTEM_PROMPT = """你是一个专业的任务规划 Agent，专门将用户的需求分解为可执行的步骤计划。

## 你的职责

1. 分析用户的目标需求
2. 理解相关的代码结构（从 RAG 知识中获取）
3. 将任务分解为清晰的执行步骤
4. 输出结构化的 PlanJSON

## 输出格式

你必须输出一个 JSON 格式的执行计划，格式如下：

```json
{
  "plan_id": "plan_YYYYMMDD_序号",
  "goal": "用户目标的简要描述",
  "analysis": "对任务的分析说明",
  "steps": [
    {
      "step_id": 0,
      "type": "analysis|code_change|verify",
      "action": "read_file|create_file|create_directory|modify_file|delete_file|run_tests",
      "target": "目标文件或目录路径",
      "description": "步骤描述"
    }
  ]
}
```

## 步骤类型说明

- **analysis**: 分析现有代码，通常是 read_file 操作
- **code_change**: 修改代码，包括 create_file、create_directory、modify_file、delete_file
- **verify**: 验证修改，通常是 run_tests 操作

## 规划原则

1. **先分析后修改**：先读取相关文件了解现状
2. **最小修改原则**：只修改必要的文件
3. **验证结束**：计划最后一步应该是验证
4. **依赖顺序**：步骤按依赖关系排序，被依赖的先执行
5. **可验证性优先**：规划时就要考虑后续测试是否“有可能通过”，不要设计明显不可能通过的测试
6. **渐进式测试**：对于复杂逻辑（如图像处理、DCT 等），优先规划 **小步验证**（例如先验证接口和基本性质），而不是一次性设计大量复杂用例

## 重要规则

1. **输出格式**：直接输出纯 JSON，不要包含任何 Markdown 代码块标记（如 \`\`\`json 或 \`\`\`），不要包含注释或解释
2. 每个步骤必须有明确的目标文件
3. 步骤描述要清晰具体
4. **关于通配符**：
   - **create_file 操作**：**禁止使用通配符**！必须使用具体文件名（如 `test_calculator.py`）
   - **read_file 操作**：可以使用通配符（如 `*.py`）读取多个文件
   - **modify_file 操作**：**禁止使用通配符**！必须使用具体文件名
5. 如果需要为多个源文件创建测试，必须为每个源文件创建独立的步骤

## 关于测试相关步骤 (type=verify / action=run_tests)

1. **目标文件必须存在**：如果计划中包含 `run_tests` 或“创建测试文件”的步骤，你必须确保：
   - 要测试的源文件真实存在，并且路径来自上下文提供的 `source_files` 或用户描述；
   - 测试文件的导入语句能够在该工程中正常工作（例如 `from utils import xxx`，前提是有 `utils.py` 且其中有对应符号）。
2. **先小后大**：
   - 第一次为某个模块创建测试时，只规划 **少量、核心的用例**，例如：接口是否可调用、最基础的性质（如“dct 与 idct 互为逆”）。
   - 不要在第一次规划中就包含大量复杂、边界极多的测试用例。
3. **分阶段增强测试**：
   - 如果用户目标很大（例如“为整个模块写完整单测”），请拆分为多次任务：
     - 当前计划只覆盖一小块最关键的行为；
     - 在 `analysis` 字段中提示“后续可以扩展的测试方向”。
4. **避免必然失败的测试**：
   - 如果根据上下文你无法确定某个函数或行为已经实现，不要规划对它做“强断言”的测试步骤；
   - 可以改为先规划“分析/读取相关文件”的步骤，或者在 `analysis` 中明确说明需要用户或后续步骤补充实现。
"""


class PlannerAgent:
    """
    规划 Agent - 将用户需求分解为执行计划
    
    工作流程：
    1. 接收用户目标和上下文
    2. 分析 RAG 知识了解代码结构
    3. 生成结构化的执行计划
    
    Attributes:
        _llm_api: LLM API 客户端
        verbose: 是否输出详细日志
    """
    
    # Phase 3.2: 类级别的调研缓存（所有实例共享）
    from llm.agent.core.research_cache import get_global_cache
    _research_cache = get_global_cache(ttl=3600)  # 1 小时过期
    
    # Phase 3.2: 智能调研策略关键词
    SKIP_RESEARCH_KEYWORDS = ["简单", "快速", "小", "修改", "删除", "重命名"]
    MUST_RESEARCH_KEYWORDS = ["复杂", "大型", "新增", "重构", "架构", "设计"]
    
    def __init__(self, llm_api=None, orchestrator=None, verbose: bool = True):
        """
        初始化 PlannerAgent
        
        Args:
            llm_api: LLM API 客户端，如果不提供则延迟加载
            orchestrator: Orchestrator 实例（Phase 3.1 新增，用于自动调研）
            verbose: 是否输出详细日志
        """
        self._llm_api = llm_api
        self.orchestrator = orchestrator  # Phase 3.1 新增
        self.verbose = verbose
        self.logger = logging.getLogger("PlannerAgent")
    
    def _get_llm_api(self):
        """获取 LLM API（延迟加载）"""
        if self._llm_api is None:
            from llm.rag_core.llm_api import DeepSeekAPI
            self._llm_api = DeepSeekAPI()
        return self._llm_api
    
    def plan(self, user_goal: str, context: Dict = None, skip_research: bool = False, use_cache: bool = True) -> Dict[str, Any]:
        """
        生成执行计划（Phase 3.2 增强版）
        
        Args:
            user_goal: 用户目标描述
            context: 上下文信息，包括 RAG 知识、对话历史等
            skip_research: 是否跳过自动调研（默认 False）
            use_cache: 是否使用缓存（默认 True，Phase 3.2 新增）
            
        Returns:
            PlanJSON 格式的计划，包含：
            - plan_id: 计划 ID
            - goal: 目标描述
            - analysis: 分析说明
            - steps: 步骤列表
            - error: 如果失败，包含错误信息
        """
        context = context or {}
        
        self._log(f"开始规划任务: {user_goal}")
        
        # Phase 3.2: 智能调研策略
        should_research = not skip_research and self._should_research(user_goal)
        
        # Phase 3.1/3.2: 自动调研代码库（如果需要）
        if should_research and self.orchestrator and hasattr(self.orchestrator, 'spawn_subagent'):
            try:
                import os
                project_path = context.get("project_path", os.getcwd())
                
                # Phase 3.2: 尝试从缓存获取
                cached_research = None
                if use_cache:
                    cached_research = self._research_cache.get(project_path, user_goal)
                    if cached_research:
                        self._log("[Phase 3.2] 缓存命中，使用缓存的调研结果")
                
                if cached_research:
                    research_summary = cached_research
                else:
                    # 执行调研
                    self._log("[Phase 3.1] 开始自动调研代码库...")
                    research_summary = self.orchestrator.spawn_subagent(
                        agent_type="research",
                        prompt=f"分析 '{user_goal}' 涉及的文件、模块和代码结构"
                    )
                    
                    # Phase 3.2: 缓存结果
                    if use_cache:
                        self._research_cache.set(project_path, user_goal, research_summary)
                        self._log("[Phase 3.2] 调研结果已缓存")
                
                # 将调研结果融入 context
                context["research"] = research_summary
                self._log(f"[Phase 3.1] 调研完成: {research_summary[:100]}...")
            except Exception as e:
                self._log(f"[Phase 3.1] 自动调研失败（继续规划）: {e}")
        
        try:
            # 构建 prompt
            prompt = self._build_prompt(user_goal, context)
            
            # 调用 LLM
            llm_api = self._get_llm_api()
            
            messages = [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            response = llm_api.chat(
                messages=messages,
                temperature=0.2,  # 低温度，更确定性
                max_tokens=8192,  # V3.3: 增加到 8192 避免大计划被截断
                timeout=120
            )
            
            # 提取响应内容
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
            else:
                content = response.get("content", "")
            
            # V3.3 DEBUG: 保存原始 LLM 输出到文件方便调试
            try:
                from pathlib import Path
                debug_path = Path(r"D:\代码仓库生图\create_graph\debug_llm_output.txt")
                debug_path.write_text(content, encoding="utf-8")
                self.logger.info(f"LLM 原始输出已保存到: {debug_path}")
            except Exception as debug_e:
                self.logger.warning(f"无法保存调试输出: {debug_e}")
            
            # 解析 JSON
            plan = self._parse_plan(content, user_goal)
            
            self._log(f"计划生成成功: {len(plan.get('steps', []))} 步")
            return plan
            
        except Exception as e:
            self.logger.error(f"规划失败: {e}")
            return {
                "plan_id": f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "goal": user_goal,
                "steps": [],
                "error": str(e)
            }
    
    def _build_prompt(self, user_goal: str, context: Dict) -> str:
        """
        构建 Planner 的 prompt
        
        Args:
            user_goal: 用户目标
            context: 上下文信息
            
        Returns:
            完整的 prompt 字符串
        """
        lines = [f"## 用户目标\n\n{user_goal}"]
        
        # 添加 RAG 知识
        rag_knowledge = context.get("rag_knowledge", {})
        if rag_knowledge:
            context_summary = rag_knowledge.get("context_summary", "")
            if context_summary:
                lines.append(f"\n## 相关代码知识\n\n{context_summary}")
        
        # 添加对话上下文
        conversation = context.get("conversation_context", {})
        if conversation:
            ctx_str = conversation.get("context", "")
            if ctx_str:
                lines.append(f"\n## 对话上下文\n\n{ctx_str}")
        
        # 添加当前状态
        current_status = context.get("current_status", "")
        if current_status:
            lines.append(f"\n## 当前执行状态\n\n{current_status}")
        
        # V3 新增：添加文件结构信息
        file_structure = context.get("file_structure", {})
        if file_structure and file_structure.get("scanned"):
            fs_content = file_structure.get("file_structure", "")
            source_files = file_structure.get("source_files", [])
            
            if fs_content:
                lines.append(f"\n## 目标目录的文件结构（已扫描）\n{fs_content}")
            
            # V3.1 新增：明确列出源文件并给出示例
            if source_files:
                lines.append("\n## 重要提示：具体文件路径")
                lines.append("\n基于上述扫描结果，以下是可用的源文件：")
                for sf in source_files[:10]:  # 最多显示10个作为示例
                    lines.append(f"  - {sf}")
                if len(source_files) > 10:
                    lines.append(f"  ... 还有 {len(source_files) - 10} 个文件")
                
                lines.append("\n**关键规则**：")
                lines.append("1. **禁止使用通配符**：不要在文件路径中使用 `*`、`?` 等通配符")
                lines.append("2. **使用具体路径**：必须使用上述列表中的具体文件名")
                lines.append("3. **示例**：如果要为 `calculator.py` 生成测试，步骤应为：")
                lines.append("   ```")
                lines.append("   {")
                lines.append('     "action": "create_file",')
                lines.append('     "target": "D:\\\\...\\\\test_sandbox\\\\test_calculator.py",')
                lines.append('     "description": "为 calculator.py 生成测试文件"')
                lines.append("   }")
                lines.append("   ```")
        
        lines.append("\n请基于以上信息，生成详细的执行计划。")
        
        return "\n".join(lines)
    
    def _parse_plan(self, content: str, user_goal: str) -> Dict[str, Any]:
        """
        解析 LLM 返回的计划
        
        Args:
            content: LLM 返回的内容
            user_goal: 用户目标（用于回退）
            
        Returns:
            解析后的计划字典
        """
        # 尝试直接解析 JSON
        try:
            # 移除可能的 markdown 代码块标记
            clean_content = content.strip()
            if clean_content.startswith("```json"):
                clean_content = clean_content[7:]
            if clean_content.startswith("```"):
                clean_content = clean_content[3:]
            if clean_content.endswith("```"):
                clean_content = clean_content[:-3]
            clean_content = clean_content.strip()
            
            plan = json.loads(clean_content)
            
            # 确保有必要的字段
            if "plan_id" not in plan:
                plan["plan_id"] = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if "goal" not in plan:
                plan["goal"] = user_goal
            if "steps" not in plan:
                plan["steps"] = []
            
            return plan
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"JSON 解析失败: {e}")
            
            # V3.3: 尝试修复常见的 JSON 问题
            try:
                # 修复1: 将换行符替换为 \n
                fixed_content = clean_content.replace('\n', '\\n').replace('\r', '')
                # 修复2: 尝试修复路径中的反斜杠
                fixed_content = fixed_content.replace('\\\\', '\\\\\\\\')
                plan = json.loads(fixed_content)
                if "plan_id" not in plan:
                    plan["plan_id"] = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                return plan
            except:
                pass
            
            # 尝试从内容中提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    # 再次尝试解析
                    extracted = json_match.group()
                    plan = json.loads(extracted)
                    if "plan_id" not in plan:
                        plan["plan_id"] = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    return plan
                except:
                    # V3.3: 尝试用 ast.literal_eval 作为后备
                    try:
                        import ast
                        plan = ast.literal_eval(extracted)
                        if isinstance(plan, dict):
                            if "plan_id" not in plan:
                                plan["plan_id"] = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            return plan
                    except:
                        pass
            
            # 回退：创建简单计划
            self.logger.warning("无法解析计划，创建简单计划")
            return {
                "plan_id": f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "goal": user_goal,
                "analysis": "无法解析 LLM 返回的计划，使用简单计划",
                "steps": [
                    {
                        "step_id": 0,
                        "type": "analysis",
                        "action": "analyze",
                        "target": "user_goal",
                        "description": user_goal
                    }
                ],
                "warning": "计划由回退机制生成"
            }
    
    def _should_research(self, user_goal: str) -> bool:
        """
        判断是否需要调研（Phase 3.2 智能策略）
        
        Args:
            user_goal: 用户目标
        
        Returns:
            是否需要调研
        """
        user_goal_lower = user_goal.lower()
        
        # 检查必须调研的关键词
        for keyword in self.MUST_RESEARCH_KEYWORDS:
            if keyword in user_goal_lower:
                return True
        
        # 检查跳过调研的关键词
        for keyword in self.SKIP_RESEARCH_KEYWORDS:
            if keyword in user_goal_lower:
                return False
        
        # 默认调研
        return True
    
    def _log(self, message: str):
        """输出日志 - 安全处理特殊字符"""
        if self.verbose:
            self.logger.info(message)
            try:
                print(f"[PlannerAgent] {message}")
            except UnicodeEncodeError:
                safe_msg = message.encode('gbk', errors='replace').decode('gbk')
                print(f"[PlannerAgent] {safe_msg}")


# 便捷函数
def create_planner_agent(llm_api=None, orchestrator=None, verbose: bool = True) -> PlannerAgent:
    """创建 PlannerAgent"""
    return PlannerAgent(llm_api=llm_api, orchestrator=orchestrator, verbose=verbose)
