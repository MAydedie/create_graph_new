#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 5.2 单元测试

测试错误恢复增强功能：
1. ErrorMemory - 错误记忆系统
2. ReflexionEngine - 反思引擎
3. RetryStrategy - 智能重试策略
4. ErrorPreventionChecker - 错误预防检查
"""

import sys
import time
from pathlib import Path

# 确保项目路径
def _find_project_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "config" / "config.py").exists():
            return current
        current = current.parent
    return Path.cwd()

PROJECT_ROOT = _find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


import pytest
from llm.agent.core.error_memory import ErrorMemory, ErrorRecord, get_global_error_memory, clear_global_error_memory
from llm.agent.core.reflexion_engine import ReflexionEngine, ReflexionResult
from llm.agent.core.retry_strategy import RetryStrategy, RetryType
from llm.agent.core.error_prevention import ErrorPreventionChecker, CheckResult


class TestErrorMemory:
    """ErrorMemory 单元测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.memory = ErrorMemory(storage_path=Path(".agent/test_error_memory.json"))
        self.memory.clear()
    
    def teardown_method(self):
        """每个测试后的清理"""
        self.memory.clear()
    
    def test_record_error(self):
        """测试记录错误"""
        error = FileNotFoundError("file.txt not found")
        context = {"step": "read_file", "file": "file.txt"}
        
        error_id = self.memory.record_error(error, context)
        
        assert error_id is not None
        assert len(self.memory) == 1
        
        record = self.memory.get_record(error_id)
        assert record is not None
        assert record.error_type == "FileNotFoundError"
        assert record.error_message == "file.txt not found"
    
    def test_record_attempt(self):
        """测试记录尝试"""
        error = FileNotFoundError("file.txt")
        error_id = self.memory.record_error(error, {})
        
        self.memory.record_attempt(error_id, {
            "action": "创建文件",
            "result": "失败"
        })
        
        attempts = self.memory.get_attempts(error_id)
        assert len(attempts) == 1
        assert attempts[0]["action"] == "创建文件"
    
    def test_record_solution(self):
        """测试记录解决方案"""
        error = FileNotFoundError("file.txt")
        error_id = self.memory.record_error(error, {})
        
        self.memory.record_solution(error_id, "使用绝对路径")
        
        record = self.memory.get_record(error_id)
        assert record.solution == "使用绝对路径"
        assert record.resolved is True
    
    def test_find_similar_errors(self):
        """测试查找相似错误"""
        # 记录第一个错误
        error1 = FileNotFoundError("file1.txt not found")
        error_id1 = self.memory.record_error(error1, {})
        self.memory.record_solution(error_id1, "解决方案1")
        
        # 记录第二个错误
        error2 = FileNotFoundError("file2.txt not found")
        error_id2 = self.memory.record_error(error2, {})
        self.memory.record_solution(error_id2, "解决方案2")
        
        # 查找相似错误
        similar = self.memory.find_similar_errors(
            FileNotFoundError("file3.txt not found")
        )
        
        assert len(similar) == 2
        assert all(r.error_type == "FileNotFoundError" for r in similar)
    
    def test_statistics(self):
        """测试统计信息"""
        error1 = FileNotFoundError("file1.txt")
        error_id1 = self.memory.record_error(error1, {})
        self.memory.record_solution(error_id1, "解决")
        
        error2 = SyntaxError("syntax error")
        self.memory.record_error(error2, {})
        
        stats = self.memory.get_statistics()
        
        assert stats["total_errors"] == 2
        assert stats["resolved_errors"] == 1
        assert stats["unresolved_errors"] == 1
        assert stats["resolution_rate"] == 50.0


