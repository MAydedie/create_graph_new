import pytest
from pathlib import Path
from llm.agent.tools.ls_tool import LsTool


def test_ls_basic(tmp_path):
    """测试基本的目录列表"""
    # 创建测试文件和目录
    (tmp_path / "file1.txt").write_text("content")
    (tmp_path / "file2.py").write_text("code")
    (tmp_path / "subdir").mkdir()
    
    result = LsTool.execute(path=str(tmp_path))
    
    assert result["success"] is True
    assert result["total_count"] == 3
    assert "file1.txt" in result["content"]
    assert "file2.py" in result["content"]
    assert "subdir/" in result["content"]


def test_ls_sorts_dirs_first(tmp_path):
    """测试目录优先排序"""
    (tmp_path / "z_file.txt").write_text("content")
    (tmp_path / "a_dir").mkdir()
    (tmp_path / "m_file.py").write_text("code")
    
    result = LsTool.execute(path=str(tmp_path))
    
    assert result["success"] is True
    lines = result["content"].split("\n")
    # 目录应该在前面
    assert "[DIR]" in lines[0]
    assert "a_dir/" in lines[0]


def test_ls_default_current_dir():
    """测试默认使用当前目录"""
    result = LsTool.execute()
    
    assert result["success"] is True
    assert "total_count" in result


def test_ls_max_entries(tmp_path):
    """测试条目数量限制"""
    # 创建 50 个文件
    for i in range(50):
        (tmp_path / f"file_{i:02d}.txt").write_text("content")
    
    result = LsTool.execute(path=str(tmp_path), max_entries=20)
    
    assert result["success"] is True
    assert result["total_count"] == 50
    assert result["showing_count"] == 20
    assert result["truncated"] is True


def test_ls_nonexistent_path():
    """测试不存在的路径"""
    result = LsTool.execute(path="/nonexistent/path")
    
    assert "error" in result
    assert "not found" in result["error"].lower()


def test_ls_file_not_dir(tmp_path):
    """测试路径是文件而非目录"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    result = LsTool.execute(path=str(test_file))
    
    assert "error" in result
    assert "not a directory" in result["error"].lower()


def test_ls_empty_dir(tmp_path):
    """测试空目录"""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    
    result = LsTool.execute(path=str(empty_dir))
    
    assert result["success"] is True
    assert result["total_count"] == 0
    assert result["content"] == ""


def test_ls_size_formatting(tmp_path):
    """测试文件大小格式化"""
    # 小文件 (< 1KB)
    small = tmp_path / "small.txt"
    small.write_text("x" * 100)
    
    # 中等文件 (几 KB)
    medium = tmp_path / "medium.txt"
    medium.write_text("x" * 5000)
    
    # 大文件 (> 1MB)
    large = tmp_path / "large.txt"
    large.write_text("x" * (2 * 1024 * 1024))
    
    result = LsTool.execute(path=str(tmp_path))
    
    assert result["success"] is True
    content = result["content"]
    assert "B" in content or "KB" in content  # small file
    assert "KB" in content  # medium file
    assert "MB" in content  # large file
