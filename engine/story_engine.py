import asyncio
import hashlib
import json
import shutil
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

from config import settings
from core.llm_client import LLMClient
from core.schemas import ProseTurnResponse
from core.prompt_loader import prompt_loader
from core.types import Character, SceneTurn, StoryInitRequest, TurnResponse, normalize_mode
from database import db, turn_store
from engine.character_agent import CharacterAgent
from engine.chronicle_manager import ChronicleManager
from engine.director_agent import DirectorAgent


class StoryEngine:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.director = DirectorAgent(self.llm)
        self.chronicle = ChronicleManager(self.llm)
        self._locks: dict[str, asyncio.Lock] = {}
        self.max_concurrent_characters = 5

    def is_busy(self, story_id: str | None = None) -> bool:
        if story_id is None:
            return any(lock.locked() for lock in self._locks.values())
        return story_id in self._locks and self._locks[story_id].locked()

    async def initialize_new_story(self, request: StoryInitRequest) -> dict[str, Any]:
        raw_id = request.title.lower().strip()
        safe_id = "".join(char if char.isalnum() else "_" for char in raw_id).strip("_")[:40] or "tarina"
        story_id = safe_id
        counter = 1
        while db.get_story_dir(story_id).exists():
            story_id = f"{safe_id}_{counter}"
            counter += 1
        directory = db.get_story_dir(story_id)
        directory.mkdir(parents=True, exist_ok=False)
        try:
            await db.init_story_db(story_id)
            mode = normalize_mode(request.user_role)
            result = await self.director.initialize_story(
                story_id=story_id, title=request.title, genre=request.genre or "Seikkailu",
                user_idea=request.user_idea or "",
                player_char_name=request.player_character_name if mode == "roleplay" else None,
                player_char_details=request.player_character_details if mode == "roleplay" else None,
                custom_plot_idea=request.custom_plot_idea,
                tone_profile=request.tone_profile or "default",
                custom_tone_override=request.custom_tone_override
            )
            events = result.get("events", [])
            if mode == "roleplay":
                player = next((character for character in result["characters"] if character.is_player_controlled), None)
                player = player or next(iter(result["characters"]), None)
                if player is None:
                    raise ValueError("Roolipeli tarvitsee pelaajahahmon.")
                await db.set_player_character(story_id, player.id)
                for character in result["characters"]:
                    character.is_player_controlled = character.id == player.id
            if any(not set(event["witnesses"]) <= {character.id for character in result["characters"]} for event in events):
                raise ValueError("Aloituskohtaus viittaa tuntemattomaan havaitsijaan.")
            observations = {
                character.id: "\n".join(event["description"] for event in events if character.id in event["witnesses"])
                or f"Olet paikassa {result['scene'].location}."
                for character in result["characters"]
            }
            await turn_store.seed_observations(story_id, observations)
            await turn_store.rebuild_exports(story_id)
            return {"story_id": story_id, **result, "mode": mode}
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    async def advance_turn_streaming(
        self, story_id: str, user_input: Optional[str] = None, mode: str = "novel",
        director_guidance: Optional[str] = None, private_intention: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AsyncIterator[dict[str, Any]]:
        db.get_story_dir(story_id)
        if mode == "director":
            director_guidance = director_guidance or user_input
            user_input = None
        mode = normalize_mode(mode)
        request_id = request_id or uuid4().hex
        fingerprint = hashlib.sha256(json.dumps([mode, user_input, director_guidance, private_intention], ensure_ascii=False).encode()).hexdigest()
        lock = self._locks.setdefault(story_id, asyncio.Lock())
        async with lock:
            if not db.get_db_path(story_id).exists():
                raise ValueError("Tarinaa ei löydy.")
            revision = await turn_store.get_revision(story_id)
            meta = await db.get_story_meta(story_id)
            if not meta:
                raise ValueError("Tarinaa ei löydy.")
            previous = await turn_store.get_receipt(story_id, request_id, fingerprint)
            if previous:
                yield {"type": "turn_complete", "data": previous.model_dump()}
                return
            yield {"type": "phase", "phase": "context_loading", "message": "Kootaan tilanne ja hahmojen havainnot..."}
            scene = await db.get_active_scene(story_id)
            if not scene or scene.id is None:
                raise ValueError("Tarinalta puuttuu aktiivinen kohtaus.")
            characters = await db.get_all_characters(story_id)
            roster = {character.id: character for character in characters}
            present = [character for character in characters if character.id in scene.active_character_ids and character.status == "active"]
            turns = await db.get_all_story_turns(story_id)
            last_id = max((turn.id or 0 for turn in turns), default=0)
            turn_index = max((turn.turn_index for turn in turns), default=0) + 1
            runtime = await turn_store.get_runtime(story_id)
            player = next((character for character in present if character.is_player_controlled), None)
            if mode == "roleplay" and player is None:
                raise ValueError("Valitse kohtauksessa oleva toimintakykyinen pelaajahahmo.")
            intentions = []
            if mode == "roleplay" and player:
                intentions.append({"character_id": player.id, "character_name": player.name,
                                   "action_and_speech": user_input or "Odotan ja tarkkailen.",
                                   "internal_monologue": private_intention or ""})
            decision_ids = set(runtime.get("decision_character_ids", []))
            acting = [character for character in present
                      if not (mode == "roleplay" and character.is_player_controlled)
                      and (mode != "novel" or character.id in decision_ids)]
            semaphore = asyncio.Semaphore(self.max_concurrent_characters)

            async def decide(character: Character):
                async with semaphore:
                    observation = await turn_store.get_observation(story_id, character.id)
                    decision = await CharacterAgent(character, self.llm).decide_intention(
                        story_id=story_id, scene_location=scene.location,
                        recent_prose_context=observation, tone_profile=meta.tone_profile,
                        custom_tone_override=meta.custom_tone_override
                    )
                    return {"character_id": character.id, "character_name": character.name, **decision}

            if acting:
                yield {"type": "phase", "phase": "characters_thinking", "message": f"Hahmot tekevät ratkaisujaan ({len(acting)})..."}
                decisions = await asyncio.gather(*(decide(character) for character in acting), return_exceptions=True)
                for decision in decisions:
                    if isinstance(decision, BaseException):
                        raise decision
                    intentions.append(decision)
            yield {"type": "phase", "phase": "prose_synthesis", "message": "Kertoja ratkaisee tapahtumat ja kirjoittaa jatkon..."}
            raw = await self.director.synthesize_turn_prose(
                story_id=story_id, scene=scene, all_character_intentions=intentions,
                recent_prose_context="\n\n".join(turn.director_prose for turn in turns[-3:])[-12000:],
                director_guidance=director_guidance, tone_profile=meta.tone_profile,
                custom_tone_override=meta.custom_tone_override, mode=mode,
                reader_wish=user_input if mode != "roleplay" else None,
                runtime=runtime, characters=characters,
                player_character_id=player.id if mode == "roleplay" and player else None
            )
            outcome = ProseTurnResponse.model_validate(raw)
            spawned = []
            for candidate in outcome.spawned_characters:
                if candidate.id in roster or not candidate.id or not all(char.isalnum() or char in "_-" for char in candidate.id):
                    raise ValueError("Kertoja palautti päällekkäisen tai virheellisen hahmotunnisteen.")
                character = Character(**candidate.model_dump(), status="active")
                character.is_player_controlled = False
                roster[character.id] = character
                spawned.append(character)
            allowed_witnesses = set(scene.active_character_ids) | {character.id for character in spawned}
            for event in outcome.events:
                if not set(event.witnesses) <= allowed_witnesses:
                    raise ValueError("Tapahtuman havaitsija ei ole kohtauksessa.")
            for update in outcome.character_state_updates:
                if update.character_id not in roster:
                    raise ValueError("Tilapäivitys viittaa tuntemattomaan hahmoon.")
                character = roster[update.character_id]
                for field in ("physical_state", "mental_state", "status"):
                    value = getattr(update, field)
                    if value is not None:
                        setattr(character, field, value)
            if outcome.active_character_ids is None:
                outcome.active_character_ids = list(scene.active_character_ids) + [character.id for character in spawned]
            if not set(outcome.active_character_ids) <= roster.keys() or not set(outcome.decision_character_ids) <= roster.keys():
                raise ValueError("Kertoja viittaa tuntemattomaan aktiiviseen hahmoon.")
            for intention in intentions:
                roster[intention["character_id"]].last_active_turn = turn_index
            action = "\n".join(f"[{intention['character_name']}]: {intention['action_and_speech']}" for intention in intentions)
            monologue = "\n".join(f"[{intention['character_name']}]: {intention['internal_monologue']}" for intention in intentions)
            response = TurnResponse(
                turn_index=turn_index, mode=mode, request_id=request_id,
                acting_character=player.model_dump() if mode == "roleplay" and player else None,
                internal_monologue=monologue, character_action=action, director_prose=outcome.prose,
                choices=outcome.choices, image_prompt=outcome.image_prompt,
                updated_characters=list(roster.values()), spawned_characters=spawned,
                story_text_snippet=outcome.prose, is_chapter_end=outcome.chapter_end
            )
            turn = SceneTurn(scene_id=scene.id, turn_index=turn_index,
                             acting_character_id=player.id if mode == "roleplay" and player else None,
                             internal_monologue=monologue, character_action=action,
                             director_prose=outcome.prose, choices=outcome.choices, image_prompt=outcome.image_prompt)
            await turn_store.commit_turn(story_id, last_id, turn, list(roster.values()), outcome, response, fingerprint,
                {"mode": mode, "user_input": user_input, "private_intention": private_intention,
                 "director_guidance": director_guidance, "director_model": settings.DIRECTOR_MODEL,
                 "character_model": settings.CHARACTER_MODEL, "intentions": intentions,
                 "contract_version": 1,
                 "prompt_hashes": {path: hashlib.sha256(prompt_loader.get_raw_prompt(path).encode()).hexdigest()
                    for path in ("director/synthesize_prose.txt", "character/decide_action.txt", "language_directive.txt", "safety_directive.txt", f"tone_profiles/{meta.tone_profile}.txt")}},
                expected_revision=revision)
            try:
                await turn_store.rebuild_exports(story_id)
            except OSError:
                response.warnings.append("Vuoro tallennettiin. Tekstivienti korjataan seuraavan viennin yhteydessä.")
            yield {"type": "turn_complete", "data": response.model_dump()}

    async def advance_turn(self, story_id: str, user_input: Optional[str] = None,
                           mode: str = "novel", director_guidance: Optional[str] = None,
                           private_intention: Optional[str] = None, request_id: Optional[str] = None) -> TurnResponse:
        async for event in self.advance_turn_streaming(story_id, user_input, mode, director_guidance, private_intention, request_id):
            if event["type"] == "turn_complete":
                return TurnResponse.model_validate(event["data"])
        raise RuntimeError("Vuoro ei valmistunut.")