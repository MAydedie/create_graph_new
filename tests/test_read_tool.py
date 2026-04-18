import pytest
import os
from pathlib import Path
from llm.agent.tools.read_tool import ReadTool

# Helper to create temporary files
@pytest.fixture
def temp_text_file(tmp_path):
    file_path = tmp_path / "test_file.txt"
    content = "\n".join([f"Line {i}" for i in range(1, 101)]) # 100 lines
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)

def test_read_success(temp_text_file):
    result = ReadTool.execute(temp_text_file)
    assert "content" in result
    assert result["total_lines"] == 100
    assert "     1\tLine 1" in result["content"]

def test_read_pagination(temp_text_file):
    # Read first 10 lines
    result = ReadTool.execute(temp_text_file, offset=0, limit=10)
    assert result["total_lines"] == 100
    assert result["showing_range"] == "1-10"
    content = result["content"]
    assert "     1\tLine 1" in content
    assert "    10\tLine 10" in content
    assert "    11\tLine 11" not in content

    # Read lines 50-59 (10 lines)
    result_offset = ReadTool.execute(temp_text_file, offset=49, limit=10) # 0-indexed offset 49 is line 50
    assert result_offset["showing_range"] == "50-59" # 1-indexed display
    content_offset = result_offset["content"]
    assert "    50\tLine 50" in content_offset
    assert "    59\tLine 59" in content_offset

def test_file_not_found():
    result = ReadTool.execute("non_existent_file.txt")
    assert "error" in result
    assert "File not found" in result["error"]

def test_image_placeholder(tmp_path):
    img_path = tmp_path / "test.png"
    img_path.touch()
    result = ReadTool.execute(str(img_path))
    assert result.get("type") == "image"
    assert "Multi-modal" in result.get("message", "")

if __name__ == "__main__":
    # Manually running for quick verify if pytest not available in cmd
    try:
        # We need to setup a temp file manually if running as script
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as tmp:
            tmp.write("\n".join([f"Line {i}" for i in range(1, 101)]))
            tmp_path = tmp.name
        
        print("Testing Read Success...")
        res = ReadTool.execute(tmp_path)
        if "content" in res: print("PASS")
        else: print(f"FAIL: {res}")

        print("Testing Pagination...")
        res = ReadTool.execute(tmp_path, offset=0, limit=5)
        if "Line 5" in res["content"] and "Line 6" not in res["content"]: print("PASS")
        else: print(f"FAIL: {res}")
        
        os.remove(tmp_path)
    except Exception as e:
        print(f"Test script failed: {e}")
