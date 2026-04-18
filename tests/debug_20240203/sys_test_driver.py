import requests
import time
import sys
import json
import logging

# Config
BASE_URL = "http://localhost:8000"
USER_GOAL = r"请给我运行D:\代码仓库生图\create_graph\tests\debug_20240203下所有python文件，查看能否正常运行，并且把每个文件的运行结果告诉我"
WORKSPACE_ROOT = r"D:\代码仓库生图\create_graph"

def wait_for_server():
    print("Waiting for server to be ready...")
    for _ in range(30):
        try:
            resp = requests.get(f"{BASE_URL}/health")
            if resp.status_code == 200:
                print("Server is ready!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    print("Server failed to start.")
    return False

def start_task():
    url = f"{BASE_URL}/api/chat"
    payload = {
        "user_goal": USER_GOAL,
        "workspace_root": WORKSPACE_ROOT
    }
    print(f"Sending request: {json.dumps(payload, ensure_ascii=False)}")
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        print(f"Task started! Task ID: {data['task_id']}")
        return data['task_id']
    except Exception as e:
        print(f"Failed to start task: {e}")
        if 'resp' in locals():
            print(f"Response: {resp.text}")
        return None

if __name__ == "__main__":
    if not wait_for_server():
        sys.exit(1)
    
    task_id = start_task()
    if not task_id:
        sys.exit(1)
    
    print(f"Monitoring task {task_id} manually needed via logs.")
