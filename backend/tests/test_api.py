import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeLLM, reply, structured, tool_calls
from weekfeed.api.app import create_app
from weekfeed.config import Config
from weekfeed.llm import LLMAuthError, LLMUnavailable

V1 = {"sections": [{"title": "Yesterday", "text": "- a"}, {"title": "Today", "text": "- b"}, {"title": "Blockers", "text": "None"}]}


@pytest.fixture
def make_client(tmp_path):
    def _make(llm=None, static_dir=None):
        cfg = Config(openai_api_key=None, openai_model=None, db_path=tmp_path / "api.db", port=0)
        return TestClient(create_app(cfg, llm=llm, static_dir=static_dir or tmp_path / "no-dist"))
    return _make


@pytest.fixture
def client(make_client):
    return make_client()


def new_project(client, name="api-server", label="work"):
    r = client.post("/api/projects", json={"name": name, "label": label})
    assert r.status_code == 201, r.text
    return r.json()


# --- health, projects, repos, settings, sync ---

def test_health_without_ai(client):
    assert client.get("/api/health").json() == {"api_key_loaded": False, "model": None, "git_available": True}


def test_project_crud_and_card_shape(client):
    p = new_project(client)
    assert p == {"id": p["id"], "name": "api-server", "label": "work", "repos": [], "open_todos": 0,
                 "open_blockers": 0, "last_standup_at": None, "oldest_fetch_at": None}
    assert client.patch(f"/api/projects/{p['id']}", json={"label": "school"}).json()["label"] == "school"
    assert client.patch(f"/api/projects/{p['id']}", json={"name": "api"}).json()["name"] == "api"
    assert [x["name"] for x in client.get("/api/projects").json()["projects"]] == ["api"]


def test_errors_have_a_uniform_shape(client):
    new_project(client)
    r = client.post("/api/projects", json={"name": "API-SERVER", "label": "work"})
    assert r.status_code == 409
    assert r.json()["error"] == "conflict" and "already exists" in r.json()["message"]
    r = client.post("/api/projects", json={"name": "x", "label": "hobby"})
    assert (r.status_code, r.json()["error"]) == (422, "invalid")
    assert client.get("/api/drafts/999").json()["error"] == "not_found"


def test_delete_project_requires_name(client):
    p = new_project(client)
    assert client.delete(f"/api/projects/{p['id']}", params={"confirm_name": "nope"}).status_code == 422
    assert client.delete(f"/api/projects/{p['id']}", params={"confirm_name": "api-server"}).status_code == 204
    assert client.get("/api/projects").json()["projects"] == []


def test_add_repo_syncs_and_rejects_bad_or_duplicate_paths(client, make_repo, tmp_path):
    git_repo = make_repo("api-server")
    git_repo.commit("first")
    p = new_project(client)
    r = client.post("/api/repos", json={"path": str(git_repo.path) + "/", "project_id": p["id"]})
    assert r.status_code == 201, r.text
    assert r.json()["display_name"] == "api-server"
    assert r.json()["last_fetched_at"] is not None

    link = tmp_path / "link-to-repo"
    link.symlink_to(git_repo.path)
    dup = client.post("/api/repos", json={"path": str(link), "project_id": p["id"]})
    assert dup.status_code == 409 and "api-server" in dup.json()["message"]

    plain = tmp_path / "plain"
    plain.mkdir()
    assert client.post("/api/repos", json={"path": str(plain), "project_id": p["id"]}).status_code == 422
    assert client.post("/api/repos", json={"path": "/does/not/exist", "project_id": p["id"]}).status_code == 422

    emails = client.get("/api/settings/emails").json()["emails"]
    assert emails[0]["email"] == "me@example.com" and emails[0]["commit_count"] == 1

    assert client.delete(f"/api/repos/{r.json()['id']}").status_code == 204


