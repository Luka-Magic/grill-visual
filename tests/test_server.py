"""server.py の結合テスト: 一時ルート + 空きポートで実際に起動して HTTP で叩く。"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import server
import state
from conftest import info_round, open_round, write_html, write_topic

pytestmark = pytest.mark.integration


@pytest.fixture
def base(root: Path):
    httpd = server.make_server(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(url: str):
    with urllib.request.urlopen(url, timeout=5) as res:
        return res.status, dict(res.headers), res.read()


def post(url: str, body: bytes | dict, content_type: str = "application/json"):
    data = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read()


# ---------------------------------------------------------------- 統合ページ

@pytest.mark.parametrize("path", ["/", "/index.html", "/?x=1"])
def test_dashboard_served_at_root(base: str, path: str):
    status, headers, body = get(base + path)
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert "no-store" in headers["Cache-Control"]
    assert b'id="list"' in body


def test_bind_is_loopback_only(root: Path):
    httpd = server.make_server(root, 0)
    try:
        assert httpd.server_address[0] == "127.0.0.1"
    finally:
        httpd.server_close()


# ---------------------------------------------------------------- /api/state

def test_api_state_reports_topics_and_counts(base: str, root: Path):
    write_topic(root, "w", [open_round(1)], title="#7 待ち", project="proj")
    write_topic(root, "d", [info_round(1)])
    write_html(root, "w")
    status, headers, body = get(base + "/api/state?x=1")
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert "no-store" in headers["Cache-Control"]
    doc = json.loads(body)
    assert doc["counts"] == {"waiting": 1, "answered": 0, "done": 1, "error": 0}
    w = next(t for t in doc["topics"] if t["topic"] == "w")
    assert (w["state"], w["issue"], w["project"], w["html_exists"]) == ("waiting", 7, "proj", True)


def test_unknown_api_is_404(base: str):
    with pytest.raises(urllib.error.HTTPError) as err:
        get(base + "/api/nope")
    assert err.value.code == 404


def test_static_html_still_served(base: str, root: Path):
    write_html(root, "x")
    status, _, body = get(base + "/grill-x.html")
    assert status == 200 and body == b"<html></html>"


# ---------------------------------------------------------------- /api/archive

def test_archive_toggle_persists(base: str, root: Path):
    write_topic(root, "old", [info_round(1)])
    status, _, body = post(base + "/api/archive", {"topic": "old", "archived": True})
    assert status == 200
    assert json.loads(body) == {"ok": True, "archived": ["old"]}
    assert "old" in state.load_archive(root)
    doc = json.loads(get(base + "/api/state")[2])
    assert next(t for t in doc["topics"] if t["topic"] == "old")["archived"] is True

    status, _, body = post(base + "/api/archive", {"topic": "old", "archived": False})
    assert status == 200 and json.loads(body)["archived"] == []


@pytest.mark.parametrize(
    "body",
    [b"{not json", {"topic": "a b", "archived": True}, {"topic": "a", "archived": "yes"}, {"archived": True}, {"topic": "", "archived": True}],
)
def test_archive_rejects_bad_input(base: str, root: Path, body):
    status, _, _ = post(base + "/api/archive", body)
    assert status == 400
    assert not (root / state.ARCHIVE_FILE).exists()


def test_archive_rejects_oversized_body(base: str):
    status, _, _ = post(base + "/api/archive", b"x" * (server.MAX_BODY_BYTES + 1))
    assert status == 400


# ---------------------------------------------------------------- /submit(回帰)

def test_submit_writes_answer_file(base: str, root: Path):
    payload = {"topic": "t-1", "round": 2, "answers": {"Q1": ["a"]}, "notes": {}, "free_text": "x"}
    status, _, body = post(base + "/submit", payload)
    assert status == 200 and json.loads(body) == {"ok": True}
    saved = json.loads((root / "answers" / "t-1-round-2.json").read_text(encoding="utf-8"))
    assert saved["answers"] == {"Q1": ["a"]}
    assert saved["received_at"]
    assert not list((root / "answers").glob("*.tmp"))


def test_submit_sanitizes_topic(base: str, root: Path):
    status, _, _ = post(base + "/submit", {"topic": "a/b c", "round": 1})
    assert status == 200
    assert (root / "answers" / "abc-round-1.json").exists()


def test_submit_rejects_bad_json(base: str):
    status, _, _ = post(base + "/submit", b"{oops")
    assert status == 400


def test_post_unknown_path_is_404(base: str):
    status, _, _ = post(base + "/other", {"a": 1})
    assert status == 404


def test_head_on_root_has_no_store_and_no_body(base: str):
    req = urllib.request.Request(base + "/", method="HEAD")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        assert "no-store" in res.headers["Cache-Control"]
        assert res.read() == b""


def test_submit_response_body_is_unchanged_from_original(base: str):
    _, headers, body = post(base + "/submit", {"topic": "t", "round": 1})
    assert body == b'{"ok":true}'
    assert headers["Content-Type"].startswith("application/json")


def test_dashboard_missing_gives_500(base: str, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(server, "DASHBOARD", tmp_path / "nope.html")
    with pytest.raises(urllib.error.HTTPError) as err:
        get(base + "/")
    assert err.value.code == 500


def test_handler_bug_gives_500_not_400(base: str, monkeypatch):
    def boom(self, doc):
        raise RuntimeError("bug")
    monkeypatch.setattr(server.Handler, "_post_archive", boom)
    status, _, _ = post(base + "/api/archive", {"topic": "a", "archived": True})
    assert status == 500
