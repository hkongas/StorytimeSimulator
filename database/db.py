import json
import asyncio
import shutil
import sqlite3
from contextlib import closing
import aiosqlite
from pathlib import Path
from typing import List, Optional, Dict, Any
from config import settings
from core.types import StoryMeta, Character, CharacterMemory, Scene, SceneTurn, ChronicleEntry

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_migration_locks: Dict[Path, asyncio.Lock] = {}

def get_story_dir(story_id: str) -> Path:
    if not story_id or len(story_id) > 100 or not all(
        char.isalnum() or char in "_-" for char in story_id
    ):
        raise ValueError("Virheellinen tarinatunniste.")
    root = settings.STORIES_DIR.resolve()
    directory = (root / story_id).resolve()
    if directory.parent != root:
        raise ValueError("Tarina ei ole sallitussa kansiossa.")
    return directory


def get_db_path(story_id: str) -> Path:
    return get_story_dir(story_id) / "story.db"

async def init_story_db(story_id: str):
    path = get_db_path(story_id)
    async with _migration_locks.setdefault(path, asyncio.Lock()):
        await _initialize_story_db(story_id)


async def _initialize_story_db(story_id: str):
    """Alustaa tarinaprojektin SQLite-tietokannan, taulut ja suorittaa automaattiset sarakemigraatiot."""
    db_path = get_db_path(story_id)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    required_tables = {"story_revision", "story_runtime", "turn_receipts", "turn_snapshots", "prose_edits",
                       "character_observations", "story_meta", "chronicle_entries", "characters",
                       "character_memories", "scenes", "scene_turns", "api_calls"}
    with closing(sqlite3.connect(":memory:")) as validation:
        validation.executescript(schema_sql)
        schema_tables = {row[0] for row in validation.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if not required_tables <= schema_tables:
        missing = ", ".join(sorted(required_tables - schema_tables))
        raise ValueError(f"Tietokannan skeematiedosto on puutteellinen: {missing}. Tarkista schema.sql ja pilvisynkronointi.")

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("PRAGMA user_version") as cursor:
            version = (await cursor.fetchone())[0]
        if version >= 5:
            async with db.execute("PRAGMA table_info(api_calls)") as cursor:
                log_columns = {row[1] for row in await cursor.fetchall()}
            async with db.execute("SELECT name FROM sqlite_master WHERE type = 'table'") as cursor:
                existing_tables = {row[0] for row in await cursor.fetchall()}
            if required_tables <= existing_tables and {"cached_tokens", "cost_known"} <= log_columns:
                return
        backup = db_path.with_suffix(".pre-v5.db" if version >= 4 else ".pre-v4.db")
        async with db.execute("SELECT name FROM sqlite_master WHERE name = 'story_meta'") as cursor:
            existing = await cursor.fetchone()
        if existing and not backup.exists():
            async with aiosqlite.connect(backup) as destination:
                await db.backup(destination)
        await db.executescript("BEGIN IMMEDIATE;\n" + schema_sql)

        # Migraatiotarkistukset olemassa oleville tauluille
        async def add_column_if_missing(table: str, column: str, col_type: str):
            async with db.execute(f"PRAGMA table_info({table})") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            if column not in columns:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

        await add_column_if_missing("story_meta", "tone_profile", "TEXT DEFAULT 'default'")
        await add_column_if_missing("story_meta", "custom_tone_override", "TEXT DEFAULT ''")
        await add_column_if_missing("story_meta", "language", "TEXT DEFAULT 'fi'")
        await add_column_if_missing("story_meta", "theme_color", "TEXT DEFAULT ''")

        await add_column_if_missing("characters", "status", "TEXT DEFAULT 'active'")
        await add_column_if_missing("characters", "tier", "TEXT DEFAULT 'major'")
        await add_column_if_missing("characters", "known_locations", "TEXT DEFAULT '[]'")
        await add_column_if_missing("characters", "last_active_turn", "INTEGER")
        await add_column_if_missing("characters", "represents_group", "TEXT")
        await add_column_if_missing("characters", "group_size_hint", "INTEGER")

        await add_column_if_missing("scene_turns", "choices", "TEXT DEFAULT '[]'")
        await add_column_if_missing("chronicle_entries", "repetition_flag", "BOOLEAN DEFAULT 0")
        await add_column_if_missing("api_calls", "cached_tokens", "INTEGER DEFAULT 0")
        await add_column_if_missing("api_calls", "cost_known", "BOOLEAN DEFAULT 0")
        for table in ("story_meta", "characters", "character_memories", "scenes", "scene_turns", "story_runtime", "chronicle_entries"):
            for operation in ("INSERT", "UPDATE", "DELETE"):
                await db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS revision_{table}_{operation.lower()} AFTER {operation} ON {table} BEGIN UPDATE story_revision SET revision = revision + 1 WHERE id = 1; END"
                )
        await db.execute("CREATE INDEX IF NOT EXISTS memories_by_character ON character_memories(character_id, id)")
        await db.execute(f"PRAGMA user_version = {max(version, 5)}")
        await db.commit()

