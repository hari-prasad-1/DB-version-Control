"""Emits DDL for a branch's full history from scratch -- the exact same
call the CLI's `emit-ddl` command makes (emit_ddl_cmd.py), just rendered in
a browser instead of printed to stdout."""

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from schemavcs.dag.persistence import load
from schemavcs.dag.walk import topological_order
from schemavcs.ddl.emitter import emit_ddl
from schemavcs_web.routes_repo import _require_repo

router = APIRouter()
templates: Jinja2Templates | None = None


@router.get("/branches/{branch}/ddl", response_class=HTMLResponse)
def branch_ddl(request: Request, branch: str, sc_session: str | None = Cookie(default=None)):
    repo_session = _require_repo(request, sc_session)
    store = load(repo_session.repo_root)
    head = store.head(branch)
    ordered_revisions = topological_order(store, head)

    operations = tuple(
        op
        for revision_id in ordered_revisions
        for compound in store.get_node(revision_id).operations
        for op in compound.operations
    )
    sql = emit_ddl(operations)
    return templates.TemplateResponse(request, "ddl.html", {"branch": branch, "sql": sql})
