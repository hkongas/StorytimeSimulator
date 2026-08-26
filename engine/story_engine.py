import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import settings
from core.types import StoryMeta, Character, Scene, SceneTurn, StoryInitRequest, TurnResponse
from engine.director_agent import DirectorAgent
from engine.character_agent import CharacterAgent
from engine.chronicle_manager import ChronicleManager
from core.llm_client import LLMClient
import database.db as db

class StoryEngine:
    """Tarinamoottorin ydin: orkestroidaan Pääagentti, Hahmoagentit ja tiedostojen tallennus."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.director = DirectorAgent(self.llm)
        self.chronicle = ChronicleManager(self.llm)

    def _get_story_dir(self, story_id: str) -> Path:
        story_dir = settings.STORIES_DIR / story_id
        story_dir.mkdir(parents=True, exist_ok=True)
        return story_dir

    def _append_to_story_files(self, story_id: str, prose_snippet: str, chapter_header: Optional[str] = None):
        """Kirjoittaa reaaliaikaisesti uutta tekstiä story.txt- ja story.md-tiedostoihin."""
        story_dir = self._get_story_dir(story_id)
        txt_path = story_dir / "story.txt"
        md_path = story_dir / "story.md"

        # Puhdas tekstitiedosto
        with open(txt_path, "a", encoding="utf-8") as f:
            if chapter_header:
                f.write(f"\n\n=== {chapter_header} ===\n\n")
            f.write(f"{prose_snippet.strip()}\n\n")

        # Markdown-tiedosto
        with open(md_path, "a", encoding="utf-8") as f:
            if chapter_header:
                f.write(f"\n\n# {chapter_header}\n\n")
            f.write(f"{prose_snippet.strip()}\n\n")

    async def initialize_new_story(self, request: StoryInitRequest) -> Dict[str, Any]:
        """Luo uuden tarinaprojektin ja alustaa maailman ja tiedostot."""
        # Luodaan turvallinen story_id otsikosta
        raw_id = request.title.lower().strip()
        safe_id = "".join([c if c.isalnum() else "_" for c in raw_id]).strip("_")[:40] or "tarina"
        
        # Varmistetaan uniikki ID
        counter = 1
        final_id = safe_id
        while (settings.STORIES_DIR / final_id).exists():
            final_id = f"{safe_id}_{counter}"
            counter += 1

        story_dir = self._get_story_dir(final_id)

        # 1. Alustetaan SQLite-tietokanta
        await db.init_story_db(final_id)

        # 2. Pyydetään Pääagentilta maailmanluonti
        init_data = await self.director.initialize_story(
            story_id=final_id,
            title=request.title,
            genre=request.genre or "Seikkailu",
            user_idea=request.user_idea or "",
            player_char_name=request.player_character_name if request.user_role == "player" else None,
            player_char_details=request.player_character_details if request.user_role == "player" else None,
            custom_plot_idea=request.custom_plot_idea
        )

        # 3. Luodaan aloitustiedostot
        meta = init_data["meta"]
        opening_prose = init_data["opening_prose"]

        # Alustetaan tiedostot otsikolla
        txt_path = story_dir / "story.txt"
        md_path = story_dir / "story.md"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"{meta.title}\nGenre: {meta.genre}\n{'='*len(meta.title)}\n\n{opening_prose}\n\n")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {meta.title}\n*Genre: {meta.genre}*\n\n---\n\n{opening_prose}\n\n")

        return {
            "story_id": final_id,
            "meta": meta,
            "characters": init_data["characters"],
            "scene": init_data["scene"],
            "opening_prose": opening_prose,
            "image_prompt": init_data.get("image_prompt")
        }

    async def advance_turn(
        self,
        story_id: str,
        user_input: Optional[str] = None,
        mode: str = "reader",
        director_guidance: Optional[str] = None
    ) -> TurnResponse:
        """Suorittaa yhden tarinavuoron (Pääagentti + Hahmoagentti + Proosasynteesi)."""
        
        # 1. Haetaan aktiivinen kohtaus ja hahmot
        active_scene = await db.get_active_scene(story_id)
        if not active_scene:
            # Luodaan oletuskohtaus jos ei ole
            active_scene = Scene(
                chapter_number=1,
                location="Tapahtumapaikka",
                scene_goal="Tarina jatkuu",
                active_character_ids=[],
                is_active=True
            )
            scene_id = await db.create_scene(story_id, active_scene)
            active_scene.id = scene_id

        all_characters = await db.get_all_characters(story_id)
        char_map = {c.id: c for c in all_characters}

        # 2. Haetaan aiemmat vuorot kontekstiksi
        recent_turns = await db.get_scene_turns(story_id, active_scene.id)
        turn_index = len(recent_turns) + 1
        recent_prose_list = [t.director_prose for t in recent_turns[-4:]]
        recent_prose_context = "\n\n".join(recent_prose_list)

        # 3. Valitaan vuorossa oleva hahmo
        acting_char: Optional[Character] = None
        player_instruction = None

        if mode == "player" and user_input:
            # Etsitään pelaajan ohjaama hahmo
            for char in all_characters:
                if char.is_player_controlled:
                    acting_char = char
                    player_instruction = user_input
                    break

        if not acting_char and all_characters:
            # Valitaan NPC vuoroon (vuorotellaan tai satunnaistetaan läsnäolijoiden kesken)
            if active_scene.active_character_ids:
                # Etsitään kuka ei ole toiminut viimeksi
                last_acting_id = recent_turns[-1].acting_character_id if recent_turns else None
                candidates = [c for c in all_characters if c.id in active_scene.active_character_ids and c.id != last_acting_id]
                acting_char = candidates[0] if candidates else all_characters[0]
            else:
                acting_char = all_characters[0]

        # 4. Hahmoagentin vuoro (jos hahmo löytyi)
        internal_monologue = ""
        action_and_speech = ""

        if acting_char:
            # Luodaan hahmolle aistikuvaus
            perceived_context = await self.director.create_perceptual_context(
                story_id=story_id,
                character=acting_char,
                scene=active_scene,
                recent_prose=recent_prose_context,
                other_recent_actions=recent_turns[-1].character_action if recent_turns else ""
            )

            # Ajetaan hahmoagentin päätöksenteko
            char_agent = CharacterAgent(acting_char, self.llm)
            decision = await char_agent.decide_action(
                story_id=story_id,
                scene_location=active_scene.location,
                perceived_context=perceived_context,
                director_nudge=director_guidance,
                player_instruction=player_instruction
            )

            internal_monologue = decision.get("internal_monologue", "")
            action_and_speech = decision.get("action_and_speech", "")
        else:
            # Maailmanlaajuinen tapahtuma ilman tiettyä hahmoa
            perceived_context = "Maailman tapahtumat etenevät."
            action_and_speech = user_input or "Aika kuluu ja ympäristössä tapahtuu muutos."

        # 5. Pääagentti kirjoittaa kaunokirjallisen proosakappaleen
        prose_result = await self.director.synthesize_turn_prose(
            story_id=story_id,
            scene=active_scene,
            acting_character=acting_char,
            action_and_speech=action_and_speech,
            internal_monologue=internal_monologue,
            recent_prose_context=recent_prose_context,
            director_guidance=director_guidance if mode == "director" else None
        )

        director_prose = prose_result.get("prose", action_and_speech)
        image_prompt = prose_result.get("image_prompt", "")

        # 6. Tallennetaan vuoro tietokantaan
        scene_turn = SceneTurn(
            scene_id=active_scene.id,
            turn_index=turn_index,
            acting_character_id=acting_char.id if acting_char else None,
            perceived_context=perceived_context,
            internal_monologue=internal_monologue,
            character_action=action_and_speech,
            director_prose=director_prose,
            image_prompt=image_prompt
        )
        await db.add_scene_turn(story_id, scene_turn)

        # 7. Kirjoitetaan lisäys story.txt ja story.md tiedostoihin
        self._append_to_story_files(story_id, director_prose)

        # 8. Tiivistys (Chronicle) säännöllisin väliajoin (esim. joka 4. vuoro)
        if turn_index % 4 == 0:
            all_scene_turns = await db.get_scene_turns(story_id, active_scene.id)
            await self.chronicle.summarize_scene_or_turns(
                story_id=story_id,
                chapter_index=active_scene.chapter_number,
                scene_index=active_scene.id,
                recent_turns=all_scene_turns[-4:]
            )

        # Haetaan päivitetyt hahmotiedot vastausta varten
        updated_characters = await db.get_all_characters(story_id)

        return TurnResponse(
            turn_index=turn_index,
            acting_character=acting_char.dict() if acting_char else None,
            internal_monologue=internal_monologue,
            character_action=action_and_speech,
            director_prose=director_prose,
            image_prompt=image_prompt,
            updated_characters=updated_characters,
            story_text_snippet=director_prose,
            is_chapter_end=False
        )
