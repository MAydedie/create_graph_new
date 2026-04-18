"""
Multi-Agent Failure Reproduction Script
This script attempts to reproduce the user's issue: "为D:\代码仓库生图\create_graph\test_sandbox下的所有python文件写测试文件"
It sets up detailed logging to capture why the agents fail and retry 3 times.
"""

import os
os.environ["HF_HUB_OFFLINE"] = "1"
import sys
import logging
import traceback
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("reproduce_issue_debug.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Set specific loggers to DEBUG
logging.getLogger("Orchestrator").setLevel(logging.DEBUG)
logging.getLogger("Planner").setLevel(logging.DEBUG)
logging.getLogger("Coder").setLevel(logging.DEBUG)
logging.getLogger("Reviewer").setLevel(logging.DEBUG)
logging.getLogger("RetryManager").setLevel(logging.DEBUG)

def reproduce_issue():
    print("=" * 60)
    print("Multi-Agent Failure Reproduction Script")
    print("=" * 60)
    
    try:
        from llm.agent.agents import orchestrator
        from llm.agent.agents import planner_agent, coder_agent, reviewer_agent
        from llm.agent.cognitive import knowledge_agent, memory_agent
        
        # User's exact prompt
        user_goal = r"为D:\代码仓库生图\create_graph\test_sandbox下的所有python文件写测试文件"
        
        print(f"Goal: {user_goal}")
        print("Initializing Agents...")
        
        # Initialize all agents
        ka = knowledge_agent.KnowledgeAgent()
        ma = memory_agent.MemoryAgent()
        planner = planner_agent.PlannerAgent()
        coder = coder_agent.CoderAgent()
        reviewer = reviewer_agent.ReviewerAgent()
        
        print("Initializing Orchestrator...")
        orch = orchestrator.create_orchestrator(
            knowledge_agent=ka,
            memory_agent=ma,
            planner=planner,
            coder=coder,
            reviewer=reviewer,
            verbose=True
        )
        
        print("Executing task...")
        result = orch.execute_with_retry(user_goal)
        
        print("\n" + "=" * 60)
        if result.get("success"):
            print("✓ SUCCESS: Task completed successfully")
            print(f"Result: {result}")
        else:
            print("✗ FAILURE: Task failed as expected")
            print(f"Error: {result.get('error')}")
            
    except Exception as e:
        print(f"\nCRITICAL EXCEPTION during execution: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    reproduce_issue()
