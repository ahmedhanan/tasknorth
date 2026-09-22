from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal, Base, engine
from app.mcp.server import mcp
from app.routers import auth, calendar, projects, tasks
from app.routers.tags import router as tags_router
from app.routers.tags import task_tag_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.env == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="TaskNorth", version="0.2.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(tags_router)
app.include_router(task_tag_router)
app.include_router(calendar.router)

app.mount("/mcp", mcp.http_app(transport="sse"))


@app.get("/health")
async def health():
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
