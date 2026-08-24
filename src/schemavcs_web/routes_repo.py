"""Repo lifecycle, branch management, and the schema-file editor -- the
direct-CLI-verb authoring path, wired straight into schemavcs's own public
functions. Sync (the file-diffing authoring path) lives in routes_rename.py
since it needs the WebConfirmBridge, unlike everything here."""

from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from schemavcs.cli.commands import branch_cmd, checkout_cmd, migrate_cmd
from schemavcs.dag.persistence import load
from schemavcs.dag.store import BranchNameRetiredError
from schemavcs.dag.walk import ancestors
from schemavcs.storage.paths import read_current_branch, schema_file
from schemavcs_web.session import RepoSession, SessionStore

router = APIRouter()
templates: Jinja2Templates | None = None  # set by app.py at startup


def _require_repo(request: Request, sc_session: str | None) -> RepoSession:
    registry: SessionStore = request.app.state.sessions
    if sc_session is not None:
        existing = registry.get_repo_session(sc_session)
        if existing is not None:
            return existing
    return registry.create_repo_session()


def _index_context(repo_session: RepoSession) -> dict:
    store = load(repo_session.repo_root)
    current_branch = read_current_branch(repo_session.repo_root)
    branches = sorted(store.all_heads().keys())
    text = schema_file(repo_session.repo_root, current_branch).read_text()
    return {
        "branches": branches,
        "current_branch": current_branch,
        "schema_text": text,
        "retired_branches": sorted(store.all_retired()),
    }


@router.get("/", response_class=HTMLResponse)
def index(request: Request, sc_session: str | None = Cookie(default=None)):
    registry: SessionStore = request.app.state.sessions
    is_new = sc_session is None or registry.get_repo_session(sc_session) is None
    repo_session = _require_repo(request, sc_session)

    response = templates.TemplateResponse(request, "index.html", _index_context(repo_session))
    if is_new:
        response.set_cookie("sc_session", repo_session.session_id, httponly=True)
    return response


@router.post("/branch")
def create_branch(
    request: Request,
    name: str = Form(...),
    from_branch: str = Form(""),
    sc_session: str | None = Cookie(default=None),
):
    repo_session = _require_repo(request, sc_session)
    try:
        branch_cmd.create(repo_session.repo_root, name, from_branch=from_branch or None)
    except (ValueError, BranchNameRetiredError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse("/", status_code=303)


@router.post("/branch/delete")
def delete_branch(
    request: Request, name: str = Form(...), sc_session: str | None = Cookie(default=None)
):
    repo_session = _require_repo(request, sc_session)
    try:
        branch_cmd.delete(repo_session.repo_root, name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse("/", status_code=303)


@router.post("/branch/rollback")
def rollback_branch(
    request: Request,
    name: str = Form(...),
    steps: int = Form(1),
    sc_session: str | None = Cookie(default=None),
):
    repo_session = _require_repo(request, sc_session)
    try:
        branch_cmd.rollback(repo_session.repo_root, name, steps)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse("/", status_code=303)


@router.post("/checkout")
def checkout(
    request: Request, branch: str = Form(...), sc_session: str | None = Cookie(default=None)
):
    repo_session = _require_repo(request, sc_session)
    checkout_cmd.run(repo_session.repo_root, branch)
    return RedirectResponse("/", status_code=303)


@router.post("/migrate/create-table")
def create_table(
    request: Request, table: str = Form(...), sc_session: str | None = Cookie(default=None)
):
    repo_session = _require_repo(request, sc_session)
    branch = read_current_branch(repo_session.repo_root)
    migrate_cmd.create_table(repo_session.repo_root, branch, table)
    return RedirectResponse("/", status_code=303)


@router.post("/migrate/add-column")
def add_column(
    request: Request,
    table: str = Form(...),
    column: str = Form(...),
    type_expr: str = Form(...),
    nullable: bool = Form(True),
    sc_session: str | None = Cookie(default=None),
):
    repo_session = _require_repo(request, sc_session)
    branch = read_current_branch(repo_session.repo_root)
    migrate_cmd.add_column(repo_session.repo_root, branch, table, column, type_expr, nullable)
    return RedirectResponse("/", status_code=303)


@router.post("/migrate/alter-column-type")
def alter_column_type(
    request: Request,
    table: str = Form(...),
    column: str = Form(...),
    new_type: str = Form(...),
    sc_session: str | None = Cookie(default=None),
):
    repo_session = _require_repo(request, sc_session)
    branch = read_current_branch(repo_session.repo_root)
    migrate_cmd.alter_column_type(repo_session.repo_root, branch, table, column, new_type)
    return RedirectResponse("/", status_code=303)


@router.post("/migrate/rename-column")
def rename_column(
    request: Request,
    table: str = Form(...),
    old_name: str = Form(...),
    new_name: str = Form(...),
    sc_session: str | None = Cookie(default=None),
):
    repo_session = _require_repo(request, sc_session)
    branch = read_current_branch(repo_session.repo_root)
    migrate_cmd.rename_column(repo_session.repo_root, branch, table, old_name, new_name)
    return RedirectResponse("/", status_code=303)


@router.post("/migrate/drop-table")
def drop_table(
    request: Request, table: str = Form(...), sc_session: str | None = Cookie(default=None)
):
    repo_session = _require_repo(request, sc_session)
    branch = read_current_branch(repo_session.repo_root)
    migrate_cmd.drop_table(repo_session.repo_root, branch, table)
    return RedirectResponse("/", status_code=303)


@router.post("/schema/save")
def save_schema_text(
    request: Request, text: str = Form(...), sc_session: str | None = Cookie(default=None)
):
    """Saves the edited schema-file text as-is, WITHOUT running sync -- the
    human edits, then explicitly clicks "Sync" (routes_rename.py) to run
    detection. Separating these two steps mirrors the real CLI workflow,
    where editing the file and running `schemavcs sync` are two distinct
    actions, not one."""
    repo_session = _require_repo(request, sc_session)
    branch = read_current_branch(repo_session.repo_root)
    schema_file(repo_session.repo_root, branch).write_text(text)
    return RedirectResponse("/", status_code=303)


@router.get("/branches/graph")
def branch_graph(request: Request, sc_session: str | None = Cookie(default=None)):
    repo_session = _require_repo(request, sc_session)
    store = load(repo_session.repo_root)
    heads = store.all_heads()

    nodes: dict[str, dict] = {}
    for head in heads.values():
        for rev in {head, *ancestors(store, head)}:
            if rev not in nodes:
                migration = store.get_node(rev)
                nodes[rev] = {"id": rev, "parents": list(migration.parents)}

    edges = [
        {"from": parent, "to": rev} for rev, node in nodes.items() for parent in node["parents"]
    ]
    return {"heads": heads, "nodes": list(nodes.values()), "edges": edges}
