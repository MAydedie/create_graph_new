import pytest
from pathlib import Path
from llm.agent.tools.glob_tool import GlobTool


def test_glob_simple_pattern(tmp_path):
    """测试简单的 glob 模式"""
    # 创建测试文件
    (tmp_path / "file1.py").write_text("code")
    (tmp_path / "file2.py").write_text("code")
    (tmp_path / "file3.txt").write_text("text")
    
    result = GlobTool.execute(pattern="*.py", path=str(tmp_path))
    
    assert result["success"] is True
    assert result["count"] == 2
    assert "file1.py" in result["matches"]
    assert "file2.py" in result["matches"]
    assert "file3.txt" not in result["matches"]


def test_glob_recursive_pattern(tmp_path):
    """测试递归 glob 模式"""
    # 创建嵌套目录结构
    (tmp_path / "root.py").write_text("code")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.py").write_text("code")
    (tmp_path / "subdir" / "deep").mkdir()
    (tmp_path / "subdir" / "deep" / "file.py").write_text("code")
    
    result = GlobTool.execute(pattern="**/*.py", path=str(tmp_path))
    
    assert result["success"] is True
    assert result["count"] == 3
    assert any("root.py" in m for m in result["matches"])
    assert any("nested.py" in m for m in result["matches"])
    assert any("file.py" in m for m in result["matches"])


def test_glob_specific_directory(tmp_path):
    """测试特定目录的 glob"""
    # 创建目录结构
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_one.py").write_text("test")
    (tmp_path / "tests" / "test_two.py").write_text("test")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "test_three.py").write_text("code")
    
    result = GlobTool.execute(pattern="tests/test_*.py", path=str(tmp_path))
    
    assert result["success"] is True
    assert result["count"] == 2
    assert any("test_one.py" in m for m in result["matches"])
    assert any("test_two.py" in m for m in result["matches"])


def test_glob_no_matches(tmp_path):
    """测试没有匹配的情况"""
    (tmp_path / "file.txt").write_text("text")
    
    result = GlobTool.execute(pattern="*.py", path=str(tmp_path))
    
    assert result["success"] is True
    assert result["count"] == 0
    assert result["matches"] == []


def test_glob_max_results(tmp_path):
    """测试结果数量限制"""
    # 创建 50 个文件
    for i in range(50):
        (tmp_path / f"file_{i:02d}.py").write_text("code")
    
    result = GlobTool.execute(pattern="*.py", path=str(tmp_path), max_results=20)
    
    assert result["success"] is True
    assert result["count"] == 20
    assert result["total_count"] == 50
    assert result["truncated"] is True


def test_glob_nonexistent_path():
    """测试不存在的路径"""
    result = GlobTool.execute(pattern="*.py", path="/nonexistent/path")
    
    assert "error" in result
    assert "not found" in result["error"].lower()


def test_glob_file_not_dir(tmp_path):
    """测试路径是文件而非目录"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    result = GlobTool.execute(pattern="*.py", path=str(test_file))
    
    assert "error" in result
    assert "not a directory" in result["error"].lower()


def test_glob_excludes_directories(tmp_path):
    """测试只返回文件，不返回目录"""
    (tmp_path / "file.py").write_text("code")
    (tmp_path / "subdir.py").mkdir()  # 目录名也匹配模式
    
    result = GlobTool.execute(pattern="*.py", path=str(tmp_path))
    
    assert result["success"] is True
    assert result["count"] == 1
    assert "file.py" in result["matches"]
    # subdir.py 不应该出现（因为是目录）


def test_glob_complex_pattern(tmp_path):
    """测试复杂的 glob 模式"""
    # 创建多种文件
    (tmp_path / "test_one.py").write_text("test")
    (tmp_path / "test_two.py").write_text("test")
    (tmp_path / "main.py").write_text("code")
    (tmp_path / "readme.txt").write_text("text")
    
    result = GlobTool.execute(pattern="test_*.py", path=str(tmp_path))
    
    assert result["success"] is True
    assert result["count"] == 2
    assert "test_one.py" in result["matches"]
    assert "test_two.py" in result["matches"]
    assert "main.py" not in result["matches"]