# --- Tarinan metatiedot ---

async def save_story_meta(story_id: str, meta: StoryMeta, runtime_updates: Optional[Dict[str, Any]] = None):
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO story_meta (id, title, genre, world_lore, director_plot_arc, director_notes, tone_profile, custom_tone_override, language, theme_color, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                meta.id, meta.title, meta.genre, meta.world_lore, meta.director_plot_arc,
                meta.director_notes, meta.tone_profile, meta.custom_tone_override, meta.language,
                meta.theme_color or ""
            )
        )
        if runtime_updates:
            async with db.execute("SELECT state_json FROM story_runtime WHERE id = 1") as cursor:
                row = await cursor.fetchone()
            state = json.loads(row[0]) if row else {}
            state.update(runtime_updates)
            await db.execute("INSERT INTO story_runtime VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json", (json.dumps(state),))
        await db.commit()

async def get_story_meta(story_id: str) -> Optional[StoryMeta]:
    db_path = get_db_path(story_id)
    if not db_path.exists():
        return None
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM story_meta WHERE id = ?", (story_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                row_keys = row.keys()
                return StoryMeta(
                    id=row["id"],
                    title=row["title"],
                    genre=row["genre"],
                    world_lore=row["world_lore"],
                    director_plot_arc=row["director_plot_arc"],
                    director_notes=row["director_notes"],
                    tone_profile=row["tone_profile"] if "tone_profile" in row_keys else "default",
                    custom_tone_override=row["custom_tone_override"] if "custom_tone_override" in row_keys else "",
                    language=row["language"] if "language" in row_keys else "fi",
                    theme_color=row["theme_color"] if "theme_color" in row_keys else "",
                    created_at=str(row["created_at"]),
                    updated_at=str(row["updated_at"])
                )
    return None

async def delete_story(story_id: str) -> bool:
    """Poistaa tarinan ja sen kansion kokonaan."""
    story_dir = get_story_dir(story_id)
    if story_dir.exists():
        shutil.rmtree(story_dir, ignore_errors=True)
        return True
    return False

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
                    "tone_profile": meta.tone_profile,
                    "created_at": meta.created_at,
                    "updated_at": meta.updated_at
                })
            else:
                stories.append({
                    "id": item.name,
                    "title": item.name,
                    "genre": "Tuntematon",
                    "tone_profile": "default",
                    "created_at": "",
                    "updated_at": ""
                })
    return sorted(stories, key=lambda x: x.get("updated_at") or "", reverse=True)

# --- Hahmot ja Muistit ---

async def save_character(story_id: str, char: Character):
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO characters 
            (id, name, age, gender, appearance, personality, is_player_controlled, physical_state, mental_state, secret_motive, public_bio, status, tier, known_locations, last_active_turn, represents_group, group_size_hint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                char.id, char.name, char.age, char.gender, char.appearance, char.personality,
                1 if char.is_player_controlled else 0,
                char.physical_state, char.mental_state, char.secret_motive, char.public_bio,
                char.status, char.tier, json.dumps(char.known_locations), char.last_active_turn,
                char.represents_group, char.group_size_hint
            )
        )
        await db.commit()

