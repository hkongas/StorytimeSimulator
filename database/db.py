import json
import aiosqlite
from pathlib import Path
from typing import List, Optional, Dict, Any
from config import settings
from core.types import StoryMeta, Character, CharacterMemory, Scene, SceneTurn, ChronicleEntry

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def get_db_path(story_id: str) -> Path:
    """Palauttaa tietyn tarinaprojektin SQLite-tietokannan tiedostopolun."""
    story_dir = settings.STORIES_DIR / story_id
    story_dir.mkdir(parents=True, exist_ok=True)
    return story_dir / "story.db"

async def init_story_db(story_id: str):
    """Alustaa tarinaprojektin SQLite-tietokannan ja taulut."""
    db_path = get_db_path(story_id)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(schema_sql)
        await db.commit()

# --- Tarinan metatiedot ---

async def save_story_meta(story_id: str, meta: StoryMeta):
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO story_meta (id, title, genre, world_lore, director_plot_arc, director_notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (meta.id, meta.title, meta.genre, meta.world_lore, meta.director_plot_arc, meta.director_notes)
        )
        await db.commit()

async def get_story_meta(story_id: str) -> Optional[StoryMeta]:
    db_path = get_db_path(story_id)
    if not db_path.exists():
        return None
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM story_meta WHERE id = ?", (story_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return StoryMeta(
                    id=row["id"],
                    title=row["title"],
                    genre=row["genre"],
                    world_lore=row["world_lore"],
                    director_plot_arc=row["director_plot_arc"],
                    director_notes=row["director_notes"],
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"])
                )
    return None

async def list_all_stories() -> List[Dict[str, Any]]:
    """Listaa kaikki olemassa olevat tarinaprojektit."""
    stories = []
    if not settings.STORIES_DIR.exists():
        return stories

    for item in settings.STORIES_DIR.iterdir():
        if item.is_dir() and (item / "story.db").exists():
            meta = await get_story_meta(item.name)
            if meta:
                stories.append({
                    "id": meta.id,
                    "title": meta.title,
                    "genre": meta.genre,
                    "created_at": meta.created_at,
                    "updated_at": meta.updated_at
                })
            else:
                stories.append({
                    "id": item.name,
                    "title": item.name,
                    "genre": "Tuntematon",
                    "created_at": "",
                    "updated_at": ""
                })
    return sorted(stories, key=lambda x: x.get("updated_at") or "", reverse=True)

# --- Hahmot ja Muistit ---

async def save_character(story_id: str, char: Character):
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO characters 
            (id, name, age, gender, appearance, personality, is_player_controlled, physical_state, mental_state, secret_motive, public_bio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                char.id, char.name, char.age, char.gender, char.appearance, char.personality,
                1 if char.is_player_controlled else 0,
                char.physical_state, char.mental_state, char.secret_motive, char.public_bio
            )
        )
        await db.commit()

async def get_character(story_id: str, char_id: str) -> Optional[Character]:
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM characters WHERE id = ?", (char_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return Character(
                    id=row["id"],
                    name=row["name"],
                    age=row["age"],
                    gender=row["gender"],
                    appearance=row["appearance"],
                    personality=row["personality"],
                    is_player_controlled=bool(row["is_player_controlled"]),
                    physical_state=row["physical_state"],
                    mental_state=row["mental_state"],
                    secret_motive=row["secret_motive"],
                    public_bio=row["public_bio"],
                    created_at=str(row["created_at"])
                )
    return None

async def get_all_characters(story_id: str) -> List[Character]:
    db_path = get_db_path(story_id)
    characters = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM characters ORDER BY name ASC") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                characters.append(Character(
                    id=row["id"],
                    name=row["name"],
                    age=row["age"],
                    gender=row["gender"],
                    appearance=row["appearance"],
                    personality=row["personality"],
                    is_player_controlled=bool(row["is_player_controlled"]),
                    physical_state=row["physical_state"],
                    mental_state=row["mental_state"],
                    secret_motive=row["secret_motive"],
                    public_bio=row["public_bio"],
                    created_at=str(row["created_at"])
                ))
    return characters

