from datetime import datetime
from typing import Optional
from enum import Enum


class TransactionType(Enum):
    """交易类型枚举"""
    INCOME = "income"  # 收入
    EXPENSE = "expense"  # 支出


class Transaction:
    """交易数据模型类
    
    用于记录财务交易信息，包括收入、支出等
    """
    
    def __init__(
        self,
        id: str,
        date: datetime,
        type: TransactionType,
        amount: float,
        category: str,
        description: Optional[str] = None
    ):
        """初始化交易对象
        
        Args:
            id: 交易唯一标识
            date: 交易日期时间
            type: 交易类型，income(收入)或expense(支出)
            amount: 交易金额
            category: 交易分类
            description: 交易描述，可选
        """
        self.id = id
        self.date = date
        self.type = type
        self.amount = amount
        self.category = category
        self.description = description
    
    def to_dict(self) -> dict:
        """将交易对象转换为字典格式
        
        Returns:
            包含交易所有属性的字典
        """
        return {
            "id": self.id,
            "date": self.date.isoformat() if isinstance(self.date, datetime) else self.date,
            "type": self.type.value,
            "amount": self.amount,
            "category": self.category,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Transaction':
        """从字典创建交易对象
        
        Args:
            data: 包含交易数据的字典
            
        Returns:
            交易对象实例
        """
        # 处理日期字段
        date_value = data.get('date')
        if isinstance(date_value, str):
            date = datetime.fromisoformat(date_value)
        else:
            date = date_value
        
        # 处理交易类型字段
        type_value = data.get('type')
        if isinstance(type_value, str):
            transaction_type = TransactionType(type_value)
        else:
            transaction_type = type_value
        
        return cls(
            id=data.get('id'),
            date=date,
            type=transaction_type,
            amount=data.get('amount', 0.0),
            category=data.get('category', ''),
            description=data.get('description')
        )
    
    def __repr__(self) -> str:
        """返回交易对象的字符串表示"""
        return (
            f"Transaction(id='{self.id}', "
            f"date={self.date}, "
            f"type={self.type.value}, "
            f"amount={self.amount}, "
            f"category='{self.category}', "
            f"description='{self.description}')"
        )
    
    def __str__(self) -> str:
        """返回交易对象的友好字符串表示"""
        type_str = "收入" if self.type == TransactionType.INCOME else "支出"
        desc = f" - {self.description}" if self.description else ""
        return f"[{self.date.strftime('%Y-%m-%d')}] {type_str}: {self.amount}元 ({self.category}){desc}"
    
    @property
    def is_income(self) -> bool:
        """判断是否为收入交易"""
        return self.type == TransactionType.INCOME
    
    @property
    def is_expense(self) -> bool:
        """判断是否为支出交易"""
        return self.type == TransactionType.EXPENSE
    
    def get_formatted_amount(self) -> str:
        """获取格式化后的金额字符串"""
        prefix = "+" if self.is_income else "-"
        return f"{prefix}{self.amount:.2f}"
