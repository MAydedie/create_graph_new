#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心业务逻辑层

实现FinanceManager类，提供高层API封装业务规则
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


class FinanceManager:
    """财务管理核心类，封装业务规则和高层API"""
    
    def __init__(self, storage):
        """
        初始化FinanceManager
        
        Args:
            storage: Storage类实例，用于数据持久化
        """
        self.storage = storage
        
    def add_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        添加交易记录
        
        Args:
            transaction_data: 交易数据，包含以下字段：
                - amount: 金额（浮点数）
                - type: 类型（'income'收入/'expense'支出）
                - category: 分类
                - description: 描述
                - date: 日期（可选，默认为当前日期）
                
        Returns:
            添加后的完整交易记录
        """
        # 验证必要字段
        required_fields = ['amount', 'type', 'category', 'description']
        for field in required_fields:
            if field not in transaction_data:
                raise ValueError(f"缺少必要字段: {field}")
        
        # 验证金额类型
        if not isinstance(transaction_data['amount'], (int, float)):
            raise ValueError("金额必须是数字类型")
        
        # 验证交易类型
        if transaction_data['type'] not in ['income', 'expense']:
            raise ValueError("交易类型必须是 'income' 或 'expense'")
        
        # 设置默认日期
        if 'date' not in transaction_data:
            transaction_data['date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 生成交易ID
        transaction_data['id'] = self._generate_transaction_id()
        
        # 保存到存储
        self.storage.save_transaction(transaction_data)
        
        return transaction_data
    
    def get_balance(self) -> float:
        """
        计算当前余额
        
        Returns:
            当前余额（总收入 - 总支出）
        """
        transactions = self.storage.get_all_transactions()
        
        balance = 0.0
        for transaction in transactions:
            if transaction['type'] == 'income':
                balance += transaction['amount']
            elif transaction['type'] == 'expense':
                balance -= transaction['amount']
        
        return round(balance, 2)
    
    def list_transactions(self, 
                         start_date: Optional[str] = None,
                         end_date: Optional[str] = None,
                         category: Optional[str] = None,
                         transaction_type: Optional[str] = None,
                         limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        列出交易记录，支持过滤和分页
        
        Args:
            start_date: 开始日期（格式: YYYY-MM-DD）
            end_date: 结束日期（格式: YYYY-MM-DD）
            category: 分类过滤
            transaction_type: 类型过滤（'income'/'expense'）
            limit: 返回记录数量限制
            
        Returns:
            过滤后的交易记录列表
        """
        transactions = self.storage.get_all_transactions()
        
        # 应用过滤器
        filtered_transactions = []
        
        for transaction in transactions:
            # 日期过滤
            if start_date:
                if transaction['date'] < start_date:
                    continue
            if end_date:
                if transaction['date'] > end_date:
                    continue
                    
            # 分类过滤
            if category and transaction['category'] != category:
                continue
                
            # 类型过滤
            if transaction_type and transaction['type'] != transaction_type:
                continue
                
            filtered_transactions.append(transaction)
        
        # 按日期倒序排序（最新的在前）
        filtered_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        # 应用数量限制
        if limit and limit > 0:
            filtered_transactions = filtered_transactions[:limit]
        
        return filtered_transactions
    
    def get_transaction_summary(self, 
                               start_date: Optional[str] = None,
                               end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取交易摘要统计
        
        Args:
            start_date: 开始日期（格式: YYYY-MM-DD）
            end_date: 结束日期（格式: YYYY-MM-DD）
            
        Returns:
            包含统计信息的字典：
                - total_income: 总收入
                - total_expense: 总支出
                - net_balance: 净余额
                - transaction_count: 交易数量
                - by_category: 按分类统计
        """
        transactions = self.list_transactions(start_date, end_date)
        
        summary = {
            'total_income': 0.0,
            'total_expense': 0.0,
            'net_balance': 0.0,
            'transaction_count': len(transactions),
            'by_category': {}
        }
        
        for transaction in transactions:
            amount = transaction['amount']
            category = transaction['category']
            transaction_type = transaction['type']
            
            # 统计总收入/支出
            if transaction_type == 'income':
                summary['total_income'] += amount
                summary['net_balance'] += amount
            else:
                summary['total_expense'] += amount
                summary['net_balance'] -= amount
            
            # 按分类统计
            if category not in summary['by_category']:
                summary['by_category'][category] = {
                    'income': 0.0,
                    'expense': 0.0,
                    'count': 0
                }
            
            summary['by_category'][category][transaction_type] += amount
            summary['by_category'][category]['count'] += 1
        
        # 四舍五入
        summary['total_income'] = round(summary['total_income'], 2)
        summary['total_expense'] = round(summary['total_expense'], 2)
        summary['net_balance'] = round(summary['net_balance'], 2)
        
        # 对分类统计进行四舍五入
        for category in summary['by_category']:
            summary['by_category'][category]['income'] = round(summary['by_category'][category]['income'], 2)
            summary['by_category'][category]['expense'] = round(summary['by_category'][category]['expense'], 2)
        
        return summary
    
    def delete_transaction(self, transaction_id: str) -> bool:
        """
        删除指定交易记录
        
        Args:
            transaction_id: 交易ID
            
        Returns:
            是否删除成功
        """
        return self.storage.delete_transaction(transaction_id)
    
    def update_transaction(self, transaction_id: str, 
                          update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        更新交易记录
        
        Args:
            transaction_id: 交易ID
            update_data: 要更新的数据
            
        Returns:
            更新后的交易记录，如果不存在则返回None
        """
        # 获取现有交易记录
        transaction = self.storage.get_transaction(transaction_id)
        if not transaction:
            return None
        
        # 更新字段
        for key, value in update_data.items():
            if key in transaction and key != 'id':  # 不允许修改ID
                transaction[key] = value
        
        # 保存更新
        self.storage.update_transaction(transaction_id, transaction)
        
        return transaction
    
    def export_transactions(self, 
                           format: str = 'list',
                           fields: Optional[List[str]] = None,
                           template_name: Optional[str] = None) -> Any:
        """
        导出交易记录
        
        Args:
            format: 导出格式（'list'列表/'table'表格）
            fields: 要导出的字段列表，如果为None则使用默认字段
            template_name: 模板名称，用于加载预定义的字段配置
            
        Returns:
            导出数据
        """
        # 获取所有交易记录
        transactions = self.storage.get_all_transactions()
        
        # 如果没有指定字段，使用默认字段
        if not fields:
            fields = ['id', 'date', 'type', 'category', 'amount', 'description']
        
        # 如果指定了模板名称，可以加载预定义的字段配置
        # 这里预留接口，实际实现需要Storage支持模板管理
        if template_name:
            # 可以调用 storage.get_template(template_name) 获取模板配置
            pass
        
        # 按指定字段提取数据
        exported_data = []
        for transaction in transactions:
            item = {}
            for field in fields:
                if field in transaction:
                    item[field] = transaction[field]
                else:
                    item[field] = None
            exported_data.append(item)
        
        # 根据格式返回不同结构的数据
        if format == 'table':
            # 表格格式：返回字段名和数据行
            return {
                'fields': fields,
                'data': exported_data
            }
        else:
            # 列表格式：直接返回数据列表
            return exported_data
    
    def _generate_transaction_id(self) -> str:
        """
        生成交易ID
        
        Returns:
            唯一的交易ID字符串
        """
        import uuid
        import time
        
        # 使用UUID和时间戳组合生成唯一ID
        timestamp = int(time.time() * 1000)
        unique_id = str(uuid.uuid4())[:8]
        
        return f"TRX_{timestamp}_{unique_id}"


# 示例使用
if __name__ == "__main__":
    # 这里需要先实现Storage类
    class MockStorage:
        def __init__(self):
            self.transactions = []
            
        def save_transaction(self, transaction):
            self.transactions.append(transaction)
            
        def get_all_transactions(self):
            return self.transactions
            
        def get_transaction(self, transaction_id):
            for t in self.transactions:
                if t.get('id') == transaction_id:
                    return t
            return None
            
        def delete_transaction(self, transaction_id):
            for i, t in enumerate(self.transactions):
                if t.get('id') == transaction_id:
                    del self.transactions[i]
                    return True
            return False
            
        def update_transaction(self, transaction_id, transaction_data):
            for i, t in enumerate(self.transactions):
                if t.get('id') == transaction_id:
                    self.transactions[i] = transaction_data
                    return True
            return False
    
    # 创建FinanceManager实例
    storage = MockStorage()
    manager = FinanceManager(storage)
    
    # 测试添加交易
    transaction1 = manager.add_transaction({
        'amount': 1000.0,
        'type': 'income',
        'category': '工资',
        'description': '月薪'
    })
    
    transaction2 = manager.add_transaction({
        'amount': 200.0,
        'type': 'expense',
        'category': '餐饮',
        'description': '晚餐'
    })
    
    # 测试获取余额
    balance = manager.get_balance()
    print(f"当前余额: {balance}")  # 应该输出 800.0
    
    # 测试列出交易
    transactions = manager.list_transactions()
    print(f"交易数量: {len(transactions)}")
    
    # 测试获取摘要
    summary = manager.get_transaction_summary()
    print(f"总收入: {summary['total_income']}")
    print(f"总支出: {summary['total_expense']}")
    
    # 测试导出
    exported = manager.export_transactions(format='table')
    print(f"导出字段: {exported['fields']}")
    print(f"导出数据行数: {len(exported['data'])}")