async def get_character(story_id: str, char_id: str) -> Optional[Character]:
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM characters WHERE id = ?", (char_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                row_keys = row.keys()
                known_locs = json.loads(row["known_locations"]) if "known_locations" in row_keys and row["known_locations"] else []
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
                    status=row["status"] if "status" in row_keys and row["status"] else "active",
                    tier=row["tier"] if "tier" in row_keys and row["tier"] else "major",
                    known_locations=known_locs,
                    last_active_turn=row["last_active_turn"] if "last_active_turn" in row_keys else None,
                    represents_group=row["represents_group"] if "represents_group" in row_keys else None,
                    group_size_hint=row["group_size_hint"] if "group_size_hint" in row_keys else None,
                    created_at=str(row["created_at"])
                )
    return None

async def get_all_characters(story_id: str, include_archived: bool = True) -> List[Character]:
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    characters = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM characters ORDER BY name ASC" if include_archived else "SELECT * FROM characters WHERE status != 'archived' ORDER BY name ASC"
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                row_keys = row.keys()
                known_locs = json.loads(row["known_locations"]) if "known_locations" in row_keys and row["known_locations"] else []
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
                    status=row["status"] if "status" in row_keys and row["status"] else "active",
                    tier=row["tier"] if "tier" in row_keys and row["tier"] else "major",
                    known_locations=known_locs,
                    last_active_turn=row["last_active_turn"] if "last_active_turn" in row_keys else None,
                    represents_group=row["represents_group"] if "represents_group" in row_keys else None,
                    group_size_hint=row["group_size_hint"] if "group_size_hint" in row_keys else None,
                    created_at=str(row["created_at"])
                ))
    return characters

async def update_character_state(
    story_id: str,
    char_id: str,
    physical_state: str,
    mental_state: str,
    secret_motive: Optional[str] = None,
    status: Optional[str] = None,
    last_active_turn: Optional[int] = None
):
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        updates = ["physical_state = ?", "mental_state = ?"]
        params: List[Any] = [physical_state, mental_state]

        if secret_motive is not None:
            updates.append("secret_motive = ?")
            params.append(secret_motive)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if last_active_turn is not None:
            updates.append("last_active_turn = ?")
            params.append(last_active_turn)

        params.append(char_id)
        sql = f"UPDATE characters SET {', '.join(updates)} WHERE id = ?"
        await db.execute(sql, tuple(params))
        await db.commit()

async def update_character_details(story_id: str, char_id: str, updates: Dict[str, Any]) -> Optional[Character]:
    """Päivittää hahmon tietoja (nimi, luonne, ulkonäkö, tilat jne.) lennosta."""
    char = await get_character(story_id, char_id)
    if not char:
        return None
    for key, val in updates.items():
        if hasattr(char, key) and val is not None:
            setattr(char, key, val)
    await save_character(story_id, char)
    return char

async def set_player_character(story_id: str, char_id: str) -> Optional[Character]:
    """Asettaa tietyn hahmon ainoaksi pelattavaksi hahmoksi."""
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE characters SET is_player_controlled = 0")
        await db.execute("UPDATE characters SET is_player_controlled = 1 WHERE id = ?", (char_id,))
        await db.commit()
    return await get_character(story_id, char_id)

async def add_character_memory(story_id: str, memory: CharacterMemory):
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO character_memories (character_id, scene_index, memory_type, content, importance_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (memory.character_id, memory.scene_index, memory.memory_type, memory.content, memory.importance_score)
        )
        await db.commit()

