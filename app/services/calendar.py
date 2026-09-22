import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
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


def get_auth_url() -> str:
    flow = get_oauth_flow()
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return auth_url


async def exchange_code(db: AsyncSession, user: User, code: str) -> None:
    flow = get_oauth_flow()
    flow.fetch_token(code=code)
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


async def sync_task_to_calendar(db: AsyncSession, user: User, task: Task) -> str:
    if not task.due_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task must have a due_date to sync to Google Calendar.",
        )
    creds = _get_credentials(user)
    service = build("calendar", "v3", credentials=creds)

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
        event = service.events().update(
            calendarId="primary", eventId=task.google_event_id, body=event_body
        ).execute()
    else:
        event = service.events().insert(calendarId="primary", body=event_body).execute()

    task.google_event_id = event["id"]
    await db.commit()
    return event["id"]


async def remove_calendar_event(db: AsyncSession, user: User, task: Task) -> None:
    if not task.google_event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No calendar event linked.")
    creds = _get_credentials(user)
    service = build("calendar", "v3", credentials=creds)
    service.events().delete(calendarId="primary", eventId=task.google_event_id).execute()
    task.google_event_id = None
    await db.commit()
