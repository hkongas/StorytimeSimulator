import asyncio
import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from config import settings
from core.types import AdvanceStoryRequest, StoryInitRequest
from database import db, turn_store
from engine.story_engine import StoryEngine
from tests.test_engine import MockLLMClient


class ReactionLLM(MockLLMClient):
    def __init__(self):
        super().__init__()
        self.resolutions = []
        self.plans = 0
        self.characters = []
        self.signal = {}
        self.followup_progress = True
        self.entered = asyncio.Event()
        self.block_followup = False

    async def json_completion(self, messages, role="director", **kwargs):
        schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
        result = await super().json_completion(messages, role=role, **kwargs)
        if schema == "turn_plan":
            self.plans += 1
        if role == "character":
            self.characters.append(messages)
        if schema == "prose_turn":
            self.resolutions.append(messages)
            cycle = len(self.resolutions)
            if cycle == 2 and self.block_followup:
                self.entered.set()
                await asyncio.Event().wait()
            result.update(
                prose=f"Beat {cycle}", character_state_updates=[],
                events=[{"id": "new", "description": f"A new clue appears {cycle}",
                         "observations": [{"character_id": "char_mira", "text": f"VISIBLE_CLUE_{cycle}"}],
                         "derived_from": "consequence",
                         "change_kind": "information" if cycle == 1 or self.followup_progress else "none"}],
                decision_character_ids=["char_mira"],
                pending_reaction_decisions=[{"decision_kind": "meaningful_choice", "event_id": "new", "character_id": "char_mira",
                                             "decision": "Choose whether to reveal the new clue or conceal it"}]
            )
            if cycle == 1:
                result.update(self.signal)
        return result


class ReactionCycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_dir = settings.STORIES_DIR
        self.directory = Path.cwd() / (".test-reactions-" + uuid4().hex)
        settings.STORIES_DIR = self.directory
        self.model = ReactionLLM()
        self.engine = StoryEngine(self.model)
        self.story_id = (await self.engine.initialize_new_story(StoryInitRequest(title="Reactions")))["story_id"]

    async def asyncTearDown(self):
        settings.STORIES_DIR = self.original_dir
        shutil.rmtree(self.directory, ignore_errors=True)

    async def advance(self, **kwargs):
        return await self.engine.advance_turn(self.story_id, request_id="request", **kwargs)

    async def test_default_off_and_option_fingerprint(self):
        self.assertFalse(AdvanceStoryRequest().extra_reaction_cycle)
        with self.assertRaises(ValidationError):
            AdvanceStoryRequest(extra_reaction_cycle="true")
        await self.advance()
        self.assertEqual(len(self.model.resolutions), 1)
        with self.assertRaises(turn_store.TurnConflictError):
            await self.advance(extra_reaction_cycle=True)

    async def test_on_cap_replay_clock_and_undo(self):
        before = await db.get_story_bible(self.story_id)
        events = [event async for event in self.engine.advance_turn_streaming(
            self.story_id, mode="simulation", request_id="request", extra_reaction_cycle=True)]
        self.assertEqual(len(self.model.resolutions), 2)
        self.assertEqual(self.model.plans, 1)
        self.assertEqual(sum(event["type"] == "turn_complete" for event in events), 1)
        self.assertTrue(any(event.get("phase") == "extra_reaction" for event in events))
        response = await self.advance(mode="simulation", extra_reaction_cycle=True)
        self.assertEqual(response.extra_reaction_cycles, 1)
        self.assertEqual(response.turn_index, 3)
        self.assertEqual(len(self.model.resolutions), 2)
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 3)
        after = await db.get_story_bible(self.story_id)
        self.assertEqual(after["clocks"][0]["remaining_beats"], before["clocks"][0]["remaining_beats"] - 1)
        await turn_store.verify_committed_turn(self.story_id, response)
        await turn_store.rollback_last_turn(self.story_id, await turn_store.get_revision(self.story_id))
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 2)
        with self.assertRaises(turn_store.TurnConflictError):
            await self.advance(mode="simulation", extra_reaction_cycle=True)

    async def test_stopping_signals(self):
        for signal in ({"chapter_end": True}, {"scene_stop": True}, {"requires_player_input": True},
                       {"pending_reaction_decisions": []}, {"decision_character_ids": []},
                       {"active_character_ids": ["char_eerik"]}):
            with self.subTest(signal=signal):
                self.model.signal = signal
                self.model.resolutions.clear()
                await self.engine.advance_turn(self.story_id, request_id=uuid4().hex, extra_reaction_cycle=True)
                self.assertEqual(len(self.model.resolutions), 1)

    async def test_invalid_event_reference_is_atomic(self):
        self.model.signal = {"pending_reaction_decisions": [{"decision_kind": "meaningful_choice", "event_id": "missing", "character_id": "char_mira", "decision": "Choose"}]}
        with self.assertRaises(ValueError):
            await self.advance(extra_reaction_cycle=True)
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 1)

    async def test_invalid_character_or_observation_never_triggers(self):
        for character_id in ("absent", "char_eerik"):
            with self.subTest(character_id=character_id):
                self.model.signal = {"pending_reaction_decisions": [{"decision_kind": "meaningful_choice", "event_id": "new", "character_id": character_id, "decision": "Choose"}]}
                self.model.resolutions.clear()
                await self.engine.advance_turn(self.story_id, request_id=uuid4().hex, extra_reaction_cycle=True)
                self.assertEqual(len(self.model.resolutions), 1)

    async def test_repeated_event_and_no_progress_stop(self):
        await self.advance()
        self.model.resolutions.clear()
        await self.engine.advance_turn(self.story_id, request_id="repeat", extra_reaction_cycle=True)
        self.assertEqual(len(self.model.resolutions), 1)

    async def test_no_progress_followup_not_committed(self):
        self.model.followup_progress = False
        response = await self.advance(extra_reaction_cycle=True)
        self.assertEqual(len(self.model.resolutions), 2)
        self.assertEqual(response.turn_index, 2)
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 2)
        await self.advance(extra_reaction_cycle=True)
        self.assertEqual(len(self.model.resolutions), 2)

    async def test_roleplay_never_replays_player_or_intervention(self):
        await db.set_player_character(self.story_id, "char_eerik")
        response = await self.advance(mode="roleplay", user_input="EXACT_PLAYER_ACTION",
                                      private_intention="PRIVATE_INTENT", director_guidance="WORLD_COMMAND",
                                      extra_reaction_cycle=True)
        self.assertEqual(response.turn_index, 3)
        content = self.model.resolutions[1][1]["content"]
        supplied = json.loads(content.split("[ALL CHARACTERS' INTENTIONS & ATTEMPTS THIS MOMENT]\n", 1)[1].split("\n\n[RECENT PROSE", 1)[0])
        self.assertEqual([item["character_id"] for item in supplied], ["char_mira"])
        self.assertNotIn("EXACT_PLAYER_ACTION", json.dumps(supplied))
        self.assertNotIn("WORLD_COMMAND", content)
        self.assertNotIn("PRIVATE_INTENT", content)
        self.assertIsNone(response.acting_character)
        self.assertTrue(response.requires_player_input)

    async def test_failed_followup_preserves_first_turn_and_never_retries(self):
        original = self.model.json_completion
        async def completion(*args, **kwargs):
            result = await original(*args, **kwargs)
            schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
            if schema == "prose_turn" and len(self.model.resolutions) == 2:
                result["events"][0]["actor_id"] = "char_eerik"
            return result
        self.model.json_completion = completion
        await db.set_player_character(self.story_id, "char_eerik")
        response = await self.advance(mode="roleplay", user_input="EXACT_PLAYER_ACTION", extra_reaction_cycle=True)
        self.assertEqual(response.turn_index, 2)
        self.assertTrue(response.warnings)
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 2)
        await self.advance(mode="roleplay", user_input="EXACT_PLAYER_ACTION", extra_reaction_cycle=True)
        self.assertEqual(len(self.model.resolutions), 2)

    async def test_completed_job_replays_final_followup_over_sse_after_restart(self):
        from web import api
        original_engine = api.engine
        api.engine = self.engine
        endpoint = f"/api/stories/{self.story_id}/turn-jobs/request"
        try:
            response = await self.advance(extra_reaction_cycle=True)
            self.assertEqual(response.turn_index, 3)
            async with AsyncClient(transport=ASGITransport(app=api.app), base_url="http://test") as client:
                result = await client.get(endpoint)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["data"]["request_id"], response.request_id)
                sse = await client.get(endpoint + "/events")
                self.assertIn("event: result", sse.text)
                self.assertIn('"extra_reaction_cycles": 1', sse.text)
                start = await client.post(endpoint.rsplit("/", 1)[0], json={"request_id": "request", "extra_reaction_cycle": True})
                self.assertEqual(start.status_code, 200)
                await api.jobs[(self.story_id, "request")]["task"]
                result = await client.get(endpoint)
                self.assertEqual(result.json()["data"]["turn_index"], 3)
                self.assertEqual(len(self.model.resolutions), 2)
        finally:
            api.jobs.pop((self.story_id, "request"), None)
            api.engine = original_engine

    async def test_player_decision_blocks_followup(self):
        await db.set_player_character(self.story_id, "char_mira")
        await self.advance(mode="roleplay", user_input="Look", extra_reaction_cycle=True)
        self.assertEqual(len(self.model.resolutions), 1)

    async def test_job_sse_cancel_and_restart_replay(self):
        from web import api
        original_engine = api.engine
        api.engine = self.engine
        self.model.block_followup = True
        request = {"request_id": "job", "extra_reaction_cycle": True}
        endpoint = f"/api/stories/{self.story_id}/turn-jobs/job"
        try:
            async with AsyncClient(transport=ASGITransport(app=api.app), base_url="http://test") as client:
                start = await client.post(endpoint.rsplit("/", 1)[0], json=request)
                self.assertEqual(start.status_code, 200)
                await asyncio.wait_for(self.model.entered.wait(), 180)
                self.assertTrue(self.engine.is_busy(self.story_id))
                cancelled = await client.delete(endpoint)
                self.assertEqual(cancelled.status_code, 200)
                await api.jobs[(self.story_id, "job")]["task"]
                result = await client.get(endpoint)
                self.assertEqual(result.json()["status"], "completed")
                self.assertEqual(result.json()["data"]["turn_index"], 2)
                sse = await client.get(endpoint + "/events")
                self.assertIn('"phase": "extra_reaction"', sse.text)
                self.assertIn("event: result", sse.text)
                api.jobs.pop((self.story_id, "job"))
                replay = await client.get(endpoint)
                self.assertEqual(replay.json()["data"]["turn_index"], 2)
                self.engine = StoryEngine(self.model)
                await self.engine.advance_turn(self.story_id, request_id="job", extra_reaction_cycle=True)
                self.assertEqual(len(self.model.resolutions), 2)
        finally:
            job = api.jobs.pop((self.story_id, "job"), None)
            if job and not job["task"].done():
                job["task"].cancel()
                await asyncio.gather(job["task"], return_exceptions=True)
            api.engine = original_engine

