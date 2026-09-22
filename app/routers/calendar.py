import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import calendar as cal_svc
from app.services import tasks as task_svc

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/connect")
async def connect_google(user: Annotated[User, Depends(get_current_user)]):
    auth_url, state = cal_svc.get_auth_url(str(user.id))
    response = RedirectResponse(url=auth_url)
    response.set_cookie("oauth_state", state, httponly=True, max_age=600, samesite="lax")
    return response


@router.get("/callback")
async def google_callback(
    code: str,
    state: str,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    import uuid as _uuid

    from sqlalchemy import select

    from app.models.user import User as UserModel

    user_id_str = cal_svc.verify_oauth_state(state)
    result = await db.execute(select(UserModel).where(UserModel.id == _uuid.UUID(user_id_str)))
    user = result.scalar_one_or_none()
    if user is None:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await cal_svc.exchange_code(db, user, code)
    response.delete_cookie("oauth_state")
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
