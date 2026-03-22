#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prompt 模板 (Prompt Templates)

ReAct 格式的 Prompt 设计，用于引导 LLM 进行多步推理和工具调用。

输出格式约定：
- <thinking>...</thinking> - 思考过程
- <plan>...</plan> - 执行计划（可选）
- <action>{"tool": "...", "args": {...}}</action> - 工具调用
- <final_answer>...</final_answer> - 最终回答
"""

from typing import List, Dict, Any, Optional


# ============================================================
# System Prompt 模板
# ============================================================

SYSTEM_PROMPT_TEMPLATE = """你是一个专业的代码分析 Agent，专门帮助用户理解和分析代码仓库。

## 你的能力

你可以使用以下工具来完成任务：

{tools_description}

## 工作流程

你遵循 ReAct (Reasoning and Acting) 模式：
1. **思考 (Thinking)**: 分析用户问题，思考需要什么信息
2. **行动 (Action)**: 调用工具获取信息
3. **观察 (Observation)**: 查看工具返回结果
4. **反复**: 如果信息不足，继续调用其他工具
5. **回答**: 信息充足后，给出最终答案

## 输出格式

你必须严格按照以下 XML 标签格式输出：

### 当需要调用工具时：
```
<thinking>
分析问题，思考需要什么信息...
</thinking>

<action>
{{"tool": "工具名称", "args": {{"参数名": "参数值"}}}}
</action>
```

### 当准备给出最终答案时：
```
<thinking>
总结已获取的信息...
</thinking>

<final_answer>
基于以上分析，答案是...
</final_answer>
```

## 重要规则

1. **必须使用 XML 标签**：所有输出必须包含 `<thinking>` 标签
2. **工具调用格式**：`<action>` 内必须是有效的 JSON
3. **一次一个动作**：每轮只能调用一个工具或给出最终答案
4. **基于证据回答**：只基于工具返回的实际信息回答，不要编造
5. **承认不知道**：如果工具返回的信息不足以回答问题，明确说明

## 当前时间
{current_time}
"""


# ============================================================
# Few-shot 示例
# ============================================================

FEW_SHOT_EXAMPLES = [
    # 示例 1: 简单的图谱查询
    {
        "user": "什么是功能分区？",
        "assistant": """<thinking>
用户问的是关于"功能分区"的概念。这是一个关于代码分析系统的概念性问题。
我应该先查询知识图谱来获取相关信息。
</thinking>

<action>
{"tool": "QueryKnowledgeGraph", "args": {"query": "什么是功能分区"}}
</action>""",
        "observation": """【工具执行结果】
成功查询知识图谱。

答案：功能分区是将代码库按照业务功能进行逻辑划分的方法。每个分区代表一个独立的功能模块，
包含相关的类、函数和它们之间的调用关系。功能分区有助于理解代码结构和定位特定功能的实现。

召回结果: 10, 重排后: 5""",
        "final": """<thinking>
知识图谱已经返回了关于功能分区的详细解释。信息足够回答用户的问题了。
</thinking>

<final_answer>
**功能分区**是将代码库按照业务功能进行逻辑划分的方法。

主要特点：
1. 每个分区代表一个独立的功能模块
2. 包含相关的类、函数和它们之间的调用关系
3. 有助于理解代码结构和定位特定功能的实现

功能分区使得大型代码库更容易理解和维护，开发者可以快速找到特定功能对应的代码位置。
</final_answer>"""
    },
    
    # 示例 2: 需要读取文件的多步推理
    {
        "user": "FileManager 类是如何实现安全读取的？",
        "assistant": """<thinking>
用户想了解 FileManager 类的 safe_read 实现细节。
首先我应该查询知识图谱，看看有没有相关信息。
</thinking>

<action>
{"tool": "RetrieveContext", "args": {"query": "FileManager safe_read 实现", "top_k": 5}}
</action>""",
        "observation": """【工具执行结果】
检索到 5 条相关上下文。

【上下文 1】(function)
FileManager.safe_read 方法位于 llm/agent/infrastructure/file_manager.py
功能：安全读取文件内容，支持大小限制和编码处理

【上下文 2】(class)
FileManager 类提供安全的文件操作能力...""",
        "step2_assistant": """<thinking>
知识图谱告诉我 safe_read 方法在 llm/agent/infrastructure/file_manager.py 文件中。
但我需要看具体的实现代码才能详细解释。让我读取这个文件。
</thinking>

<action>
{"tool": "ReadFile", "args": {"path": "llm/agent/infrastructure/file_manager.py"}}
</action>""",
        "step2_observation": """【工具执行结果】
读取成功，内容如下：

def safe_read(self, path: str, max_bytes: Optional[int] = None, encoding: str = "utf-8") -> Dict[str, Any]:
    max_bytes = max_bytes or self.max_read_bytes
    resolved = self._resolve_path(path)
    
    # 安全检查
    if not self._is_path_allowed(resolved):
        return {"success": False, "error": f"路径不在允许范围内: {path}"}
    
    if not resolved.exists():
        return {"success": False, "error": f"文件不存在: {path}"}
    ...""",
        "final": """<thinking>
