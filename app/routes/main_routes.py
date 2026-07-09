#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Main page routes

Stage G closure policy:
- '/'                    -> 首页单工作台正式主入口
- '/hierarchy'           -> legacy 四层页（冻结/调试保留）
- '/function_hierarchy'  -> legacy 功能层级页（fallback / 调试保留）

第一轮只做入口与口径收口，不删除旧路由。
"""

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file, send_from_directory

from app.services.se_team_embedded_service import resolve_se_team_html_path

main_bp = Blueprint("main", __name__)


def _frontend_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend_gitnexus" / "dist"


def _frontend_dist_ready() -> bool:
    dist_dir = _frontend_dist_dir()
    return (dist_dir / "index.html").exists()


def _se_team_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "ui" / "se_team_frontend" / "dist"


def _se_team_dist_ready() -> bool:
    dist_dir = _se_team_dist_dir()
    return (dist_dir / "index.html").exists()


def _edict_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "ui" / "edict_frontend" / "dist"


def _edict_dist_ready() -> bool:
    dist_dir = _edict_dist_dir()
    return (dist_dir / "index.html").exists()


@main_bp.route("/")
def index():
    if str(request.args.get("legacy_entry") or "").strip() == "1":
        return render_template("index.html")
    if _frontend_dist_ready():
        return send_from_directory(_frontend_dist_dir(), "index.html")
    return render_template("index.html")


@main_bp.route("/assets/<path:filename>")
def frontend_assets(filename: str):
    if not _frontend_dist_ready():
        return "Frontend dist build not found. Run npm --prefix frontend_gitnexus run build.", 503
    return send_from_directory(_frontend_dist_dir() / "assets", filename)


@main_bp.route("/vite.svg")
def frontend_vite_icon():
    if not _frontend_dist_ready():
        return "", 204
    return send_from_directory(_frontend_dist_dir(), "vite.svg")


@main_bp.route("/wasm/<path:filename>")
def frontend_wasm_assets(filename: str):
    if not _frontend_dist_ready():
        return "Frontend dist build not found. Run npm --prefix frontend_gitnexus run build.", 503
    return send_from_directory(_frontend_dist_dir() / "wasm", filename)


@main_bp.route("/favicon.ico")
def frontend_favicon():
    dist_favicon = _frontend_dist_dir() / "favicon.ico"
    if dist_favicon.exists():
        return send_from_directory(_frontend_dist_dir(), "favicon.ico")
    return "", 204


@main_bp.route("/se_team")
@main_bp.route("/se_team/")
def se_team_index():
    if _se_team_dist_ready():
        return send_from_directory(_se_team_dist_dir(), "index.html")
    return "SE Team frontend build not found. Run npm install && npm run build in ui/se_team_frontend.", 503


@main_bp.route("/se_team_full")
@main_bp.route("/se_team_full/")
def se_team_full_index():
    html_path = resolve_se_team_html_path()
    if not html_path.exists():
        return f"SE-Team page not found: {html_path}", 503
    return send_file(str(html_path))


@main_bp.route("/se_team_full/status")
def se_team_full_status():
    return jsonify({"ready": True, "url": "/se_team_full"})


@main_bp.route("/se_team/assets/<path:filename>")
def se_team_assets(filename: str):
    return send_from_directory(_se_team_dist_dir() / "assets", filename)


@main_bp.route("/se_team/<path:filename>")
def se_team_static(filename: str):
    dist_dir = _se_team_dist_dir()
    requested_file = dist_dir / filename
    if requested_file.is_file():
        return send_from_directory(dist_dir, filename)
    if _se_team_dist_ready():
        return send_from_directory(dist_dir, "index.html")
    return "SE Team frontend build not found. Run npm install && npm run build in ui/se_team_frontend.", 503


@main_bp.route("/edict")
@main_bp.route("/edict/")
def edict_index():
    if _edict_dist_ready():
        return send_from_directory(_edict_dist_dir(), "index.html")
    return "Edict frontend build not found. Run npm install && npm run build in ui/edict_frontend.", 503


@main_bp.route("/edict/assets/<path:filename>")
def edict_assets(filename: str):
    return send_from_directory(_edict_dist_dir() / "assets", filename)


@main_bp.route("/edict/<path:filename>")
def edict_static(filename: str):
    dist_dir = _edict_dist_dir()
    requested_file = dist_dir / filename
    if requested_file.is_file():
        return send_from_directory(dist_dir, filename)
    if _edict_dist_ready():
        return send_from_directory(dist_dir, "index.html")
    return "Edict frontend build not found. Run npm install && npm run build in ui/edict_frontend.", 503


@main_bp.route("/hierarchy")
def hierarchy_view():
    return render_template("index_hierarchy.html")


@main_bp.route("/function_hierarchy")
def function_hierarchy_view():
    return render_template("function_hierarchy.html")








