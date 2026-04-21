import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import os

class TodoWriteTool:
    """
    Todo List Management Tool
    Implements short-term memory (session-level task tracking).
    """
    name = "TodoWrite"
    description = """
Create and manage a structured task list.

When to use:
1. Complex multi-step tasks (3+ steps)
2. Tracking progress on user requests
3. Non-trivial tasks requiring state persistence

Task Status:
- pending: Not started
- in_progress: Currently working on (Only ONE allowed at a time!)
- completed: Finished

Constraints:
- Only ONE task can be 'in_progress' at any time.
- Mark tasks as 'completed' immediately when done.
    """
    
    @staticmethod
    def get_schema() -> Dict:
        return {
            "name": "TodoWrite",
            "description": TodoWriteTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string", "minLength": 1},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"]
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"]
                                },
                                "id": {"type": "string"}
                            },
                            "required": ["content", "status", "priority", "id"]
                        }
                    }
                },
                "required": ["todos"]
            }
        }
    
    @staticmethod
    def _get_todo_dir() -> Path:
        """Get or create todo directory"""
        # Using a fixed hidden directory in user home for persistence
        todo_dir = Path.home() / ".create_graph" / "todos"
        todo_dir.mkdir(parents=True, exist_ok=True)
        return todo_dir

    @staticmethod
    def execute(todos: List[Dict], session_id: str) -> Dict[str, Any]:
        """Execute Todo write operation"""
        try:
            # Validate constraint: Only one in_progress task
            in_progress_count = sum(1 for t in todos if t["status"] == "in_progress")
            if in_progress_count > 1:
                return {
                    "error": f"Constraint Violation: Found {in_progress_count} tasks marked 'in_progress'. Only 1 is allowed per session."
                }
            
            todo_dir = TodoWriteTool._get_todo_dir()
            
            # Write to JSON file
            # Using session_id as filename
            safe_session_id = "".join([c for c in session_id if c.isalnum() or c in ('-', '_')])
            if not safe_session_id:
                safe_session_id = "default_session"
                
            todo_file = todo_dir / f"{safe_session_id}.json"
            
            todo_data = {
                "session_id": session_id,
                "updated_at": datetime.now().isoformat(),
                "todos": todos
            }
            
            todo_file.write_text(
                json.dumps(todo_data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            
            # Calculate stats
            stats = {
                "pending": sum(1 for t in todos if t["status"] == "pending"),
                "in_progress": in_progress_count,
                "completed": sum(1 for t in todos if t["status"] == "completed"),
                "total": len(todos)
            }
            
            return {
                "success": True,
                "message": f"Todo list updated. {stats['completed']}/{len(todos)} tasks completed.",
                "stats": stats,
                "file_path": str(todo_file)
            }
            
        except Exception as e:
            return {"error": f"Todo update failed: {str(e)}"}

    @staticmethod
    def load_todos(session_id: str) -> List[Dict]:
        """Load todos for a session (helper for Orchestrator)"""
        try:
            todo_dir = TodoWriteTool._get_todo_dir()
            safe_session_id = "".join([c for c in session_id if c.isalnum() or c in ('-', '_')])
            if not safe_session_id:
                return []
                
            todo_file = todo_dir / f"{safe_session_id}.json"
            
            if not todo_file.exists():
                return []
            
            content = todo_file.read_text(encoding='utf-8')
            data = json.loads(content)
            return data.get("todos", [])
        except Exception:
            return []
