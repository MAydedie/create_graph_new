from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app


SIMPLE_QA_QUESTIONS = [
    "全局经验库里有哪些与agent规划器设计相关的路径？请列出来源项目和分区。",
    "请从全局经验中找出agent工具调用编排的实现路径，并说明每条路径用途。",
    "全局经验中，agent如何做任务分解和执行？请给出具体路径证据。",
    "请列出全局经验中agent memory或上下文管理相关的经验路径。",
    "全局经验里关于agent失败重试与容错的代码路径有哪些？",
    "帮我找全局经验中agent路由与决策策略的具体实现路径。",
    "全局经验里多agent协作有哪些可复用路径？请按项目分组列出。",
    "请从全局经验中找agent prompt组装与系统提示词注入相关路径。",
    "全局经验中agent会话状态管理是怎么做的？请给具体路径。",
    "把全局经验里agent调用LLM与工具融合的经验路径直接列出来。",
]


CODE_GEN_QUESTIONS = [
    "请生成一个独立Python函数 summarize_tool_metrics(logs)，仅用标准库；logs是[{tool:str,duration_ms:number}]，返回每个tool的count与avg_ms；包含类型标注和示例。",
    "请生成一个独立TypeScript函数 buildStageSummary(events)，输入为{stage:string,start:number,end:number,ok:boolean}[]，输出按stage聚合的耗时与成功率。",
    "请生成一个独立Python代码片段：实现带指数退避的任务重试执行器，参数包含max_retries/base_delay，含注释和示例调用。",
    "请生成一个独立JavaScript函数 groupEvidenceToMarkdown(items)，items含project/partition/path/desc字段，输出markdown分组文本。",
    "请生成一个独立Python dataclass PathEvidence，字段project/partition/path/methods/description，带to_dict方法。",
    "请生成一个最小Flask接口示例 /api/global/search：接收query和top_k并返回JSON，包含参数校验与错误处理。",
    "请生成一个独立Python函数 merge_candidates(a,b)：按project_path去重并按score降序返回。",
    "请生成一个独立TypeScript函数 buildSessionPayload(mode, projectPath)：global时清空project_path，single_project时保留。",
    "请生成一个独立Python函数 parse_sse_events(text)：解析data: JSON行并提取workflow_complete/simple_qa_answer。",
    "请生成一个pytest单测样例：断言global模式下project_path会被置空且调用白名单检索参数。",
]


@dataclass
class CaseResult:
    index: int
    kind: str
    question: str
    http_ok: bool
    route_ok: bool
    complete_ok: bool
    answer_ok: bool
    route_code: int
    event_count: int
    reason: str

    @property
    def passed(self) -> bool:
        return self.http_ok and self.route_ok and self.complete_ok and self.answer_ok


def _event_name(evt: dict[str, Any]) -> str:
    return str(evt.get("event") or evt.get("type") or "").strip()


