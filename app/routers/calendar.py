import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import calendar as cal_svc
from app.services import tasks as task_svc

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/connect")
async def connect_google():
    auth_url = cal_svc.get_auth_url()
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def google_callback(
    code: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await cal_svc.exchange_code(db, user, code)
    return {"detail": "Google Calendar connected successfully"}


@router.post("/tasks/{task_id}/sync")
async def sync_task(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task = await task_svc.get_task(db, user.id, task_id)
    event_id = await cal_svc.sync_task_to_calendar(db, user, task)
    return {"google_event_id": event_id}


@router.delete("/tasks/{task_id}/sync", status_code=204)
async def remove_task_sync(
    task_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    task = await task_svc.get_task(db, user.id, task_id)
    await cal_svc.remove_calendar_event(db, user, task)
