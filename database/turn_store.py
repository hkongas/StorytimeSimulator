import json
import hashlib
import os
import base64
import gzip
from pathlib import Path
from uuid import uuid4
from typing import Any

import aiosqlite

from core.types import Character, SceneTurn, TurnResponse
from core.schemas import ProseTurnResponse
from database import db


class TurnConflictError(ValueError):
    pass


STATE_TABLES = ("characters", "character_memories", "character_observations", "scenes", "story_runtime",
                "chronicle_entries", "secret_truths", "clocks", "offscreen_agents", "locations",
                "items", "relationships")


def _encode_snapshot(state: dict) -> str:
    return "gzip:" + base64.b64encode(gzip.compress(json.dumps(state, ensure_ascii=False).encode())).decode()


def _decode_snapshot(value: str) -> dict:
    if value.startswith("gzip:"):
        return json.loads(gzip.decompress(base64.b64decode(value[5:])).decode())
    return json.loads(value)


def get_recovery_dir(story_id: str) -> Path:
    from config import settings
    project = hashlib.sha256(str(settings.BASE_DIR.resolve()).encode()).hexdigest()[:16]
    root = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return root / "Tarinamoottori" / "recovery" / project / db.get_story_dir(story_id).name


def _save_recovery(story_id: str, payload: dict):
    directory = get_recovery_dir(story_id)
    directory.mkdir(parents=True, exist_ok=True)
    identifier = hashlib.sha256(payload["response"]["request_id"].encode()).hexdigest()
    target = directory / f"{identifier}.json"
    temporary = directory / f"{uuid4().hex}.tmp"
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


async def verify_committed_turn(story_id: str, response: TurnResponse):
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute(
            "SELECT response_json FROM turn_receipts WHERE request_id = ?", (response.request_id,)
        ) as cursor:
            receipt = await cursor.fetchone()
        async with connection.execute(
            "SELECT t.director_prose FROM scene_turns t JOIN turn_snapshots s ON s.turn_id = t.id WHERE s.request_id = ?",
            (response.request_id,)
        ) as cursor:
            turn = await cursor.fetchone()
    if not receipt or not turn or turn[0] != response.director_prose:
        raise TurnConflictError("Vuoron tallennusta ei voitu varmistaa levyltä. Vastaus säilytettiin paikalliseen palautuslokiin. Älä generoi uutta vuoroa ennen palautusta.")
    stored = TurnResponse.model_validate_json(receipt[0])
    if stored.request_id != response.request_id or stored.director_prose != response.director_prose:
        raise TurnConflictError("Tallennettu vuorokuitti ei vastaa valmistunutta vastausta.")


async def _capture_state(connection, tables=None) -> dict:
    state = {}
    selected_tables = tuple(tables or STATE_TABLES)
    if not set(selected_tables) <= set(STATE_TABLES):
        raise ValueError("Palautuspiste sisältää tuntemattoman tilataulun.")
    for table in selected_tables:
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


async def get_latest_player_view(story_id: str, character_id: str, before_turn_id: int | None = None) -> dict:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        query = "SELECT view_json FROM player_view_artifacts WHERE character_id = ? AND status = 'view_ready'"
        params = [character_id]
        if before_turn_id is not None:
            query += " AND turn_id < ?"
            params.append(before_turn_id)
        query += " ORDER BY turn_id DESC LIMIT 1"
        async with connection.execute(query, params) as cursor:
            row = await cursor.fetchone()
    return json.loads(row[0]) if row and row[0] else {}


async def get_character_catchups(story_id: str) -> dict:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute(
            "SELECT character_id, turn_id, view_json FROM player_view_artifacts "
            "WHERE status = 'catchup_ready' AND turn_id = (SELECT MAX(id) FROM scene_turns WHERE branch_id = 'main')"
        ) as cursor:
            rows = await cursor.fetchall()
    revision = await get_revision(story_id)
    return {character_id: {**json.loads(view_json), "turn_id": turn_id} for character_id, turn_id, view_json in rows
            if json.loads(view_json).get("revision") == revision}


