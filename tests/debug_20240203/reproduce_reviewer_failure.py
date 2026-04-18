import subprocess
import os
import sys
from pathlib import Path

# Mocking ReviewerAgent logic
def reproduce():
    # Target and inferred root
    target = r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli\finance_cli\test"
    cwd = r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli"
    
    # Command
    cmd = f"{sys.executable} -m pytest {target} -v"
    
    # Env
    env = os.environ.copy()
    if cwd not in env.get("PYTHONPATH", ""):
         env["PYTHONPATH"] = f"{cwd}{os.pathsep}{env.get('PYTHONPATH', '')}"
    
    print(f"CWD: {cwd}")
    print(f"CMD: {cmd}")
    print(f"PYTHONPATH: {env.get('PYTHONPATH')}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            encoding='gbk',
            errors='replace'
        )
        
        with open("reproduce_log.txt", "w", encoding="utf-8") as f:
            f.write(f"Return Code: {result.returncode}\n")
            f.write("STDOUT:\n")
            f.write(result.stdout)
            f.write("\nSTDERR:\n")
            f.write(result.stderr)
        
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    reproduce()
