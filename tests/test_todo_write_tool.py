import pytest
from llm.agent.tools.todo_write_tool import TodoWriteTool
import shutil
from pathlib import Path

# Use a separate test dir for todos to avoid polluting real user home
@pytest.fixture
def mock_todo_dir(monkeypatch, tmp_path):
    d = tmp_path / ".create_graph" / "todos"
    d.mkdir(parents=True)
    monkeypatch.setattr(TodoWriteTool, "_get_todo_dir", lambda: d)
    return d

def test_todo_write_success(mock_todo_dir):
    todos = [
        {"id": "1", "content": "Task 1", "status": "pending", "priority": "high"},
        {"id": "2", "content": "Task 2", "status": "pending", "priority": "medium"}
    ]
    
    result = TodoWriteTool.execute(todos, "test_session_1")
    assert result["success"] == True
    assert result["stats"]["total"] == 2
    
    # Verify file
    f = mock_todo_dir / "test_session_1.json"
    assert f.exists()
    assert "Task 1" in f.read_text(encoding="utf-8")

def test_todo_constraint_in_progress(mock_todo_dir):
    # Two in_progress tasks -> Should fail
    todos = [
        {"id": "1", "content": "Task 1", "status": "in_progress", "priority": "high"},
        {"id": "2", "content": "Task 2", "status": "in_progress", "priority": "medium"}
    ]
    
    result = TodoWriteTool.execute(todos, "test_session_fail")
    assert "error" in result
    assert "Constraint Violation" in result["error"]

def test_load_todos(mock_todo_dir):
    todos = [
        {"id": "1", "content": "Task 1", "status": "pending", "priority": "high"}
    ]
    TodoWriteTool.execute(todos, "load_test")
    
    loaded = TodoWriteTool.load_todos("load_test")
    assert len(loaded) == 1
    assert loaded[0]["content"] == "Task 1"

def test_load_non_existent(mock_todo_dir):
    loaded = TodoWriteTool.load_todos("non_existent")
    assert loaded == []

if __name__ == "__main__":
    print("Run via pytest")
