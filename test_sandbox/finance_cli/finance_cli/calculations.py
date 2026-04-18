#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融计算核心模块

提供常用的金融计算函数，包括：
- 未来价值 (Future Value, FV)
- 现值 (Present Value, PV)
- 贷款月供 (Loan Payment)
- 内部收益率 (Internal Rate of Return, IRR)
- 净现值 (Net Present Value, NPV)
- 投资回报率 (Return on Investment, ROI)
- 年化收益率 (Annualized Return)
"""

import math
from typing import List, Optional


def future_value(pv: float, rate: float, periods: int) -> float:
    """
    计算未来价值 (Future Value)
    
    公式: FV = PV × (1 + r)^n
    
    Args:
        pv: 现值 (Present Value)
        rate: 每期利率 (如年利率0.05表示5%)
        periods: 期数
        
    Returns:
        未来价值
    """
    return pv * ((1 + rate) ** periods)


def present_value(fv: float, rate: float, periods: int) -> float:
    """
    计算现值 (Present Value)
    
    公式: PV = FV / (1 + r)^n
    
    Args:
        fv: 未来价值 (Future Value)
        rate: 每期利率 (如年利率0.05表示5%)
        periods: 期数
        
    Returns:
        现值
    """
    return fv / ((1 + rate) ** periods)


def loan_payment(principal: float, annual_rate: float, years: int, 
                  payments_per_year: int = 12) -> float:
    """
    计算贷款每期还款额 (等额本息)
    
    公式: PMT = P × [r(1+r)^n] / [(1+r)^n - 1]
    
    Args:
        principal: 贷款本金
        annual_rate: 年利率 (如0.05表示5%)
        years: 贷款年限
        payments_per_year: 每年还款次数，默认为12(月供)
        
    Returns:
        每期还款金额
    """
    # 计算每期利率
    period_rate = annual_rate / payments_per_year
    # 计算总期数
    total_periods = years * payments_per_year
    
    # 等额本息公式
    if period_rate == 0:
        return principal / total_periods
    
    numerator = period_rate * ((1 + period_rate) ** total_periods)
    denominator = ((1 + period_rate) ** total_periods) - 1
    
    return principal * (numerator / denominator)


def net_present_value(cash_flows: List[float], discount_rate: float) -> float:
    """
    计算净现值 (Net Present Value)
    
    Args:
        cash_flows: 现金流列表，第一个元素通常是初始投资(负数)
        discount_rate: 贴现率
        
    Returns:
        净现值
    """
    npv = 0.0
    for i, cash_flow in enumerate(cash_flows):
        npv += cash_flow / ((1 + discount_rate) ** i)
    return npv


def internal_rate_of_return(cash_flows: List[float], 
                           max_iterations: int = 1000, 
                           tolerance: float = 1e-6) -> Optional[float]:
    """
    计算内部收益率 (Internal Rate of Return) 使用牛顿法
    
    Args:
        cash_flows: 现金流列表
        max_iterations: 最大迭代次数
        tolerance: 容差
        
    Returns:
        内部收益率，如果无法计算则返回None
    """
    if len(cash_flows) < 2:
        return None
    
    # 初始猜测值
    x0 = 0.1  # 10%
    
    for _ in range(max_iterations):
        # 计算NPV和NPV的导数
        npv = 0.0
        d_npv = 0.0
        
        for t, cf in enumerate(cash_flows):
            discount_factor = (1 + x0) ** t
            npv += cf / discount_factor
            if t > 0:  # t=0时导数为0
                d_npv -= t * cf / ((1 + x0) ** (t + 1))
        
        # 牛顿法更新公式: x1 = x0 - f(x0)/f'(x0)
        if abs(d_npv) < tolerance:
            break
            
        x1 = x0 - npv / d_npv
        
        # 检查收敛
        if abs(x1 - x0) < tolerance:
            return x1
            
        x0 = x1
    
    return None


def return_on_investment(initial_investment: float, final_value: float) -> float:
    """
    计算投资回报率 (Return on Investment)
    
    公式: ROI = (最终价值 - 初始投资) / 初始投资
    
    Args:
        initial_investment: 初始投资额
        final_value: 最终价值
        
    Returns:
        投资回报率 (小数形式)
    """
    if initial_investment == 0:
        return 0.0
    return (final_value - initial_investment) / initial_investment


def annualized_return(initial_value: float, final_value: float, years: float) -> float:
    """
    计算年化收益率
    
    公式: 年化收益率 = (最终价值/初始价值)^(1/年数) - 1
    
    Args:
        initial_value: 初始价值
        final_value: 最终价值
        years: 投资年数
        
    Returns:
        年化收益率 (小数形式)
    """
    if initial_value <= 0 or years <= 0:
        return 0.0
    
    return (final_value / initial_value) ** (1 / years) - 1


def compound_interest(principal: float, rate: float, years: int, 
                     compounding_per_year: int = 1) -> float:
    """
    计算复利
    
    公式: A = P(1 + r/n)^(nt)
    
    Args:
        principal: 本金
        rate: 年利率
        years: 年数
        compounding_per_year: 每年复利次数
        
    Returns:
        复利后的总金额
    """
    return principal * (1 + rate / compounding_per_year) ** (compounding_per_year * years)


def rule_of_72(rate: float) -> float:
    """
    72法则：估算投资翻倍所需年数
    
    公式: 年数 ≈ 72 / 年利率百分比
    
    Args:
        rate: 年利率 (小数形式)
        
    Returns:
        翻倍所需的大致年数
    """
    if rate <= 0:
        return float('inf')
    return 72 / (rate * 100)


def effective_annual_rate(nominal_rate: float, compounding_per_year: int) -> float:
    """
    计算有效年利率 (Effective Annual Rate)
    
    公式: EAR = (1 + r/n)^n - 1
    
    Args:
        nominal_rate: 名义年利率
        compounding_per_year: 每年复利次数
        
    Returns:
        有效年利率
    """
    return (1 + nominal_rate / compounding_per_year) ** compounding_per_year - 1


# 测试代码
if __name__ == "__main__":
    # 测试未来价值
    print("测试未来价值:")
    fv = future_value(1000, 0.05, 10)
    print(f"现值1000，年利率5%，10年后的未来价值: {fv:.2f}")
    
    # 测试现值
    print("\n测试现值:")
    pv = present_value(1628.89, 0.05, 10)
    print(f"未来价值1628.89，年利率5%，10年后的现值: {pv:.2f}")
    
    # 测试贷款月供
    print("\n测试贷款月供:")
    payment = loan_payment(100000, 0.05, 20)
    print(f"贷款10万，年利率5%，20年，月供: {payment:.2f}")
    
    # 测试净现值
    print("\n测试净现值:")
    cash_flows = [-1000, 300, 300, 300, 300]
    npv = net_present_value(cash_flows, 0.1)
    print(f"现金流{ cash_flows }，贴现率10%，净现值: {npv:.2f}")
    
    # 测试投资回报率
    print("\n测试投资回报率:")
    roi = return_on_investment(1000, 1500)
    print(f"初始投资1000，最终价值1500，投资回报率: {roi:.2%}")
    
    # 测试年化收益率
    print("\n测试年化收益率:")
    annual_return = annualized_return(1000, 2000, 5)
    print(f"初始1000，最终2000，5年，年化收益率: {annual_return:.2%}")
    
    # 测试72法则
    print("\n测试72法则:")
    doubling_years = rule_of_72(0.08)
    print(f"年利率8%，翻倍所需年数: {doubling_years:.1f}年")
