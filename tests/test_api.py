import asyncio
import os
import sys
import shutil
from pathlib import Path

# Lisätään projektin juuri polkuun
sys.path.insert(0, str(Path(__file__).parent.parent))

from httpx import AsyncClient, ASGITransport
from web.api import app, engine
from tests.test_engine import MockLLMClient
from config import settings

async def test_api_endpoints():
    print("\n--- Testataan FastAPI Web API -rajapinnat ---")
    
    # Asetetaan valemalli engineen
    mock_llm = MockLLMClient()
    engine.llm = mock_llm
    engine.director.llm = mock_llm
    engine.chronicle.llm = mock_llm

    # Siivotaan vanhat testikansiot
    for item in settings.STORIES_DIR.glob("api_testitarina*"):
        if item.is_dir():
            shutil.rmtree(item)

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

    # Siivotaan
    for item in settings.STORIES_DIR.glob("api_testitarina*"):
        if item.is_dir():
            shutil.rmtree(item)

    print("\n[OK] Kaikki API-testit lapaisty onnistuneesti!\n")

if __name__ == "__main__":
    asyncio.run(test_api_endpoints())
