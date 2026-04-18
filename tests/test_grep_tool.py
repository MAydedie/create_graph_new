import pytest
from pathlib import Path
from llm.agent.tools.grep_tool import GrepTool


def test_grep_basic_search(tmp_path):
    """测试基本的文本搜索"""
    # 创建测试文件
    test_file = tmp_path / "test.py"
    test_file.write_text("""
def hello():
    print("Hello World")
    
def goodbye():
    print("Goodbye World")
""")
    
    # 搜索 "hello"
    result = GrepTool.execute(pattern="hello", path=str(tmp_path))
    
    assert result["success"] is True
    assert result["count"] == 1
    assert "hello" in result["matches"]


def test_grep_case_insensitive(tmp_path):
    """测试大小写不敏感搜索"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello World\nHELLO WORLD\nhello world")
    
    result = GrepTool.execute(
        pattern="hello",
        path=str(tmp_path),
        ignore_case=True
    )
    
    assert result["success"] is True
    assert result["count"] == 3


def test_grep_with_include_pattern(tmp_path):
    """测试文件过滤"""
    # 创建多个文件
    (tmp_path / "test.py").write_text("def foo(): pass")
    (tmp_path / "test.txt").write_text("def foo(): pass")
    
    # 只搜索 .py 文件
    result = GrepTool.execute(
        pattern="def",
        path=str(tmp_path),
        include="*.py"
    )
    
    assert result["success"] is True
    assert result["count"] == 1
    assert ".py" in result["matches"]


def test_grep_no_matches(tmp_path):
    """测试没有匹配的情况"""
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")
    
    result = GrepTool.execute(pattern="nonexistent", path=str(tmp_path))
    
    assert result["success"] is True
    assert result["count"] == 0
    assert result["message"] == "No matches found."


def test_grep_invalid_regex():
    """测试无效的正则表达式"""
    result = GrepTool.execute(pattern="[invalid(", path=".")
    
    assert "error" in result
    assert "Invalid regex pattern" in result["error"]


def test_grep_max_results(tmp_path):
    """测试结果数量限制"""
    test_file = tmp_path / "test.py"
    # 创建 200 行包含 "test" 的内容
    content = "\n".join([f"test line {i}" for i in range(200)])
    test_file.write_text(content)
    
    result = GrepTool.execute(
        pattern="test",
        path=str(tmp_path),
        max_results=50
    )
    
    assert result["success"] is True
    assert result["count"] == 50
    assert "limited to 50" in result["message"]


def test_grep_single_file(tmp_path):
    """测试搜索单个文件"""
    test_file = tmp_path / "test.py"
    test_file.write_text("def foo(): pass\ndef bar(): pass")
    
    result = GrepTool.execute(pattern="def", path=str(test_file))
    
    assert result["success"] is True
    assert result["count"] == 2
