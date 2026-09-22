"""
FastMCP server — TaskNorth tools via SSE transport.
Mounted at /mcp/sse in main.py.

Auth: set X-Api-Key header in your MCP client config.
The key never appears as a tool parameter — it is read from the SSE request header.
"""
import uuid
from datetime import datetime
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.tag import Tag
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import projects as proj_svc
from app.services import tasks as task_svc

mcp = FastMCP("tasknorth")


async def _resolve_user(ctx: Context):
    """Read X-Api-Key header and return (user, open db session). Caller must close the session."""
    api_key = ctx.request_context.request.headers.get("x-api-key", "")
    if not api_key:
        raise ToolError("Missing X-Api-Key header. Set it in your MCP client config.")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.mcp_api_key == api_key))
        user = result.scalar_one_or_none()
        if user is None:
            raise ToolError("Invalid MCP API key.")
        return user.id  # return only the scalar to avoid detached-instance errors


def _parse_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ToolError(f"Invalid {field}: '{value}' is not a valid UUID.")


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, AttributeError):
        raise ToolError(f"Invalid {field}: '{value}' must be ISO 8601, e.g. '2026-10-01T09:00:00'.")


def _parse_status(value: str | None) -> TaskStatus | None:
    if value is None:
        return None
    try:
        return TaskStatus(value)
    except ValueError:
        raise ToolError(f"Invalid status '{value}'. Must be: todo, in_progress, done, cancelled.")


def _parse_priority(value: str | None) -> TaskPriority | None:
    if value is None:
        return None
    try:
        return TaskPriority(value)
    except ValueError:
        raise ToolError(f"Invalid priority '{value}'. Must be: low, medium, high, urgent.")


# ── Task tools ────────────────────────────────────────────────────────────────

