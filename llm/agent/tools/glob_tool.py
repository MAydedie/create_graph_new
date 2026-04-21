from pathlib import Path
from typing import Dict, Any, List


class GlobTool:
    """
    Glob Tool
    Find files matching a glob pattern.
    """
    name = "Glob"
    description = """
Find files matching a glob pattern.

Parameters:
- pattern: Glob pattern to match (e.g. "*.py", "**/*.json")
- path: Directory to search in (default: ".")
- max_results: Maximum number of results to return (default: 200)

Returns:
- List of matching file paths

Examples:
- "*.py" - All Python files in current directory
- "**/*.py" - All Python files recursively
- "tests/test_*.py" - Test files in tests directory
    """
    
    @staticmethod
    def get_schema() -> Dict:
        return {
            "name": "Glob",
            "description": GlobTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern (e.g. '**/*.py')"
                    },
                    "path": {
                        "type": "string",
                        "description": "Root directory (default: .)"
                    },
                    "max_results": {
                        "type": "number",
                        "description": "Maximum number of results",
                        "default": 200
                    }
                },
                "required": ["pattern"]
            }
        }

    @staticmethod
    def to_prompt_dict() -> Dict:
        """返回用于 LLM 提示的工具描述（SubAgent 兼容）"""
        return GlobTool.get_schema()
    
    @staticmethod
    def execute(pattern: str, path: str = ".", max_results: int = 200) -> Dict[str, Any]:
        """Execute glob search"""
        try:
            # Resolve base path
            base_path = Path(path).resolve()
            
            if not base_path.exists():
                return {"error": f"Path not found: {path}"}
            
            if not base_path.is_dir():
                return {"error": f"Path is not a directory: {path}"}
            
            # Determine if pattern is recursive
            if "**" in pattern:
                # Use rglob for recursive patterns
                # Remove leading ** if present
                clean_pattern = pattern.replace("**/", "").replace("**", "*")
                matches = list(base_path.rglob(clean_pattern))
            else:
                # Use glob for non-recursive patterns
                matches = list(base_path.glob(pattern))
            
            # Filter to only files (exclude directories)
            file_matches = [m for m in matches if m.is_file()]
            
            # Sort by path
            file_matches.sort()
            
            # Limit results
            total_count = len(file_matches)
            limited_matches = file_matches[:max_results]
            
            # Format paths (relative to base_path for readability)
            formatted_paths = []
            for match in limited_matches:
                try:
                    rel_path = match.relative_to(base_path)
                    formatted_paths.append(str(rel_path))
                except ValueError:
                    # If relative path fails, use absolute
                    formatted_paths.append(str(match))
            
            result = {
                "success": True,
                "matches": formatted_paths,
                "count": len(formatted_paths),
                "total_count": total_count
            }
            
            if total_count > max_results:
                result["truncated"] = True
                result["message"] = f"Showing {len(formatted_paths)} of {total_count} matches"
            else:
                result["message"] = f"Found {total_count} matches"
            
            return result
            
        except Exception as e:
            return {"error": f"Glob failed: {str(e)}"}
