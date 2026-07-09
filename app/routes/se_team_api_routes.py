from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
import json
import os
import re
from typing import Iterator

from flask import Blueprint, Response, jsonify, request, send_file

from llm.rag_core.llm_api import DeepSeekAPI

from app.services import conversation_service as conversation_memory_service
from app.services.simple_qa_engine import SimpleQaEngine
from app.services.se_team_embedded_service import (
    _extract_ai_team_model_config,
    artifact_payload,
    create_session,
    decide_request_mode,
    ensure_stream_session,
    experiences_payload,
    format_sse_event,
    get_session_scope,
    iterate_async_generator,
    start_opencode_workflow_stream,
    simple_qa_sse_payload,
    resolve_session_file,
    session_files_payload,
    session_payload,
    start_workflow_stream,
    resume_workflow_stream,
    update_model_config,
    workflow_steps_payload,
)

se_team_api_bp = Blueprint("se_team_api", __name__, url_prefix="/api")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_existing_project_path(project_path: str) -> str:
    raw_value = str(project_path or "").strip()
    if not raw_value:
        return ""
    if not os.path.isabs(raw_value):
        return ""
    normalized = os.path.normpath(os.path.abspath(raw_value))
    if not os.path.isdir(normalized):
        return ""
    return normalized


def _strip_thinking_block(text: str) -> str:
    return re.sub(r"<think>[\s\S]*?</think>\s*", "", str(text or ""), flags=re.IGNORECASE).strip()


def _extract_json_object(text: str) -> dict:
    cleaned = _strip_thinking_block(text)
    if not cleaned:
        return {}
    fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned, flags=re.IGNORECASE)
    candidate = fenced_match.group(1) if fenced_match else cleaned
    direct_match = re.search(r"\{[\s\S]*\}", candidate)
    if not direct_match:
        return {}
    try:
        parsed = json.loads(direct_match.group(0))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _project_alias_token(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "").lower())


def _candidate_matches_requirement(requirement: str, candidate: dict) -> bool:
    query_token = _project_alias_token(requirement)
    if not query_token:
        return False
    aliases = []
    for key in ("project_name", "source_file", "project_path"):
        value = str(candidate.get(key) or "").strip()
        if value:
            aliases.append(_project_alias_token(value))
            aliases.append(_project_alias_token(os.path.basename(value)))
    for alias in aliases:
        if alias and (alias in query_token or query_token in alias):
            return True
        if alias.endswith("main") and alias[:-4] and alias[:-4] in query_token:
            return True
    return False


