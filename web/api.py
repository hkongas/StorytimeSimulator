import os
import asyncio
import json
import logging
from uuid import uuid4
from urllib.parse import urlsplit
from pathlib import Path
from typing import Dict, Any, List, Literal, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from dotenv import set_key
from pydantic import BaseModel, Field

from config import settings
from core.types import StoryInitRequest, QuickStoryRequest, AdvanceStoryRequest, StoryMeta, TurnResponse
from core.llm_client import LLMClient
from core.prompt_loader import prompt_loader
from core.profile_store import KEY_FIELDS, load_profiles, save_profile_keys
from engine.story_engine import StoryEngine
import database.db as db
from database import turn_store

logger = logging.getLogger("uvicorn.error.tarinamoottori.api")

app = FastAPI(title="Tarinamoottori API", version="2.0.0")

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "test", "testserver"])

engine = StoryEngine()
jobs: dict[tuple[str, str], dict] = {}
background_tasks: set[asyncio.Task] = set()


def publish_progress(job: dict, event: dict):
    job.setdefault("progress", []).append(event)
    job["progress"] = job["progress"][-100:]
    job.setdefault("changed", asyncio.Event()).set()


def story_busy(story_id: str | None = None) -> bool:
    return engine.is_busy(story_id) or any(job["status"] == "running" and (story_id is None or key[0] == story_id) for key, job in jobs.items())


