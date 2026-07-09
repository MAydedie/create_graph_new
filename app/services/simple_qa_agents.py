from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentType(str, Enum):
    STANDARD = "standard"
    ADVISOR = "advisor"
    QA = "qa"


@dataclass
class Agent:
    name: str
    agent_type: AgentType
    icon: str
    prompt_template: str
    timeout_seconds: int = 30


@dataclass
class WorkflowContext:
    raw_requirement: str
    session_id: str
    session_mode: str = "single_project"
    project_path: str = ""
    project_name: str = ""
    project_description: str = ""
    project_readme_excerpt: str = ""
    project_structure: str = ""
    retrieval_overview: str = ""
    experience_summary: str = ""
    experience_evidence: str = ""
    project_evidence_blocks: str = ""
    project_bias_summary: str = ""
    experience_refs: list[dict[str, Any]] = field(default_factory=list)
    candidate_projects: list[dict[str, Any]] = field(default_factory=list)
    stage_outputs: dict[str, Any] = field(default_factory=dict)

    def set_output(self, stage: str, value: Any) -> None:
        self.stage_outputs[stage] = value

    def get_output(self, stage: str, default: Any = None) -> Any:
        return self.stage_outputs.get(stage, default)


SIMPLE_QA_AGENTS = {
    "requirement_analysis": Agent(
        name="requirement_analysis",
        agent_type=AgentType.STANDARD,
        icon="📋",
        prompt_template=(
            "你是 SE-Team 的需求分析专家。\n"
            "当前会话模式：{session_mode}\n"
            "当前项目路径：{project_path}\n"
            "项目名：{project_name}\n"
            "项目简介：{project_description}\n"
            "用户问题：{requirement}\n"
            "请判断问题意图，并给出检索策略。\n"
            "输出格式（严格按以下三行）：\n"
            "1) 问题类型: 架构设计 / 实现细节 / 工程治理 / 其他\n"
            "2) 检索目标: 需要重点提取的经验维度\n"
            "3) 回答策略: 先列经验再总结结论"
        ),
    ),
    "experience_retrieval": Agent(
        name="experience_retrieval",
        agent_type=AgentType.ADVISOR,
        icon="�️",
        prompt_template=(
            "你是 SE-Team 的经验检索规划专家。\n"
            "原始问题：{requirement}\n"
            "需求分析：{analysis_result}\n"
            "会话模式：{session_mode}\n"
            "候选经验库项目摘要：\n"
            "{experience_summary}\n"
            "请输出结构化检索总览，格式如下：\n"
            "- 检索覆盖: 本次命中的项目数量/路径数量\n"
            "- 重点经验库: 列出 3-6 个项目及其相关性一句话\n"
            "- 下一步提取策略: 逐库提取的字段清单（路径/方法/描述/适用场景）"
        ),
    ),
    "per_project_extraction": Agent(
        name="per_project_extraction",
        agent_type=AgentType.STANDARD,
        icon="🧩",
        prompt_template=(
            "你是 SE-Team 的逐库证据提取专家。\n"
            "问题：{requirement}\n"
            "需求分析：{analysis_result}\n"
            "检索总览：{retrieval_overview}\n"
            "经验库结构化证据：\n"
            "{project_evidence_blocks}\n"
            "请按项目逐个输出，格式严格如下：\n"
            "### [项目名]\n"
            "- 代表路径1: 项目 / 分区 / 路径名 | 一句话说明\n"
            "- 代表路径2: ...\n"
            "- 关键方法链: ...\n"
            "- 适用问题: ...\n"
            "- 局限性: ...\n"
            "要求：至少覆盖 4 个项目；每个项目至少列 2 条路径。"
        ),
        timeout_seconds=45,
    ),
    "cross_project_comparison": Agent(
        name="cross_project_comparison",
        agent_type=AgentType.STANDARD,
        icon="⚖️",
        prompt_template=(
            "你是 SE-Team 的跨库对比专家。\n"
            "问题：{requirement}\n"
            "需求分析：{analysis_result}\n"
            "逐库提取结果：{per_project_result}\n"
            "候选项目推荐度与适应场景信息：{project_bias_summary}\n"
            "请输出三部分：\n"
            "1) 经验库优先级排序（Top 1~Top 5）及理由；\n"
            "2) 每个经验库最擅长回答的子问题；\n"
            "3) 整合思路（如何串联多个库的设计思路以给出最完整且具体的答案）。"
        ),
        timeout_seconds=45,
    ),
    "qa_advisor": Agent(
        name="qa_advisor",
        agent_type=AgentType.STANDARD,
        icon="💡",
        prompt_template=(
            "你是 SE-Team 的回答策略顾问。\n"
            "问题：{requirement}\n"
            "需求分析：{analysis_result}\n"
            "逐库提取：{per_project_result}\n"
            "跨库对比：{comparison_result}\n"
            "请输出“最终回答大纲”，格式：\n"
            "- 总结结论（1-2句）\n"
            "- 按经验库列出要引用的证据条目（每库至少2条）\n"
            "- 落地实施指导（分步骤描述如何基于各库设计核心落地路径）"
        ),
        timeout_seconds=45,
    ),
    "qa_evidence_reasoning": Agent(
        name="qa_evidence_reasoning",
        agent_type=AgentType.STANDARD,
        icon="🔎",
        prompt_template=(
            "你是 SE-Team 的推理整合专家。\n"
            "问题：{requirement}\n"
            "需求分析：{analysis_result}\n"
            "检索总览：{retrieval_overview}\n"
            "逐库提取：{per_project_result}\n"
            "跨库对比：{comparison_result}\n"
            "顾问大纲：{advisor_guidance}\n"
            "经验库证据（必须直接引用其中的项目/分区/路径名/方法/描述）：\n"
            "{experience_evidence}\n"
            "请产出结构化草稿：\n"
            "1) 按项目列出核心证据（至少 6-12 条路径）；\n"
            "2) 推荐最核心参考的经验库及原因与适用场景；\n"
            "3) 给出整合核心经验后的统一设计结论。"
        ),
        timeout_seconds=45,
    ),
    "qa_reply": Agent(
        name="qa_reply",
        agent_type=AgentType.QA,
        icon="✅",
        prompt_template=(
            "你是 SE-Team 的高级全栈架构专家与核心 AI 助手。\n"
            "你的任务是直接回答用户的问题，并结合我们检索到的本地经验库提供知识增强支持。\n\n"
            "=== 用户问题 ===\n"
            "{requirement}\n\n"
            "=== 本地相关经验库参考证据 ===\n"
            "{experience_evidence}\n\n"
            "=== 辅助分析与推理草稿 ===\n"
            "逐库提取结果：{per_project_result}\n"
            "跨库对比结果：{comparison_result}\n"
            "内部推理草稿：{reasoning_result}\n\n"
            "=== 回答要求 ===\n"
            "1) 【模型主导，直奔主题】：不要套用生硬死板的条框或千篇一律的段落！严禁在你的整个回复中写出“偏向建议”、“融合方案”这两个词（包括以此命名的任何级别标题或正文内容）。像资深全栈工程师一样，以极其流畅、敏捷、自然的语气，直接针对用户的问题给出精炼、切中肯綮的深度解答和最佳实践方案。如果需要表达相关融合或倾向思路，请用极其自然的自然技术散文方式描述。\n"
            "2) 【经验库知识增强】：在组织回答的过程中，请有机、自然地融合检索到的经验库证据（如具体项目、文件名或关键函数等引用）。如果经验库中有对解决该问题有启发意义的文件或实践（参考证据中的条目，形式如「项目 / 分区 / 路径名」），请在正文叙述或示例中自然提及或融合进去，让用户知道这些参考来源于哪里，但严禁千篇一律干瘪无脑地列一长串路径列表。\n"
            "3) 【精简、干货优先】：去除冗余的、为了列证据而列证据的空洞章节。不生搬硬套、不刻意长篇大论、重点突出，直接展示核心代码、思路或关键配置。\n"
            "4) 【禁止原始来源附录】：不要在答案末尾追加“来源: ...”“经验库：...”“match_score=...”“partition_x”这类原始检索条目、分组清单或证据附录。若需要引用，只能在正文中零散自然提到少量项目名、文件名或函数名。\n"
            "5) 【保持高级智感】：发挥你的大模型（如 DeepSeek）最高水平的推理与集成能力，做到融会贯通，给出一个对用户最有帮助、可以直接用于生产或开发的卓越技术回复。\n"
            "6) 【严禁特定词汇】：你的任何输出文本里绝对不能出现“偏向建议”和“融合方案”这两个具体字眼！"
        ),
        timeout_seconds=45,
    ),
}


