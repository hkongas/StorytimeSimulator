import asyncio
import hashlib
import json
import logging
import shutil
import time
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

from config import settings
from core.llm_client import LLMClient
from core.schemas import ProseTurnResponse, StoryEvent, pydantic_to_json_schema
from core.prompt_loader import prompt_loader
from core.types import Character, SceneTurn, StoryInitRequest, TurnResponse, normalize_mode
from database import db, turn_store
from engine.character_agent import CharacterAgent
from engine.chronicle_manager import ChronicleManager
from engine.director_agent import DirectorAgent

logger = logging.getLogger(__name__)


class StoryEngine:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.director = DirectorAgent(self.llm)
        self.chronicle = ChronicleManager(self.llm)
        self._locks: dict[str, asyncio.Lock] = {}
        self.max_concurrent_characters = 5
        self.authored_previews: dict[str, dict[str, Any]] = {}

    def is_busy(self, story_id: str | None = None) -> bool:
        if story_id is None:
            return any(lock.locked() for lock in self._locks.values())
        return story_id in self._locks and self._locks[story_id].locked()

    async def retry_player_view(self, story_id: str, turn_id: int, character_id: str) -> dict:
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            context = await turn_store.get_player_view_retry_context(story_id, turn_id, character_id)
            character = await db.get_character(story_id, character_id)
            if not character:
                raise ValueError("Hahmoa ei löydy.")
            outcome = ProseTurnResponse.model_validate(context["outcome"])
            intention = next((item for item in context["audit"].get("intentions", [])
                              if item.get("character_id") == character_id), {})
            meta = await db.get_story_meta(story_id)
            if not meta:
                raise ValueError("Tarinaa ei löydy.")
            view = await self.director.create_player_view(
                story_id, character, outcome, intention, await turn_store.get_runtime(story_id),
                context["location"], meta.tone_profile, meta.custom_tone_override,
                before_turn_id=turn_id
            )
            await turn_store.save_player_view(story_id, turn_id, character_id, view)
            receipt = await turn_store.get_receipt(story_id, context["request_id"])
            if receipt:
                receipt.player_view_status = "view_ready"
                receipt.warnings = [warning for warning in receipt.warnings if "näkökulma epäonnistui" not in warning]
                await turn_store.update_receipt_response(story_id, context["request_id"], receipt)
            return {"status": "view_ready", "player_view": view}

    async def preview_authored_turn(self, story_id: str, prose: str, expected_revision: int) -> dict[str, Any]:
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            revision = await turn_store.get_revision(story_id)
            if revision != expected_revision:
                raise turn_store.TurnConflictError("Tarina muuttui. Lataa se uudelleen ennen esikatselua.")
            meta = await db.get_story_meta(story_id)
            scene = await db.get_active_scene(story_id)
            if not meta or not scene or scene.id is None:
                raise ValueError("Tarinalta puuttuu aktiivinen kohtaus.")
            if not prose.strip() or len(prose) > 20000:
                raise ValueError("Oman jatkon pituuden on oltava 1–20 000 merkkiä.")
            characters = await db.get_all_characters(story_id)
            runtime = await turn_store.get_runtime(story_id)
            turns = await db.get_all_story_turns(story_id)
            system = prompt_loader.compose_system_prompt(
                "director/reconcile_authored", tone_profile=meta.tone_profile,
                custom_tone_override=meta.custom_tone_override
            )
            raw = await self.llm.json_completion(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps({
                    "world_lore": meta.world_lore, "scene": scene.model_dump(), "continuity": runtime,
                    "characters": [character.model_dump() for character in characters],
                    "preceding_prose": "\n\n".join(turn.director_prose for turn in turns[-3:])[-12000:],
                    "authored_prose": prose
                }, ensure_ascii=False)}], role="director", story_id=story_id,
                json_schema=pydantic_to_json_schema(ProseTurnResponse, "authored_reconciliation")
            )
            outcome = ProseTurnResponse.model_validate(raw)
            outcome.prose = prose
            outcome.choices = []
            outcome.image_prompt = ""
            roster = {character.id: character for character in characters}
            if outcome.spawned_characters:
                raise ValueError("Oman jatkon synkronointi ei vielä luo uusia hahmoja. Lisää hahmot ensin tarinaan.")
            for event in outcome.events:
                if not set(event.witnesses) <= roster.keys():
                    raise ValueError("Havainto viittaa tuntemattomaan hahmoon.")
            seen_updates = set()
            for update in outcome.character_state_updates:
                if update.character_id not in roster or update.character_id in seen_updates:
                    raise ValueError("Tilapäivityksessä on tuntematon tai toistuva hahmo.")
                seen_updates.add(update.character_id)
                for field in ("physical_state", "mental_state", "status"):
                    value = getattr(update, field)
                    if value is not None:
                        setattr(roster[update.character_id], field, value)
            if outcome.active_character_ids is None:
                outcome.active_character_ids = list(scene.active_character_ids)
            if not set(outcome.active_character_ids) <= roster.keys() or not set(outcome.decision_character_ids) <= roster.keys():
                raise ValueError("Jatko viittaa tuntemattomaan päätöksentekijään tai läsnäolijaan.")
            if revision != await turn_store.get_revision(story_id):
                raise turn_store.TurnConflictError("Tarina muuttui analyysin aikana. Muutoksia ei tallennettu.")
            player_views = {}
            viewpoint_character = next((character for character in await db.get_all_characters(story_id) if character.is_player_controlled), None)
            if viewpoint_character:
                player_views[viewpoint_character.id] = await self.director.create_player_view(
                    story_id, viewpoint_character, outcome, {}, runtime, scene.location,
                    meta.tone_profile, meta.custom_tone_override)
            now = time.monotonic()
            self.authored_previews = {identifier: preview for identifier, preview in self.authored_previews.items()
                                     if preview["expires"] > now and preview["story_id"] != story_id}
            if len(self.authored_previews) >= 100:
                raise ValueError("Liikaa avoimia esikatseluja. Sulje aiemmat esikatselut.")
            identifier = uuid4().hex
            self.authored_previews[identifier] = {
                "story_id": story_id, "revision": revision, "expires": now + 1800,
                "outcome": outcome, "characters": list(roster.values()), "scene": scene,
                "player_views": player_views,
                "last_id": max((turn.id or 0 for turn in turns), default=0),
                "turn_index": max((turn.turn_index for turn in turns), default=0) + 1,
                "mode": runtime.get("mode", "novel")
            }
            return {"preview_id": identifier, "revision": revision, "prose": prose,
                    "events": [event.model_dump() for event in outcome.events],
                    "character_updates": [update.model_dump() for update in outcome.character_state_updates],
                    "summary": outcome.summary, "world_facts": outcome.world_facts,
                    "plot_threads": outcome.plot_threads, "decision_character_ids": outcome.decision_character_ids,
                    "active_character_ids": outcome.active_character_ids, "scene_location": outcome.scene_location,
                    "scene_goal": outcome.scene_goal, "chapter_end": outcome.chapter_end}

    async def accept_authored_turn(self, story_id: str, preview_id: str) -> TurnResponse:
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            request_id = "authored_" + preview_id
            receipt = await turn_store.get_receipt(story_id, request_id)
            if receipt:
                return receipt
            preview = self.authored_previews.get(preview_id)
            if not preview or preview["story_id"] != story_id or preview["expires"] <= time.monotonic():
                raise turn_store.TurnConflictError("Esikatselu vanheni tai palvelin käynnistyi uudelleen. Analysoi teksti uudelleen.")
            outcome = preview["outcome"]
            response = TurnResponse(turn_index=preview["turn_index"], mode=preview["mode"], request_id=request_id,
                                    director_prose=outcome.prose, story_text_snippet=outcome.prose,
                                    updated_characters=preview["characters"], is_chapter_end=outcome.chapter_end)
            turn = SceneTurn(scene_id=preview["scene"].id, turn_index=preview["turn_index"],
                             director_prose=outcome.prose, character_action="Käyttäjän kirjoittama jatko")
            await turn_store.commit_turn(story_id, preview["last_id"], turn, preview["characters"], outcome, response,
                                         hashlib.sha256(outcome.prose.encode()).hexdigest(),
                                         {"source": "authored", "preview_id": preview_id, "player_views": preview["player_views"]}, expected_revision=preview["revision"])
            self.authored_previews.pop(preview_id, None)
            try:
                await turn_store.rebuild_exports(story_id)
            except OSError:
                response.warnings.append("Jatko tallennettiin, mutta tekstivienti epäonnistui.")
            return response

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
            events = [StoryEvent.model_validate(event) for event in result.get("events", [])]
            if mode == "roleplay":
                player = next((character for character in result["characters"] if character.is_player_controlled), None)
                player = player or next(iter(result["characters"]), None)
                if player is None:
                    raise ValueError("Roolipeli tarvitsee pelaajahahmon.")
                await db.set_player_character(story_id, player.id)
                for character in result["characters"]:
                    character.is_player_controlled = character.id == player.id
            if any(not set(event.witnesses) <= {character.id for character in result["characters"]} for event in events):
                raise ValueError("Aloituskohtaus viittaa tuntemattomaan havaitsijaan.")
            observations = {}
            for character in result["characters"]:
                perceived = []
                for event in events:
                    if character.id in event.witnesses:
                        detail = next((item for item in event.witness_details if item.character_id == character.id), None)
                        perceived.append(detail.perceived_text or detail.detail or event.description if detail else event.description)
                observations[character.id] = "\n".join(perceived) or f"Olet paikassa {result['scene'].location}."
            await turn_store.seed_observations(story_id, observations)
            opening_turn_id = max((turn.id or 0 for turn in await db.get_all_story_turns(story_id)), default=0)
            await turn_store.save_initial_events(story_id, opening_turn_id, events)
            player = next((character for character in result["characters"] if character.is_player_controlled), None)
            if player:
                opening_outcome = ProseTurnResponse(prose=result["opening_prose"], summary="Tarinan aloitus", events=events)
                view = await self.director.create_player_view(story_id, player, opening_outcome, {}, {},
                                                            result["scene"].location, request.tone_profile or "default", request.custom_tone_override)
                opening_turn = (await db.get_all_story_turns(story_id))[0]
                await turn_store.save_initial_reading(story_id, {str(opening_turn.id): {
                    "chapter_id": opening_turn.scene_id, "chapter_title": "", "recap": "", "player_views": {player.id: view}}})
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
            scene_location_id = db.location_identifier(scene.location)
            present = [character for character in characters if character.id in scene.active_character_ids
                       and character.status == "active" and character.location_id in {None, scene_location_id}]
            turns = await db.get_all_story_turns(story_id)
            last_id = max((turn.id or 0 for turn in turns), default=0)
            turn_index = max((turn.turn_index for turn in turns), default=0) + 1
            runtime = await turn_store.get_runtime(story_id)
            await self.director.ensure_story_bible(story_id, scene, characters)
            revision = await turn_store.get_revision(story_id)
            player = next((character for character in present if character.is_player_controlled), None)
            if mode == "roleplay" and player is None:
                raise ValueError("Valitse kohtauksessa oleva toimintakykyinen pelaajahahmo.")
            yield {"type": "phase", "phase": "turn_planning", "message": "Kertoja suunnittelee tilanteen ja hahmojen havainnot..."}
            plan = await self.director.plan_turn(story_id, scene, characters, runtime, mode,
                                                 user_input, director_guidance, private_intention)
            bible = await db.get_story_bible(story_id)
            truths = {truth["id"]: truth for truth in bible["secret_truths"]}
            clocks = {clock["id"]: clock for clock in bible["clocks"]}
            offscreen = {agent["id"]: agent for agent in bible["offscreen_agents"]}
            planned_progress = bool(
                plan.reveals or plan.clock_ticks or plan.offscreen_moves or plan.state_changes
                or plan.character_state_updates
                or (plan.scene_location and plan.scene_location != scene.location)
            )
            if runtime.get("no_progress_beats", 0) >= 2 and not planned_progress:
                raise ValueError("Pysähtynyttä tarinaa ei voi jatkaa ilman maailman etenemistä.")
            if len({reveal.truth_id for reveal in plan.reveals}) != len(plan.reveals):
                raise ValueError("Samaa salaisuutta ei voi paljastaa kahdesti samalla vuorolla.")
            reveal_events = []
            for reveal in plan.reveals:
                truth = truths.get(reveal.truth_id)
                if not truth:
                    raise ValueError("Suunnitelma viittaa tuntemattomaan salaiseen totuuteen.")
                next_state = {"hidden": "hinted", "hinted": "revealed", "revealed": "revealed"}[truth["reveal_state"]]
                reveal_events.append(StoryEvent(
                    description=(reveal.how if next_state == "hinted" else truth["fact"]),
                    witnesses=[character_id for character_id in scene.active_character_ids],
                    derived_from="world"
                ))
            requested_ticks = {}
            for tick in plan.clock_ticks:
                if tick.clock_id not in clocks:
                    raise ValueError("Suunnitelma viittaa tuntemattomaan kelloon.")
                requested_ticks[tick.clock_id] = requested_ticks.get(tick.clock_id, 0) + tick.amount
            for clock_id, clock in clocks.items():
                if clock["remaining_beats"] - 1 - requested_ticks.get(clock_id, 0) <= 0:
                    reveal_events.append(StoryEvent(
                        description=clock["on_expire_effect"] or clock["description"],
                        witnesses=list(scene.active_character_ids), derived_from="world"
                    ))
            for agent_id, move in plan.offscreen_moves.items():
                if agent_id not in offscreen:
                    raise ValueError("Suunnitelma viittaa tuntemattomaan sivuhenkilöön.")
                if move.strip():
                    reveal_events.append(StoryEvent(
                        description=move, witnesses=list(offscreen[agent_id]["visible_to"]), derived_from="world"
                    ))
            allowed_change_fields = {
                "character": {"location_id", "physical_state", "mental_state", "status"},
                "item": {"holder_character_id", "location_id", "state"},
                "relationship": {"attitude", "trust", "summary"},
            }
            for change in plan.state_changes:
                if change.entity not in allowed_change_fields or change.field not in allowed_change_fields[change.entity]:
                    raise ValueError("Suunnitelmassa on virheellinen tilamuutos.")
                if change.entity == "character":
                    if change.entity_id not in roster:
                        raise ValueError("Tilamuutos viittaa tuntemattomaan hahmoon.")
                    if change.field == "status" and change.value not in {"active", "unconscious", "dead", "inactive", "archived"}:
                        raise ValueError("Hahmon tilamuutos on virheellinen.")
                    if change.field != "status" and not isinstance(change.value, str):
                        raise ValueError("Hahmon tilamuutoksen arvon on oltava tekstiä.")
                    planned_location_id = db.location_identifier(plan.scene_location) if plan.scene_location else None
                    if change.field == "location_id" and str(change.value) != planned_location_id and not await db.location_exists(story_id, str(change.value)):
                        raise ValueError("Hahmon sijaintimuutos viittaa tuntemattomaan paikkaan.")
                    setattr(roster[change.entity_id], change.field, change.value)
                elif change.entity == "item":
                    item = await db.get_item(story_id, change.entity_id)
                    if not item:
                        raise ValueError("Tilamuutos viittaa tuntemattomaan esineeseen.")
                    if change.field == "holder_character_id" and change.value is not None and change.value not in scene.active_character_ids:
                        raise ValueError("Esine voidaan siirtää vain paikalla olevalle hahmolle.")
                    if change.field == "state" and not isinstance(change.value, str):
                        raise ValueError("Esineen tila on määritettävä tekstinä.")
                    if change.field in {"holder_character_id", "location_id"} and change.value is not None and not isinstance(change.value, str):
                        raise ValueError("Esineen tilamuutoksen arvon on oltava tekstiä.")
                    planned_location_id = db.location_identifier(plan.scene_location) if plan.scene_location else None
                    if change.field == "location_id" and str(change.value) != planned_location_id and not await db.location_exists(story_id, str(change.value)):
                        raise ValueError("Esineen sijaintimuutos viittaa tuntemattomaan paikkaan.")
                else:
                    relation_ids = change.entity_id.split("|", 1)
                    if len(relation_ids) != 2 or not await db.relationship_exists(story_id, *relation_ids):
                        raise ValueError("Tilamuutos viittaa tuntemattomaan suhteeseen.")
                    if change.field == "trust":
                        if not isinstance(change.value, (int, float)) or not -1 <= change.value <= 1:
                            raise ValueError("Suhteen luottamuksen on oltava välillä -1 ja 1.")
                    elif not isinstance(change.value, str):
                        raise ValueError("Suhteen muutosarvon on oltava tekstiä.")
            plan.events.extend(reveal_events)
            planned_spawned = []
            for candidate in plan.spawned_characters:
                if candidate.id in roster or not candidate.id or not all(char.isalnum() or char in "_-" for char in candidate.id):
                    raise ValueError("Suunnitelmassa on virheellinen uusi hahmo.")
                character = Character(**candidate.model_dump(), status="active")
                character.is_player_controlled = False
                character.location_id = db.location_identifier(plan.scene_location or scene.location)
                roster[character.id] = character
                planned_spawned.append(character)
            if not set(plan.active_character_ids) <= roster.keys():
                raise ValueError("Suunnitelmassa on tuntematon läsnäolija.")
            event_location_id = db.location_identifier(plan.scene_location or scene.location)
            if plan.scene_location and plan.scene_location != scene.location:
                for character_id in plan.active_character_ids:
                    if character_id in roster:
                        roster[character_id].location_id = event_location_id
            scene.active_character_ids = plan.active_character_ids
            scene.location = plan.scene_location or scene.location
            present_ids = {
                character.id for character in roster.values()
                if character.id in plan.active_character_ids
                and character.location_id in {None, event_location_id}
            }
            for event in plan.events:
                if not set(event.witnesses) <= roster.keys():
                    raise ValueError("Suunnitelman havaitsija ei ole tunnettu hahmo.")
                if not set(event.witnesses) <= present_ids:
                    logger.warning("Removed out-of-scene witnesses from planned event %s", event.id)
                    event.witnesses = list(dict.fromkeys(identifier for identifier in event.witnesses if identifier in present_ids))
                event.witness_details = [detail for detail in event.witness_details if detail.character_id in event.witnesses]
                event.derived_from = "world"
            updated_ids = set()
            for update in plan.character_state_updates:
                if update.character_id not in roster or update.character_id in updated_ids:
                    raise ValueError("Suunnitelmassa on virheellinen hahmopäivitys.")
                updated_ids.add(update.character_id)
                for field in ("physical_state", "mental_state", "status"):
                    value = getattr(update, field)
                    if value is not None:
                        setattr(roster[update.character_id], field, value)
            scene.scene_goal = plan.scene_goal
            characters = list(roster.values())
            present = [character for character in characters if character.id in scene.active_character_ids
                       and character.status == "active" and character.location_id in {None, event_location_id}]
            if not set(plan.decision_character_ids) <= {character.id for character in present}:
                raise ValueError("Suunnitelma pyytää päätöstä toimintakyvyttömältä hahmolta.")
            if mode == "roleplay" and player and player.id in plan.decision_character_ids:
                raise ValueError("Suunnitelma ei saa päättää pelaajan puolesta.")
            if mode == "simulation":
                plan.decision_character_ids = [character.id for character in present]
            intentions = []
            if mode == "roleplay" and player and player in present:
                intentions.append({"character_id": player.id, "character_name": player.name,
                                   "action_and_speech": user_input or "Odotan ja tarkkailen.",
                                   "internal_monologue": private_intention or ""})
            decision_ids = set(plan.decision_character_ids)
            acting = [character for character in present
                      if not (mode == "roleplay" and character.is_player_controlled)
                      and character.id in decision_ids]
            semaphore = asyncio.Semaphore(self.max_concurrent_characters)
            progress_queue = asyncio.Queue()

            async def decide(character: Character):
                async with semaphore:
                    observation = await turn_store.get_observation(story_id, character.id)
                    new_observations = [event.description for event in plan.events if character.id in event.witnesses]
                    if new_observations:
                        observation += "\n\n" + "\n".join(new_observations)
                    agent_character = character.model_copy(update={"is_player_controlled": False}) if mode != "roleplay" else character
                    decision = await CharacterAgent(agent_character, self.llm).decide_intention(
                        story_id=story_id, scene_location=scene.location,
                        recent_prose_context=observation, tone_profile=meta.tone_profile,
                        custom_tone_override=meta.custom_tone_override,
                        nearby_characters=[other.name for other in present if other.id != character.id]
                    )
                    progress = {"character_id": character.id, "character_name": character.name}
                    if mode != "roleplay":
                        progress["character_thought"] = decision["internal_monologue"]
                    progress_queue.put_nowait(progress)
                    return {"character_id": character.id, "character_name": character.name, **decision}

            if acting:
                yield {"type": "phase", "phase": "characters_thinking", "message": f"Hahmot tekevät ratkaisujaan ({len(acting)})..."}
                tasks = [asyncio.create_task(decide(character)) for character in acting]
                completed_count = 0
                try:
                    while not all(task.done() for task in tasks):
                        try:
                            progress = await asyncio.wait_for(progress_queue.get(), timeout=0.2)
                            completed_count += 1
                            yield {"type": "phase", "phase": "character_complete", "message": f"{progress['character_name']}: aie valmis ({completed_count}/{len(acting)})", **progress}
                        except asyncio.TimeoutError:
                            pass
                    while not progress_queue.empty():
                        progress = progress_queue.get_nowait()
                        completed_count += 1
                        yield {"type": "phase", "phase": "character_complete", "message": f"{progress['character_name']}: aie valmis ({completed_count}/{len(acting)})", **progress}
                    decisions = await asyncio.gather(*tasks, return_exceptions=True)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                for decision in decisions:
                    if isinstance(decision, BaseException):
                        raise decision
                    if decision.get("goal_update"):
                        roster[decision["character_id"]].current_goal = decision["goal_update"]
                    intentions.append(decision)
            yield {"type": "phase", "phase": "prose_synthesis", "message": "Kertoja ratkaisee tapahtumat ja kirjoittaa jatkon..."}
            raw = await self.director.synthesize_turn_prose(
                story_id=story_id, scene=scene, all_character_intentions=intentions,
                recent_prose_context="\n\n".join(turn.director_prose for turn in turns[-3:])[-12000:],
                director_guidance=director_guidance, tone_profile=meta.tone_profile,
                custom_tone_override=meta.custom_tone_override, mode=mode,
                reader_wish=user_input if mode != "roleplay" else None,
                runtime=runtime, characters=characters,
                player_character_id=player.id if mode == "roleplay" and player else None,
                turn_plan=plan.model_dump() | {"truths": bible["secret_truths"], "clocks": bible["clocks"],
                                                "offscreen_agents": bible["offscreen_agents"]}
            )
            outcome = ProseTurnResponse.model_validate(raw)
            outcome.scene_location = outcome.scene_location or scene.location
            outcome.scene_goal = outcome.scene_goal or scene.scene_goal
            if runtime.get("chapter_title"):
                outcome.chapter_title = runtime["chapter_title"]
            spawned = list(planned_spawned)
            for candidate in outcome.spawned_characters:
                if candidate.id in roster or not candidate.id or not all(char.isalnum() or char in "_-" for char in candidate.id):
                    raise ValueError("Kertoja palautti päällekkäisen tai virheellisen hahmotunnisteen.")
                character = Character(**candidate.model_dump(), status="active")
                character.is_player_controlled = False
                character.location_id = db.location_identifier(scene.location)
                roster[character.id] = character
                spawned.append(character)
            current_location_id = db.location_identifier(scene.location)
            allowed_witnesses = {
                identifier for identifier in set(scene.active_character_ids) | {character.id for character in spawned}
                if roster[identifier].location_id in {None, current_location_id}
            }
            intention_ids = {intent["character_id"] for intent in intentions}
            accepted_events = []
            for event in outcome.events:
                if not set(event.witnesses) <= roster.keys():
                    raise ValueError("Tapahtuman havaitsija ei ole tunnettu hahmo.")
                if not set(event.witnesses) <= allowed_witnesses:
                    logger.warning("Removed out-of-scene witnesses from resolver event %s", event.id)
                    event.witnesses = list(dict.fromkeys(identifier for identifier in event.witnesses if identifier in allowed_witnesses))
                event.witness_details = [detail for detail in event.witness_details if detail.character_id in event.witnesses]
                if event.derived_from.startswith("intent:"):
                    actor_id = event.derived_from.split(":", 1)[1]
                    if actor_id not in intention_ids:
                        raise ValueError("Tapahtuman aikomuslähde ei vastaa hahmokutsua.")
                    if event.actor_id and event.actor_id != actor_id:
                        raise ValueError("Tapahtuman tekijä ei vastaa aikomuslähdettä.")
                    event.actor_id = actor_id
                else:
                    text = event.description.casefold()
                    action_words = ("nousi", "seurasi", "astui", "sanoi", "vastasi", "lähti", "siirtyi",
                                    "rose", "followed", "stepped", "said", "moved", "decided")
                    named_actor = roster.get(event.actor_id) if event.actor_id else next(
                        (character for character in characters if character.name.casefold() in text
                         or character.name.casefold().split()[0] in text), None)
                    if named_actor and any(word in text for word in action_words):
                        logger.warning("Removed voluntary resolver event without matching intent: %s", event.id)
                        continue
                accepted_events.append(event)
            final_events = list(plan.events)
            for event in accepted_events:
                if event not in final_events:
                    final_events.append(event)
            outcome.events = final_events
            for update in outcome.character_state_updates:
                if update.character_id not in roster:
                    raise ValueError("Tilapäivitys viittaa tuntemattomaan hahmoon.")
                character = roster[update.character_id]
                if character.status == "dead" and update.status is not None and update.status != "dead":
                    raise ValueError("Loppukertoja ei saa perua jo toteutunutta kuolemaa.")
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
            player_views = {}
            player_view_statuses = {}
            player_view_errors = {}
            stored_characters = await db.get_all_characters(story_id)
            viewpoint_character = next((character for character in stored_characters if character.is_player_controlled), None)
            own_intention = {}
            if viewpoint_character:
                player_view_statuses[viewpoint_character.id] = "view_pending"
                own_intention = next((intention for intention in intentions if intention["character_id"] == viewpoint_character.id), {})
            action = "\n".join(f"[{intention['character_name']}]: {intention['action_and_speech']}" for intention in intentions)
            monologue = "\n".join(f"[{intention['character_name']}]: {intention['internal_monologue']}" for intention in intentions)
            response = TurnResponse(
                turn_index=turn_index, mode=mode, request_id=request_id,
                acting_character=player.model_dump() if mode == "roleplay" and player else None,
                internal_monologue=monologue, character_action=action, director_prose=outcome.prose,
                choices=outcome.choices, image_prompt=outcome.image_prompt,
                updated_characters=list(roster.values()), spawned_characters=spawned,
                story_text_snippet=outcome.prose, is_chapter_end=outcome.chapter_end,
                requires_player_input=plan.requires_player_input or outcome.requires_player_input or mode == "roleplay",
                player_view_status="view_pending" if viewpoint_character else None
            )
            turn = SceneTurn(scene_id=scene.id, turn_index=turn_index,
                             acting_character_id=player.id if mode == "roleplay" and player else None,
                             internal_monologue=monologue, character_action=action,
                             director_prose=outcome.prose, choices=outcome.choices, image_prompt=outcome.image_prompt)
            yield {"type": "phase", "phase": "saving", "message": "Tarkistetaan vastaus ja tallennetaan vuoro..."}
            await turn_store.commit_turn(story_id, last_id, turn, list(roster.values()), outcome, response, fingerprint,
                {"mode": mode, "user_input": user_input, "private_intention": private_intention,
                 "turn_plan": plan.model_dump(),
                 "player_views": player_views,
                 "player_view_statuses": player_view_statuses,
                 "player_view_errors": player_view_errors,
                 "objective_progress": bool(planned_progress
                                            or any(event.derived_from == "consequence" and event.actor_id for event in outcome.events)),
                 "director_guidance": director_guidance, "director_model": settings.DIRECTOR_MODEL,
                 "character_model": settings.CHARACTER_MODEL, "intentions": intentions,
                 "contract_version": 2,
                 "prompt_hashes": {path: hashlib.sha256(prompt_loader.get_raw_prompt(path).encode()).hexdigest()
                    for path in ("director/plan_turn.txt", "director/synthesize_prose.txt", "director/player_view.txt", f"director/mode_{mode}.txt", "character/decide_action.txt", "language_directive.txt", "safety_directive.txt", f"tone_profiles/{meta.tone_profile}.txt")}},
                expected_revision=revision)
            if viewpoint_character:
                yield {"type": "phase", "phase": "player_view", "message": "Vuoro tallennettiin; muodostetaan hahmon tietorajattu näkökulma..."}
                try:
                    player_views[viewpoint_character.id] = await self.director.create_player_view(
                        story_id, viewpoint_character, outcome, own_intention, runtime,
                        scene.location, meta.tone_profile, meta.custom_tone_override)
                    response.player_view_status = "view_ready"
                except Exception as exc:
                    logger.warning("Player view generation failed after committed turn %s: %s", turn_index, exc)
                    response.player_view_status = "view_failed"
                    response.warnings.append("Vuoro tallennettiin, mutta hahmon näkökulma epäonnistui. Sen voi yrittää uudelleen.")
                try:
                    committed_turn_id = max((item.id or 0 for item in await db.get_all_story_turns(story_id)), default=last_id + 1)
                    await turn_store.save_player_view(
                        story_id, committed_turn_id, viewpoint_character.id,
                        player_views.get(viewpoint_character.id),
                        error="" if response.player_view_status == "view_ready" else "View generation failed"
                    )
                    await turn_store.update_receipt_response(story_id, request_id, response)
                except Exception as exc:
                    logger.warning("Could not persist player-view status for turn %s: %s", turn_index, exc)
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