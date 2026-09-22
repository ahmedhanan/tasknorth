from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.mcp.server import mcp
from app.routers import auth, calendar, projects, tags, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="TaskNorth", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(tags.router)
app.include_router(calendar.router)

# Mount FastMCP server (SSE transport) — MCP clients connect to /mcp/sse
app.mount("/mcp", mcp.http_app(transport="sse"))


@app.get("/health")
async def health():
    return {"status": "ok"}
