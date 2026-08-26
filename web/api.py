import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from core.types import StoryInitRequest, AdvanceStoryRequest
from engine.story_engine import StoryEngine
import database.db as db

app = FastAPI(title="Tarinamoottori API", version="1.0.0")

# CORS tuki
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = StoryEngine()

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
        result = await engine.initialize_new_story(req)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stories/{story_id}")
async def get_story_details(story_id: str):
    """Hakee tarinan koko tilan: metatiedot, hahmot, aktiivisen kohtauksen ja kaikki vuorot."""
    meta = await db.get_story_meta(story_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Tarinaa ei löydy.")

    characters = await db.get_all_characters(story_id)
    active_scene = await db.get_active_scene(story_id)
    turns = await db.get_all_story_turns(story_id)
    chronicle = await db.get_chronicle(story_id)

    # Luetaan story.txt jos olemassa
    txt_path = settings.STORIES_DIR / story_id / "story.txt"
    full_text = txt_path.read_text(encoding="utf-8") if txt_path.exists() else ""

    return {
        "meta": meta,
        "characters": characters,
        "active_scene": active_scene,
        "turns": turns,
        "chronicle": chronicle,
        "full_text": full_text
    }

@app.get("/api/stories/{story_id}/characters")
async def get_characters(story_id: str):
    """Hakee hahmot ja niiden tuoreimmat yksityiset muistit."""
    characters = await db.get_all_characters(story_id)
    result = []
    for c in characters:
        memories = await db.get_character_memories(story_id, c.id, limit=15)
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
        "version": "1.0",
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
            "is_player_controlled": char.is_player_controlled
        }
    }

    if include_state:
        export_card["state"] = {
            "physical_state": char.physical_state,
            "mental_state": char.mental_state,
            "secret_motive": char.secret_motive
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hahmon tuonti epäonnistui: {str(e)}")

@app.post("/api/stories/{story_id}/advance")
async def advance_story(story_id: str, req: AdvanceStoryRequest):
    """Edistää tarinaa yhden vuoron verran."""
    meta = await db.get_story_meta(story_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Tarinaa ei löydy.")

    try:
        turn_response = await engine.advance_turn(
            story_id=story_id,
            user_input=req.user_input,
            mode=req.mode,
            director_guidance=req.user_input if req.mode == "director" else None
        )
        return {"status": "success", "data": turn_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Vienti ja Tiedostot ---

@app.get("/api/stories/{story_id}/export/txt")
async def export_txt(story_id: str):
    """Lataa story.txt tiedoston."""
    txt_path = settings.STORIES_DIR / story_id / "story.txt"
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
    md_path = settings.STORIES_DIR / story_id / "story.md"
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Tiedostoa ei löydy.")
    return FileResponse(
        md_path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{story_id}.md"
    )

# --- Asetukset ja LLM-hallinta ---

class SettingsUpdate(BaseModel):
    llm_provider: Optional[str] = None
    xai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_api_version: Optional[str] = None
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    
    director_model: Optional[str] = None
    director_max_tokens: Optional[int] = None
    director_temperature: Optional[float] = None
    director_reasoning_effort: Optional[str] = None
    
    character_model: Optional[str] = None
    character_max_tokens: Optional[int] = None
    character_temperature: Optional[float] = None
    character_reasoning_effort: Optional[str] = None

@app.get("/api/settings")
async def get_settings():
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "has_xai_key": bool(settings.XAI_API_KEY),
        "has_azure_key": bool(settings.AZURE_OPENAI_API_KEY),
        "azure_openai_endpoint": settings.AZURE_OPENAI_ENDPOINT,
        "azure_openai_api_version": settings.AZURE_OPENAI_API_VERSION,
        "has_openai_key": bool(settings.OPENAI_API_KEY),
        "has_openrouter_key": bool(settings.OPENROUTER_API_KEY),
        
        "director_model": settings.DIRECTOR_MODEL,
        "director_max_tokens": settings.DIRECTOR_MAX_TOKENS,
        "director_temperature": settings.DIRECTOR_TEMPERATURE,
        "director_reasoning_effort": settings.DIRECTOR_REASONING_EFFORT,
        
        "character_model": settings.CHARACTER_MODEL,
        "character_max_tokens": settings.CHARACTER_MAX_TOKENS,
        "character_temperature": settings.CHARACTER_TEMPERATURE,
        "character_reasoning_effort": settings.CHARACTER_REASONING_EFFORT
    }

@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    if req.llm_provider:
        settings.LLM_PROVIDER = req.llm_provider
    if req.xai_api_key is not None:
        settings.XAI_API_KEY = req.xai_api_key
    if req.azure_openai_endpoint is not None:
        settings.AZURE_OPENAI_ENDPOINT = req.azure_openai_endpoint
    if req.azure_openai_api_key is not None:
        settings.AZURE_OPENAI_API_KEY = req.azure_openai_api_key
    if req.azure_openai_api_version is not None:
        settings.AZURE_OPENAI_API_VERSION = req.azure_openai_api_version
    if req.openai_api_key is not None:
        settings.OPENAI_API_KEY = req.openai_api_key
    if req.openrouter_api_key is not None:
        settings.OPENROUTER_API_KEY = req.openrouter_api_key
        
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

    # Uudelleenalustetaan enginen LLM-asiakas
    engine.llm = engine.director.llm = engine.chronicle.llm = engine.director.llm.__class__()

    return {"status": "success", "message": "Asetukset päivitetty."}

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
