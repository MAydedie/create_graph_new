"""
上下文压缩器模块

负责将对话切分为语义单元，并为每个单元生成主题和摘要。
实现了主题切换检测、关键词提取和 LLM 驱动的摘要生成。
"""

import re
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime

# 添加项目路径
sys.path.insert(0, r"D:\代码仓库生图\create_graph")

from .context_unit import ContextUnit


# 中文停用词
CHINESE_STOPWORDS = {
    "的", "了", "在", "是", "我", "你", "他", "她", "它", "这", "那",
    "和", "与", "或", "但", "如果", "因为", "所以", "虽然", "但是",
    "就", "也", "都", "还", "很", "非常", "可以", "能够", "应该",
    "会", "要", "想", "让", "把", "被", "对", "从", "到", "给",
    "吗", "呢", "啊", "吧", "呀", "哦", "哈", "嗯", "好", "不",
    "有", "没有", "什么", "怎么", "为什么", "哪里", "哪个", "谁",
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "to", "of",
    "in", "for", "on", "with", "at", "by", "from", "as", "into",
    "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "then", "once"
}


class ContextCompressor:
    """
    上下文压缩器
    
    职责：
    1. 检测对话主题切换
    2. 将对话切分为语义单元
    3. 为每个单元生成摘要
    """
    
    def __init__(
        self,
        llm_api=None,
        max_unit_messages: int = 10,
        keyword_overlap_threshold: int = 2
    ):
        """
        初始化压缩器
        
        Args:
            llm_api: LLM API 客户端（用于生成摘要）
            max_unit_messages: 单个单元最大消息数（超过则强制分割）
            keyword_overlap_threshold: 关键词重叠阈值（低于则认为是新主题）
        """
        self.llm_api = llm_api
        self.max_unit_messages = max_unit_messages
        self.keyword_overlap_threshold = keyword_overlap_threshold
        
        # 当前正在构建的单元
        self.current_unit_messages: List[Dict] = []
        self.current_topic: Optional[str] = None
    
    def should_create_new_unit(self, new_message: Dict) -> bool:
        """
        判断是否应该创建新单元
        
        策略：
        1. 消息数量达到阈值
        2. 检测到主题切换（通过关键词变化）
        3. 用户明确开始新任务（通过关键词检测）
        
        Args:
            new_message: 新的消息
            
        Returns:
            是否应该创建新单元
        """
        # 策略 1：消息数量达到阈值
        if len(self.current_unit_messages) >= self.max_unit_messages:
            return True
        
        # 如果当前单元为空，不需要创建新单元
        if not self.current_unit_messages:
            return False
        
        # 策略 2：主题切换检测
        if self._detect_topic_shift(new_message):
            return True
        
        # 策略 3：用户明确开始新任务
        if self._detect_new_task_keywords(new_message):
            return True
        
        return False
    
    def _detect_topic_shift(self, new_message: Dict) -> bool:
        """
        检测主题切换
        
        简化实现：检测关键词变化
        
        Args:
            new_message: 新的消息
            
        Returns:
            是否检测到主题切换
        """
        if not self.current_unit_messages:
            return False
        
        # 获取最近一条消息的关键词
        last_content = self.current_unit_messages[-1].get("content", "")
        current_keywords = set(self._extract_keywords(last_content))
        
        # 获取新消息的关键词
        new_content = new_message.get("content", "")
        new_keywords = set(self._extract_keywords(new_content))
        
        # 如果关键词重叠度低，认为是新主题
        overlap = len(current_keywords & new_keywords)
        return overlap < self.keyword_overlap_threshold
    
    def _detect_new_task_keywords(self, new_message: Dict) -> bool:
        """
        检测是否包含新任务关键词
        
        Args:
            new_message: 新的消息
            
        Returns:
            是否检测到新任务
        """
        new_task_indicators = [
            "新任务", "另外", "接下来", "下一个", "换个",
            "new task", "next", "another", "switch to"
        ]
        
        content = new_message.get("content", "").lower()
        return any(indicator in content for indicator in new_task_indicators)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        提取关键词
        
        简化实现：提取非停用词的词语
        
        Args:
            text: 原始文本
            
        Returns:
            关键词列表
        """
        # 提取所有词语（中文和英文）
        # 中文：匹配连续的中文字符
        # 英文：匹配连续的字母数字
        chinese_words = re.findall(r'[\u4e00-\u9fff]+', text)
        english_words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower())
        
        all_words = chinese_words + english_words
        
        # 过滤停用词和短词
        keywords = [
            w for w in all_words 
            if w.lower() not in CHINESE_STOPWORDS and len(w) > 1
        ]
        
        return keywords
    
    def add_message(self, message: Dict) -> Optional[ContextUnit]:
        """
        添加消息，如果需要则自动创建新单元
        
        Args:
            message: 新消息 {"role": "user"|"assistant", "content": "..."}
            
        Returns:
            如果创建了新单元则返回，否则返回 None
        """
        created_unit = None
        
        # 检查是否需要创建新单元
        if self.should_create_new_unit(message) and self.current_unit_messages:
            # 创建单元
            created_unit = self.create_unit(self.current_unit_messages)
            # 清空当前消息
            self.current_unit_messages = []
        
        # 添加新消息到当前单元
        self.current_unit_messages.append(message)
        
        return created_unit
    
    def create_unit(self, messages: List[Dict]) -> ContextUnit:
        """
        创建上下文单元
        
        步骤：
        1. 提取主题
        2. 生成摘要
        3. 提取关键词
        
        Args:
            messages: 消息列表
            
        Returns:
            创建的上下文单元
        """
        # 1. 提取主题（使用 LLM 或简化方法）
        topic = self._extract_topic(messages)
        
        # 2. 生成摘要（使用 LLM 或简化方法）
        summary = self._generate_summary(messages)
        
        # 3. 提取关键词
        all_text = " ".join([msg.get("content", "") for msg in messages])
        keywords = self._extract_keywords(all_text)
        
        return ContextUnit.create(
            topic=topic,
            summary=summary,
            messages=messages,
            keywords=keywords
        )
    
    def _extract_topic(self, messages: List[Dict]) -> str:
        """
        提取主题
        
        优先使用 LLM，如果不可用则使用简化方法
        
        Args:
            messages: 消息列表
            
        Returns:
            提取的主题
        """
        if self.llm_api:
            return self._extract_topic_with_llm(messages)
        else:
            return self._extract_topic_simple(messages)
    
    def _extract_topic_with_llm(self, messages: List[Dict]) -> str:
        """
        使用 LLM 提取主题
        """
        # 构建对话文本（截断以节省 Token）
        conversation = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')[:100]}"
            for msg in messages[:5]  # 只使用前 5 条
        ])
        
        prompt = f"""请为以下对话提取一个简洁的主题（不超过 10 个字）：

