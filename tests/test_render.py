"""render.py: 印字する URL と postMessage の埋め込み。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, open_round, write_topic

pytestmark = pytest.mark.unit
RENDER = REPO / "render.py"


def run_render(root: Path, topic: str, env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "GRILL_URL"}
    env.update({"GRILL_ROOT": str(root), **env_extra})
    return subprocess.run(
        [sys.executable, str(RENDER), str(root / "grill-data" / f"{topic}.json")],
        capture_output=True, text=True, env=env, check=True,
    )


def test_prints_dashboard_url_with_grill_url(root: Path):
    write_topic(root, "t-1", [open_round(1)], intro="")
    out = run_render(root, "t-1", {"GRILL_URL": "http://example.test:9000/"}).stdout.strip().splitlines()
    assert out[-1] == "http://example.test:9000/#t-1"
    assert out[0] == str(root / "grill-t-1.html")
    assert (root / "grill-t-1.html").exists()


def test_prints_localhost_url_without_env(root: Path):
    write_topic(root, "t-2", [open_round(1)], intro="")
    out = run_render(root, "t-2", {}).stdout.strip().splitlines()
    assert out[-1] == "http://localhost:8787/#t-2"


def test_html_posts_message_to_parent(root: Path):
    write_topic(root, "t-3", [open_round(1)], intro="")
    run_render(root, "t-3", {})
    html = (root / "grill-t-3.html").read_text(encoding="utf-8")
    assert "grill-submitted" in html
    assert "window.parent.postMessage" in html


def test_dashboard_url_helper():
    sys.path.insert(0, str(REPO))
    import render
    assert render.dashboard_url("abc", "http://x/") == "http://x/#abc"
    assert render.dashboard_url("abc", "http://x") == "http://x/#abc"
    assert render.dashboard_url("abc", "") == "http://localhost:8787/#abc"


def test_html_has_draft_persistence(root: Path):
    write_topic(root, "t-4", [open_round(1)], intro="")
    run_render(root, "t-4", {})
    html = (root / "grill-t-4.html").read_text(encoding="utf-8")
    assert "grill-draft:" in html
    assert "restoreDraft()" in html


XSS = '<script>alert(1)</script><img src="x" onerror="alert(2)"><a href="javascript:alert(3)">l</a>'


def test_every_html_field_is_sanitized(root: Path):
    question = {
        "id": "Q1", "title": XSS, "body": XSS, "why": XSS, "answer_note": XSS,
        "image": "javascript:alert(4)",
        "options": [{"key": "a", "label": XSS, "image": 'x.png" onerror="alert(5)'}],
    }
    rounds = [
        {"round": 1, "status": "answered", "facts": [XSS], "declarations": [XSS],
         "free_text_answer": XSS, "questions": [{**question, "answer": ["a"]}]},
        {"round": 2, "status": "open", "label": XSS, "questions": [question]},
    ]
    write_topic(root, "t-6", rounds, title=XSS, intro=XSS,
                tree=[{"label": XSS, "status": 'x" onmouseover="alert(6)', "note": XSS}])
    run_render(root, "t-6", {})
    page = (root / "grill-t-6.html").read_text(encoding="utf-8")
    body = page.split("<script>", 1)[0]  # 本文側(自前の <script> より前)
    assert "<script>alert" not in body
    assert "onerror" not in body.replace("onerror=&quot;", "")
    assert "javascript:" not in body.replace("javascript:alert(3)&quot;", "")
    assert 'href="javascript' not in page and 'src="javascript' not in page
    assert "onmouseover" not in page


def test_rejects_topic_with_path_characters(root: Path):
    write_topic(root, "ok", [open_round(1)])
    path = root / "grill-data" / "ok.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"ok"', '"../evil"'), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(RENDER), str(path)], capture_output=True, text=True,
                          env={**os.environ, "GRILL_ROOT": str(root)})
    assert proc.returncode != 0
    assert not (root.parent / "grill-evil.html").exists()


def test_script_json_cannot_close_script_tag(root: Path):
    write_topic(root, "t-7", [{"round": 1, "status": "open", "questions": [
        {"id": "</script><script>alert(1)//", "title": "t", "body": "b", "options": [{"key": "a", "label": "A"}]}]}])
    run_render(root, "t-7", {})
    page = (root / "grill-t-7.html").read_text(encoding="utf-8")
    assert page.count("</script>") == 1