async def get_relevant_memories(story_id: str, char_id: str, query: str, limit: int = 20) -> List[CharacterMemory]:
    recent = await get_character_memories(story_id, char_id, limit=max(1, limit // 2))
    terms = list(dict.fromkeys(word.casefold().strip(".,!?;:") for word in query.split() if len(word) > 3))[:8]
    conditions = " OR ".join("LOWER(content) LIKE ?" for term in terms) or "0"
    recent_ids = [memory.id for memory in recent]
    exclusion = f"AND id NOT IN ({', '.join('?' for identifier in recent_ids)})" if recent_ids else ""
    async with aiosqlite.connect(get_db_path(story_id)) as connection:
        connection.row_factory = aiosqlite.Row
        async with connection.execute(
            f"SELECT * FROM character_memories WHERE character_id = ? AND (importance_score > 1 OR {conditions}) {exclusion} ORDER BY importance_score DESC, id DESC LIMIT ?",
            (char_id, *(f"%{term}%" for term in terms), *recent_ids, limit - len(recent))
        ) as cursor:
            recalled = [CharacterMemory.model_validate(dict(row)) for row in await cursor.fetchall()]
    return sorted(recent + recalled, key=lambda memory: memory.id or 0)


async def get_character_memories(story_id: str, char_id: str, limit: int = 25) -> List[CharacterMemory]:
    """Hakee hahmon tuoreimmat muistit (kasvatettu raja pitkille seikkailuille)."""
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
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
    await init_story_db(story_id)
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

    base_id = raw_char.get("id") or raw_char.get("name", "char").lower().replace(" ", "_")
    base_id = "".join([c if c.isalnum() else "_" for c in base_id]).strip("_")[:30] or "imported_char"
    
    existing = await get_all_characters(story_id)
    existing_ids = {c.id for c in existing}
    
    final_id = base_id
    counter = 1
    while final_id in existing_ids:
        final_id = f"{base_id}_{counter}"
        counter += 1

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
        public_bio=raw_char.get("public_bio", ""),
        status=raw_char.get("status", "active"),
        tier=raw_char.get("tier", "major"),
        known_locations=raw_char.get("known_locations", [])
    )

    await save_character(story_id, char)

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
    await init_story_db(story_id)
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
    if not db_path.exists():
        return None
    await init_story_db(story_id)
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
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE scenes SET is_active = 0 WHERE id = ?", (scene_id,))
        await db.commit()

async def add_scene_turn(story_id: str, turn: SceneTurn) -> int:
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO scene_turns (scene_id, turn_index, acting_character_id, perceived_context, internal_monologue, character_action, director_prose, choices, image_prompt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn.scene_id, turn.turn_index, turn.acting_character_id,
                turn.perceived_context, turn.internal_monologue, turn.character_action,
                turn.director_prose, json.dumps(turn.choices or []), turn.image_prompt
            )
        )
        await db.commit()
        return cursor.lastrowid

async def get_scene_turns(story_id: str, scene_id: int) -> List[SceneTurn]:
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    turns = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM scene_turns WHERE scene_id = ? ORDER BY turn_index ASC", (scene_id,)) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                row_keys = row.keys()
                choices = json.loads(row["choices"]) if "choices" in row_keys and row["choices"] else []
                turns.append(SceneTurn(
                    id=row["id"],
                    scene_id=row["scene_id"],
                    turn_index=row["turn_index"],
                    acting_character_id=row["acting_character_id"],
                    perceived_context=row["perceived_context"],
                    internal_monologue=row["internal_monologue"],
                    character_action=row["character_action"],
                    director_prose=row["director_prose"],
                    choices=choices,
                    image_prompt=row["image_prompt"],
                    created_at=str(row["created_at"])
                ))
    return turns

async def get_all_story_turns(story_id: str) -> List[SceneTurn]:
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    turns = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM scene_turns ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                row_keys = row.keys()
                choices = json.loads(row["choices"]) if "choices" in row_keys and row["choices"] else []
                turns.append(SceneTurn(
                    id=row["id"],
                    scene_id=row["scene_id"],
                    turn_index=row["turn_index"],
                    acting_character_id=row["acting_character_id"],
                    perceived_context=row["perceived_context"],
                    internal_monologue=row["internal_monologue"],
                    character_action=row["character_action"],
                    director_prose=row["director_prose"],
                    choices=choices,
                    image_prompt=row["image_prompt"],
                    created_at=str(row["created_at"])
                ))
    return turns

