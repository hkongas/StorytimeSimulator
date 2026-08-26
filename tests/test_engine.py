import asyncio
import os
import sys
import shutil
from pathlib import Path

# Lisätään projektin juuri polkuun
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings
from core.types import StoryInitRequest, AdvanceStoryRequest, Character, CharacterMemory, Scene, SceneTurn, StoryMeta
import database.db as db
from engine.story_engine import StoryEngine
from core.llm_client import LLMClient

class MockLLMClient(LLMClient):
    """Testivalemalli nopeaan automaattitestaukseen ilman verkkoliikennettä."""

    async def chat_completion(self, messages, model=None, temperature=None, max_tokens=None,
                              reasoning_effort=None, response_format=None, timeout=120.0, role="director"):
        return "Tämä on testisilmukan generoimaa kaunokirjallista tarinaproosaa. Kuun valo heijastuu puiden oksien läpi."

    async def json_completion(self, messages, model=None, temperature=None, max_tokens=None,
                              reasoning_effort=None, role="director"):
        content = messages[0]["content"] if messages else ""
        user_content = messages[1]["content"] if len(messages) > 1 else ""

        if "Pääagentin salainen juonisuunnitelma" in content or "initial_characters" in content:
            return {
                "world_lore": "Vanha valtakunta on varjojen peitossa ja muinaiset linnat seisovat usvan keskellä.",
                "director_plot_arc": "Sankarit löytävät salaisen riimukiven ja paljastavat hovin salajuonen.",
                "director_notes": "Tumma ja mystinen ilmapiiri.",
                "initial_characters": [
                    {
                        "id": "char_eerik",
                        "name": "Eerik Korvenhaltija",
                        "age": 29,
                        "gender": "Mies",
                        "appearance": "Pitkä, tummat hiukset ja vanha villaviitta.",
                        "personality": "Hiljainen, uskollinen ja valpas.",
                        "secret_motive": "Kostaa veljensä kohtalo.",
                        "public_bio": "Tunnetaan pohjoisen oppaana.",
                        "physical_state": "Terve",
                        "mental_state": "Valpas",
                        "is_player_controlled": False
                    },
                    {
                        "id": "char_mira",
                        "name": "Mira Varjokuiskaaja",
                        "age": 26,
                        "gender": "Nainen",
                        "appearance": "Harmaat silmät, nopea liikkumaan, kantaa tikaria.",
                        "personality": "Nokkela ja varovainen.",
                        "secret_motive": "Etsii kadonnutta kääröä.",
                        "public_bio": "Kaupungin varjoissa elävä tiedonvälittäjä.",
                        "physical_state": "Hyväkuntoinen",
                        "mental_state": "Utelias",
                        "is_player_controlled": False
                    }
                ],
                "initial_scene": {
                    "location": "Vanha metsänreuna linnan raunioiden edustalla",
                    "scene_goal": "Hahmot kohtaavat raunioilla",
                    "opening_prose": "Yön hiljaisuus laskeutui metsän ylle kuin raskas samettiverho. Eerik seisoi raunioiden kynnyksellä ja katseli sumun halki kohoavia torneja."
                }
            }
        elif "Sisäinen monologi" in content or "internal_monologue" in content:
            return {
                "internal_monologue": "Mietin, kuka toinen liikkuu raunioilla näin myöhään...",
                "action_and_speech": "Eerik astuu esiin ja kuiskaa: 'Kuka siellä on?'",
                "updated_physical_state": "Valppaana, lihakset jännittyneinä",
                "updated_mental_state": "Varautunut ja jännittynyt",
                "new_memory": "Kohtasin toisen henkilön vanhoilla raunioilla sumuisena yönä."
            }
        elif "mestarillinen kirjailija" in content or "plot_pivot_needed" in content:
            return {
                "prose": "Eerikin ääni rikkoi yön hiljaisuuden vaimeana kaikuna. Varjojen keskeltä erottui nopea liike, kun Mira astui esiin kivipaaden takaa tikari valmiina kädessään.",
                "world_update": "Raunioiden ympäristössä liikkuu muitakin yöllisiä etsijöitä.",
                "plot_pivot_needed": False,
                "plot_pivot_note": "",
                "image_prompt": "Two mysterious figures in a foggy ancient forest ruins at night, dramatic lighting, fantasy oil painting"
            }
        elif "tiivistää tarinan viimeisimmät tapahtumat" in content:
            return {
                "summary": "Eerik ja Mira kohtasivat raunioilla ja vaihtoivat ensimmäiset varovaiset sanansa.",
                "world_updates": "Raunioiden salaisuus herättää useamman osapuolen kiinnostuksen."
            }
        else:
            return {
                "summary": "Tarina eteni.",
                "world_updates": ""
            }