现在我已经看到了 safe_read 的具体实现代码，可以详细解释它的工作原理了。
</thinking>

<final_answer>
**FileManager.safe_read() 的安全读取机制**

该方法通过多层安全检查来实现安全读取：

1. **路径白名单检查** (`_is_path_allowed`)
   - 验证请求的路径是否在允许的目录范围内
   - 防止越权访问系统敏感文件

2. **文件存在性检查**
   - 确保目标文件确实存在
   - 返回清晰的错误信息

3. **大小限制** (`max_bytes`)
   - 默认限制读取 50KB
   - 自动截断过大的文件，避免内存问题

4. **编码处理**
   - 支持指定编码（默认 UTF-8）
   - 使用 `errors="replace"` 防止编码错误导致崩溃

这种设计确保了 Agent 不会意外读取敏感文件或因读取大文件而导致系统问题。
</final_answer>"""
    },
    
    # 示例 3: 工具调用失败后的重试
    {
        "user": "查看 config/settings.py 的内容",
        "assistant": """<thinking>
用户想查看 config/settings.py 文件的内容。我直接使用 ReadFile 工具读取。
</thinking>

<action>
{"tool": "ReadFile", "args": {"path": "config/settings.py"}}
</action>""",
        "observation": """【工具执行结果】
读取失败：文件不存在: config/settings.py""",
        "step2_assistant": """<thinking>
文件不存在。可能是路径不对，或者这个文件真的不存在。
让我先查看 config 目录下有哪些文件。
</thinking>

<action>
{"tool": "ListDir", "args": {"path": "config"}}
</action>""",
        "step2_observation": """【工具执行结果】
目录内容 (3 项):
[文件] config.py (5.2 KB)
[文件] __init__.py (0.1 KB)
[目录] __pycache__/""",
        "final": """<thinking>
config 目录下没有 settings.py，只有 config.py。我应该告诉用户这个情况。
</thinking>

<final_answer>
文件 `config/settings.py` 不存在。

查看 `config/` 目录，发现实际存在的配置文件是：
- `config.py` (5.2 KB) - 这可能是您要找的配置文件

如果您想查看配置内容，请确认是否要查看 `config/config.py`？
</final_answer>"""
    }
]


def build_tools_description(tools: List[Dict[str, Any]]) -> str:
    """
    构建工具描述文本
    
    Args:
        tools: 工具信息列表，每个工具包含 name, description, parameters
        
    Returns:
        格式化的工具描述
    """
    lines = []
    for i, tool in enumerate(tools, 1):
        lines.append(f"### {i}. {tool['name']}")
        lines.append(f"**描述**: {tool['description']}")
        
        if 'parameters' in tool and tool['parameters'].get('properties'):
            lines.append("**参数**:")
            props = tool['parameters']['properties']
            required = tool['parameters'].get('required', [])
            
            for param_name, param_info in props.items():
                param_type = param_info.get('type', 'any')
                param_desc = param_info.get('description', '')
                is_required = "必填" if param_name in required else "可选"
                lines.append(f"  - `{param_name}` ({param_type}, {is_required}): {param_desc}")
        
        lines.append("")
    
    return "\n".join(lines)


def build_system_prompt(tools: List[Dict[str, Any]], current_time: str = None) -> str:
    """
    构建系统提示词
    
    Args:
        tools: 工具信息列表
        current_time: 当前时间字符串
        
    Returns:
        完整的系统提示词
    """
    from datetime import datetime
    
    tools_desc = build_tools_description(tools)
    time_str = current_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return SYSTEM_PROMPT_TEMPLATE.format(
        tools_description=tools_desc,
        current_time=time_str
    )


def build_few_shot_messages() -> List[Dict[str, str]]:
    """
    构建 Few-shot 示例消息列表
    
    Returns:
        消息列表，可直接用于 LLM 对话历史
    """
    messages = []
    
    for example in FEW_SHOT_EXAMPLES[:2]:  # 只使用前 2 个示例，避免 prompt 过长
        # 用户问题
        messages.append({
            "role": "user",
            "content": example["user"]
        })
        
        # 助手第一次回复（调用工具）
        messages.append({
            "role": "assistant",
            "content": example["assistant"]
        })
        
        # 工具结果（作为用户消息呈现）
        messages.append({
            "role": "user",
            "content": example["observation"]
        })
        
        # 如果有第二步
        if "step2_assistant" in example:
            messages.append({
                "role": "assistant",
                "content": example["step2_assistant"]
            })
            messages.append({
                "role": "user",
                "content": example["step2_observation"]
            })
        
        # 最终答案
        messages.append({
            "role": "assistant",
            "content": example["final"]
        })
    
    return messages


def format_observation(tool_name: str, result: Dict[str, Any]) -> str:
    """
    格式化工具执行结果为 observation 文本
    
    Args:
        tool_name: 工具名称
        result: 工具返回结果
        
    Returns:
        格式化的 observation 文本
    """
    if result.get("success"):
        content = result.get("result", str(result))
        return f"【工具 {tool_name} 执行结果】\n{content}"
    else:
        error = result.get("error", "未知错误")
        return f"【工具 {tool_name} 执行失败】\n错误: {error}"
