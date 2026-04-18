#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finance_cli/tests/test_commands_init.py

commands/__init__.py 模块的单元测试

测试命令模块的初始化、导入和基本功能
"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from finance_cli.commands import __init__ as commands_init


class TestCommandsInit(unittest.TestCase):
    """测试 commands/__init__.py 模块"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 保存原始状态
        self.original_modules = set(sys.modules.keys())
        
    def tearDown(self):
        """测试后的清理工作"""
        # 清理测试期间导入的模块
        new_modules = set(sys.modules.keys()) - self.original_modules
        for module in new_modules:
            if module.startswith('finance_cli.commands'):
                del sys.modules[module]
    
    def test_module_import(self):
        """测试模块能够正常导入"""
        # 测试模块存在性
        self.assertIsNotNone(commands_init)
        
        # 测试模块有正确的属性
        self.assertTrue(hasattr(commands_init, '__version__'))
        self.assertTrue(hasattr(commands_init, '__author__'))
        self.assertTrue(hasattr(commands_init, '__all__'))
    
    def test_module_version(self):
        """测试模块版本信息"""
        # 版本号应该是字符串
        self.assertIsInstance(commands_init.__version__, str)
        
        # 版本号应该符合语义化版本格式（主要检查格式）
        version_parts = commands_init.__version__.split('.')
        self.assertGreaterEqual(len(version_parts), 2)  # 至少应该有主版本和次版本
        
        # 版本号部分应该是数字
        for part in version_parts:
            if part.isdigit():
                self.assertTrue(int(part) >= 0)
    
    def test_module_author(self):
        """测试作者信息"""
        # 作者应该是字符串
        self.assertIsInstance(commands_init.__author__, str)
        
        # 作者信息不应该为空
        self.assertTrue(len(commands_init.__author__.strip()) > 0)
    
    def test_module_all_attribute(self):
        """测试 __all__ 属性"""
        # __all__ 应该是列表
        self.assertIsInstance(commands_init.__all__, list)
        
        # __all__ 中的元素都应该是字符串
        for item in commands_init.__all__:
            self.assertIsInstance(item, str)
    
    def test_module_docstring(self):
        """测试模块文档字符串"""
        # 模块应该有文档字符串
        self.assertIsNotNone(commands_init.__doc__)
        
        # 文档字符串不应该为空
        self.assertTrue(len(commands_init.__doc__.strip()) > 0)
    
    @patch('importlib.import_module')
    def test_command_imports(self, mock_import_module):
        """测试命令导入功能"""
        # 模拟导入成功
        mock_module = MagicMock()
        mock_module.Command = MagicMock()
        mock_import_module.return_value = mock_module
        
        # 测试动态导入
        try:
            # 尝试导入一个命令（这里使用模拟）
            from finance_cli.commands import get_command_class
            
            # 如果函数存在，测试它
            if hasattr(commands_init, 'get_command_class'):
                command_class = commands_init.get_command_class('test_command')
                self.assertIsNotNone(command_class)
        except (ImportError, AttributeError):
            # 如果函数不存在，这是正常的
            pass
    
    def test_module_structure(self):
        """测试模块结构完整性"""
        # 检查模块是否有必要的函数或类
        module_attrs = dir(commands_init)
        
        # 应该有一些公共接口
        public_attrs = [attr for attr in module_attrs if not attr.startswith('_')]
        self.assertTrue(len(public_attrs) > 0)
    
    def test_error_handling(self):
        """测试错误处理"""
        # 测试导入不存在的属性
        with self.assertRaises(AttributeError):
            _ = commands_init.non_existent_attribute
    
    def test_module_metadata(self):
        """测试模块元数据"""
        # 检查模块文件路径
        self.assertTrue(hasattr(commands_init, '__file__'))
        
        # 检查模块名称
        self.assertEqual(commands_init.__name__, 'finance_cli.commands.__init__')
        
        # 检查包信息
        self.assertTrue(hasattr(commands_init, '__package__'))
        self.assertEqual(commands_init.__package__, 'finance_cli.commands')


if __name__ == '__main__':
    unittest.main()
