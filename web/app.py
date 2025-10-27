"""FastAPI application serving the DungeonGPT web experience."""
from __future__ import annotations

import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from web.story_engine import StoryEngine, get_engine


app = FastAPI(title="DungeonGPT Web")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")
_engine: StoryEngine = get_engine()


class StartPayload(BaseModel):
    name: str
    archetype: str
    trait: str


class ActionPayload(BaseModel):
    session_id: str
    action: str


class ResetPayload(BaseModel):
    session_id: str


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/start")
async def start_story(payload: StartPayload) -> dict:
    session_id = uuid.uuid4().hex
    state = _engine.create_story(session_id, payload.name, payload.archetype, payload.trait)
    return {"sessionId": session_id, "state": state.as_dict()}


@app.post("/api/step")
async def advance_story(payload: ActionPayload) -> dict:
    try:
        state = _engine.advance(payload.session_id, payload.action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"state": state.as_dict()}


@app.post("/api/reset")
async def reset_story(payload: ResetPayload) -> dict:
    _engine.reset(payload.session_id)
    return {"status": "ok"}
