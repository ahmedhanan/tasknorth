import pytest
from httpx import AsyncClient


async def _setup(client: AsyncClient):
    reg = await client.post("/auth/register", json={"email": "t@test.com", "password": "password123"})
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers


async def test_create_and_get_task(client: AsyncClient):
    h = await _setup(client)
    r = await client.post("/tasks/", json={"title": "My task", "priority": "high"}, headers=h)
    assert r.status_code == 201
    task_id = r.json()["id"]

    r2 = await client.get(f"/tasks/{task_id}", headers=h)
    assert r2.status_code == 200
    assert r2.json()["title"] == "My task"


async def test_list_tasks_filter_by_priority(client: AsyncClient):
    h = await _setup(client)
    await client.post("/tasks/", json={"title": "Urgent task", "priority": "urgent"}, headers=h)
    await client.post("/tasks/", json={"title": "Low task", "priority": "low"}, headers=h)

    r = await client.get("/tasks/?priority=urgent", headers=h)
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Urgent task"


async def test_list_tasks_search(client: AsyncClient):
    h = await _setup(client)
    await client.post("/tasks/", json={"title": "Deploy to production"}, headers=h)
    await client.post("/tasks/", json={"title": "Write tests"}, headers=h)

    r = await client.get("/tasks/?search=deploy", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_pagination(client: AsyncClient):
    h = await _setup(client)
    for i in range(5):
        await client.post("/tasks/", json={"title": f"Task {i}"}, headers=h)

    r = await client.get("/tasks/?limit=2&offset=0", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 2

    r2 = await client.get("/tasks/?limit=2&offset=2", headers=h)
    assert len(r2.json()) == 2


async def test_update_task_status(client: AsyncClient):
    h = await _setup(client)
    r = await client.post("/tasks/", json={"title": "To update"}, headers=h)
    task_id = r.json()["id"]

    r2 = await client.patch(f"/tasks/{task_id}", json={"status": "in_progress"}, headers=h)
    assert r2.status_code == 200
    assert r2.json()["status"] == "in_progress"


async def test_complete_task_endpoint(client: AsyncClient):
    h = await _setup(client)
    r = await client.post("/tasks/", json={"title": "Complete me"}, headers=h)
    task_id = r.json()["id"]

    r2 = await client.post(f"/tasks/{task_id}/complete", headers=h)
    assert r2.status_code == 200
    assert r2.json()["status"] == "done"


async def test_subtask_creation_and_listing(client: AsyncClient):
    h = await _setup(client)
    parent = await client.post("/tasks/", json={"title": "Parent"}, headers=h)
    parent_id = parent.json()["id"]

    sub = await client.post(f"/tasks/{parent_id}/subtasks", json={"title": "Child"}, headers=h)
    assert sub.status_code == 201
    assert sub.json()["parent_task_id"] == parent_id

    r = await client.get(f"/tasks/{parent_id}/subtasks", headers=h)
    assert len(r.json()) == 1

    # subtasks should NOT appear in top-level list
    top = await client.get("/tasks/", headers=h)
    ids = [t["id"] for t in top.json()]
    assert sub.json()["id"] not in ids


async def test_delete_task(client: AsyncClient):
    h = await _setup(client)
    r = await client.post("/tasks/", json={"title": "Delete me"}, headers=h)
    task_id = r.json()["id"]

    del_r = await client.delete(f"/tasks/{task_id}", headers=h)
    assert del_r.status_code == 204

    get_r = await client.get(f"/tasks/{task_id}", headers=h)
    assert get_r.status_code == 404


async def test_task_not_visible_to_other_user(client: AsyncClient):
    h1 = await _setup(client)
    reg2 = await client.post("/auth/register", json={"email": "other@test.com", "password": "password123"})
    h2 = {"Authorization": f"Bearer {reg2.json()['access_token']}"}

    r = await client.post("/tasks/", json={"title": "Private"}, headers=h1)
    task_id = r.json()["id"]

    r2 = await client.get(f"/tasks/{task_id}", headers=h2)
    assert r2.status_code == 404
