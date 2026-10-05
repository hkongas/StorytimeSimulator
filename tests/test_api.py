import asyncio
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

# Lisätään projektin juuri polkuun
sys.path.insert(0, str(Path(__file__).parent.parent))

from httpx import AsyncClient, ASGITransport
from web.api import app, engine
from tests.test_engine import MockLLMClient
from config import settings

async def test_api_endpoints():
    print("\n--- Testataan FastAPI Web API -rajapinnat ---")
    
    # Asetetaan valemalli kaikkialle engineen
    mock_llm = MockLLMClient()
    engine.llm = mock_llm
    engine.director.llm = mock_llm
    engine.chronicle.llm = mock_llm
    # Päivitetään myös Director- ja Chronicle-agentin sisäiset LLM-viittaukset
    if hasattr(engine.director, 'llm'):
        engine.director.llm = mock_llm
    if hasattr(engine.chronicle, 'llm'):
        engine.chronicle.llm = mock_llm

    # Siivotaan vanhat testikansiot (kaikki tunnetut testitarinat)
    for pattern in ["api_testitarina*", "api_test*"]:
        for item in settings.STORIES_DIR.glob(pattern):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Testaa GET /api/settings
        res = await client.get("/api/settings")
        assert res.status_code == 200
        print("1. GET /api/settings OK:", res.json()["llm_provider"])

        # 2. Testaa POST /api/stories
        create_payload = {
            "title": "API Testitarina",
            "genre": "Kyberpunk",
            "user_idea": "Kyberetsivä tutkii kadonnutta tekoälyä neonvalaistussa kaupungissa.",
            "user_role": "reader"
        }
        res = await client.post("/api/stories", json=create_payload)
        assert res.status_code == 200
        data = res.json()["data"]
        story_id = data["story_id"]
        print(f"2. POST /api/stories OK: Luotu tarina '{story_id}'")

        # 3. Testaa GET /api/stories
        res = await client.get("/api/stories")
        assert res.status_code == 200
        stories = res.json()["stories"]
        assert any(s["id"] == story_id for s in stories)
        print("3. GET /api/stories OK: Tarina löytyi listasta.")

        # 4. Testaa GET /api/stories/{story_id}
        res = await client.get(f"/api/stories/{story_id}")
        assert res.status_code == 200
        story_details = res.json()
        assert len(story_details["characters"]) == 2
        print(f"4. GET /api/stories/{story_id} OK: {len(story_details['characters'])} hahmoa.")

        # 5. Testaa POST /api/stories/{story_id}/advance
        res = await client.post(f"/api/stories/{story_id}/advance", json={"mode": "reader"})
        assert res.status_code == 200
        turn_data = res.json()["data"]
        assert turn_data["turn_index"] == 2
        print(f"5. POST /api/stories/{story_id}/advance OK: Vuoro {turn_data['turn_index']} generoitu.")

        # 6. Testaa GET /api/stories/{story_id}/characters
        res = await client.get(f"/api/stories/{story_id}/characters")
        assert res.status_code == 200
        char_list = res.json()["characters"]
        assert len(char_list) >= 2
        print(f"6. GET /api/stories/{story_id}/characters OK: Muistit noudettu.")

        # 7. Testaa vienti GET /api/stories/{story_id}/export/txt
        res = await client.get(f"/api/stories/{story_id}/export/txt")
        assert res.status_code == 200
        assert len(res.text) > 100
        print("7. GET /api/stories/{story_id}/export/txt OK: Tiedosto ladattavissa.")

        # 8. Testaa Hahmon vienti: GET /api/stories/{story_id}/characters/{char_id}/export
        first_char_id = char_list[0]["character"]["id"]
        res = await client.get(f"/api/stories/{story_id}/characters/{first_char_id}/export?include_state=true&include_memories=true")
        assert res.status_code == 200
        card_data = res.json()
        assert card_data["format"] == "storytime_character"
        assert card_data["character"]["name"] is not None
        assert "state" in card_data
        print(f"8. GET .../characters/{first_char_id}/export OK: Hahmokortti viety.")

        # 9. Testaa Hahmon tuonti: POST /api/stories/{story_id}/characters/import
        import_payload = {
            "payload": {
                "character": {
                    "id": "char_vieras",
                    "name": "Korpivaeltaja Aarni",
                    "age": 35,
                    "gender": "Mies",
                    "appearance": "Harmaantunut parta, susiturkisviitta.",
                    "personality": "Hiljainen ja kokenut.",
                    "public_bio": "Pohjoisten rajaseutujen tuntija."
                },
                "state": {
                    "physical_state": "Väsynyt pitkästä matkasta",
                    "mental_state": "Varautunut",
                    "secret_motive": "Viedä varoitus etelään"
                },
                "memories": [
                    {
                        "memory_type": "observation",
                        "content": "Näin outoja valoja vuorten takana.",
                        "importance_score": 1.0
                    }
                ]
            },
            "include_state": True,
            "include_memories": True,
            "as_player": False
        }
        res = await client.post(f"/api/stories/{story_id}/characters/import", json=import_payload)
        assert res.status_code == 200
        imported_res = res.json()
        assert imported_res["character"]["name"] == "Korpivaeltaja Aarni"
        print("9. POST .../characters/import OK: Hahmo 'Korpivaeltaja Aarni' tuotu onnistuneesti.")

        # 10. Testaa Hahmon tietojen päivitys lennosta: POST .../update
        update_payload = {
            "physical_state": "Haavoittunut käteen",
            "mental_state": "Pelokas ja valpas"
        }
        res = await client.post(f"/api/stories/{story_id}/characters/{first_char_id}/update", json=update_payload)
        assert res.status_code == 200
        assert res.json()["character"]["physical_state"] == "Haavoittunut käteen"
        print(f"10. POST .../characters/{first_char_id}/update OK: Fyysinen tila päivitetty.")

        # 11. Testaa Pelaajahahmon asetus: POST .../set_player
        res = await client.post(f"/api/stories/{story_id}/characters/{first_char_id}/set_player")
        assert res.status_code == 200
        assert res.json()["character"]["is_player_controlled"] is True
        print(f"11. POST .../characters/{first_char_id}/set_player OK: Asetettu pelaajan hahmoksi.")

        # 12. Testaa Tarinan poisto: DELETE /api/stories/{story_id}
        res = await client.delete(f"/api/stories/{story_id}")
        assert res.status_code == 200
        assert not (settings.STORIES_DIR / story_id).exists()
        print(f"12. DELETE /api/stories/{story_id} OK: Tarina ja kansio poistettu.")

    print("\n[OK] Kaikki API-testit lapaisty onnistuneesti!\n")

