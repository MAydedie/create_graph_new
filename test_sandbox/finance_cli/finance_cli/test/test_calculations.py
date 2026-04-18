#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calculations.py 单元测试

测试金融计算核心模块的所有函数
"""

import unittest
import math
from typing import List

# 导入被测试模块
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from finance_cli.calculations import (
    future_value,
    present_value,
    loan_payment,
    net_present_value,
    internal_rate_of_return,
    return_on_investment,
    annualized_return
)


class TestFutureValue(unittest.TestCase):
    """测试未来价值计算函数"""
    
    def test_basic_future_value(self):
        """测试基本未来价值计算"""
        # 现值1000，年利率5%，投资10年
        result = future_value(1000, 0.05, 10)
        expected = 1000 * (1.05 ** 10)
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_zero_rate(self):
        """测试零利率情况"""
        result = future_value(1000, 0, 10)
        self.assertEqual(result, 1000)
    
    def test_negative_rate(self):
        """测试负利率情况"""
        result = future_value(1000, -0.02, 5)
        expected = 1000 * (0.98 ** 5)
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_zero_periods(self):
        """测试零期数情况"""
        result = future_value(1000, 0.05, 0)
        self.assertEqual(result, 1000)


class TestPresentValue(unittest.TestCase):
    """测试现值计算函数"""
    
    def test_basic_present_value(self):
        """测试基本现值计算"""
        # 未来价值1628.89，年利率5%，10年
        fv = 1000 * (1.05 ** 10)
        result = present_value(fv, 0.05, 10)
        self.assertAlmostEqual(result, 1000, places=2)
    
    def test_zero_rate(self):
        """测试零利率情况"""
        result = present_value(1000, 0, 10)
        self.assertEqual(result, 1000)
    
    def test_high_rate(self):
        """测试高利率情况"""
        result = present_value(1000, 0.20, 5)
        expected = 1000 / (1.20 ** 5)
        self.assertAlmostEqual(result, expected, places=2)


class TestLoanPayment(unittest.TestCase):
    """测试贷款还款计算函数"""
    
    def test_basic_loan_payment(self):
        """测试基本贷款月供计算"""
        # 贷款10万，年利率5%，20年，月供
        result = loan_payment(100000, 0.05, 20, 12)
        # 手动计算验证
        period_rate = 0.05 / 12
        total_periods = 20 * 12
        numerator = period_rate * ((1 + period_rate) ** total_periods)
        denominator = ((1 + period_rate) ** total_periods) - 1
        expected = 100000 * (numerator / denominator)
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_zero_interest_loan(self):
        """测试零利率贷款"""
        result = loan_payment(12000, 0, 1, 12)
        # 零利率时，每月还款 = 本金 / 总期数
        self.assertAlmostEqual(result, 1000, places=2)
    
    def test_quarterly_payments(self):
        """测试季度还款"""
        result = loan_payment(100000, 0.06, 10, 4)
        period_rate = 0.06 / 4
        total_periods = 10 * 4
        numerator = period_rate * ((1 + period_rate) ** total_periods)
        denominator = ((1 + period_rate) ** total_periods) - 1
        expected = 100000 * (numerator / denominator)
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_one_year_loan(self):
        """测试一年期贷款"""
        result = loan_payment(12000, 0.12, 1, 12)
        # 验证结果合理性
        self.assertGreater(result, 1000)  # 应大于零利率时的1000
        self.assertLess(result, 1100)     # 应小于某个合理上限


class TestNetPresentValue(unittest.TestCase):
    """测试净现值计算函数"""
    
    def test_basic_npv(self):
        """测试基本NPV计算"""
        cash_flows = [-1000, 300, 300, 300, 300]
        result = net_present_value(cash_flows, 0.1)
        # 手动计算
        expected = -1000 + 300/1.1 + 300/(1.1**2) + 300/(1.1**3) + 300/(1.1**4)
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_positive_npv(self):
        """测试正NPV情况"""
        cash_flows = [-1000, 500, 500, 500]
        result = net_present_value(cash_flows, 0.1)
        self.assertGreater(result, 0)
    
    def test_negative_npv(self):
        """测试负NPV情况"""
        cash_flows = [-1000, 200, 200, 200]
        result = net_present_value(cash_flows, 0.1)
        self.assertLess(result, 0)
    
    def test_zero_discount_rate(self):
        """测试零贴现率"""
        cash_flows = [-1000, 400, 400, 400]
        result = net_present_value(cash_flows, 0)
        expected = sum(cash_flows)
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_single_cash_flow(self):
        """测试单笔现金流"""
        cash_flows = [-1000]
        result = net_present_value(cash_flows, 0.1)
        self.assertEqual(result, -1000)


class TestInternalRateOfReturn(unittest.TestCase):
    """测试内部收益率计算函数"""
    
    def test_basic_irr(self):
        """测试基本IRR计算"""
        cash_flows = [-1000, 300, 300, 300, 300]
        result = internal_rate_of_return(cash_flows)
        # IRR应该使NPV=0
        if result is not None:
            npv = net_present_value(cash_flows, result)
            self.assertAlmostEqual(npv, 0, places=4)
    
    def test_irr_with_high_return(self):
        """测试高回报率的IRR"""
        cash_flows = [-1000, 1500]
        result = internal_rate_of_return(cash_flows)
        # 一年期，从-1000到1500，IRR应为0.5
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.5, places=2)
    
    def test_irr_with_loss(self):
        """测试亏损项目的IRR"""
        cash_flows = [-1000, 800]
        result = internal_rate_of_return(cash_flows)
        self.assertIsNotNone(result)
        self.assertLess(result, 0)  # 应为负值
    
    def test_insufficient_cash_flows(self):
        """测试现金流不足的情况"""
        cash_flows = [1000]
        result = internal_rate_of_return(cash_flows)
        self.assertIsNone(result)
    
    def test_all_positive_cash_flows(self):
        """测试全部为正的现金流"""
        cash_flows = [100, 200, 300]
        result = internal_rate_of_return(cash_flows)
        # 全部为正的现金流，IRR可能无法计算或为负
        # 这里主要测试函数不崩溃
        self.assertTrue(result is None or isinstance(result, float))


class TestReturnOnInvestment(unittest.TestCase):
    """测试投资回报率计算函数"""
    
    def test_positive_roi(self):
        """测试正ROI"""
        result = return_on_investment(1000, 1500)
        expected = (1500 - 1000) / 1000
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_negative_roi(self):
        """测试负ROI"""
        result = return_on_investment(1000, 800)
        expected = (800 - 1000) / 1000
        self.assertAlmostEqual(result, expected, places=2)
    
    def test_zero_roi(self):
        """测试零ROI"""
        result = return_on_investment(1000, 1000)
        self.assertEqual(result, 0)
    
    def test_zero_initial_investment(self):
        """测试零初始投资"""
        result = return_on_investment(0, 1000)
        self.assertEqual(result, 0.0)
    
    def test_high_roi(self):
        """测试高ROI"""
        result = return_on_investment(100, 500)
        self.assertEqual(result, 4.0)  # 400%回报


class TestAnnualizedReturn(unittest.TestCase):
    """测试年化收益率计算函数"""
    
    def test_basic_annualized_return(self):
        """测试基本年化收益率计算"""
        # 1000元投资，5年后变为1628.89元，年化收益率应为5%
        final_value = 1000 * (1.05 ** 5)
        result = annualized_return(1000, final_value, 5)
        self.assertAlmostEqual(result, 0.05, places=4)
    
    def test_one_year_return(self):
        """测试一年期年化收益率"""
        result = annualized_return(1000, 1100, 1)
        self.assertAlmostEqual(result, 0.10, places=2)
    
    def test_negative_return(self):
        """测试负年化收益率"""
        result = annualized_return(1000, 900, 2)
        expected = (900/1000) ** (1/2) - 1
        self.assertAlmostEqual(result, expected, places=4)
    
    def test_zero_initial_value(self):
        """测试零初始价值"""
        result = annualized_return(0, 1000, 5)
        self.assertEqual(result, 0.0)
    
    def test_zero_years(self):
        """测试零年数"""
        result = annualized_return(1000, 1100, 0)
        self.assertEqual(result, 0.0)
    
    def test_fractional_years(self):
        """测试非整数年数"""
        # 1000元投资，1.5年后变为1100元
        result = annualized_return(1000, 1100, 1.5)
        expected = (1100/1000) ** (1/1.5) - 1
        self.assertAlmostEqual(result, expected, places=4)


class TestEdgeCases(unittest.TestCase):
    """测试边界情况"""
    
    def test_very_small_values(self):
        """测试非常小的数值"""
        # 未来价值
        result = future_value(0.01, 0.05, 10)
        expected = 0.01 * (1.05 ** 10)
        self.assertAlmostEqual(result, expected, places=10)
        
        # 现值
        result = present_value(0.01, 0.05, 10)
        expected = 0.01 / (1.05 ** 10)
        self.assertAlmostEqual(result, expected, places=10)
    
    def test_very_large_values(self):
        """测试非常大的数值"""
        result = future_value(1e9, 0.05, 30)
        expected = 1e9 * (1.05 ** 30)
        self.assertAlmostEqual(result, expected, places=-2)  # 允许较大误差
    
    def test_extreme_rates(self):
        """测试极端利率"""
        # 极高利率
        result = future_value(1000, 5.0, 3)  # 500%利率
        expected = 1000 * (6.0 ** 3)
        self.assertAlmostEqual(result, expected, places=2)
        
        # 极低利率
        result = future_value(1000, 0.0001, 10)
        expected = 1000 * (1.0001 ** 10)
        self.assertAlmostEqual(result, expected, places=2)


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    suite = unittest.TestSuite()
    
    # 添加测试类
    test_classes = [
        TestFutureValue,
        TestPresentValue,
        TestLoanPayment,
        TestNetPresentValue,
        TestInternalRateOfReturn,
        TestReturnOnInvestment,
        TestAnnualizedReturn,
        TestEdgeCases
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTest(tests)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    # 直接运行测试
    run_tests()
