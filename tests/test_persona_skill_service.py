import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.services import persona_skill_service as pss
from app.services import se_team_embedded_service as stes
from app.services import simple_qa_engine as sqe


def _sample_skill_text() -> str:
    return """---
name: huangqing-perspective
description: |
  黄箐的思维框架与表达方式。
---

## 角色扮演规则（最重要）
- 用“我”说话。
- 直接使用该角色语气。

## 身份卡
我是黄箐。

## 核心心智模型
### 模型1: 场景痛点驱动
**一句话**：研究从真实场景痛点出发。

### 模型2: 组织能力杠杆化
**一句话**：通过组织链路放大团队能力。

## 表达DNA
- 结论前置
- 短句
"""


def _prepare_storage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pss, "_PERSONA_ROOT", tmp_path / "personas")
    monkeypatch.setattr(pss, "_STATE_FILE", tmp_path / "persona_state.json")


def _create_skill_dir(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "huangqing-perspective"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_sample_skill_text(), encoding="utf-8")
    return skill_dir


def test_import_activate_compose_and_disclaimer(monkeypatch, tmp_path):
    _prepare_storage(monkeypatch, tmp_path)
    skill_dir = _create_skill_dir(tmp_path)

    imported = pss.import_persona_skill(str(skill_dir))
    assert imported["ok"] is True
    assert imported["persona"]["personaId"]

    listed = pss.list_persona_skills()
    assert len(listed) == 1
    persona_id = listed[0]["personaId"]

    activated = pss.activate_persona_skill(persona_id)
    assert activated["ok"] is True

    prompt_payload = pss.compose_system_prompt("你是代码助手")
    prompt_text = str(prompt_payload.get("systemPrompt") or "")
    assert "Persona 模式" in prompt_text
    assert "你是代码助手" in prompt_text

    first_disclaimer = pss.consume_pending_disclaimer()
    second_disclaimer = pss.consume_pending_disclaimer()
    assert "视角" in first_disclaimer
    assert second_disclaimer == ""

    deactivated = pss.deactivate_persona_skill()
    assert deactivated["ok"] is True
    assert pss.get_active_persona_state().get("persona") is None


def test_persona_skill_api_endpoints(monkeypatch, tmp_path):
    _prepare_storage(monkeypatch, tmp_path)
    skill_dir = _create_skill_dir(tmp_path)

    client = create_app().test_client()

    import_response = client.post(
        "/api/skills/persona/import",
        json={"skill_path": str(skill_dir)},
    )
    assert import_response.status_code == 200
    import_payload = import_response.get_json()
    assert import_payload["ok"] is True
    persona_id = import_payload["persona"]["personaId"]

    list_response = client.get("/api/skills/persona/list")
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert isinstance(list_payload, list)
    assert any(item.get("personaId") == persona_id for item in list_payload)

    active_before = client.get("/api/skills/persona/active")
    assert active_before.status_code == 200
    assert active_before.get_json().get("persona") is None

    activate_response = client.post(
        "/api/skills/persona/activate",
        json={"persona_id": persona_id},
    )
    assert activate_response.status_code == 200
    assert activate_response.get_json().get("persona", {}).get("personaId") == persona_id

    active_after = client.get("/api/skills/persona/active")
    assert active_after.status_code == 200
    assert active_after.get_json().get("activePersonaId") == persona_id

    deactivate_response = client.post("/api/skills/persona/deactivate", json={})
    assert deactivate_response.status_code == 200
    assert deactivate_response.get_json().get("ok") is True

    delete_response = client.delete(f"/api/skills/persona/{persona_id}")
    assert delete_response.status_code == 200
    assert delete_response.get_json().get("ok") is True


def test_simple_qa_engine_uses_persona_prompt(monkeypatch, tmp_path):
    _prepare_storage(monkeypatch, tmp_path)
    skill_dir = _create_skill_dir(tmp_path)
    imported = pss.import_persona_skill(str(skill_dir))
    persona_id = str(imported.get("persona", {}).get("personaId") or "")
    pss.activate_persona_skill(persona_id)

    captured_calls: list[dict] = []

    class FakeDeepSeekAPI:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            captured_calls.append(kwargs)
            return {
                "choices": [
                    {
                        "message": {
                            "content": "结论先说：CAT-Net 通过压缩不一致性定位可疑区域。",
                        }
                    }
                ]
            }

    monkeypatch.setattr(sqe, "_extract_ai_team_model_config", lambda: ("k", "m", "u"))
    monkeypatch.setattr(sqe, "DeepSeekAPI", FakeDeepSeekAPI)

    async def _collect_events():
        engine = sqe.SimpleQaEngine()
        events = []
        async for event in engine.run_workflow(
            session_id="sess-test",
            requirement="CAT-Net是什么",
            project_path=str(tmp_path),
            decision={"route_code": 2, "mode": "simple_qa"},
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect_events())
    answer_event = next(event for event in events if event.get("event") == "simple_qa_answer")
    answer_text = str(answer_event.get("content") or "")

    assert "我将以" in answer_text
    assert "CAT-Net" in answer_text
    assert captured_calls
    first_call = captured_calls[0]
    messages = first_call.get("messages") or []
    assert messages and "Persona 模式" in str(messages[0].get("content") or "")
    assert float(first_call.get("temperature") or 0) == 0.62


