import pytest
from pathlib import Path
from llm.agent.tools.write_tool import WriteTool

def test_write_new_file(tmp_path):
    p = tmp_path / "new.txt"
    result = WriteTool.execute(str(p), "hello world")
    assert result["success"] == True
    assert p.read_text(encoding="utf-8") == "hello world"

def test_write_overwrite(tmp_path):
    p = tmp_path / "existing.txt"
    p.write_text("old content", encoding="utf-8")
    
    result = WriteTool.execute(str(p), "new content")
    assert result["success"] == True
    assert p.read_text(encoding="utf-8") == "new content"

def test_create_directories(tmp_path):
    p = tmp_path / "deep" / "nested" / "dir" / "file.txt"
    result = WriteTool.execute(str(p), "content")
    assert result["success"] == True
    assert p.exists()
    assert p.read_text(encoding="utf-8") == "content"

if __name__ == "__main__":
    try:
        import tempfile
        import shutil
        import os
        
        tmp_dir = tempfile.mkdtemp()
        try:
            print("Testing Write New...")
            p = Path(tmp_dir) / "test.txt"
            res = WriteTool.execute(str(p), "hello")
            if res.get("success") and p.read_text() == "hello": print("PASS")
            else: print(f"FAIL: {res}")
            
            print("Testing Overwrite...")
            res = WriteTool.execute(str(p), "world")
            if res.get("success") and p.read_text() == "world": print("PASS")
            else: print(f"FAIL: {res}")
            
        finally:
            shutil.rmtree(tmp_dir)
            
    except Exception as e:
        print(f"Test script failed: {e}")