def test_sync_endpoint(client, make_repo):
    git_repo = make_repo()
    git_repo.commit("first")
    p = new_project(client)
    client.post("/api/repos", json={"path": str(git_repo.path), "project_id": p["id"]})
    results = client.post("/api/sync", json={"project_id": p["id"]}).json()["results"]
    assert results[0]["fetched"] is True
    assert client.post("/api/sync", json={"label": "work", "force": False}).json()["results"][0]["fetched"] is False


def test_settings_round_trip(client):
    body = {"github_username": "kdb82", "my_emails": ["Me@Example.com"]}
    assert client.put("/api/settings", json=body).json() == {"github_username": "kdb82", "my_emails": ["me@example.com"]}
    assert client.get("/api/settings").json()["github_username"] == "kdb82"


# --- drafts ---

def started(make_client, *script):
    llm = FakeLLM([structured(V1), *script])
    c = make_client(llm=llm)
    p = new_project(c)
    r = c.post("/api/drafts", json={"kind": "standup", "label": "work", "project_id": p["id"]})
    assert r.status_code == 201, r.text
    return c, llm, p, r.json()


def test_start_draft_returns_detail(make_client):
    c, _, p, detail = started(make_client)
    assert detail["draft"]["status"] == "in_progress"
    assert detail["draft"]["sections"] == V1["sections"]
    assert detail["messages"][0]["draft_snapshot"] == V1["sections"]
    assert detail["stats"] == {"commits": 0, "closed": 0, "notes": 0}
    history = c.get("/api/drafts", params={"project_id": p["id"]}).json()["drafts"]
    assert [d["id"] for d in history] == [detail["draft"]["id"]]


def test_start_draft_without_ai_is_503(client):
    p = new_project(client)
    r = client.post("/api/drafts", json={"kind": "standup", "label": "work", "project_id": p["id"]})
    assert (r.status_code, r.json()["error"]) == (503, "ai_disabled")


def test_chat_turn_returns_batch_changes_and_undo(make_client):
    c, llm, p, detail = started(make_client)
    llm.add(tool_calls(("add_todo", {"text": "Review PR", "project": None})),
            tool_calls(("update_draft", {"sections": V1["sections"]})), reply("Added."))
    draft_id = detail["draft"]["id"]
    r = c.post(f"/api/drafts/{draft_id}/messages", json={"content": "add review PR"})
    assert r.status_code == 200, r.text
    msg = r.json()["message"]
    assert msg["batch"]["changes"] == [{"action": "created", "kind": "todo", "text": "Review PR", "new_status": "open"}]
    items = c.get("/api/items", params={"project_id": p["id"]}).json()
    assert [i["text"] for i in items["todos"]] == ["Review PR"]

    undo = c.post(f"/api/batches/{msg['batch']['id']}/undo", json={})
    assert undo.status_code == 200 and undo.json()["batch"]["undone_at"] is not None
    assert undo.json()["draft_restored"] in (True, False)
    assert c.get("/api/items", params={"project_id": p["id"]}).json()["todos"] == []
    assert c.post(f"/api/batches/{msg['batch']['id']}/undo", json={}).status_code == 409


def test_undo_conflict_is_409_with_items(make_client):
    c, llm, p, detail = started(make_client)
    llm.add(tool_calls(("add_todo", {"text": "Review PR", "project": None})),
            tool_calls(("update_draft", {"sections": V1["sections"]})), reply("Added."),
            tool_calls(("list_open_items", {"project": None})), reply("checking"))
    draft_id = detail["draft"]["id"]
    batch_id = c.post(f"/api/drafts/{draft_id}/messages", json={"content": "add"}).json()["message"]["batch"]["id"]
    # simulate a later edit of the created item
    from weekfeed.store.db import connect
    conn = connect(c.app.state.config.db_path)
    conn.execute("UPDATE items SET updated_at = '2999-01-01T00:00:00.000000+00:00'")
    conn.close()
    r = c.post(f"/api/batches/{batch_id}/undo", json={})
    assert r.status_code == 409
    assert r.json()["error"] == "undo_conflict"
    assert r.json()["conflicts"][0]["text"] == "Review PR"
    assert c.post(f"/api/batches/{batch_id}/undo", json={"force": True}).status_code == 200


