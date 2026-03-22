import subprocess
import shlex
from typing import Dict, Any, Optional
import time
import os

class BashTool:
    """
    Bash Command Tool
    Executes shell commands with timeout.
    """
    name = "Bash"
    description = """
Execute a bash command.

Parameters:
- command: The command to execute (required)
- timeout: Timeout in milliseconds (default: 120000ms / 2 minutes)
- cwd: Working directory (optional, default: current directory)

Returns:
- stdout and stderr
- exit code
    """
    
    @staticmethod
    def get_schema() -> Dict:
        return {
            "name": "Bash",
            "description": BashTool.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in milliseconds (default 120000)"
                    },
                    "cwd": {"type": "string"}
                },
                "required": ["command"]
            }
        }
    
    @staticmethod
    def execute(command: str, timeout: Optional[float] = 120000.0, cwd: Optional[str] = None) -> Dict[str, Any]:
        """Execute bash command"""
        try:
            # Convert ms to seconds
            timeout_sec = (timeout or 120000.0) / 1000.0
            
            # Use shell=True for windows command compatibility (cmd.exe/powershell style)
            # or split arguments for robust execution if on linux.
            # On Windows, shell=True is often needed for built-ins like 'dir' or pipes.
            is_windows = os.name == 'nt'
            use_shell = True if is_windows else False
            
            args = command if use_shell else shlex.split(command)
            
            start_time = time.time()
            
            process = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                shell=use_shell
            )
            
            duration = (time.time() - start_time) * 1000 # duration in ms
            
            # Truncate output if too long (simulate Claude Code behavior)
            MAX_OUTPUT = 30000
            stdout = process.stdout
            if len(stdout) > MAX_OUTPUT:
                stdout = stdout[:MAX_OUTPUT] + "\n...[Output Truncated]..."
                
            stderr = process.stderr
            if len(stderr) > MAX_OUTPUT:
                stderr = stderr[:MAX_OUTPUT] + "\n...[Output Truncated]..."
            
            return {
                "command": command,
                "exit_code": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration_ms": int(duration),
                "timed_out": False
            }
            
        except subprocess.TimeoutExpired as e:
            return {
                "command": command,
                "exit_code": -1,
                "stdout": e.stdout.decode() if e.stdout else "",
                "stderr": e.stderr.decode() if e.stderr else "",
                "timed_out": True,
                "error": f"Command timed out after {timeout}ms"
            }
        except Exception as e:
            return {"error": f"Execution failed: {str(e)}"}
