import json
from typing import Any

import aiosqlite

from core.types import Character, SceneTurn, TurnResponse
from core.schemas import ProseTurnResponse
from database import db


class TurnConflictError(ValueError):
    pass


STATE_TABLES = ("characters", "character_memories", "character_observations", "scenes", "story_runtime", "chronicle_entries")


async def _capture_state(connection) -> dict:
    state = {}
    for table in STATE_TABLES:
        async with connection.execute(f"SELECT * FROM {table} ORDER BY rowid") as cursor:
            columns = [column[0] for column in cursor.description]
            state[table] = [dict(zip(columns, row)) for row in await cursor.fetchall()]
    return state


async def get_revision(story_id: str) -> int:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute("SELECT revision FROM story_revision WHERE id = 1") as cursor:
            return (await cursor.fetchone())[0]


async def get_runtime(story_id: str) -> dict[str, Any]:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute("SELECT state_json FROM story_runtime WHERE id = 1") as cursor:
            row = await cursor.fetchone()
    return json.loads(row[0]) if row else {}


async def get_observation(story_id: str, character_id: str) -> str:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute("SELECT content FROM character_observations WHERE character_id = ?", (character_id,)) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else "Ei uusia varmennettuja havaintoja. Tukeudu omiin muistoihisi ja tietoihisi."


async def seed_observations(story_id: str, observations: dict[str, str]):
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.executemany(
            "INSERT INTO character_observations VALUES (?, ?) ON CONFLICT(character_id) DO NOTHING",
            list(observations.items())
        )
        await connection.commit()


async def get_receipt(story_id: str, request_id: str, fingerprint: str | None = None) -> TurnResponse | None:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute("SELECT fingerprint, response_json, payload_json FROM turn_receipts WHERE request_id = ?", (request_id,)) as cursor:
            row = await cursor.fetchone()
    if row and json.loads(row[2]).get("rolled_back"):
        raise TurnConflictError("Vuoro on kumottu. Kayta uutta pyyntotunnistetta.")
    if row and fingerprint is not None and row[0] != fingerprint:
        raise TurnConflictError("Samaa pyyntotunnistetta ei voi kayttaa eri sisallolle.")
    return TurnResponse.model_validate_json(row[1]) if row else None


async def commit_turn(story_id: str, expected_last_id: int, turn: SceneTurn,
                      characters: list[Character], outcome: ProseTurnResponse,
                      response: TurnResponse, fingerprint: str, audit: dict[str, Any], expected_revision: int | None = None):
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            async with connection.execute("SELECT revision FROM story_revision WHERE id = 1") as cursor:
                revision = (await cursor.fetchone())[0]
            if expected_revision is not None and revision != expected_revision:
                raise TurnConflictError("Tarinan tilaa muokattiin generoinnin aikana. Muutoksia ei ylikirjoitettu.")
            async with connection.execute("SELECT COALESCE(MAX(id), 0) FROM scene_turns") as cursor:
                current_id = (await cursor.fetchone())[0]
            if current_id != expected_last_id:
                raise TurnConflictError("Tarina muuttui generoinnin aikana. Lataa tarina uudelleen.")
            before = await _capture_state(connection)
            for character in characters:
                values = character.model_dump(exclude={"created_at"})
                values["known_locations"] = json.dumps(values["known_locations"])
                columns = list(values)
                updates = ", ".join(f"{column} = excluded.{column}" for column in columns if column != "id")
                await connection.execute(
                    f"INSERT INTO characters ({', '.join(columns)}) VALUES ({', '.join('?' for column in columns)}) ON CONFLICT(id) DO UPDATE SET {updates}",
                    tuple(values.values())
                )
                observations = [event.description for event in outcome.events if character.id in event.witnesses]
                await connection.execute(
                    "INSERT INTO character_observations VALUES (?, ?) ON CONFLICT(character_id) DO UPDATE SET content = excluded.content",
                    (character.id, "\n".join(observations) or "Ei uusia havaintoja.")
                )
                for observation in observations:
                    await connection.execute(
                        "INSERT INTO character_memories (character_id, scene_index, memory_type, content, importance_score) VALUES (?, ?, 'observation', ?, 1)",
                        (character.id, turn.scene_id, observation)
                    )
            inserted = await connection.execute(
                "INSERT INTO scene_turns (scene_id, turn_index, acting_character_id, perceived_context, internal_monologue, character_action, director_prose, choices, image_prompt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (turn.scene_id, turn.turn_index, turn.acting_character_id, turn.perceived_context, turn.internal_monologue, turn.character_action, turn.director_prose, json.dumps(turn.choices), turn.image_prompt)
            )
            state = {key: getattr(outcome, key) for key in ("summary", "world_facts", "plot_threads", "decision_character_ids")}
            state["mode"] = response.mode
            await connection.execute(
                "INSERT INTO story_runtime VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json",
                (json.dumps(state),)
            )
            await connection.execute(
                "UPDATE scenes SET active_character_ids = ?, location = COALESCE(?, location), scene_goal = COALESCE(?, scene_goal) WHERE id = ?",
                (json.dumps(outcome.active_character_ids), outcome.scene_location, outcome.scene_goal, turn.scene_id)
            )
            if outcome.chapter_end:
                await connection.execute("UPDATE scenes SET is_active = 0 WHERE id = ?", (turn.scene_id,))
                await connection.execute(
                    "INSERT INTO scenes (chapter_number, location, scene_goal, active_character_ids, is_active) SELECT chapter_number + 1, location, scene_goal, active_character_ids, 1 FROM scenes WHERE id = ?",
                    (turn.scene_id,)
                )
            await connection.execute("UPDATE story_meta SET updated_at = CURRENT_TIMESTAMP")
            await connection.execute(
                "INSERT INTO turn_receipts (request_id, fingerprint, response_json, payload_json) VALUES (?, ?, ?, ?)",
                (response.request_id, fingerprint, response.model_dump_json(), json.dumps({"outcome": outcome.model_dump(), "audit": audit}))
            )
            await connection.execute(
                "INSERT INTO turn_snapshots VALUES (?, ?, ?, ?)",
                (inserted.lastrowid, response.request_id, json.dumps(before), json.dumps(await _capture_state(connection)))
            )
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise


