import pytest
import os
from llm.agent.tools.bash_tool import BashTool

def test_echo_command():
    cmd = "echo hello"
    # On windows echo is a shell builtin
    result = BashTool.execute(cmd)
    
    assert result["exit_code"] == 0
    # Windows echo might output \r\n
    assert "hello" in result["stdout"].strip()
    assert result["timed_out"] == False

def test_command_timeout():
    # Use python to sleep for a bit
    # Sleep 2 seconds, but timeout is 100ms
    cmd = "python -c \"import time; time.sleep(2)\""
    result = BashTool.execute(cmd, timeout=100) # 100ms
    
    assert result["timed_out"] == True
    assert "timed out" in result["error"]

def test_stderr_capture():
    cmd = "python -c \"import sys; print('error message', file=sys.stderr)\""
    result = BashTool.execute(cmd)
    
    assert result["exit_code"] == 0
    assert "error message" in result["stderr"].strip()

def test_cwd_parameter(tmp_path):
    # Determine directory
    d = tmp_path / "subdir"
    d.mkdir()
    
    # Run command in that dir. 'cd' won't work with subprocess easily unless shell=True and valid command
    # just print cwd
    cmd = "python -c \"import os; print(os.getcwd())\""
    result = BashTool.execute(cmd, cwd=str(d))
    
    assert result["exit_code"] == 0
    # On windows paths are weird, use resolve/lowercase for loose check
    assert str(d.resolve()).lower() in result["stdout"].lower().strip()

if __name__ == "__main__":
    print("Testing Echo...")
    res = BashTool.execute("echo test")
    if "test" in res["stdout"]: print("PASS")
    else: print(f"FAIL: {res}")
    
    print("Testing Timeout...")
    res = BashTool.execute("python -c \"import time; time.sleep(1)\"", timeout=100)
    if res.get("timed_out"): print("PASS")
    else: print(f"FAIL: {res}")
