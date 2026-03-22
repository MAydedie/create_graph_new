import re
from pathlib import Path
from typing import Dict, Any, List, Optional


class GrepTool:
    """
    Grep Tool (Python Native)
    Search for patterns in files using Python's re module.
    This is a fallback implementation for systems without ripgrep (rg).
    """
    name = "Grep"
    description = """
Search for patterns in files using regex.

Parameters:
- pattern: Regex pattern to search for (required)
- path: Directory or file to search in (default: ".")
- include: Glob pattern to include (e.g. "*.py")
- ignore_case: Case insensitive search (default: False)
- max_results: Maximum number of results to return (default: 100)

Returns:
- Matches in format: "file_path:line_number:line_content"
    """
    
    @staticmethod
    def get_schema() -> Dict:
        return {
            "name": "Grep",
            "description": GrepTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in",
                        "default": "."
                    },
                    "include": {
                        "type": "string",
                        "description": "Glob pattern to include (e.g. '*.py')"
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "description": "Case insensitive search",
                        "default": False
                    },
                    "max_results": {
                        "type": "number",
                        "description": "Maximum number of results to return",
                        "default": 100
                    }
                },
                "required": ["pattern"]
            }
        }

    @staticmethod
    def to_prompt_dict() -> Dict:
        """返回用于 LLM 提示的工具描述（SubAgent 兼容）"""
        return GrepTool.get_schema()
    
    @staticmethod
    def execute(
        pattern: str,
        path: str = ".",
        include: Optional[str] = None,
        ignore_case: bool = False,
        max_results: int = 100
    ) -> Dict[str, Any]:
        """Execute grep search"""
        try:
            # Compile regex pattern
            flags = re.IGNORECASE if ignore_case else 0
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return {"error": f"Invalid regex pattern: {e}"}
            
            # Resolve path
            search_path = Path(path).resolve()
            
            if not search_path.exists():
                return {"error": f"Path not found: {path}"}
            
            # Collect files to search
            files_to_search: List[Path] = []
            
            if search_path.is_file():
                files_to_search.append(search_path)
            else:
                # Recursively find files
                if include:
                    # Use glob pattern
                    files_to_search = list(search_path.rglob(include))
                else:
                    # Search all text files (exclude common binary extensions)
                    binary_exts = {'.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', 
                                   '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
                                   '.pdf', '.zip', '.tar', '.gz', '.7z', '.rar'}
                    
                    for file_path in search_path.rglob("*"):
                        if file_path.is_file() and file_path.suffix.lower() not in binary_exts:
                            files_to_search.append(file_path)
            
            # Search in files
            matches: List[str] = []
            total_matches = 0
            
            for file_path in files_to_search:
                if total_matches >= max_results:
                    break
                
                try:
                    # Try to read as text
                    content = file_path.read_text(encoding='utf-8')
                    lines = content.splitlines()
                    
                    for line_num, line in enumerate(lines, start=1):
                        if regex.search(line):
                            # Format: file_path:line_number:line_content
                            relative_path = file_path.relative_to(search_path.parent) if search_path.is_dir() else file_path.name
                            match_str = f"{relative_path}:{line_num}:{line}"
                            matches.append(match_str)
                            total_matches += 1
                            
                            if total_matches >= max_results:
                                break
                                
                except (UnicodeDecodeError, PermissionError):
                    # Skip binary files or files we can't read
                    continue
            
            if total_matches == 0:
                return {
                    "success": True,
                    "matches": "",
                    "count": 0,
                    "message": "No matches found."
                }
            
            message = f"Found {total_matches} matches"
            if total_matches >= max_results:
                message += f" (limited to {max_results})"
            
            return {
                "success": True,
                "matches": "\n".join(matches),
                "count": total_matches,
                "message": message
            }
            
        except Exception as e:
            return {"error": f"Grep failed: {str(e)}"}
