# TaskNorth

A todo API with Google Calendar integration, multi-user JWT auth, and a built-in [FastMCP](https://github.com/jlowin/fastmcp) server — so any MCP client (Claude Desktop, custom agents) can manage tasks over SSE without touching REST.

**Stack:** FastAPI · SQLAlchemy (async) · PostgreSQL · FastMCP 4.x · asyncpg · bcrypt · python-jose

---

## Quick start

### 1. Clone and set up the environment

```bash
git clone <repo-url> tasknorth
cd tasknorth
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>/<db>?sslmode=require
JWT_SECRET=<at-least-32-random-chars>

# Optional — only needed for Google Calendar integration
GOOGLE_CLIENT_ID=<your-client-id>
GOOGLE_CLIENT_SECRET=<your-client-secret>
GOOGLE_REDIRECT_URI=http://localhost:8000/calendar/callback
```

> **Neon / hosted Postgres:** paste the connection string from your provider and keep `?sslmode=require`. The app strips it from the URL and passes it correctly to asyncpg.

### 3. Run the server

The app auto-creates all tables on first startup (no migration step needed for local dev).

```bash
uvicorn app.main:app --reload
```

Server is now at **http://localhost:8000**

| URL | Purpose |
|---|---|
| `http://localhost:8000/docs` | Swagger UI — interactive API explorer |
| `http://localhost:8000/redoc` | ReDoc — clean reference docs |
| `http://localhost:8000/mcp/sse` | FastMCP SSE endpoint for agents |

---

## Authentication

TaskNorth uses **JWT** for REST endpoints and a separate **MCP API key** for agent access.

### Register

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
```

Response:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "mcp_api_key": "vOjnoGm9MDHGzPV_..."
}
```

Save both tokens. The `mcp_api_key` is permanent (doesn't expire) — use it for MCP client config.

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}'
```

### Refresh access token

```bash
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

For the rest of this guide, set:

```bash
export TOKEN="eyJ..."   # your access_token
```

---

## Projects

Group tasks under named projects with an optional colour.

### Create a project

```bash
curl -X POST http://localhost:8000/projects/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project", "description": "Optional description", "color": "#6366f1"}'
```

### List projects

```bash
curl http://localhost:8000/projects/ \
  -H "Authorization: Bearer $TOKEN"
```

### Update / delete

```bash
# Update
curl -X PATCH http://localhost:8000/projects/<project_id> \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Renamed"}'

# Delete (cascades to tasks)
curl -X DELETE http://localhost:8000/projects/<project_id> \
  -H "Authorization: Bearer $TOKEN"
```

---

## Tasks

### Create a task

All fields except `title` are optional.

```bash
curl -X POST http://localhost:8000/tasks/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Set up CI pipeline",
    "description": "GitHub Actions for tests and deploy",
    "priority": "urgent",
    "status": "todo",
    "due_date": "2026-10-01T09:00:00",
    "project_id": "<project_id>",
    "tag_ids": ["<tag_id>"]
  }'
```

**Priority values:** `low` · `medium` · `high` · `urgent`  
**Status values:** `todo` · `in_progress` · `done` · `cancelled`

### List tasks (with filters)

```bash
# All top-level tasks
curl "http://localhost:8000/tasks/" \
  -H "Authorization: Bearer $TOKEN"

# Filter by status
curl "http://localhost:8000/tasks/?status=in_progress" \
  -H "Authorization: Bearer $TOKEN"

# Filter by priority
curl "http://localhost:8000/tasks/?priority=urgent" \
  -H "Authorization: Bearer $TOKEN"

# Filter by project
curl "http://localhost:8000/tasks/?project_id=<project_id>" \
  -H "Authorization: Bearer $TOKEN"

# Filter by tag name
curl "http://localhost:8000/tasks/?tag=backend" \
  -H "Authorization: Bearer $TOKEN"

# Due before a date
curl "http://localhost:8000/tasks/?due_before=2026-10-15T00:00:00" \
  -H "Authorization: Bearer $TOKEN"

# Full-text search (title + description)
curl "http://localhost:8000/tasks/?search=pipeline" \
  -H "Authorization: Bearer $TOKEN"

# Combine filters freely
curl "http://localhost:8000/tasks/?priority=urgent&status=todo&project_id=<project_id>" \
  -H "Authorization: Bearer $TOKEN"
```

### Get, update, delete

```bash
# Get single task
curl "http://localhost:8000/tasks/<task_id>" \
  -H "Authorization: Bearer $TOKEN"

# Partial update (only send fields you want to change)
curl -X PATCH "http://localhost:8000/tasks/<task_id>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'

# Delete
curl -X DELETE "http://localhost:8000/tasks/<task_id>" \
  -H "Authorization: Bearer $TOKEN"
```

### Subtasks

```bash
# Create a subtask under a parent
curl -X POST "http://localhost:8000/tasks/<parent_task_id>/subtasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Write workflow YAML", "priority": "high"}'

# List subtasks of a task
curl "http://localhost:8000/tasks/<parent_task_id>/subtasks" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Tags

### Create a tag

```bash
curl -X POST http://localhost:8000/tags \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "backend", "color": "#10b981"}'
```

### List / delete tags

```bash
curl http://localhost:8000/tags -H "Authorization: Bearer $TOKEN"
curl -X DELETE http://localhost:8000/tags/<tag_id> -H "Authorization: Bearer $TOKEN"
```

### Attach / detach tags on a task

```bash
# Attach
curl -X POST "http://localhost:8000/tasks/<task_id>/tags/<tag_id>" \
  -H "Authorization: Bearer $TOKEN"

# Detach
curl -X DELETE "http://localhost:8000/tasks/<task_id>/tags/<tag_id>" \
  -H "Authorization: Bearer $TOKEN"
```

> You can also set `tag_ids` directly in the task create/update body to set all tags in one call.

---

## Google Calendar integration

### 1. Create OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → APIs & Services → Credentials → **OAuth 2.0 Client ID** (Web application)
3. Add `http://localhost:8000/calendar/callback` as an authorised redirect URI
4. Copy the client ID and secret into `.env`

### 2. Connect your account

Open this URL in a browser (you must be logged in — the OAuth callback uses your JWT, so visit after logging in):

```
http://localhost:8000/calendar/connect
```

Complete the Google consent screen. You'll be redirected back and see:

```json
{"detail": "Google Calendar connected successfully"}
```

### 3. Sync a task to Calendar

The task must have a `due_date`.

```bash
curl -X POST "http://localhost:8000/calendar/tasks/<task_id>/sync" \
  -H "Authorization: Bearer $TOKEN"
```

Response: `{"google_event_id": "abc123..."}` — the event appears in your primary Google Calendar.

### 4. Remove the calendar event

```bash
curl -X DELETE "http://localhost:8000/calendar/tasks/<task_id>/sync" \
  -H "Authorization: Bearer $TOKEN"
```

---

## MCP server (for AI agents)

The FastMCP server runs on the same process as the REST API, mounted at `/mcp/sse`.

### Connect Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tasknorth": {
      "url": "http://localhost:8000/mcp/sse",
      "headers": {
        "x-api-key": "<your mcp_api_key from /auth/register>"
      }
    }
  }
}
```

Restart Claude Desktop. TaskNorth tools will appear in the tool picker.

### Available MCP tools

| Tool | Description |
|---|---|
| `list_tasks` | List tasks with optional `status`, `priority`, `project_id`, `search` filters |
| `create_task` | Create a task (`title` required; optional `description`, `priority`, `due_date`, `project_id`) |
| `update_task` | Update any field on a task by `task_id` |
| `complete_task` | Shorthand — marks a task as `done` |
| `delete_task` | Delete a task by `task_id` |
| `create_subtask` | Create a child task under a `parent_task_id` |
| `list_projects` | List all projects |
| `create_project` | Create a project (`name` required; optional `description`, `color`) |
| `search_tasks` | Full-text search over task titles and descriptions |

Every tool takes `api_key` as its first argument — this is your `mcp_api_key`.

### Example agent prompt

> "Create a project called 'Q4 Launch', then add three urgent tasks to it: write copy, design assets, and schedule social posts — all due October 15."

Claude will call `create_project`, then three `create_task` calls, chaining the project ID automatically.

---

## Database migrations (production)

The auto-create on startup is convenient for development. For production, use Alembic:

```bash
# Generate a migration after model changes
alembic revision --autogenerate -m "describe change"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```

---

## Project structure

```
tasknorth/
├── app/
│   ├── main.py              # FastAPI app + MCP mount
│   ├── config.py            # Settings via pydantic-settings
│   ├── database.py          # Async SQLAlchemy engine + session
│   ├── models/              # ORM models (User, Project, Task, Tag)
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/             # Route handlers (auth, tasks, projects, tags, calendar)
│   ├── services/            # Business logic (shared by routers and MCP tools)
│   ├── auth/                # JWT + MCP API key dependencies
│   └── mcp/
│       └── server.py        # FastMCP tool definitions
├── alembic/                 # DB migrations
├── pyproject.toml
├── requirements.txt
└── .env.example
```
