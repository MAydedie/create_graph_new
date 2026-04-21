"""
上下文单元模块

定义语义化的上下文单元，用于组织和管理对话历史。
每个单元代表一段语义连贯的对话，包含主题、摘要和关键词。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid


@dataclass
class ContextUnit:
    """
    上下文单元：一段语义连贯的对话
    
    类比：一个"章节"或"话题"
    
    Attributes:
        unit_id: 唯一标识符
        topic: 主题（如："文件保存路径设置"）
        summary: 摘要（如："用户指定将文件保存到 output/ 目录"）
        messages: 原始对话消息列表
        keywords: 关键词列表
        timestamp: 创建时间
        embedding: 可选的向量化表示（用于语义检索）
    """
    unit_id: str
    topic: str
    summary: str
    messages: List[Dict[str, str]]
    keywords: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    embedding: Optional[List[float]] = None
    
    @classmethod
    def create(
        cls,
        topic: str,
        summary: str,
        messages: List[Dict[str, str]],
        keywords: List[str],
        embedding: Optional[List[float]] = None
    ) -> "ContextUnit":
        """
        工厂方法：创建新的上下文单元
        """
        return cls(
            unit_id=f"unit_{uuid.uuid4().hex[:8]}",
            topic=topic,
            summary=summary,
            messages=messages,
            keywords=keywords[:10],  # 保留前 10 个关键词
            timestamp=datetime.now(),
            embedding=embedding
        )
    
    def to_context_string(self) -> str:
        """
        转换为简洁的上下文字符串（用于 Prompt）
        
        Returns:
            格式化的上下文字符串
        """
        return f"【{self.topic}】{self.summary}"
    
    def to_full_string(self) -> str:
        """
        完整内容（包含原始对话）
        
        Returns:
            包含所有对话内容的完整字符串
        """
        lines = [f"## {self.topic}", f"摘要: {self.summary}", ""]
        for msg in self.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于序列化）
        """
        return {
            "unit_id": self.unit_id,
            "topic": self.topic,
            "summary": self.summary,
            "messages": self.messages,
            "keywords": self.keywords,
            "timestamp": self.timestamp.isoformat(),
            "embedding": self.embedding
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextUnit":
        """
        从字典创建（用于反序列化）
        """
        return cls(
            unit_id=data["unit_id"],
            topic=data["topic"],
            summary=data["summary"],
            messages=data["messages"],
            keywords=data["keywords"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            embedding=data.get("embedding")
        )
    
    def get_token_estimate(self) -> int:
        """
        估算 Token 数量（用于上下文管理）
        
        简化实现：假设平均每 4 个字符 = 1 个 Token
        """
        full_text = self.to_full_string()
        return len(full_text) // 4
    
    def get_summary_token_estimate(self) -> int:
        """
        估算摘要的 Token 数量
        """
        summary_text = self.to_context_string()
        return len(summary_text) // 4
