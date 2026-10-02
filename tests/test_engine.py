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
                "secret_truths": [
                    {"id": "truth_ruin", "fact": "Raunioiden alla on vanha tunneli.", "discoverable_via": "Tutki kivipaaden alle."},
                    {"id": "truth_scroll", "fact": "Käärö oli viety vartijan torniin.", "discoverable_via": "Etsi tornin sinetti."},
                    {"id": "truth_brother", "fact": "Eerikin veli elää maanpaossa.", "discoverable_via": "Kohtaa pohjoinen viestinviejä."},
                    {"id": "truth_mist", "fact": "Sumu nousee raunioiden alla olevasta lähteestä.", "discoverable_via": "Seuraa veden ääntä."}
                ],
                "clocks": [{"id": "clock_patrol", "description": "Vartijat lähestyvät.", "remaining_beats": 5,
                            "on_expire_effect": "Vartijat saapuvat raunioille.", "visible": True}],
                "offscreen_agents": [],
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
        elif schema_name == "turn_plan":
            import json
            inputs = json.loads(messages[1]["content"])
            present = inputs["scene"]["active_character_ids"]
            capable = [character["id"] for character in inputs["characters"] if character["id"] in present and character["status"] == "active"
                   and not (inputs["mode"] == "roleplay" and character["is_player_controlled"])]
            decisions = capable if inputs["mode"] != "novel" else [identifier for identifier in capable if identifier in inputs.get("next_decision_candidates", [])]
            response = {"events": [], "active_character_ids": present, "decision_character_ids": decisions,
                "scene_goal": inputs["scene"]["scene_goal"], "direction": "Resolve the next meaningful beat."}
            if inputs.get("no_progress_beats", 0) >= 2:
                response["clock_ticks"] = [{"clock_id": inputs["clocks"][0]["id"], "amount": 1}]
            return response
        elif schema_name == "authored_reconciliation":
            return {
                "prose": "Model must not replace user prose", "summary": "A bell rang.",
                "events": [{"description": "A bell rings.", "witnesses": ["char_eerik"], "derived_from": "world"}],
                "world_facts": ["The bell has rung."], "plot_threads": [], "decision_character_ids": ["char_eerik"],
                "active_character_ids": ["char_eerik", "char_mira"],
                "character_state_updates": [{"character_id": "char_eerik", "mental_state": "Alert"}]
            }
        elif role == "character":
            return {
                "internal_monologue": "Mietin, kuka toinen liikkuu raunioilla näin myöhään...",
                "action_and_speech": "Eerik astuu esiin ja kuiskaa: 'Kuka siellä on?'",
                "updated_physical_state": "Valppaana, lihakset jännittyneinä",
                "updated_mental_state": "Varautunut ja jännittynyt",
                "new_memory": "Kohtasin toisen henkilön vanhoilla raunioilla sumuisena yönä."
            }
        elif schema_name == "player_view":
            return {"prose": "PRIVATE_VIEW_TEXT", "recap": "PRIVATE_VIEW_RECAP", "chapter_title": "Oma havainto", "choices": ["Tarkkaile"]}
        elif schema_name == "prose_turn":
            return {
            "events": [{"description": "Eerik ja Mira kohtaavat raunioilla.", "witnesses": ["char_eerik", "char_mira"], "derived_from": "consequence"}],
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
    def test_azure_completion_budget_ignores_deployment_alias(self):
        from core.providers import AzureProvider
        provider = AzureProvider("test", "https://example.services.ai.azure.com/openai/v1/")
        for model in ("gpt-6-luna", "my-writer-deployment", "gpt-4o"):
            payload = provider._build_payload([], model, 0.7, 32000, "medium", True)
            self.assertEqual(payload["max_completion_tokens"], 32000)
            self.assertNotIn("max_tokens", payload)
        payload = provider._build_payload([], "gpt-6-luna", 0.7, 32000, "medium", True)
        self.assertEqual(payload["temperature"], 1.0)
        self.assertEqual(payload["reasoning_effort"], "medium")
        self.assertEqual(provider._build_payload([], "gpt-4o", 0.7, 4000, None, False)["max_tokens"], 4000)

    def test_azure_endpoint_modes(self):
        from core.providers import AzureProvider
        provider = AzureProvider("test", "https://example.openai.azure.com/openai/v1/", deployment_name="ignored")
        endpoint, headers, v1 = provider._resolve_endpoint_and_headers("writer-deployment")
        self.assertEqual(endpoint, "https://example.openai.azure.com/openai/v1/chat/completions")
        self.assertTrue(v1)
        self.assertEqual(provider._build_payload([], "writer-deployment", 0.7, 100, None, v1)["model"], "writer-deployment")
        provider = AzureProvider("test", "https://example.openai.azure.com/", deployment_name="shared")
        self.assertIn("/deployments/shared/chat/completions?api-version=", provider._resolve_endpoint_and_headers("writer")[0])
        provider.deployment_name = ""
        self.assertIn("/deployments/writer/chat/completions?api-version=", provider._resolve_endpoint_and_headers("writer")[0])
        provider.base_url = "https://example.openai.azure.com/openai/deployments/writer"
        with self.assertRaises(ValueError):
            provider._resolve_endpoint_and_headers("writer")

    def test_gemini_payload_and_routing(self):
        from core.providers import GeminiProvider, OpenAIProvider
        provider = LLMClient(provider="gemini", api_key="test")._get_provider()
        self.assertIsInstance(provider, GeminiProvider)
        self.assertEqual(provider.base_url, "https://generativelanguage.googleapis.com/v1beta/openai")
        payload = provider._build_payload([], "gemini-2.5-flash-lite", 0.7, 1200, "none")
        self.assertEqual(payload["reasoning_effort"], "none")
        self.assertEqual(payload["max_tokens"], 1200)
        self.assertEqual(payload["temperature"], 0.7)
        with self.assertRaises(ValueError):
            provider._build_payload([], "gemini-2.5-pro", 0.7, 1200, "none")
        with self.assertRaises(ValueError):
            provider._build_payload([], "gemini-3.5-flash-lite", 0.7, 1200, "none")
        openai = OpenAIProvider("test")._build_payload([], "gpt-5", 0.7, 1200, "high")
        self.assertEqual(openai["max_completion_tokens"], 1200)
        self.assertEqual(openai["temperature"], 1.0)

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


class AzureTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_parameters_adapt_for_deployment_alias(self):
        import json
        import httpx
        from datetime import timedelta
        from unittest.mock import patch
        from core.providers import AzureProvider
        requests = []
        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if "max_tokens" in payload:
                return httpx.Response(400, json={"error": {"param": "max_tokens", "code": "unsupported_parameter",
                    "message": "Use max_completion_tokens instead."}})
            if "temperature" in payload:
                return httpx.Response(400, json={"error": {"param": "temperature", "code": "unsupported_value",
                    "message": "Only the default value is supported."}})
            response = httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]})
            response.elapsed = timedelta(milliseconds=10)
            return response
        client_type = httpx.AsyncClient
        def make_client(**kwargs):
            return client_type(transport=httpx.MockTransport(respond), **kwargs)
        provider = AzureProvider("test", "https://example.openai.azure.com/", deployment_name="writer-alias")
        with patch("core.providers.azure_provider.httpx.AsyncClient", side_effect=make_client):
            self.assertEqual(await provider.json_completion([], "writer-alias", max_tokens=32000), {})
        self.assertEqual(len(requests), 3)
        self.assertEqual(requests[-1]["max_completion_tokens"], 32000)
        self.assertNotIn("temperature", requests[-1])


class GeminiTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_usage_and_truncation(self):
        import json
        import httpx
        from datetime import timedelta
        from unittest.mock import patch
        from core.providers import GeminiProvider, TruncatedResponseError
        requests = []
        finish_reason = "stop"
        def respond(request):
            requests.append(json.loads(request.content))
            self.assertEqual(str(request.url), "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
            self.assertEqual(request.headers["authorization"], "Bearer test")
            response = httpx.Response(200, json={
                "choices": [{"finish_reason": finish_reason, "message": {"content": '{"action": "wait"}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                          "prompt_tokens_details": {"cached_tokens": 50}}
            })
            response.elapsed = timedelta(milliseconds=10)
            return response
        client_type = httpx.AsyncClient
        def make_client(**kwargs):
            return client_type(transport=httpx.MockTransport(respond), **kwargs)
        provider = GeminiProvider("test")
        schema = {"type": "json_schema", "json_schema": {"name": "action", "schema": {"type": "object"}}}
        with patch("core.providers.openai_provider.httpx.AsyncClient", side_effect=make_client):
            result = await provider.json_completion([], "gemini-2.5-flash-lite", max_tokens=1200, reasoning_effort="none", json_schema=schema)
            self.assertEqual(result, {"action": "wait"})
            self.assertEqual(requests[-1]["response_format"], schema)
            self.assertEqual(provider.last_usage["cached_tokens"], 50)
            self.assertFalse(provider.last_usage["cost_known"])
            finish_reason = "length"
            with self.assertRaises(TruncatedResponseError):
                await provider.json_completion([], "gemini-2.5-flash-lite")


class RecordingLLM(MockLLMClient):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.invalid = False

    async def json_completion(self, messages, role="director", **kwargs):
        self.calls.append((role, messages))
        result = await super().json_completion(messages, role=role, **kwargs)
        if "prose" in result and kwargs.get("json_schema", {}).get("json_schema", {}).get("name") != "authored_reconciliation":
            if self.invalid:
                result["events"] = [{"description": "Invalid witness", "witnesses": ["absent"], "derived_from": "consequence"}]
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

    async def test_api_logging_in_fresh_database(self):
        await db.log_api_call("test", "director", "azure-test", 0.1,
                              prompt_tokens=100, cached_tokens=50, cost_known=True, cost_usd=0.01)
        logs = await db.get_api_calls_for_story("test")
        self.assertEqual(logs[0]["cached_tokens"], 50)
        self.assertTrue(logs[0]["cost_known"])

    async def test_incomplete_schema_is_rejected_before_database_creation(self):
        from unittest.mock import patch, mock_open
        with patch("database.db.open", mock_open(read_data="CREATE TABLE story_meta (id TEXT);")):
            with self.assertRaisesRegex(ValueError, "skeematiedosto on puutteellinen"):
                await db.init_story_db("incomplete")
        self.assertFalse(db.get_db_path("incomplete").exists())

    async def test_current_version_repairs_missing_scenes_table(self):
        import aiosqlite
        await db.save_story_meta("test", StoryMeta(id="test", title="Original"))
        async with aiosqlite.connect(db.get_db_path("test")) as connection:
            await connection.execute("DROP TABLE scenes")
            await connection.commit()
        await db.init_story_db("test")
        scene_id = await db.create_scene("test", Scene(location="Room", scene_goal="Test"))
        self.assertIsNotNone(scene_id)
        self.assertTrue(db.get_db_path("test").with_suffix(".pre-v5.db").exists())
        self.assertEqual((await db.get_story_meta("test")).title, "Original")

    async def test_current_version_repairs_missing_log_columns(self):
        import aiosqlite
        await db.save_story_meta("test", StoryMeta(id="test", title="Original"))
        await db.log_api_call("test", "director", "azure-test", 0.1)
        async with aiosqlite.connect(db.get_db_path("test")) as connection:
            await connection.execute("ALTER TABLE api_calls DROP COLUMN cost_known")
            await connection.execute("ALTER TABLE api_calls DROP COLUMN cached_tokens")
            await connection.commit()
        await db.log_api_call("test", "director", "azure-test", 0.2,
                              cached_tokens=10, cost_known=False)
        self.assertTrue(db.get_db_path("test").with_suffix(".pre-v5.db").exists())
        logs = await db.get_api_calls_for_story("test")
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["cached_tokens"], 10)
        self.assertFalse(logs[0]["cost_known"])
        self.assertEqual((await db.get_story_meta("test")).title, "Original")
        await db.init_story_db("test")
        self.assertEqual(len(await db.get_api_calls_for_story("test")), 2)

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
                    result["initial_scene"]["events"] = [{"description": "A bell rings.", "witnesses": ["char-eerik"], "derived_from": "world"}]
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

    async def test_roleplay_opening_has_private_reading_view(self):
        from database import turn_store
        model = RecordingLLM()
        engine = StoryEngine(model)
        result = await engine.initialize_new_story(StoryInitRequest(title="Private opening", user_role="roleplay"))
        sid = result["story_id"]
        metadata = await turn_store.get_reading_metadata(sid)
        opening = next(iter(metadata.values()))
        self.assertEqual(opening["player_views"]["char_eerik"]["prose"], "PRIVATE_VIEW_TEXT")
        await engine.advance_turn(sid, mode="roleplay", user_input="Tarkkailen")
        self.assertEqual((await turn_store.get_reading_metadata(sid))[next(iter(metadata))], opening)

    async def test_editor_and_rollback_restore_state(self):
        from database import turn_store
        import aiosqlite
        model, engine, story_id = await self.create_recorded_story()
        async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
            before = await turn_store._capture_state(connection)
        await engine.advance_turn(story_id, mode="simulation", request_id="undo-test")
        turns = await db.get_all_story_turns(story_id)
        revision = await turn_store.get_revision(story_id)
        await turn_store.update_turn_prose(story_id, turns[-1].id, "Edited prose", revision)
        self.assertIn("Edited prose", (db.get_story_dir(story_id) / "story.md").read_text(encoding="utf-8"))
        with self.assertRaises(turn_store.TurnConflictError):
            await turn_store.update_turn_prose(story_id, turns[-1].id, "Stale", revision)
        await turn_store.rollback_last_turn(story_id, await turn_store.get_revision(story_id))
        async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
            self.assertEqual(await turn_store._capture_state(connection), before)
        self.assertEqual(len(await db.get_all_story_turns(story_id)), 1)
        with self.assertRaises(turn_store.TurnConflictError):
            await turn_store.get_receipt(story_id, "undo-test")
        with self.assertRaises(turn_store.TurnConflictError):
            await turn_store.rollback_last_turn(story_id, await turn_store.get_revision(story_id))

    async def test_undo_preserves_later_state_edits(self):
        from database import turn_store
        model, engine, story_id = await self.create_recorded_story()
        await engine.advance_turn(story_id)
        await db.update_character_state(story_id, "char_mira", "User edit", "Alert")
        with self.assertRaises(turn_store.TurnConflictError):
            await turn_store.rollback_last_turn(story_id, await turn_store.get_revision(story_id))
        self.assertFalse(await turn_store.can_rollback(story_id))
        self.assertEqual((await db.get_character(story_id, "char_mira")).physical_state, "User edit")

    async def test_editor_reaches_director_and_undo_restores_chapter(self):
        from database import turn_store
        model, engine, story_id = await self.create_recorded_story()
        original_scene = await db.get_active_scene(story_id)
        opening = (await db.get_all_story_turns(story_id))[-1]
        await turn_store.update_turn_prose(story_id, opening.id, "EDITED_CONTEXT_MARKER", await turn_store.get_revision(story_id))
        original = model.json_completion
        async def end_chapter(*args, **kwargs):
            result = await original(*args, **kwargs)
            if "prose" in result:
                result["chapter_end"] = True
            return result
        model.json_completion = end_chapter
        await engine.advance_turn(story_id, mode="simulation")
        director_calls = str([messages for role, messages in model.calls if role == "director"])
        self.assertIn("EDITED_CONTEXT_MARKER", director_calls)
        self.assertTrue(all("EDITED_CONTEXT_MARKER" not in str(messages) for role, messages in model.calls if role == "character"))
        self.assertNotEqual((await db.get_active_scene(story_id)).id, original_scene.id)
        await turn_store.rollback_last_turn(story_id, await turn_store.get_revision(story_id))
        self.assertEqual((await db.get_active_scene(story_id)).id, original_scene.id)
        self.assertEqual((await db.get_all_story_turns(story_id))[-1].director_prose, "EDITED_CONTEXT_MARKER")

    async def test_v4_editor_migration_keeps_backup(self):
        import aiosqlite
        await db.save_story_meta("test", StoryMeta(id="test", title="Original"))
        async with aiosqlite.connect(db.get_db_path("test")) as connection:
            await connection.execute("DROP TABLE turn_snapshots")
            await connection.execute("DROP TABLE prose_edits")
            await connection.execute("PRAGMA user_version = 4")
            await connection.commit()
        await db.init_story_db("test")
        self.assertTrue(db.get_db_path("test").with_suffix(".pre-v5.db").exists())
        async with aiosqlite.connect(db.get_db_path("test")) as connection:
            async with connection.execute("PRAGMA user_version") as cursor:
                self.assertEqual((await cursor.fetchone())[0], 6)
            await connection.execute("SELECT * FROM turn_snapshots")
        self.assertEqual((await db.get_story_meta("test")).title, "Original")

    async def test_authored_preview_acceptance_and_undo(self):
        from database import turn_store
        model, engine, story_id = await self.create_recorded_story()
        revision = await turn_store.get_revision(story_id)
        prose = "  The bell rang.\n\nEerik listened.  "
        preview = await engine.preview_authored_turn(story_id, prose, revision)
        self.assertEqual(await turn_store.get_revision(story_id), revision)
        self.assertEqual(len(await db.get_all_story_turns(story_id)), 1)
        self.assertEqual(await db.get_character_memories(story_id, "char_eerik"), [])
        response = await engine.accept_authored_turn(story_id, preview["preview_id"])
        self.assertEqual(response.director_prose, prose)
        self.assertEqual((await db.get_character(story_id, "char_eerik")).mental_state, "Alert")
        self.assertEqual(await turn_store.get_observation(story_id, "char_eerik"), "A bell rings.")
        self.assertNotIn("bell", await turn_store.get_observation(story_id, "char_mira"))
        self.assertEqual((await engine.accept_authored_turn(story_id, preview["preview_id"])).request_id, response.request_id)
        self.assertEqual(len(await db.get_all_story_turns(story_id)), 2)
        await turn_store.rollback_last_turn(story_id, await turn_store.get_revision(story_id))
        self.assertEqual(len(await db.get_all_story_turns(story_id)), 1)
        self.assertEqual(await db.get_character_memories(story_id, "char_eerik"), [])

    async def test_authored_preview_rejects_stale_acceptance(self):
        from database import turn_store
        model, engine, story_id = await self.create_recorded_story()
        preview = await engine.preview_authored_turn(story_id, "A bell rang.", await turn_store.get_revision(story_id))
        await db.update_character_state(story_id, "char_mira", "User edit", "Alert")
        with self.assertRaises(turn_store.TurnConflictError):
            await engine.accept_authored_turn(story_id, preview["preview_id"])
        self.assertEqual(len(await db.get_all_story_turns(story_id)), 1)

    async def test_authored_invalid_witness_changes_nothing(self):
        from database import turn_store
        model, engine, story_id = await self.create_recorded_story()
        original = model.json_completion
        async def invalid_witness(*args, **kwargs):
            result = await original(*args, **kwargs)
            result["events"] = [{"description": "A bell rings.", "witnesses": ["unknown"], "derived_from": "consequence"}]
            return result
        model.json_completion = invalid_witness
        revision = await turn_store.get_revision(story_id)
        with self.assertRaises(ValueError):
            await engine.preview_authored_turn(story_id, "A bell rang.", revision)
        self.assertEqual(await turn_store.get_revision(story_id), revision)
        self.assertEqual(engine.authored_previews, {})

    async def test_turn_recovery_journal_and_disk_verification(self):
        from database import turn_store
        import json
        import aiosqlite
        model, engine, story_id = await self.create_recorded_story()
        response = await engine.advance_turn(story_id, request_id="journal-test")
        directory = turn_store.get_recovery_dir(story_id)
        try:
            import hashlib
            journal_path = directory / f"{hashlib.sha256(response.request_id.encode()).hexdigest()}.json"
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(journal["response"]["request_id"], response.request_id)
            self.assertEqual(journal["outcome"]["prose"], response.director_prose)
            self.assertIn("events", journal["outcome"])
            await turn_store.verify_committed_turn(story_id, response)
            async with aiosqlite.connect(db.get_db_path(story_id)) as connection:
                await connection.execute("DELETE FROM scene_turns WHERE id = (SELECT MAX(id) FROM scene_turns)")
                await connection.commit()
            with self.assertRaises(turn_store.TurnConflictError):
                await turn_store.verify_committed_turn(story_id, response)
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    async def test_planning_observation_precedes_decision(self):
        from database import turn_store
        model, engine, story_id = await self.create_recorded_story()
        original = model.json_completion
        async def plan_changes(*args, **kwargs):
            result = await original(*args, **kwargs)
            if kwargs.get("json_schema", {}).get("json_schema", {}).get("name") == "turn_plan":
                result["events"] = [{"description": "VISIBLE_POWER_FAILURE", "witnesses": ["char_eerik"], "derived_from": "consequence"}]
                result["character_state_updates"] = [{"character_id": "char_mira", "status": "dead"}]
                result["decision_character_ids"] = ["char_eerik"]
                result["requires_player_input"] = True
            elif kwargs.get("json_schema", {}).get("json_schema", {}).get("name") == "prose_turn":
                result["character_state_updates"] = []
            return result
        model.json_completion = plan_changes
        response = await engine.advance_turn(story_id, mode="simulation", director_guidance="SECRET_OVERRIDE")
        character_calls = [str(messages) for role, messages in model.calls if role == "character"]
        self.assertEqual(len(character_calls), 1)
        self.assertIn("VISIBLE_POWER_FAILURE", character_calls[0])
        self.assertNotIn("SECRET_OVERRIDE", character_calls[0])
        self.assertTrue(response.requires_player_input)
        self.assertIn("VISIBLE_POWER_FAILURE", await turn_store.get_observation(story_id, "char_eerik"))

    async def test_private_intention_continuity_and_undo(self):
        from database import turn_store
        model, engine, sid = await self.create_recorded_story()
        original = model.json_completion
        generation = 1
        async def changing_intention(*args, **kwargs):
            result = await original(*args, **kwargs)
            if kwargs.get("role") == "character":
                result["internal_monologue"] = f"PRIVATE_THOUGHT_{generation}"
                result["action_and_speech"] = f"ATTEMPT_{generation}"
            return result
        model.json_completion = changing_intention
        await engine.advance_turn(sid, mode="simulation")
        previous = await turn_store.get_last_intention(sid, "char_eerik")
        self.assertEqual(previous["character_id"], "char_eerik")
        self.assertEqual(previous["internal_monologue"], "PRIVATE_THOUGHT_1")
        model.calls.clear()
        generation = 2
        await engine.advance_turn(sid, mode="simulation")
        latest = await turn_store.get_last_intention(sid, "char_eerik")
        self.assertEqual(latest["internal_monologue"], "PRIVATE_THOUGHT_2")
        self.assertEqual(latest["action_and_speech"], "ATTEMPT_2")
        planning = next(messages for role, messages in model.calls
                        if role == "director" and "previous_intentions" in messages[1]["content"])
        self.assertNotIn("PRIVATE_THOUGHT_1", planning[1]["content"])
        calls = [messages for role, messages in model.calls if role == "character"]
        self.assertIn("YOUR PREVIOUS PRIVATE THOUGHT AND ATTEMPT", str(calls))
        self.assertIn("PRIVATE_THOUGHT_1", str(calls))
        self.assertNotIn("PRIVATE_THOUGHT_2", str(calls))
        self.assertIn("not proof it succeeded", str(calls))
        self.assertEqual(calls[0][0]["content"], calls[-1][0]["content"])
        await turn_store.rollback_last_turn(sid, await turn_store.get_revision(sid))
        self.assertEqual(await turn_store.get_last_intention(sid, "char_eerik"), previous)

    async def test_invalid_plan_changes_nothing(self):
        from database import turn_store
        model, engine, story_id = await self.create_recorded_story()
        original = model.json_completion
        async def invalid_plan(*args, **kwargs):
            result = await original(*args, **kwargs)
            if kwargs.get("json_schema", {}).get("json_schema", {}).get("name") == "turn_plan":
                result["decision_character_ids"] = ["unknown"]
            return result
        model.json_completion = invalid_plan
        revision = await turn_store.get_revision(story_id)
        with self.assertRaises(ValueError):
            await engine.advance_turn(story_id)
        self.assertEqual(await turn_store.get_revision(story_id), revision)
        self.assertEqual(len(await db.get_all_story_turns(story_id)), 1)

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
        self.assertEqual([role for role, _ in model.calls], ["director", "director"])
        self.assertIn("READER_WISH", str(model.calls))
        model.calls.clear()
        results = await asyncio.gather(*[engine.advance_turn(story_id, mode="novel", user_input="READER_WISH", request_id="novel") for _ in range(2)])
        self.assertEqual(results[0].turn_index, results[1].turn_index)
        self.assertEqual(model.calls, [])
        with self.assertRaises(ValueError):
            await engine.advance_turn(story_id, user_input="Different", request_id="novel")

    async def test_reading_views_and_evolving_director_state(self):
        import json
        from database import turn_store
        model, engine, sid = await self.create_recorded_story()
        await db.set_player_character(sid, "char_eerik")
        original = model.json_completion
        async def evolving_state(*args, **kwargs):
            result = await original(*args, **kwargs)
            if kwargs.get("json_schema", {}).get("json_schema", {}).get("name") == "prose_turn":
                result.update(chapter_title="Kohtaaminen", director_plan="EVOLVING_PLAN", director_notes="CURRENT_NOTES",
                              world_description="CHANGED_WORLD", character_state_updates=[])
                result["events"] = [{"description": "VISIBLE_OUTCOME", "witnesses": ["char_eerik"], "derived_from": "consequence"},
                                    {"description": "SECRET_OFFSTAGE", "witnesses": [], "derived_from": "world"}]
            return result
        model.json_completion = evolving_state
        await engine.advance_turn(sid, mode="simulation")
        metadata = await turn_store.get_reading_metadata(sid)
        self.assertEqual(list(metadata.values())[-1]["chapter_title"], "Kohtaaminen")
        self.assertEqual(list(metadata.values())[-1]["player_views"]["char_eerik"]["prose"], "PRIVATE_VIEW_TEXT")
        player_call = next(messages for role, messages in model.calls if "perceived_events" in messages[1]["content"])
        self.assertIn("VISIBLE_OUTCOME", player_call[1]["content"])
        self.assertNotIn("SECRET_OFFSTAGE", player_call[1]["content"])
        self.assertNotIn("EVOLVING_PLAN", player_call[1]["content"])
        self.assertNotIn("char_mira", player_call[1]["content"])
        model.calls.clear()
        await engine.advance_turn(sid, mode="simulation")
        planning = next(messages for role, messages in model.calls if "previous_intentions" in messages[1]["content"])
        inputs = json.loads(planning[1]["content"])
        self.assertEqual(inputs["plot"], "EVOLVING_PLAN")
        self.assertNotIn("notes", inputs)
        self.assertEqual(inputs["world"], "CHANGED_WORLD")
        await turn_store.rollback_last_turn(sid, await turn_store.get_revision(sid))
        self.assertEqual(await turn_store.get_reading_metadata(sid), metadata)

    async def test_player_marker_only_limits_roleplay(self):
        import json
        model, engine, story_id = await self.create_recorded_story()
        await db.set_player_character(story_id, "char_eerik")
        original = model.json_completion
        async def omit_player(*args, **kwargs):
            result = await original(*args, **kwargs)
            schema = kwargs.get("json_schema", {}).get("json_schema", {}).get("name")
            if schema == "turn_plan":
                result["decision_character_ids"] = ["char_mira"]
            elif schema == "prose_turn":
                result["character_state_updates"] = []
            return result
        model.json_completion = omit_player
        await engine.advance_turn(story_id, mode="simulation")
        calls = [messages for role, messages in model.calls if role == "character"]
        self.assertEqual(len(calls), 2)
        profiles = [json.loads(messages[1]["content"].split("[YOUR PRIVATE CHARACTER PROFILE]\n", 1)[1].split("\n[YOUR RECALLED MEMORIES]", 1)[0]) for messages in calls]
        self.assertEqual({profile["id"] for profile in profiles}, {"char_eerik", "char_mira"})
        self.assertTrue(all(not profile["is_player_controlled"] for profile in profiles))
        self.assertTrue((await db.get_character(story_id, "char_eerik")).is_player_controlled)
        model.calls.clear()
        async def select_former_player(*args, **kwargs):
            result = await original(*args, **kwargs)
            if kwargs.get("json_schema", {}).get("json_schema", {}).get("name") == "turn_plan":
                result["decision_character_ids"] = ["char_eerik"]
            return result
        model.json_completion = select_former_player
        await engine.advance_turn(story_id, mode="novel")
        self.assertEqual(len([role for role, messages in model.calls if role == "character"]), 1)
        planning = next(messages for role, messages in model.calls if role == "director" and "previous_intentions" in messages[1]["content"])
        self.assertTrue(all(not character["is_player_controlled"] for character in json.loads(planning[1]["content"])["characters"]))
        synthesis = next(messages for role, messages in model.calls if role == "director" and "[CHARACTER DOSSIERS" in messages[1]["content"])
        self.assertIn("NEVER in prose", synthesis[0]["content"])

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
        outcome = ProseTurnResponse(prose="Prose", summary="Summary", events=[StoryEvent(description="A bell rings.", witnesses=["actor"], derived_from="world")], active_character_ids=[])
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
