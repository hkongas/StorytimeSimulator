"""Simulation HTTP contracts without model calls or story database writes."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

import web.api as api


class FakeSimulationEngine:
    def __init__(self):
        self.revision = 7
        self.preset = "balanced"
        self.ended = False
        self.selected = None
        self.migrated = {}
        self.characters = [
            {"id": "eligible", "name": "Known", "status": "active", "location_id": "room", "hidden": False},
            {"id": "null", "name": "Unknown", "status": "active", "location_id": None, "hidden": False},
            {"id": "hidden", "name": "Secret", "status": "active", "location_id": "room", "hidden": True},
            {"id": "away", "name": "Elsewhere", "status": "active", "location_id": "street", "hidden": False},
            {"id": "dead", "name": "Gone", "status": "dead", "location_id": "room", "hidden": False},
        ]

    def is_busy(self, story_id=None):
        return False

    def check_revision(self, revision):
        if revision != self.revision:
            raise api.turn_store.TurnConflictError("Stale revision")

    async def get_simulation_controls(self, story_id):
        return {"revision": self.revision, "plot_guidance": self.preset, "player_failed": True,
                "ended": self.ended, "eligible_characters": [
                    {**c, "private_thought": "must not leak"} for c in self.characters
                    if c["status"] == "active" and c["location_id"] == "room" and not c["hidden"]],
                "snapshots": [{"id": "snapshot-1", "label": "Before failure", "director_plan": "secret plan"}],
                "secret_truths": ["must not leak"]}

    async def set_plot_guidance(self, story_id, preset, expected_revision):
        self.check_revision(expected_revision)
        self.preset = preset
        self.revision += 1
        return {"story_id": story_id, "revision": self.revision}

    async def preview_null_locations(self, story_id):
        return {"revision": self.revision, "candidates": [{"character_id": "null", "name": "Unknown",
            "suggested_location_id": "room", "ambiguous": True,
            "locations": [{"id": "room", "name": "Room"}]}]}

    async def apply_null_locations(self, story_id, selections, expected_revision):
        self.check_revision(expected_revision)
        if any(key != "null" or value != "room" for key, value in selections.items()):
            raise ValueError("Invalid migration selection")
        self.migrated.update(selections)
        self.revision += 1
        return {"story_id": story_id, "revision": self.revision}

    async def continue_failed_player(self, story_id, action, expected_revision, character_id=None, snapshot_id=None):
        self.check_revision(expected_revision)
        if action == "choose_character":
            controls = await self.get_simulation_controls(story_id)
            if character_id not in {c["id"] for c in controls["eligible_characters"]}:
                raise ValueError("Character is not eligible")
            self.selected = character_id
        elif action == "branch":
            if snapshot_id != "snapshot-1":
                raise ValueError("Unknown snapshot")
            return {"story_id": "new-branch", "revision": 1}
        else:
            self.ended = True
        self.revision += 1
        return {"story_id": story_id, "revision": self.revision}


class SimulationApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = FakeSimulationEngine()
        self.engine_patch = patch.object(api, "engine", self.engine)
        self.engine_patch.start()
        self.adapter_patches = [patch.object(api, name, getattr(self.engine, method)) for name, method in (
            ("simulation_controls", "get_simulation_controls"), ("simulation_set_plot", "set_plot_guidance"),
            ("simulation_preview_locations", "preview_null_locations"), ("simulation_apply_locations", "apply_null_locations"),
            ("simulation_continue", "continue_failed_player"))]
        for adapter_patch in self.adapter_patches:
            adapter_patch.start()
        self.meta_patch = patch.object(api.db, "get_story_meta", AsyncMock(
            side_effect=lambda sid: SimpleNamespace(id=sid) if sid != "missing" else None))
        self.meta_patch.start()
        self.jobs_patch = patch.object(api, "jobs", {})
        self.jobs_patch.start()
        self.client = AsyncClient(transport=ASGITransport(app=api.app), base_url="http://test")
        self.base = "/api/stories/story/simulation"

    async def asyncTearDown(self):
        await self.client.aclose()
        self.jobs_patch.stop()
        self.meta_patch.stop()
        self.engine_patch.stop()
        for adapter_patch in reversed(self.adapter_patches):
            adapter_patch.stop()

    async def test_controls_only_public_options_not_omniscient_information(self):
        result = await self.client.get(self.base + "/controls")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["eligible_characters"], [{"id": "eligible", "name": "Known"}])
        self.assertEqual(result.json()["snapshots"], [{"id": "snapshot-1", "label": "Before failure"}])
        self.assertNotIn("must not leak", result.text)
        self.assertNotIn("secret plan", result.text)
        self.assertNotIn("Secret", result.text)

    async def test_all_presets_persist_and_stale_write_conflicts(self):
        for preset in ("adaptive", "balanced", "strong"):
            result = await self.client.post(self.base + "/plot-guidance", json={
                "preset": preset, "expected_revision": self.engine.revision})
            self.assertEqual(result.status_code, 200)
            self.assertEqual((await self.client.get(self.base + "/controls")).json()["plot_guidance"], preset)
        stale = await self.client.post(self.base + "/plot-guidance", json={"preset": "adaptive", "expected_revision": 7})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.engine.preset, "strong")
        invalid = await self.client.post(self.base + "/plot-guidance", json={"preset": "80%", "expected_revision": 10})
        self.assertEqual(invalid.status_code, 422)

    async def test_migration_is_preview_then_explicit_revision_checked_apply(self):
        preview = await self.client.get(self.base + "/null-locations")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(self.engine.migrated, {})
        request = {"expected_revision": 6, "selections": {"null": "room"}}
        self.assertEqual((await self.client.post(self.base + "/null-locations", json=request)).status_code, 409)
        self.assertEqual(self.engine.migrated, {})
        request["expected_revision"] = preview.json()["revision"]
        self.assertEqual((await self.client.post(self.base + "/null-locations", json=request)).status_code, 200)
        self.assertEqual(self.engine.migrated, {"null": "room"})
        self.assertEqual((await self.client.post(self.base + "/null-locations", json=request)).status_code, 409)

    async def test_null_hidden_out_of_scene_dead_player_selection_rejected(self):
        for character_id in ("null", "hidden", "away", "dead"):
            with self.subTest(character_id=character_id):
                result = await self.client.post(self.base + "/continuation", json={
                    "action": "choose_character", "character_id": character_id, "expected_revision": 7})
                self.assertEqual(result.status_code, 400)
                self.assertIsNone(self.engine.selected)
        result = await self.client.post(self.base + "/continuation", json={
            "action": "choose_character", "character_id": "eligible", "expected_revision": 7})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.engine.selected, "eligible")

    async def test_legacy_set_player_uses_same_safe_eligibility(self):
        setter = AsyncMock(return_value={"id": "eligible", "is_player_controlled": True})
        with patch.object(api.db, "set_player_character", setter), patch.object(api.db, "get_all_characters", AsyncMock(return_value=[])):
            for character_id in ("null", "hidden", "away", "dead"):
                result = await self.client.post(f"/api/stories/story/characters/{character_id}/set_player")
                self.assertEqual(result.status_code, 400)
            setter.assert_not_awaited()
            result = await self.client.post("/api/stories/story/characters/eligible/set_player")
            self.assertEqual(result.status_code, 200)
            setter.assert_awaited_once_with("story", "eligible")

    async def test_branch_does_not_change_original_and_end_is_revision_checked(self):
        result = await self.client.post(self.base + "/continuation", json={
            "action": "branch", "snapshot_id": "snapshot-1", "expected_revision": 7})
        self.assertEqual(result.json()["story_id"], "new-branch")
        self.assertEqual(self.engine.revision, 7)
        self.assertFalse(self.engine.ended)
        result = await self.client.post(self.base + "/continuation", json={"action": "end", "expected_revision": 7})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(self.engine.ended)
        self.assertEqual((await self.client.post(self.base + "/continuation", json={
            "action": "end", "expected_revision": 7})).status_code, 409)

    async def test_continuation_requires_failed_player_and_available_snapshot(self):
        controls = await self.engine.get_simulation_controls("story")
        controls["player_failed"] = False
        with patch.object(api, "simulation_controls", AsyncMock(return_value=controls)):
            response = await self.client.post(self.base + "/continuation", json={"action": "end", "expected_revision": 7})
            self.assertEqual(response.status_code, 409)
        self.assertFalse(self.engine.ended)
        response = await self.client.post(self.base + "/continuation", json={
            "action": "branch", "snapshot_id": "unavailable", "expected_revision": 7})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.engine.revision, 7)

    async def test_missing_story_busy_origin_and_action_payload_validation(self):
        self.assertEqual((await self.client.get("/api/stories/missing/simulation/controls")).status_code, 404)
        for request in ({"action": "branch", "expected_revision": 7},
                        {"action": "choose_character", "expected_revision": 7},
                        {"action": "end", "character_id": "eligible", "expected_revision": 7},
                        {"action": "end", "snapshot_id": "snapshot-1", "expected_revision": 7}):
            self.assertEqual((await self.client.post(self.base + "/continuation", json=request)).status_code, 422)
        payload = {"preset": "adaptive", "expected_revision": 7}
        response = await self.client.post(self.base + "/plot-guidance", json=payload,
                                          headers={"Origin": "https://outside.example"})
        self.assertEqual(response.status_code, 403)
        with patch.object(self.engine, "is_busy", return_value=True):
            self.assertEqual((await self.client.post(self.base + "/plot-guidance", json=payload)).status_code, 409)
        self.assertEqual(self.engine.preset, "balanced")

    async def test_character_visibility_editor_contract(self):
        updater = AsyncMock(return_value={"id": "eligible", "visibility_state": "hidden"})
        with patch.object(api.db, "update_character_details", updater), patch.object(api.db, "get_all_characters", AsyncMock(return_value=[])):
            response = await self.client.post("/api/stories/story/characters/eligible/update", json={"visibility_state": "hidden"})
            self.assertEqual(response.status_code, 200)
            updater.assert_awaited_once_with("story", "eligible", {"visibility_state": "hidden"})
            response = await self.client.post("/api/stories/story/characters/eligible/update", json={"visibility_state": "invisible-magic"})
            self.assertEqual(response.status_code, 422)

    async def test_conventional_advance_forwards_controls_and_conflict(self):
        self.engine.advance_turn = AsyncMock(return_value=SimpleNamespace(turn_index=1))
        request = {"mode": "simulation", "plot_guidance": "adaptive", "expected_revision": 7,
                   "decision_budget": 3, "extra_reaction_cycle": True}
        response = await self.client.post("/api/stories/story/advance", json=request)
        self.assertEqual(response.status_code, 200)
        kwargs = self.engine.advance_turn.await_args.kwargs
        for field in ("plot_guidance", "expected_revision", "decision_budget", "extra_reaction_cycle"):
            self.assertEqual(kwargs[field], request[field])
        self.engine.advance_turn.side_effect = api.turn_store.TurnConflictError("Stale revision")
        self.assertEqual((await self.client.post("/api/stories/story/advance", json=request)).status_code, 409)

    async def test_omitted_advance_controls_are_resolved_by_backend_not_reset_by_api(self):
        self.engine.advance_turn = AsyncMock(return_value=SimpleNamespace(turn_index=1))
        response = await self.client.post("/api/stories/story/advance", json={"mode": "simulation"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.engine.advance_turn.await_args.kwargs["plot_guidance"])
        self.assertIsNone(self.engine.advance_turn.await_args.kwargs["decision_budget"])

    async def test_decision_group_progress_keeps_single_extra_reaction_budget(self):
        async def stream(*args, **kwargs):
            self.assertEqual(args[-1], True)
            self.assertEqual(kwargs["plot_guidance"], "strong")
            self.assertEqual(kwargs["decision_budget"], 4)
            self.assertEqual(kwargs["expected_revision"], 7)
            yield {"type": "phase", "message": "Deciding", "group_index": 0,
                   "group_count": 2, "group_mode": "sequential"}
        self.engine.advance_turn_streaming = stream
        job = {"status": "running"}
        await api.run_turn_job("story", api.AdvanceStoryRequest(
            mode="simulation", extra_reaction_cycle=True, request_id="fake-request",
            plot_guidance="strong", decision_budget=4, expected_revision=7), job)
        self.assertEqual(len(job["progress"]), 1)
        self.assertEqual(job["progress"][0]["group_count"], 2)


class SimulationBackendIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import shutil
        from pathlib import Path
        from uuid import uuid4
        from core.types import Character, Scene, StoryMeta
        self.shutil = shutil
        self.root = Path(__file__).resolve().parent.parent / (".simulation-api-test-" + uuid4().hex)
        self.root.mkdir()
        self.addCleanup(self.shutil.rmtree, self.root)
        self.settings_patch = patch.object(api.settings, "STORIES_DIR", self.root)
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.jobs_patch = patch.object(api, "jobs", {})
        self.jobs_patch.start()
        self.addCleanup(self.jobs_patch.stop)
        self.sid = "isolated-simulation"
        self.base = f"/api/stories/{self.sid}/simulation"
        await api.db.save_story_meta(self.sid, StoryMeta(id=self.sid, title="Isolated test"))
        self.location = await api.db.ensure_location(self.sid, "Room")
        scene = Scene(location="Room", location_id=self.location, scene_goal="Test", active_character_ids=["player", "eligible", "null", "hidden", "away"])
        await api.db.create_scene(self.sid, scene)
        for character in (
            Character(age=25, id="player", name="Player", is_player_controlled=True, location_id=self.location),
            Character(age=25, id="eligible", name="Known", location_id=self.location),
            Character(age=25, id="null", name="Unknown", location_id=None),
            Character(age=25, id="hidden", name="Secret", location_id=self.location, visibility_state="hidden"),
            Character(age=25, id="away", name="Elsewhere", location_id=await api.db.ensure_location(self.sid, "Street")),
        ):
            await api.db.save_character(self.sid, character)
        self.client = AsyncClient(transport=ASGITransport(app=api.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_actual_backend_migration_visibility_and_selection(self):
        controls = (await self.client.get(self.base + "/controls")).json()
        self.assertEqual(controls["plot_guidance"], "balanced")
        self.assertEqual({c["id"] for c in controls["eligible_characters"]}, {"player", "eligible"})
        preview = await self.client.get(self.base + "/null-locations")
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIsNone((await api.db.get_character(self.sid, "null")).location_id)
        revision = preview.json()["revision"]
        result = await self.client.post(self.base + "/null-locations", json={"expected_revision": revision, "selections": {"null": self.location}})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual((await api.db.get_character(self.sid, "null")).location_id, self.location)
        self.assertGreater(result.json()["revision"], revision)
        self.assertEqual((await self.client.post(self.base + "/null-locations", json={"expected_revision": revision, "selections": {"null": self.location}})).status_code, 409)
        for identifier in ("hidden", "away"):
            self.assertEqual((await self.client.post(f"/api/stories/{self.sid}/characters/{identifier}/set_player")).status_code, 400)
        updated = await self.client.post(f"/api/stories/{self.sid}/characters/eligible/update", json={"visibility_state": "hidden"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual((await api.db.get_character(self.sid, "eligible")).visibility_state, "hidden")
        controls = (await self.client.get(self.base + "/controls")).json()
        saved = await self.client.put(self.base + "/plot-guidance", json={"preset": "strong", "expected_revision": controls["revision"]})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((await api.turn_store.get_runtime(self.sid))["plot_guidance"], "strong")
        stale = await self.client.put(self.base + "/plot-guidance", json={"preset": "adaptive", "expected_revision": controls["revision"]})
        self.assertEqual(stale.status_code, 409)
        advance = AsyncMock(return_value=SimpleNamespace(turn_index=1))
        with patch.object(api.engine, "advance_turn", advance):
            response = await self.client.post(f"/api/stories/{self.sid}/advance", json={"mode": "simulation"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(advance.await_args.kwargs["plot_guidance"])
        self.assertIsNone(advance.await_args.kwargs["decision_budget"])
        self.assertEqual((await api.turn_store.get_runtime(self.sid))["plot_guidance"], "strong")

    async def test_actual_put_plot_presets_persist_and_stale_revision_conflicts(self):
        controls = (await self.client.get(self.base + "/controls")).json()
        initial_revision = controls["revision"]
        for preset in ("adaptive", "balanced", "strong"):
            result = await self.client.put(self.base + "/plot-guidance", json={"preset": preset, "expected_revision": controls["revision"]})
            self.assertEqual(result.status_code, 200, result.text)
            controls = (await self.client.get(self.base + "/controls")).json()
            self.assertEqual(controls["plot_guidance"], preset)
            self.assertEqual((await api.turn_store.get_runtime(self.sid))["plot_guidance"], preset)
        stale = await self.client.put(self.base + "/plot-guidance", json={"preset": "adaptive", "expected_revision": initial_revision})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual((await api.turn_store.get_runtime(self.sid))["plot_guidance"], "strong")

    async def test_actual_end_and_retry_snapshot_preserve_original_history(self):
        import aiosqlite
        from core.types import SceneTurn
        async with aiosqlite.connect(api.db.get_db_path(self.sid)) as connection:
            before = await api.turn_store._capture_state(connection)
        scene = await api.db.get_active_scene(self.sid)
        turn_id = await api.db.add_scene_turn(self.sid, SceneTurn(scene_id=scene.id, turn_index=1, director_prose="The final turn."))
        async with aiosqlite.connect(api.db.get_db_path(self.sid)) as connection:
            after = await api.turn_store._capture_state(connection)
            await connection.execute("INSERT INTO turn_snapshots (turn_id, request_id, branch_id, before_json, after_json) VALUES (?, ?, 'main', ?, ?)",
                (turn_id, "isolated-snapshot", api.turn_store._encode_snapshot(before), api.turn_store._encode_snapshot(after)))
            await connection.commit()
        await api.db.update_character_details(self.sid, "player", {"status": "dead"})
        controls_response = await self.client.get(self.base + "/controls")
        self.assertEqual(controls_response.status_code, 200, controls_response.text)
        controls = controls_response.json()
        self.assertTrue(controls["player_failed"])
        self.assertTrue(controls["snapshots"])
        branch = await self.client.post(self.base + "/continuation", json={"action": "branch", "snapshot_id": controls["snapshots"][0]["id"], "expected_revision": controls["revision"]})
        self.assertEqual(branch.status_code, 200, branch.text)
        target = branch.json()["story_id"]
        self.assertNotEqual(target, self.sid)
        self.assertEqual((await api.db.get_character(self.sid, "player")).status, "dead")
        self.assertEqual((await api.db.get_character(target, "player")).status, "active")
        self.assertEqual(len(await api.db.get_all_story_turns(self.sid)), 1)
        self.assertEqual(len(await api.db.get_all_story_turns(target)), 0)
        self.assertEqual(await api.turn_store.get_revision(self.sid), controls["revision"])
        result = await self.client.post(self.base + "/continuation", json={"action": "end", "expected_revision": controls["revision"]})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue((await api.turn_store.get_runtime(self.sid))["ended"])
        self.assertGreater(result.json()["revision"], controls["revision"])


if __name__ == "__main__":
    unittest.main()
