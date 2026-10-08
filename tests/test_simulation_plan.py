import asyncio
import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import aiosqlite
from pydantic import ValidationError

from config import settings
from core.schemas import DecisionGroup, PlannerResponse, ProseTurnResponse, StateChange
from core.types import Character, Scene, SceneTurn, StoryInitRequest
from database import db, turn_store
from engine.simulation_contract import collect_groups, is_present, validate_groups, visible_neighbours
from engine.story_engine import StoryEngine
from tests.test_engine import MockLLMClient


class SimulationUnitTests(unittest.IsolatedAsyncioTestCase):
    def test_typed_mutations(self):
        base = dict(event_id="e", entity="character", entity_id="a", field="location_id", value=None)
        self.assertIsNone(StateChange(**base).value)
        for change in ({"value": {}}, {"field": "mental_state", "value": None},
                       {"entity": "relationship", "field": "trust", "value": True},
                       {"entity": "relationship", "field": "trust", "value": float("nan")},
                       {"field": "visibility_state", "value": "maybe"}):
            with self.assertRaises(ValidationError):
                StateChange(**(base | change))

    async def test_exact_null_location_mutation_and_event_link(self):
        from engine.turn_contract import apply_resolved_changes, validate_event_links
        from core.schemas import StoryEvent
        character = Character(id="actor", name="Actor", age=30, location_id="room")
        change = StateChange(event_id="resolved", entity="character", entity_id="actor", field="location_id", value=None)
        event = StoryEvent(id="resolved", description="The character's location becomes unknown", derived_from="world")
        validate_event_links([event], [change])
        changed = await apply_resolved_changes("unused", [change], {"actor": character}, {"actor"}, "Room")
        self.assertTrue(changed)
        self.assertIsNone(character.location_id)
        with self.assertRaises(ValueError):
            validate_event_links([], [change])

    def test_presence_and_hidden_names(self):
        scene = Scene(location="Room", scene_goal="Talk", active_character_ids=["a", "b"])
        a = Character(id="a", name="A", age=30)
        b = Character(id="b", name="Hidden B", age=30, location_id="room", visibility_state="hidden")
        self.assertFalse(is_present(a, scene))
        self.assertTrue(is_present(b, scene))
        self.assertEqual(visible_neighbours(a, [a, b]), [])

    async def test_sequential_start_and_parallel_isolation(self):
        roster = {identifier: Character(id=identifier, name=identifier, age=30, location_id="room") for identifier in ("a", "b", "c")}
        calls = {}
        async def decide(character, starts, intermediate):
            calls[character.id] = json.loads(json.dumps(starts))
            return {"character_id": character.id, "private_thought": "SECRET", "action": "OUTCOME_NOT_FACT",
                    "public_start": {"text": character.id + " says hello", "observer_ids": list(roster)}}
        groups = [DecisionGroup(id="talk", mode="sequential", character_ids=["a", "b"]),
                  DecisionGroup(id="other", character_ids=["c"], depends_on=["talk"])]
        result = await collect_groups(groups, decide, roster)
        self.assertEqual(calls["a"], [])
        self.assertEqual(calls["b"][0]["text"], "a says hello")
        self.assertNotIn("SECRET", json.dumps(calls))
        self.assertNotIn("OUTCOME_NOT_FACT", json.dumps(calls))
        calls.clear()
        await collect_groups([DecisionGroup(id="parallel", character_ids=["a", "b"])], decide, roster)
        self.assertEqual(calls, {"a": [], "b": []})
        stopped = await collect_groups([DecisionGroup(id="stop", character_ids=["a"], stop_for_player=True)], decide, roster)
        self.assertTrue(stopped[-1])
        self.assertEqual(stopped[0], [])

    async def test_outcome_dependency_uses_fresh_intentions_once_and_stops(self):
        roster = {identifier: Character(id=identifier, name=identifier, age=30, location_id="room") for identifier in ("a", "b", "c")}
        received = []
        async def decide(character, starts, intermediate):
            return {"character_id": character.id, "action": "Try", "private_thought": "Private"}
        async def resolve(intentions, starts, previous):
            received.append([item["character_id"] for item in intentions])
            return ProseTurnResponse(prose="Resolved", events=[], scene_stop=len(received) == 2)
        groups = [DecisionGroup(id="first", character_ids=["a"]),
                  DecisionGroup(id="second", character_ids=["b"], requires_resolved_outcome=True),
                  DecisionGroup(id="third", character_ids=["c"], requires_resolved_outcome=True)]
        result = await collect_groups(groups, decide, roster, resolve_intermediate=resolve)
        self.assertEqual(received, [["a"], ["b"]])
        self.assertEqual(result[-2:], (2, True))

    async def test_departed_actor_cannot_decide_after_intermediate_resolution(self):
        scene = Scene(location="Room", location_id="room", scene_goal="Talk", active_character_ids=["a", "b"])
        roster = {identifier: Character(id=identifier, name=identifier, age=30, location_id="room")
                  for identifier in ("a", "b")}
        calls = []

        async def decide(character, starts, intermediate):
            calls.append(character.id)
            return {"character_id": character.id, "action": "Try", "private_thought": ""}

        async def resolve(intentions, starts, previous):
            roster["b"].location_id = "other_room"
            return ProseTurnResponse(prose="B departed", events=[])

        groups = [DecisionGroup(id="first", character_ids=["a"]),
                  DecisionGroup(id="next", character_ids=["b"], requires_resolved_outcome=True)]
        result = await collect_groups(groups, decide, roster, resolve_intermediate=resolve, scene=scene)
        self.assertEqual(calls, ["a"])
        self.assertTrue(result[-1])

    def test_group_dependencies_and_budget(self):
        for groups in ([DecisionGroup(id="a", character_ids=["a"], depends_on=["later"])],
                       [DecisionGroup(id="a", character_ids=["absent"])],
                       [DecisionGroup(id="a", character_ids=["a"]), DecisionGroup(id="b", character_ids=["a"]) ]):
            with self.assertRaises(ValueError):
                validate_groups(PlannerResponse(direction="talk", decision_character_ids=[], decision_groups=groups), {"a"}, None, 4)


class SimulationStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_dir = settings.STORIES_DIR
        self.directory = Path.cwd() / (".test-simulation-" + uuid4().hex)
        settings.STORIES_DIR = self.directory
        self.model = MockLLMClient()
        self.engine = StoryEngine(self.model)
        self.story_id = (await self.engine.initialize_new_story(StoryInitRequest(title="Simulation")))["story_id"]
        self.recovery_patch = patch("database.turn_store.get_recovery_dir", return_value=self.directory / "recovery")
        self.recovery_patch.start()

    async def asyncTearDown(self):
        self.recovery_patch.stop()
        settings.STORIES_DIR = self.original_dir
        shutil.rmtree(self.directory, ignore_errors=True)

    def customize(self, transform):
        original = self.model.json_completion
        async def completion(*args, **kwargs):
            result = await original(*args, **kwargs)
            schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
            transform(schema, result, args[0] if args else kwargs.get("messages", []))
            return result
        self.model.json_completion = completion

    async def test_controls_revision_and_hidden_continuation(self):
        controls = await turn_store.get_simulation_controls(self.story_id)
        changed = await turn_store.set_simulation_controls(self.story_id, "strong", controls["revision"], 3)
        self.assertEqual(changed["plot_guidance"], "strong")
        self.assertEqual(changed["decision_budget"], 3)
        with self.assertRaises(turn_store.TurnConflictError):
            await turn_store.set_simulation_controls(self.story_id, "adaptive", controls["revision"])
        await db.update_character_details(self.story_id, "char_mira", {"visibility_state": "hidden"})
        self.assertNotIn("char_mira", (await turn_store.get_failure_options(self.story_id))["switch_character_ids"])
        safe = await self.engine.get_simulation_controls(self.story_id)
        self.assertNotIn("char_mira", {item["id"] for item in safe["eligible_characters"]})
        with self.assertRaises(ValueError):
            await db.set_player_character(self.story_id, "char_mira")
        changed = await self.engine.set_plot_guidance(self.story_id, "adaptive", safe["revision"])
        self.assertEqual(changed["plot_guidance"], "adaptive")
        ended = await self.engine.continue_failed_player(self.story_id, "end", changed["revision"])
        self.assertTrue(ended["ended"])

    async def test_advance_preserves_saved_plot_controls_without_override(self):
        controls = await turn_store.get_simulation_controls(self.story_id)
        await turn_store.set_simulation_controls(self.story_id, "strong", controls["revision"], 3)
        await self.engine.advance_turn(self.story_id, mode="simulation", request_id="saved-controls")
        current = await turn_store.get_simulation_controls(self.story_id)
        self.assertEqual(current["plot_guidance"], "strong")
        self.assertEqual(current["decision_budget"], 3)
        replay = await self.engine.advance_turn(self.story_id, mode="simulation", request_id="saved-controls")
        self.assertEqual(replay.turn_index, 2)

    async def test_migration_is_explicit_and_revision_checked(self):
        await db.update_character_details(self.story_id, "char_mira", {"location_id": None})
        preview = await db.preview_null_location_migration(self.story_id)
        self.assertEqual(preview["characters"][0]["id"], "char_mira")
        self.assertIsNone((await db.get_character(self.story_id, "char_mira")).location_id)
        await db.apply_null_location_migration(self.story_id, {"char_mira": preview["characters"][0]["suggested_location_id"]}, preview["revision"])
        self.assertIsNotNone((await db.get_character(self.story_id, "char_mira")).location_id)
        with self.assertRaises(turn_store.TurnConflictError):
            await db.apply_null_location_migration(self.story_id, {}, preview["revision"])

    async def test_absent_no_observation_hidden_no_name_leak(self):
        await db.update_character_details(self.story_id, "char_mira", {"location_id": None})
        response = await self.engine.advance_turn(self.story_id, mode="simulation", request_id="absent")
        self.assertEqual(await turn_store.get_observation(self.story_id, "char_mira"), "Ei uusia havaintoja.")
        self.assertEqual(await db.get_character_memories(self.story_id, "char_mira"), [])
        await db.apply_null_location_migration(self.story_id, {"char_mira": db.location_identifier((await db.get_active_scene(self.story_id)).location)}, await turn_store.get_revision(self.story_id))
        await db.update_character_details(self.story_id, "char_mira", {"visibility_state": "hidden"})
        captured = []
        original = self.model.json_completion
        async def capture(*args, **kwargs):
            if kwargs.get("role") == "character":
                captured.append(kwargs["messages"])
            return await original(*args, **kwargs)
        self.model.json_completion = capture
        await self.engine.advance_turn(self.story_id, mode="simulation")
        for messages in captured:
            if '"id": "char_eerik"' in messages[1]["content"]:
                self.assertNotIn("[NÄET NYT]", messages[1]["content"])

    async def test_same_response_creation_elapsed_attempt_and_commitment(self):
        def transform(schema, result, messages):
            if schema == "prose_turn":
                supplied = json.loads(messages[1]["content"].split("[ALL CHARACTERS' INTENTIONS & ATTEMPTS THIS MOMENT]\n", 1)[1].split("\n\n[RECENT PROSE", 1)[0])
                result.update(entity_additions={"locations": [{"event_id": "resolved", "id": "new_room", "name": "Another room"}],
                                               "items": [{"event_id": "resolved", "id": "new_letter", "name": "Letter", "location_id": "new_room"}],
                                               "relationships": [{"event_id": "resolved", "character_a": "char_eerik", "character_b": "char_mira", "summary": "Agreement"}]},
                              state_changes=[{"event_id": "resolved", "entity": "character", "entity_id": "char_eerik", "field": "location_id", "value": "new_room"},
                                             {"event_id": "resolved", "entity": "item", "entity_id": "new_letter", "field": "state", "value": "open"}],
                              elapsed_time={"amount": 2, "unit": "minutes", "clock_beats": 0},
                              attempt_results=[{"intent_id": supplied[0]["id"], "status": "failed", "event_id": "resolved"}],
                              commitments=[{"id": "meeting", "event_id": "resolved", "description": "Meet tomorrow", "participants": ["char_eerik", "char_mira"]}])
        self.customize(transform)
        response = await self.engine.advance_turn(self.story_id, mode="simulation", plot_guidance="adaptive")
        world = await db.get_planning_world(self.story_id)
        location = next(item for item in world["locations"] if item["name"] == "Another room")
        self.assertEqual((await db.get_character(self.story_id, "char_eerik")).location_id, location["id"])
        self.assertEqual(world["items"][0]["state"], "open")
        self.assertEqual(world["items"][0]["location_id"], location["id"])
        runtime = await turn_store.get_runtime(self.story_id)
        self.assertEqual(runtime["elapsed_total_seconds"], 120)
        self.assertEqual(runtime["commitments"]["meeting"]["description"], "Meet tomorrow")
        self.assertEqual(runtime["plot_guidance"], "adaptive")
        self.assertEqual((await db.get_story_bible(self.story_id))["clocks"][0]["remaining_beats"], 5)

    async def test_one_repair_retains_intentions_and_failure_state(self):
        def invalid(schema, result, messages):
            if schema == "prose_turn":
                result["state_changes"] = [{"event_id": "resolved", "entity": "character", "entity_id": "char_eerik", "field": "location_id", "value": {}}]
        self.customize(invalid)
        self.engine.director.repair_turn_response = AsyncMock(return_value={"prose": "Repaired", "events": []})
        response = await self.engine.advance_turn(self.story_id, mode="simulation", request_id="repair")
        self.assertEqual(response.director_prose, "Repaired")
        self.engine.director.repair_turn_response.assert_awaited_once()
        candidate = await turn_store.get_resolver_candidate(self.story_id, "repair")
        self.assertEqual(candidate["status"], "committed")
        self.assertEqual(len(candidate["audit"]["intentions"]), 2)
        self.engine.director.repair_turn_response = AsyncMock(return_value={"prose": "Bad", "events": [], "consistency_issues": ["contradiction"]})
        revision = await turn_store.get_revision(self.story_id)
        with self.assertRaises(ValueError):
            await self.engine.advance_turn(self.story_id, mode="simulation", request_id="failed")
        self.assertEqual(await turn_store.get_revision(self.story_id), revision)
        self.assertEqual((await turn_store.get_resolver_candidate(self.story_id, "failed"))["status"], "failed")
        with self.assertRaises(turn_store.TurnConflictError):
            await self.engine.advance_turn(self.story_id, mode="simulation", request_id="failed")
        self.engine.director.repair_turn_response.assert_awaited_once()

    async def test_retry_branch_does_not_resurrect_source_and_switch_keeps_memories(self):
        response = await self.engine.advance_turn(self.story_id, request_id="source")
        turns = await db.get_all_story_turns(self.story_id)
        await db.set_player_character(self.story_id, "char_eerik")
        await db.update_character_details(self.story_id, "char_eerik", {"status": "dead"})
        revision = await turn_store.get_revision(self.story_id)
        branch = await asyncio.wait_for(turn_store.create_retry_branch(self.story_id, turns[-1].id, revision), 30)
        self.assertEqual((await db.get_character(self.story_id, "char_eerik")).status, "dead")
        self.assertEqual((await db.get_character(branch["story_id"], "char_eerik")).status, "active")
        self.assertEqual(len(await db.get_all_story_turns(branch["story_id"])), 1)
        branch_source = (await turn_store.get_runtime(branch["story_id"]))["branch_source"]
        await self.engine.advance_turn(branch["story_id"], request_id="branch-next")
        self.assertEqual((await turn_store.get_runtime(branch["story_id"]))["branch_source"], branch_source)
        self.assertEqual((await db.get_character(self.story_id, "char_eerik")).status, "dead")
        options = await turn_store.get_failure_options(self.story_id)
        self.assertTrue(options["failed"])
        await turn_store.continue_after_failure(self.story_id, "switch", revision, "char_mira")
        self.assertTrue((await db.get_character(self.story_id, "char_mira")).is_player_controlled)
        mira_memories = await db.get_character_memories(self.story_id, "char_mira")
        self.assertTrue(all(memory.character_id == "char_mira" for memory in mira_memories))

    async def test_domain_repair_preserves_original_intentions(self):
        def invalid(schema, result, messages):
            if schema == "prose_turn":
                result["state_changes"] = [{"event_id": "resolved", "entity": "item", "entity_id": "missing", "field": "state", "value": "open"}]
        self.customize(invalid)
        self.engine.director.repair_turn_response = AsyncMock(return_value={"prose": "Repaired domain", "events": []})
        await self.engine.advance_turn(self.story_id, mode="simulation", request_id="domain")
        audit = self.engine.director.repair_turn_response.call_args.args[1]
        self.assertEqual(len(audit["intentions"]), 2)
        self.assertIn("tuntemattomaan esineeseen", audit["validation_errors"][0][0]["msg"])
        persisted = await turn_store.get_resolver_candidate(self.story_id, "domain")
        self.assertEqual(persisted["audit"]["intentions"], audit["intentions"])
        self.assertEqual(persisted["status"], "committed")
        self.engine.director.repair_turn_response.assert_awaited_once()

    async def test_integrated_intermediate_resolution_is_atomic(self):
        def transform(schema, result, messages):
            if schema == "turn_plan":
                result["decision_groups"] = [{"id": "first", "character_ids": ["char_eerik"]},
                                             {"id": "second", "character_ids": ["char_mira"], "requires_resolved_outcome": True, "depends_on": ["first"]}]
            elif schema == "prose_turn" and '"intermediate_resolution": true' in messages[1]["content"]:
                result.update(prose="Intermediate", events=[{"id": "intermediate", "description": "FIRST_OBSERVED", "derived_from": "world", "observations": [{"character_id": "char_mira", "text": "FIRST_OBSERVED"}]}],
                              state_changes=[{"event_id": "intermediate", "entity": "character", "entity_id": "char_eerik", "field": "physical_state", "value": "Tired"}],
                              elapsed_time={"amount": 1, "unit": "seconds", "clock_beats": 0})
        self.customize(transform)
        response = await self.engine.advance_turn(self.story_id, mode="simulation", request_id="intermediate")
        self.assertEqual(response.decision_groups_used, 2)
        self.assertEqual((await db.get_character(self.story_id, "char_eerik")).physical_state, "Tired")
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 2)
        self.assertIn("FIRST_OBSERVED", await turn_store.get_observation(self.story_id, "char_mira"))
        async with aiosqlite.connect(db.get_db_path(self.story_id)) as connection:
            async with connection.execute("SELECT payload_json FROM turn_receipts WHERE request_id = 'intermediate'") as cursor:
                payload = json.loads((await cursor.fetchone())[0])
        self.assertTrue(any(intent["context_manifest"]["intermediate_event_ids"] for intent in payload["audit"]["intentions"]))

    async def test_chronicle_sources_not_new_world_facts(self):
        turns = await db.get_all_story_turns(self.story_id)
        lore = (await db.get_story_meta(self.story_id)).world_lore
        original_prose = [turn.director_prose for turn in turns]
        revision = await turn_store.get_revision(self.story_id)
        await self.engine.chronicle.summarize_scene_or_turns(self.story_id, 1, 1, turns)
        entry = (await db.get_chronicle(self.story_id))[0]
        self.assertEqual(entry.source_turn_ids, [turns[0].id])
        self.assertEqual(entry.summary_version, 1)
        self.assertEqual([turn.director_prose for turn in await db.get_all_story_turns(self.story_id)], original_prose)
        self.assertGreater(await turn_store.get_revision(self.story_id), revision)
        self.assertEqual((await db.get_story_meta(self.story_id)).world_lore, lore)