def _parse_sse_events(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8", errors="ignore")
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            evt = json.loads(payload)
        except Exception:
            continue
        if isinstance(evt, dict):
            events.append(evt)
    return events


def _post_stream(client, endpoint: str, payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    response = client.post(endpoint, json=payload, buffered=True)
    if response.status_code != 200:
        return response.status_code, []
    return response.status_code, _parse_sse_events(response.data)


def _extract_session_id(events: list[dict[str, Any]]) -> str:
    for evt in events:
        session_id = str(evt.get("session_id") or "").strip()
        if session_id:
            return session_id
    return ""


def _has_suspend_event(events: list[dict[str, Any]]) -> bool:
    suspend_names = {"stage_suspended", "workflow_suspend"}
    return any(_event_name(evt) in suspend_names for evt in events)


def _has_complete_event(events: list[dict[str, Any]]) -> bool:
    for evt in events:
        if _event_name(evt) != "workflow_complete":
            continue
        status = str(evt.get("status") or "completed").strip().lower()
        if status in {"", "completed", "complete"}:
            return True
    return False


def _run_case(client, *, idx: int, kind: str, question: str, mode: str, expected_route: int) -> CaseResult:
    status_code, events = _post_stream(
        client,
        "/api/session/start-stream",
        {
            "requirement": question,
            "session_mode": "global",
            "mode": mode,
        },
    )

    if status_code != 200:
        return CaseResult(
            index=idx,
            kind=kind,
            question=question,
            http_ok=False,
            route_ok=False,
            complete_ok=False,
            answer_ok=False,
            route_code=0,
            event_count=0,
            reason=f"http={status_code}",
        )

    merged_events = list(events)
    session_id = _extract_session_id(merged_events)

    if kind == "code_generation":
        resume_answers = [
            "确认：这是独立代码生成任务，不依赖现有项目私有类型定义；请使用通用字段与标准库直接完成。",
            "确认：可自行做合理默认假设（在注释写明）并继续执行到workflow_complete，不需要再次提问。",
        ]
        resume_round = 0
        while _has_suspend_event(merged_events) and not _has_complete_event(merged_events) and session_id and resume_round < 2:
            answer = resume_answers[min(resume_round, len(resume_answers) - 1)]
            _, resume_events = _post_stream(
                client,
                "/api/session/resume-stream",
                {
                    "session_id": session_id,
                    "answers": [answer],
                },
            )
            merged_events.extend(resume_events)
            resume_round += 1

    route_event = next((e for e in merged_events if _event_name(e) == "route_decision"), {})
    route_code = int(route_event.get("route_code") or 0)

    workflow_complete = _has_complete_event(merged_events)

    if expected_route == 2:
        route_ok = route_code == 2
    else:
        route_ok = (
            route_code == 1
            or (
                route_code == 0
                and any(_event_name(e) == "workflow_start" for e in merged_events)
                and not any(_event_name(e) == "simple_qa_answer" for e in merged_events)
            )
        )

    if expected_route == 2:
        answer_ok = any(
            _event_name(e) == "simple_qa_answer" and str(e.get("content") or "").strip()
            for e in merged_events
        )
    else:
        answer_ok = any(
            (
                _event_name(e) == "stage_complete"
                and str(e.get("output") or e.get("content") or "").strip()
            )
            or (
                _event_name(e) == "stream_chunk"
                and str(e.get("stage") or "") in {"code_implementation", "code_testing", "requirement_validation"}
                and str(e.get("content") or "").strip()
            )
            for e in merged_events
        )

    reason = "ok"
    if not route_ok:
        reason = "route_mismatch"
    elif not workflow_complete and _has_suspend_event(merged_events):
        reason = "still_suspended"
    elif not workflow_complete:
        reason = "no_workflow_complete"
    elif not answer_ok:
        reason = "no_effective_answer"

    return CaseResult(
        index=idx,
        kind=kind,
        question=question,
        http_ok=True,
        route_ok=route_ok,
        complete_ok=workflow_complete,
        answer_ok=answer_ok,
        route_code=route_code,
        event_count=len(merged_events),
        reason=reason,
    )


def _print_group_summary(title: str, results: list[CaseResult]) -> None:
    print(f"\n===== {title} =====")
    passed = 0
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        if r.passed:
            passed += 1
        print(
            f"[{mark}] #{r.index:02d} route={r.route_code} events={r.event_count} "
            f"http_ok={r.http_ok} route_ok={r.route_ok} complete_ok={r.complete_ok} answer_ok={r.answer_ok}"
        )
        if not r.passed:
            print(f"       reason={r.reason} q={r.question}")
    print(f"Summary: {passed}/{len(results)} passed")


def main() -> int:
    app = create_app()
    client = app.test_client()

    simple_results: list[CaseResult] = []
    for i, q in enumerate(SIMPLE_QA_QUESTIONS, start=1):
        simple_results.append(
            _run_case(client, idx=i, kind="simple_qa", question=q, mode="simple_qa", expected_route=2)
        )

    code_results: list[CaseResult] = []
    for i, q in enumerate(CODE_GEN_QUESTIONS, start=1):
        code_results.append(
            _run_case(client, idx=i, kind="code_generation", question=q, mode="code_generation", expected_route=1)
        )

    _print_group_summary("Global Simple-QA (10)", simple_results)
    _print_group_summary("Global Code-Generation (10)", code_results)

    all_results = simple_results + code_results
    all_passed = sum(1 for r in all_results if r.passed)
    print(f"\nTOTAL: {all_passed}/{len(all_results)} passed")

    return 0 if all_passed == len(all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
