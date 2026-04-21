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

from flask import Blueprint, render_template, send_from_directory

main_bp = Blueprint("main", __name__)


def _frontend_dist_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend_gitnexus" / "dist"


def _frontend_dist_ready() -> bool:
    dist_dir = _frontend_dist_dir()
    return (dist_dir / "index.html").exists()


@main_bp.route("/")
def index():
    if _frontend_dist_ready():
        return send_from_directory(_frontend_dist_dir(), "index.html")
    return render_template("index.html")


@main_bp.route("/assets/<path:filename>")
def frontend_assets(filename: str):
    return send_from_directory(_frontend_dist_dir() / "assets", filename)


@main_bp.route("/vite.svg")
def frontend_vite_icon():
    return send_from_directory(_frontend_dist_dir(), "vite.svg")


@main_bp.route("/wasm/<path:filename>")
def frontend_wasm_assets(filename: str):
    return send_from_directory(_frontend_dist_dir() / "wasm", filename)


@main_bp.route("/favicon.ico")
def frontend_favicon():
    dist_favicon = _frontend_dist_dir() / "favicon.ico"
    if dist_favicon.exists():
        return send_from_directory(_frontend_dist_dir(), "favicon.ico")
    return "", 204


@main_bp.route("/hierarchy")
def hierarchy_view():
    return render_template("index_hierarchy.html")


@main_bp.route("/function_hierarchy")
def function_hierarchy_view():
    return render_template("function_hierarchy.html")








