import unittest
from calculator import Calculator


class TestCalculator(unittest.TestCase):
    """Calculator 类的单元测试"""
    
    def setUp(self):
        """在每个测试方法前执行，创建 Calculator 实例"""
        self.calc = Calculator()
    
    def test_add(self):
        """测试加法运算"""
        # 正常情况测试
        self.assertEqual(self.calc.add(2, 3), 5)
        self.assertEqual(self.calc.add(-1, 1), 0)
        self.assertEqual(self.calc.add(0, 0), 0)
        self.assertEqual(self.calc.add(-5, -3), -8)
        
        # 测试浮点数
        self.assertAlmostEqual(self.calc.add(2.5, 3.1), 5.6)
        
    def test_subtract(self):
        """测试减法运算"""
        # 正常情况测试
        self.assertEqual(self.calc.subtract(5, 3), 2)
        self.assertEqual(self.calc.subtract(3, 5), -2)
        self.assertEqual(self.calc.subtract(0, 0), 0)
        self.assertEqual(self.calc.subtract(-5, -3), -2)
        
        # 测试浮点数
        self.assertAlmostEqual(self.calc.subtract(5.5, 2.2), 3.3)
        
    def test_multiply(self):
        """测试乘法运算"""
        # 正常情况测试
        self.assertEqual(self.calc.multiply(2, 3), 6)
        self.assertEqual(self.calc.multiply(-2, 3), -6)
        self.assertEqual(self.calc.multiply(0, 5), 0)
        self.assertEqual(self.calc.multiply(-2, -3), 6)
        
        # 测试浮点数
        self.assertAlmostEqual(self.calc.multiply(2.5, 4), 10.0)
        
    def test_divide(self):
        """测试除法运算"""
        # 正常情况测试
        self.assertEqual(self.calc.divide(6, 3), 2)
        self.assertEqual(self.calc.divide(5, 2), 2.5)
        self.assertEqual(self.calc.divide(-6, 3), -2)
        self.assertEqual(self.calc.divide(0, 5), 0)
        
        # 测试浮点数
        self.assertAlmostEqual(self.calc.divide(10, 3), 3.3333333333333335)
        
        # 测试除零异常
        with self.assertRaises(ValueError):
            self.calc.divide(5, 0)
        
    def test_power(self):
        """测试幂运算"""
        # 正常情况测试
        self.assertEqual(self.calc.power(2, 3), 8)
        self.assertEqual(self.calc.power(5, 0), 1)
        self.assertEqual(self.calc.power(0, 5), 0)
        self.assertEqual(self.calc.power(4, 0.5), 2)  # 平方根
        
        # 测试负指数
        self.assertEqual(self.calc.power(2, -1), 0.5)
        
    def test_square_root(self):
        """测试平方根运算"""
        # 正常情况测试
        self.assertEqual(self.calc.square_root(4), 2)
        self.assertEqual(self.calc.square_root(9), 3)
        self.assertEqual(self.calc.square_root(0), 0)
        
        # 测试浮点数
        self.assertAlmostEqual(self.calc.square_root(2), 1.4142135623730951)
        
        # 测试负数平方根（应抛出异常）
        with self.assertRaises(ValueError):
            self.calc.square_root(-1)
    
    def test_factorial(self):
        """测试阶乘运算"""
        # 正常情况测试
        self.assertEqual(self.calc.factorial(0), 1)
        self.assertEqual(self.calc.factorial(1), 1)
        self.assertEqual(self.calc.factorial(5), 120)
        
        # 测试负数阶乘（应抛出异常）
        with self.assertRaises(ValueError):
            self.calc.factorial(-1)
        
        # 测试非整数阶乘（应抛出异常）
        with self.assertRaises(ValueError):
            self.calc.factorial(2.5)
    
    def test_modulo(self):
        """测试取模运算"""
        # 正常情况测试
        self.assertEqual(self.calc.modulo(10, 3), 1)
        self.assertEqual(self.calc.modulo(5, 5), 0)
        self.assertEqual(self.calc.modulo(-10, 3), 2)  # Python 的取模行为
        
        # 测试除零异常
        with self.assertRaises(ValueError):
            self.calc.modulo(5, 0)
    
    def test_chain_operations(self):
        """测试链式操作"""
        # 测试连续多次操作
        result = self.calc.add(2, 3)
        result = self.calc.multiply(result, 4)
        result = self.calc.subtract(result, 5)
        self.assertEqual(result, 15)  # (2+3)*4-5 = 15
    
    def test_edge_cases(self):
        """测试边界情况"""
        # 大数测试
        self.assertEqual(self.calc.add(1000000, 2000000), 3000000)
        
        # 极小值测试
        self.assertAlmostEqual(self.calc.add(0.000001, 0.000002), 0.000003)
        
        # 混合类型测试（整数和浮点数）
        self.assertAlmostEqual(self.calc.add(5, 3.2), 8.2)
        
    def test_method_chaining(self):
        """测试方法链式调用（如果 Calculator 支持）"""
        # 如果 Calculator 支持链式调用，可以这样测试
        # 例如：calc.add(2,3).multiply(4).subtract(5)
        # 但需要根据实际实现调整
        pass


if __name__ == '__main__':
    unittest.main()
