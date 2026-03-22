from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional
from decimal import Decimal

from storage import Storage


@dataclass
class Transaction:
    """交易数据类
    
    Attributes:
        id: 交易唯一标识
        date: 交易日期
        type: 交易类型（收入/支出）
        category: 交易类别
        amount: 交易金额
        description: 交易描述
    """
    id: str
    date: date
    type: str  # 'income' 或 'expense'
    category: str
    amount: Decimal
    description: str = ""
    
    def to_dict(self) -> dict:
        """将交易对象转换为字典格式，便于存储"""
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'type': self.type,
            'category': self.category,
            'amount': str(self.amount),
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Transaction':
        """从字典创建交易对象"""
        return cls(
            id=data['id'],
            date=date.fromisoformat(data['date']),
            type=data['type'],
            category=data['category'],
            amount=Decimal(data['amount']),
            description=data.get('description', '')
        )


class Ledger:
    """账本类，管理交易记录和业务逻辑
    
    Attributes:
        transactions: 交易列表
        storage: 存储对象，用于数据持久化
    """
    
    def __init__(self, storage: Storage):
        """初始化账本
        
        Args:
            storage: 存储对象，负责数据的加载和保存
        """
        self.storage = storage
        self.transactions: List[Transaction] = []
        self._load_transactions()
    
    def _load_transactions(self):
        """从存储中加载交易数据"""
        try:
            data = self.storage.load()
            if data and 'transactions' in data:
                self.transactions = [
                    Transaction.from_dict(tx_data) 
                    for tx_data in data['transactions']
                ]
        except Exception as e:
            print(f"加载交易数据失败: {e}")
            self.transactions = []
    
    def _save_transactions(self):
        """保存交易数据到存储"""
        try:
            data = {
                'transactions': [tx.to_dict() for tx in self.transactions]
            }
            self.storage.save(data)
        except Exception as e:
            print(f"保存交易数据失败: {e}")
    
    def add_transaction(self, transaction: Transaction) -> bool:
        """添加交易记录
        
        Args:
            transaction: 交易对象
            
        Returns:
            bool: 添加是否成功
        """
        # 检查ID是否已存在
        if any(tx.id == transaction.id for tx in self.transactions):
            print(f"交易ID {transaction.id} 已存在")
            return False
        
        self.transactions.append(transaction)
        self._save_transactions()
        return True
    
    def remove_transaction(self, transaction_id: str) -> bool:
        """删除交易记录
        
        Args:
            transaction_id: 交易ID
            
        Returns:
            bool: 删除是否成功
        """
        initial_count = len(self.transactions)
        self.transactions = [
            tx for tx in self.transactions if tx.id != transaction_id
        ]
        
        if len(self.transactions) < initial_count:
            self._save_transactions()
            return True
        return False
    
    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """根据ID获取交易记录
        
        Args:
            transaction_id: 交易ID
            
        Returns:
            Optional[Transaction]: 交易对象，如果不存在则返回None
        """
        for transaction in self.transactions:
            if transaction.id == transaction_id:
                return transaction
        return None
    
    def get_all_transactions(self) -> List[Transaction]:
        """获取所有交易记录
        
        Returns:
            List[Transaction]: 交易列表
        """
        return self.transactions.copy()
    
    def get_transactions_by_date_range(self, start_date: date, end_date: date) -> List[Transaction]:
        """根据日期范围获取交易记录
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            List[Transaction]: 符合条件的交易列表
        """
        return [
            tx for tx in self.transactions 
            if start_date <= tx.date <= end_date
        ]
    
    def get_transactions_by_category(self, category: str) -> List[Transaction]:
        """根据类别获取交易记录
        
        Args:
            category: 交易类别
            
        Returns:
            List[Transaction]: 符合条件的交易列表
        """
        return [tx for tx in self.transactions if tx.category == category]
    
    def get_transactions_by_type(self, transaction_type: str) -> List[Transaction]:
        """根据类型获取交易记录
        
        Args:
            transaction_type: 交易类型（'income' 或 'expense'）
            
        Returns:
            List[Transaction]: 符合条件的交易列表
        """
        return [tx for tx in self.transactions if tx.type == transaction_type]
    
    def calculate_balance(self) -> Decimal:
        """计算当前余额
        
        Returns:
            Decimal: 余额（总收入 - 总支出）
        """
        total_income = Decimal('0')
        total_expense = Decimal('0')
        
        for transaction in self.transactions:
            if transaction.type == 'income':
                total_income += transaction.amount
            elif transaction.type == 'expense':
                total_expense += transaction.amount
        
        return total_income - total_expense
    
    def calculate_income_total(self) -> Decimal:
        """计算总收入
        
        Returns:
            Decimal: 总收入金额
        """
        return sum(
            tx.amount for tx in self.transactions 
            if tx.type == 'income'
        )
    
    def calculate_expense_total(self) -> Decimal:
        """计算总支出
        
        Returns:
            Decimal: 总支出金额
        """
        return sum(
            tx.amount for tx in self.transactions 
            if tx.type == 'expense'
        )
    
    def get_categories(self) -> List[str]:
        """获取所有交易类别
        
        Returns:
            List[str]: 类别列表（去重）
        """
        return list(set(tx.category for tx in self.transactions))
    
    def clear_all(self) -> bool:
        """清空所有交易记录
        
        Returns:
            bool: 清空是否成功
        """
        self.transactions.clear()
        try:
            self._save_transactions()
            return True
        except Exception as e:
            print(f"清空交易记录失败: {e}")
            return False
