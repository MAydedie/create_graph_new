
import sys
import os
import threading
import time

# Mocking the environment in analysis_service.py
project_root = r"D:\代码仓库生图\create_graph"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Change CWD to project root as if running app.py
os.chdir(project_root)

import build_graph_index

print(f"Current CWD: {os.getcwd()}")
print("Starting build_index...")

try:
    build_graph_index.build_index()
    print("build_index completed.")
except Exception as e:
    print(f"build_index failed: {e}")

# Check if file was updated
preview_path = os.path.join(project_root, "data", "graph_index", "knowledge_base_preview.md")
if os.path.exists(preview_path):
    print(f"Preview file exists. Last modified: {time.ctime(os.path.getmtime(preview_path))}")
else:
    print("Preview file does not exist.")
