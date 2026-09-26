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
    env = {k: v for k, v in os.environ.items() if k != "PARALLEL_GRILL_URL"}
    env.update({"GRILL_ROOT": str(root), **env_extra})
    return subprocess.run(
        [sys.executable, str(RENDER), str(root / "grill-data" / f"{topic}.json")],
        capture_output=True, text=True, env=env, check=True,
    )


def test_prints_dashboard_url_with_parallel_root(root: Path):
    write_topic(root, "t-1", [open_round(1)], intro="")
    out = run_render(root, "t-1", {"PARALLEL_GRILL_URL": "http://h:8374/"}).stdout.strip().splitlines()
    assert out[-1] == "http://h:8374/#t-1"
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