async def update_turn_prose(story_id: str, turn_id: int, new_prose: str, expected_revision: int):
    if not new_prose.strip():
        raise ValueError("Proosa ei voi olla tyhja.")
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            async with connection.execute("SELECT revision FROM story_revision WHERE id = 1") as cursor:
                if (await cursor.fetchone())[0] != expected_revision:
                    raise TurnConflictError("Tarina muuttui. Lataa se uudelleen ennen muokkausta.")
            async with connection.execute("SELECT director_prose FROM scene_turns WHERE id = ?", (turn_id,)) as cursor:
                previous = await cursor.fetchone()
            if not previous:
                raise ValueError("Vuoroa ei loydy.")
            await connection.execute(
                "INSERT INTO prose_edits (turn_id, old_prose, new_prose) VALUES (?, ?, ?)",
                (turn_id, previous[0], new_prose)
            )
            cursor = await connection.execute(
                "UPDATE scene_turns SET director_prose = ? WHERE id = ?", (new_prose, turn_id)
            )
            if cursor.rowcount != 1:
                raise ValueError("Vuoroa ei loydy.")
            await connection.execute("UPDATE story_meta SET updated_at = CURRENT_TIMESTAMP")
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
    await rebuild_exports(story_id)


async def rollback_last_turn(story_id: str, expected_revision: int):
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            async with connection.execute("SELECT revision FROM story_revision WHERE id = 1") as cursor:
                if (await cursor.fetchone())[0] != expected_revision:
                    raise TurnConflictError("Tarina muuttui. Lataa se uudelleen ennen kumoamista.")
            async with connection.execute("SELECT turn_id, request_id, before_json, after_json FROM turn_snapshots WHERE turn_id = (SELECT MAX(id) FROM scene_turns)") as cursor:
                snapshot = await cursor.fetchone()
            if not snapshot:
                raise TurnConflictError("Vuorolla ei ole palautuspistetta. Vanhoja vuoroja tai aloitusta ei voi kumota.")
            if await _capture_state(connection) != json.loads(snapshot[3]):
                raise TurnConflictError("Vuoron jalkeen on muokattu tarinan tilaa. Kumoaminen poistaisi nama muutokset.")
            before = json.loads(snapshot[2])
            await connection.execute("DELETE FROM scene_turns WHERE id = ?", (snapshot[0],))
            for table in reversed(STATE_TABLES):
                await connection.execute(f"DELETE FROM {table}")
            for table in STATE_TABLES:
                for row in before[table]:
                    columns = list(row)
                    await connection.execute(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for column in columns)})",
                        tuple(row.values())
                    )
            await connection.execute("DELETE FROM turn_snapshots WHERE turn_id = ?", (snapshot[0],))
            await connection.execute("UPDATE turn_receipts SET payload_json = ? WHERE request_id = ?",
                                     (json.dumps({"rolled_back": True}), snapshot[1]))
            await connection.execute("UPDATE story_meta SET updated_at = CURRENT_TIMESTAMP")
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
    await rebuild_exports(story_id)


async def can_rollback(story_id: str) -> bool:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute("SELECT after_json FROM turn_snapshots WHERE turn_id = (SELECT MAX(id) FROM scene_turns)") as cursor:
            row = await cursor.fetchone()
        return bool(row) and await _capture_state(connection) == json.loads(row[0])


async def rebuild_exports(story_id: str):
    meta = await db.get_story_meta(story_id)
    turns = await db.get_all_story_turns(story_id)
    if not meta:
        raise ValueError("Tarinaa ei loydy.")
    body = "\n\n".join(turn.director_prose.strip() for turn in turns)
    for filename, text in (("story.txt", f"{meta.title}\nGenre: {meta.genre}\n\n{body}\n"),
                           ("story.md", f"# {meta.title}\n*Genre: {meta.genre}*\n\n{body}\n")):
        target = db.get_story_dir(story_id) / filename
        from uuid import uuid4
        temporary = target.with_suffix(target.suffix + f".{uuid4().hex}.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(target)