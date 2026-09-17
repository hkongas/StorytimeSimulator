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

    async def test_existing_api_cycle(self):
        await test_api_endpoints()

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

    async def test_prompt_paths_reject_escape(self):
        response = await self.client.get("/api/prompts/content", params={"path": "../../config.py"})
        self.assertEqual(response.status_code, 400)

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
