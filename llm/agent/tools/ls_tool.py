from pathlib import Path
from typing import Dict, Any, Optional


class LsTool:
    """
    Ls Tool (List Directory)
    List directory contents in a simple, readable format.
    """
    name = "Ls"
    description = """
List directory contents.

Parameters:
- path: Directory path to list (default: ".")
- max_entries: Maximum number of entries to return (default: 200)

Returns:
- List of files and directories with sizes
    """
    
    @staticmethod
    def get_schema() -> Dict:
        return {
            "name": "Ls",
            "description": LsTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list",
                        "default": "."
                    },
                    "max_entries": {
                        "type": "number",
                        "description": "Maximum number of entries to return",
                        "default": 200
                    }
                },
                "required": []
            }
        }
    
    @staticmethod
    def to_prompt_dict() -> Dict:
        """返回用于 LLM 提示的工具描述（SubAgent 兼容）"""
        return LsTool.get_schema()
    
    @staticmethod
    def execute(path: str = ".", max_entries: int = 200) -> Dict[str, Any]:
        """Execute ls operation"""
        try:
            # Resolve path
            dir_path = Path(path).resolve()
            
            if not dir_path.exists():
                return {"error": f"Path not found: {path}"}
            
            if not dir_path.is_dir():
                return {"error": f"Path is not a directory: {path}"}
            
            # List entries
            entries = []
            try:
                all_items = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                return {"error": f"Permission denied: {path}"}
            
            # Limit entries
            total_count = len(all_items)
            items_to_show = all_items[:max_entries]
            
            # Format output
            formatted_lines = []
            for item in items_to_show:
                try:
                    if item.is_dir():
                        formatted_lines.append(f"[DIR]  {item.name}/")
                        entries.append({
                            "name": item.name,
                            "is_dir": True,
                            "size": 0
                        })
                    else:
                        size = item.stat().st_size
                        size_kb = size / 1024
                        if size_kb < 1:
                            size_str = f"{size} B"
                        elif size_kb < 1024:
                            size_str = f"{size_kb:.1f} KB"
                        else:
                            size_mb = size_kb / 1024
                            size_str = f"{size_mb:.1f} MB"
                        
                        formatted_lines.append(f"[FILE] {item.name} ({size_str})")
                        entries.append({
                            "name": item.name,
                            "is_dir": False,
                            "size": size
                        })
                except (PermissionError, OSError):
                    # Skip items we can't access
                    continue
            
            result = {
                "success": True,
                "content": "\n".join(formatted_lines),
                "entries": entries,
                "total_count": total_count,
                "showing_count": len(entries)
            }
            
            if total_count > max_entries:
                result["truncated"] = True
                result["message"] = f"Showing {len(entries)} of {total_count} entries"
            
            return result
            
        except Exception as e:
            return {"error": f"Ls failed: {str(e)}"}
