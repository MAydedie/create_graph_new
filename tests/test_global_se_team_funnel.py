"""
Tests for the two-stage global SE-Team funnel.

阶段一：ProjectManagerService 项目级粗筛
阶段二：ExperienceStore.search 在 project_whitelist 内做路径级精排

这些测试避免触发 sentence-transformers 真实加载（mock 掉 _LazyEmbeddingModel.encode），
也避免依赖磁盘上的真实经验库（构造临时目录）。
"""

from __future__ import annotations

import json
import os
import sys
import math
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CODE_CHAT_ROOT = PROJECT_ROOT.parent.parent / "借鉴项目" / "code_chat"
if str(CODE_CHAT_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_CHAT_ROOT))


def _fake_text_embedding(text: str, dim: int = 16) -> List[float]:
    """Deterministic hash-bucket embedding for tests (avoid loading real model)."""
    text = (text or "").lower()
    vec = [0.0] * dim
    for token in text.split():
        bucket = hash(token) % dim
        vec[bucket] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _make_experience_payload(project_name: str, project_path: str, partition_name: str, paths: list) -> dict:
    return {
        "project_name": project_name,
        "project_path": project_path,
        "total_paths": len(paths),
        "partitions": [
            {
                "partition_id": f"{project_name}_part1",
                "partition_name": partition_name,
                "total_paths": len(paths),
                "paths": paths,
            }
        ],
    }


def _make_path(name: str, description: str) -> dict:
    return {
        "path_name": name,
        "path_description": description,
        "leaf_node": "leaf_node",
        "path": [f"{name}.entry", f"{name}.process", f"{name}.leaf_node"],
        "input_info": {},
        "output_info": {},
        "cfg": {"nodes": {}},
        "semantics": {"functional_domain": "computer vision", "keywords": ["vision", "image"]},
    }


