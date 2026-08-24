"""FastAPI app wiring. No auth, no persistence beyond one process's
lifetime -- this is a demo/evaluation tool for walking through the engine,
not a production multi-user service (see decisions.md)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from schemavcs_web import routes_ddl, routes_merge, routes_rename, routes_repo
from schemavcs_web.session import SessionStore

_HERE = Path(__file__).resolve().parent

app = FastAPI(title="schemavcs")
app.state.sessions = SessionStore()

templates = Jinja2Templates(directory=str(_HERE / "templates"))
routes_repo.templates = templates
routes_merge.templates = templates
routes_rename.templates = templates
routes_ddl.templates = templates

app.include_router(routes_repo.router)
app.include_router(routes_merge.router)
app.include_router(routes_rename.router)
app.include_router(routes_ddl.router)

static_dir = _HERE / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