SIMPLE_QA_WORKFLOW_STEPS = [
    {
        "step": 1,
        "agent": "requirement_analysis",
        "stage": "requirement_analysis",
        "display": "需求分析",
        "input_keys": ["raw_requirement"],
        "output_key": "analysis_result",
        "pass_token": "ANALYSIS_READY",
    },
    {
        "step": 2,
        "agent": "experience_retrieval",
        "stage": "experience_retrieval",
        "display": "全局经验检索",
        "input_keys": ["raw_requirement", "analysis_result"],
        "output_key": "retrieval_overview",
        "pass_token": "RETRIEVAL_READY",
    },
    {
        "step": 3,
        "agent": "per_project_extraction",
        "stage": "per_project_extraction",
        "display": "逐经验库提取",
        "input_keys": ["raw_requirement", "analysis_result", "retrieval_overview"],
        "output_key": "per_project_result",
        "pass_token": "PROJECT_EXTRACTION_READY",
    },
    {
        "step": 4,
        "agent": "cross_project_comparison",
        "stage": "cross_project_comparison",
        "display": "跨经验库对比",
        "input_keys": ["raw_requirement", "analysis_result", "per_project_result"],
        "output_key": "comparison_result",
        "pass_token": "COMPARISON_READY",
    },
    {
        "step": 5,
        "agent": "qa_advisor",
        "stage": "qa_advisor",
        "display": "问答策略规划",
        "input_keys": ["raw_requirement", "analysis_result", "per_project_result", "comparison_result"],
        "output_key": "advisor_guidance",
        "pass_token": "ADVISOR_READY",
    },
    {
        "step": 6,
        "agent": "qa_evidence_reasoning",
        "stage": "qa_evidence_reasoning",
        "display": "寻找证据与构思回复",
        "input_keys": [
            "raw_requirement",
            "analysis_result",
            "retrieval_overview",
            "per_project_result",
            "comparison_result",
            "advisor_guidance",
        ],
        "output_key": "reasoning_result",
        "pass_token": "REASONING_READY",
    },
    {
        "step": 7,
        "agent": "qa_reply",
        "stage": "qa_reply",
        "display": "给出回复",
        "input_keys": [
            "retrieval_overview",
            "per_project_result",
            "comparison_result",
            "reasoning_result",
        ],
        "output_key": "final_answer",
        "pass_token": "REPLY_READY",
    },
]