def _seed_experience_paths_dir(tmp_path: Path) -> Path:
    experience_paths = tmp_path / "experience_paths"
    experience_paths.mkdir(parents=True, exist_ok=True)

    # Three distinct projects so the embedding ranker has real choices.
    cv_payload = _make_experience_payload(
        project_name="vision-tool",
        project_path=str(tmp_path / "vision-tool"),
        partition_name="image processing",
        paths=[
            _make_path("detect_object", "computer vision object detection pipeline"),
            _make_path("classify_image", "image classification using neural network"),
        ],
    )
    nlp_payload = _make_experience_payload(
        project_name="nlp-engine",
        project_path=str(tmp_path / "nlp-engine"),
        partition_name="text understanding",
        paths=[
            _make_path("tokenize_text", "natural language tokenizer pipeline"),
            _make_path("classify_sentiment", "sentiment classifier on tokens"),
        ],
    )
    cv_alt_payload = _make_experience_payload(
        project_name="object-detector",
        project_path=str(tmp_path / "object-detector"),
        partition_name="vision detection",
        paths=[
            _make_path("yolo_detect", "yolo style object detection"),
            _make_path("draw_boxes", "draw bounding boxes on image"),
        ],
    )

    (experience_paths / "vision-tool.json").write_text(
        json.dumps(cv_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (experience_paths / "nlp-engine.json").write_text(
        json.dumps(nlp_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (experience_paths / "object-detector.json").write_text(
        json.dumps(cv_alt_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return experience_paths


def _patch_embedder(service):
    """Replace lazy embedder so tests do not download sentence-transformers."""
    class FakeEmbedder:
        dim = 16

        def encode(self, text: str) -> List[float]:
            return _fake_text_embedding(text, dim=16)

    service._embedder = FakeEmbedder()


def test_bulk_register_and_retrieve_top_projects(tmp_path):
    from app.services.project_manager_service import ProjectManagerService

    experience_paths_dir = _seed_experience_paths_dir(tmp_path)
    registry_path = tmp_path / "project_library" / "_global_registry.json"

    service = ProjectManagerService(
        experience_root=tmp_path,
        registry_path=registry_path,
    )
    _patch_embedder(service)

    summary = service.bulk_register_from_experience_paths(force_refresh=True)
    assert summary["registered"] == 3
    assert summary["errors"] == 0
    assert registry_path.exists(), "registry should be persisted to disk"

    # CV-flavoured query should rank vision projects higher than NLP project
    matches = service.retrieve_top_projects(
        query="object detection on images using computer vision",
        top_k=3,
        mmr_lambda=0.7,
    )
    assert matches, "should return at least one project"
    project_names = [m["project_name"] for m in matches]
    assert "nlp-engine" not in project_names[:1], "first match should not be NLP project"
    assert any(name in {"vision-tool", "object-detector"} for name in project_names[:2])


def test_search_respects_project_whitelist():
    from ai_team_system.experience import ExperienceStore, ExperienceEntry

    store = ExperienceStore()
    store._loaded = True
    cv = ExperienceEntry(
        project_name="vision-tool",
        project_path="/tmp/vision-tool",
        partitions=_make_experience_payload(
            "vision-tool", "/tmp/vision-tool", "image processing",
            [_make_path("detect_object", "computer vision object detection pipeline")],
        )["partitions"],
        total_paths=1,
        raw_data={},
    )
    nlp = ExperienceEntry(
        project_name="nlp-engine",
        project_path="/tmp/nlp-engine",
        partitions=_make_experience_payload(
            "nlp-engine", "/tmp/nlp-engine", "text understanding",
            [_make_path("tokenize_text", "natural language tokenizer pipeline")],
        )["partitions"],
        total_paths=1,
        raw_data={},
    )
    store._experiences = [cv, nlp]
    for entry in store._experiences:
        store._build_index_entry(entry)

    whitelist_only_cv = [{"project_name": "vision-tool", "project_path": "/tmp/vision-tool"}]
    results = store.search(
        query="object detection pipeline computer vision",
        top_k=5,
        project_whitelist=whitelist_only_cv,
        attach_source=True,
        per_project_top_paths=3,
    )

    assert len(results) == 1
    assert results[0]["project_name"] == "vision-tool"
    first_partition = results[0]["partitions"][0]
    first_path = first_partition["paths"][0]
    assert first_path["source_project_name"] == "vision-tool"
    assert first_path["source_partition_name"] == "image processing"


def test_engine_session_state_supports_global_mode():
    from ai_team_system.engine import WorkflowEngine

    engine = WorkflowEngine()
    state = engine.create_session("sess1", selected_project_path="/some/path", mode="global")
    assert state.mode == "global"
    assert state.selected_project_path == "/some/path"

    state_default = engine.create_session("sess2")
    assert state_default.mode == "single_project"

    state_unknown = engine.create_session("sess3", mode="weird")
    assert state_unknown.mode == "single_project"


def test_engine_global_mode_dispatches_whitelist_search(monkeypatch):
    import ai_team_system.engine as engine_mod

    calls = {}
    candidate_projects = [
        {"project_name": "vision-tool", "project_path": "/tmp/vision-tool", "score": 0.91},
        {"project_name": "object-detector", "project_path": "/tmp/object-detector", "score": 0.88},
    ]

    class FakeExperienceStore:
        def search(self, query, top_k=3, project_path=None, project_whitelist=None, attach_source=True, per_project_top_paths=3):
            calls["query"] = query
            calls["top_k"] = top_k
            calls["project_path"] = project_path
            calls["project_whitelist"] = project_whitelist
            calls["attach_source"] = attach_source
            calls["per_project_top_paths"] = per_project_top_paths
            return [{"project_name": "vision-tool", "total_paths": 1, "partitions": []}]

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 2, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            calls["pm_query"] = query
            calls["pm_top_k"] = top_k
            calls["pm_mmr_lambda"] = mmr_lambda
            calls["pm_expand_query"] = expand_query
            return candidate_projects

    monkeypatch.setattr(engine_mod, "get_experience_store", lambda: FakeExperienceStore())

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())

    engine = engine_mod.WorkflowEngine()
    state = engine.create_session("sess-global", mode="global")
    experiences, candidates = engine._retrieve_advisor_experiences(state, "object detection for image")

    assert experiences
    assert candidates == candidate_projects
    assert state.candidate_projects == candidate_projects
    assert calls["project_path"] is None
    assert calls["project_whitelist"] == candidate_projects
    assert calls["attach_source"] is True
    assert calls["per_project_top_paths"] == 3
    assert calls["pm_query"] == "object detection for image"


def test_engine_single_project_mode_keeps_locked_search(monkeypatch):
    import ai_team_system.engine as engine_mod

    calls = {}

    class FakeExperienceStore:
        def search(self, query, top_k=3, project_path=None, project_whitelist=None, attach_source=True, per_project_top_paths=3):
            calls["query"] = query
            calls["top_k"] = top_k
            calls["project_path"] = project_path
            calls["project_whitelist"] = project_whitelist
            return [{"project_name": "locked-project", "total_paths": 1, "partitions": []}]

    monkeypatch.setattr(engine_mod, "get_experience_store", lambda: FakeExperienceStore())

    engine = engine_mod.WorkflowEngine()
    state = engine.create_session("sess-locked", selected_project_path="/repo/locked", mode="single_project")
    experiences, candidates = engine._retrieve_advisor_experiences(state, "any query")

    assert experiences
    assert candidates == []
    assert calls["project_path"] == "/repo/locked"
    assert calls["project_whitelist"] is None


def test_se_team_api_global_mode_clears_project_path():
    from app import create_app

    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/session/start",
        json={"project_path": "/already/locked", "mode": "global"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["mode"] == "global"
    assert data["status"] == "created"
    assert data.get("session_id")


def test_se_team_codegen_resolves_single_valid_candidate_path(monkeypatch, tmp_path):
    from app import create_app
    from app.routes import se_team_api_routes

    app = create_app()
    client = app.test_client()
    project_dir = tmp_path / "EvoSkill-main"
    project_dir.mkdir(parents=True, exist_ok=True)
    captured = {}

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 1, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            captured["query"] = query
            return [
                {
                    "project_name": "EvoSkill-main",
                    "project_path": str(project_dir),
                    "source_file": "EvoSkill-main_dcc38938.json",
                    "score": 0.97,
                    "summary": "EvoSkill 项目，包含服务函数和路由注册风格。",
                }
            ]

    async def _fake_start_opencode_workflow_stream(session_id, requirement, project_path, support_context=None):
        yield {
            "event": "workflow_complete",
            "type": "workflow_complete",
            "status": "completed",
            "session_id": session_id,
            "project_path": project_path,
        }

    class FakeDeepSeekAPI:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            captured["messages"] = kwargs.get("messages") or []
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"selected_index": 1, "reason": "用户明确要求参考 EvoSkill 项目", "confidence": 0.96}'
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        se_team_api_routes,
        "start_opencode_workflow_stream",
        _fake_start_opencode_workflow_stream,
    )
    monkeypatch.setattr(se_team_api_routes, "DeepSeekAPI", FakeDeepSeekAPI)
    monkeypatch.setattr(se_team_api_routes, "_extract_ai_team_model_config", lambda: ("k", "m", "u"))

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())

    response = client.post(
        "/api/session/start-stream",
        json={
            "requirement": "请参考经验库中 evoskill 项目的代码组织方式生成最小功能模板",
            "session_mode": "global",
        },
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    assert events[-1]["event"] == "workflow_complete"
    assert os.path.normpath(events[-1]["project_path"]) == os.path.normpath(str(project_dir))
    assert captured["query"]
    assert captured["messages"]


def test_se_team_codegen_rejects_multiple_valid_candidate_paths(monkeypatch, tmp_path):
    from app import create_app
    from app.routes import se_team_api_routes

    app = create_app()
    client = app.test_client()
    first_project = tmp_path / "EvoSkill-main"
    second_project = tmp_path / "OtherSkill-main"
    first_project.mkdir(parents=True, exist_ok=True)
    second_project.mkdir(parents=True, exist_ok=True)

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 2, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            return [
                {"project_name": "evoskill", "project_path": str(first_project), "score": 0.95, "summary": "first"},
                {"project_name": "other-skill", "project_path": str(second_project), "score": 0.93, "summary": "second"},
            ]

    class FakeDeepSeekAPI:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"selected_index": null, "reason": "两个候选项目都可能相关", "confidence": 0.41}'
                        }
                    }
                ]
            }

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())
    monkeypatch.setattr(se_team_api_routes, "DeepSeekAPI", FakeDeepSeekAPI)
    monkeypatch.setattr(se_team_api_routes, "_extract_ai_team_model_config", lambda: ("k", "m", "u"))

    response = client.post(
        "/api/session/start-stream",
        json={
            "requirement": "请参考经验库项目生成最小新增功能模板",
            "session_mode": "global",
        },
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    assert events[-1]["event"] == "workflow_error"
    assert "语义判定未能唯一锁定项目" in events[-1]["reason"]


def test_se_team_codegen_global_mode_uses_current_project_path_before_semantic_candidates(monkeypatch, tmp_path):
    from app import create_app
    from app.routes import se_team_api_routes

    app = create_app()
    client = app.test_client()
    current_project = tmp_path / "create_graph"
    first_project = tmp_path / "EvoSkill-main"
    second_project = tmp_path / "ProjectManager"
    current_project.mkdir(parents=True, exist_ok=True)
    first_project.mkdir(parents=True, exist_ok=True)
    second_project.mkdir(parents=True, exist_ok=True)
    captured = {}

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 2, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            return [
                {"project_name": "EvoSkill-main", "project_path": str(first_project), "score": 0.95, "summary": "first"},
                {"project_name": "ProjectManager", "project_path": str(second_project), "score": 0.93, "summary": "second"},
            ]

    async def _fake_start_opencode_workflow_stream(session_id, requirement, project_path, support_context=None):
        captured["project_path"] = project_path
        captured["support_context"] = support_context or {}
        yield {
            "event": "workflow_complete",
            "type": "workflow_complete",
            "status": "completed",
            "session_id": session_id,
            "project_path": project_path,
        }

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())
    monkeypatch.setattr(se_team_api_routes, "_extract_ai_team_model_config", lambda: ("", "", ""))
    monkeypatch.setattr(se_team_api_routes, "start_opencode_workflow_stream", _fake_start_opencode_workflow_stream)

    response = client.post(
        "/api/session/start-stream",
        json={
            "requirement": "请参考经验库里的多个项目经验，修改当前项目的代码生成入口",
            "session_mode": "global",
            "project_path": str(current_project),
        },
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    assert events[-1]["event"] == "workflow_complete"
    assert os.path.normpath(captured["project_path"]) == os.path.normpath(str(current_project))
    assert captured["support_context"]["resolution_source"] == "explicit_project_path"
    assert captured["support_context"]["bound_project_path"] == captured["project_path"]


def test_se_team_codegen_single_project_ui_keeps_global_experience_context(monkeypatch, tmp_path):
    from app import create_app
    from app.routes import se_team_api_routes

    app = create_app()
    client = app.test_client()
    current_project = tmp_path / "create_graph"
    first_project = tmp_path / "EvoSkill-main"
    second_project = tmp_path / "ProjectManager"
    current_project.mkdir(parents=True, exist_ok=True)
    first_project.mkdir(parents=True, exist_ok=True)
    second_project.mkdir(parents=True, exist_ok=True)
    captured = {}

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 2, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            return [
                {"project_name": "EvoSkill-main", "project_path": str(first_project), "score": 0.95, "summary": "first"},
                {"project_name": "ProjectManager", "project_path": str(second_project), "score": 0.93, "summary": "second"},
            ]

    async def _fake_start_opencode_workflow_stream(session_id, requirement, project_path, support_context=None):
        captured["project_path"] = project_path
        captured["support_context"] = support_context or {}
        yield {
            "event": "workflow_complete",
            "type": "workflow_complete",
            "status": "completed",
            "session_id": session_id,
            "project_path": project_path,
        }

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())
    monkeypatch.setattr(se_team_api_routes, "_extract_ai_team_model_config", lambda: ("", "", ""))
    monkeypatch.setattr(se_team_api_routes, "start_opencode_workflow_stream", _fake_start_opencode_workflow_stream)

    response = client.post(
        "/api/session/start-stream",
        json={
            "requirement": "请参考经验库里的多个项目经验，修改当前项目的代码生成入口",
            "session_mode": "single_project",
            "project_path": str(current_project),
        },
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    assert events[-1]["event"] == "workflow_complete"
    assert os.path.normpath(captured["project_path"]) == os.path.normpath(str(current_project))
    assert captured["support_context"]["session_mode"] == "global"
    assert [item["project_name"] for item in captured["support_context"]["candidate_projects"]] == [
        "EvoSkill-main",
        "ProjectManager",
    ]


def test_se_team_codegen_explicit_project_name_uses_registry_even_when_semantic_rank_misses(monkeypatch, tmp_path):
    from app import create_app
    from app.routes import se_team_api_routes

    app = create_app()
    client = app.test_client()
    evoskill_project = tmp_path / "EvoSkill-main"
    other_project = tmp_path / "ProjectManager"
    evoskill_project.mkdir(parents=True, exist_ok=True)
    other_project.mkdir(parents=True, exist_ok=True)
    captured = {}

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 2, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            return [
                {"project_name": "ProjectManager", "project_path": str(other_project), "score": 0.99, "summary": "semantic top"},
            ]

        def list_registry(self):
            return [
                {
                    "project_name": "EvoSkill-main",
                    "project_path": str(evoskill_project),
                    "source_file": "EvoSkill-main_dcc38938.json",
                    "score": None,
                    "summary": "explicit registry match",
                },
                {"project_name": "ProjectManager", "project_path": str(other_project), "source_file": "ProjectManager.json"},
            ]

    async def _fake_start_opencode_workflow_stream(session_id, requirement, project_path, support_context=None):
        captured["project_path"] = project_path
        captured["support_context"] = support_context or {}
        yield {
            "event": "workflow_complete",
            "type": "workflow_complete",
            "status": "completed",
            "session_id": session_id,
            "project_path": project_path,
        }

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())
    monkeypatch.setattr(se_team_api_routes, "_extract_ai_team_model_config", lambda: ("", "", ""))
    monkeypatch.setattr(se_team_api_routes, "start_opencode_workflow_stream", _fake_start_opencode_workflow_stream)

    response = client.post(
        "/api/session/start-stream",
        json={
            "requirement": "请参考经验库中 evoskill 项目的代码组织方式，仿照其中服务函数 + 路由注册的实现风格生成模板",
            "session_mode": "global",
        },
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    assert events[-1]["event"] == "workflow_complete"
    assert os.path.normpath(captured["project_path"]) == os.path.normpath(str(evoskill_project))
    assert captured["support_context"]["candidate_projects"][0]["project_name"] == "EvoSkill-main"


def test_se_team_codegen_prefers_alias_match_from_real_project_name(monkeypatch, tmp_path):
    from app import create_app
    from app.routes import se_team_api_routes

    app = create_app()
    client = app.test_client()
    evoskill_project = tmp_path / "EvoSkill-main"
    other_project = tmp_path / "OtherSkill-main"
    evoskill_project.mkdir(parents=True, exist_ok=True)
    other_project.mkdir(parents=True, exist_ok=True)

    async def _fake_start_opencode_workflow_stream(session_id, requirement, project_path, support_context=None):
        yield {
            "event": "workflow_complete",
            "type": "workflow_complete",
            "status": "completed",
            "session_id": session_id,
            "project_path": project_path,
        }

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 2, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            return [
                {
                    "project_name": "OtherSkill-main",
                    "project_path": str(other_project),
                    "source_file": "OtherSkill-main_abcd1234.json",
                    "score": 0.99,
                    "summary": "other summary",
                },
                {
                    "project_name": "EvoSkill-main",
                    "project_path": str(evoskill_project),
                    "source_file": "EvoSkill-main_dcc38938.json",
                    "score": 0.95,
                    "summary": "evoskill summary",
                },
            ]

    class FakeDeepSeekAPI:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"selected_index": 2, "reason": "用户明确要求参考 evoskill 项目组织方式", "confidence": 0.94}'
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        se_team_api_routes,
        "start_opencode_workflow_stream",
        _fake_start_opencode_workflow_stream,
    )
    monkeypatch.setattr(se_team_api_routes, "DeepSeekAPI", FakeDeepSeekAPI)
    monkeypatch.setattr(se_team_api_routes, "_extract_ai_team_model_config", lambda: ("k", "m", "u"))

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())

    response = client.post(
        "/api/session/start-stream",
        json={
            "requirement": "请参考经验库中 evoskill 项目的代码组织方式，仿照其中服务函数 + 路由注册的实现风格生成模板",
            "session_mode": "global",
        },
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    assert events[-1]["event"] == "workflow_complete"
    assert os.path.normpath(events[-1]["project_path"]) == os.path.normpath(str(evoskill_project))


def test_se_team_codegen_rejects_multiple_candidates_without_model(monkeypatch, tmp_path):
    from app import create_app
    from app.routes import se_team_api_routes

    app = create_app()
    client = app.test_client()
    first_project = tmp_path / "first-project"
    second_project = tmp_path / "second-project"
    first_project.mkdir(parents=True, exist_ok=True)
    second_project.mkdir(parents=True, exist_ok=True)

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 2, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            return [
                {"project_name": "first-project", "project_path": str(first_project), "score": 0.9, "summary": "first"},
                {"project_name": "second-project", "project_path": str(second_project), "score": 0.89, "summary": "second"},
            ]

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())
    monkeypatch.setattr(se_team_api_routes, "_extract_ai_team_model_config", lambda: ("", "", ""))

    response = client.post(
        "/api/session/start-stream",
        json={
            "requirement": "请参考经验库中的项目生成模板",
            "session_mode": "global",
        },
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    assert events[-1]["event"] == "workflow_error"
    assert "未配置可用模型进行语义判定" in events[-1]["reason"]


def test_se_team_codegen_rejects_stale_candidate_paths(monkeypatch):
    from app import create_app

    app = create_app()
    client = app.test_client()

    class FakeProjectManagerService:
        def bulk_register_from_experience_paths(self, force_refresh=False):
            return {"registered": 0, "skipped": 1, "errors": 0}

        def retrieve_top_projects(self, query, top_k=3, mmr_lambda=0.7, expand_query=False, expand_query_fn=None):
            return [
                {
                    "project_name": "evoskill",
                    "project_path": str(Path("D:/definitely/missing/path")),
                    "score": 0.97,
                }
            ]

    import app.services.project_manager_service as pm_module

    monkeypatch.setattr(pm_module, "get_project_manager_service", lambda: FakeProjectManagerService())

    response = client.post(
        "/api/session/start-stream",
        json={
            "requirement": "请参考经验库中 evoskill 项目的代码组织方式生成最小功能模板",
            "session_mode": "global",
        },
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))

    assert events[-1]["event"] == "workflow_error"
    assert "未能从经验库/项目库解析到有效的绝对路径" in events[-1]["reason"]


def test_se_team_resume_stream_stops_after_terminal_event(monkeypatch):
    from app import create_app
    from app.routes import se_team_api_routes

    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(se_team_api_routes, "resume_workflow_stream", lambda session_id, answers: object())

    def _fake_iterate(_async_iter, first_event_timeout_seconds=None):
        yield {
            "event": "workflow_complete",
            "type": "workflow_complete",
            "status": "completed",
            "session_id": "sess-resume",
        }
        yield {
            "event": "stream_chunk",
            "type": "stream_chunk",
            "stage": "code_implementation",
            "content": "should not be emitted after completion",
            "session_id": "sess-resume",
        }

    monkeypatch.setattr(se_team_api_routes, "iterate_async_generator", _fake_iterate)

    response = client.post(
        "/api/session/resume-stream",
        json={"session_id": "sess-resume", "answers": ["继续执行"]},
        buffered=True,
    )

    assert response.status_code == 200
    events = []
    for line in response.data.decode("utf-8", errors="ignore").splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    assert [evt.get("event") or evt.get("type") for evt in events] == ["workflow_complete"]
