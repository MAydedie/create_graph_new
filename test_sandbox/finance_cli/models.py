from datetime import datetime
from typing import List, Optional
from enum import Enum


class TransactionType(Enum):
    """交易类型枚举"""
    INCOME = "income"  # 收入
    EXPENSE = "expense"  # 支出


class Transaction:
    """交易数据类
    
    表示一笔具体的收入或支出交易
    """
    
    def __init__(self, 
                 transaction_id: str,
                 transaction_type: TransactionType,
                 amount: float,
                 description: str,
                 date: datetime,
                 category: Optional[str] = None,
                 tags: Optional[List[str]] = None):
        """初始化交易对象
        
        Args:
            transaction_id: 交易唯一标识
            transaction_type: 交易类型（收入/支出）
            amount: 交易金额
            description: 交易描述
            date: 交易日期
            category: 交易分类（可选）
            tags: 交易标签（可选）
        """
        self.id = transaction_id
        self.type = transaction_type
        self.amount = amount
        self.description = description
        self.date = date
        self.category = category
        self.tags = tags or []
    
    def to_dict(self) -> dict:
        """将交易对象转换为字典格式"""
        return {
            "id": self.id,
            "type": self.type.value,
            "amount": self.amount,
            "description": self.description,
            "date": self.date.isoformat(),
            "category": self.category,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Transaction':
        """从字典创建交易对象"""
        return cls(
            transaction_id=data["id"],
            transaction_type=TransactionType(data["type"]),
            amount=data["amount"],
            description=data["description"],
            date=datetime.fromisoformat(data["date"]),
            category=data.get("category"),
            tags=data.get("tags", [])
        )
    
    def __repr__(self) -> str:
        """返回交易对象的字符串表示"""
        return f"Transaction(id='{self.id}', type={self.type.value}, amount={self.amount}, date={self.date.strftime('%Y-%m-%d')})"


class Ledger:
    """账本类
    
    作为交易集合的包装类，提供交易管理和统计功能
    """
    
    def __init__(self, name: str = "默认账本"):
        """初始化账本
        
        Args:
            name: 账本名称
        """
        self.name = name
        self.transactions: List[Transaction] = []
    
    def add_transaction(self, transaction: Transaction) -> None:
        """添加交易到账本"""
        self.transactions.append(transaction)
    
    def remove_transaction(self, transaction_id: str) -> bool:
        """根据ID移除交易
        
        Returns:
            bool: 是否成功移除
        """
        for i, transaction in enumerate(self.transactions):
            if transaction.id == transaction_id:
                self.transactions.pop(i)
                return True
        return False
    
    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """根据ID获取交易"""
        for transaction in self.transactions:
            if transaction.id == transaction_id:
                return transaction
        return None
    
    def get_all_transactions(self) -> List[Transaction]:
        """获取所有交易"""
        return self.transactions.copy()
    
    def filter_by_type(self, transaction_type: TransactionType) -> List[Transaction]:
        """根据交易类型筛选交易"""
        return [t for t in self.transactions if t.type == transaction_type]
    
    def filter_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Transaction]:
        """根据日期范围筛选交易"""
        return [t for t in self.transactions if start_date <= t.date <= end_date]
    
    def calculate_balance(self) -> float:
        """计算账本余额（总收入 - 总支出）"""
        total_income = sum(t.amount for t in self.transactions if t.type == TransactionType.INCOME)
        total_expense = sum(t.amount for t in self.transactions if t.type == TransactionType.EXPENSE)
        return total_income - total_expense
    
    def calculate_total_income(self) -> float:
        """计算总收入"""
        return sum(t.amount for t in self.transactions if t.type == TransactionType.INCOME)
    
    def calculate_total_expense(self) -> float:
        """计算总支出"""
        return sum(t.amount for t in self.transactions if t.type == TransactionType.EXPENSE)
    
    def get_transactions_by_category(self) -> dict:
        """按分类统计交易"""
        result = {}
        for transaction in self.transactions:
            category = transaction.category or "未分类"
            if category not in result:
                result[category] = []
            result[category].append(transaction)
        return result
    
    def to_dict(self) -> dict:
        """将账本对象转换为字典格式"""
        return {
            "name": self.name,
            "transactions": [t.to_dict() for t in self.transactions]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Ledger':
        """从字典创建账本对象"""
        ledger = cls(name=data["name"])
        for transaction_data in data["transactions"]:
            ledger.add_transaction(Transaction.from_dict(transaction_data))
        return ledger
    
    def __len__(self) -> int:
        """返回交易数量"""
        return len(self.transactions)
    
    def __repr__(self) -> str:
        """返回账本对象的字符串表示"""
        return f"Ledger(name='{self.name}', transactions={len(self.transactions)})"


# 示例使用代码
if __name__ == "__main__":
    # 创建账本
    ledger = Ledger("我的个人账本")
    
    # 添加一些示例交易
    ledger.add_transaction(Transaction(
        transaction_id="1",
        transaction_type=TransactionType.INCOME,
        amount=5000.00,
        description="工资收入",
        date=datetime(2024, 1, 15),
        category="工资",
        tags=["工资", "月度"]
    ))
    
    ledger.add_transaction(Transaction(
        transaction_id="2",
        transaction_type=TransactionType.EXPENSE,
        amount=1500.00,
        description="房租支出",
        date=datetime(2024, 1, 10),
        category="住房",
        tags=["房租", "月度"]
    ))
    
    # 打印账本信息
    print(f"账本名称: {ledger.name}")
    print(f"交易数量: {len(ledger)}")
    print(f"总收入: {ledger.calculate_total_income():.2f}")
    print(f"总支出: {ledger.calculate_total_expense():.2f}")
    print(f"余额: {ledger.calculate_balance():.2f}")
    
    # 按分类统计
    by_category = ledger.get_transactions_by_category()
    print("\n按分类统计:")
    for category, transactions in by_category.items():
        print(f"  {category}: {len(transactions)}笔交易")
