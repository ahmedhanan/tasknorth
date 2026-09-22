"""
FastMCP server exposing TaskNorth tools via SSE transport.
Mounted at /mcp in main.py.
Auth: pass X-Api-Key header with the mcp_api_key returned at registration.
"""
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.task import TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import projects as proj_svc
from app.services import tasks as task_svc

mcp = FastMCP("tasknorth")


async def _resolve_user(api_key: str, db: AsyncSession) -> User:
    from fastmcp.exceptions import ToolError
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.mcp_api_key == api_key))
    user = result.scalar_one_or_none()
    if user is None:
        raise ToolError("Invalid MCP API key")
    return user


@mcp.tool()
async def list_tasks(
    api_key: str,
    project_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """List tasks for the authenticated user with optional filters."""
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        tasks = await task_svc.list_tasks(
            db,
            user.id,
            project_id=uuid.UUID(project_id) if project_id else None,
            status=TaskStatus(status) if status else None,
            priority=TaskPriority(priority) if priority else None,
            search=search,
        )
        return [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status.value,
                "priority": t.priority.value,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "project_id": str(t.project_id) if t.project_id else None,
                "tags": [tag.name for tag in t.tags],
            }
            for t in tasks
        ]


@mcp.tool()
async def create_task(
    api_key: str,
    title: str,
    description: str | None = None,
    priority: str = "medium",
    due_date: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Create a new task."""
    from datetime import datetime

    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        data = TaskCreate(
            title=title,
            description=description,
            priority=TaskPriority(priority),
            due_date=datetime.fromisoformat(due_date) if due_date else None,
            project_id=uuid.UUID(project_id) if project_id else None,
        )
        task = await task_svc.create_task(db, user.id, data)
        return {"id": str(task.id), "title": task.title, "status": task.status.value}


@mcp.tool()
async def update_task(
    api_key: str,
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
) -> dict[str, Any]:
    """Update fields on an existing task."""
    from datetime import datetime

    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        data = TaskUpdate(
            title=title,
            description=description,
            status=TaskStatus(status) if status else None,
            priority=TaskPriority(priority) if priority else None,
            due_date=datetime.fromisoformat(due_date) if due_date else None,
        )
        task = await task_svc.update_task(db, user.id, uuid.UUID(task_id), data)
        return {"id": str(task.id), "title": task.title, "status": task.status.value}


@mcp.tool()
async def complete_task(api_key: str, task_id: str) -> dict[str, str]:
    """Mark a task as done."""
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        task = await task_svc.complete_task(db, user.id, uuid.UUID(task_id))
        return {"id": str(task.id), "status": task.status.value}


@mcp.tool()
async def delete_task(api_key: str, task_id: str) -> dict[str, str]:
    """Delete a task."""
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        await task_svc.delete_task(db, user.id, uuid.UUID(task_id))
        return {"deleted": task_id}


@mcp.tool()
async def create_subtask(
    api_key: str,
    parent_task_id: str,
    title: str,
    description: str | None = None,
    priority: str = "medium",
) -> dict[str, Any]:
    """Create a subtask under an existing task."""
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        data = TaskCreate(title=title, description=description, priority=TaskPriority(priority))
        task = await task_svc.create_task(db, user.id, data, parent_task_id=uuid.UUID(parent_task_id))
        return {"id": str(task.id), "title": task.title, "parent_task_id": parent_task_id}


@mcp.tool()
async def list_projects(api_key: str) -> list[dict[str, Any]]:
    """List all projects for the authenticated user."""
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        projects = await proj_svc.list_projects(db, user.id)
        return [{"id": str(p.id), "name": p.name, "description": p.description} for p in projects]


@mcp.tool()
async def create_project(api_key: str, name: str, description: str | None = None, color: str | None = None) -> dict[str, Any]:
    """Create a new project."""
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        data = ProjectCreate(name=name, description=description, color=color)
        project = await proj_svc.create_project(db, user.id, data)
        return {"id": str(project.id), "name": project.name}


@mcp.tool()
async def search_tasks(api_key: str, query: str) -> list[dict[str, Any]]:
    """Full-text search over task titles and descriptions."""
    async with AsyncSessionLocal() as db:
        user = await _resolve_user(api_key, db)
        tasks = await task_svc.list_tasks(db, user.id, search=query)
        return [
            {"id": str(t.id), "title": t.title, "status": t.status.value, "priority": t.priority.value}
            for t in tasks
        ]
