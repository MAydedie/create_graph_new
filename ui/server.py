#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 5 后端服务
提供 REST API 和 WebSocket 接口，连接前端与 Multi-Agent 系统。
"""

import sys
import os
import asyncio
import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 添加项目根目录到 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm.agent.agents import orchestrator, planner_agent, coder_agent, reviewer_agent, error_solver_agent
from llm.agent.cognitive import knowledge_agent, memory_agent
from llm.agent.core.execution_state import StepStatus, TaskStatus
from llm.agent.core.task_session import TaskSession

# Phase 3 & 6 集成
from llm.agent.tools.tool_registry import ToolRegistry
from llm.agent.prompts_v2 import PLANNER_PROMPT_V2, CODER_PROMPT_V2, REVIEWER_PROMPT_V2
from llm.agent.core.subagent import SubAgent

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebServer")

app = FastAPI(title="Agent Demo Backend")

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，仅用于演示
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 数据模型 ---

class TaskRequest(BaseModel):
    user_goal: str
    workspace_root: str
    restore_from: Optional[str] = None  # 检查点路径

class FileReadRequest(BaseModel):
    path: str

class FileListRequest(BaseModel):
    path: str

class ApprovalRequest(BaseModel):
    task_id: str
    action: str  # "allow" | "reject"
    feedback: Optional[str] = None

class QuickQuestionRequest(BaseModel):
    question: str
    workspace_root: Optional[str] = None

# --- 任务管理器 ---

class TaskManager:
    """管理运行中的任务会话"""
    
    def __init__(self):
        self.sessions: Dict[str, TaskSession] = {}
        self.orchestrators: Dict[str, orchestrator.Orchestrator] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.active_websockets: Dict[str, List[WebSocket]] = {}
        self.approval_events: Dict[str, threading.Event] = {}
        self.approval_decisions: Dict[str, Dict] = {}  # {task_id: {"action": "allow", "feedback": ""}}
        self.stopped_tasks: Dict[str, bool] = {}  # V3: 任务停止标记
    
    def create_task(self, request: TaskRequest) -> str:
        """创建并启动新任务（Phase 3 & 6 增强版 + 智能路由）"""
        
        # 智能路由: 检测是否为简单问答
        from llm.agent.utils.question_detector import QuestionDetector
        
        analysis = QuestionDetector.analyze(request.user_goal)
        
        if analysis["is_question"] and analysis["confidence"] > 0.6:
            # 简单问答 -> 使用直接 LLM 调用（方案 B-1）
            logger.info(f"[智能路由] 检测到简单问答（置信度: {analysis['confidence']:.2f}）")
            logger.info(f"[智能路由] 原因: {analysis['reason']}")
            logger.info(f"[智能路由] 使用快速问答模式（直接 LLM）...")
            
            # 创建任务 ID
            task_id = f"quick_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            
            # 使用直接 LLM 调用快速回答
            try:
                from llm.rag_core.llm_api import DeepSeekAPI
                
                # 轻量级问答系统提示词
                qa_system_prompt = """你是一个**智能代码生成助手**，专门帮助用户通过自然语言描述来生成、修改和优化代码。

## 核心能力
1. **代码生成**：根据用户需求自动生成完整的代码文件
2. **代码修改**：理解用户意图，精准修改现有代码
3. **代码审查**：自动检测代码问题并提供修复方案
4. **智能规划**：将复杂需求分解为可执行的步骤

## 回答策略

### 如果用户问系统介绍类问题（"你是谁"、"你能做什么"等）
回答模板：
```
你好！我是智能代码生成助手 🤖

我可以帮你：
✅ 生成代码 - 告诉我你想实现什么功能，我会自动生成代码
✅ 修改代码 - 描述你想改什么，我会精准修改
✅ 修复 Bug - 遇到错误？我会分析并自动修复
✅ 代码审查 - 我会检查代码质量并提出改进建议

**试试这样问我**：
- "帮我生成一个用户登录功能"
- "修改这个函数，让它支持异步"
- "这段代码报错了，帮我看看"

有什么代码需求吗？😊
```

### 如果用户问功能咨询类问题（"支持什么语言"、"能生成前端吗"等）
回答模板：
```
我支持几乎所有主流编程语言：
- 前端：HTML/CSS/JavaScript/React/Vue
- 后端：Python/Java/Node.js/Go
- 数据库：SQL/MongoDB
- 其他：配置文件、测试代码等

**直接告诉我你的需求**，比如：
- "用 React 生成一个待办事项列表"
- "用 Python 写一个爬虫"
- "帮我重构这个类，提取公共方法"

现在就开始吧！你想生成什么代码？
```

