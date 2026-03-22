from pathlib import Path
from typing import Dict, Any

class EditTool:
    """
    Edit File Tool
    Performs precise string replacement.
    """
    name = "Edit"
    description = """
Perform precise string replacement in a file.

Key Rules:
1. You MUST read the file first using Read tool.
2. old_string must be unique in the file (unless replace_all is True).
3. Indentation is preserved if included in old_string.

Parameters:
- file_path: Absolute path to the file
- old_string: Text to replace (exact match)
- new_string: Text to replace with
- replace_all: Replace all occurrences (default: False)
    """
    
    @staticmethod
    def get_schema() -> Dict:
        return {
            "name": "Edit",
            "description": EditTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to edit"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact string to replace (must match exactly)"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "New string to insert"
                    },
                    "replace_all": {"type": "boolean", "default": False}
                },
                "required": ["file_path", "old_string", "new_string"]
            }
        }
    
    @staticmethod
    def to_prompt_dict() -> Dict:
        """返回用于 LLM 提示的工具描述（SubAgent 兼容）"""
        return EditTool.get_schema()
    
    @staticmethod
    def execute(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> Dict[str, Any]:
        """Execute edit operation"""
        try:
            path = Path(file_path).resolve()
            
            if not path.exists():
                return {"error": f"File not found: {file_path}"}
            
            content = path.read_text(encoding='utf-8')
            
            # Check occurrence count
            count = content.count(old_string)
            
            if count == 0:
                # Provide a snippet preview if possible
                preview = old_string[:100] + "..." if len(old_string) > 100 else old_string
                return {
                    "error": "String not found in file.",
                    "old_string_preview": preview
                }
            
            if count > 1 and not replace_all:
                return {
                    "error": f"String appears {count} times. Use replace_all=true or provide unique context."
                }
            
            # Execute replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
            
            path.write_text(new_content, encoding='utf-8')
            
            return {
                "success": True,
                "replacements": count if replace_all else 1,
                "file_path": str(path)
            }
            
        except Exception as e:
            return {"error": f"Edit failed: {str(e)}"}
