"""
AI router (plan §3.2): provider config + SSE-streamed chat.

    GET    /api/ai/providers           → providers with configured flag + model catalogue
    PUT    /api/ai/providers/{id}       → set the API key (api-key providers; Copilot uses device flow)
    DELETE /api/ai/providers/{id}       → clear the stored key
    POST   /api/ai/chat                 → SSE stream: token* then done|error

Provider credentials are machine-global (encrypted file via Logic_AI_Credentials,
honoring ARCHVALIDATOR_CONFIG_DIR), independent of the open project. Chat
streams tokens by running the blocking provider call on a worker thread and
hopping each chunk onto the event loop (the same thread→loop bridge the global
SSE bus uses).
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from Application_Logic import Logic_AI_Providers as providers
from Application_Logic import Logic_AI_Credentials as creds

from ..deps import get_state
from ..security import require_token
from ..state import AppState, ProjectError

router = APIRouter(prefix="/api/ai", tags=["ai"],
                   dependencies=[Depends(require_token)])


def _guard(fn):
    try:
        return fn()
    except ProjectError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class SetKeyBody(BaseModel):
    api_key: str


def _provider_view(p) -> dict:
    return {
        "id": p.id,
        "label": p.label,
        "configured": p.is_configured(),
        "supports_tools": getattr(p, "SUPPORTS_TOOLS", False),
        "models": p.list_models(),
    }


@router.get("/providers")
def list_providers() -> dict:
    return {"providers": [_provider_view(p) for p in providers.list_providers()]}


@router.put("/providers/{provider_id}")
def set_provider_key(provider_id: str, body: SetKeyBody) -> dict:
    try:
        p = providers.get_provider(provider_id)
    except providers.AIError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")
    if provider_id == "copilot":
        raise HTTPException(status_code=400,
                            detail="Copilot uses the OAuth device flow, not an API key.")
    creds.set_key(provider_id, body.api_key)
    return _provider_view(p)


@router.delete("/providers/{provider_id}")
def clear_provider_key(provider_id: str) -> dict:
    try:
        p = providers.get_provider(provider_id)
    except providers.AIError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")
    creds.delete_key(provider_id)
    return _provider_view(p)


# ---------------------------------------------------------------------------
# Prompt / rules editing (AI Generation + AI Chat). These live in project_meta
# (de-roleplayed defaults via Logic_AI_Context) so they travel with the .arch.
# ---------------------------------------------------------------------------
class PromptsBody(BaseModel):
    rules: Optional[str] = None
    prompt: Optional[str] = None
    chat_rules: Optional[str] = None


@router.get("/prompts")
def get_prompts(state: AppState = Depends(get_state)) -> dict:
    def go():
        from Application_Logic import Logic_AI_Context as ctx
        db = state.require_open()
        return {
            "rules": ctx.get_rules(db),
            "prompt": ctx.get_prompt(db),
            "chat_rules": ctx.get_chat_rules(db),
        }
    return _guard(go)


@router.put("/prompts")
def set_prompts(body: PromptsBody, state: AppState = Depends(get_state)) -> dict:
    def go():
        from Application_Logic import Logic_AI_Context as ctx
        db = state.require_edit()
        if body.rules is not None:
            ctx.set_rules(db, body.rules)
        if body.prompt is not None:
            ctx.set_prompt(db, body.prompt)
        if body.chat_rules is not None:
            ctx.set_chat_rules(db, body.chat_rules)
        db.commit()
        return {
            "rules": ctx.get_rules(db),
            "prompt": ctx.get_prompt(db),
            "chat_rules": ctx.get_chat_rules(db),
        }
    return _guard(go)


# ---------------------------------------------------------------------------
# Mind-map status (AI Generation grounds + regenerates the model/release map).
# ---------------------------------------------------------------------------
@router.get("/mindmap")
def mindmap_status(model_id: Optional[int] = None, release_id: Optional[int] = None,
                   state: AppState = Depends(get_state)) -> dict:
    def go():
        db = state.require_open()
        mid = model_id
        if mid is None and state.arch_manager is not None:
            mid = state.arch_manager.active_model_id
        rid = release_id if release_id is not None else db.get_active_release_id()
        if mid is None:
            return {"model_id": None, "release_id": rid, "has_mindmap": False, "meta": None}
        meta = db.get_model_mindmap_meta(mid, release_id=rid)
        return {
            "model_id": mid,
            "release_id": rid,
            "has_mindmap": db.has_model_mindmap(mid, release_id=rid),
            "has_source": db.has_release_source(rid) if rid is not None else False,
            "meta": meta,
        }
    return _guard(go)


# ---------------------------------------------------------------------------
# HLT design-file parsing (AI Generation checklist)
# ---------------------------------------------------------------------------
class ParseHltBody(BaseModel):
    file_path: str


@router.post("/parse-hlt")
def parse_hlt(body: ParseHltBody) -> dict:
    """Parse one HLT ``*_Test_Case_Design.md`` into its title/model + test-case
    checklist so the frontend can show them for selection before generation."""
    import os
    from Application_Logic import Logic_AI_Context as ctx
    if not body.file_path or not os.path.isfile(body.file_path):
        raise HTTPException(status_code=404, detail=f"No such file: {body.file_path}")
    try:
        return ctx.parse_hlt_file(body.file_path)
    except Exception as e:  # noqa: BLE001 — surface parse failures as 400
        raise HTTPException(status_code=400, detail=f"Could not parse HLT file: {e}") from e


# ---------------------------------------------------------------------------
# Chat (SSE token stream)
# ---------------------------------------------------------------------------
class ChatBody(BaseModel):
    provider_id: str
    model: str
    messages: list[dict]
    system_prompt: Optional[str] = None
    # Optional grounding: inject the model/release mind map as standing context.
    model_id: Optional[int] = None
    release_id: Optional[int] = None
    ground_in_mindmap: bool = True


def _build_system_prompt(state: AppState, body: ChatBody) -> Optional[str]:
    """Chat rules + the compact mind map for the model/release (Phase 12 strategy)."""
    if not body.ground_in_mindmap:
        return body.system_prompt
    db = state.db
    if db is None or not db.is_open:
        return body.system_prompt
    from Application_Logic import Logic_AI_Context as ctx
    mid = body.model_id
    if mid is None and state.arch_manager is not None:
        mid = state.arch_manager.active_model_id
    rid = body.release_id if body.release_id is not None else db.get_active_release_id()
    mm = db.get_model_mindmap(mid, release_id=rid) if mid is not None else None
    base = body.system_prompt or ctx.get_chat_rules(db)
    if mm:
        return base + "\n\n# CODE MIND MAP\n" + ctx.mind_map_to_text(mm)
    return base


@router.post("/chat")
async def chat(body: ChatBody, request: Request,
               state: AppState = Depends(get_state)) -> Response:
    try:
        provider = providers.get_provider(body.provider_id)
    except providers.AIError:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {body.provider_id}")
    if not provider.is_configured():
        raise HTTPException(status_code=409,
                            detail=f"Provider '{body.provider_id}' is not configured.")

    system_prompt = _build_system_prompt(state, body)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    def push(item):
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def worker():
        try:
            text = providers.generate(
                body.provider_id, body.model, body.messages,
                system_prompt=system_prompt,
                stream_cb=lambda chunk: push(("token", chunk)),
            )
            push(("done", text))
        except Exception as e:  # noqa: BLE001 — surface to the stream as an error event
            push(("error", str(e)))
        finally:
            push(_DONE)

    threading.Thread(target=worker, name="ai-chat", daemon=True).start()

    async def generator():
        while True:
            if await request.is_disconnected():
                break
            item = await queue.get()
            if item is _DONE:
                break
            kind, payload = item
            yield {"event": kind, "data": json.dumps(payload)}

    return EventSourceResponse(generator())
