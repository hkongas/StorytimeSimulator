import json
from typing import Dict, Any, List, Optional, AsyncIterator
from config import settings
from core.llm_client import LLMClient
from core.types import StoryMeta, Character, Scene, SceneTurn, ChronicleEntry
from core.schemas import StoryInitResponse, ProseTurnResponse, pydantic_to_json_schema
from core.prompt_loader import prompt_loader
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

        # 2. Tallennetaan hahmot
        characters = []
        char_ids = []
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
                is_player_controlled=is_player,
                physical_state=char_data.get("physical_state", "Terve ja hyväkuntoinen"),
                mental_state=char_data.get("mental_state", "Rauhallinen ja tarkkaavainen"),
                secret_motive=char_data.get("secret_motive", ""),
                public_bio=char_data.get("public_bio", ""),
                tier=char_data.get("tier", "major"),
                known_locations=char_data.get("known_locations", [])
            )
            await db.save_character(story_id, char)
            characters.append(char)
            char_ids.append(char.id)

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
        player_character_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Kirjoittaa monihahmoisista aikeista rikkaan suomenkielisen proosakappaleen.
        
        all_character_intentions: Lista dictionaryja, kukin sisältäen:
            - character_id: str
            - character_name: str
            - action_and_speech: str  (hahmon yritys/aie)
            - internal_monologue: str (hahmon sisäinen monologi)
        """
        
        meta = await db.get_story_meta(story_id)
        chronicle = await db.get_chronicle(story_id)
        chronicle_summary = "\n".join([f"- {c.summary}" for c in chronicle[-4:]]) if chronicle else "Tarina on alussa."

        system_prompt = prompt_loader.compose_system_prompt(
            prompt_name="director/synthesize_prose",
            tone_profile=tone_profile,
            custom_tone_override=custom_tone_override,
            story_title=meta.title if meta else 'Tarina',
            story_genre=meta.genre if meta else 'Seikkailu'
        )

        # Muodostetaan kaikkien hahmojen aikeet yhdeksi blokiksi
        intentions_block = ""
        for intention in all_character_intentions:
            char_name = intention.get("character_name", "Tuntematon")
            char_id = intention.get("character_id", "?")
            action = intention.get("action_and_speech", "")
            monologue = intention.get("internal_monologue", "")
            intentions_block += f"""
--- {char_name} (id: {char_id}) ---
Intention / Attempted Action & Speech:
{action}

Private Internal Monologue (for narrator's use only):
{monologue}
"""

        if not intentions_block.strip():
            intentions_block = "Maailma elää ja tapahtumat etenevät omalla painollaan."

        user_content = f"""
[CURRENT SCENE]
Location: {scene.location}
Scene Goal / Tension: {scene.scene_goal}

[WORLD LORE & CONTEXT]
{meta.world_lore if meta else ''}

[RECENT CHRONICLE SUMMARY]
{chronicle_summary}

[SECRET PLOT ARC TRAJECTORY]
{meta.director_plot_arc if meta else ''}

[DIRECTOR NOTES]
{meta.director_notes if meta else ''}

[ENGINE MODE]
{mode}
Player character ID: {player_character_id or 'none'}
Reader wish: {reader_wish or 'none'}

[CUMULATIVE CONTINUITY STATE]
{json.dumps(runtime or {}, ensure_ascii=False)}

[CHARACTER DOSSIERS - NARRATOR ONLY]
{json.dumps([character.model_dump() for character in (characters or [])], ensure_ascii=False)}

[ALL CHARACTERS' INTENTIONS & ATTEMPTS THIS MOMENT]
{intentions_block}

[PRECEDING STORY PROSE]
{recent_prose_context}
"""
        if director_guidance:
            user_content += f"\n[DIRECTOR OVERRIDE / GUIDANCE]: {director_guidance}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        prose_schema = pydantic_to_json_schema(ProseTurnResponse, "prose_turn")
        policies = {
            "novel": "Continue routine activity fluently. Stop before an important independent character decision and request it through decision_character_ids.",
            "simulation": "Resolve a meaningful situation from the supplied independent character intentions; avoid unnecessary round-robin speeches.",
            "roleplay": "Preserve the designated player's attempted action and private intention. Stop before choosing their next important action."
        }
        messages[0]["content"] += (
            f"\n\nENGINE CONTRACT ({mode}): {policies[mode]} "
            "Return a complete schema-valid result, cumulative summary, updated facts and unresolved threads. "
            "Current continuity supersedes the initial plot or lore when events changed them. "
            "Events contain only observable descriptions and explicit witness IDs, never private thoughts or director instructions. "
            "Empty witness lists are narrator-only facts. Do not grant offstage characters observations."
        )
        data = await self.llm.json_completion(
            messages=messages, role="director", json_schema=prose_schema, story_id=story_id
        )
        return ProseTurnResponse.model_validate(data).model_dump()

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