async def update_character_state(story_id: str, char_id: str, physical_state: str, mental_state: str, secret_motive: Optional[str] = None):
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        if secret_motive is not None:
            await db.execute(
                "UPDATE characters SET physical_state = ?, mental_state = ?, secret_motive = ? WHERE id = ?",
                (physical_state, mental_state, secret_motive, char_id)
            )
        else:
            await db.execute(
                "UPDATE characters SET physical_state = ?, mental_state = ? WHERE id = ?",
                (physical_state, mental_state, char_id)
            )
        await db.commit()

async def add_character_memory(story_id: str, memory: CharacterMemory):
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO character_memories (character_id, scene_index, memory_type, content, importance_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (memory.character_id, memory.scene_index, memory.memory_type, memory.content, memory.importance_score)
        )
        await db.commit()

async def get_character_memories(story_id: str, char_id: str, limit: int = 20) -> List[CharacterMemory]:
    db_path = get_db_path(story_id)
    memories = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM character_memories WHERE character_id = ? ORDER BY id DESC LIMIT ?",
            (char_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            for row in reversed(rows):
                memories.append(CharacterMemory(
                    id=row["id"],
                    character_id=row["character_id"],
                    scene_index=row["scene_index"],
                    memory_type=row["memory_type"],
                    content=row["content"],
                    importance_score=row["importance_score"],
                    created_at=str(row["created_at"])
                ))
    return memories

async def update_scene_active_characters(story_id: str, scene_id: int, character_ids: List[str]):
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE scenes SET active_character_ids = ? WHERE id = ?",
            (json.dumps(character_ids), scene_id)
        )
        await db.commit()

async def import_character_to_story(
    story_id: str,
    payload: Dict[str, Any],
    include_state: bool = True,
    include_memories: bool = True,
    as_player: Optional[bool] = None
) -> Character:
    """Tuo hahmokortin annettuun tarinaan valituilla tiedoilla."""
    raw_char = payload.get("character", payload)
    raw_state = payload.get("state", {})
    raw_memories = payload.get("memories", [])

    # Määritetään ID ilman törmäystä
    base_id = raw_char.get("id") or raw_char.get("name", "char").lower().replace(" ", "_")
    base_id = "".join([c if c.isalnum() else "_" for c in base_id]).strip("_")[:30] or "imported_char"
    
    existing = await get_all_characters(story_id)
    existing_ids = {c.id for c in existing}
    
    final_id = base_id
    counter = 1
    while final_id in existing_ids:
        final_id = f"{base_id}_{counter}"
        counter += 1

    # Tilan määritys
    phys_state = "Terve ja hyväkuntoinen"
    ment_state = "Rauhallinen ja tarkkaavainen"
    sec_motive = ""

    if include_state:
        phys_state = raw_state.get("physical_state") or raw_char.get("physical_state", phys_state)
        ment_state = raw_state.get("mental_state") or raw_char.get("mental_state", ment_state)
        sec_motive = raw_state.get("secret_motive") or raw_char.get("secret_motive", sec_motive)

    is_player = raw_char.get("is_player_controlled", False) if as_player is None else as_player

    char = Character(
        id=final_id,
        name=raw_char.get("name", "Nimetön Hahmo"),
        age=raw_char.get("age", 25),
        gender=raw_char.get("gender"),
        appearance=raw_char.get("appearance", ""),
        personality=raw_char.get("personality", ""),
        is_player_controlled=is_player,
        physical_state=phys_state,
        mental_state=ment_state,
        secret_motive=sec_motive,
        public_bio=raw_char.get("public_bio", "")
    )

    # Tallennetaan hahmo
    await save_character(story_id, char)

    # Tallennetaan muistit jos valittu
    if include_memories and raw_memories:
        for m in raw_memories:
            content = m.get("content") if isinstance(m, dict) else str(m)
            m_type = m.get("memory_type", "observation") if isinstance(m, dict) else "observation"
            score = m.get("importance_score", 1.0) if isinstance(m, dict) else 1.0
            if content:
                mem_item = CharacterMemory(
                    character_id=final_id,
                    memory_type=m_type,
                    content=content,
                    importance_score=score
                )
                await add_character_memory(story_id, mem_item)

    # Lisätään hahmo aktiiviseen kohtaukseen
    active_scene = await get_active_scene(story_id)
    if active_scene:
        if final_id not in active_scene.active_character_ids:
            active_scene.active_character_ids.append(final_id)
            if active_scene.id:
                await update_scene_active_characters(story_id, active_scene.id, active_scene.active_character_ids)

    return char

