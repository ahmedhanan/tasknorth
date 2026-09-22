import pytest
from httpx import AsyncClient


async def _setup(client: AsyncClient, email: str = "tag@test.com"):
    reg = await client.post("/auth/register", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def test_create_and_list_tags(client: AsyncClient):
    h = await _setup(client)
    r = await client.post("/tags/", json={"name": "backend", "color": "#10b981"}, headers=h)
    assert r.status_code == 201
    assert r.json()["name"] == "backend"

    r2 = await client.get("/tags/", headers=h)
    assert len(r2.json()) == 1


async def test_invalid_color_rejected(client: AsyncClient):
    h = await _setup(client)
    r = await client.post("/tags/", json={"name": "bad", "color": "not-a-color"}, headers=h)
    assert r.status_code == 422


async def test_update_tag(client: AsyncClient):
    h = await _setup(client)
    r = await client.post("/tags/", json={"name": "old-name"}, headers=h)
    tag_id = r.json()["id"]

    r2 = await client.patch(f"/tags/{tag_id}", json={"name": "new-name"}, headers=h)
    assert r2.status_code == 200
    assert r2.json()["name"] == "new-name"


async def test_delete_tag(client: AsyncClient):
    h = await _setup(client)
    r = await client.post("/tags/", json={"name": "to-delete"}, headers=h)
    tag_id = r.json()["id"]

    del_r = await client.delete(f"/tags/{tag_id}", headers=h)
    assert del_r.status_code == 204

    r2 = await client.get("/tags/", headers=h)
    assert len(r2.json()) == 0


async def test_attach_tag_from_other_user_rejected(client: AsyncClient):
    h1 = await _setup(client, email="user1@test.com")
    h2 = await _setup(client, email="user2@test.com")

    task_r = await client.post("/tasks/", json={"title": "My task"}, headers=h1)
    task_id = task_r.json()["id"]

    tag_r = await client.post("/tags/", json={"name": "other-tag"}, headers=h2)
    tag_id = tag_r.json()["id"]

    r = await client.post(f"/tasks/{task_id}/tags/{tag_id}", headers=h1)
    assert r.status_code == 404  # tag belongs to different user


async def test_attach_and_detach_tag(client: AsyncClient):
    h = await _setup(client)
    task_r = await client.post("/tasks/", json={"title": "Tagged task"}, headers=h)
    task_id = task_r.json()["id"]

    tag_r = await client.post("/tags/", json={"name": "work"}, headers=h)
    tag_id = tag_r.json()["id"]

    attach = await client.post(f"/tasks/{task_id}/tags/{tag_id}", headers=h)
    assert attach.status_code == 204

    task_detail = await client.get(f"/tasks/{task_id}", headers=h)
    assert any(t["name"] == "work" for t in task_detail.json()["tags"])

    detach = await client.delete(f"/tasks/{task_id}/tags/{tag_id}", headers=h)
    assert detach.status_code == 204

    task_detail2 = await client.get(f"/tasks/{task_id}", headers=h)
    assert len(task_detail2.json()["tags"]) == 0
