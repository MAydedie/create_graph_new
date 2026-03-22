from pathlib import Path
from typing import Dict, Any

class WriteTool:
    """
    Write File Tool
    Writes content to a file (overwrites existing).
    """
    name = "Write"
    description = """
Write a file to the local filesystem.

Usage:
- Overwrites existing file if it exists.
- Must read file first if it exists (enforced by policy, not code here, but good practice).
- Creates parent directories if they don't exist.

Parameters:
- file_path: Absolute path to the file
- content: Content to write
    """
    
    @staticmethod
    def get_schema() -> Dict:
        return {
            "name": "Write",
            "description": WriteTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["file_path", "content"]
            }
        }
    
    @staticmethod
    def execute(file_path: str, content: str) -> Dict[str, Any]:
        """Execute write operation"""
        try:
            path = Path(file_path).resolve()
            
            # Create parent directories
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            path.write_text(content, encoding='utf-8')
            
            return {
                "success": True,
                "file_path": str(path),
                "bytes_written": len(content.encode('utf-8'))
            }
            
        except Exception as e:
            return {"error": f"Write failed: {str(e)}"}
