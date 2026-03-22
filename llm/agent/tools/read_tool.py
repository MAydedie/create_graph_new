from pathlib import Path
from typing import Optional, Dict, Any
import os

class ReadTool:
    """
    Read File Tool
    Supports: Text files (with pagination)
    Note: Image and PDF support placeholders added for future extensibility
    """
    name = "Read"
    description = """
Read files from the local filesystem.

Parameters:
- file_path: Absolute path to the file (required)
- offset: Start line number (optional, for pagination)
- limit: Number of lines to read (optional, default 2000)

Returns content in cat -n format (with line numbers).
    """
    
    @staticmethod
    def get_schema() -> Dict:
        return {
            "name": "Read",
            "description": ReadTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file"
                    },
                    "offset": {
                        "type": "number",
                        "description": "Start line number (0-indexed)"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Number of lines to read"
                    }
                },
                "required": ["file_path"]
            }
        }
    
    @staticmethod
    def to_prompt_dict() -> Dict:
        """返回用于 LLM 提示的工具描述（SubAgent 兼容）"""
        return ReadTool.get_schema()
    
    @staticmethod
    def execute(file_path: str, offset: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Execute read operation"""
        try:
            # Normalize and validate path
            path = Path(file_path).resolve()
            
            if not path.exists():
                return {"error": f"File not found: {file_path}"}
            
            if not path.is_file():
                return {"error": f"Path is not a file: {file_path}"}

            # Check file type (basic extension check)
            suffix = path.suffix.lower()
            
            # Image files (Placeholder)
            if suffix in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
                return {
                    "type": "image",
                    "path": str(path),
                    "message": "Image file detected. (Multi-modal support required)"
                }
            
            # PDF files (Placeholder)
            if suffix == '.pdf':
                return {
                    "type": "pdf",
                    "path": str(path),
                    "message": "PDF file detected. (PDF parser required)"
                }
            
            # Text files
            try:
                content = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                # Fallback for binary or non-utf8 files if needed, or just error
                return {"error": "File is not valid UTF-8 text."}

            lines = content.splitlines()
            total_lines = len(lines)
            
            # Apply pagination
            start = offset if offset is not None else 0
            # Default limit 2000, max limit could be enforced here if needed
            read_limit = limit if limit is not None else 2000
            end = min(start + read_limit, total_lines)
            
            if start >= total_lines and total_lines > 0:
                 return {
                    "content": "",
                    "total_lines": total_lines,
                    "showing_range": f"{start}-{start} (End of file)",
                    "message": "Offset is beyond file length."
                }

            selected_lines = lines[start:end]
            
            # Format as cat -n (1-indexed line numbers for display)
            # {i+1+start:6d} aligns numbers to 6 digits
            formatted = "\n".join(
                f"{i+1+start:6d}\t{line}" 
                for i, line in enumerate(selected_lines)
            )
            
            return {
                "content": formatted,
                "total_lines": total_lines,
                "showing_range": f"{start+1}-{end}"
            }
            
        except Exception as e:
            return {"error": f"Read failed: {str(e)}"}
