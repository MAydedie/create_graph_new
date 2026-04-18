import unittest
import sys
import os

# 添加父目录到路径，以便导入 calculations 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'finance_cli')))

from calculations import (
    calculate_future_value,
    calculate_present_value,
    calculate_loan_payment,
    calculate_investment_return,
    calculate_compound_interest,
    calculate_roi,
    calculate_npv,
    calculate_irr,
    calculate_amortization_schedule
)


class TestFinanceCalculations(unittest.TestCase):
    """测试金融计算功能"""
    
    def test_calculate_future_value(self):
        """测试未来价值计算"""
        # 测试基本场景
        result = calculate_future_value(1000, 0.05, 10)
        self.assertAlmostEqual(result, 1628.89, places=2)
        
        # 测试零利率
        result = calculate_future_value(1000, 0, 5)
        self.assertEqual(result, 1000)
        
        # 测试负利率
        result = calculate_future_value(1000, -0.02, 5)
        self.assertAlmostEqual(result, 903.92, places=2)
    
    def test_calculate_present_value(self):
        """测试现值计算"""
        # 测试基本场景
        result = calculate_present_value(1628.89, 0.05, 10)
        self.assertAlmostEqual(result, 1000.00, places=2)
        
        # 测试零折现率
        result = calculate_present_value(1000, 0, 5)
        self.assertEqual(result, 1000)
        
        # 测试高折现率
        result = calculate_present_value(1000, 0.10, 10)
        self.assertAlmostEqual(result, 385.54, places=2)
    
    def test_calculate_loan_payment(self):
        """测试贷款月供计算"""
        # 测试30年房贷
        result = calculate_loan_payment(300000, 0.04, 30)
        self.assertAlmostEqual(result, 1432.25, places=2)
        
        # 测试5年车贷
        result = calculate_loan_payment(20000, 0.06, 5)
        self.assertAlmostEqual(result, 386.66, places=2)
        
        # 测试零利率贷款
        result = calculate_loan_payment(10000, 0, 1)
        self.assertAlmostEqual(result, 833.33, places=2)
    
    def test_calculate_investment_return(self):
        """测试投资回报计算"""
        # 测试正回报
        result = calculate_investment_return(1000, 1500)
        self.assertEqual(result, 0.5)  # 50%回报率
        
        # 测试负回报
        result = calculate_investment_return(1000, 800)
        self.assertEqual(result, -0.2)  # -20%回报率
        
        # 测试零回报
        result = calculate_investment_return(1000, 1000)
        self.assertEqual(result, 0.0)
    
    def test_calculate_compound_interest(self):
        """测试复利计算"""
        # 测试年复利
        result = calculate_compound_interest(1000, 0.05, 10, 1)
        self.assertAlmostEqual(result, 628.89, places=2)
        
        # 测试月复利
        result = calculate_compound_interest(1000, 0.05, 10, 12)
        self.assertAlmostEqual(result, 647.01, places=2)
        
        # 测试季度复利
        result = calculate_compound_interest(1000, 0.05, 10, 4)
        self.assertAlmostEqual(result, 643.62, places=2)
    
    def test_calculate_roi(self):
        """测试投资回报率计算"""
        # 测试简单ROI
        result = calculate_roi(1000, 1500, 500)
        self.assertEqual(result, 0.0)  # (1500-1000-500)/1000 = 0
        
        # 测试正ROI
        result = calculate_roi(1000, 2000, 500)
        self.assertEqual(result, 0.5)  # (2000-1000-500)/1000 = 0.5
        
        # 测试负ROI
        result = calculate_roi(1000, 1200, 500)
        self.assertEqual(result, -0.3)  # (1200-1000-500)/1000 = -0.3
    
    def test_calculate_npv(self):
        """测试净现值计算"""
        # 测试单期现金流
        result = calculate_npv(0.1, [-1000, 1100])
        self.assertAlmostEqual(result, 0.0, places=2)
        
        # 测试多期现金流
        result = calculate_npv(0.1, [-1000, 500, 500, 500])
        self.assertAlmostEqual(result, 243.43, places=2)
        
        # 测试负NPV
        result = calculate_npv(0.2, [-1000, 500, 500, 500])
        self.assertAlmostEqual(result, -52.08, places=2)
    
    def test_calculate_irr(self):
        """测试内部收益率计算"""
        # 测试简单IRR
        result = calculate_irr([-1000, 1100])
        self.assertAlmostEqual(result, 0.10, places=2)  # 10%
        
        # 测试多期现金流
        result = calculate_irr([-1000, 500, 500, 500])
        self.assertAlmostEqual(result, 0.234, places=3)  # 23.4%
        
        # 测试无解情况（所有现金流为正）
        with self.assertRaises(ValueError):
            calculate_irr([1000, 1100])
    
    def test_calculate_amortization_schedule(self):
        """测试分期还款计划计算"""
        # 测试1年期贷款
        schedule = calculate_amortization_schedule(12000, 0.12, 1)
        
        # 检查返回类型
        self.assertIsInstance(schedule, list)
        
        # 检查期数
        self.assertEqual(len(schedule), 12)
        
        # 检查第一期数据
        first_payment = schedule[0]
        self.assertIn('payment', first_payment)
        self.assertIn('principal', first_payment)
        self.assertIn('interest', first_payment)
        self.assertIn('balance', first_payment)
        
        # 检查总还款额
        total_payment = sum(p['payment'] for p in schedule)
        self.assertAlmostEqual(total_payment, 12000 * 0.12 / 12 * 12 + 12000, places=2)
        
        # 检查最后一期余额为0
        last_payment = schedule[-1]
        self.assertAlmostEqual(last_payment['balance'], 0, places=2)


if __name__ == '__main__':
    unittest.main()