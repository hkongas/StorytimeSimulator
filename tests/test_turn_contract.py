import json
import tempfile
import unittest
from pathlib import Path

import aiosqlite

from config import settings
from core.schemas import StoryEvent, StoryObservation, PlannerResponse
from core.types import StoryInitRequest
from database import db, turn_store
from engine.story_engine import StoryEngine
from engine.turn_contract import concrete_progress
from tests.test_engine import RecordingLLM


class TurnContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.original_dir = settings.STORIES_DIR
        settings.STORIES_DIR = Path(self.temporary.name)
        self.model = RecordingLLM()
        self.engine = StoryEngine(self.model)
        result = await self.engine.initialize_new_story(StoryInitRequest(title="Contract"))
        self.story_id = result["story_id"]
        self.model.calls.clear()

    async def asyncTearDown(self):
        settings.STORIES_DIR = self.original_dir
        self.temporary.cleanup()

    def customize(self, transform):
        original = self.model.json_completion

        async def completion(*args, **kwargs):
            result = await original(*args, **kwargs)
            schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
            transform(schema, result)
            if schema == "prose_turn":
                intention_block = args[0] if args else kwargs.get("messages", [])
                content = intention_block[1]["content"]
                supplied = json.loads(content.split("[ALL CHARACTERS' INTENTIONS & ATTEMPTS THIS MOMENT]\n", 1)[1].split("\n\n[RECENT PROSE", 1)[0])
                for event in result.get("events", []):
                    if event.get("derived_from", "").startswith("intent:"):
                        actor_id = event["derived_from"].split(":", 1)[1]
                        event["intent_id"] = next(item["id"] for item in supplied if item["character_id"] == actor_id)
            return result

        self.model.json_completion = completion

    async def test_observation_details_survive_commit_and_next_decision(self):
        def transform(schema, result):
            if schema == "prose_turn":
                result["character_state_updates"] = []
                result["events"] = [{"description": "PRIVATE_GENERAL_DESCRIPTION",
                    "derived_from": "intent:char_mira", "actor_id": "char_mira",
                    "observations": [
                        {"character_id": "char_eerik", "text": "ONLY_HEARD_WORDS", "modality": "heard"},
                        {"character_id": "char_mira", "text": "ONLY_OWN_EXPERIENCE"}]}]
        self.customize(transform)
        await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual(await turn_store.get_observation(self.story_id, "char_eerik"), "ONLY_HEARD_WORDS")
        self.assertEqual(await turn_store.get_observation(self.story_id, "char_mira"), "ONLY_OWN_EXPERIENCE")
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            async with connection.execute("SELECT content FROM character_memories WHERE created_at_turn = 2 AND memory_type = 'observation'") as cursor:
                memories = [row[0] for row in await cursor.fetchall()]
        self.assertNotIn("PRIVATE_GENERAL_DESCRIPTION", memories)
        self.model.calls.clear()
        await self.engine.advance_turn(self.story_id, mode="simulation")
        character_calls = [messages for role, messages in self.model.calls if role == "character"]
        self.assertTrue(character_calls)
        self.assertTrue(all("PRIVATE_GENERAL_DESCRIPTION" not in str(messages) for messages in character_calls))

    async def test_expired_clock_fires_once_without_omniscient_observers(self):
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            await connection.execute("UPDATE clocks SET remaining_beats = 1")
            await connection.commit()
        await self.engine.advance_turn(self.story_id, mode="simulation")
        await self.engine.advance_turn(self.story_id, mode="simulation")
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            async with connection.execute("SELECT id FROM events WHERE description = 'Vartijat saapuvat raunioille.'") as cursor:
                rows = await cursor.fetchall()
            self.assertEqual(len(rows), 1)
            async with connection.execute("SELECT COUNT(*) FROM event_witnesses WHERE event_id = ?", (rows[0][0],)) as cursor:
                self.assertEqual((await cursor.fetchone())[0], 0)

    async def test_reveal_only_transmits_explicit_observed_evidence(self):
        secret = (await db.get_story_bible(self.story_id))["secret_truths"][0]
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            await connection.execute("UPDATE secret_truths SET reveal_state = 'hinted' WHERE id = ?", (secret["id"],))
            await connection.commit()
        def transform(schema, result):
            if schema == "turn_plan":
                result["reveals"] = [{"truth_id": secret["id"], "how": "NARRATOR_DISCOVERY"}]
                result["events"] = [{"description": "SIGN_VISIBLE", "derived_from": "world",
                    "observations": [{"character_id": "char_eerik", "text": "VISIBLE_LETTERS"}]}]
        self.customize(transform)
        await self.engine.advance_turn(self.story_id, mode="simulation")
        calls = [messages for role, messages in self.model.calls if role == "character"]
        self.assertTrue(all(secret["fact"] not in str(messages) and "NARRATOR_DISCOVERY" not in str(messages) for messages in calls))
        self.assertTrue(any("VISIBLE_LETTERS" in str(messages) for messages in calls))
        self.assertEqual((await db.get_story_bible(self.story_id))["secret_truths"][0]["reveal_state"], "revealed")

    async def test_planner_cannot_resolve_character_intent(self):
        def transform(schema, result):
            if schema == "turn_plan":
                result["events"] = [{"description": "Eerik chooses to leave", "derived_from": "intent:char_eerik",
                    "actor_id": "char_eerik", "witnesses": ["char_eerik"]}]
        self.customize(transform)
        with self.assertRaisesRegex(ValueError, "vapaaehtoista"):
            await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 1)
        self.assertFalse(any(role == "character" for role, _ in self.model.calls))

    async def test_planner_current_location_id_preserves_scene_name(self):
        scene = await db.get_active_scene(self.story_id)
        def transform(schema, result):
            if schema == "turn_plan":
                result["scene_location"] = db.location_identifier(scene.location)
        self.customize(transform)
        await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual((await db.get_active_scene(self.story_id)).location, scene.location)
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 2)
        self.assertTrue(any(role == "character" for role, _ in self.model.calls))
        for character in await db.get_all_characters(self.story_id):
            self.assertEqual(character.location_id, db.location_identifier(scene.location))

    async def test_planner_cannot_move_scene_before_character_decisions(self):
        properties = PlannerResponse.model_json_schema()["properties"]
        self.assertNotIn("scene_location", properties)
        self.assertNotIn("character_state_updates", properties)
        self.assertNotIn("active_character_ids", properties)

    async def test_cosmetic_mental_update_does_not_count_as_progress(self):
        def transform(schema, result):
            if schema == "turn_plan":
                result["character_state_updates"] = [{"event_id": "resolved", "character_id": "char_eerik", "mental_state": "Chosen retreat"}]
            if schema == "prose_turn":
                result["character_state_updates"] = [{"event_id": "resolved", "character_id": "char_eerik", "mental_state": "Still cautious"}]
        self.customize(transform)
        response = await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual((await turn_store.get_runtime(self.story_id))["no_progress_beats"], 1)
        self.assertEqual(response.warnings, [])

    async def test_resolved_location_and_state_used_in_player_view(self):
        await db.set_player_character(self.story_id, "char_eerik")
        def transform(schema, result):
            if schema == "prose_turn":
                result["location"] = {"event_id": "resolved", "id": db.location_identifier("New courtyard"), "name": "New courtyard"}
                result["active_character_ids"] = ["char_eerik", "char_mira"]
                result["character_state_updates"] = [{"event_id": "resolved", "character_id": "char_eerik", "physical_state": "NEW_STATE"}]
        self.customize(transform)
        await self.engine.advance_turn(self.story_id, mode="simulation")
        messages = next(messages for role, messages in self.model.calls if '"perceived_events"' in messages[1]["content"])
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["location"], "New courtyard")
        self.assertEqual(payload["character"]["physical_state"], "NEW_STATE")
        self.assertEqual(payload["character"]["location_id"], db.location_identifier("New courtyard"))
        self.assertEqual((await db.get_character(self.story_id, "char_eerik")).location_id, db.location_identifier("New courtyard"))
        self.assertEqual((await turn_store.get_runtime(self.story_id))["no_progress_beats"], 0)

    async def test_resolved_possession_persists_atomically(self):
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            await connection.execute("INSERT INTO items (id, name, holder_character_id, state) VALUES ('letter', 'Letter', 'char_eerik', 'sealed')")
            await connection.commit()
        def transform(schema, result):
            if schema == "prose_turn":
                result["state_changes"] = [{"event_id": "resolved", "entity": "item", "entity_id": "letter", "field": "holder_character_id", "value": "char_mira"}]
        self.customize(transform)
        await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual((await db.get_item(self.story_id, "letter"))["holder_character_id"], "char_mira")
        self.assertEqual((await turn_store.get_runtime(self.story_id))["no_progress_beats"], 0)
        await turn_store.rollback_last_turn(self.story_id, await turn_store.get_revision(self.story_id))
        self.assertEqual((await db.get_item(self.story_id, "letter"))["holder_character_id"], "char_eerik")

    async def test_view_retry_uses_historical_state_and_memories(self):
        await db.set_player_character(self.story_id, "char_eerik")
        original = self.model.json_completion
        fail = True
        async def completion(*args, **kwargs):
            schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
            if schema == "player_view" and fail:
                raise RuntimeError("temporary view failure")
            result = await original(*args, **kwargs)
            if schema == "prose_turn":
                result["character_state_updates"] = [{"event_id": "resolved", "character_id": "char_eerik", "physical_state": "HISTORICAL_STATE"}]
            return result
        self.model.json_completion = completion
        await self.engine.advance_turn(self.story_id, mode="simulation")
        turn_id = max(turn.id for turn in await db.get_all_story_turns(self.story_id))
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            await connection.execute("UPDATE characters SET physical_state = 'FUTURE_STATE' WHERE id = 'char_eerik'")
            await connection.execute("INSERT INTO character_memories (character_id, content, memory_type, importance_score) VALUES ('char_eerik', 'FUTURE_SECRET', 'belief', 10)")
            await connection.execute("UPDATE character_observations SET content = 'FUTURE_OBSERVATION' WHERE character_id = 'char_eerik'")
            await connection.commit()
        fail = False
        self.model.calls.clear()
        await self.engine.retry_player_view(self.story_id, turn_id, "char_eerik")
        messages = next(messages for role, messages in self.model.calls if '"perceived_events"' in messages[1]["content"])
        self.assertIn("HISTORICAL_STATE", str(messages))
        self.assertNotIn("FUTURE_STATE", str(messages))
        self.assertNotIn("FUTURE_SECRET", str(messages))
        self.assertNotIn("FUTURE_OBSERVATION", str(messages))

    async def test_destroyed_access_updates_route_without_rewriting_truth(self):
        secret = (await db.get_story_bible(self.story_id))["secret_truths"][0]
        def transform(schema, result):
            if schema == "prose_turn":
                result["truth_access_updates"] = [{"event_id": "resolved", "truth_id": secret["id"], "discoverable_via": "Old route destroyed; new access unknown", "related_location_id": None}]
        self.customize(transform)
        await self.engine.advance_turn(self.story_id, mode="simulation")
        updated = (await db.get_story_bible(self.story_id))["secret_truths"][0]
        self.assertEqual(updated["fact"], secret["fact"])
        self.assertEqual(updated["discoverable_via"], "Old route destroyed; new access unknown")

    async def test_resolver_context_omits_reading_baggage(self):
        runtime = await turn_store.get_runtime(self.story_id)
        runtime["player_views"] = {"secret": "READING_BAGGAGE"}
        runtime["initial_reading"] = {"prose": "OPENING_BAGGAGE"}
        runtime["summary"] = "CANONICAL_SUMMARY"
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            await connection.execute("INSERT INTO story_runtime (id, state_json) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json", (json.dumps(runtime),))
            await connection.commit()
        await self.engine.advance_turn(self.story_id, mode="simulation")
        resolver = next(messages for role, messages in self.model.calls if "[ALL CHARACTERS' INTENTIONS" in messages[1]["content"])
        content = resolver[1]["content"]
        self.assertNotIn("READING_BAGGAGE", content)
        self.assertNotIn("OPENING_BAGGAGE", content)
        self.assertEqual(content.count("CANONICAL_SUMMARY"), 1)

    async def test_invalid_resolved_change_does_not_commit(self):
        def transform(schema, result):
            if schema == "prose_turn":
                result["state_changes"] = [{"event_id": "resolved", "entity": "item", "entity_id": "unknown", "field": "state", "value": "taken"}]
        self.customize(transform)
        with self.assertRaisesRegex(ValueError, "tuntemattomaan esineeseen"):
            await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 1)

    async def test_empty_bible_remains_empty_across_turns(self):
        await db.save_story_bible(self.story_id, [], [], [])
        await self.engine.advance_turn(self.story_id, mode="simulation")
        await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual(await db.get_story_bible(self.story_id),
                         {"secret_truths": [], "clocks": [], "offscreen_agents": []})
        self.assertFalse(any('"story_bible"' in str(messages) for _, messages in self.model.calls))

    async def test_initialization_accepts_no_secrets_or_clocks(self):
        def transform(schema, result):
            if schema == "story_initialization":
                result["secret_truths"] = []
                result["clocks"] = []
                result["offscreen_agents"] = []
        self.customize(transform)
        created = await self.engine.initialize_new_story(StoryInitRequest(title="Quiet afternoon"))
        bible = await db.get_story_bible(created["story_id"])
        self.assertTrue(all(not values for values in bible.values()))
        await self.engine.advance_turn(created["story_id"], mode="simulation")
        self.assertEqual(await db.get_story_bible(created["story_id"]), bible)

    async def test_history_compression_is_separate_from_resolver(self):
        runtime = await turn_store.get_runtime(self.story_id)
        runtime["summary"] = "Older history. " * 360
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            await connection.execute("INSERT INTO story_runtime (id, state_json) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json", (json.dumps(runtime),))
            await connection.commit()
        await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual((await turn_store.get_runtime(self.story_id))["summary"], "COMPACT_HISTORY")
        self.assertTrue(any("Compress the supplied narrator continuity" in str(messages) for _, messages in self.model.calls))

    async def test_bible_additions_commit_and_undo(self):
        def transform(schema, result):
            if schema == "prose_turn":
                result["bible_additions"] = {"clocks": [{"id": "new_clock", "description": "Meeting starts", "remaining_beats": 3}]}
        self.customize(transform)
        await self.engine.advance_turn(self.story_id, mode="simulation")
        clocks = (await db.get_story_bible(self.story_id))["clocks"]
        self.assertEqual(next(clock for clock in clocks if clock["id"] == "new_clock")["remaining_beats"], 3)
        await turn_store.rollback_last_turn(self.story_id, await turn_store.get_revision(self.story_id))
        self.assertFalse(any(clock["id"] == "new_clock" for clock in (await db.get_story_bible(self.story_id))["clocks"]))

    async def test_unknown_event_link_rejects_entire_turn(self):
        def transform(schema, result):
            if schema == "prose_turn":
                result["character_state_updates"] = [{"event_id": "missing", "character_id": "char_eerik", "physical_state": "Injured"}]
        self.customize(transform)
        with self.assertRaisesRegex(ValueError, "tapahtumaviite"):
            await self.engine.advance_turn(self.story_id, mode="simulation")
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 1)


class ProgressTests(unittest.TestCase):
    def test_negative_tableau_is_not_progress(self):
        event = StoryEvent(description="No movement, no reply", observations=[], derived_from="consequence", actor_id="actor")
        self.assertFalse(concrete_progress({}, {}, [event]))
        event.change_kind = "goal"
        self.assertTrue(concrete_progress({}, {}, [event]))

    def test_observation_requires_witness(self):
        event = StoryEvent(description="Secret", derived_from="world",
                           observations=[StoryObservation(character_id="actor", text="Visible evidence")])
        self.assertEqual(event.observation_for("actor"), "Visible evidence")
        self.assertEqual(event.observation_for("absent"), "")
