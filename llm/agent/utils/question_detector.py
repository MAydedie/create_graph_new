"""
智能问题检测器

用于区分简单问答和复杂任务
"""
import re
from typing import Dict, Any


class QuestionDetector:
    """检测用户输入是否为简单问答"""
    
    # 简单问答的关键词
    QUESTION_KEYWORDS = [
        "什么", "为什么", "怎么", "如何", "哪个", "哪些", "谁", "哪里",
        "what", "why", "how", "which", "who", "where", "when",
        "是什么", "是谁", "能做什么", "可以做什么", "有什么功能",
        "你好", "hello", "hi", "介绍", "说明"
    ]
    
    # 任务关键词（表示需要执行操作）
    TASK_KEYWORDS = [
        "创建", "生成", "修改", "删除", "添加", "更新", "实现", "编写",
        "测试", "运行", "执行", "部署", "重构", "优化",
        "create", "generate", "modify", "delete", "add", "update",
        "implement", "write", "test", "run", "execute", "deploy",
        "refactor", "optimize", "fix", "debug"
    ]
    
    @classmethod
    def is_simple_question(cls, user_input: str) -> bool:
        """
        判断是否为简单问答
        
        规则:
        1. 包含问答关键词
        2. 不包含任务关键词
        3. 长度较短（< 100 字符）
        4. 包含问号
        """
        user_input_lower = user_input.lower()
        
        # 规则 1: 包含问答关键词
        has_question_keyword = any(
            keyword in user_input_lower 
            for keyword in cls.QUESTION_KEYWORDS
        )
        
        # 规则 2: 不包含任务关键词
        has_task_keyword = any(
            keyword in user_input_lower 
            for keyword in cls.TASK_KEYWORDS
        )
        
        # 规则 3: 长度较短
        is_short = len(user_input) < 100
        
        # 规则 4: 包含问号
        has_question_mark = "?" in user_input or "？" in user_input
        
        # 综合判断
        if has_task_keyword:
            return False  # 明确的任务请求
        
        if has_question_keyword or has_question_mark:
            return True  # 明确的问答
        
        if is_short and not has_task_keyword:
            return True  # 短文本且无任务关键词，视为问答
        
        return False  # 默认视为任务
    
    @classmethod
    def analyze(cls, user_input: str) -> Dict[str, Any]:
        """
        分析用户输入
        
        Returns:
            {
                "is_question": bool,
                "confidence": float,  # 0-1
                "reason": str
            }
        """
        is_question = cls.is_simple_question(user_input)
        
        # 计算置信度
        user_input_lower = user_input.lower()
        question_score = sum(
            1 for kw in cls.QUESTION_KEYWORDS 
            if kw in user_input_lower
        )
        task_score = sum(
            1 for kw in cls.TASK_KEYWORDS 
            if kw in user_input_lower
        )
        
        if is_question:
            confidence = min(0.5 + question_score * 0.1, 1.0)
            reason = "包含问答关键词" if question_score > 0 else "短文本且无任务关键词"
        else:
            confidence = min(0.5 + task_score * 0.1, 1.0)
            reason = "包含任务关键词" if task_score > 0 else "长文本或复杂请求"
        
        return {
            "is_question": is_question,
            "confidence": confidence,
            "reason": reason
        }
