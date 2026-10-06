import json
from typing import Dict, Any, List, Optional, AsyncIterator
from config import settings
from core.llm_client import LLMClient
from core.types import StoryMeta, Character, Scene, SceneTurn, ChronicleEntry
from core.schemas import StoryInitResponse, ResolverResponse, PlannerResponse, PlayerViewDraft, PlayerViewResponse, ContinuitySummary, CharacterCatchup, pydantic_to_json_schema
from core.prompt_loader import prompt_loader
from engine.turn_contract import merge_continuity
import database.db as db

class DirectorAgent:
    """Pääagentti (Ohjaaja / Kirjailija / Pelinjohtaja).
    
    Vastaa maailman luomisesta, juonikaaresta, aistisuodatuksesta,
    vuorojen koordinoinnista, proosan kirjoittamisesta ja valvojareflektiosta.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    async def initialize_story(
        self,
        story_id: str,
        title: str,
        genre: str,
        user_idea: str = "",
        player_char_name: Optional[str] = None,
        player_char_details: Optional[str] = None,
        custom_plot_idea: Optional[str] = None,
        tone_profile: str = "default",
        custom_tone_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Luo uuden tarinamaailman, salaisen juonisuunnitelman, alkuhahmot ja aloituskappaleen."""
        
        system_prompt = prompt_loader.compose_system_prompt(
            prompt_name="director/initialize_story",
            tone_profile=tone_profile,
            custom_tone_override=custom_tone_override
        )

        user_content = f"""
STORY TITLE: {title}
GENRE: {genre}
PREMISE / INSPIRATION: {user_idea or 'Create an original, immersive narrative premise.'}
"""
        if custom_plot_idea:
            user_content += f"\nDIRECTOR PLOT INTENT: {custom_plot_idea}\n"

        if player_char_name:
            user_content += f"\nPLAYER CHARACTER: Name '{player_char_name}', details: '{player_char_details or 'None specified'}'. Mark this character with 'is_player_controlled': true."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        init_schema = pydantic_to_json_schema(StoryInitResponse, "story_initialization")
        init_max_tokens = max(getattr(settings, "DIRECTOR_MAX_TOKENS", 8000), 8000)
        data = await self.llm.json_completion(
            messages=messages,
            role="director",
            temperature=settings.STORY_INIT_TEMPERATURE,
            reasoning_effort=settings.STORY_INIT_REASONING_EFFORT,
            max_tokens=init_max_tokens,
            timeout=240.0,
            json_schema=init_schema,
            story_id=story_id
        )

        # 1. Tallennetaan StoryMeta tietokantaan
        data = StoryInitResponse.model_validate(data).model_dump()
        meta = StoryMeta(
            id=story_id,
            title=title,
            genre=genre,
            world_lore=data.get("world_lore", ""),
            director_plot_arc=data.get("director_plot_arc", ""),
            director_notes=data.get("director_notes", ""),
            tone_profile=tone_profile,
            custom_tone_override=custom_tone_override or ""
        )
        await db.save_story_meta(story_id, meta)
        await db.save_story_bible(story_id, data["secret_truths"], data["clocks"], data["offscreen_agents"])

        # 2. Tallennetaan hahmot
        characters = []
        char_ids = []
        opening_location_id = await db.ensure_location(
            story_id, data["initial_scene"]["location"], data["initial_scene"].get("scene_goal", "")
        )
        for char_data in data.get("initial_characters", []):
            char_id = char_data.get("id") or char_data.get("name", "char").lower().replace(" ", "_")
            if len(char_id) > 80 or not all(character.isalnum() or character in "_-" for character in char_id):
                raise ValueError("Alustuksessa syntyi virheellinen hahmotunniste.")
            if not char_id or char_id in char_ids:
                raise ValueError("Alustuksessa syntyi päällekkäinen hahmotunniste.")
            is_player = char_data.get("is_player_controlled", False)
            if player_char_name and player_char_name.lower() in char_data.get("name", "").lower():
                is_player = True

            char = Character(
                id=char_id,
                name=char_data.get("name", "Tuntematon"),
                age=char_data.get("age", 25),
                gender=char_data.get("gender"),
                appearance=char_data.get("appearance", ""),
                personality=char_data.get("personality", ""),
                speech_style=char_data.get("speech_style", ""),
                values=char_data.get("values", ""),
                current_goal=char_data.get("current_goal", ""),
                fears=char_data.get("fears", ""),
                skills=char_data.get("skills", ""),
                limitations=char_data.get("limitations", ""),
                is_player_controlled=is_player,
                physical_state=char_data.get("physical_state", "Terve ja hyväkuntoinen"),
                mental_state=char_data.get("mental_state", "Rauhallinen ja tarkkaavainen"),
                secret_motive=char_data.get("secret_motive", ""),
                public_bio=char_data.get("public_bio", ""),
                tier=char_data.get("tier", "major"),
                known_locations=char_data.get("known_locations", []),
                location_id=opening_location_id
            )
            await db.save_character(story_id, char)
            characters.append(char)
            char_ids.append(char.id)

        relationships = data.get("initial_relationships", [])
        for relation in relationships:
            if relation["character_a"] not in char_ids or relation["character_b"] not in char_ids:
                raise ValueError("Alustuksen suhde viittaa virheelliseen hahmoon.")
            if relation["character_a"] == relation["character_b"]:
                raise ValueError("Alustuksen suhde viittaa virheelliseen hahmoon.")
        await db.save_relationships(story_id, relationships)
        items = data.get("initial_items", [])
        seen_item_ids = set()
        for item in items:
            if not item["id"] or len(item["id"]) > 80 or not all(char.isalnum() or char in "_-" for char in item["id"]):
                raise ValueError("Alustuksessa syntyi virheellinen esinetunniste.")
            if item["id"] in seen_item_ids or (item.get("holder_character_id") and item["holder_character_id"] not in char_ids):
                raise ValueError("Alustuksen esine viittaa virheelliseen tunnisteeseen.")
            if item.get("holder_character_id") and item.get("location_id"):
                raise ValueError("Esineellä voi olla joko hahmo tai sijainti, ei molempia.")
            if item.get("location_id") == data["initial_scene"]["location"]:
                item["location_id"] = opening_location_id
            if item.get("location_id") and item["location_id"] != opening_location_id:
                raise ValueError("Aloitusväline viittaa tuntemattomaan paikkaan.")
            seen_item_ids.add(item["id"])
            if not item.get("holder_character_id") and not item.get("location_id"):
                item["location_id"] = opening_location_id
        await db.save_items(story_id, items)

        # 3. Luodaan aloituskohtaus
        init_scene = data.get("initial_scene", {})
        scene = Scene(
            chapter_number=1,
            location=init_scene.get("location", "Tuntematon paikka"),
            scene_goal=init_scene.get("scene_goal", "Tarina alkaa"),
            active_character_ids=char_ids,
            is_active=True
        )
        scene_id = await db.create_scene(story_id, scene)
        scene.id = scene_id

        # 4. Tallennetaan aloitustarinavuoro
        opening_prose = init_scene.get("opening_prose", f"{title} alkaa...")
        first_turn = SceneTurn(
            scene_id=scene_id,
            turn_index=1,
            acting_character_id=None,
            perceived_context="Tarinan aloitushetki",
            internal_monologue="",
            character_action="",
            director_prose=opening_prose,
            choices=[
                "Tutki ympäristöä tarkemmin",
                "Keskustele läsnäolijoiden kanssa",
                "Ryhdy suoraan toimintaan"
            ],
            image_prompt=f"Cinematic atmospheric opening scene for {genre}, {init_scene.get('location', '')}, dramatic lighting, highly detailed novel illustration"
        )
        await db.add_scene_turn(story_id, first_turn)

        return {
            "meta": meta,
            "characters": characters,
            "scene": scene,
            "opening_prose": opening_prose,
            "choices": first_turn.choices,
            "image_prompt": first_turn.image_prompt,
            "events": init_scene.get("events", [])
        }

    async def create_perceptual_context(
        self,
        story_id: str,
        character: Character,
        scene: Scene,
        recent_prose: str,
        other_recent_actions: str,
        tone_profile: str = "default",
        custom_tone_override: Optional[str] = None
    ) -> str:
        """Suodattaa ja muodostaa aistisyötteen: mitä kyseinen hahmo näkee, kuulee ja tietää tässä hetkessä."""
        
        system_prompt = prompt_loader.compose_system_prompt(
            prompt_name="director/perceptual_filter",
            tone_profile=tone_profile,
            custom_tone_override=custom_tone_override,
            character_name=character.name
        )

        user_prompt = f"""
CHARACTER: {character.name} (Location: {scene.location})
RECENT SCENE PROSE CONTEXT:
{recent_prose}

RECENT ACTIONS / SPEECHES OF OTHER NEARBY CHARACTERS:
{other_recent_actions or 'No immediate preceding actions in this specific exchange.'}

Deliver the sensory perception briefing directly for '{character.name}'.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            return await self.llm.chat_completion(messages=messages, temperature=0.7, max_tokens=400, role="director", story_id=story_id)
        except Exception:
            return f"Olet tilassa {scene.location}. Havaitset ympärilläsi olevat hahmot ja tilanteen kehittyvän."

    async def ensure_story_bible(self, story_id, scene, characters):
        return await db.get_story_bible(story_id)

    async def plan_turn(self, story_id, scene, characters, runtime, mode, user_input, director_guidance, private_intention):
        meta = await db.get_story_meta(story_id)
        bible = await self.ensure_story_bible(story_id, scene, characters)
        system = prompt_loader.compose_system_prompt("director/plan_turn", tone_profile=meta.tone_profile,
                                                     custom_tone_override=meta.custom_tone_override)
        system += "\n" + prompt_loader.get_raw_prompt(f"director/mode_{mode}.txt")
        system += "\nPLANNER SCOPE: Mode governs control and pacing, not permission to act for characters. Only external world events occur here, before fresh decisions. Never execute user actions, private intentions, previous attempts, voluntary movement, speech, or mental decisions. The subsequent resolver handles fresh supplied intentions."
        no_progress = int(runtime.get("no_progress_beats", 0))
        world_state = await db.get_planning_world(story_id)
        if no_progress >= 2:
            system += "\nFORCED ADVANCE: The last two beats made no objective change. Prefer an established reveal or practical change to available options that lets characters complete their own goals next. Use only supported external causes; never invent an arbitrary hazard, execute previous intentions, or choose for a character. The subsequent resolver prioritizes completing fresh supplied intentions and routines."
        data = await self.llm.json_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps({
                "mode": mode, "user_input": user_input, "world_intervention": director_guidance,
                "player_private_intention": private_intention if mode == "roleplay" else None,
                "scene": scene.model_dump(exclude={"created_at"}),
                "characters": [character.model_dump(exclude={"created_at", "known_locations", "tier", "group_size_hint", "represents_group",
                                                               "secret_motive", "fears", "private_thought"})
                               | {"is_player_controlled": character.is_player_controlled if mode == "roleplay" else False}
                               for character in characters],
                "next_decision_candidates": runtime.get("decision_character_ids", []),
                "story_summary": runtime.get("summary", ""),
                "world_facts": runtime.get("world_facts", []),
                "plot_threads": runtime.get("plot_threads", []),
                "world": runtime.get("world_description") or meta.world_lore,
                "plot": runtime.get("director_plan") or meta.director_plot_arc,
                "truths": bible["secret_truths"],
                "clocks": bible["clocks"],
                "offscreen_agents": bible["offscreen_agents"],
                "items": world_state["items"],
                "relationships": world_state["relationships"],
                "locations": world_state["locations"],
                "no_progress_beats": no_progress
            }, ensure_ascii=False)}], role="director", story_id=story_id,
            temperature=settings.DIRECTOR_PLAN_TEMPERATURE,
            max_tokens=settings.DIRECTOR_PLAN_MAX_TOKENS,
            reasoning_effort=settings.DIRECTOR_PLAN_REASONING_EFFORT,
            json_schema=pydantic_to_json_schema(PlannerResponse, "turn_plan")
        )
        return PlannerResponse.model_validate(data)

    async def create_character_catchup(self, story_id: str, character: Character, meta: StoryMeta) -> dict:
        from database import turn_store
        memories = await db.get_character_memories(story_id, character.id, limit=30)
        intention = await turn_store.get_last_intention(story_id, character.id)
        data = {
            "character": {"name": character.name, "physical_state": character.physical_state,
                          "mental_state": character.mental_state},
            "memories": [{"type": memory.memory_type, "content": memory.content} for memory in memories],
            "observation": await turn_store.get_observation(story_id, character.id),
            "own_intention": {key: intention.get(key, "") for key in ("action", "speech", "private_thought")},
        }
        system = prompt_loader.compose_system_prompt("director/character_catchup", tone_profile=meta.tone_profile,
                                                     custom_tone_override=meta.custom_tone_override)
        result = await self.llm.json_completion(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
            role="director", story_id=story_id, temperature=settings.PLAYER_VIEW_TEMPERATURE,
            max_tokens=settings.PLAYER_VIEW_MAX_TOKENS, reasoning_effort=settings.PLAYER_VIEW_REASONING_EFFORT,
            json_schema=pydantic_to_json_schema(CharacterCatchup, "character_catchup"))
        return CharacterCatchup.model_validate(result).model_dump()

    async def create_player_view(self, story_id, character, outcome, intention, runtime, location, tone_profile,
                                 custom_tone_override, before_turn_id=None):
        from database import turn_store
        if before_turn_id is not None:
            snapshot = await turn_store.get_viewpoint_snapshot(story_id, before_turn_id, character.id)
            memories = [{"memory_type": memory.get("memory_type", "observation"),
                         "content": memory.get("content", "")}
                        for memory in snapshot.get("memories", [])[-20:]]
            observation = snapshot.get("observation", "Ei uusia havaintoja.")
        else:
            recalled = await db.get_relevant_memories(story_id, character.id, location, limit=20)
            memories = [{"memory_type": memory.memory_type, "content": memory.content}
                        for memory in recalled]
            observation = await turn_store.get_observation(story_id, character.id)
        previous_view = await turn_store.get_latest_player_view(story_id, character.id, before_turn_id)
        previous_view = previous_view or runtime.get("player_views", {}).get(character.id, {})
        system = prompt_loader.compose_system_prompt("director/player_view", tone_profile=tone_profile,
                                                     custom_tone_override=custom_tone_override)
        public_character = character.model_dump(exclude={"secret_motive", "values", "current_goal", "fears", "skills", "limitations",
                                                          "created_at", "known_locations", "tier", "represents_group", "group_size_hint"})
        perceived_events = []
        for event in outcome.events:
            if character.id in event.witnesses:
                perceived_events.append(event.observation_for(character.id))
        data = {"character": public_character, "location": location,
                "memories": memories,
                "previous_observation": observation,
                "perceived_events": perceived_events,
                "own_intention": intention,
                "previous_chapter_title": previous_view.get("chapter_title", "") if runtime.get("chapter_title") else ""}
        result = await self.llm.json_completion(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
            role="director", story_id=story_id, temperature=settings.PLAYER_VIEW_TEMPERATURE,
            max_tokens=settings.PLAYER_VIEW_MAX_TOKENS, reasoning_effort=settings.PLAYER_VIEW_REASONING_EFFORT,
            json_schema=pydantic_to_json_schema(PlayerViewDraft, "player_view"))
        if not result.get("prose"):
            result["prose"] = result.get("recap_delta") or " ".join(perceived_events)
        if not result.get("chapter_title"):
            result["chapter_title"] = previous_view.get("chapter_title") or runtime.get("chapter_title") or "Ensimmäinen luku"
        view = PlayerViewResponse.model_validate(result).model_dump()
        delta = view["recap_delta"]
        combined = "\n".join(part for part in (previous_view.get("recap", "").strip(), delta.strip()) if part)
        if len(combined) > 4000:
            recent = combined[-3000:]
            older = combined[:-3000][-997:]
            if " " in older:
                older = older[older.find(" ") + 1:]
            combined = f"{older}\n…\n{recent}" if older else recent
        view["recap_delta"] = delta
        view["recap"] = combined[:4000]
        if data["previous_chapter_title"]:
            view["chapter_title"] = data["previous_chapter_title"]
        return view

    async def synthesize_turn_prose(
        self,
        story_id: str,
        scene: Scene,
        all_character_intentions: List[Dict[str, Any]],
        recent_prose_context: str,
        director_guidance: Optional[str] = None,
        tone_profile: str = "default",
        custom_tone_override: Optional[str] = None,
        mode: str = "novel",
        reader_wish: Optional[str] = None,
        runtime: Optional[Dict[str, Any]] = None,
        characters: Optional[List[Character]] = None,
        player_character_id: Optional[str] = None,
        turn_plan: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Resolves canonical intentions and renders their consequences."""
        
        meta = await db.get_story_meta(story_id)
        runtime = runtime or {}
        continuity = {key: runtime[key] for key in (
            "summary", "world_facts", "plot_threads", "decision_character_ids", "chapter_title",
            "director_plan", "director_notes", "world_description", "no_progress_beats"
        ) if key in runtime}
        for key, initial in (
            ("world_description", meta.world_lore if meta else ""),
            ("director_plan", meta.director_plot_arc if meta else ""),
            ("director_notes", meta.director_notes if meta else "")
        ):
            continuity.setdefault(key, initial)
        if not continuity.get("summary"):
            chronicle = await db.get_chronicle(story_id)
            continuity["summary"] = "\n".join(c.summary for c in chronicle[-4:]) if chronicle else ""

        system_prompt = prompt_loader.compose_system_prompt(
            prompt_name="director/synthesize_prose",
            tone_profile=tone_profile,
            custom_tone_override=custom_tone_override,
            story_title=meta.title if meta else 'Tarina',
            story_genre=meta.genre if meta else 'Seikkailu'
        )
        system_prompt = system_prompt.split("RESPONSE SPECIFICATION:")[0] + "\nReturn the supplied schema with this turn's continuity delta only."
        system_prompt += "\n" + prompt_loader.get_language_directive()
        system_prompt += "\n" + prompt_loader.get_raw_prompt(f"director/mode_{mode}.txt")

        intentions = []
        for intention in all_character_intentions:
            attempt = {key: intention[key] for key in (
                "id", "character_id", "character_name", "goal", "time_horizon", "target", "volume", "if_interrupted"
            ) if key in intention}
            attempt.update(action=intention["action"], speech=intention.get("speech", ""))
            attempt["private_thought"] = intention.get("private_thought", "")
            intentions.append(attempt)
        intentions_block = json.dumps(intentions, ensure_ascii=False)

        user_content = f"""
[CURRENT SCENE]
Location: {scene.location}
Scene Goal / Tension: {scene.scene_goal}

[ENGINE MODE]
{mode}
Player character ID: {player_character_id or 'none'}
Reader wish: {reader_wish or 'none'}

[CUMULATIVE CONTINUITY STATE]
{json.dumps(continuity, ensure_ascii=False)}

[CHARACTER DOSSIERS - NARRATOR ONLY]
{json.dumps([character.model_dump(exclude={"created_at", "known_locations", "tier", "represents_group", "group_size_hint", "last_active_turn"}) | {"is_player_controlled": character.is_player_controlled if mode == "roleplay" else False} for character in (characters or [])], ensure_ascii=False)}

[ALL CHARACTERS' INTENTIONS & ATTEMPTS THIS MOMENT]
{intentions_block}

[RECENT PROSE TAIL - HISTORICAL STYLE / LOCAL CONTEXT, NOT NEW ATTEMPTS]
{recent_prose_context[-3000:]}
"""
        if director_guidance:
            user_content += f"\n[DIRECTOR OVERRIDE / GUIDANCE]: {director_guidance}\n"
        if turn_plan:
            user_content = "[ACCEPTED PRE-DECISION PLAN]\n" + json.dumps(turn_plan, ensure_ascii=False) + "\n" + user_content
            system_prompt += "\nThe plan's events already happened before character intentions. Do not repeat or undo them. Honor its direction and resolve only the subsequent actions."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        prose_schema = pydantic_to_json_schema(ResolverResponse, "prose_turn")
        messages[0]["content"] += (
            f"\n\nENGINE CONTRACT ({mode}): "
            "Return a schema-valid result and only new recap sentences, fact and thread additions/removals. "
            "Current continuity supersedes the initial plot or lore when events changed them. "
            "Events contain only observable descriptions and per-character observations, never private thoughts or director instructions. "
            "Empty observations are narrator-only facts. Do not grant offstage characters observations."
            " Put suggested choices exclusively in the choices array. Never append menus, numbered options or user instructions to prose."
        )
        if mode != "roleplay":
            messages[0]["content"] += " All characters are AI-controlled in this mode. Never wait for user input to supply a formerly player-controlled character's response."
        messages[0]["content"] += " The prose field is the narrator's omniscient reading version in ALL modes, including roleplay; a separate knowledge-limited player version is generated from perceived events only. Integrate supplied private thoughts selectively. Leave unchanged director_plan, director_notes and world_description empty; plans are revisable possibilities, never accomplished facts. Keep this chapter's title stable until chapter_end."
        data = await self.llm.json_completion(
            messages=messages, role="director", json_schema=prose_schema, story_id=story_id,
            temperature=settings.PROSE_TEMPERATURE, max_tokens=settings.PROSE_MAX_TOKENS,
            reasoning_effort=settings.PROSE_REASONING_EFFORT
        )
        resolved = ResolverResponse.model_validate(data)
        merged = merge_continuity(resolved, runtime)
        if len(merged["summary"]) > 4800:
            compressed = await self.llm.json_completion(
                messages=[{"role": "system", "content": "Compress the supplied narrator continuity history to at most 4000 characters in Finnish. Preserve consequential older events, identities, outcomes and unresolved causes. Do not invent events or add private thoughts. Return the supplied schema."},
                          {"role": "user", "content": merged["summary"]}],
                role="director", story_id=story_id, max_tokens=2200,
                json_schema=pydantic_to_json_schema(ContinuitySummary, "continuity_summary"))
            merged["summary"] = ContinuitySummary.model_validate(compressed).summary
        return resolved.model_dump() | merged

    async def check_narrative_watchdog(
        self,
        story_id: str,
        recent_chronicles: List[ChronicleEntry],
        recent_turns: List[SceneTurn]
    ) -> Optional[Dict[str, Any]]:
        """Tarkistaa onko tarina jumiutunut tai toistaako se samaa kaavaa."""
        if not recent_chronicles and not recent_turns:
            return None

        system_prompt = prompt_loader.compose_system_prompt("director/watchdog_reflection")

        summary_text = "\n".join([f"- Luku {c.chapter_index}: {c.summary}" for c in recent_chronicles[-5:]])
        recent_prose_snippets = "\n".join([f"Turn {t.turn_index}: {t.director_prose[:180]}..." for t in recent_turns[-4:]])

        user_content = f"""
RECENT CHRONICLE LOGS:
{summary_text}

RECENT PROSE TURNS:
{recent_prose_snippets}
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            result = await self.llm.json_completion(messages=messages, temperature=0.4, role="director", story_id=story_id)
            return result
        except Exception:
            return None
