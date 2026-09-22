import asyncio
import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.task import Task
from app.models.user import User

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def get_oauth_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def get_auth_url(user_id: str) -> str:
    """Return (auth_url, state). state is signed with JWT secret to prevent CSRF."""
    from jose import jwt as jose_jwt

    flow = get_oauth_flow()
    state = jose_jwt.encode(
        {"sub": user_id, "purpose": "oauth_state"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline", state=state)
    return auth_url, state


def verify_oauth_state(state: str) -> str:
    """Verify the signed state and return the user_id embedded in it."""
    from jose import JWTError, jwt as jose_jwt

    try:
        payload = jose_jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("purpose") != "oauth_state":
            raise ValueError("bad state purpose")
        return payload["sub"]
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state") from exc


async def exchange_code(db: AsyncSession, user: User, code: str) -> None:
    flow = get_oauth_flow()
    await asyncio.to_thread(flow.fetch_token, code=code)
    creds = flow.credentials
    user.google_credentials = creds.to_json()
    await db.commit()


def _get_credentials(user: User) -> Credentials:
    if not user.google_credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar not connected. Visit /calendar/connect first.",
        )
    return Credentials.from_authorized_user_info(json.loads(user.google_credentials), SCOPES)


async def _get_refreshed_credentials(db: AsyncSession, user: User) -> Credentials:
    creds = _get_credentials(user)
    if creds.expired and creds.refresh_token:
        await asyncio.to_thread(creds.refresh, Request())
        user.google_credentials = creds.to_json()
        await db.commit()
    return creds


async def sync_task_to_calendar(db: AsyncSession, user: User, task: Task) -> str:
    if not task.due_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task must have a due_date to sync to Google Calendar.",
        )
    creds = await _get_refreshed_credentials(db, user)
    service = await asyncio.to_thread(build, "calendar", "v3", credentials=creds)

    due = task.due_date
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)

    event_body = {
        "summary": task.title,
        "description": task.description or "",
        "start": {"dateTime": due.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": due.isoformat(), "timeZone": "UTC"},
    }

    if task.google_event_id:
        event = await asyncio.to_thread(
            lambda: service.events().update(
                calendarId="primary", eventId=task.google_event_id, body=event_body
            ).execute()
        )
    else:
        event = await asyncio.to_thread(
            lambda: service.events().insert(calendarId="primary", body=event_body).execute()
        )

    task.google_event_id = event["id"]
    await db.commit()
    return event["id"]


async def remove_calendar_event(db: AsyncSession, user: User, task: Task) -> None:
    if not task.google_event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No calendar event linked.")
    creds = await _get_refreshed_credentials(db, user)
    service = await asyncio.to_thread(build, "calendar", "v3", credentials=creds)
    await asyncio.to_thread(
        lambda: service.events().delete(calendarId="primary", eventId=task.google_event_id).execute()
    )
    task.google_event_id = None
    await db.commit()