### 如果用户闲聊或问无关问题
策略：简短回应（1-2句话），然后立即引导回代码话题

回答模板：
```
[简短回应闲聊内容]

不过，我更擅长的是帮你写代码 😄

比如：
- 自动化重复性工作
- 快速搭建项目框架
- 修复棘手的 Bug

有什么代码需求吗？我随时准备帮你！
```

### 如果用户质疑或负面问题（"你能行吗"、"AI靠谱吗"等）
回答模板：
```
好问题！我的优势是：

✅ **多 Agent 协作** - 规划、编码、审查三重保障
✅ **自动测试** - 生成代码后自动运行测试
✅ **智能修复** - 发现错误会自动尝试修复

当然，复杂需求可能需要多次迭代。

**不如试试看**？给我一个小任务，比如：
- "生成一个简单的计算器函数"
- "帮我写一个数据验证函数"

让代码说话！😎
```

## 重要原则
1. **始终引导用户到代码生成任务**
2. **回答要简洁、友好、有emoji**
3. **给出具体的使用示例**
4. **避免长篇大论，保持在 150 字以内**"""

                api = DeepSeekAPI()
                
                # 调用 LLM
                answer = api.chat([
                    {"role": "system", "content": qa_system_prompt},
                    {"role": "user", "content": request.user_goal}
                ])
                
                # ✅ 修复：从 API 响应中提取实际的文本内容
                # answer 是完整的 API 响应对象，需要提取 choices[0].message.content
                if isinstance(answer, dict) and 'choices' in answer:
                    answer_text = answer['choices'][0]['message']['content']
                else:
                    # 如果是字符串，直接使用
                    answer_text = str(answer)
                
                logger.info(f"[智能路由] LLM 回答: {answer_text[:100]}...")
                
                # 创建简化的 Session 用于前端显示
                session = TaskSession.create(
                    user_goal=request.user_goal,
                    task_id=task_id
                )
                session.event_log.log(
                    event_type="quick_answer",
                    agent="QA_LLM",
                    summary=answer_text,  # ✅ 使用提取的文本而不是完整响应对象
                    step_id=0
                )
                # ✅ 修复：设置正确的状态字段
                session.status = TaskStatus.COMPLETED
                session.save()
                
                self.sessions[task_id] = session
                
                logger.info(f"[智能路由] 快速问答完成: {task_id}")
                return task_id
                
            except Exception as e:
                logger.error(f"[智能路由] 快速问答失败: {e}")
                logger.info(f"[智能路由] 降级到完整任务流程...")
                import traceback
                traceback.print_exc()
                # 失败则降级到完整流程
        
        # 复杂任务 -> 使用完整 Multi-Agent 流程
        logger.info(f"[智能路由] 使用完整任务流程...")
        
        # 初始化 Agents
        # 注意：这里重新创建 Agent 实例，确保每个任务独立
        # 在真实场景中可能复用单例
        # 设置工作区（通过环境变量或其他方式传递给 CoderAgent）
        os.environ["WORKSPACE_ROOT"] = request.workspace_root
        
        from llm.rag_core.llm_api import DeepSeekAPI
        shared_api = DeepSeekAPI()
        
        # Phase 3: 创建 ToolRegistry
        tool_registry = ToolRegistry()
        
        ka = knowledge_agent.KnowledgeAgent()
        ma = memory_agent.MemoryAgent()
        
        # Phase 6: TODO - 使用 V2 提示词（需要先修改 Agents 支持 system_prompt 参数）
        planner = planner_agent.PlannerAgent(
            llm_api=shared_api
            # system_prompt=PLANNER_PROMPT_V2  # TODO: 待 Agent 支持
        )
        coder = coder_agent.CoderAgent(
            # system_prompt=CODER_PROMPT_V2  # TODO: 待 Agent 支持
        )
        reviewer = reviewer_agent.ReviewerAgent(
            # system_prompt=REVIEWER_PROMPT_V2  # TODO: 待 Agent 支持
        )
        error_solver = error_solver_agent.ErrorSolverAgent(llm_api=shared_api)
        
        # Phase 3: 传入 ToolRegistry
        orch = orchestrator.create_orchestrator(
            knowledge_agent=ka,
            memory_agent=ma,
            planner=planner,
            coder=coder,
            reviewer=reviewer,
            error_solver=error_solver,
            tool_registry=tool_registry,  # Phase 3 新增
            verbose=True
        )
        
        # 创建 Session (这里手动创建以便获取 ID，或者由 Orchestrator 创建后获取)
        # 为简单起见，我们调用 orchestrator 内部方法先创建 session
        # 但 orchestrator.execute 会创建新的。
        # 我们这里稍微 hack 一下，先生成 ID
        # 我们这里稍微 hack 一下，先生成 ID
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        self.orchestrators[task_id] = orch
        self.approval_events[task_id] = threading.Event()
        
        # 启动线程执行
        thread = threading.Thread(
            target=self._run_task_thread,
            args=(task_id, request.user_goal, orch)
        )
        thread.daemon = True
        thread.start()
        self.threads[task_id] = thread
        
        logger.info(f"任务 {task_id} 已启动，线程: {thread.name}")
        return task_id
    
    def _run_task_thread(self, task_id: str, user_goal: str, orch: orchestrator.Orchestrator):
        """后台线程执行任务 (V2)"""
        try:
            # 注入拦截器：当 Coder 准备执行修改时，暂停等待审批
            # 注意：这需要修改 CoderAgent 或 Orchestrator 才能实现真正的暂停
            # 为了演示，我们暂时假设 Orchestrator 提供了 hook
            # 或者通过轮询 session 状态来实现
            
            # 使用 V4 死磕模式
            result = orch.execute_with_resolution_loop(user_goal)
            
            logger.info(f"任务 {task_id} 执行完成: {result.get('success')}")
            
        except Exception as e:
            logger.error(f"任务 {task_id} 执行异常: {e}")
            import traceback
            traceback.print_exc()
            
        finally:
            # ========== 关键变更：保证总结与清理 ==========
            logger.info(f"任务 {task_id} 线程正在清理...")
            
            # 1. 强制生成总结（如果尚未生成）
            try:
                if orch.current_session:
                    orch.force_summary_generation()
                    # 更新 Session 状态以便最后一次获取
                    self.sessions[task_id] = orch.get_current_session()
            except Exception as summary_err:
                logger.error(f"任务 {task_id} 清理时生成总结失败: {summary_err}")

            # 2. 清理资源：保留 Session 一段时间（比如5分钟）供查看，但标记为结束
            # 如果是 Stop 触发的，应该在 Stop 逻辑里已经处理了
            # 这里主要是线程自然结束或 crash 后的处理
            if task_id in self.active_websockets:
                logger.info(f"关闭任务 {task_id} 的 WebSocket 连接")
                # 可选：通知前端任务结束
                # ...
                
            # 3. 从活跃 Orchestrator 列表中移除，防止继续操作
            if task_id in self.orchestrators:
                # 注意：这里不立即删除，允许前端获取最后状态
                # 但要确保它不会再被执行
                pass

    def stop_task(self, task_id: str) -> bool:
        """停止任务并清理上下文"""
        logger.info(f"请求停止任务: {task_id}")
        
        # 1. 标记停止
        self.stopped_tasks[task_id] = True
        
        # 2. 通知 Orchestrator
        if task_id in self.orchestrators:
            orch = self.orchestrators[task_id]
            orch.request_stop()
            
            # V2: 强制生成总结（立即）- 线程里的 finally 也会做，这里双重保险
            try:
                orch.force_summary_generation()
            except:
                pass
                
        # 3. 清理 Session (彻底销毁上下文)
        # 注意：这里我们保留 Session 对象在内存中，以便前端还能看到"已停止"状态和总结
        # 但必须切断 MemoryAgent 的关联
        
        # 如果是"开启新任务前清理旧任务"，则由 create_task 处理
        # 这里只负责停止当前任务
        
        return True

    def get_session(self, task_id: str) -> Optional[TaskSession]:
        """获取任务会话"""
        if task_id in self.orchestrators:
            return self.orchestrators[task_id].get_current_session()
        return self.sessions.get(task_id)

    async def connect_websocket(self, websocket: WebSocket, task_id: str):
        """处理 WebSocket 连接"""
        await websocket.accept()
        if task_id not in self.active_websockets:
            self.active_websockets[task_id] = []
        self.active_websockets[task_id].append(websocket)
        
        logger.info(f"WS 连接: {task_id}")
        
        try:
            # 检查任务是否已经完成（快速问答或已完成的完整任务）
            # 如果是，立即推送现有的日志
            session = self.get_session(task_id)
            # ✅ 修复：检查正确的状态字段
            if session and (session.status == TaskStatus.COMPLETED or session.is_completed()):
                logger.info(f"任务 {task_id} 已完成，推送历史日志...")
                logger.info(f"事件数量: {len(session.event_log.events)}")
                
                for idx, event in enumerate(session.event_log.events):
                    try:
                        event_dict = event.to_dict()
                        logger.info(f"事件 {idx} 的原始数据: {event_dict}")
                        
                        summary = event_dict.get('summary', '')
                        summary_preview = summary[:50] if summary else 'None'
                        logger.info(f"推送事件 {idx}: type={event_dict.get('event_type')}, summary={summary_preview}")
                        
                        await websocket.send_json({
                            "type": "event",
                            "data": event_dict
                        })
                        logger.info(f"事件 {idx} 推送成功")
                    except Exception as e:
                        logger.error(f"推送事件 {idx} 时出错: {e}")
                        import traceback
                        traceback.print_exc()
                
                # ✅ 修复：推送完成状态，让前端知道任务已结束
                await websocket.send_json({
                    "type": "status",
                    "data": "completed"
                })
                
                # ✅ 修复：短暂延迟确保消息发送完成，然后关闭连接
                await asyncio.sleep(0.1)
                logger.info(f"任务 {task_id} 的历史日志已全部推送，关闭连接")
                return

            last_event_idx = 0
            while True:
                session = self.get_session(task_id)
                if session:
                    # 获取新事件
                    events = session.event_log.events
                    if len(events) > last_event_idx:
                        new_events = events[last_event_idx:]
                        for event in new_events:
                            await websocket.send_json({
                                "type": "event",
                                "data": event.to_dict()
                            })
                        last_event_idx = len(events)
                    
                    # 检查是否完成
                    if session.is_completed() or session.is_failed():
                        await websocket.send_json({
                            "type": "status",
                            "data": session.status.value
                        })
                        # 发送一次完整结果后退出循环? 不，保持连接以便查看
                        
                await asyncio.sleep(0.5) # 轮询间隔
                
        except WebSocketDisconnect:
            logger.info(f"WS 断开: {task_id}")
            self.active_websockets[task_id].remove(websocket)
        except Exception as e:
            logger.error(f"WS 错误: {e}")
            
task_manager = TaskManager()

# --- API 路由 ---

@app.post("/api/chat")
async def start_chat(request: TaskRequest):
    """开始新任务"""
    if not os.path.exists(request.workspace_root):
        raise HTTPException(status_code=400, detail="工作区路径不存在")
    
    task_id = task_manager.create_task(request)
    return {"task_id": task_id, "status": "started"}

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket 流式接口"""
    await task_manager.connect_websocket(websocket, task_id)

