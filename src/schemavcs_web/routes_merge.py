"""Drives a real merge() one click at a time via WebConfirmBridge. GET
/next either returns the current pending conflict (poll again if none
arrived within the timeout) or the final MergeResult once the worker's
done; POST /answer builds a real HumanConfirmationToken from the human's
choice and unblocks the worker for one more step."""

from fastapi import APIRouter, Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from schemavcs.dag.persistence import load, save
from schemavcs.merge.classify import ClassifiedGroup
from schemavcs.merge.engine import merge
from schemavcs.merge.resolve import HumanConfirmationToken
from schemavcs.model_sync.sync import sync_model_file
from schemavcs.storage.paths import write_current_branch
from schemavcs_web.confirm_adapter import build_token_from_choice, classify_ui_mode
from schemavcs_web.routes_repo import _require_repo
from schemavcs_web.session import MergeSession, SessionStore

router = APIRouter()
templates: Jinja2Templates | None = None


@router.post("/merge/start")
def start_merge(
    request: Request,
    target_branch: str = Form(...),
    source_branch: str = Form(...),
    sc_session: str | None = Cookie(default=None),
):
    repo_session = _require_repo(request, sc_session)
    registry: SessionStore = request.app.state.sessions
    store = load(repo_session.repo_root)

    session = MergeSession(
        session_id=f"{repo_session.session_id}:{target_branch}:{source_branch}",
        repo_root=repo_session.repo_root,
        store=store,
        target_branch=target_branch,
        source_branch=source_branch,
    )
    bridge = session.bridge
    bridge.run_in_background(lambda: merge(store, target_branch, source_branch, confirm=bridge.ask))
    registry.register_merge_session(session)

    return {"session_id": session.session_id}


def _current_question(session: MergeSession) -> ClassifiedGroup | None:
    return session.bridge.poll_question(timeout=5.0)


@router.get("/merge/{session_id}/step", response_class=HTMLResponse)
def merge_step(request: Request, session_id: str):
    registry: SessionStore = request.app.state.sessions
    session = registry.get_merge_session(session_id)
    if session is None:
        raise HTTPException(404, "unknown merge session")

    if session.bridge.is_done():
        try:
            result = session.bridge.result()
        except Exception as exc:  # noqa: BLE001 -- surfaced to the page, not swallowed
            return templates.TemplateResponse(
                request, "merge_error.html", {"error": str(exc), "session_id": session_id}
            )
        # Persist the merge to disk and regenerate the target branch's
        # tracked .schema file -- every route loads a FRESH DagStore from
        # disk per request (load(repo_root)), so without this the merge's
        # result only ever lived in this one in-memory `store` object and
        # was silently lost the moment the next request reloaded from disk.
        # Mirrors merge_cmd.py's own save()+sync_model_file() call exactly.
        save(session.store, session.repo_root)
        sync_model_file(session.repo_root, session.store, session.target_branch)

        # Switch the repo's current branch to the merge target -- without
        # this, a user who was on the SOURCE branch when they started the
        # merge stays there after it completes, and going "back to repo"
        # shows the source branch's unrelated state, which looks exactly
        # like the merge did nothing even though the target branch (main,
        # here) really did get updated.
        write_current_branch(session.repo_root, session.target_branch)
        return templates.TemplateResponse(
            request,
            "merge_done.html",
            {"result": result, "session_id": session_id, "target_branch": session.target_branch},
        )

    question = _current_question(session)
    if question is None:
        return templates.TemplateResponse(request, "merge_waiting.html", {"session_id": session_id})

    ui_mode = classify_ui_mode(question)
    return templates.TemplateResponse(
        request,
        "merge_step.html",
        {"session_id": session_id, "group": question, "ui_mode": ui_mode},
    )


@router.post("/merge/{session_id}/answer")
def merge_answer(request: Request, session_id: str, choice: str = Form(...)):
    registry: SessionStore = request.app.state.sessions
    session = registry.get_merge_session(session_id)
    if session is None:
        raise HTTPException(404, "unknown merge session")

    question = _current_question(session)
    if question is None:
        raise HTTPException(409, "no pending question to answer")

    token: HumanConfirmationToken = build_token_from_choice(question, choice)
    session.bridge.submit_answer(token)

    return RedirectResponse(f"/merge/{session_id}/step", status_code=303)
