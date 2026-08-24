"""Drives generate_operations() -- the file-diffing authoring path -- one
click at a time via WebConfirmBridge, then commits the result through the
exact same DagStore.append + sync_model_file path migrate_cmd's CLI verbs
use (mirrors generate_migration_cmd.py's `run()`, just non-blocking)."""

from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from schemavcs.dag.persistence import load, save
from schemavcs.dag.revision_id import make_revision_id
from schemavcs.dag.walk import replay
from schemavcs.dsl.parser import parse
from schemavcs.model_sync.sync import sync_model_file
from schemavcs.rename_detect.detector import RenameProposal
from schemavcs.snapshot.diff import diff_snapshot
from schemavcs.snapshot.to_operations import generate_operations
from schemavcs.storage.paths import read_current_branch, schema_file
from schemavcs_web.confirm_adapter import proposal_to_dict
from schemavcs_web.routes_repo import _require_repo
from schemavcs_web.session import RenameSession, SessionStore

router = APIRouter()
templates: Jinja2Templates | None = None


@router.post("/sync/start")
def start_sync(request: Request, sc_session: str | None = Cookie(default=None)):
    repo_session = _require_repo(request, sc_session)
    registry: SessionStore = request.app.state.sessions
    branch = read_current_branch(repo_session.repo_root)
    store = load(repo_session.repo_root)
    head = store.head(branch)
    old_snapshot = replay(store, head, branch)
    new_raw_tables = parse(schema_file(repo_session.repo_root, branch).read_text())
    diff = diff_snapshot(old_snapshot, new_raw_tables)

    session = RenameSession(session_id=f"{repo_session.session_id}:{branch}", branch=branch)
    bridge = session.bridge

    def _finish():
        generated = generate_operations(diff, confirm=bridge.ask)
        if not generated.operations:
            return None
        revision_id = make_revision_id((head,), generated.operations)
        store.append(revision_id, branch, (head,), generated.operations)
        save(store, repo_session.repo_root)
        sync_model_file(repo_session.repo_root, store, branch)
        return revision_id

    bridge.run_in_background(_finish)
    registry.register_rename_session(session)
    return {"session_id": session.session_id}


@router.get("/sync/{session_id}/step", response_class=HTMLResponse)
def sync_step(request: Request, session_id: str):
    registry: SessionStore = request.app.state.sessions
    session = registry.get_rename_session(session_id)
    if session is None:
        raise HTTPException(404, "unknown sync session")

    if session.bridge.is_done():
        try:
            revision_id = session.bridge.result()
        except Exception as exc:  # noqa: BLE001 -- surfaced to the page
            return templates.TemplateResponse(
                request, "sync_error.html", {"error": str(exc), "session_id": session_id}
            )
        return templates.TemplateResponse(
            request,
            "sync_done.html",
            {"session_id": session_id, "revision_id": revision_id, "branch": session.branch},
        )

    proposal: RenameProposal | None = session.bridge.poll_question(timeout=5.0)
    if proposal is None:
        return templates.TemplateResponse(request, "sync_waiting.html", {"session_id": session_id})

    return templates.TemplateResponse(
        request,
        "sync_step.html",
        {
            "session_id": session_id,
            "proposal": proposal,
            "proposal_dict": proposal_to_dict(proposal),
        },
    )


@router.post("/sync/{session_id}/answer")
def sync_answer(request: Request, session_id: str, accept: str = Form(...)):
    registry: SessionStore = request.app.state.sessions
    session = registry.get_rename_session(session_id)
    if session is None:
        raise HTTPException(404, "unknown sync session")

    if session.bridge.poll_question(timeout=5.0) is None:
        raise HTTPException(409, "no pending proposal to answer")

    session.bridge.submit_answer(accept == "yes")
    return RedirectResponse(f"/sync/{session_id}/step", status_code=303)
