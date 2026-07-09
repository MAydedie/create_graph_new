#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_FILE = PROJECT_ROOT / "app.py"
AUDIT_PARENT = Path(r"D:\代码仓库生图\汇报\4.25")
CATNET_REPO = Path(r"D:\catnet\CAT-Net-main")
METRIC_FILE = CATNET_REPO / "lib" / "utils" / "metric.py"
ADVISOR_ROOT = PROJECT_ROOT / "advisor_consultant_lab"
ADVISOR_RUNTIME = ADVISOR_ROOT / "runtime"
TASK_INPUT_FILE = ADVISOR_ROOT / "task_input.txt"
CONVERSATION_STORAGE_DIR = PROJECT_ROOT / "output_analysis" / "conversations"

QA_PROMPT = (
    "metric.py 这个节点有多少个类，多少个方法。其中选取出一个这个节点最重要的方法，告诉我这个方法主要是干嘛的，这个metric.py节点主要是干嘛的。主要的方法被谁调用，又调用了谁。被调用者 和 调用者又分别是干嘛的。\n"
    "请查看这个6个顶层函数的源码，然后告诉我这6个函数分别干了啥，算法中有啥亮点"
)

CODEGEN_PROMPT = (
    "请基于当前 CAT-Net 的经验库，生成一个真实可落地的 Python 命令行 demo 项目。"
    "这个项目要演示 CAT-Net 最核心的篡改定位能力：输入一张图像路径后，输出一个简化版的篡改定位结果，并打印关键处理阶段说明。"
)

ADVISOR_ARTIFACTS = [
    "step1_match_result.json",
    "step1_match_process.json",
    "step2_analysis.json",
    "step2_analysis.md",
    "step2_analysis_process.json",
    "step3_design.json",
    "step3_design.md",
    "step3_design_process.json",
    "step4_codegen.json",
    "step4_codegen.md",
    "step4_codegen_process.json",
    "stage_traces.jsonl",
]


