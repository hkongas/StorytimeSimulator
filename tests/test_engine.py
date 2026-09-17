import asyncio
import os
import sys
import shutil
import tempfile
import unittest
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
                              reasoning_effort=None, timeout=180.0, role="director", json_schema=None, **kwargs):
        sys_msg = (messages[0]["content"] if messages else "").lower()

        schema_name = (json_schema or {}).get("json_schema", {}).get("name")
        if schema_name == "story_initialization":
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
                        "tier": "major",
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
                        "tier": "major",
                        "is_player_controlled": False
                    }
                ],
                "initial_scene": {
                    "location": "Vanha metsänreuna linnan raunioiden edustalla",
                    "scene_goal": "Hahmot kohtaavat raunioilla",
                    "opening_prose": "Yön hiljaisuus laskeutui metsän ylle kuin raskas samettiverho. Eerik seisoi raunioiden kynnyksellä ja katseli sumun halki kohoavia torneja."
                }
            }
        elif role == "character":
            return {
                "internal_monologue": "Mietin, kuka toinen liikkuu raunioilla näin myöhään...",
                "action_and_speech": "Eerik astuu esiin ja kuiskaa: 'Kuka siellä on?'",
                "updated_physical_state": "Valppaana, lihakset jännittyneinä",
                "updated_mental_state": "Varautunut ja jännittynyt",
                "new_memory": "Kohtasin toisen henkilön vanhoilla raunioilla sumuisena yönä."
            }
        elif schema_name == "prose_turn":
            return {
            "events": [{"description": "Eerik ja Mira kohtaavat raunioilla.", "witnesses": ["char_eerik", "char_mira"]}],
            "summary": "Eerik ja Mira ovat kohdanneet raunioilla.",
                "prose": "Eerikin ääni rikkoi yön hiljaisuuden vaimeana kaikuna. Varjojen keskeltä erottui nopea liike, kun Mira astui esiin kivipaaden takaa tikari valmiina kädessään.",
                "choices": [
                    "Kysy Miran aikeista raunioilla",
                    "Vedä oma aseesi esiin ja valmistaudu taisteluun",
                    "Ehdotat varovaista rauhaa ja jaettua nuotiota"
                ],
                "spawned_characters": [],
                "world_update": "Raunioiden ympäristössä liikkuu muitakin yöllisiä etsijöitä.",
                "plot_pivot_needed": False,
                "plot_pivot_note": "",
                "image_prompt": "Two mysterious figures in a foggy ancient forest ruins at night, dramatic lighting, fantasy oil painting"
            }
        elif "chronicler" in sys_msg or "summarize" in sys_msg:
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
            shutil.rmtree(item, ignore_errors=True)

    mock_llm = MockLLMClient()
    engine = StoryEngine(llm_client=mock_llm)

    # 1. Testataan uuden tarinan luonti
    print("1. Luodaan uusi tarina...")
    req = StoryInitRequest(
        title="Testitarina Varjoista",
        genre="Tumma Fantasia",
        user_idea="Kaksi seikkailijaa tapaa sumuisilla raunioilla",
        user_role="reader",
        tone_profile="gritty_realism"
    )
    init_res = await engine.initialize_new_story(req)
    story_id = init_res["story_id"]
    print(f"   -> Tarina luotu ID:llä: {story_id}")
    assert (settings.STORIES_DIR / story_id / "story.db").exists()
    assert (settings.STORIES_DIR / story_id / "story.txt").exists()
    assert (settings.STORIES_DIR / story_id / "story.md").exists()

    # 2. Tarkistetaan tietokanta ja hahmot
    print("2. Tarkistetaan tietokannan tila ja hahmot...")
    meta = await db.get_story_meta(story_id)
    assert meta is not None
    assert meta.title == "Testitarina Varjoista"
    assert meta.tone_profile == "gritty_realism"
    print(f"   -> Otsikko: {meta.title}, Genre: {meta.genre}, Sävy: {meta.tone_profile}")

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
    print(f"   -> Valintaehdotukset: {turn_res.choices}")
    assert len(turn_res.choices) >= 2

    # 4. Tarkistetaan muistivirta
    print("4. Tarkistetaan hahmon muistivirta...")
    char_id = characters[0].id
    memories = await db.get_character_memories(story_id, char_id)
    assert len(memories) >= 1
    print(f"   -> Hahmon {char_id} muisti: {memories[0].content}")

    # 5. Testataan streaming-silmukka
    print("5. Testataan advance_turn_streaming (WebSocket-logiikka)...")
    events = []
    async for event in engine.advance_turn_streaming(story_id=story_id, mode="reader"):
        events.append(event)
    
    phase_events = [e for e in events if e.get("type") == "phase"]
    assert len(phase_events) >= 2
    print(f"   -> Vastaanotettu {len(events)} streaming-tapahtumaa, vaiheet: {[p.get('phase') for p in phase_events]}")

    # Siivotaan testikansio
    test_auto_dir = settings.STORIES_DIR / story_id
    if test_auto_dir.exists():
        shutil.rmtree(test_auto_dir, ignore_errors=True)

    print("\n[OK] Kaikki testit läpäisty onnistuneesti!\n")

