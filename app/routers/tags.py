import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.tag import Tag
from app.models.task import Task
from app.models.user import User
from app.schemas.tag import TagCreate, TagResponse, TagUpdate

router = APIRouter(prefix="/tags", tags=["tags"])
task_tag_router = APIRouter(tags=["tags"])


@router.get("/", response_model=list[TagResponse])
async def list_tags(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Tag).where(Tag.user_id == user.id))
    return list(result.scalars().all())


@router.post("/", response_model=TagResponse, status_code=http_status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tag = Tag(user_id=user.id, **body.model_dump())
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.patch("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: uuid.UUID,
    body: TagUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Tag not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tag, field, value)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Tag not found")
    await db.delete(tag)
    await db.commit()


@task_tag_router.post("/tasks/{task_id}/tags/{tag_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def attach_tag(
    task_id: uuid.UUID,
    tag_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task_result = await db.execute(
        select(Task).where(Task.id == task_id, Task.user_id == user.id).options(selectinload(Task.tags))
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Task not found")
    tag_result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    tag = tag_result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Tag not found")
    if tag not in task.tags:
        task.tags.append(tag)
        await db.commit()


@task_tag_router.delete("/tasks/{task_id}/tags/{tag_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def detach_tag(
    task_id: uuid.UUID,
    tag_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task_result = await db.execute(
        select(Task).where(Task.id == task_id, Task.user_id == user.id).options(selectinload(Task.tags))
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Task not found")
    task.tags = [t for t in task.tags if t.id != tag_id]
    await db.commit()