def test_generate_simple_qa_answer_fallback_respects_persona(monkeypatch, tmp_path):
    _prepare_storage(monkeypatch, tmp_path)
    skill_dir = _create_skill_dir(tmp_path)
    imported = pss.import_persona_skill(str(skill_dir))
    persona_id = str(imported.get("persona", {}).get("personaId") or "")
    pss.activate_persona_skill(persona_id)

    monkeypatch.setattr(stes, "_extract_ai_team_model_config", lambda: ("", "", ""))

    first_answer = stes.generate_simple_qa_answer("CAT-Net是什么")
    second_answer = stes.generate_simple_qa_answer("CAT-Net有什么应用场景")

    assert "我将以" in first_answer
    assert "[huangqing-perspective视角]" in first_answer
    assert "我将以" not in second_answer
    assert "[huangqing-perspective视角]" in second_answer


def test_simple_qa_global_mode_injects_concrete_experience_evidence(monkeypatch):
    captured_calls: list[dict] = []
    search_calls: list[dict] = []

    class FakeDeepSeekAPI:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            captured_calls.append(kwargs)
            return {
                "choices": [
                    {
                        "message": {
                            "content": "已基于经验库路径生成回答。",
                        }
                    }
                ]
            }

    class _State:
        mode = "global"
        selected_project_path = ""

    class FakeEngine:
        def get_session(self, _session_id):
            return _State()

    class FakeStore:
        def search(self, query, top_k=3, project_path=None, project_whitelist=None, attach_source=True, per_project_top_paths=3):
            search_calls.append(
                {
                    "query": query,
                    "top_k": top_k,
                    "project_path": project_path,
                    "project_whitelist": project_whitelist,
                    "attach_source": attach_source,
                    "per_project_top_paths": per_project_top_paths,
                }
            )
            return [
                {
                    "project_name": "learn-claude-code-main",
                    "match_score": 12.0,
                    "total_paths": 1,
                    "partitions": [
                        {
                            "partition_name": "agent-core",
                            "paths": [
                                {
                                    "path_name": "AgentPlanner.plan -> ToolExecutor.run",
                                    "path_description": "agent 任务分解与工具执行主链路",
                                    "source_project_name": "learn-claude-code-main",
                                    "source_partition_name": "agent-core",
                                    "methods": ["AgentPlanner.plan", "ToolExecutor.run"],
                                }
                            ],
                        }
                    ],
                }
            ]

    class FakePmService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            _ = force_refresh
            return {"registered": 0, "skipped": 0, "errors": 0}

        def retrieve_top_projects(self, query, top_k=4, mmr_lambda=0.7, expand_query=False):
            _ = (query, top_k, mmr_lambda, expand_query)
            return [
                {"project_name": "learn-claude-code-main", "project_path": "/tmp/learn-claude-code-main", "score": 0.9}
            ]

    monkeypatch.setattr(sqe, "_extract_ai_team_model_config", lambda: ("k", "m", "u"))
    monkeypatch.setattr(sqe, "DeepSeekAPI", FakeDeepSeekAPI)
    monkeypatch.setattr(
        sqe,
        "_load_ai_team_modules",
        lambda: {
            "get_engine": lambda: FakeEngine(),
            "get_experience_store": lambda: FakeStore(),
        },
    )

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakePmService())

    async def _collect_events():
        engine = sqe.SimpleQaEngine()
        events = []
        async for event in engine.run_workflow(
            session_id="sess-global-evidence",
            requirement="把全局经验里和agent相关的路径给我",
            project_path="",
            decision={"route_code": 2, "mode": "simple_qa"},
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect_events())
    matched_event = next(event for event in events if event.get("event") == "experience_matched")

    stage_names = [str(event.get("stage") or "") for event in events if event.get("event") == "stage_start"]

    assert matched_event.get("session_mode") == "global"
    assert matched_event.get("candidate_projects")
    assert "project_evidence_blocks" in matched_event
    assert "project_bias_summary" in matched_event
    assert search_calls
    assert int(search_calls[0].get("per_project_top_paths") or 0) >= 6
    assert int(search_calls[0].get("top_k") or 0) >= 8

    assert stage_names == [
        "requirement_analysis",
        "experience_retrieval",
        "per_project_extraction",
        "cross_project_comparison",
        "qa_advisor",
        "qa_evidence_reasoning",
        "qa_reply",
    ]
    assert captured_calls

    user_prompts = [
        str((call.get("messages") or [{}, {}])[1].get("content") or "")
        for call in captured_calls
        if len(call.get("messages") or []) >= 2
    ]
    merged_prompt = "\n".join(user_prompts)
    assert "经验库证据" in merged_prompt
    assert "AgentPlanner.plan" in merged_prompt
    assert "learn-claude-code-main / agent-core" in merged_prompt
    assert "逐库提取" in merged_prompt or "逐经验库" in merged_prompt
    assert "跨库对比" in merged_prompt or "融合策略" in merged_prompt


def test_simple_qa_fallback_payload_keeps_7_stages(monkeypatch):
    monkeypatch.setattr(stes, "generate_simple_qa_answer", lambda _q: "fallback-answer")

    events = stes.simple_qa_sse_payload(
        session_id="sess-fallback-7",
        requirement="什么是agent规划器",
        decision={"route_code": 2, "mode": "simple_qa", "reason": "timeout_fallback"},
    )

    workflow_start = next(event for event in events if event.get("event") == "workflow_start")
    assert int(workflow_start.get("total_steps") or 0) == 7

    stage_starts = [
        str(event.get("stage") or "")
        for event in events
        if event.get("event") == "stage_start"
    ]
    assert stage_starts == [
        "requirement_analysis",
        "experience_retrieval",
        "per_project_extraction",
        "cross_project_comparison",
        "qa_advisor",
        "qa_evidence_reasoning",
        "qa_reply",
    ]