async def test_full_story_cycle():
    print("\n--- Aloitetaan Tarinamoottorin testit ---")
    
    # Siivotaan vanhat testikansiot
    for item in settings.STORIES_DIR.glob("testitarina_varjoista*"):
        if item.is_dir():
            shutil.rmtree(item)

    mock_llm = MockLLMClient()
    engine = StoryEngine(llm_client=mock_llm)

    # 1. Testataan uuden tarinan luonti
    print("1. Luodaan uusi tarina...")
    req = StoryInitRequest(
        title="Testitarina Varjoista",
        genre="Tumma Fantasia",
        user_idea="Kaksi seikkailijaa tapaa sumuisilla raunioilla",
        user_role="reader"
    )
    init_res = await engine.initialize_new_story(req)
    story_id = init_res["story_id"]
    print(f"   -> Tarina luotu ID:llä: {story_id}")
    assert (settings.STORIES_DIR / story_id / "story.db").exists()
    assert (settings.STORIES_DIR / story_id / "story.txt").exists()
    assert (settings.STORIES_DIR / story_id / "story.md").exists()

    # 2. Tarkistetaan tietokanta ja hahmot
    print("2. Tarkistetaan tietokannan tila ja hahmot...")
    print(f"   -> Haetaan story_id: '{story_id}' polusta: {db.get_db_path(story_id)}")
    meta = await db.get_story_meta(story_id)
    print(f"   -> get_story_meta tulos: {meta}")
    assert meta is not None
    assert meta.title == "Testitarina Varjoista"
    print(f"   -> Otsikko: {meta.title}, Genre: {meta.genre}")

    characters = await db.get_all_characters(story_id)
    assert len(characters) == 2
    print(f"   -> Hahmot luotu: {[c.name for c in characters]}")

    # 3. Testataan tarinavuoron edistäminen (Lukijatila)
    print("3. Ajetaan tarinavuoro (Lukijatila)...")
    turn_res = await engine.advance_turn(story_id=story_id, mode="reader")
    print(f"   -> Vuoro {turn_res.turn_index} valmis.")
    print(f"   -> Toimiva hahmo: {turn_res.acting_character['name'] if turn_res.acting_character else 'Maailma'}")
    print(f"   -> Sisäinen monologi: {turn_res.internal_monologue}")
    print(f"   -> Kirjamainen proosa: {turn_res.director_prose[:120]}...")
    print(f"   -> Kuvausprompti: {turn_res.image_prompt}")

    # 4. Tarkistetaan muistivirta
    print("4. Tarkistetaan hahmon muistivirta...")
    char_id = characters[0].id
    memories = await db.get_character_memories(story_id, char_id)
    assert len(memories) >= 1
    print(f"   -> Hahmon {char_id} muisti: {memories[0].content}")

    # 5. Tarkistetaan story.txt tiedosto
    print("5. Tarkistetaan story.txt tiedoston sisältö...")
    txt_content = (settings.STORIES_DIR / story_id / "story.txt").read_text(encoding="utf-8")
    assert len(txt_content) > 100
    print(f"   -> story.txt koko: {len(txt_content)} merkkiä.")

    # Siivotaan testikansio
    test_auto_dir = settings.STORIES_DIR / story_id
    if test_auto_dir.exists():
        shutil.rmtree(test_auto_dir, ignore_errors=True)

    print("\n[OK] Kaikki testit lapaisty onnistuneesti!\n")

if __name__ == "__main__":
    asyncio.run(test_full_story_cycle())