class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.original_dir = settings.STORIES_DIR
        self.original_base = settings.BASE_DIR
        settings.STORIES_DIR = Path(self.temporary.name)
        settings.BASE_DIR = Path(self.temporary.name)
        import web.api as api
        api.jobs.clear()
        engine.llm = engine.director.llm = engine.chronicle.llm = MockLLMClient()
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        settings.STORIES_DIR = self.original_dir
        settings.BASE_DIR = self.original_base
        self.temporary.cleanup()

    async def test_api_log_content_endpoint(self):
        from database import db
        from unittest.mock import patch

        created = await self.client.post("/api/stories", json={"title": "Log content test"})
        story_id = created.json()["data"]["story_id"]
        with patch.object(settings, "LLM_CALL_CONTENT_LOGGING", True):
            await db.log_api_call(story_id, "director", "test-model", 0.1,
                                  prompt_data={"messages": [{"content": "private prompt"}]},
                                  response_data={"prose": "test response"})

        logs = await self.client.get(f"/api/stories/{story_id}/logs")
        self.assertEqual(logs.status_code, 200)
        log = logs.json()["logs"][0]
        self.assertNotIn("prompt_payload", log)
        self.assertNotIn("response_payload", log)
        content = await self.client.get(f"/api/stories/{story_id}/logs/{log['id']}")
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content.json()["prompt"]["messages"][0]["content"], "private prompt")
        self.assertEqual(content.json()["response"]["prose"], "test response")
        self.assertEqual((await self.client.get(f"/api/stories/{story_id}/logs/999999")).status_code, 404)

    async def test_existing_api_cycle(self):
        await test_api_endpoints()

    async def test_prose_editor_undo_and_conflicts(self):
        created = await self.client.post("/api/stories", json={"title": "Editor test"})
        story_id = created.json()["data"]["story_id"]
        endpoint = f"/api/stories/{story_id}"
        await engine.advance_turn(story_id, mode="novel", request_id="editor-turn")
        details = (await self.client.get(endpoint)).json()
        self.assertTrue(details["can_undo"])
        edit_endpoint = endpoint + f'/turns/{details["turns"][-1]["id"]}'
        payload = {"prose": "Edited <script>not executed</script>", "expected_revision": details["revision"]}
        self.assertEqual((await self.client.put(edit_endpoint, json={**payload, "sync_state": True})).status_code, 422)
        self.assertEqual((await self.client.put(edit_endpoint, json=payload)).status_code, 200)
        self.assertEqual((await self.client.put(edit_endpoint, json=payload)).status_code, 409)
        self.assertIn(payload["prose"], (await self.client.get(endpoint + "/export/txt")).text)
        details = (await self.client.get(endpoint)).json()
        undo = await self.client.post(endpoint + "/turns/undo", json={"expected_revision": details["revision"]})
        self.assertEqual(undo.status_code, 200)
        details = (await self.client.get(endpoint)).json()
        self.assertEqual(len(details["turns"]), 1)
        self.assertFalse(details["can_undo"])
        self.assertEqual((await self.client.get(endpoint + "/turn-jobs/editor-turn")).status_code, 409)
        self.assertEqual((await self.client.put("/api/stories/missing/turns/1", json=payload)).status_code, 404)

    async def test_authored_preview_and_accept_api(self):
        created = await self.client.post("/api/stories", json={"title": "Authored test"})
        story_id = created.json()["data"]["story_id"]
        endpoint = f"/api/stories/{story_id}"
        revision = (await self.client.get(endpoint)).json()["revision"]
        preview = await self.client.post(endpoint + "/authored-turns/preview", json={"prose": "A bell rang.", "expected_revision": revision})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(len((await self.client.get(endpoint)).json()["turns"]), 1)
        request = {"preview_id": preview.json()["preview_id"]}
        accepted = await self.client.post(endpoint + "/authored-turns/accept", json=request)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["data"]["director_prose"], "A bell rang.")
        self.assertEqual((await self.client.post(endpoint + "/authored-turns/accept", json=request)).status_code, 200)
        self.assertEqual(len((await self.client.get(endpoint)).json()["turns"]), 2)
        missing = await self.client.post(endpoint + "/authored-turns/accept", json={"preview_id": "0" * 32})
        self.assertEqual(missing.status_code, 409)

    async def test_gemini_profile_key_stays_server_side(self):
        from core.profile_store import load_profiles
        original_key = settings.GEMINI_API_KEY
        original_provider = settings.LLM_PROVIDER
        try:
            response = await self.client.post("/api/settings", json={
                "profile_id": "google", "llm_provider": "gemini", "gemini_api_key": "synthetic-gemini-value"
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(load_profiles()["google"]["gemini_api_key"], "synthetic-gemini-value")
            result = await self.client.get("/api/settings")
            self.assertTrue(result.json()["has_gemini_key"])
            self.assertNotIn("synthetic-gemini-value", result.text)
            await self.client.post("/api/settings", json={"profile_id": "google", "gemini_api_key": ""})
            self.assertEqual(settings.GEMINI_API_KEY, "synthetic-gemini-value")
        finally:
            settings.GEMINI_API_KEY = original_key
            settings.LLM_PROVIDER = original_provider

    async def test_background_job_replay_and_origin(self):
        import web.api as api
        created = await self.client.post("/api/stories", json={"title": "Job test"})
        story_id = created.json()["data"]["story_id"]
        endpoint = f"/api/stories/{story_id}/turn-jobs"
        request = {"mode": "novel", "request_id": "same-request"}
        response = await self.client.post(endpoint, json=request)
        self.assertEqual(response.status_code, 200)
        await asyncio.gather(*api.background_tasks)
        completed = await self.client.get(endpoint + "/same-request")
        self.assertEqual(completed.json()["status"], "completed")
        api.jobs.clear()
        replay = await self.client.get(endpoint + "/same-request")
        self.assertEqual(replay.json()["data"]["turn_index"], 2)
        blocked = await self.client.post(endpoint, json=request, headers={"Origin": "https://outside.example"})
        self.assertEqual(blocked.status_code, 403)

    async def test_sse_completed_job_replays_progress_and_result(self):
        import web.api as api
        created = await self.client.post("/api/stories", json={"title": "SSE test"})
        sid = created.json()["data"]["story_id"]
        endpoint = f"/api/stories/{sid}/turn-jobs"
        await self.client.post(endpoint, json={"mode": "simulation", "request_id": "sse-test"})
        await asyncio.gather(*api.background_tasks)
        result = await self.client.get(endpoint + "/sse-test/events")
        self.assertEqual(result.status_code, 200)
        self.assertIn("text/event-stream", result.headers["content-type"])
        self.assertIn("event: progress", result.text)
        self.assertIn("aie valmis", result.text)
        self.assertIn('"character_thought"', result.text)
        self.assertIn("event: result", result.text)
        self.assertIn('"status": "completed"', result.text)
        api.jobs.clear()
        recovered = await self.client.get(endpoint + "/sse-test/events")
        self.assertIn('"status": "completed"', recovered.text)

    async def test_roleplay_progress_hides_other_character_thoughts(self):
        import web.api as api
        created = await self.client.post("/api/stories", json={"title": "Private progress"})
        sid = created.json()["data"]["story_id"]
        await api.db.set_player_character(sid, "char_eerik")
        endpoint = f"/api/stories/{sid}/turn-jobs"
        await self.client.post(endpoint, json={"mode": "roleplay", "request_id": "private-progress"})
        await asyncio.gather(*api.background_tasks)
        phases = api.jobs[(sid, "private-progress")]["progress"]
        character_phases = [phase for phase in phases if phase.get("phase") == "character_complete"]
        self.assertTrue(character_phases)
        self.assertTrue(all("character_thought" not in phase for phase in phases))

    async def test_manual_director_edit_updates_runtime(self):
        created = await self.client.post("/api/stories", json={"title": "Director edit"})
        sid = created.json()["data"]["story_id"]
        endpoint = f"/api/stories/{sid}"
        result = await self.client.post(endpoint + "/meta", json={"director_plot_arc": "MANUAL_PLAN", "world_lore": "MANUAL_WORLD", "director_notes": "MANUAL_NOTES"})
        self.assertEqual(result.status_code, 200)
        details = (await self.client.get(endpoint)).json()
        self.assertEqual(details["runtime"]["director_plan"], "MANUAL_PLAN")
        self.assertEqual(details["runtime"]["world_description"], "MANUAL_WORLD")
        self.assertEqual(details["runtime"]["director_notes"], "MANUAL_NOTES")

    async def test_bible_is_returned_and_editable(self):
        created = await self.client.post("/api/stories", json={"title": "Bible edit"})
        sid = created.json()["data"]["story_id"]
        endpoint = f"/api/stories/{sid}"
        await engine.advance_turn(sid, mode="novel")
        details = (await self.client.get(endpoint)).json()
        bible = details["bible"]
        self.assertEqual(len(bible["secret_truths"]), 4)
        payload = {
            "secret_truths": [{**truth, "fact": "MUOKATTU" if index == 0 else truth["fact"],
                               "reveal_state": "revealed" if index == 0 else truth["reveal_state"]}
                              for index, truth in enumerate(bible["secret_truths"])],
            "clocks": [{**clock, "remaining_beats": 2} for clock in bible["clocks"]],
            "offscreen_agents": [{"id": "agent_1", "name": "Vartija", "goal": "Etsiä", "visible_to": ["char_eerik"]}],
            "expected_revision": details["revision"]
        }
        result = await self.client.put(endpoint + "/bible", json=payload)
        self.assertEqual(result.status_code, 200)
        saved = result.json()["bible"]
        self.assertEqual(saved["secret_truths"][0]["fact"], "MUOKATTU")
        self.assertEqual(saved["secret_truths"][0]["reveal_state"], "revealed")
        self.assertIsNotNone(saved["secret_truths"][0]["revealed_at_turn"])
        self.assertEqual(saved["clocks"][0]["remaining_beats"], 2)
        self.assertEqual(saved["offscreen_agents"][0]["visible_to"], ["char_eerik"])
        self.assertEqual((await self.client.put(endpoint + "/bible", json=payload)).status_code, 409)
        payload.pop("expected_revision")
        payload["offscreen_agents"][0]["visible_to"] = ["unknown"]
        self.assertEqual((await self.client.put(endpoint + "/bible", json=payload)).status_code, 400)
        payload["offscreen_agents"][0]["visible_to"] = []
        payload["clocks"] = payload["clocks"] * 2
        self.assertEqual((await self.client.put(endpoint + "/bible", json=payload)).status_code, 400)
        self.assertEqual((await self.client.put("/api/stories/missing/bible", json=payload)).status_code, 404)

    async def test_prompt_paths_reject_escape(self):
        response = await self.client.get("/api/prompts/content", params={"path": "../../config.py"})
        self.assertEqual(response.status_code, 400)

    async def test_completed_job_detects_missing_disk_turn(self):
        import web.api as api
        import aiosqlite
        from database import db
        created = await self.client.post("/api/stories", json={"title": "Missing turn test"})
        story_id = created.json()["data"]["story_id"]
        endpoint = f"/api/stories/{story_id}/turn-jobs"
        await self.client.post(endpoint, json={"mode": "novel", "request_id": "disk-check"})
        await asyncio.gather(*api.background_tasks)
        async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
            await connection.execute("DELETE FROM scene_turns WHERE id = (SELECT MAX(id) FROM scene_turns)")
            await connection.commit()
        result = await self.client.get(endpoint + "/disk-check")
        self.assertEqual(result.json()["status"], "failed")
        self.assertIn("levyltä", result.json()["message"])

    async def test_profile_secrets_are_not_returned(self):
        response = await self.client.post("/api/settings/profile-secrets", json={"profiles": [{"id": "first", "xai_api_key": "synthetic-test-value"}, {"id": "second", "azure_openai_api_key": "other-test-value"}]})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("synthetic-test-value", response.text)
        from core.profile_store import load_profiles
        self.assertEqual(load_profiles()["first"]["xai_api_key"], "synthetic-test-value")
        self.assertNotIn("synthetic-test-value", (await self.client.get("/api/settings")).text)
        response = await self.client.post("/api/prompts/save", json={"path": "../outside.txt", "content": "test"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
