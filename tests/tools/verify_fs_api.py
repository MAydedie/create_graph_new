import requests
import json
import os

BASE_URL = "http://localhost:8000"
TEST_DIR = r"D:\代码仓库生图\create_graph\test_sandbox\finance_cli"

def test_fs_api():
    print(f"Testing Backend API at {BASE_URL}...")
    
    # 1. Test Health
    try:
        resp = requests.get(f"{BASE_URL}/health")
        print(f"Health Check: {resp.status_code} - {resp.json()}")
    except Exception as e:
        print(f"Health Check Failed: {e}")
        return

    # Ensure test dir exists
    if not os.path.exists(TEST_DIR):
        print(f"Creating test dir: {TEST_DIR}")
        os.makedirs(TEST_DIR, exist_ok=True)
        # Create a dummy file
        with open(os.path.join(TEST_DIR, "readme.txt"), "w", encoding="utf-8") as f:
            f.write("Hello Agent!")

    # 2. Test List Files
    print(f"\nTesting List Files: {TEST_DIR}")
    resp = requests.post(f"{BASE_URL}/api/fs/list", json={"path": TEST_DIR})
    if resp.status_code == 200:
        items = resp.json().get("items", [])
        print(f"Success! Found {len(items)} items:")
        for item in items:
            print(f" - {item['name']} ({item['type']})")
    else:
        print(f"Failed: {resp.status_code} - {resp.text}")

    # 3. Test Read File
    test_file = os.path.join(TEST_DIR, "readme.txt")
    print(f"\nTesting Read File: {test_file}")
    resp = requests.post(f"{BASE_URL}/api/fs/read", json={"path": test_file})
    if resp.status_code == 200:
        content = resp.json().get("content", "")
        print(f"Success! Content: {content}")
    else:
        print(f"Failed: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    test_fs_api()