# --- Kohtaukset ja Vuorot ---

async def create_scene(story_id: str, scene: Scene) -> int:
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO scenes (chapter_number, location, scene_goal, active_character_ids, is_active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (scene.chapter_number, scene.location, scene.scene_goal, json.dumps(scene.active_character_ids), 1 if scene.is_active else 0)
        )
        await db.commit()
        return cursor.lastrowid

async def get_active_scene(story_id: str) -> Optional[Scene]:
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM scenes WHERE is_active = 1 ORDER BY id DESC LIMIT 1") as cursor:
            row = await cursor.fetchone()
            if row:
                return Scene(
                    id=row["id"],
                    chapter_number=row["chapter_number"],
                    location=row["location"],
                    scene_goal=row["scene_goal"],
                    active_character_ids=json.loads(row["active_character_ids"] or "[]"),
                    is_active=bool(row["is_active"]),
                    created_at=str(row["created_at"])
                )
    return None

async def close_scene(story_id: str, scene_id: int):
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE scenes SET is_active = 0 WHERE id = ?", (scene_id,))
        await db.commit()

async def add_scene_turn(story_id: str, turn: SceneTurn) -> int:
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO scene_turns (scene_id, turn_index, acting_character_id, perceived_context, internal_monologue, character_action, director_prose, image_prompt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn.scene_id, turn.turn_index, turn.acting_character_id,
                turn.perceived_context, turn.internal_monologue, turn.character_action,
                turn.director_prose, turn.image_prompt
            )
        )
        await db.commit()
        return cursor.lastrowid

async def get_scene_turns(story_id: str, scene_id: int) -> List[SceneTurn]:
    db_path = get_db_path(story_id)
    turns = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM scene_turns WHERE scene_id = ? ORDER BY turn_index ASC", (scene_id,)) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                turns.append(SceneTurn(
                    id=row["id"],
                    scene_id=row["scene_id"],
                    turn_index=row["turn_index"],
                    acting_character_id=row["acting_character_id"],
                    perceived_context=row["perceived_context"],
                    internal_monologue=row["internal_monologue"],
                    character_action=row["character_action"],
                    director_prose=row["director_prose"],
                    image_prompt=row["image_prompt"],
                    created_at=str(row["created_at"])
                ))
    return turns

async def get_all_story_turns(story_id: str) -> List[SceneTurn]:
    db_path = get_db_path(story_id)
    turns = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM scene_turns ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                turns.append(SceneTurn(
                    id=row["id"],
                    scene_id=row["scene_id"],
                    turn_index=row["turn_index"],
                    acting_character_id=row["acting_character_id"],
                    perceived_context=row["perceived_context"],
                    internal_monologue=row["internal_monologue"],
                    character_action=row["character_action"],
                    director_prose=row["director_prose"],
                    image_prompt=row["image_prompt"],
                    created_at=str(row["created_at"])
                ))
    return turns

# --- Tapahtumakronikka (Chronicle) ---

async def add_chronicle_entry(story_id: str, entry: ChronicleEntry):
    db_path = get_db_path(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO chronicle_entries (chapter_index, scene_index, summary, world_updates)
            VALUES (?, ?, ?, ?)
            """,
            (entry.chapter_index, entry.scene_index, entry.summary, entry.world_updates)
        )
        await db.commit()

async def get_chronicle(story_id: str) -> List[ChronicleEntry]:
    db_path = get_db_path(story_id)
    entries = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM chronicle_entries ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                entries.append(ChronicleEntry(
                    id=row["id"],
                    chapter_index=row["chapter_index"],
                    scene_index=row["scene_index"],
                    summary=row["summary"],
                    world_updates=row["world_updates"],
                    created_at=str(row["created_at"])
                ))
    return entries