def test_llm_failure_is_502_then_retry_works(make_client):
    c, llm, _, detail = started(make_client)
    draft_id = detail["draft"]["id"]
    llm.add(LLMUnavailable("down"))
    r = c.post(f"/api/drafts/{draft_id}/messages", json={"content": "hello"})
    assert (r.status_code, r.json()["error"]) == (502, "llm_unavailable")
    llm.add(reply("hi"))
    assert c.post(f"/api/drafts/{draft_id}/retry").json()["message"]["content"] == "hi"


def test_bad_api_key_is_502_llm_auth(make_client):
    c, llm, _, detail = started(make_client)
    llm.add(LLMAuthError("OpenAI rejected the API key."))
    r = c.post(f"/api/drafts/{detail['draft']['id']}/messages", json={"content": "hello"})
    assert (r.status_code, r.json()["error"]) == (502, "llm_auth")


def test_patch_sections_discord_save_and_read_only(make_client):
    c, llm, _, detail = started(make_client)
    draft_id = detail["draft"]["id"]
    edited = c.patch(f"/api/drafts/{draft_id}", json={"sections": [{"title": "Today", "text": "- mine"}]}).json()
    assert edited["draft"]["sections"][1]["text"] == "- mine"
    llm.add(reply("**Yesterday**\n- a"))
    discord = c.get(f"/api/drafts/{draft_id}/discord").json()
    assert discord["text"].startswith("**Standup · ") and discord["over_limit"] is False
    saved = c.post(f"/api/drafts/{draft_id}/save").json()
    assert saved["draft"]["status"] == "saved" and saved["draft"]["record_text"].startswith("Yesterday")
    assert c.patch(f"/api/drafts/{draft_id}", json={"sections": V1["sections"]}).status_code == 422
    assert c.delete(f"/api/drafts/{draft_id}").status_code == 422


def test_change_range_and_discard(make_client):
    c, llm, _, detail = started(make_client)
    draft_id = detail["draft"]["id"]
    llm.add(structured(V1))
    r = c.patch(f"/api/drafts/{draft_id}", json={"period_start": "2026-10-01T00:00:00Z", "period_end": "2026-10-07T00:00:00Z"})
    assert r.json()["draft"]["period_start"] == "2026-10-01T00:00:00.000000+00:00"
    assert c.delete(f"/api/drafts/{draft_id}").status_code == 204


def test_label_wide_draft(make_client):
    llm = FakeLLM([structured(V1)])
    c = make_client(llm=llm)
    r = c.post("/api/drafts", json={"kind": "weekly", "label": "school"})
    assert r.status_code == 201
    assert r.json()["draft"]["project_id"] is None
    assert len(c.get("/api/drafts", params={"label": "school"}).json()["drafts"]) == 1
    assert c.get("/api/drafts", params={"label": "hobby"}).status_code == 422


# --- ask and notes ---

def test_ask_and_save_note(make_client):
    llm = FakeLLM([structured({"terms": ["x"]}), reply("I couldn't find this in your notes or commits.")])
    c = make_client(llm=llm)
    r = c.post("/api/ask", json={"messages": [{"role": "user", "content": "anything?"}]})
    assert r.status_code == 200
    assert r.json() == {"answer": "I couldn't find this in your notes or commits.", "terms": ["anything"],
                        "citations": [], "batch": None}
    note = c.post("/api/notes", json={"text": "keep this", "label": "personal", "project_id": None}).json()
    assert note["item"]["text"] == "keep this"
    assert note["batch"]["changes"][0]["kind"] == "note"


# --- static frontend ---

def test_serves_spa_index_for_client_routes(make_client, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    c = make_client(static_dir=dist)
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/projects/3").text == "<html>app</html>"
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/nope").status_code == 404
