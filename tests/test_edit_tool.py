import pytest
from pathlib import Path
from llm.agent.tools.edit_tool import EditTool

@pytest.fixture
def temp_file(tmp_path):
    p = tmp_path / "code.py"
    p.write_text("def hello():\n    print('world')\n    print('world')\n", encoding="utf-8")
    return str(p)

def test_edit_single(temp_file):
    # Should fail because 'print('world')' appears twice
    result = EditTool.execute(temp_file, "print('world')", "print('python')")
    assert "error" in result
    assert "appears 2 times" in result["error"]

    # Unique string (with indentation)
    unique_str = "    print('world')\n"
    # Wait, the file has two indentical lines with indentation too.
    # "    print('world')\n" appears twice as well.
    
    # Let's try to replace "def hello():"
    result = EditTool.execute(temp_file, "def hello():", "def hi():")
    assert result["success"] == True
    path = Path(temp_file)
    assert "def hi():" in path.read_text(encoding="utf-8")

def test_edit_replace_all(temp_file):
    result = EditTool.execute(temp_file, "print('world')", "print('python')", replace_all=True)
    assert result["success"] == True
    assert result["replacements"] == 2
    path = Path(temp_file)
    content = path.read_text(encoding="utf-8")
    assert content.count("print('python')") == 2

def test_not_found(temp_file):
    result = EditTool.execute(temp_file, "non_existent", "foo")
    assert "error" in result
    assert "String not found" in result["error"]

def test_file_not_found():
    result = EditTool.execute("missing.txt", "a", "b")
    assert "error" in result
    assert "File not found" in result["error"]

if __name__ == "__main__":
    # Manually running for quick verify if pytest not available in cmd
    try:
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.py', encoding='utf-8') as tmp:
            tmp.write("def hello():\n    print('world')\n    print('world')\n")
            tmp_path = tmp.name
        
        print("Testing Single Edit (Should Fail)...")
        res = EditTool.execute(tmp_path, "print('world')", "foo")
        if "error" in res: print("PASS")
        else: print(f"FAIL: {res}")
        
        print("Testing Replace All...")
        res = EditTool.execute(tmp_path, "print('world')", "foo", replace_all=True)
        if res.get("success"): print("PASS")
        else: print(f"FAIL: {res}")

        os.remove(tmp_path)
    except Exception as e:
        print(f"Test script failed: {e}")