@mcp.tool()
async def list_tasks(
    ctx: Context,
    project_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    due_before: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    List tasks for the authenticated user (top-level only, no subtasks).

    Filters (all optional):
    - project_id: UUID string of a project
    - status: "todo" | "in_progress" | "done" | "cancelled"
    - priority: "low" | "medium" | "high" | "urgent"
    - search: full-text search over title and description
    - due_before: ISO 8601 datetime, e.g. "2026-10-01T09:00:00"
    - limit / offset: pagination (default limit=50)
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        tasks = await task_svc.list_tasks(
            db,
            user_id,
            project_id=_parse_uuid(project_id, "project_id") if project_id else None,
            status=_parse_status(status),
            priority=_parse_priority(priority),
            search=search,
            due_before=_parse_datetime(due_before, "due_before") if due_before else None,
            top_level_only=True,
            limit=limit,
            offset=offset,
        )
        return [
            {
                "id": str(t.id),
                "title": t.title,
                "description": t.description,
                "status": t.status.value,
                "priority": t.priority.value,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "project_id": str(t.project_id) if t.project_id else None,
                "tags": [tag.name for tag in t.tags],
            }
            for t in tasks
        ]


@mcp.tool()
async def get_task(ctx: Context, task_id: str) -> dict[str, Any]:
    """
    Get full details of a single task including description, tags, and subtask count.

    - task_id: UUID string (required)
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        task = await task_svc.get_task(db, user_id, _parse_uuid(task_id, "task_id"))
        return {
            "id": str(task.id),
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority.value,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "project_id": str(task.project_id) if task.project_id else None,
            "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
            "google_event_id": task.google_event_id,
            "tags": [{"id": str(t.id), "name": t.name} for t in task.tags],
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }


@mcp.tool()
async def create_task(
    ctx: Context,
    title: str,
    description: str | None = None,
    priority: str = "medium",
    status: str = "todo",
    due_date: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a new task.

    - title: required
    - priority: "low" | "medium" | "high" | "urgent" (default: "medium")
    - status: "todo" | "in_progress" | "done" | "cancelled" (default: "todo")
    - due_date: ISO 8601 string, e.g. "2026-10-01T09:00:00" (optional)
    - project_id: UUID of an existing project (optional)
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        data = TaskCreate(
            title=title,
            description=description,
            priority=_parse_priority(priority) or TaskPriority.medium,
            status=_parse_status(status) or TaskStatus.todo,
            due_date=_parse_datetime(due_date, "due_date") if due_date else None,
            project_id=_parse_uuid(project_id, "project_id") if project_id else None,
        )
        task = await task_svc.create_task(db, user_id, data)
        return {"id": str(task.id), "title": task.title, "status": task.status.value, "priority": task.priority.value}


@mcp.tool()
async def update_task(
    ctx: Context,
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
) -> dict[str, Any]:
    """
    Update fields on an existing task. Only provided fields are changed.

    - task_id: UUID string (required)
    - status: "todo" | "in_progress" | "done" | "cancelled"
    - priority: "low" | "medium" | "high" | "urgent"
    - due_date: ISO 8601 string, or omit to leave unchanged
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        data = TaskUpdate(
            title=title,
            description=description,
            status=_parse_status(status),
            priority=_parse_priority(priority),
            due_date=_parse_datetime(due_date, "due_date") if due_date else None,
        )
        task = await task_svc.update_task(db, user_id, _parse_uuid(task_id, "task_id"), data)
        return {"id": str(task.id), "title": task.title, "status": task.status.value}


@mcp.tool()
async def complete_task(ctx: Context, task_id: str) -> dict[str, str]:
    """Mark a task as done. - task_id: UUID string"""
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        task = await task_svc.complete_task(db, user_id, _parse_uuid(task_id, "task_id"))
        return {"id": str(task.id), "status": task.status.value}


@mcp.tool()
async def cancel_task(ctx: Context, task_id: str) -> dict[str, str]:
    """Mark a task as cancelled. - task_id: UUID string"""
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        task = await task_svc.cancel_task(db, user_id, _parse_uuid(task_id, "task_id"))
        return {"id": str(task.id), "status": task.status.value}


@mcp.tool()
async def delete_task(ctx: Context, task_id: str) -> dict[str, str]:
    """Delete a task and all its subtasks. - task_id: UUID string"""
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        await task_svc.delete_task(db, user_id, _parse_uuid(task_id, "task_id"))
        return {"deleted": task_id}


@mcp.tool()
async def create_subtask(
    ctx: Context,
    parent_task_id: str,
    title: str,
    description: str | None = None,
    priority: str = "medium",
) -> dict[str, Any]:
    """
    Create a subtask under an existing task.

    - parent_task_id: UUID string of the parent task (required)
    - priority: "low" | "medium" | "high" | "urgent" (default: "medium")
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        data = TaskCreate(title=title, description=description, priority=_parse_priority(priority) or TaskPriority.medium)
        task = await task_svc.create_task(
            db, user_id, data, parent_task_id=_parse_uuid(parent_task_id, "parent_task_id")
        )
        return {"id": str(task.id), "title": task.title, "parent_task_id": parent_task_id}


@mcp.tool()
async def list_subtasks(ctx: Context, parent_task_id: str) -> list[dict[str, Any]]:
    """
    List all subtasks of a given task.

    - parent_task_id: UUID string of the parent task
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        tasks = await task_svc.list_tasks(
            db, user_id, parent_id=_parse_uuid(parent_task_id, "parent_task_id")
        )
        return [{"id": str(t.id), "title": t.title, "status": t.status.value, "priority": t.priority.value} for t in tasks]


@mcp.tool()
async def search_tasks(ctx: Context, query: str) -> list[dict[str, Any]]:
    """
    Full-text search over task titles and descriptions.

    - query: search string (partial matches supported)
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        tasks = await task_svc.list_tasks(db, user_id, search=query)
        return [{"id": str(t.id), "title": t.title, "status": t.status.value, "priority": t.priority.value} for t in tasks]


# ── Project tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def list_projects(ctx: Context) -> list[dict[str, Any]]:
    """List all projects for the authenticated user."""
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        projects = await proj_svc.list_projects(db, user_id)
        return [{"id": str(p.id), "name": p.name, "description": p.description, "color": p.color} for p in projects]


@mcp.tool()
async def create_project(
    ctx: Context, name: str, description: str | None = None, color: str | None = None
) -> dict[str, Any]:
    """
    Create a new project.

    - name: required
    - color: hex color code, e.g. "#6366f1" (optional)
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        try:
            data = ProjectCreate(name=name, description=description, color=color)
        except Exception as e:
            raise ToolError(str(e))
        project = await proj_svc.create_project(db, user_id, data)
        return {"id": str(project.id), "name": project.name}


@mcp.tool()
async def update_project(
    ctx: Context,
    project_id: str,
    name: str | None = None,
    description: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    """
    Update a project's name, description, or color.

    - project_id: UUID string (required)
    - color: hex color code, e.g. "#6366f1" (optional)
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        try:
            data = ProjectUpdate(name=name, description=description, color=color)
        except Exception as e:
            raise ToolError(str(e))
        project = await proj_svc.update_project(db, user_id, _parse_uuid(project_id, "project_id"), data)
        return {"id": str(project.id), "name": project.name}


@mcp.tool()
async def delete_project(ctx: Context, project_id: str) -> dict[str, str]:
    """
    Delete a project. Tasks become unassigned (not deleted).

    - project_id: UUID string
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        await proj_svc.delete_project(db, user_id, _parse_uuid(project_id, "project_id"))
        return {"deleted": project_id}


# ── Tag tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def list_tags(ctx: Context) -> list[dict[str, Any]]:
    """List all tags for the authenticated user."""
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tag).where(Tag.user_id == user_id))
        tags = result.scalars().all()
        return [{"id": str(t.id), "name": t.name, "color": t.color} for t in tags]