class TestReflexionEngine:
    """ReflexionEngine 单元测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.engine = ReflexionEngine(verbose=False)
    
    def test_default_result_file_not_found(self):
        """测试 FileNotFoundError 的默认结果"""
        error = FileNotFoundError("file.txt not found")
        result = self.engine._default_result(error)
        
        assert result.root_cause == "文件不存在"
        assert "绝对路径" in result.recommended_solution
        assert result.confidence > 0.5
    
    def test_default_result_syntax_error(self):
        """测试 SyntaxError 的默认结果"""
        error = SyntaxError("invalid syntax")
        result = self.engine._default_result(error)
        
        assert result.root_cause == "代码语法错误"
        assert "语法" in result.recommended_solution
        assert result.confidence > 0.5
    
    def test_default_result_import_error(self):
        """测试 ImportError 的默认结果"""
        error = ImportError("No module named 'xxx'")
        result = self.engine._default_result(error)
        
        assert result.root_cause == "模块导入失败"
        assert len(result.improvements) > 0


class TestRetryStrategy:
    """RetryStrategy 单元测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.strategy = RetryStrategy()
    
    def test_syntax_error_no_retry(self):
        """测试语法错误不重试"""
        error = SyntaxError("invalid syntax")
        
        should_retry = self.strategy.should_retry(error, attempt=1)
        
        assert should_retry is False
    
    def test_file_not_found_retry(self):
        """测试文件不存在错误可以重试"""
        error = FileNotFoundError("file.txt")
        
        should_retry = self.strategy.should_retry(error, attempt=1)
        
        assert should_retry is True
    
    def test_max_retries(self):
        """测试最大重试次数"""
        error = FileNotFoundError("file.txt")
        
        # FileNotFoundError 的 max_retries 是 2
        # 第 1 次尝试
        assert self.strategy.should_retry(error, attempt=1) is True
        
        # 第 2 次尝试（达到最大值）
        assert self.strategy.should_retry(error, attempt=2) is False
    
    def test_exponential_backoff_delay(self):
        """测试指数退避延迟"""
        error = ConnectionError("connection failed")
        
        delay1 = self.strategy.get_delay(error, attempt=1)
        delay2 = self.strategy.get_delay(error, attempt=2)
        delay3 = self.strategy.get_delay(error, attempt=3)
        
        # 延迟应该递增
        assert delay2 > delay1
        assert delay3 > delay2
    
    def test_get_fix_action(self):
        """测试获取修复动作"""
        error = FileNotFoundError("file.txt")
        
        fix_action = self.strategy.get_fix_action(error)
        
        assert fix_action is not None
        assert "文件" in fix_action or "路径" in fix_action


class TestErrorPreventionChecker:
    """ErrorPreventionChecker 单元测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.checker = ErrorPreventionChecker(verbose=False)
    
    def test_file_not_exists_warning(self):
        """测试文件不存在警告"""
        step = {
            "action": "read",
            "target": "/nonexistent/file.txt"
        }
        
        result = self.checker.check_before_execute(step)
        
        assert result.safe is False
        assert len(result.warnings) > 0
        assert any("不存在" in w for w in result.warnings)
    
    def test_syntax_error_warning(self):
        """测试语法错误警告"""
        step = {
            "action": "write",
            "target": "test.py",
            "content": "def foo(\n    print('hello')"  # 语法错误
        }
        
        result = self.checker.check_before_execute(step)
        
        assert result.safe is False
        assert len(result.warnings) > 0
    
    def test_valid_code_no_warning(self):
        """测试有效代码无警告"""
        step = {
            "action": "write",
            "target": "test.py",
            "content": "def foo():\n    print('hello')"
        }
        
        result = self.checker.check_before_execute(step)
        
        # 可能有其他警告（如父目录不存在），但不应该有语法警告
        syntax_warnings = [w for w in result.warnings if "语法" in w]
        assert len(syntax_warnings) == 0


class TestIntegration:
    """集成测试"""
    
    def test_error_recovery_flow(self):
        """测试完整的错误恢复流程"""
        memory = ErrorMemory(storage_path=Path(".agent/test_integration.json"))
        memory.clear()
        
        engine = ReflexionEngine(verbose=False)
        strategy = RetryStrategy()
        
        # 1. 记录错误
        error = FileNotFoundError("config.json not found")
        error_id = memory.record_error(error, {"step": "load_config"})
        
        # 2. 第一次尝试
        memory.record_attempt(error_id, {
            "action": "直接读取",
            "result": "失败"
        })
        
        # 3. Reflexion 分析
        attempts = memory.get_attempts(error_id)
        reflexion_result = engine._default_result(error)
        
        assert reflexion_result.root_cause == "文件不存在"
        
        # 4. 判断是否重试
        should_retry = strategy.should_retry(error, attempt=1)
        assert should_retry is True
        
        # 5. 获取延迟
        delay = strategy.get_delay(error, attempt=1)
        assert delay >= 0
        
        # 6. 记录解决方案
        memory.record_solution(error_id, reflexion_result.recommended_solution)
        
        # 7. 查找相似错误
        similar = memory.find_similar_errors(FileNotFoundError("another.json"))
        assert len(similar) == 1
        
        # 清理
        memory.clear()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
