import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tag import Tag
from app.models.task import Task, TaskPriority, TaskStatus
from app.schemas.task import TaskCreate, TaskUpdate


def _task_query(user_id: uuid.UUID):
    return (
        select(Task)
        .where(Task.user_id == user_id)
        .options(selectinload(Task.tags))
    )


async def list_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    tag_name: str | None = None,
    due_before: datetime | None = None,
    search: str | None = None,
    parent_id: uuid.UUID | None = None,
    top_level_only: bool = False,
) -> list[Task]:
    q = _task_query(user_id)
    if project_id:
        q = q.where(Task.project_id == project_id)
    if status:
        q = q.where(Task.status == status)
    if priority:
        q = q.where(Task.priority == priority)
    if due_before:
        q = q.where(Task.due_date <= due_before)
    if search:
        q = q.where(or_(Task.title.ilike(f"%{search}%"), Task.description.ilike(f"%{search}%")))
    if parent_id is not None:
        q = q.where(Task.parent_task_id == parent_id)
    elif top_level_only:
        q = q.where(Task.parent_task_id.is_(None))
    if tag_name:
        q = q.join(Task.tags).where(Tag.name == tag_name)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_task(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    result = await db.execute(
        _task_query(user_id).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


async def _resolve_tags(db: AsyncSession, user_id: uuid.UUID, tag_ids: list[uuid.UUID]) -> list[Tag]:
    if not tag_ids:
        return []
    result = await db.execute(select(Tag).where(Tag.id.in_(tag_ids), Tag.user_id == user_id))
    return list(result.scalars().all())


async def create_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: TaskCreate,
    parent_task_id: uuid.UUID | None = None,
) -> Task:
    tag_ids = data.tag_ids
    task_data = data.model_dump(exclude={"tag_ids"})
    task = Task(user_id=user_id, parent_task_id=parent_task_id, **task_data)
    task.tags = await _resolve_tags(db, user_id, tag_ids)
    db.add(task)
    await db.commit()
    await db.refresh(task, ["tags"])
    return task


async def update_task(
    db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, data: TaskUpdate
) -> Task:
    task = await get_task(db, user_id, task_id)
    update = data.model_dump(exclude_unset=True)
    tag_ids = update.pop("tag_ids", None)
    for field, value in update.items():
        setattr(task, field, value)
    if tag_ids is not None:
        task.tags = await _resolve_tags(db, user_id, tag_ids)
    await db.commit()
    await db.refresh(task, ["tags"])
    return task


async def complete_task(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = await get_task(db, user_id, task_id)
    task.status = TaskStatus.done
    await db.commit()
    await db.refresh(task, ["tags"])
    return task


async def delete_task(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    task = await get_task(db, user_id, task_id)
    await db.delete(task)
    await db.commit()