{conversation}

主题："""
        
        try:
            response = self.llm_api.chat([
                {"role": "user", "content": prompt}
            ], temperature=0.3, max_tokens=50)
            
            topic = response["choices"][0]["message"]["content"].strip()
            # 限制长度
            return topic[:20] if len(topic) > 20 else topic
        except Exception as e:
            # 降级到简化方法
            return self._extract_topic_simple(messages)
    
    def _extract_topic_simple(self, messages: List[Dict]) -> str:
        """
        简化的主题提取（不使用 LLM）
        
        策略：提取第一条用户消息的前 10 个字作为主题
        """
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # 取前 20 个字符，去除换行
                topic = content.replace("\n", " ")[:20]
                if len(topic) > 10:
                    topic = topic[:10] + "..."
                return topic or "对话"
        return "对话"
    
    def _generate_summary(self, messages: List[Dict]) -> str:
        """
        生成摘要
        
        优先使用 LLM，如果不可用则使用简化方法
        
        Args:
            messages: 消息列表
            
        Returns:
            生成的摘要
        """
        if self.llm_api:
            return self._generate_summary_with_llm(messages)
        else:
            return self._generate_summary_simple(messages)
    
    def _generate_summary_with_llm(self, messages: List[Dict]) -> str:
        """
        使用 LLM 生成摘要
        """
        conversation = "\n".join([
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in messages
        ])
        
        prompt = f"""请为以下对话生成一个简洁的摘要（不超过 50 字），重点关注：
1. 用户的需求或指令
2. 关键的约定或设置
3. 重要的结果

对话：
{conversation}

摘要："""
        
        try:
            response = self.llm_api.chat([
                {"role": "user", "content": prompt}
            ], temperature=0.3, max_tokens=100)
            
            summary = response["choices"][0]["message"]["content"].strip()
            # 限制长度
            return summary[:100] if len(summary) > 100 else summary
        except Exception as e:
            # 降级到简化方法
            return self._generate_summary_simple(messages)
    
    def _generate_summary_simple(self, messages: List[Dict]) -> str:
        """
        简化的摘要生成（不使用 LLM）
        
        策略：提取用户消息的关键信息
        """
        user_messages = [
            msg.get("content", "")[:50]
            for msg in messages
            if msg.get("role") == "user"
        ]
        
        if user_messages:
            # 合并用户消息，截断
            summary = " → ".join(user_messages[:3])
            return summary[:100] if len(summary) > 100 else summary
        return "对话内容"
    
    def flush_current_unit(self) -> Optional[ContextUnit]:
        """
        强制将当前消息创建为单元
        
        用于会话结束时
        
        Returns:
            创建的单元，如果当前没有消息则返回 None
        """
        if self.current_unit_messages:
            unit = self.create_unit(self.current_unit_messages)
            self.current_unit_messages = []
            return unit
        return None
    
    def get_current_messages(self) -> List[Dict]:
        """
        获取当前正在构建的消息列表
        """
        return self.current_unit_messages.copy()