@app.post("/api/stop")
async def stop_task(body: Dict[str, str]):
    """停止任务"""
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(status_code=400, detail="Missing task_id")
    
    if task_manager.stop_task(task_id):
        return {"status": "stopped", "task_id": task_id}
    else:
        raise HTTPException(status_code=404, detail="Task not found")

@app.post("/api/fs/list")
async def list_files(request: FileListRequest):
    """列出文件"""
    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="路径不存在")
    
    items = []
    try:
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "path": str(item.resolve()),
                "size": item.stat().st_size if item.is_file() else 0
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"items": items}

@app.post("/api/fs/read")
async def read_file(request: FileReadRequest):
    """读取文件内容"""
    path = Path(request.path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    try:
        # 简单读取，不处理大文件
        content = path.read_text(encoding="utf-8")
        return {"content": content, "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/quick_question")
async def quick_question(request: QuickQuestionRequest):
    """
    处理简单问答（Phase 3: 轻量级 Session）
    
    使用 SubAgent 快速回答问题，不创建完整的任务会话
    """
    try:
        # 创建 ToolRegistry
        tool_registry = ToolRegistry()
        
        # 设置工作区（如果提供）
        if request.workspace_root:
            os.environ["WORKSPACE_ROOT"] = request.workspace_root
        
        # 创建 SubAgent（research 类型适合问答）
        subagent = SubAgent(
            agent_type="research",
            prompt=request.question,
            tool_registry=tool_registry,
            verbose=True
        )
        
        # 执行并获取答案
        answer = subagent.run()
        
        return {
            "success": True,
            "answer": answer,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Quick question failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    # 获取本机IP
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"Server starting at http://{local_ip}:8000")
    print(f"Also available at http://localhost:8000")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
