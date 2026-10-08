import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import settings
from core.schemas import (DecisionGroup, PlannerResponse, ProseTurnResponse, SituationResponse, StoryEvent)
from core.types import Character, Scene, StoryInitRequest
from database import db, turn_store
from engine.adaptive_interaction import (InteractionBudget, as_outcome, collect_adaptive,
                                         environment_signature, relay_response, verify_permit)
from engine.interaction_history import accepted_outcome
from engine.story_engine import StoryEngine
from tests.test_engine import MockLLMClient


class AdaptiveInteractionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.roster = {key: Character(id=key, name=key, age=30, location_id="room") for key in "abc"}
        self.scene = Scene(location="Room", location_id="room", active_character_ids=list(self.roster), scene_goal="Talk")
        self.calls = []

    async def decide(self, actor, starts, previous):
        self.calls.append((actor.id, [event.observation_for(actor.id) for item in previous for event in item.events
                                     if event.observation_for(actor.id)]))
        return {"character_id": actor.id, "action": "Talk", "speech": actor.id + " reply", "private_thought": "PRIVATE"}

    async def accept(self, response, fresh, previous):
        return as_outcome(response)

    def response(self, intention, receiver=None, identifier=None):
        event = StoryEvent(id=identifier or intention["id"] + "-event", description=intention["speech"],
                           derived_from="intent:" + intention["character_id"], actor_id=intention["character_id"],
                           intent_id=intention["id"], observations=[{"character_id": key, "text": intention["speech"], "modality": "heard"} for key in "abc"])
        return SituationResponse(events=[event], next_group={"reactions": [{"decision_kind": "meaningful_choice",
            "event_id": event.id, "character_id": receiver, "decision": "New response"}]} if receiver else None,
            stop_reason="continue" if receiver else "ended")

    async def test_dynamic_a_b_a_and_unplanned_c(self):
        next_actors = iter(["b", "a", "c", None])
        async def resolve(fresh, previous, budget):
            return self.response(fresh[0], next(next_actors))
        result = await collect_adaptive(DecisionGroup(id="start", character_ids=["a"]), self.decide, resolve,
                                       self.accept, self.roster, self.scene)
        self.assertEqual([item[0] for item in self.calls], ["a", "b", "a", "c"])
        self.assertEqual(self.calls[2][1], ["a reply", "b reply"])
        self.assertEqual(len(result[2]), 4)

    async def test_sequential_group_cannot_preassign_dependent_actors(self):
        from unittest.mock import AsyncMock
        resolve = AsyncMock()
        with self.assertRaisesRegex(ValueError, "one actor"):
            await collect_adaptive(DecisionGroup(id="start", mode="sequential", character_ids=["a", "b"]),
                self.decide, resolve, self.accept, self.roster, self.scene)
        self.assertEqual(self.calls, [])
        resolve.assert_not_awaited()

    async def test_parallel_locked_views_not_completion_order(self):
        async def resolve(fresh, previous, budget):
            self.assertEqual([item["character_id"] for item in fresh], ["a", "b"])
            return SituationResponse(stop_reason="ended")
        await collect_adaptive(DecisionGroup(id="start", character_ids=["a", "b"]), self.decide,
                               resolve, self.accept, self.roster, self.scene)
        self.assertEqual(self.calls, [("a", []), ("b", [])])

    async def test_player_and_decision_controller_time_token_budgets(self):
        async def resolve(fresh, previous, budget):
            return self.response(fresh[0], "b" if fresh[0]["character_id"] == "a" else "a")
        for budget in (InteractionBudget(decision_limit=1), InteractionBudget(call_limit=1),
                       InteractionBudget(seconds=0), InteractionBudget(token_limit=0)):
            self.calls.clear()
            result = await collect_adaptive(DecisionGroup(id="start", character_ids=["a"]), self.decide,
                resolve, self.accept, self.roster, self.scene, budget=budget)
            self.assertTrue(result[-1])
            self.assertLessEqual(len(self.calls), 1)
            self.assertIn("budget", budget.stop_reason)
        self.calls.clear()
        result = await collect_adaptive(DecisionGroup(id="start", character_ids=["a"]), self.decide,
            resolve, self.accept, self.roster, self.scene, player_id="b")
        self.assertEqual([item[0] for item in self.calls], ["a"])
        self.assertTrue(result[-1])

    async def test_consumed_or_unobserved_trigger_rejected(self):
        event = StoryEvent(id="seed", description="hello", derived_from="world", observations=[{"character_id": "a", "text": "hello"}])
        async def resolve(fresh, previous, budget):
            return SituationResponse(next_group={"reactions": [{"decision_kind": "meaningful_choice", "event_id": "seed",
                "character_id": "a", "decision": "Again"}]}, stop_reason="continue")
        with self.assertRaisesRegex(ValueError, "consumed"):
            await collect_adaptive(DecisionGroup(id="start", character_ids=["b"]), self.decide,
                resolve, self.accept, self.roster, self.scene, initial_events=[event])

    async def test_situation_role_uses_own_model_and_defaults(self):
        from core.llm_client import LLMClient
        from unittest.mock import AsyncMock
        client = LLMClient(provider="openai", api_key="fake", base_url="http://127.0.0.1:1")
        provider = client._get_provider()
        with patch.object(settings, "SITUATION_MODEL", "situation-test-model"), patch.object(provider, "json_completion", new=AsyncMock(return_value={})) as completion:
            await client.json_completion(messages=[], role="situation")
        self.assertEqual(completion.call_args.kwargs["model"], "situation-test-model")
        self.assertEqual(completion.call_args.kwargs["reasoning_effort"], settings.SITUATION_REASONING_EFFORT)
        self.assertEqual(completion.call_args.kwargs["max_tokens"], settings.SITUATION_MAX_TOKENS)

    async def test_token_reservation_prevents_service_call(self):
        from engine.interaction_llm import InteractionLLM, InteractionTokenLimit
        from unittest.mock import AsyncMock
        model = type("Fake", (), {"json_completion": AsyncMock(return_value={})})()
        budget = InteractionBudget(token_limit=1)
        with self.assertRaises(InteractionTokenLimit):
            await InteractionLLM(model, budget).json_completion(messages=[{"role": "user", "content": "context"}], role="character")
        model.json_completion.assert_not_awaited()
        budget = InteractionBudget(token_limit=100)
        await InteractionLLM(model, budget).json_completion(messages=[], role="character", max_tokens=200)
        self.assertLessEqual(budget.tokens, 100)
        self.assertLess(model.json_completion.call_args.kwargs["max_tokens"], 200)

    async def test_parallel_private_observations_are_isolated(self):
        first = ProseTurnResponse(prose="not given to actors", events=[StoryEvent(id="secret", description="SECRET_WORLD",
            derived_from="world", observations=[{"character_id": "a", "text": "A_ONLY", "modality": "heard"}])])
        calls = {}
        async def decide(actor, starts, previous):
            calls[actor.id] = [event.observation_for(actor.id) for item in previous for event in item.events]
            self.assertNotIn("SECRET_WORLD", json.dumps([item.model_dump() for item in previous]))
            return {"character_id": actor.id, "action": "Wait", "speech": ""}
        resolutions = 0
        async def resolve(fresh, previous, budget):
            nonlocal resolutions
            resolutions += 1
            if resolutions == 1:
                return SituationResponse(events=first.events, next_group={"reactions": [{"decision_kind": "meaningful_choice",
                    "event_id": "secret", "character_id": "a", "decision": "Consider private words"}]}, stop_reason="continue")
            return SituationResponse(stop_reason="ended")
        await collect_adaptive(DecisionGroup(id="start", character_ids=["a", "b"]), decide,
            resolve, self.accept, self.roster, self.scene)
        self.assertEqual(calls["b"], [])
        self.assertEqual(calls["a"], ["A_ONLY"])

    async def test_unheard_stimulus_and_hidden_relay_are_rejected(self):
        async def resolve(fresh, previous, budget):
            response = self.response(fresh[0], "c")
            response.events[0].observations = [observation for observation in response.events[0].observations if observation.character_id != "c"]
            return response
        with self.assertRaisesRegex(ValueError, "verified observation"):
            await collect_adaptive(DecisionGroup(id="first", character_ids=["a"]), self.decide,
                resolve, self.accept, self.roster, self.scene)
        from core.schemas import RelayPermit
        event = self.response({"id": "i", "character_id": "a", "speech": "hello"}).events[0]
        self.roster["b"].visibility_state = "hidden"
        with self.assertRaises(ValueError):
            verify_permit(RelayPermit(source_event_id=event.id, participant_ids=["a", "b"], max_utterances=1),
                          {event.id: event}, self.roster, self.scene)

    async def test_relay_speech_only_and_invalidation(self):
        source = self.response({"id": "i", "character_id": "a", "speech": "hello"}, "b").events[0]
        from core.schemas import RelayPermit
        permit = RelayPermit(source_event_id=source.id, participant_ids=["a", "b"], max_utterances=3)
        verify_permit(permit, {source.id: source}, self.roster, self.scene)
        signature = environment_signature(self.roster, self.scene)
        decision = {"id": "reply", "character_id": "b", "speech": "Answer", "private_thought": "SECRET",
                    "interaction_kind": "speech", "resolution_hint": False, "suggested_recipient_ids": ["a"]}
        response = relay_response([decision], permit, signature, self.roster, self.scene)
        self.assertEqual(response.events[0].witnesses, ["a", "b"])
        self.assertNotIn("SECRET", response.model_dump_json())
        self.assertNotIn("c", response.events[0].witnesses)
        self.roster["b"].location_id = None
        self.assertIsNone(relay_response([decision], permit, signature, self.roster, self.scene))
        with self.assertRaises(ValueError):
            verify_permit(permit, {source.id: source}, self.roster, self.scene)

    async def test_fast_path_a_b_a_without_per_utterance_controller(self):
        calls = []
        async def decide(actor, starts, previous):
            return {"character_id": actor.id, "action": "Talk", "speech": actor.id + " says hello",
                    "interaction_kind": "speech", "resolution_hint": False, "private_thought": "SECRET"}
        async def resolve(fresh, previous, budget):
            calls.append(fresh[0]["character_id"])
            response = self.response(fresh[0], "b")
            response.relay_permit = __import__("core.schemas", fromlist=["RelayPermit"]).RelayPermit(
                source_event_id=response.events[0].id, participant_ids=["a", "b"], max_utterances=2)
            return response
        budget = InteractionBudget(decision_limit=3)
        result = await collect_adaptive(DecisionGroup(id="first", character_ids=["a"]), decide,
            resolve, self.accept, self.roster, self.scene, budget=budget)
        self.assertEqual(calls, ["a"])
        self.assertEqual([item["character_id"] for item in result[0]], ["a", "b", "a"])
        self.assertEqual(len(result[2]), 3)

    def test_ordered_intermediate_continuity_commitments_and_time(self):
        intermediate = [ProseTurnResponse(prose="ignored", events=[StoryEvent(id="e1", description="agreement", derived_from="world")],
                         recap_delta="Agreed", continuity={"facts_added": ["temporary"]},
                         commitments=[{"id": "promise", "event_id": "e1", "description": "Help", "participants": ["a"]}],
                         elapsed_time={"amount": 2, "clock_beats": 0}),
                        ProseTurnResponse(prose="ignored", events=[StoryEvent(id="e2", description="fulfilled", derived_from="world")],
                         recap_delta="Fulfilled", continuity={"facts_removed": ["temporary"], "facts_added": ["done"]},
                         commitments=[{"id": "promise", "event_id": "e2", "description": "Help", "participants": ["a"], "status": "fulfilled"}],
                         elapsed_time={"amount": 3, "clock_beats": 0})]
        result = accepted_outcome(PlannerResponse(direction="talk", decision_character_ids=[]), intermediate, {}, self.scene)
        self.assertEqual([event.id for event in result.events], ["e1", "e2"])
        self.assertEqual([item.status for item in result.commitments], ["pending", "fulfilled"])
        self.assertEqual(result.world_facts, ["done"])
        self.assertEqual(result.summary, "Agreed\nFulfilled")
        self.assertEqual(result.elapsed_time.amount, 5)


class AdaptiveStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.budgets = patch.multiple(settings, SITUATION_TOKEN_LIMIT=48000, SITUATION_DECISION_LIMIT=12,
                                      SITUATION_CALL_LIMIT=8, SITUATION_CHARACTER_LIMIT=4, SITUATION_TIME_LIMIT_SECONDS=120)
        self.budgets.start()
        self.original_dir = settings.STORIES_DIR
        settings.STORIES_DIR = Path(self.temp.name)
        self.recovery = patch("database.turn_store.get_recovery_dir", return_value=Path(self.temp.name) / "recovery")
        self.recovery.start()
        self.model = MockLLMClient()
        self.engine = StoryEngine(self.model)
        self.story_id = (await self.engine.initialize_new_story(StoryInitRequest(title="Adaptive")))["story_id"]
        characters = await db.get_all_characters(self.story_id)
        self.actors = [item.id for item in characters]
        self.names = {item.id: item.name for item in characters}
        self.schemas = []
        self.decision_number = 0
        self.resolve_number = 0
        original = self.model.json_completion
        async def completion(*args, **kwargs):
            schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
            self.schemas.append(schema)
            messages = args[0] if args else kwargs.get("messages", [])
            if schema == "turn_plan":
                return PlannerResponse(interaction_mode="adaptive", direction="Talk", decision_character_ids=[],
                    decision_groups=[DecisionGroup(id="opening", character_ids=[self.actors[0]])]).model_dump()
            if schema == "character_decision":
                data = await original(*args, **kwargs)
                self.decision_number += 1
                data.update(speech="Utterance " + str(self.decision_number), public_start=None)
                return data
            if schema == "situation_resolution":
                payload = json.loads(messages[-1]["content"])
                intention = payload["fresh_intentions"][0]
                utterance = intention["speech"] or intention["action"]
                self.resolve_number += 1
                receiver = self.actors[1] if self.resolve_number == 1 else self.actors[0] if self.resolve_number == 2 else None
                event = StoryEvent(id="event" + str(self.resolve_number), description=utterance,
                    derived_from="intent:" + intention["character_id"], actor_id=intention["character_id"], intent_id=intention["id"],
                    observations=[{"character_id": identifier, "text": utterance, "modality": "heard"} for identifier in self.actors])
                return SituationResponse(events=[event], recap_delta=utterance,
                    attempt_results=[{"intent_id": intention["id"], "event_id": event.id, "status": "succeeded"}],
                    next_group={"reactions": [{"decision_kind": "meaningful_choice", "character_id": receiver,
                        "event_id": event.id, "decision": "Answer"}]} if receiver else None,
                    stop_reason="continue" if receiver else "ended").model_dump()
            if schema == "interaction_prose":
                payload = json.loads(messages[-1]["content"])
                return {"prose": " ".join(event["description"] for event in payload["accepted_events_in_order"]) or "Tilanne jää odottamaan."}
            return await original(*args, **kwargs)
        self.model.json_completion = completion

    async def asyncTearDown(self):
        self.budgets.stop()
        self.recovery.stop()
        settings.STORIES_DIR = self.original_dir
        self.temp.cleanup()

    async def test_player_new_choice_stops_before_ai_player_response(self):
        player = await db.get_character(self.story_id, self.actors[0])
        player.is_player_controlled = True
        await db.save_character(self.story_id, player)
        original = self.model.json_completion
        async def completion(*args, **kwargs):
            result = await original(*args, **kwargs)
            if kwargs.get("json_schema", {}).get("json_schema", {}).get("name") == "turn_plan":
                result["decision_groups"][0]["character_ids"] = [self.actors[1]]
            return result
        self.model.json_completion = completion
        response = await self.engine.advance_turn(self.story_id, mode="roleplay", user_input="Ask a question", request_id="player-stop")
        self.assertEqual(self.decision_number, 1)
        self.assertEqual(self.resolve_number, 2)
        self.assertTrue(response.requires_player_input)
        runtime = await turn_store.get_runtime(self.story_id)
        self.assertEqual(runtime["interaction_boundary"]["budget"]["stop_reason"], "player")
        self.assertEqual(runtime["interaction_boundary"]["pending_reactions"][0]["character_id"], player.id)

    async def test_budget_boundary_preserves_unresolved_attempt(self):
        with patch.object(settings, "SITUATION_CALL_LIMIT", 0):
            response = await self.engine.advance_turn(self.story_id, mode="simulation", request_id="budget-stop")
        self.assertTrue(response.scene_stop)
        self.assertEqual(self.decision_number, 0)
        runtime = await turn_store.get_runtime(self.story_id)
        self.assertEqual(runtime["interaction_boundary"]["budget"]["stop_reason"], "controller_budget")

    async def test_render_repair_preserves_chain_and_streams_public_progress(self):
        original = self.model.json_completion
        render_calls = []
        async def completion(*args, **kwargs):
            schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
            if schema == "interaction_prose":
                payload = json.loads(kwargs["messages"][-1]["content"])
                render_calls.append(payload)
                if len(render_calls) == 1:
                    return {"prose": "Contradictory", "consistency_issues": ["Omitted agreement"]}
            return await original(*args, **kwargs)
        self.model.json_completion = completion
        phases = []
        async for event in self.engine.advance_turn_streaming(self.story_id, mode="simulation", request_id="render-repair"):
            phases.append(event)
        self.assertEqual(len(render_calls), 2)
        self.assertEqual(render_calls[0]["accepted_events_in_order"], render_calls[1]["accepted_events_in_order"])
        self.assertTrue(render_calls[1]["render_validation_error"])
        self.assertEqual(self.decision_number, 3)
        self.assertEqual(self.resolve_number, 3)
        self.assertEqual(sum(event.get("phase") == "situation_resolution" for event in phases), 3)

    async def test_world_addition_and_commitment_survive_controller_boundary(self):
        original = self.model.json_completion
        async def completion(*args, **kwargs):
            result = await original(*args, **kwargs)
            schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
            if schema == "situation_resolution" and self.resolve_number == 1:
                event_id = result["events"][0]["id"]
                result.update(entity_additions={"items": [{"event_id": event_id, "id": "letter", "name": "Letter"}]},
                    commitments=[{"id": "promise", "event_id": event_id, "description": "Help later", "participants": self.actors}],
                    continuity={"facts_added": ["A promise exists"]})
            elif schema == "situation_resolution" and self.resolve_number == 2:
                event_id = result["events"][0]["id"]
                result.update(commitments=[{"id": "promise", "event_id": event_id, "description": "Help later", "participants": self.actors, "status": "fulfilled"}],
                    continuity={"facts_removed": ["A promise exists"], "facts_added": ["Help completed"]})
            return result
        self.model.json_completion = completion
        await self.engine.advance_turn(self.story_id, mode="simulation", request_id="world-chain")
        runtime = await turn_store.get_runtime(self.story_id)
        self.assertEqual(runtime["commitments"]["promise"]["status"], "fulfilled")
        self.assertIn("Help completed", runtime["world_facts"])
        self.assertNotIn("A promise exists", runtime["world_facts"])
        self.assertTrue(any(item["name"] == "Letter" for item in (await db.get_planning_world(self.story_id))["items"]))

    async def test_interrupted_chain_retains_intentions_without_replay(self):
        original = self.engine.director.render_interaction
        async def interrupted(*args, **kwargs):
            raise __import__("asyncio").CancelledError()
        self.engine.director.render_interaction = interrupted
        with self.assertRaises(__import__("asyncio").CancelledError):
            await self.engine.advance_turn(self.story_id, mode="simulation", request_id="cancelled-chain")
        self.assertEqual(len(await db.get_all_story_turns(self.story_id)), 1)
        candidate = await turn_store.get_resolver_candidate(self.story_id, "cancelled-chain")
        self.assertEqual(len(candidate["audit"]["intentions"]), 3)
        before = len(self.schemas)
        self.engine.director.render_interaction = original
        with self.assertRaises(turn_store.TurnConflictError):
            await self.engine.advance_turn(self.story_id, mode="simulation", request_id="cancelled-chain")
        self.assertEqual(len(self.schemas), before)

    async def test_dynamic_speech_persisted_once_and_receipt_replay(self):
        response = await self.engine.advance_turn(self.story_id, mode="simulation", request_id="adaptive-chain")
        self.assertEqual(self.decision_number, 3)
        self.assertEqual(self.resolve_number, 3)
        self.assertEqual(response.director_prose, "Utterance 1 Utterance 2 Utterance 3")
        self.assertNotIn("prose_turn", self.schemas)
        runtime = await turn_store.get_runtime(self.story_id)
        self.assertTrue(runtime["summary"].endswith("Utterance 1\nUtterance 2\nUtterance 3"))
        self.assertEqual(len(runtime["attempt_results"]), 3)
        before = len(self.schemas)
        repeated = await self.engine.advance_turn(self.story_id, mode="simulation", request_id="adaptive-chain")
        self.assertEqual(repeated.turn_index, response.turn_index)
        self.assertEqual(len(self.schemas), before)
        candidate = await turn_store.get_resolver_candidate(self.story_id, "adaptive-chain")
        self.assertEqual(candidate["status"], "committed")