class ReactionEligibilityTests(unittest.TestCase):
    def test_only_new_material_observed_meaningful_choices_for_eligible_ai(self):
        from core.schemas import ProseTurnResponse
        from core.types import Character, Scene
        from engine.reaction_cycle import eligible_reaction_decisions
        scene = Scene(id=1, location="Room", scene_goal="Talk", active_character_ids=["ai", "player"])
        roster = {identifier: Character(id=identifier, name=identifier, age=30,
                  is_player_controlled=identifier == "player") for identifier in ("ai", "player")}
        base = {"prose": "Clue", "scene_location": "Room", "active_character_ids": ["ai", "player"],
                "decision_character_ids": ["ai"],
                "events": [{"id": "event", "description": "New clue", "derived_from": "consequence",
                            "change_kind": "information", "observations": [{"character_id": "ai", "text": "Clue"}]}],
                "pending_reaction_decisions": [{"decision_kind": "meaningful_choice", "event_id": "event", "character_id": "ai", "decision": "Share or conceal"}]}
        def eligible(data=None, progress=True, sources=None, prior=None):
            return eligible_reaction_decisions(ProseTurnResponse.model_validate(data or base), roster, scene,
                                              "roleplay", progress, sources if sources is not None else {"event"}, prior or set())
        self.assertEqual(len(eligible()), 1)
        self.assertEqual(eligible(progress=False), [])
        self.assertEqual(eligible(sources=set()), [])
        self.assertEqual(eligible(prior={"new clue"}), [])
        for field, value in (("chapter_end", True), ("scene_stop", True), ("requires_player_input", True),
                             ("scene_location", "Elsewhere"), ("active_character_ids", []),
                             ("decision_character_ids", ["ai", "player"])):
            with self.subTest(field=field):
                self.assertEqual(eligible(base | {field: value}), [])
        for change in ({"change_kind": "none"}, {"observations": []},
                       {"observations": [{"character_id": "player", "text": "Clue"}]}):
            self.assertEqual(eligible(base | {"events": [base["events"][0] | change]}), [])
        for status in ("dead", "unconscious", "inactive", "archived"):
            roster["ai"].status = status
            self.assertEqual(eligible(), [])
        roster["ai"].status = "active"
        roster["ai"].location_id = "elsewhere"
        self.assertEqual(eligible(), [])
        with self.assertRaises(ValidationError):
            ProseTurnResponse.model_validate(base | {"pending_reaction_decisions": [base["pending_reaction_decisions"][0] | {"decision_kind": "possible_reaction"}]})