@mcp.tool()
async def create_tag(ctx: Context, name: str, color: str | None = None) -> dict[str, Any]:
    """
    Create a new tag.

    - name: required
    - color: hex color code, e.g. "#10b981" (optional)
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        tag = Tag(user_id=user_id, name=name, color=color)
        db.add(tag)
        await db.commit()
        await db.refresh(tag)
        return {"id": str(tag.id), "name": tag.name, "color": tag.color}


@mcp.tool()
async def attach_tag(ctx: Context, task_id: str, tag_id: str) -> dict[str, Any]:
    """
    Attach an existing tag to a task.

    - task_id: UUID string of the task
    - tag_id: UUID string of the tag (get IDs from list_tags)
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        task_result = await db.execute(
            select(Task)
            .where(Task.id == _parse_uuid(task_id, "task_id"), Task.user_id == user_id)
            .options(selectinload(Task.tags))
        )
        task = task_result.scalar_one_or_none()
        if task is None:
            raise ToolError(f"Task {task_id} not found.")
        tag_result = await db.execute(
            select(Tag).where(Tag.id == _parse_uuid(tag_id, "tag_id"), Tag.user_id == user_id)
        )
        tag = tag_result.scalar_one_or_none()
        if tag is None:
            raise ToolError(f"Tag {tag_id} not found.")
        if tag not in task.tags:
            task.tags.append(tag)
            await db.commit()
        return {"task_id": task_id, "tag_id": tag_id, "attached": True}


@mcp.tool()
async def detach_tag(ctx: Context, task_id: str, tag_id: str) -> dict[str, Any]:
    """
    Remove a tag from a task.

    - task_id: UUID string of the task
    - tag_id: UUID string of the tag
    """
    user_id = await _resolve_user(ctx)
    async with AsyncSessionLocal() as db:
        task_result = await db.execute(
            select(Task)
            .where(Task.id == _parse_uuid(task_id, "task_id"), Task.user_id == user_id)
            .options(selectinload(Task.tags))
        )
        task = task_result.scalar_one_or_none()
        if task is None:
            raise ToolError(f"Task {task_id} not found.")
        task.tags = [t for t in task.tags if str(t.id) != tag_id]
        await db.commit()
        return {"task_id": task_id, "tag_id": tag_id, "detached": True}
