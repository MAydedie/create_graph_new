#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文件模板

这是一个基础的测试文件模板，包含常用的测试框架导入和测试类骨架。
可以根据需要选择使用unittest或pytest风格。
"""

import unittest
import pytest
import sys
import os

# 添加项目根目录到Python路径，以便导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# unittest风格测试类
# ============================================================================

class TestExampleUnittest(unittest.TestCase):
    """unittest风格的测试类示例"""
    
    @classmethod
    def setUpClass(cls):
        """
        类级别的设置方法
        在所有测试方法执行前执行一次
        """
        print("\n=== unittest测试类开始 ===")
        # 初始化测试所需的资源
        cls.shared_resource = "shared_data"
    
    @classmethod
    def tearDownClass(cls):
        """
        类级别的清理方法
        在所有测试方法执行后执行一次
        """
        print("=== unittest测试类结束 ===\n")
        # 清理测试资源
        cls.shared_resource = None
    
    def setUp(self):
        """
        测试方法级别的设置方法
        在每个测试方法执行前执行
        """
        print(f"执行测试: {self._testMethodName}")
        # 每个测试方法前的初始化
        self.test_data = [1, 2, 3, 4, 5]
    
    def tearDown(self):
        """
        测试方法级别的清理方法
        在每个测试方法执行后执行
        """
        # 每个测试方法后的清理
        self.test_data = None
    
    def test_addition(self):
        """测试加法运算"""
        result = 2 + 3
        self.assertEqual(result, 5, "2 + 3 应该等于 5")
        self.assertIsInstance(result, int, "结果应该是整数类型")
    
    def test_list_operations(self):
        """测试列表操作"""
        # 测试列表长度
        self.assertEqual(len(self.test_data), 5)
        
        # 测试列表包含
        self.assertIn(3, self.test_data)
        
        # 测试列表切片
        self.assertEqual(self.test_data[1:3], [2, 3])
    
    def test_exception(self):
        """测试异常抛出"""
        with self.assertRaises(ZeroDivisionError):
            result = 1 / 0
    
    @unittest.skip("跳过示例测试")
    def test_skip_example(self):
        """跳过测试的示例"""
        self.fail("这个测试不应该执行")


# ============================================================================
# pytest风格测试函数和类
# ============================================================================

# pytest fixture示例
@pytest.fixture
def sample_data():
    """pytest fixture，提供测试数据"""
    return {"name": "test", "value": 42}


@pytest.fixture(scope="module")
def module_resource():
    """模块级别的fixture"""
    print("\n=== pytest模块级别fixture设置 ===")
    resource = {"initialized": True}
    yield resource
    print("=== pytest模块级别fixture清理 ===\n")
    resource.clear()


class TestExamplePytest:
    """pytest风格的测试类示例"""
    
    def test_with_fixture(self, sample_data):
        """使用fixture的测试"""
        assert sample_data["name"] == "test"
        assert sample_data["value"] == 42
    
    def test_module_fixture(self, module_resource):
        """使用模块级别fixture的测试"""
        assert module_resource["initialized"] is True
    
    def test_parametrized_example(self, sample_data):
        """参数化测试的简单示例"""
        # 在实际使用中可以使用@pytest.mark.parametrize装饰器
        test_cases = [
            (1, 1, 2),
            (2, 3, 5),
            (-1, 1, 0),
        ]
        
        for a, b, expected in test_cases:
            assert a + b == expected, f"{a} + {b} 应该等于 {expected}"
    
    def test_exception_pytest(self):
        """pytest风格的异常测试"""
        with pytest.raises(ValueError):
            int("not_a_number")


# ============================================================================
# 通用测试工具函数
# ============================================================================

def assert_approx_equal(actual, expected, tolerance=1e-6):
    """
    断言近似相等（用于浮点数比较）
    
    Args:
        actual: 实际值
        expected: 期望值
        tolerance: 容差
    """
    assert abs(actual - expected) < tolerance, \
        f"实际值 {actual} 与期望值 {expected} 的差超过容差 {tolerance}"


def setup_test_environment():
    """设置测试环境"""
    # 设置环境变量
    os.environ["TEST_MODE"] = "true"
    
    # 创建测试目录
    test_dir = "test_temp"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
    
    return test_dir


def cleanup_test_environment(test_dir):
    """清理测试环境"""
    # 清理测试目录
    if os.path.exists(test_dir):
        import shutil
        shutil.rmtree(test_dir)
    
    # 清理环境变量
    if "TEST_MODE" in os.environ:
        del os.environ["TEST_MODE"]


# ============================================================================
# 测试运行入口
# ============================================================================

if __name__ == "__main__":
    """
    直接运行测试的入口
    
    使用方式:
    1. 运行所有测试: python test_template.py
    2. 运行unittest测试: python test_template.py unittest
    3. 运行pytest测试: python test_template.py pytest
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="运行测试")
    parser.add_argument("framework", nargs="?", default="all", 
                       choices=["all", "unittest", "pytest"],
                       help="选择测试框架 (默认: all)")
    
    args = parser.parse_args()
    
    if args.framework in ["all", "unittest"]:
        print("\n" + "="*60)
        print("运行unittest测试")
        print("="*60)
        unittest.main(argv=[sys.argv[0]], verbosity=2)
    
    if args.framework in ["all", "pytest"]:
        print("\n" + "="*60)
        print("运行pytest测试")
        print("="*60)
        # 注意：pytest.main()需要在pytest环境中运行
        # 这里只是示例，实际使用时可能需要调整
        try:
            pytest.main(["-v", "--tb=short"])
        except SystemExit:
            pass  # pytest正常退出