async def save_character_catchup(story_id: str, character_id: str, turn_id: int, view: dict, expected_revision: int):
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.execute("BEGIN IMMEDIATE")
        try:
            async with connection.execute("SELECT revision FROM story_revision WHERE id = 1") as cursor:
                if (await cursor.fetchone())[0] != expected_revision:
                    raise TurnConflictError("Tarina muuttui kertauksen aikana. Yritä uudelleen.")
            async with connection.execute("SELECT status FROM player_view_artifacts WHERE turn_id = ? AND character_id = ?",
                                          (turn_id, character_id)) as cursor:
                existing = await cursor.fetchone()
            if existing and existing[0] != "catchup_ready":
                raise TurnConflictError("Vuorolle on jo näkökulma tai keskeneräinen näkökulmatyö.")
            await connection.execute(
                "INSERT INTO player_view_artifacts (turn_id, character_id, status, view_json) VALUES (?, ?, 'catchup_ready', ?) "
                "ON CONFLICT(turn_id, character_id) DO UPDATE SET view_json = excluded.view_json, updated_at = CURRENT_TIMESTAMP",
                (turn_id, character_id, json.dumps({**view, "revision": expected_revision}, ensure_ascii=False)))
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise


async def get_player_view_retry_context(story_id: str, turn_id: int, character_id: str) -> dict:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute(
            """SELECT p.status, r.payload_json, s.request_id, sc.location, s.after_json
               FROM player_view_artifacts p
               JOIN turn_snapshots s ON s.turn_id = p.turn_id
               JOIN turn_receipts r ON r.request_id = s.request_id
               JOIN scene_turns t ON t.id = p.turn_id
               JOIN scenes sc ON sc.id = t.scene_id
               WHERE p.turn_id = ? AND p.character_id = ?""",
            (turn_id, character_id)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        raise ValueError("Tälle vuorolle ei ole rajattua näkökulmaa.")
    if row[0] not in {"view_failed", "view_pending"}:
        raise ValueError("Näkökulma on jo valmis.")
    payload = json.loads(row[1])
    snapshot = _decode_snapshot(row[4])
    character = next((item for item in snapshot.get("characters", []) if item["id"] == character_id), None)
    if character:
        character = dict(character)
        character["values"] = character.pop("character_values", "")
        character["known_locations"] = json.loads(character.get("known_locations") or "[]")
    return {"status": row[0], "request_id": row[2],
            "location": payload["outcome"].get("scene_location") or row[3], "character": character,
            "outcome": payload["outcome"], "audit": payload.get("audit", {}),
            "runtime": json.loads(snapshot["story_runtime"][0]["state_json"]) if snapshot.get("story_runtime") else {}}


async def get_viewpoint_snapshot(story_id: str, turn_id: int, character_id: str) -> dict:
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute("SELECT after_json FROM turn_snapshots WHERE turn_id = ?", (turn_id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return {}
    state = _decode_snapshot(row[0])
    return {
        "memories": [item for item in state.get("character_memories", []) if item["character_id"] == character_id],
        "observation": next((item["content"] for item in state.get("character_observations", [])
                             if item["character_id"] == character_id), "Ei uusia havaintoja.")
    }


async def get_last_intention(story_id: str, character_id: str) -> dict:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute("SELECT payload_json FROM turn_receipts ORDER BY rowid DESC") as cursor:
            async for row in cursor:
                payload = json.loads(row[0])
                if payload.get("rolled_back"):
                    continue
                for intention in payload.get("audit", {}).get("intentions", []):
                    if intention.get("character_id") == character_id:
                        return intention
    return {}


async def seed_observations(story_id: str, observations: dict[str, str]):
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.executemany(
            "INSERT INTO character_observations VALUES (?, ?) ON CONFLICT(character_id) DO NOTHING",
            list(observations.items())
        )
        await connection.commit()


async def get_reading_metadata(story_id: str) -> dict:
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        async with connection.execute(
            "SELECT s.turn_id, t.scene_id, r.payload_json FROM turn_snapshots s JOIN scene_turns t ON t.id = s.turn_id JOIN turn_receipts r ON r.request_id = s.request_id WHERE s.branch_id = 'main' ORDER BY s.turn_id"
        ) as cursor:
            rows = await cursor.fetchall()
    result = (await get_runtime(story_id)).get("initial_reading", {}).copy()
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        connection.row_factory = aiosqlite.Row
        async with connection.execute("SELECT turn_id, character_id, status, view_json FROM player_view_artifacts") as cursor:
            artifacts = {(str(row["turn_id"]), row["character_id"]): row for row in await cursor.fetchall()}
    for turn_id, scene_id, payload_json in rows:
        payload = json.loads(payload_json)
        if payload.get("rolled_back"):
            continue
        outcome = payload.get("outcome", {})
        views = payload.get("audit", {}).get("player_views", {})
        statuses = {}
        for (artifact_turn, character_id), artifact in artifacts.items():
            if artifact_turn == str(turn_id):
                statuses[character_id] = artifact["status"]
                if artifact["view_json"] and artifact["status"] == "view_ready":
                    views[character_id] = json.loads(artifact["view_json"])
        result[str(turn_id)] = {"chapter_id": scene_id, "chapter_title": outcome.get("chapter_title", ""),
                               "recap": outcome.get("summary", ""), "player_views": views,
                               "player_view_status": statuses}
    return result


async def save_initial_reading(story_id: str, metadata: dict):
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.execute("INSERT INTO story_runtime VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json",
                                 (json.dumps({"initial_reading": metadata}),))
        await connection.commit()


async def save_player_view(story_id: str, turn_id: int, character_id: str,
                           view: dict | None = None, error: str = ""):
    status = "view_ready" if view is not None else "view_failed"
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.execute(
            """INSERT INTO player_view_artifacts (turn_id, character_id, status, view_json, error_message)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(turn_id, character_id) DO UPDATE SET status = excluded.status,
               view_json = excluded.view_json, error_message = excluded.error_message,
               updated_at = CURRENT_TIMESTAMP""",
            (turn_id, character_id, status, json.dumps(view, ensure_ascii=False) if view else None, error[:1000])
        )
        await connection.commit()


async def save_initial_events(story_id: str, turn_id: int, events: list):
    if not events:
        return
    await db.init_story_db(story_id)
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        for event in events:
            await connection.execute(
                "INSERT OR IGNORE INTO events (id, turn_id, description, derived_from, actor_id) VALUES (?, ?, ?, ?, ?)",
                (event.id, turn_id, event.description, event.derived_from, event.actor_id)
            )
            for observation in event.observations:
                await connection.execute(
                    "INSERT OR IGNORE INTO event_witnesses (event_id, character_id, detail, modality) VALUES (?, ?, ?, ?)",
                    (event.id, observation.character_id, observation.text, observation.modality)
                )
        await connection.commit()


async def update_receipt_response(story_id: str, request_id: str, response: TurnResponse):
    async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
        await connection.execute(
            "UPDATE turn_receipts SET response_json = ? WHERE request_id = ?",
            (response.model_dump_json(), request_id)
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
            _save_recovery(story_id, {
                "story_id": story_id, "expected_last_id": expected_last_id,
                "expected_revision": revision, "before": before,
                "turn": turn.model_dump(mode="json"), "characters": [character.model_dump(mode="json") for character in characters],
                "outcome": outcome.model_dump(mode="json"), "response": response.model_dump(mode="json"),
                "fingerprint": fingerprint, "audit": audit
            })
            if outcome.scene_location:
                await connection.execute(
                    "INSERT OR IGNORE INTO locations (id, name) VALUES (?, ?)",
                    (db.location_identifier(outcome.scene_location), outcome.scene_location)
                )
            for character in characters:
                values = character.model_dump(exclude={"created_at"})
                values["known_locations"] = json.dumps(values["known_locations"])
                values["character_values"] = values.pop("values")
                columns = list(values)
                updates = ", ".join(f"{column} = excluded.{column}" for column in columns if column != "id")
                await connection.execute(
                    f"INSERT INTO characters ({', '.join(columns)}) VALUES ({', '.join('?' for column in columns)}) ON CONFLICT(id) DO UPDATE SET {updates}",
                    tuple(values.values())
                )
                observed_events = [event for event in outcome.events if character.id in event.witnesses]
                observations = [event.observation_for(character.id) for event in observed_events]
                await connection.execute(
                    "INSERT INTO character_observations VALUES (?, ?) ON CONFLICT(character_id) DO UPDATE SET content = excluded.content",
                    (character.id, "\n".join(observations) or "Ei uusia havaintoja.")
                )
                for event, observation in zip(observed_events, observations):
                    await connection.execute(
                        "INSERT INTO character_memories (character_id, scene_index, memory_type, content, importance_score, source_event_id, created_at_turn) VALUES (?, ?, 'observation', ?, 1, ?, ?)",
                        (character.id, turn.scene_id, observation, event.id, turn.turn_index)
                    )
            for intention in audit.get("intentions", []):
                memory = intention.get("memory")
                for memory_id in intention.get("context_manifest", {}).get("memory_ids", []):
                    await connection.execute(
                        "UPDATE character_memories SET last_accessed = CURRENT_TIMESTAMP WHERE id = ? AND character_id = ?",
                        (memory_id, intention["character_id"])
                    )
                if memory and memory.strip():
                    source = next((event.id for event in outcome.events
                                   if intention["character_id"] in event.witnesses), None)
                    await connection.execute(
                        "INSERT INTO character_memories (character_id, scene_index, memory_type, content, importance_score, source_event_id, created_at_turn) VALUES (?, ?, 'reflection', ?, ?, ?, ?)",
                        (intention["character_id"], turn.scene_id, memory.strip(),
                         max(1, min(10, int(intention.get("importance", 5)))), source, turn.turn_index)
                    )
                for belief in intention.get("belief_updates", []):
                    if isinstance(belief, str) and belief.strip():
                        await connection.execute(
                            "INSERT INTO character_memories (character_id, scene_index, memory_type, content, importance_score, source_event_id, created_at_turn) VALUES (?, ?, 'belief', ?, ?, NULL, ?)",
                            (intention["character_id"], turn.scene_id, belief.strip(),
                             max(1, min(10, int(intention.get("importance", 5)))), turn.turn_index)
                        )
            inserted = await connection.execute(
                "INSERT INTO scene_turns (scene_id, turn_index, acting_character_id, perceived_context, internal_monologue, character_action, director_prose, choices, image_prompt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (turn.scene_id, turn.turn_index, turn.acting_character_id, turn.perceived_context, turn.internal_monologue, turn.character_action, turn.director_prose, json.dumps(turn.choices), turn.image_prompt)
            )
            turn_id = inserted.lastrowid
            plan = audit.get("turn_plan", {})
            for event in outcome.events:
                await connection.execute(
                    "INSERT OR IGNORE INTO events (id, turn_id, description, derived_from, actor_id) VALUES (?, ?, ?, ?, ?)",
                    (event.id, turn_id, event.description, event.derived_from, event.actor_id)
                )
                for observation in event.observations:
                    await connection.execute(
                        "INSERT OR IGNORE INTO event_witnesses (event_id, character_id, detail, modality) VALUES (?, ?, ?, ?)",
                        (event.id, observation.character_id, observation.text, observation.modality)
                    )
            for reveal in plan.get("reveals", []):
                async with connection.execute("SELECT reveal_state FROM secret_truths WHERE id = ?", (reveal["truth_id"],)) as cursor:
                    row = await cursor.fetchone()
                if row:
                    next_state = {"hidden": "hinted", "hinted": "revealed", "revealed": "revealed"}[row[0]]
                    await connection.execute(
                        "UPDATE secret_truths SET reveal_state = ?, revealed_at_turn = CASE WHEN ? = 'revealed' THEN ? ELSE revealed_at_turn END WHERE id = ?",
                        (next_state, next_state, turn.turn_index, reveal["truth_id"])
                    )
            for access in outcome.truth_access_updates:
                await connection.execute(
                    "UPDATE secret_truths SET discoverable_via = ?, related_location_id = ? WHERE id = ?",
                    (access.discoverable_via, access.related_location_id, access.truth_id)
                )
            ticks = {}
            for item in plan.get("clock_ticks", []):
                ticks[item["clock_id"]] = ticks.get(item["clock_id"], 0) + item.get("amount", 1)
            async with connection.execute("SELECT id FROM clocks") as cursor:
                clock_rows = await cursor.fetchall()
            for (clock_id,) in clock_rows:
                await connection.execute(
                    "UPDATE clocks SET remaining_beats = MAX(0, remaining_beats - 1 - ?) WHERE id = ?",
                    (ticks.get(clock_id, 0), clock_id)
                )
            for agent_id, move in plan.get("offscreen_moves", {}).items():
                await connection.execute(
                    "UPDATE offscreen_agents SET progress = ?, next_move = '' WHERE id = ?",
                    (move, agent_id)
                )
            for additions in (plan.get("bible_additions", {}), outcome.bible_additions.model_dump()):
                for truth in additions.get("secret_truths", []):
                    await connection.execute(
                        "INSERT INTO secret_truths (id, fact, discoverable_via, reveal_state, related_location_id) VALUES (?, ?, ?, ?, ?)",
                        (truth["id"], truth["fact"], truth["discoverable_via"], truth["reveal_state"], truth["related_location_id"])
                    )
                for clock in additions.get("clocks", []):
                    await connection.execute(
                        "INSERT INTO clocks (id, description, remaining_beats, on_expire_effect, visible) VALUES (?, ?, ?, ?, ?)",
                        (clock["id"], clock["description"], clock["remaining_beats"], clock["on_expire_effect"], clock["visible"])
                    )
                for agent in additions.get("offscreen_agents", []):
                    await connection.execute(
                        "INSERT INTO offscreen_agents (id, name, goal, progress, location, next_move, visible_to) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (agent["id"], agent["name"], agent["goal"], agent["progress"], agent["location"], agent["next_move"], json.dumps(agent["visible_to"]))
                    )
            for change in plan.get("state_changes", []) + [item.model_dump() for item in outcome.state_changes]:
                if change.get("entity") == "item":
                    if change["field"] == "holder_character_id":
                        await connection.execute(
                            "UPDATE items SET holder_character_id = ?, location_id = NULL WHERE id = ?",
                            (change["value"], change["entity_id"])
                        )
                    elif change["field"] == "location_id":
                        await connection.execute(
                            "UPDATE items SET location_id = ?, holder_character_id = NULL WHERE id = ?",
                            (change["value"], change["entity_id"])
                        )
                    else:
                        await connection.execute(
                            "UPDATE items SET state = ? WHERE id = ?",
                            (change["value"], change["entity_id"])
                        )
                elif change.get("entity") == "relationship":
                    character_a, character_b = change["entity_id"].split("|", 1)
                    await connection.execute(
                        f"UPDATE relationships SET {change['field']} = ? WHERE character_a = ? AND character_b = ?",
                        (change["value"], character_a, character_b)
                    )
            state = {key: getattr(outcome, key) for key in ("summary", "world_facts", "plot_threads", "decision_character_ids")}
            previous_state = json.loads(before["story_runtime"][0]["state_json"]) if before["story_runtime"] else {}
            for key in ("director_plan", "director_notes", "world_description"):
                state[key] = getattr(outcome, key) or previous_state.get(key, "")
            state["chapter_title"] = outcome.chapter_title or previous_state.get("chapter_title", "")
            state["player_views"] = audit.get("player_views", previous_state.get("player_views", {}))
            state["initial_reading"] = previous_state.get("initial_reading", {})
            if outcome.chapter_end:
                state["chapter_title"] = ""
            state["mode"] = response.mode
            state["no_progress_beats"] = (0 if audit.get("objective_progress") else int(previous_state.get("no_progress_beats", 0)) + 1)
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
            view_statuses = audit.get("player_view_statuses", {})
            for character_id, status in view_statuses.items():
                view = audit.get("player_views", {}).get(character_id)
                await connection.execute(
                    "INSERT INTO player_view_artifacts (turn_id, character_id, status, view_json, error_message) VALUES (?, ?, ?, ?, ?)",
                    (turn_id, character_id, status, json.dumps(view, ensure_ascii=False) if view else None,
                     audit.get("player_view_errors", {}).get(character_id, ""))
                )
            await connection.execute(
                "INSERT INTO turn_snapshots (turn_id, request_id, before_json, after_json) VALUES (?, ?, ?, ?)",
                (turn_id, response.request_id, _encode_snapshot(before), _encode_snapshot(await _capture_state(connection)))
            )
            await connection.commit()
        except BaseException:
            await connection.rollback()
            raise
    await verify_committed_turn(story_id, response)


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
            async with connection.execute("SELECT turn_id, request_id, before_json, after_json FROM turn_snapshots WHERE branch_id = 'main' AND turn_id = (SELECT MAX(id) FROM scene_turns WHERE branch_id = 'main')") as cursor:
                snapshot = await cursor.fetchone()
            if not snapshot:
                raise TurnConflictError("Vuorolla ei ole palautuspistetta. Vanhoja vuoroja tai aloitusta ei voi kumota.")
            after = _decode_snapshot(snapshot[3])
            if await _capture_state(connection, after.keys()) != after:
                raise TurnConflictError("Vuoron jalkeen on muokattu tarinan tilaa. Kumoaminen poistaisi nama muutokset.")
            before = _decode_snapshot(snapshot[2])
            await connection.execute("DELETE FROM event_witnesses WHERE event_id IN (SELECT id FROM events WHERE turn_id = ?)", (snapshot[0],))
            await connection.execute("DELETE FROM events WHERE turn_id = ?", (snapshot[0],))
            await connection.execute("DELETE FROM player_view_artifacts WHERE turn_id = ?", (snapshot[0],))
            await connection.execute("DELETE FROM scene_turns WHERE id = ?", (snapshot[0],))
            for table in reversed(STATE_TABLES):
                if table in before:
                    await connection.execute(f"DELETE FROM {table}")
            for table in STATE_TABLES:
                if table not in before:
                    continue
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
        async with connection.execute("SELECT after_json FROM turn_snapshots WHERE branch_id = 'main' AND turn_id = (SELECT MAX(id) FROM scene_turns WHERE branch_id = 'main')") as cursor:
            row = await cursor.fetchone()
        if not row:
            return False
        after = _decode_snapshot(row[0])
        return await _capture_state(connection, after.keys()) == after


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