# --- Tapahtumakronikka (Chronicle) ---

async def add_chronicle_entry(story_id: str, entry: ChronicleEntry):
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO chronicle_entries (chapter_index, scene_index, summary, world_updates, repetition_flag)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entry.chapter_index, entry.scene_index, entry.summary, entry.world_updates, 1 if entry.repetition_flag else 0)
        )
        await db.commit()

async def get_chronicle(story_id: str) -> List[ChronicleEntry]:
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    entries = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM chronicle_entries ORDER BY id ASC") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                row_keys = row.keys()
                entries.append(ChronicleEntry(
                    id=row["id"],
                    chapter_index=row["chapter_index"],
                    scene_index=row["scene_index"],
                    summary=row["summary"],
                    world_updates=row["world_updates"],
                    repetition_flag=bool(row["repetition_flag"]) if "repetition_flag" in row_keys else False,
                    created_at=str(row["created_at"])
                ))
    return entries

# --- Rajapintakutsut ja Token-lokitus (Debug & Profilointi) ---

async def log_api_call(
    story_id: Optional[str],
    role: str,
    model: str,
    duration_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    reasoning_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
    status: str = "success",
    error_message: str = "",
    cached_tokens: int = 0,
    cost_known: bool = False
):
    """Kirjaa tehdyn LLM-kutsun tiedot ja keston tietokantaan."""
    if not story_id:
        return
    db_path = get_db_path(story_id)
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO api_calls (story_id, role, model, duration_seconds, prompt_tokens, completion_tokens, reasoning_tokens, total_tokens, cost_usd, status, error_message, cached_tokens, cost_known)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (story_id, role, model, duration_seconds, prompt_tokens, completion_tokens, reasoning_tokens, total_tokens, cost_usd, status, error_message, cached_tokens, cost_known)
        )
        await db.commit()

async def get_api_calls_for_story(story_id: str, limit: int = 60) -> List[Dict[str, Any]]:
    """Hakee tarinaan liittyvät rajapintakutsut aikajärjestyksessä laskevasti."""
    db_path = get_db_path(story_id)
    if not db_path.exists():
        return []
    await init_story_db(story_id)
    logs = []
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM api_calls WHERE story_id = ? ORDER BY id DESC LIMIT ?", (story_id, limit)) as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                logs.append(dict(r))
    return logs

async def get_story_api_stats(story_id: str) -> Dict[str, Any]:
    """Laskee yhteenvedon tarinan API-käytöstä: tokenit, kesto, hinta ja viimeisin kutsu."""
    db_path = get_db_path(story_id)
    if not db_path.exists():
        return {
            "total_calls": 0, "total_tokens": 0, "total_prompt_tokens": 0,
            "total_completion_tokens": 0, "total_reasoning_tokens": 0,
            "total_duration_seconds": 0.0, "total_cost_usd": 0.0, "last_duration_seconds": 0.0
        }
    await init_story_db(story_id)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT 
                COUNT(*) as total_calls,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                COALESCE(SUM(cached_tokens), 0) as total_cached_tokens,
                COALESCE(SUM(cost_known), 0) as priced_calls,
                COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                COALESCE(SUM(reasoning_tokens), 0) as total_reasoning_tokens,
                COALESCE(SUM(duration_seconds), 0.0) as total_duration_seconds,
                COALESCE(SUM(CASE WHEN cost_known = 1 THEN cost_usd ELSE 0 END), 0.0) as total_cost_usd
            FROM api_calls WHERE story_id = ?
            """,
            (story_id,)
        ) as cursor:
            stats = dict(await cursor.fetchone() or {})

        # Haetaan viimeisimmän kutsun kesto
        async with db.execute("SELECT duration_seconds, model FROM api_calls WHERE story_id = ? ORDER BY id DESC LIMIT 1", (story_id,)) as cursor:
            last_row = await cursor.fetchone()
            stats["last_duration_seconds"] = last_row["duration_seconds"] if last_row else 0.0
            stats["last_model"] = last_row["model"] if last_row else ""

    return stats