def _dedupe_project_candidates(candidate_projects: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in candidate_projects:
        if not isinstance(item, dict):
            continue
        key = _normalize_existing_project_path(item.get("project_path") or "") or str(item.get("project_path") or item.get("source_file") or item.get("project_name") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _collect_explicit_project_name_candidates(requirement: str) -> list[dict]:
    try:
        from app.services.project_manager_service import get_project_manager_service

        pm_service = get_project_manager_service()
        pm_service.bulk_register_from_experience_paths(force_refresh=False)
        registry_items = pm_service.list_registry()
    except Exception:
        registry_items = []

    explicit_matches = []
    for item in registry_items:
        if isinstance(item, dict) and _candidate_matches_requirement(requirement, item):
            explicit_matches.append(item)
    return explicit_matches


def _collect_valid_code_generation_candidates(requirement: str) -> list[dict]:
    try:
        from app.services.project_manager_service import get_project_manager_service

        pm_service = get_project_manager_service()
        pm_service.bulk_register_from_experience_paths(force_refresh=False)
        candidate_projects = pm_service.retrieve_top_projects(
            query=requirement,
            top_k=6,
            mmr_lambda=0.7,
            expand_query=False,
        ) or []
    except Exception:
        candidate_projects = []

    explicit_matches = _collect_explicit_project_name_candidates(requirement)
    return _normalize_code_generation_candidates(_dedupe_project_candidates([*explicit_matches, *candidate_projects]))


def _normalize_code_generation_candidates(candidate_projects: list[dict]) -> list[dict]:
    valid_candidates = []
    for item in candidate_projects:
        if not isinstance(item, dict):
            continue
        candidate_path = _normalize_existing_project_path(item.get("project_path") or "")
        if not candidate_path:
            continue
        valid_candidates.append(
            {
                "project_name": str(item.get("project_name") or "").strip(),
                "project_path": candidate_path,
                "score": item.get("score"),
                "source_file": str(item.get("source_file") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
            }
        )
    return valid_candidates


def _build_code_generation_support_context(
    requirement: str,
    retrieval_project_path: str,
    session_mode: str,
) -> dict:
    engine = SimpleQaEngine()
    experiences, candidate_projects = engine._search_experience(
        requirement,
        retrieval_project_path,
        session_mode=session_mode,
    )
    explicit_matches = _collect_explicit_project_name_candidates(requirement)
    candidate_projects = _dedupe_project_candidates([*explicit_matches, *candidate_projects])
    return {
        "session_mode": session_mode,
        "candidate_projects": candidate_projects,
        "experience_summary": engine._build_experience_summary(
            experiences,
            candidate_projects=candidate_projects,
            session_mode=session_mode,
        ),
        "experience_evidence": engine._build_experience_evidence(experiences),
    }


def _find_candidate_by_path(candidate_projects: list[dict], project_path: str) -> dict:
    normalized_project_path = _normalize_existing_project_path(project_path)
    if not normalized_project_path:
        return {}
    for item in candidate_projects:
        candidate_path = _normalize_existing_project_path(item.get("project_path") or "")
        if candidate_path and candidate_path == normalized_project_path:
            return item
    return {}


def _semantic_select_project_path(requirement: str, candidate_projects: list[dict]) -> tuple[str, str]:
    unique_paths: list[str] = []
    for item in candidate_projects:
        candidate_path = str(item.get("project_path") or "").strip()
        if candidate_path and candidate_path not in unique_paths:
            unique_paths.append(candidate_path)

    if not unique_paths:
        return "", "代码生成/修改任务必须绑定具体项目路径，当前未能从经验库/项目库解析到有效的绝对路径。"

    api_key, model_name, base_url = _extract_ai_team_model_config()
    if not (api_key and model_name and base_url):
        if len(unique_paths) == 1:
            return unique_paths[0], ""
        candidate_names = [str(item.get("project_name") or item.get("project_path") or "") for item in candidate_projects[:4]]
        return "", f"代码生成/修改任务必须绑定具体项目路径，当前存在多个候选项目且未配置可用模型进行语义判定：{' / '.join(candidate_names)}"

    candidate_blocks = []
    for index, item in enumerate(candidate_projects, start=1):
        candidate_blocks.append(
            "\n".join(
                [
                    f"候选 {index}",
                    f"project_name: {str(item.get('project_name') or '').strip()}",
                    f"project_path: {str(item.get('project_path') or '').strip()}",
                    f"source_file: {str(item.get('source_file') or '').strip()}",
                    f"score: {item.get('score')}",
                    f"summary: {str(item.get('summary') or '').strip()[:500]}",
                ]
            )
        )

    system_prompt = (
        "你是 SE-Team 的项目选择顾问。"
        "你的唯一任务是根据用户需求，在给定候选项目中选出最适合进入 OpenCode 的唯一项目。"
        "你只能从候选列表里选，不能编造新项目。"
        "如果无法唯一确定，必须返回 selected_index 为 null。"
        "输出必须是 JSON：{\"selected_index\": number|null, \"reason\": string, \"confidence\": number}."
    )
    user_prompt = (
        f"用户需求：\n{str(requirement or '').strip()}\n\n"
        "候选项目如下：\n"
        + "\n\n".join(candidate_blocks)
        + "\n\n请只返回 JSON，不要输出其他内容。"
    )

    try:
        client = DeepSeekAPI(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            timeout=20,
        )
        response = client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=220,
            timeout=20,
        )
        choices = response.get("choices") if isinstance(response, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        payload = _extract_json_object((message or {}).get("content") or "")
    except Exception:
        payload = {}

    raw_index = payload.get("selected_index") if isinstance(payload, dict) else None
    try:
        selected_index = int(str(raw_index)) if raw_index is not None else None
    except (TypeError, ValueError):
        selected_index = None

    if selected_index is None:
        candidate_names = [str(item.get("project_name") or item.get("project_path") or "") for item in candidate_projects[:4]]
        reason = str(payload.get("reason") or "语义判定未能唯一确定目标项目").strip()
        return "", f"代码生成/修改任务必须绑定具体项目路径，当前语义判定未能唯一锁定项目：{' / '.join(candidate_names)}。{reason}"

    selected_offset = selected_index - 1
    if selected_offset < 0 or selected_offset >= len(candidate_projects):
        return "", "代码生成/修改任务必须绑定具体项目路径，当前语义判定结果无效，未能锁定候选项目。"

    selected_path = _normalize_existing_project_path(candidate_projects[selected_offset].get("project_path") or "")
    if not selected_path:
        return "", "代码生成/修改任务必须绑定具体项目路径，当前语义判定命中的项目路径无效或不存在。"
    return selected_path, ""


def _resolve_code_generation_project_path(
    requirement: str,
    project_path: str,
    session_project_path: str = "",
    candidate_projects: list[dict] | None = None,
) -> tuple[str, str, str]:
    normalized_explicit_path = _normalize_existing_project_path(project_path)
    if normalized_explicit_path:
        return normalized_explicit_path, "", "explicit_project_path"
    if str(project_path or "").strip():
        return "", f"代码生成/修改任务必须绑定具体项目路径，当前提供的 project_path 无效或不存在：{str(project_path).strip()}", "invalid_explicit_project_path"

    normalized_session_path = _normalize_existing_project_path(session_project_path)
    if normalized_session_path:
        return normalized_session_path, "", "session_selected_project_path"

    valid_candidates = _normalize_code_generation_candidates(candidate_projects) if isinstance(candidate_projects, list) and candidate_projects else _collect_valid_code_generation_candidates(requirement)
    explicit_valid_candidates = [item for item in valid_candidates if _candidate_matches_requirement(requirement, item)]
    if explicit_valid_candidates:
        return explicit_valid_candidates[0]["project_path"], "", "explicit_project_name_match"
    resolved_path, error = _semantic_select_project_path(requirement, valid_candidates)
    return resolved_path, error, "semantic_candidate_selection"


def _apply_runtime_llm_config(payload: dict) -> None:
    """
    如果请求体里带了 llm_config，就把用户在前端 Settings 里配的
    api_key / base_url / model 推到后端 ai-team 全局 config，
    这样 SE-Team 流程（_extract_ai_team_model_config）会用用户自己的 key。

    期望格式：
      llm_config = {
        "provider": "openai" | "deepseek" | ...,
        "api_key": "sk-...",
        "base_url": "https://...",
        "model":    "gpt-4o",
      }
    """
    if not isinstance(payload, dict):
        return
    raw = payload.get("llm_config")
    if not isinstance(raw, dict):
        raw = payload.get("llmConfig")
    if not isinstance(raw, dict):
        return

    api_key = str(raw.get("api_key") or raw.get("apiKey") or "").strip()
    base_url = str(raw.get("base_url") or raw.get("baseUrl") or "").strip()
    model = str(raw.get("model") or "").strip()
    if not api_key:
        return
    try:
        update_model_config(
            api_key=api_key,
            model_name=model,
            base_url=base_url,
        )
    except Exception:
        # 配置同步失败不应阻塞主流程 —— 引擎会回退到环境变量配置
        pass


@se_team_api_bp.route("/workflow/steps", methods=["GET"])
def se_team_workflow_steps():
    return jsonify(workflow_steps_payload())


@se_team_api_bp.route("/experiences", methods=["GET"])
def se_team_experiences():
    return jsonify(experiences_payload())


@se_team_api_bp.route("/session/start", methods=["POST"])
def se_team_start_session():
    payload = request.get_json(silent=True) or {}
    _apply_runtime_llm_config(payload)
    project_path = str(payload.get("project_path") or "").strip()
    mode = str(payload.get("mode") or "single_project").strip().lower()
    if mode not in {"single_project", "global"}:
        mode = "single_project"
    session_id = create_session(project_path=project_path, mode=mode)
    return jsonify({"session_id": session_id, "status": "created", "mode": mode})


@se_team_api_bp.route("/session/start-stream", methods=["POST"])
def se_team_start_stream():
    payload = request.get_json(silent=True) or {}
    _apply_runtime_llm_config(payload)
    requirement = str(payload.get("requirement") or "").strip()
    if not requirement:
        return jsonify({"detail": "requirement is required"}), 400

    requested_project_path = str(payload.get("project_path") or "").strip()
    session_mode = str(payload.get("session_mode") or payload.get("workflow_mode") or "").strip().lower()
    if session_mode not in {"single_project", "global"}:
        session_mode = "global" if (not requested_project_path) else "single_project"

    workflow_project_path = requested_project_path if session_mode == "single_project" else ""

    session_id = ensure_stream_session(
        session_id=str(payload.get("session_id") or "").strip(),
        project_path=requested_project_path,
        mode=session_mode,
    )
    session_scope = get_session_scope(session_id)
    session_selected_project_path = str(session_scope.get("selected_project_path") or "").strip()

    history: list[dict[str, str]] = []
    try:
        conversation_memory_service.data_accessor.ensure_conversation(session_id, requested_project_path or session_selected_project_path)
        conversation_memory_service.data_accessor.append_conversation_message(
            session_id,
            {
                "role": "user",
                "content": requirement,
                "sessionId": session_id,
            },
        )
        history = conversation_memory_service._history_for_prompt(session_id, limit=10)
    except Exception:
        history = []

    preferred_mode = str(payload.get("mode") or "").strip()
    decision = decide_request_mode(requirement=requirement, preferred_mode=preferred_mode)
    route_code = int(decision.get("route_code") or 1)

    def generate() -> Iterator[str]:
        if route_code == 2:
            started_stages: set[str] = set()
            completed_stages: set[str] = set()
            final_answer = ""

            def emit_and_track(event: dict) -> str:
                nonlocal final_answer
                event_type = str(event.get("event") or event.get("type") or "").strip()
                stage_name = str(event.get("stage") or "").strip()
                if event_type == "stage_start" and stage_name:
                    started_stages.add(stage_name)
                elif event_type == "stage_complete" and stage_name:
                    completed_stages.add(stage_name)
                elif event_type == "simple_qa_answer":
                    final_answer = str(event.get("content") or "").strip()
                return format_sse_event(event)

            def emit_fallback(reason: str):
                fallback_decision = dict(decision)
                fallback_decision["reason"] = reason
                fallback_events = simple_qa_sse_payload(
                    session_id=session_id,
                    requirement=requirement,
                    decision=fallback_decision,
                )
                for event in fallback_events:
                    event_type = str(event.get("event") or event.get("type") or "").strip()
                    stage_name = str(event.get("stage") or "").strip()

                    if started_stages:
                        if event_type in {"route_decision", "workflow_start"}:
                            continue
                        if stage_name in completed_stages:
                            continue
                        if event_type == "stage_start" and stage_name in started_stages:
                            continue

                    yield emit_and_track(event)

            async_iter = SimpleQaEngine().run_workflow(
                session_id=session_id,
                requirement=requirement,
                project_path=workflow_project_path,
                decision=decision,
                history=history,
            )
            try:
                for event in iterate_async_generator(
                    async_iter,
                    first_event_timeout_seconds=12,
                    per_event_timeout_seconds=600,
                ):
                    yield emit_and_track(event)
            except FuturesTimeoutError:
                yield from emit_fallback("simple qa engine timeout; fallback payload")
            except Exception as exc:
                yield from emit_fallback(f"simple qa engine failed; fallback payload: {str(exc)}")
            if final_answer:
                try:
                    conversation_memory_service.data_accessor.append_conversation_message(
                        session_id,
                        {
                            "role": "assistant",
                            "content": final_answer,
                            "sessionId": session_id,
                        },
                    )
                    conversation_memory_service._post_turn_housekeeping(
                        session_id,
                        user_query=requirement,
                        project_path=workflow_project_path,
                        action="general_chat",
                        task_mode=None,
                        reason="se_team_simple_qa",
                        clarification_context=None,
                    )
                except Exception:
                    pass
            return

        support_context = _build_code_generation_support_context(
            requirement=requirement,
            retrieval_project_path="",
            session_mode="global",
        )
        resolved_project_path, resolution_error, resolution_source = _resolve_code_generation_project_path(
            requirement=requirement,
            project_path=requested_project_path,
            session_project_path=session_selected_project_path,
            candidate_projects=support_context.get("candidate_projects") or [],
        )
        if resolution_error:
            yield format_sse_event(
                {
                    "event": "workflow_error",
                    "type": "workflow_error",
                    "status": "failed",
                    "mode": "code_generation",
                    "session_id": session_id,
                    "reason": resolution_error,
                    "timestamp": _utcnow_iso(),
                }
            )
            return

        selected_candidate = _find_candidate_by_path(
            support_context.get("candidate_projects") or [],
            resolved_project_path,
        )
        opencode_support_context = {
            **support_context,
            "resolution_source": resolution_source,
            "bound_project_path": resolved_project_path,
            "bound_project_name": str(selected_candidate.get("project_name") or os.path.basename(resolved_project_path) or "").strip(),
            "session_selected_project_path": session_selected_project_path,
        }

        async_iter = start_opencode_workflow_stream(
            session_id=session_id,
            requirement=requirement,
            project_path=resolved_project_path,
            support_context=opencode_support_context,
        )
        for event in iterate_async_generator(async_iter):
            yield format_sse_event(event)
            event_type = str(event.get("event") or event.get("type") or "").strip()
            if event_type in {"stage_suspended", "workflow_suspend", "stage_error", "workflow_complete", "workflow_error"}:
                break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@se_team_api_bp.route("/workflow/decide-route", methods=["POST"])
def se_team_decide_route():
    payload = request.get_json(silent=True) or {}
    requirement = str(payload.get("requirement") or "").strip()
    preferred_mode = str(payload.get("mode") or "").strip()

    if not requirement and preferred_mode.strip().lower() not in {"simple_qa", "code_generation", "1", "2"}:
        return jsonify({"detail": "requirement is required"}), 400

    decision = decide_request_mode(requirement=requirement, preferred_mode=preferred_mode)
    return jsonify(decision)


@se_team_api_bp.route("/session/resume-stream", methods=["POST"])
def se_team_resume_stream():
    payload = request.get_json(silent=True) or {}
    session_id = str(payload.get("session_id") or "").strip()
    answers = payload.get("answers") or []

    if not session_id:
        return jsonify({"detail": "session_id is required"}), 400
    if not isinstance(answers, list):
        return jsonify({"detail": "answers must be a list"}), 400

    def generate() -> Iterator[str]:
        normalized_answers = [str(answer) for answer in answers]
        async_iter = resume_workflow_stream(
            session_id=session_id,
            answers=normalized_answers,
        )
        try:
            for event in iterate_async_generator(async_iter, first_event_timeout_seconds=12):
                yield format_sse_event(event)
                event_type = str(event.get("event") or event.get("type") or "").strip()
                if event_type in {"stage_suspended", "workflow_suspend", "stage_error", "workflow_complete", "workflow_error"}:
                    break
        except FuturesTimeoutError:
            fallback_requirement = str(normalized_answers[-1] if normalized_answers else "").strip()
            if not fallback_requirement:
                yield format_sse_event(
                    {
                        "event": "workflow_error",
                        "status": "failed",
                        "reason": "resume timeout and no fallback requirement",
                        "session_id": session_id,
                    }
                )
                return

            yield format_sse_event(
                {
                    "event": "resume_fallback",
                    "status": "fallback_to_direct_requirement",
                    "reason": "resume stream timeout; use latest user answer as final requirement",
                    "session_id": session_id,
                    "requirement": fallback_requirement,
                }
            )
            fallback_iter = start_workflow_stream(session_id=session_id, requirement=fallback_requirement)
            for event in iterate_async_generator(fallback_iter):
                yield format_sse_event(event)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@se_team_api_bp.route("/session/<session_id>", methods=["GET"])
def se_team_session(session_id: str):
    payload = session_payload(session_id)
    if payload is None:
        return jsonify({"detail": "Session not found"}), 404
    return jsonify(payload)


@se_team_api_bp.route("/session/<session_id>/artifact/<key>", methods=["GET"])
def se_team_session_artifact(session_id: str, key: str):
    payload = artifact_payload(session_id, key)
    if payload is None:
        return jsonify({"detail": "Artifact not found"}), 404
    return jsonify(payload)


@se_team_api_bp.route("/session/<session_id>/files", methods=["GET"])
def se_team_session_files(session_id: str):
    return jsonify(session_files_payload(session_id))


@se_team_api_bp.route("/session/<session_id>/files/<path:file_path>", methods=["GET"])
def se_team_session_file(session_id: str, file_path: str):
    try:
        full_path = resolve_session_file(session_id, file_path)
    except ValueError:
        return jsonify({"detail": "Invalid file path"}), 400

    if not full_path.exists() or not full_path.is_file():
        return jsonify({"detail": "File not found"}), 404
    return send_file(str(full_path), as_attachment=True)


@se_team_api_bp.route("/config", methods=["POST"])
def se_team_update_config():
    payload = request.get_json(silent=True) or {}
    api_key = str(payload.get("api_key") or "").strip()
    model_name = str(payload.get("model_name") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    return jsonify(update_model_config(api_key=api_key, model_name=model_name, base_url=base_url))


@se_team_api_bp.route("/global/projects", methods=["GET"])
def se_team_global_projects_list():
    from app.services.project_manager_service import get_project_manager_service

    service = get_project_manager_service()
    return jsonify({"items": service.list_registry(), "count": len(service.list_registry())})


@se_team_api_bp.route("/global/projects/refresh", methods=["POST"])
def se_team_global_projects_refresh():
    from app.services.project_manager_service import get_project_manager_service

    payload = request.get_json(silent=True) or {}
    force_refresh = bool(payload.get("force_refresh", False))
    service = get_project_manager_service()
    return jsonify(service.bulk_register_from_experience_paths(force_refresh=force_refresh))


@se_team_api_bp.route("/global/projects/search", methods=["POST"])
def se_team_global_projects_search():
    from app.services.project_manager_service import get_project_manager_service

    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query") or "").strip()
    if not query:
        return jsonify({"detail": "query is required"}), 400
    top_k = int(payload.get("top_k") or 4)
    mmr_lambda = float(payload.get("mmr_lambda") or 0.7)
    service = get_project_manager_service()
    try:
        service.bulk_register_from_experience_paths(force_refresh=False)
    except Exception:
        pass
    matches = service.retrieve_top_projects(
        query=query,
        top_k=max(1, min(top_k, 12)),
        mmr_lambda=max(0.0, min(mmr_lambda, 1.0)),
        expand_query=False,
    )
    return jsonify({"query": query, "top_k": top_k, "matches": matches})
