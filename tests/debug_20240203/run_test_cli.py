import sys
import os
import subprocess

def run_tests():
    env = os.environ.copy()
    env["PYTHONPATH"] = r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli"
    
    cmd = [sys.executable, "-m", "pytest", "finance_cli/test/test_cli.py", "-v"]
    
    result = subprocess.run(
        cmd,
        cwd=r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli",
        capture_output=True,
        text=True,
        env=env,
        encoding='utf-8',
        errors='replace'
    )
    
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    return result.returncode

if __name__ == "__main__":
    sys.exit(run_tests())