def _load_app():
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    spec = importlib.util.spec_from_file_location("create_graph_capture_app", APP_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 app.py: {APP_FILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_app()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    return (cleaned[:80] or "item").strip("_") or "item"


def _conversation_storage_path(conversation_id: str) -> Path:
    import hashlib
    import re

    text = (conversation_id or "").strip()
    prefix = re.sub(r"[^0-9a-zA-Z_-]+", "_", text).strip("_")[:24] or "conversation"
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return CONVERSATION_STORAGE_DIR / f"{prefix}_{digest}.json"


def _selected_metric_node() -> Dict[str, Any]:
    return {
        "id": "lib/utils/metric.py",
        "name": "metric.py",
        "label": "metric.py",
        "display_name": "metric.py",
        "type": "file",
        "file_path": str(METRIC_FILE),
        "start_line": 1,
        "end_line": None,
        "signature": "lib/utils/metric.py",
        "full_name": "lib/utils/metric.py",
    }


def _poll_json(client, url: str, *, terminal_statuses: Optional[set[str]] = None, timeout_seconds: int = 900, interval_seconds: float = 1.0) -> Dict[str, Any]:
    started = time.time()
    last_payload: Dict[str, Any] = {}
    statuses = terminal_statuses or {"completed", "failed"}
    while time.time() - started <= timeout_seconds:
        response = client.get(url)
        payload = response.get_json() or {}
        last_payload = payload
        if str(payload.get("status") or "") in statuses:
            return payload
        time.sleep(interval_seconds)
    raise TimeoutError(f"poll timeout: {url} | last={last_payload}")


def _run_advisor_pipeline(prompt: str, target_dir: Path) -> Dict[str, Any]:
    target_dir.mkdir(parents=True, exist_ok=True)
    TASK_INPUT_FILE.write_text(prompt, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    started = time.time()
    completed = __import__("subprocess").run(
        [sys.executable, str(ADVISOR_ROOT / "run_pipeline.py")],
        cwd=str(ADVISOR_ROOT),
        env=env,
        stdout=__import__("subprocess").PIPE,
        stderr=__import__("subprocess").PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    summary = {
        "returncode": completed.returncode,
        "duration_seconds": round(time.time() - started, 3),
        "stdout_tail": (completed.stdout or "")[-4000:],
        "stderr_tail": (completed.stderr or "")[-4000:],
    }
    _write_json(target_dir / "advisor_pipeline_execution.json", summary)
    for name in ADVISOR_ARTIFACTS:
        src = ADVISOR_RUNTIME / name
        if src.exists():
            _copy_file(src, target_dir / name)
    return summary


def _copy_tree_listing(root: Path) -> List[str]:
    if not root.exists():
        return []
    items: List[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            items.append(str(path.relative_to(root)).replace("\\", "/"))
    return items


def _capture_qa_case(client, audit_root: Path) -> Dict[str, Any]:
    from data.data_accessor import get_data_accessor
    from app.services import conversation_service as cs
    from app.services import multi_agent_service as mas

    data_accessor = get_data_accessor()
    case_dir = audit_root / "qa_metric_py"
    case_dir.mkdir(parents=True, exist_ok=True)
    selected_node = _selected_metric_node()
    conversation_id = f"audit_qa_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    request_payload = {
        "project_path": str(CATNET_REPO),
        "query": QA_PROMPT,
        "conversation_id": conversation_id,
        "selected_node": selected_node,
        "auto_start_multi_agent": False,
        "opencode_enabled": True,
    }
    _write_json(case_dir / "request.json", request_payload)
    start_response = client.post("/api/conversations/session/start", json=request_payload)
    start_payload = start_response.get_json() or {}
    _write_json(case_dir / "session_start_response.json", {"status_code": start_response.status_code, "payload": start_payload})
    session_id = str(start_payload.get("sessionId") or "")
    if not session_id:
        raise RuntimeError(f"QA session start failed: {start_payload}")

    status_payload = _poll_json(client, f"/api/conversations/session/{session_id}/status", timeout_seconds=900)
    result_response = client.get(f"/api/conversations/session/{session_id}/result")
    result_payload = result_response.get_json() or {}
    _write_json(case_dir / "session_status_terminal.json", status_payload)
    _write_json(case_dir / "session_result.json", {"status_code": result_response.status_code, "payload": result_payload})

    conversation_payload = data_accessor.get_conversation(conversation_id) or {}
    session_payload = data_accessor.get_conversation_session(session_id) or {}
    events = data_accessor.list_conversation_events(conversation_id, since_seq=0, limit=1000)
    _write_json(case_dir / "conversation_events.json", events)
    _write_json(case_dir / "conversation_persisted.json", conversation_payload)
    _write_json(case_dir / "conversation_session_payload.json", session_payload)
    storage_path = _conversation_storage_path(conversation_id)
    if storage_path.exists():
        _copy_file(storage_path, case_dir / "conversation_storage_snapshot.json")
    _copy_file(METRIC_FILE, case_dir / "metric.py.snapshot")

    retrieval = ((result_payload.get("payload") or {}) if "payload" in result_payload else result_payload).get("retrieval") or {}
    _write_json(case_dir / "retrieval_result.json", retrieval)

    qa_context = mas.build_qa_context_bundle(
        project_path=str(CATNET_REPO),
        user_query=QA_PROMPT,
        task_mode="none",
        preferred_partition_id=None,
        selected_node=selected_node,
        qa_route="run_retrieval",
        task_weight="heavy",
        advisor_enabled=True,
    )
    _write_json(case_dir / "qa_context_bundle.json", qa_context)

    highlights = retrieval.get("highlights") if isinstance(retrieval, dict) else []
    fact_payload = cs._build_python_file_fact_payload(str(CATNET_REPO), QA_PROMPT, highlights if isinstance(highlights, list) else [])
    _write_json(case_dir / "python_file_fact_payload.json", fact_payload or {})

    bridge_result = cs.run_opencode_qa(
        project_path=str(CATNET_REPO),
        conversation_id=conversation_id,
        opencode_session_id="",
        user_query=QA_PROMPT,
        system_prompt=(
            "你是代码库事实问答助手。你会基于已经提取好的文件结构事实来直接回答用户问题。"
            "不要输出定位结论/关键证据/建议改动步骤/建议验证命令这类模板。"
            "必须覆盖：类数量、方法数量、最重要的方法、文件作用、调用者、被调者。"
            "如果 facts 里没有某项证据，就明确说未找到，不要猜。"
        ),
        history=[{"role": "user", "content": QA_PROMPT}],
        context_payload=cs._merge_qa_context_payload({"facts": fact_payload or {}}, qa_context),
        enabled=True,
        model=cs._opencode_qa_model(),
        agent=cs._opencode_qa_agent(),
        timeout_seconds=cs._opencode_qa_timeout_seconds(),
    )
    _write_json(case_dir / "opencode_qa_bridge_result.json", bridge_result)

    advisor_summary = _run_advisor_pipeline(QA_PROMPT, case_dir / "advisor_runtime")

    return {
        "case_dir": str(case_dir),
        "conversation_id": conversation_id,
        "session_id": session_id,
        "storage_path": str(storage_path),
        "advisor_pipeline": advisor_summary,
        "result_next_step": ((result_payload.get("payload") or {}) if "payload" in result_payload else result_payload).get("nextStep"),
        "answer_preview": str((((result_payload.get("payload") or {}) if "payload" in result_payload else result_payload).get("answer") or ""))[:500],
    }


def _capture_codegen_case(client, audit_root: Path) -> Dict[str, Any]:
    from data.data_accessor import get_data_accessor

    data_accessor = get_data_accessor()
    case_dir = audit_root / "codegen_catnet_demo"
    generated_root = case_dir / "materialized_demo"
    case_dir.mkdir(parents=True, exist_ok=True)
    generated_root.mkdir(parents=True, exist_ok=True)

    conversation_id = f"audit_codegen_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    handoff_request = {
        "project_path": str(CATNET_REPO),
        "query": CODEGEN_PROMPT,
        "conversation_id": conversation_id,
        "auto_start_multi_agent": False,
        "force_action": "start_multi_agent",
        "output_root": str(generated_root),
        "auto_apply_output": True,
        "opencode_enabled": True,
    }
    _write_json(case_dir / "conversation_request.json", handoff_request)
    start_response = client.post("/api/conversations/session/start", json=handoff_request)
    start_payload = start_response.get_json() or {}
    _write_json(case_dir / "conversation_start_response.json", {"status_code": start_response.status_code, "payload": start_payload})
    conv_session_id = str(start_payload.get("sessionId") or "")
    if not conv_session_id:
        raise RuntimeError(f"Codegen conversation start failed: {start_payload}")

    conv_status = _poll_json(client, f"/api/conversations/session/{conv_session_id}/status", timeout_seconds=900)
    conv_result_response = client.get(f"/api/conversations/session/{conv_session_id}/result")
    conv_result_payload = conv_result_response.get_json() or {}
    _write_json(case_dir / "conversation_status_terminal.json", conv_status)
    _write_json(case_dir / "conversation_result.json", {"status_code": conv_result_response.status_code, "payload": conv_result_payload})

    conversation_payload = data_accessor.get_conversation(conversation_id) or {}
    conv_session_payload = data_accessor.get_conversation_session(conv_session_id) or {}
    conv_events = data_accessor.list_conversation_events(conversation_id, since_seq=0, limit=1000)
    _write_json(case_dir / "conversation_events.json", conv_events)
    _write_json(case_dir / "conversation_persisted.json", conversation_payload)
    _write_json(case_dir / "conversation_session_payload.json", conv_session_payload)
    storage_path = _conversation_storage_path(conversation_id)
    if storage_path.exists():
        _copy_file(storage_path, case_dir / "conversation_storage_snapshot.json")

    handoff_payload = ((conv_result_payload.get("payload") or {}) if "payload" in conv_result_payload else conv_result_payload).get("handoff") or {}
    _write_json(case_dir / "conversation_handoff_gate.json", handoff_payload)
    if not handoff_payload:
        raise RuntimeError(f"Codegen handoff missing: {conv_result_payload}")

    multi_agent_request = {
        "project_path": handoff_payload.get("project_path") or str(CATNET_REPO),
        "query": handoff_payload.get("query") or CODEGEN_PROMPT,
        "task_mode": handoff_payload.get("task_mode") or "write_new_code",
        "partition_id": handoff_payload.get("partition_id"),
        "selected_node": handoff_payload.get("selected_node") or {},
        "clarification_context": handoff_payload.get("clarification_context") or {},
        "conversation_id": conversation_id,
        "output_root": handoff_payload.get("output_root") or str(generated_root),
        "auto_apply_output": True,
        "opencode_enabled": handoff_payload.get("opencode_enabled") if handoff_payload.get("opencode_enabled") is not None else True,
        "advisor_enabled": True,
        "swarm_enabled": True,
    }
    _write_json(case_dir / "multi_agent_request.json", multi_agent_request)
    ma_start_response = client.post("/api/multi_agent/session/start", json=multi_agent_request)
    ma_start_payload = ma_start_response.get_json() or {}
    _write_json(case_dir / "multi_agent_start_response.json", {"status_code": ma_start_response.status_code, "payload": ma_start_payload})
    ma_session_id = str(ma_start_payload.get("sessionId") or "")
    if not ma_session_id:
        raise RuntimeError(f"Multi-agent start failed: {ma_start_payload}")

    ma_status = _poll_json(client, f"/api/multi_agent/session/{ma_session_id}/status", timeout_seconds=2400)
    ma_result_response = client.get(f"/api/multi_agent/session/{ma_session_id}/result")
    ma_result_payload = ma_result_response.get_json() or {}
    _write_json(case_dir / "multi_agent_status_terminal.json", ma_status)
    _write_json(case_dir / "multi_agent_result.json", {"status_code": ma_result_response.status_code, "payload": ma_result_payload})

    ma_session_payload = data_accessor.get_multi_agent_session(ma_session_id) or {}
    _write_json(case_dir / "multi_agent_session_payload.json", ma_session_payload)
    conv_events_after = data_accessor.list_conversation_events(conversation_id, since_seq=0, limit=2000)
    _write_json(case_dir / "conversation_events_after_multi_agent.json", conv_events_after)
    conversation_payload_after = data_accessor.get_conversation(conversation_id) or {}
    _write_json(case_dir / "conversation_persisted_after_multi_agent.json", conversation_payload_after)

    result_payload = (ma_result_payload.get("payload") or {}) if "payload" in ma_result_payload else ma_result_payload
    _write_json(case_dir / "retrieval_bundle.json", result_payload.get("retrieval_bundle") or {})
    _write_json(case_dir / "evidence_packet.json", result_payload.get("evidence_packet") or {})
    _write_json(case_dir / "advisor_packet.json", result_payload.get("advisor_packet") or {})
    _write_json(case_dir / "evidence_verdict.json", result_payload.get("evidence_verdict") or {})
    _write_json(case_dir / "solution_packet.json", result_payload.get("solution_packet") or {})
    _write_json(case_dir / "output_protocol.json", result_payload.get("output_protocol") or {})
    _write_json(case_dir / "opencode_kernel.json", result_payload.get("opencode_kernel") or {})
    _write_json(case_dir / "output_write.json", result_payload.get("output_write") or {})
    _write_json(case_dir / "stage_outputs.json", result_payload.get("stage_outputs") or {})
    _write_json(case_dir / "swarm_packet.json", result_payload.get("swarm_packet") or {})

    generated_files = _copy_tree_listing(generated_root)
    _write_json(case_dir / "materialized_demo_files.json", generated_files)
    advisor_summary = _run_advisor_pipeline(CODEGEN_PROMPT, case_dir / "advisor_runtime")

    return {
        "case_dir": str(case_dir),
        "conversation_id": conversation_id,
        "conversation_session_id": conv_session_id,
        "multi_agent_session_id": ma_session_id,
        "generated_root": str(generated_root),
        "generated_file_count": len(generated_files),
        "advisor_pipeline": advisor_summary,
        "multi_agent_status": ma_status.get("status"),
        "output_write": result_payload.get("output_write") or {},
    }


def main() -> int:
    if not AUDIT_PARENT.exists():
        raise RuntimeError(f"audit parent missing: {AUDIT_PARENT}")
    if not CATNET_REPO.exists():
        raise RuntimeError(f"CAT-Net repo missing: {CATNET_REPO}")
    if not METRIC_FILE.exists():
        raise RuntimeError(f"metric.py missing: {METRIC_FILE}")

    run_id = datetime.now().strftime("catnet_capture_%Y%m%d_%H%M%S")
    audit_root = AUDIT_PARENT / run_id
    audit_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        audit_root / "run_manifest.json",
        {
            "run_id": run_id,
            "generated_at": datetime.now().isoformat(),
            "project_root": str(PROJECT_ROOT),
            "catnet_repo": str(CATNET_REPO),
            "metric_file": str(METRIC_FILE),
            "qa_prompt": QA_PROMPT,
            "codegen_prompt": CODEGEN_PROMPT,
        },
    )

    app = _load_app()
    client = app.test_client()

    qa_summary = _capture_qa_case(client, audit_root)
    codegen_summary = _capture_codegen_case(client, audit_root)

    summary = {
        "run_id": run_id,
        "audit_root": str(audit_root),
        "qa_case": qa_summary,
        "codegen_case": codegen_summary,
    }
    _write_json(audit_root / "capture_summary.json", summary)
    _write_text(audit_root / "README.txt", "Artifacts generated by scripts/capture_catnet_audit_20260425.py\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
