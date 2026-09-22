import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str = "user@test.com", password: str = "password123"):
    r = await client.post("/auth/register", json={"email": email, "password": password})
    return r


async def test_register_success(client: AsyncClient):
    r = await _register(client)
    assert r.status_code == 201
    data = r.json()
    assert "access_token" in data
    assert "mcp_api_key" in data


async def test_register_duplicate_email(client: AsyncClient):
    await _register(client)
    r = await _register(client)
    assert r.status_code == 409


async def test_register_short_password(client: AsyncClient):
    r = await _register(client, password="short")
    assert r.status_code == 422


async def test_login_success(client: AsyncClient):
    await _register(client)
    r = await client.post("/auth/login", json={"email": "user@test.com", "password": "password123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


async def test_login_wrong_password(client: AsyncClient):
    await _register(client)
    r = await client.post("/auth/login", json={"email": "user@test.com", "password": "wrongpass"})
    assert r.status_code == 401


async def test_login_unknown_email(client: AsyncClient):
    r = await client.post("/auth/login", json={"email": "nobody@test.com", "password": "password123"})
    assert r.status_code == 401


async def test_get_me(client: AsyncClient):
    reg = await _register(client)
    token = reg.json()["access_token"]
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "user@test.com"


async def test_get_me_no_token(client: AsyncClient):
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_rotate_mcp_key(client: AsyncClient):
    reg = await _register(client)
    token = reg.json()["access_token"]
    old_key = reg.json()["mcp_api_key"]
    r = await client.post("/auth/rotate-mcp-key", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["mcp_api_key"] != old_key


async def test_refresh_token(client: AsyncClient):
    reg = await _register(client)
    r = await client.post("/auth/refresh", json={"refresh_token": reg.json()["refresh_token"]})
    assert r.status_code == 200
    assert "access_token" in r.json()