class ProviderTests(unittest.TestCase):
    def test_context_budget_prevents_oversized_request(self):
        with self.assertRaises(ValueError):
            LLMClient()._check_context([{"role": "user", "content": "x" * (settings.MAX_INPUT_TOKENS * 3 + 1)}])

    def test_response_usage_and_incomplete_json(self):
        from core.providers.xai_provider import XAIProvider
        from core.providers.base import TruncatedResponseError
        provider = XAIProvider(api_key="test")
        payload = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                   "usage": {"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 60}, "completion_tokens": 20, "total_tokens": 120}}
        self.assertEqual(provider._read_response(payload, "test-model", 1.5), "{}")
        self.assertEqual(provider.last_usage["cached_tokens"], 60)
        self.assertFalse(provider.last_usage["cost_known"])
        for invalid in ('{"prose": "incomplete', '[]'):
            with self.assertRaises(ValueError):
                provider._extract_json(invalid)
        payload["choices"][0]["finish_reason"] = "length"
        with self.assertRaises(TruncatedResponseError):
            provider._read_response(payload, "test-model", 1.5)


class RecordingLLM(MockLLMClient):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.invalid = False

    async def json_completion(self, messages, role="director", **kwargs):
        self.calls.append((role, messages))
        result = await super().json_completion(messages, role=role, **kwargs)
        if "prose" in result:
            if self.invalid:
                result["events"] = [{"description": "Invalid witness", "witnesses": ["absent"]}]
            result["character_state_updates"] = [{"character_id": "char_mira", "status": "unconscious"}]
        return result


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.original_dir = settings.STORIES_DIR
        settings.STORIES_DIR = Path(self.temporary.name)

    async def asyncTearDown(self):
        settings.STORIES_DIR = self.original_dir
        self.temporary.cleanup()

    async def test_story_paths_are_confined_and_reads_do_not_create(self):
        for invalid in ("..", "../outside", "C:\\outside", "a/b", "a\\b", ""):
            with self.assertRaises(ValueError):
                db.get_db_path(invalid)
        self.assertIsNone(await db.get_story_meta("missing"))
        self.assertFalse((settings.STORIES_DIR / "missing").exists())

    async def test_migration_is_repeatable(self):
        await db.save_story_meta("test", StoryMeta(id="test", title="Original"))
        await db.init_story_db("test")
        self.assertEqual((await db.get_story_meta("test")).title, "Original")

    async def test_legacy_migration_keeps_backup(self):
        import aiosqlite
        await db.save_story_meta("test", StoryMeta(id="test", title="Original"))
        async with aiosqlite.connect(db.get_db_path("test")) as connection:
            await connection.execute("PRAGMA user_version = 0")
        await db.init_story_db("test")
        self.assertTrue(db.get_db_path("test").with_suffix(".pre-v4.db").exists())
        self.assertEqual((await db.get_story_meta("test")).title, "Original")

    async def test_full_cycle_with_new_contract(self):
        await test_full_story_cycle()

    async def test_initial_observation_keeps_character_id(self):
        class HyphenModel(MockLLMClient):
            async def json_completion(self, *args, **kwargs):
                result = await super().json_completion(*args, **kwargs)
                if "initial_characters" in result:
                    result["initial_characters"][0]["id"] = "char-eerik"
                    result["initial_scene"]["events"] = [{"description": "A bell rings.", "witnesses": ["char-eerik"]}]
                return result
        from database import turn_store
        result = await StoryEngine(HyphenModel()).initialize_new_story(StoryInitRequest(title="Identifier test"))
        self.assertEqual(await turn_store.get_observation(result["story_id"], "char-eerik"), "A bell rings.")

    async def create_recorded_story(self):
        model = RecordingLLM()
        engine = StoryEngine(model)
        result = await engine.initialize_new_story(StoryInitRequest(title="Test"))
        model.calls.clear()
        return model, engine, result["story_id"]

    async def test_modes_information_boundaries_and_replay(self):
        model, engine, story_id = await self.create_recorded_story()
        scene = await db.get_active_scene(story_id)
        await db.add_scene_turn(story_id, SceneTurn(scene_id=scene.id, turn_index=2, director_prose="PRIVATE_PROSE_MARKER"))
        await engine.advance_turn(story_id, mode="simulation", director_guidance="SECRET_WORLD_COMMAND", request_id="sim")
        character_calls = [str(messages) for role, messages in model.calls if role == "character"]
        self.assertEqual(len(character_calls), 2)
        self.assertTrue(all("PRIVATE_PROSE_MARKER" not in messages and "SECRET_WORLD_COMMAND" not in messages for messages in character_calls))
        self.assertEqual((await db.get_character(story_id, "char_mira")).status, "unconscious")
        model.calls.clear()
        await engine.advance_turn(story_id, mode="novel", user_input="READER_WISH", request_id="novel")
        self.assertEqual([role for role, _ in model.calls], ["director"])
        self.assertIn("READER_WISH", str(model.calls))
        model.calls.clear()
        results = await asyncio.gather(*[engine.advance_turn(story_id, mode="novel", user_input="READER_WISH", request_id="novel") for _ in range(2)])
        self.assertEqual(results[0].turn_index, results[1].turn_index)
        self.assertEqual(model.calls, [])
        with self.assertRaises(ValueError):
            await engine.advance_turn(story_id, user_input="Different", request_id="novel")

    async def test_player_is_not_lost_among_many_characters(self):
        model, engine, story_id = await self.create_recorded_story()
        for index in range(6):
            await db.import_character_to_story(story_id, {"id": f"extra_{index}", "name": f"Extra {index}", "age": 30})
        await db.set_player_character(story_id, "extra_5")
        await engine.advance_turn(story_id, mode="roleplay", user_input="EXACT_PLAYER_ACTION", private_intention="PRIVATE_PLAYER_PLAN")
        director_messages = str([messages for role, messages in model.calls if role == "director"])
        self.assertIn("EXACT_PLAYER_ACTION", director_messages)
        self.assertIn("PRIVATE_PLAYER_PLAN", director_messages)
        character_calls = [str(messages) for role, messages in model.calls if role == "character"]
        self.assertEqual(len(character_calls), 7)
        self.assertTrue(all("PRIVATE_PLAYER_PLAN" not in messages for messages in character_calls))

    async def test_invalid_outcome_changes_nothing(self):
        model, engine, story_id = await self.create_recorded_story()
        model.invalid = True
        with self.assertRaises(ValueError):
            await engine.advance_turn(story_id)
        self.assertEqual(len(await db.get_all_story_turns(story_id)), 1)
        self.assertEqual((await db.get_character(story_id, "char_mira")).status, "active")
        self.assertEqual(await db.get_character_memories(story_id, "char_mira"), [])

    async def test_old_relevant_memory_survives_recency_window(self):
        await db.save_character("test", Character(id="actor", name="Actor", age=30))
        await db.add_character_memory("test", CharacterMemory(character_id="actor", content="Observatory: the key is hidden."))
        for index in range(25):
            await db.add_character_memory("test", CharacterMemory(character_id="actor", content=f"Routine event {index}"))
        memories = await db.get_relevant_memories("test", "actor", "Observatory", limit=10)
        self.assertTrue(any("Observatory" in memory.content for memory in memories))
        self.assertTrue(any("Routine event 24" in memory.content for memory in memories))

    async def test_edit_during_generation_is_not_overwritten(self):
        from database import turn_store
        model, engine, story_id = await self.create_recorded_story()
        original = model.json_completion
        async def edit_while_generating(*args, **kwargs):
            result = await original(*args, **kwargs)
            if "prose" in result:
                await db.update_character_state(story_id, "char_mira", "User edited state", "Alert")
            return result
        model.json_completion = edit_while_generating
        with self.assertRaises(turn_store.TurnConflictError):
            await engine.advance_turn(story_id)
        self.assertEqual((await db.get_character(story_id, "char_mira")).physical_state, "User edited state")
        self.assertEqual(len(await db.get_all_story_turns(story_id)), 1)

    async def test_atomic_turn_and_stale_write(self):
        from database import turn_store
        from core.schemas import ProseTurnResponse, StoryEvent
        from core.types import TurnResponse
        await db.save_story_meta("test", StoryMeta(id="test", title="Test"))
        character = Character(id="actor", name="Actor", age=30, status="unconscious")
        scene_id = await db.create_scene("test", Scene(location="Room", scene_goal="Test"))
        turn = SceneTurn(scene_id=scene_id, turn_index=1, director_prose="Prose")
        outcome = ProseTurnResponse(prose="Prose", summary="Summary", events=[StoryEvent(description="A bell rings.", witnesses=["actor"])], active_character_ids=[])
        response = TurnResponse(turn_index=1, director_prose="Prose", story_text_snippet="Prose", request_id="one")
        await turn_store.commit_turn("test", 0, turn, [character], outcome, response, "fingerprint", {})
        self.assertEqual((await db.get_character("test", "actor")).status, "unconscious")
        self.assertEqual(await turn_store.get_observation("test", "actor"), "A bell rings.")
        self.assertEqual((await turn_store.get_receipt("test", "one", "fingerprint")).turn_index, 1)
        character.status = "active"
        with self.assertRaises(turn_store.TurnConflictError):
            await turn_store.commit_turn("test", 0, turn, [character], outcome, response, "fingerprint", {})
        self.assertEqual((await db.get_character("test", "actor")).status, "unconscious")
        self.assertEqual(len(await db.get_all_story_turns("test")), 1)


if __name__ == "__main__":
    unittest.main()
