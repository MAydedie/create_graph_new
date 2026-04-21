#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""QA extraction entrypoint with experience-library controls."""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, send_from_directory

from app.services.analysis_service import (
    api_workbench_project_status,
    api_workbench_session_start,
    api_workbench_session_status,
)
from app.services.conversation_service import (
    api_conversation_events,
    api_conversation_export_runbook,
    api_conversation_messages,
    api_conversation_reply,
    api_conversation_session_result,
    api_conversation_session_start,
    api_conversation_session_status,
)
from app.services.experience_library_service import (
    api_experience_library_overview,
)
from app.services.multi_agent_service import (
    api_multi_agent_session_result,
    api_multi_agent_session_start,
    api_multi_agent_session_status,
)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')

app = Flask(__name__)


@app.get('/')
def index():
    return send_from_directory(ROOT / 'qa_ui', 'index.html')


@app.post('/api/conversations/session/start')
def conversation_session_start():
    return api_conversation_session_start()


@app.get('/api/conversations/session/<session_id>/status')
def conversation_session_status(session_id: str):
    return api_conversation_session_status(session_id)


@app.get('/api/conversations/session/<session_id>/result')
def conversation_session_result(session_id: str):
    return api_conversation_session_result(session_id)


@app.get('/api/conversations/<conversation_id>/messages')
def conversation_messages(conversation_id: str):
    return api_conversation_messages(conversation_id)


@app.post('/api/conversations/<conversation_id>/reply')
def conversation_reply(conversation_id: str):
    return api_conversation_reply(conversation_id)


@app.get('/api/conversations/<conversation_id>/events')
def conversation_events(conversation_id: str):
    return api_conversation_events(conversation_id)


@app.post('/api/conversations/<conversation_id>/export_runbook')
def conversation_export_runbook(conversation_id: str):
    return api_conversation_export_runbook(conversation_id)


@app.post('/api/multi_agent/session/start')
def multi_agent_start():
    return api_multi_agent_session_start()


@app.get('/api/multi_agent/session/<session_id>/status')
def multi_agent_status(session_id: str):
    return api_multi_agent_session_status(session_id)


@app.get('/api/multi_agent/session/<session_id>/result')
def multi_agent_result(session_id: str):
    return api_multi_agent_session_result(session_id)


@app.get('/api/experience/library')
def experience_library_overview():
    return api_experience_library_overview()


@app.post('/api/workbench/session/start')
def workbench_session_start():
    return api_workbench_session_start()


@app.get('/api/workbench/session/<session_id>/status')
def workbench_session_status(session_id: str):
    return api_workbench_session_status(session_id)


@app.get('/api/workbench/project_status')
def workbench_project_status():
    return api_workbench_project_status()


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5123'))
    app.run(host='0.0.0.0', port=port, debug=False)