@app.middleware("http")
async def local_request_boundary(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and (urlsplit(origin).scheme not in {"http", "https"} or urlsplit(origin).netloc != request.headers.get("host")):
        return JSONResponse({"detail": "Ulkopuolinen alkuperä ei ole sallittu."}, status_code=403)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        parts = request.url.path.strip("/").split("/")
        if parts[:2] == ["api", "stories"] and len(parts) >= 3:
            if "turn-jobs" not in parts and "advance" not in parts and story_busy(parts[2]):
                return JSONResponse({"detail": "Odota vuoron valmistumista ennen tarinan muokkausta."}, status_code=409)
        elif story_busy() and parts[:2] in (["api", "settings"], ["api", "prompts"], ["api", "tone-profiles"]):
            return JSONResponse({"detail": "Odota generoinnin valmistumista ennen asetusten muokkausta."}, status_code=409)
    return await call_next(request)


@app.exception_handler(ValueError)
async def invalid_request(request: Request, error: ValueError):
    return JSONResponse({"detail": str(error)}, status_code=400)


@app.exception_handler(turn_store.TurnConflictError)
async def turn_conflict(request: Request, error: turn_store.TurnConflictError):
    return JSONResponse({"detail": str(error)}, status_code=409)


async def run_turn_job(story_id: str, req: AdvanceStoryRequest, job: dict):
    try:
        async for event in engine.advance_turn_streaming(
            story_id, req.user_input, req.mode, req.custom_guidance,
            req.private_intention, req.request_id, req.extra_reaction_cycle,
            plot_guidance=req.plot_guidance, decision_budget=req.decision_budget,
            expected_revision=req.expected_revision
        ):
            if event["type"] == "phase":
                job["message"] = event["message"]
                publish_progress(job, event)
            elif event["type"] == "turn_complete":
                job.update(status="completed", data=event["data"])
    except asyncio.CancelledError:
        receipt = await turn_store.get_receipt(story_id, req.request_id)
        if receipt:
            job.update(status="completed", data=receipt.model_dump())
        else:
            job.update(status="cancelled", message="Generointi keskeytettiin. Tarinaa ei muutettu.")
    except Exception as error:
        logger.exception("Vuorotyö epäonnistui")
        job.update(status="failed", message=str(error))
    finally:
        job.setdefault("changed", asyncio.Event()).set()


@app.post("/api/stories/{story_id}/turn-jobs")
async def start_turn_job(story_id: str, req: AdvanceStoryRequest):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    req.request_id = req.request_id or uuid4().hex
    key = (story_id, req.request_id)
    payload = req.model_dump()
    if key in jobs:
        if jobs[key]["payload"] != payload:
            raise HTTPException(409, "Pyyntötunniste on jo käytössä eri sisällöllä.")
    else:
        if story_busy(story_id):
            raise HTTPException(409, "Tarinan vuoro on jo kesken.")
        if len(jobs) > 200:
            for old_key in list(jobs):
                if jobs[old_key]["status"] != "running":
                    del jobs[old_key]
        job = {"status": "running", "message": "Valmistellaan vuoroa...", "payload": payload}
        jobs[key] = job
        task = asyncio.create_task(run_turn_job(story_id, req, job))
        job["task"] = task
        background_tasks.add(task)
        def finish_task(completed):
            background_tasks.discard(completed)
            if completed.cancelled() and job["status"] == "running":
                job.update(status="cancelled", message="Generointi keskeytettiin. Tarinaa ei muutettu.")
                job.setdefault("changed", asyncio.Event()).set()
        task.add_done_callback(finish_task)
    return {"request_id": req.request_id, "status": jobs[key]["status"]}


@app.get("/api/stories/{story_id}/turn-jobs/{request_id}")
async def get_turn_job(story_id: str, request_id: str):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    job = jobs.get((story_id, request_id))
    if job:
        if job["status"] == "completed":
            try:
                await turn_store.verify_committed_turn(story_id, TurnResponse.model_validate(job["data"]))
            except turn_store.TurnConflictError as error:
                return {"status": "failed", "message": str(error)}
        return {key: value for key, value in job.items() if key not in {"payload", "task", "changed"}}
    receipt = await turn_store.get_receipt(story_id, request_id)
    if receipt:
        await turn_store.verify_committed_turn(story_id, receipt)
        return {"status": "completed", "data": receipt.model_dump()}
    raise HTTPException(404, "Työtä ei löydy. Palvelin on voinut käynnistyä uudelleen.")


@app.get("/api/stories/{story_id}/turn-jobs/{request_id}/events")
async def stream_turn_events(story_id: str, request_id: str, request: Request):
    await get_turn_job(story_id, request_id)
    async def events():
        sent = 0
        while not await request.is_disconnected():
            job = jobs.get((story_id, request_id))
            changed = job.setdefault("changed", asyncio.Event()) if job else None
            if changed:
                changed.clear()
            if job:
                progress = job.get("progress", [])
                for event in progress[sent:]:
                    yield "event: progress\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                sent = len(progress)
            if not job or job["status"] != "running":
                try:
                    result = await get_turn_job(story_id, request_id)
                except (ValueError, HTTPException) as error:
                    result = {"status": "failed", "message": str(error)}
                yield "event: result\ndata: " + json.dumps(result, ensure_ascii=False) + "\n\n"
                return
            try:
                await asyncio.wait_for(changed.wait(), timeout=15)
            except asyncio.TimeoutError:
                yield 'event: heartbeat\ndata: {"status":"running"}\n\n'
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.delete("/api/stories/{story_id}/turn-jobs/{request_id}")
async def cancel_turn_job(story_id: str, request_id: str):
    job = jobs.get((story_id, request_id))
    if not job:
        if not await db.get_story_meta(story_id):
            raise HTTPException(404, "Tarinaa ei löydy.")
        receipt = await turn_store.get_receipt(story_id, request_id)
        jobs[(story_id, request_id)] = ({"status": "completed", "data": receipt.model_dump(), "payload": {}}
            if receipt else {"status": "cancelled", "message": "Generointi keskeytettiin. Tarinaa ei muutettu.", "payload": {}})
    if job and job["status"] == "running":
        job["task"].cancel()
    return {"status": "cancellation_requested"}

# --- Tarinaprojektien reitit ---

@app.get("/api/stories")
async def list_stories():
    """Listaa kaikki tallennetut tarinaprojektit."""
    stories = await db.list_all_stories()
    return {"stories": stories}

@app.post("/api/stories")
async def create_story(req: StoryInitRequest):
    """Luo uuden tarinaprojektin ja generoi aloituksen."""
    try:
        logger.info(f"Aloitetaan uuden tarinan luonti: '{req.title}', genre: '{req.genre}'...")
        result = await engine.initialize_new_story(req)
        logger.info(f"Uusi tarina luotu onnistuneesti: {result.get('story_id')}")
        return {"status": "success", "data": result}
    except Exception as e:
        logger.exception(f"Virhe uuden tarinan luonnissa: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stories/quick")
async def quick_create_story(req: QuickStoryRequest):
    try:
        logger.info("Pikaluonti alkaa: mode=%s", req.mode or "auto")
        result = await engine.quick_create_story(req)
    except Exception:
        logger.exception("Pikaluonti epäonnistui")
        raise
    return {"status": "success", "data": result}


@app.get("/api/stories/{story_id}")
async def get_story_details(story_id: str):
    """Hakee tarinan koko tilan: metatiedot, hahmot, aktiivisen kohtauksen ja kaikki vuorot."""
    meta = await db.get_story_meta(story_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Tarinaa ei löydy.")

    revision = await turn_store.get_revision(story_id)
    characters = await db.get_all_characters(story_id)
    active_scene = await db.get_active_scene(story_id)
    turns = await db.get_all_story_turns(story_id)
    chronicle = await db.get_chronicle(story_id)

    txt_path = db.get_story_dir(story_id) / "story.txt"
    full_text = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""
    runtime = await turn_store.get_runtime(story_id)
    can_undo = await turn_store.can_rollback(story_id)
    reading_metadata = await turn_store.get_reading_metadata(story_id)
    bible = {**await db.get_story_bible(story_id), **await db.get_planning_world(story_id)}
    character_catchups = await turn_store.get_character_catchups(story_id)
    if revision != await turn_store.get_revision(story_id):
        raise turn_store.TurnConflictError("Tarina muuttui latauksen aikana. Lataa se uudelleen.")

    return {
        "meta": meta,
        "characters": characters,
        "last_intentions": {character.id: await turn_store.get_last_intention(story_id, character.id) for character in characters},
        "active_scene": active_scene,
        "turns": turns,
        "reading_metadata": reading_metadata,
        "character_catchups": character_catchups,
        "chronicle": chronicle,
        "runtime": runtime,
        "bible": bible,
        "revision": revision,
        "can_undo": can_undo,
        "full_text": full_text
    }

class SimulationRevisionRequest(BaseModel):
    expected_revision: int = Field(ge=0)


class PlotGuidanceRequest(SimulationRevisionRequest):
    preset: Literal["adaptive", "balanced", "strong"]


class NullLocationRequest(SimulationRevisionRequest):
    selections: Dict[str, str] = Field(min_length=1, max_length=200)


class PlayerContinuationRequest(SimulationRevisionRequest):
    action: Literal["end", "choose_character", "branch"]
    character_id: Optional[str] = Field(default=None, min_length=1, max_length=200)
    snapshot_id: Optional[str] = Field(default=None, min_length=1, max_length=200)


class SimulationCharacterOption(BaseModel):
    id: str
    name: str


class SimulationSnapshotOption(BaseModel):
    id: str
    label: str


class SimulationMutationResponse(BaseModel):
    story_id: str
    revision: int


class NullLocationCandidate(BaseModel):
    character_id: str
    name: str
    suggested_location_id: Optional[str] = None
    ambiguous: bool
    locations: List[SimulationCharacterOption]


class NullLocationPreviewResponse(BaseModel):
    revision: int
    candidates: List[NullLocationCandidate]


class SimulationControlsResponse(BaseModel):
    revision: int
    plot_guidance: Literal["adaptive", "balanced", "strong"]
    player_failed: bool
    ended: bool
    eligible_characters: List[SimulationCharacterOption]
    snapshots: List[SimulationSnapshotOption]
    known_character_ids: List[str] = Field(default_factory=list)


async def require_simulation_story(story_id: str):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")


async def simulation_controls(story_id: str):
    revision = await turn_store.get_revision(story_id)
    runtime = await turn_store.get_runtime(story_id)
    options = await turn_store.get_failure_options(story_id)
    characters = await db.get_all_characters(story_id)
    scene = await db.get_active_scene(story_id)
    eligible_ids = set(options["switch_character_ids"])
    eligible = [{"id": character.id, "name": character.name} for character in characters
                if scene and character.id in eligible_ids and character.status == "active"
                and character.location_id is not None and character.location_id == scene.location_id
                and character.id in scene.active_character_ids and character.visibility_state == "visible"]
    if revision != await turn_store.get_revision(story_id):
        raise turn_store.TurnConflictError("Tarina muuttui esikatselun aikana.")
    return {"revision": revision, "plot_guidance": runtime.get("plot_guidance", "balanced"),
            "player_failed": options["failed"], "ended": bool(runtime.get("ended")),
            "eligible_characters": eligible,
            "snapshots": [{"id": str(identifier), "label": f"Ennen vuoroa {identifier}"}
                          for identifier in options["retry_turn_ids"]],
            "known_character_ids": options.get("known_character_ids", [])}


async def simulation_set_plot(story_id: str, preset: str, expected_revision: int):
    controls = await turn_store.get_simulation_controls(story_id)
    saved = await turn_store.set_simulation_controls(
        story_id, preset, expected_revision, decision_budget=controls["decision_budget"])
    return {"story_id": story_id, "revision": saved["revision"]}


async def simulation_preview_locations(story_id: str):
    preview = await db.preview_null_location_migration(story_id)
    locations = (await db.get_planning_world(story_id))["locations"]
    if preview["revision"] != await turn_store.get_revision(story_id):
        raise turn_store.TurnConflictError("Tarina muuttui sijaintien esikatselun aikana.")
    return {"revision": preview["revision"], "candidates": [
        {"character_id": character["id"], "name": character["name"],
         "suggested_location_id": character["suggested_location_id"],
         "ambiguous": character["requires_approval"], "locations": locations}
        for character in preview["characters"]]}


async def simulation_apply_locations(story_id: str, selections: Dict[str, str], expected_revision: int):
    await db.apply_null_location_migration(story_id, selections, expected_revision)
    return {"story_id": story_id, "revision": await turn_store.get_revision(story_id)}


async def simulation_continue(story_id: str, action: str, expected_revision: int,
                              character_id: Optional[str] = None, snapshot_id: Optional[str] = None):
    if action == "branch":
        result = await turn_store.create_retry_branch(story_id, int(snapshot_id), expected_revision)
        target_id = result["story_id"]
    else:
        await turn_store.continue_after_failure(story_id, "switch" if action == "choose_character" else "end",
                                               expected_revision, character_id)
        target_id = story_id
    return {"story_id": target_id, "revision": await turn_store.get_revision(target_id)}


@app.get("/api/stories/{story_id}/simulation/controls", response_model=SimulationControlsResponse)
async def get_simulation_controls(story_id: str):
    await require_simulation_story(story_id)
    return await simulation_controls(story_id)


@app.put("/api/stories/{story_id}/simulation/plot-guidance", response_model=SimulationMutationResponse)
@app.post("/api/stories/{story_id}/simulation/plot-guidance", response_model=SimulationMutationResponse)
async def set_plot_guidance(story_id: str, req: PlotGuidanceRequest):
    await require_simulation_story(story_id)
    return await simulation_set_plot(story_id, req.preset, req.expected_revision)


@app.get("/api/stories/{story_id}/simulation/null-locations", response_model=NullLocationPreviewResponse)
async def preview_null_locations(story_id: str):
    await require_simulation_story(story_id)
    return await simulation_preview_locations(story_id)


@app.post("/api/stories/{story_id}/simulation/null-locations", response_model=SimulationMutationResponse)
async def apply_null_locations(story_id: str, req: NullLocationRequest):
    await require_simulation_story(story_id)
    return await simulation_apply_locations(story_id, req.selections, req.expected_revision)


@app.post("/api/stories/{story_id}/simulation/continuation", response_model=SimulationMutationResponse)
async def continue_failed_player(story_id: str, req: PlayerContinuationRequest):
    await require_simulation_story(story_id)
    if (req.action == "choose_character") != (req.character_id is not None):
        raise HTTPException(422, "Hahmo valitaan vain hahmonvaihdossa.")
    if (req.action == "branch") != (req.snapshot_id is not None):
        raise HTTPException(422, "Tilannekuva valitaan vain uudessa haarassa.")
    controls = await simulation_controls(story_id)
    if req.expected_revision != controls["revision"]:
        raise turn_store.TurnConflictError("Jatkon esikatselu on vanhentunut.")
    if req.action != "branch" and (not controls["player_failed"] or controls["ended"]):
        raise HTTPException(409, "Pelaajahahmon jatkovalinta ei ole käytettävissä.")
    if req.action == "choose_character" and req.character_id not in {char["id"] for char in controls["eligible_characters"]}:
        raise HTTPException(400, "Hahmo ei ole kelvollinen pelaajahahmo.")
    if req.action == "branch" and req.snapshot_id not in {snapshot["id"] for snapshot in controls["snapshots"]}:
        raise HTTPException(400, "Tilannekuvaa ei ole käytettävissä.")
    return await simulation_continue(
        story_id, req.action, req.expected_revision,
        character_id=req.character_id, snapshot_id=req.snapshot_id)


class BibleTruth(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    fact: str = Field(min_length=1, max_length=2000)
    discoverable_via: str = Field(default="", max_length=1000)
    reveal_state: Literal["hidden", "hinted", "revealed"] = "hidden"
    related_location_id: Optional[str] = Field(default=None, max_length=200)

class BibleClock(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    remaining_beats: int = Field(ge=0, le=1000)
    on_expire_effect: str = Field(default="", max_length=1000)
    visible: bool = False

class BibleOffscreenAgent(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=1000)
    progress: str = Field(default="", max_length=1000)
    location: str = Field(default="", max_length=200)
    next_move: str = Field(default="", max_length=1000)
    visible_to: List[str] = Field(default_factory=list)

class BibleUpdateRequest(BaseModel):
    secret_truths: List[BibleTruth] = Field(default_factory=list)
    clocks: List[BibleClock] = Field(default_factory=list)
    offscreen_agents: List[BibleOffscreenAgent] = Field(default_factory=list)
    expected_revision: Optional[int] = Field(default=None, ge=0)

@app.put("/api/stories/{story_id}/bible")
async def update_story_bible(story_id: str, req: BibleUpdateRequest):
    """Tallentaa kertojan salaiset totuudet, kellot ja kuvaruudun ulkopuoliset toimijat."""
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    for label, items in (("salaisuuksien", req.secret_truths), ("kellojen", req.clocks), ("sivuhenkilöiden", req.offscreen_agents)):
        if len({item.id for item in items}) != len(items):
            raise ValueError(f"{label} tunnisteiden on oltava yksilöllisiä.")
    known_ids = {character.id for character in await db.get_all_characters(story_id)}
    for agent in req.offscreen_agents:
        if not set(agent.visible_to) <= known_ids:
            raise ValueError("Sivuhenkilön näkyvyys viittaa tuntemattomaan hahmoon.")
    existing = {truth["id"]: truth for truth in (await db.get_story_bible(story_id))["secret_truths"]}
    turn_index = max((turn.turn_index for turn in await db.get_all_story_turns(story_id)), default=0)
    truths = []
    for truth in req.secret_truths:
        values = truth.model_dump()
        previous = existing.get(truth.id, {}).get("revealed_at_turn")
        values["revealed_at_turn"] = (previous if previous is not None else turn_index) if truth.reveal_state == "revealed" else None
        truths.append(values)
    await db.save_story_bible(
        story_id, truths, [clock.model_dump() for clock in req.clocks],
        [agent.model_dump() for agent in req.offscreen_agents], expected_revision=req.expected_revision
    )
    bible = {**await db.get_story_bible(story_id), **await db.get_planning_world(story_id)}
    return {"status": "success", "bible": bible, "revision": await turn_store.get_revision(story_id)}

class TurnProseUpdate(BaseModel):
    prose: str = Field(min_length=1, max_length=200000)
    expected_revision: int = Field(ge=0)
    sync_state: bool = False


class TurnUndoRequest(BaseModel):
    expected_revision: int = Field(ge=0)


class AuthoredPreviewRequest(BaseModel):
    prose: str = Field(min_length=1, max_length=20000)
    expected_revision: int = Field(ge=0)


class AuthoredAcceptRequest(BaseModel):
    preview_id: str = Field(pattern=r"^[a-f0-9]{32}$")


@app.post("/api/stories/{story_id}/authored-turns/preview")
async def preview_authored_turn(story_id: str, req: AuthoredPreviewRequest):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    return await engine.preview_authored_turn(story_id, req.prose, req.expected_revision)


@app.post("/api/stories/{story_id}/authored-turns/accept")
async def accept_authored_turn(story_id: str, req: AuthoredAcceptRequest):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    response = await engine.accept_authored_turn(story_id, req.preview_id)
    return {"status": "success", "data": response.model_dump()}


@app.delete("/api/stories/{story_id}/authored-turns/previews/{preview_id}")
async def discard_authored_preview(story_id: str, preview_id: str):
    preview = engine.authored_previews.get(preview_id)
    if preview and preview["story_id"] == story_id:
        engine.authored_previews.pop(preview_id, None)
    return {"status": "success"}


@app.put("/api/stories/{story_id}/turns/{turn_id}")
async def edit_turn(story_id: str, turn_id: int, req: TurnProseUpdate):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    if req.sync_state:
        raise HTTPException(422, "Automaattista tilasynkronointia ei ole vielä toteutettu. Tekstiä ei tallennettu.")
    await turn_store.update_turn_prose(story_id, turn_id, req.prose, req.expected_revision)
    return {"status": "success", "revision": await turn_store.get_revision(story_id)}


class CharacterCatchupRequest(BaseModel):
    expected_revision: int


@app.post("/api/stories/{story_id}/characters/{character_id}/catchup")
async def character_catchup(story_id: str, character_id: str, req: CharacterCatchupRequest):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    if engine.is_busy(story_id):
        raise HTTPException(409, "Tarinaa käsitellään. Odota työn valmistumista.")
    try:
        return await engine.create_character_catchup(story_id, character_id, req.expected_revision)
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.post("/api/stories/{story_id}/turns/{turn_id}/player-view/retry")
async def retry_player_view(story_id: str, turn_id: int, character_id: str):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    try:
        return await engine.retry_player_view(story_id, turn_id, character_id)
    except ValueError as error:
        raise HTTPException(409, str(error))


@app.post("/api/stories/{story_id}/turns/undo")
async def undo_turn(story_id: str, req: TurnUndoRequest):
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    await turn_store.rollback_last_turn(story_id, req.expected_revision)
    for key in list(jobs):
        if key[0] == story_id and jobs[key]["status"] != "running":
            del jobs[key]
    return {"status": "success", "revision": await turn_store.get_revision(story_id)}


@app.delete("/api/stories/{story_id}")
async def delete_story_endpoint(story_id: str):
    """Poistaa tarinaprojektin ja sen tiedostot."""
    logger.info(f"Poistetaan tarina: '{story_id}'...")
    success = await db.delete_story(story_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tarinaa ei löydy.")
    return {"status": "success", "message": f"Tarina '{story_id}' poistettu."}

class StoryMetaUpdate(BaseModel):
    title: Optional[str] = None
    genre: Optional[str] = None
    world_lore: Optional[str] = None
    director_plot_arc: Optional[str] = None
    director_notes: Optional[str] = None
    tone_profile: Optional[str] = None
    custom_tone_override: Optional[str] = None
    theme_color: Optional[str] = None

@app.post("/api/stories/{story_id}/meta")
async def update_story_meta(story_id: str, req: StoryMetaUpdate):
    """Päivittää tarinan metatiedot ja sävyprofiilin."""
    meta = await db.get_story_meta(story_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Tarinaa ei löydy.")

    if req.title is not None:
        meta.title = req.title
    if req.genre is not None:
        meta.genre = req.genre
    if req.world_lore is not None:
        meta.world_lore = req.world_lore
    if req.director_plot_arc is not None:
        meta.director_plot_arc = req.director_plot_arc
    if req.director_notes is not None:
        meta.director_notes = req.director_notes
    if req.tone_profile is not None:
        meta.tone_profile = req.tone_profile
    if req.custom_tone_override is not None:
        meta.custom_tone_override = req.custom_tone_override
    if req.theme_color is not None:
        meta.theme_color = req.theme_color

    runtime_updates = {target: getattr(req, source) for source, target in (
        ("world_lore", "world_description"), ("director_plot_arc", "director_plan"), ("director_notes", "director_notes"))
        if getattr(req, source) is not None}
    await db.save_story_meta(story_id, meta, runtime_updates=runtime_updates)
    return {"status": "success", "meta": meta}

class CharacterUpdateRequest(BaseModel):
    visibility_state: Optional[Literal["hidden", "visible"]] = None
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    appearance: Optional[str] = None
    personality: Optional[str] = None
    physical_state: Optional[str] = None
    mental_state: Optional[str] = None
    secret_motive: Optional[str] = None
    public_bio: Optional[str] = None
    status: Optional[str] = None
    tier: Optional[str] = None

@app.post("/api/stories/{story_id}/characters/{char_id}/update")
async def update_character(story_id: str, char_id: str, req: CharacterUpdateRequest):
    """Päivittää hahmon tietoja lennosta."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    char = await db.update_character_details(story_id, char_id, updates)
    if not char:
        raise HTTPException(status_code=404, detail="Hahmoa ei löydy.")
    all_chars = await db.get_all_characters(story_id)
    return {"status": "success", "character": char, "all_characters": all_chars}

@app.post("/api/stories/{story_id}/characters/{char_id}/set_player")
async def set_player_character_endpoint(story_id: str, char_id: str):
    """Asettaa valitun hahmon pelaajan ohjaamaksi."""
    await require_simulation_story(story_id)
    controls = await simulation_controls(story_id)
    if controls["ended"] or char_id not in {char["id"] for char in controls["eligible_characters"]}:
        raise HTTPException(400, "Hahmo ei ole kelvollinen pelaajahahmo.")
    char = await db.set_player_character(story_id, char_id)
    if not char:
        raise HTTPException(status_code=404, detail="Hahmoa ei löydy.")
    all_chars = await db.get_all_characters(story_id)
    return {"status": "success", "character": char, "all_characters": all_chars}

@app.get("/api/stories/{story_id}/characters")
async def get_characters(story_id: str):
    """Hakee hahmot ja niiden tuoreimmat yksityiset muistit."""
    characters = await db.get_all_characters(story_id)
    result = []
    for c in characters:
        memories = await db.get_character_memories(story_id, c.id, limit=20)
        result.append({
            "character": c,
            "memories": memories
        })
    return {"characters": result}

@app.get("/api/stories/{story_id}/characters/{char_id}/export")
async def export_character(
    story_id: str,
    char_id: str,
    include_state: bool = True,
    include_memories: bool = True
):
    """Vie hahmon siirrettäväksi Storytime Character Card JSON -muotoon."""
    char = await db.get_character(story_id, char_id)
    if not char:
        raise HTTPException(status_code=404, detail="Hahmoa ei löydy.")

    memories = []
    if include_memories:
        raw_mems = await db.get_character_memories(story_id, char_id, limit=50)
        memories = [
            {
                "memory_type": m.memory_type,
                "content": m.content,
                "importance_score": m.importance_score
            }
            for m in raw_mems
        ]

    export_card = {
        "version": "2.0",
        "format": "storytime_character",
        "exported_from_story": story_id,
        "character": {
            "id": char.id,
            "name": char.name,
            "age": char.age,
            "gender": char.gender,
            "appearance": char.appearance,
            "personality": char.personality,
            "public_bio": char.public_bio,
            "tier": char.tier,
            "is_player_controlled": char.is_player_controlled
        }
    }

    if include_state:
        export_card["state"] = {
            "physical_state": char.physical_state,
            "mental_state": char.mental_state,
            "secret_motive": char.secret_motive,
            "status": char.status
        }

    if include_memories:
        export_card["memories"] = memories

    return JSONResponse(
        content=export_card,
        headers={"Content-Disposition": f'attachment; filename="character_{char.id}.json"'}
    )

class CharacterImportRequest(BaseModel):
    payload: Dict[str, Any]
    include_state: bool = True
    include_memories: bool = True
    as_player: Optional[bool] = None

@app.post("/api/stories/{story_id}/characters/import")
async def import_character(story_id: str, req: CharacterImportRequest):
    """Tuo hahmokortin valittuun tarinaan valituilla lisämääreillä."""
    meta = await db.get_story_meta(story_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Tarinaa ei löydy.")

    try:
        char = await db.import_character_to_story(
            story_id=story_id,
            payload=req.payload,
            include_state=req.include_state,
            include_memories=req.include_memories,
            as_player=req.as_player
        )
        all_chars = await db.get_all_characters(story_id)
        return {"status": "success", "character": char, "all_characters": all_chars}
    except turn_store.TurnConflictError:
        raise
    except ValueError as error:
        raise HTTPException(400, str(error))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hahmon tuonti epäonnistui: {str(e)}")

@app.post("/api/stories/{story_id}/advance")
async def advance_story(story_id: str, req: AdvanceStoryRequest):
    """Edistää tarinaa yhden vuoron verran (REST)."""
    meta = await db.get_story_meta(story_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Tarinaa ei löydy.")

    try:
        logger.info(f"Edistetään tarinaa '{story_id}' (mode={req.mode})...")
        turn_response = await engine.advance_turn(
            story_id=story_id,
            user_input=req.user_input,
            mode=req.mode,
            director_guidance=req.custom_guidance or (req.user_input if req.mode == "director" else None),
            private_intention=req.private_intention,
            request_id=req.request_id,
            extra_reaction_cycle=req.extra_reaction_cycle,
            plot_guidance=req.plot_guidance,
            decision_budget=req.decision_budget,
            expected_revision=req.expected_revision
        )
        logger.info(f"Tarinaa '{story_id}' edistetty: vuoro {turn_response.turn_index}")
        return {"status": "success", "data": turn_response}
    except turn_store.TurnConflictError:
        raise
    except ValueError as error:
        raise HTTPException(400, str(error))
    except Exception as e:
        logger.exception(f"Virhe tarinan '{story_id}' vuoron edistämisessä: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- WebSocket Reaaliaikaiseen Striimaukseen ---

@app.websocket("/ws/stories/{story_id}/live")
async def websocket_story_live(websocket: WebSocket, story_id: str):
    """WebSocket-päätepiste: striimaa agenttien työvaiheet ja proosan reaaliajassa."""
    origin = websocket.headers.get("origin")
    if origin and urlsplit(origin).netloc != websocket.headers.get("host"):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            raw_msg = await websocket.receive_text()
            data = AdvanceStoryRequest.model_validate_json(raw_msg).model_dump()
            
            user_input = data.get("user_input")
            mode = data.get("mode", "reader")
            custom_guidance = data.get("custom_guidance")

            async for event in engine.advance_turn_streaming(
                story_id=story_id,
                user_input=user_input,
                mode=mode,
                director_guidance=custom_guidance or (user_input if mode == "director" else None),
                private_intention=data.get("private_intention"),
                request_id=data.get("request_id"),
                extra_reaction_cycle=data["extra_reaction_cycle"]
            ):
                await websocket.send_json(event)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass

# --- System Promptien & Sävyprofiilien Hallinta ---

@app.get("/api/tone-profiles")
async def get_tone_profiles():
    """Listaa kaikki saatavilla olevat sävyprofiilit."""
    profiles = prompt_loader.list_tone_profiles()
    return {"profiles": profiles}

class ToneProfileSaveRequest(BaseModel):
    id: str
    title: str
    content: str

@app.post("/api/tone-profiles")
async def save_tone_profile(req: ToneProfileSaveRequest):
    """Luo tai tallentaa muokatun sävyprofiilin."""
    safe_id = "".join([c if c.isalnum() else "_" for c in req.id]).strip("_").lower()
    if not safe_id:
        raise HTTPException(status_code=400, detail="Virheellinen profiilitunniste.")
    
    prompt_loader.save_custom_prompt(f"tone_profiles/{safe_id}.txt", req.content)
    return {"status": "success", "id": safe_id}

@app.get("/api/prompts")
async def list_prompts():
    """Listaa muokattavat system promptit."""
    prompts = [
        {"id": "safety_directive", "title": "Turvallisuusdirektiivi (Safety)", "path": "safety_directive.txt"},
        {"id": "language_directive", "title": "Kielidirektiivi (Language)", "path": "language_directive.txt"},
        {"id": "director_initialize", "title": "Ohjaaja: Tarinan alustus", "path": "director/initialize_story.txt"},
        {"id": "director_perceptual", "title": "Ohjaaja: Aistisuodatin", "path": "director/perceptual_filter.txt"},
        {"id": "director_prose", "title": "Ohjaaja: Proosasynteesi / Kertoja", "path": "director/synthesize_prose.txt"},
        {"id": "director_watchdog", "title": "Ohjaaja: Valvoja (Watchdog)", "path": "director/watchdog_reflection.txt"},
        {"id": "character_action", "title": "Hahmoagentti: Päätöksenteko", "path": "character/decide_action.txt"},
        {"id": "chronicle_summarize", "title": "Kronikoitsija: Tapahtumatiivistys", "path": "chronicle/summarize.txt"},
    ]
    return {"prompts": prompts}

@app.get("/api/prompts/content")
async def get_prompt_content(path: str = Query(..., description="Promptin suhteellinen polku")):
    """Hakee tietyn promptin nykyisen sisällön."""
    content = prompt_loader.get_raw_prompt(path)
    return {"path": path, "content": content}

class PromptSaveRequest(BaseModel):
    path: str
    content: str

@app.post("/api/prompts/save")
async def save_prompt(req: PromptSaveRequest):
    """Tallentaa käyttäjän muokkaaman promptin."""
    prompt_loader.save_custom_prompt(req.path, req.content)
    return {"status": "success", "message": "Prompti tallennettu."}

class PromptResetRequest(BaseModel):
    path: str

@app.post("/api/prompts/reset")
async def reset_prompt(req: PromptResetRequest):
    """Palauttaa muokatun promptin järjestelmän oletukseen."""
    success = prompt_loader.reset_custom_prompt(req.path)
    return {"status": "success", "reset": success}

# --- Vienti ja Tiedostot ---

@app.get("/api/stories/{story_id}/export/txt")
async def export_txt(story_id: str):
    """Lataa story.txt tiedoston."""
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    await turn_store.rebuild_exports(story_id)
    txt_path = db.get_story_dir(story_id) / "story.txt"
    if not txt_path.exists():
        raise HTTPException(status_code=404, detail="Tiedostoa ei löydy.")
    return FileResponse(
        txt_path,
        media_type="text/plain; charset=utf-8",
        filename=f"{story_id}.txt"
    )

@app.get("/api/stories/{story_id}/export/md")
async def export_md(story_id: str):
    """Lataa story.md tiedoston."""
    if not await db.get_story_meta(story_id):
        raise HTTPException(404, "Tarinaa ei löydy.")
    await turn_store.rebuild_exports(story_id)
    md_path = db.get_story_dir(story_id) / "story.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Tiedostoa ei löydy.")
    return FileResponse(
        md_path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{story_id}.md"
    )

# --- Asetukset ja LLM-hallinta ---

class SettingsUpdate(BaseModel):
    profile_id: Optional[str] = None
    llm_provider: Optional[str] = None
    xai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_api_version: Optional[str] = None
    azure_deployment_name: Optional[str] = None
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    
    director_model: Optional[str] = None
    director_max_tokens: Optional[int] = None
    director_temperature: Optional[float] = None
    director_reasoning_effort: Optional[str] = None
    
    character_model: Optional[str] = None
    character_max_tokens: Optional[int] = None
    character_temperature: Optional[float] = None
    character_reasoning_effort: Optional[str] = None

    situation_model: Optional[str] = None
    situation_max_tokens: Optional[int] = None
    situation_temperature: Optional[float] = None
    situation_reasoning_effort: Optional[str] = None
    situation_decision_limit: Optional[int] = None
    situation_call_limit: Optional[int] = None
    situation_character_limit: Optional[int] = None
    situation_time_limit_seconds: Optional[float] = None
    situation_token_limit: Optional[int] = None

@app.get("/api/settings")
async def get_settings():
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "has_xai_key": bool(settings.XAI_API_KEY),
        "has_azure_key": bool(settings.AZURE_OPENAI_API_KEY),
        "azure_openai_endpoint": settings.AZURE_OPENAI_ENDPOINT,
        "azure_openai_api_version": settings.AZURE_OPENAI_API_VERSION,
        "azure_deployment_name": settings.AZURE_DEPLOYMENT_NAME,
        "has_openai_key": bool(settings.OPENAI_API_KEY),
        "has_openrouter_key": bool(settings.OPENROUTER_API_KEY),
        "has_gemini_key": bool(settings.GEMINI_API_KEY),
        
        "director_model": settings.DIRECTOR_MODEL,
        "director_max_tokens": settings.DIRECTOR_MAX_TOKENS,
        "director_temperature": settings.DIRECTOR_TEMPERATURE,
        "director_reasoning_effort": settings.DIRECTOR_REASONING_EFFORT,
        
        "character_model": settings.CHARACTER_MODEL,
        "character_max_tokens": settings.CHARACTER_MAX_TOKENS,
        "character_temperature": settings.CHARACTER_TEMPERATURE,
        "character_reasoning_effort": settings.CHARACTER_REASONING_EFFORT,

        "situation_model": settings.SITUATION_MODEL or settings.CHARACTER_MODEL,
        "situation_max_tokens": settings.SITUATION_MAX_TOKENS,
        "situation_temperature": settings.SITUATION_TEMPERATURE,
        "situation_reasoning_effort": settings.SITUATION_REASONING_EFFORT,
        "situation_decision_limit": settings.SITUATION_DECISION_LIMIT,
        "situation_call_limit": settings.SITUATION_CALL_LIMIT,
        "situation_character_limit": settings.SITUATION_CHARACTER_LIMIT,
        "situation_time_limit_seconds": settings.SITUATION_TIME_LIMIT_SECONDS,
        "situation_token_limit": settings.SITUATION_TOKEN_LIMIT
    }

class ProfileKeyTransfer(BaseModel):
    profiles: List[Dict[str, Any]]


@app.post("/api/settings/profile-secrets")
async def migrate_profile_keys(req: ProfileKeyTransfer):
    save_profile_keys(req.profiles)
    return {"status": "success"}


@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    if req.profile_id:
        save_profile_keys([{"id": req.profile_id, **req.model_dump(exclude_none=True)}])
        for name, value in load_profiles().get(req.profile_id, {}).items():
            if name in KEY_FIELDS and not getattr(req, name):
                setattr(req, name, value)
    if req.llm_provider:
        settings.LLM_PROVIDER = req.llm_provider
    if req.xai_api_key:
        settings.XAI_API_KEY = req.xai_api_key
    if req.azure_openai_endpoint is not None:
        settings.AZURE_OPENAI_ENDPOINT = req.azure_openai_endpoint
    if req.azure_openai_api_key:
        settings.AZURE_OPENAI_API_KEY = req.azure_openai_api_key
    if req.azure_openai_api_version is not None:
        settings.AZURE_OPENAI_API_VERSION = req.azure_openai_api_version
    if req.azure_deployment_name is not None:
        settings.AZURE_DEPLOYMENT_NAME = req.azure_deployment_name
    if req.openai_api_key:
        settings.OPENAI_API_KEY = req.openai_api_key
    if req.openrouter_api_key:
        settings.OPENROUTER_API_KEY = req.openrouter_api_key
    if req.gemini_api_key:
        settings.GEMINI_API_KEY = req.gemini_api_key
        
    if req.director_model:
        settings.DIRECTOR_MODEL = req.director_model
    if req.director_max_tokens is not None:
        settings.DIRECTOR_MAX_TOKENS = req.director_max_tokens
    if req.director_temperature is not None:
        settings.DIRECTOR_TEMPERATURE = req.director_temperature
    if req.director_reasoning_effort is not None:
        settings.DIRECTOR_REASONING_EFFORT = req.director_reasoning_effort

    if req.character_model:
        settings.CHARACTER_MODEL = req.character_model
    if req.character_max_tokens is not None:
        settings.CHARACTER_MAX_TOKENS = req.character_max_tokens
    if req.character_temperature is not None:
        settings.CHARACTER_TEMPERATURE = req.character_temperature
    if req.character_reasoning_effort is not None:
        settings.CHARACTER_REASONING_EFFORT = req.character_reasoning_effort

    for name in (
        "situation_model", "situation_max_tokens", "situation_temperature",
        "situation_reasoning_effort", "situation_decision_limit", "situation_call_limit",
        "situation_character_limit", "situation_time_limit_seconds", "situation_token_limit"
    ):
        value = getattr(req, name)
        if value is not None:
            setattr(settings, name.upper(), value)

    # Uudelleenalustetaan enginen LLM-asiakas
    for name, value in req.model_dump(exclude_none=True).items():
        if name == "profile_id":
            continue
        if name.endswith("api_key") and not value:
            continue
        set_key(str(settings.BASE_DIR / ".env"), name.upper(), str(value))
    engine.llm = LLMClient()
    engine.director.llm = engine.llm
    engine.chronicle.llm = engine.llm

    return {"status": "success", "message": "Asetukset päivitetty."}

@app.get("/api/stories/{story_id}/logs")
async def get_story_logs(story_id: str, limit: int = 60):
    """Hakee tarinan rajapintalokit ja suoritustiedot."""
    logs = await db.get_api_calls_for_story(story_id, limit=limit)
    for log in logs:
        log.pop("prompt_payload", None)
        log.pop("response_payload", None)
    return {"status": "success", "logs": logs}

@app.get("/api/stories/{story_id}/logs/{call_id}")
async def get_story_log_content(story_id: str, call_id: int):
    content = await db.get_api_call_content(story_id, call_id)
    if content is None:
        raise HTTPException(status_code=404, detail="API-kutsua ei löydy.")
    return {"status": "success", **content}

@app.get("/api/stories/{story_id}/stats")
async def get_story_stats(story_id: str):
    """Hakee yhteenvedon tarinan API-käytöstä (tokenit, kesto, hinta)."""
    stats = await db.get_story_api_stats(story_id)
    return {"status": "success", "stats": stats}

# --- Staattiset tiedostot ja Web UI ---

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def serve_index():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return PlainTextResponse("Tarinamoottori Web UI käynnistyy...")
