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
from core.schemas import PlannerResponse, ProseTurnResponse, ResolverResponse, StoryEvent, pydantic_to_json_schema
from core.prompt_loader import prompt_loader
from core.types import Character, SceneTurn, StoryInitRequest, QuickStoryRequest, TurnResponse, normalize_mode
from database import db, turn_store
from engine.reaction_cycle import eligible_reaction_decisions
from engine.simulation_contract import (is_present, visible_neighbours, validate_groups, collect_groups,
    normalize_additions, validate_simulation_outcome, consequence_links)
from engine.adaptive_interaction import InteractionBudget, as_outcome, collect_adaptive
from engine.situation_agent import SituationAgent
from engine.character_agent import CharacterAgent
from engine.chronicle_manager import ChronicleManager
from engine.director_agent import DirectorAgent
from engine.turn_contract import apply_resolved_changes, concrete_progress, merge_continuity, validate_event_links, validate_bible_additions, assign_event_ids

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

    async def get_simulation_controls(self, story_id):
        controls = await turn_store.get_simulation_controls(story_id)
        options = await turn_store.get_failure_options(story_id)
        eligible = set(options["switch_character_ids"])
        characters = await db.get_all_characters(story_id)
        runtime = await turn_store.get_runtime(story_id)
        return {**controls, "player_failed": options["failed"], "ended": bool(runtime.get("ended")),
                "eligible_characters": [{"id": character.id, "name": character.name} for character in characters
                                        if character.id in eligible and character.visibility_state == "visible"],
                "snapshots": [{"id": identifier, "label": f"Ennen vuoroa {identifier}"} for identifier in options["retry_turn_ids"]]}

    async def set_plot_guidance(self, story_id, preset, expected_revision):
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            current = await turn_store.get_simulation_controls(story_id)
            await turn_store.set_simulation_controls(story_id, preset, expected_revision, current["decision_budget"])
            return await self.get_simulation_controls(story_id)

    async def preview_null_locations(self, story_id):
        preview = await db.preview_null_location_migration(story_id)
        world = await db.get_planning_world(story_id)
        locations = [{"id": item["id"], "name": item["name"]} for item in world["locations"]]
        return {"revision": preview["revision"], "candidates": [
            {"character_id": item["id"], "name": item["name"], "suggested_location_id": item["suggested_location_id"],
             "locations": locations, "ambiguous": True} for item in preview["characters"]]}

    async def apply_null_locations(self, story_id, selections, expected_revision):
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            await db.apply_null_location_migration(story_id, selections, expected_revision)
            return await self.preview_null_locations(story_id)

    async def continue_failed_player(self, story_id, action, expected_revision, character_id=None, snapshot_id=None):
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            action = {"select_character": "switch", "choose_character": "switch", "retry_branch": "retry", "branch": "retry"}.get(action, action)
            if action == "retry":
                if isinstance(snapshot_id, bool) or not isinstance(snapshot_id, int):
                    raise ValueError("Retry requires a snapshot ID")
                result = await turn_store.create_retry_branch(story_id, snapshot_id, expected_revision)
                return {**result, **(await self.get_simulation_controls(result["story_id"]))}
            if action == "switch":
                safe = await self.get_simulation_controls(story_id)
                if character_id not in {item["id"] for item in safe["eligible_characters"]}:
                    raise ValueError("Continuation character is not eligible")
            await turn_store.continue_after_failure(story_id, action, expected_revision, character_id)
            return {"story_id": story_id, **(await self.get_simulation_controls(story_id))}

    async def create_character_catchup(self, story_id: str, character_id: str, expected_revision: int) -> dict:
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            revision = await turn_store.get_revision(story_id)
            if revision != expected_revision:
                raise turn_store.TurnConflictError("Tarina muuttui. Lataa se uudelleen.")
            character = await db.get_character(story_id, character_id)
            scene = await db.get_active_scene(story_id)
            if not character or not character.is_player_controlled or character.status != "active" or not scene or character_id not in scene.active_character_ids or not is_present(character, scene):
                raise ValueError("Kertaus voidaan muodostaa vain aktiivisessa kohtauksessa olevalle pelaajahahmolle.")
            turns = await db.get_all_story_turns(story_id)
            if not turns or turns[-1].id is None:
                raise ValueError("Tarinalta puuttuu viimeisin vuoro.")
            turn_id = turns[-1].id
            metadata = await turn_store.get_reading_metadata(story_id)
            entry = metadata.get(str(turn_id), {})
            if entry.get("player_views", {}).get(character_id) or entry.get("player_view_status", {}).get(character_id) in {"view_pending", "view_failed"}:
                raise ValueError("Viimeiselle vuorolle on jo hahmon näkökulma tai uusittava näkökulmatyö.")
            cached = (await turn_store.get_character_catchups(story_id)).get(character_id)
            if cached:
                return {"status": "catchup_ready", "catchup": cached}
            meta = await db.get_story_meta(story_id)
            if not meta:
                raise ValueError("Tarinaa ei löydy.")
            view = await self.director.create_character_catchup(story_id, character, meta)
            await turn_store.save_character_catchup(story_id, character_id, turn_id, view, revision)
            return {"status": "catchup_ready", "catchup": {**view, "turn_id": turn_id}}

    async def retry_player_view(self, story_id: str, turn_id: int, character_id: str) -> dict:
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            context = await turn_store.get_player_view_retry_context(story_id, turn_id, character_id)
            character = Character.model_validate(context["character"]) if context.get("character") else await db.get_character(story_id, character_id)
            if not character:
                raise ValueError("Hahmoa ei löydy.")
            outcome = ProseTurnResponse.model_validate(context["outcome"])
            intention = next((item for item in context["audit"].get("intentions", [])
                              if item.get("character_id") == character_id), {})
            meta = await db.get_story_meta(story_id)
            if not meta:
                raise ValueError("Tarinaa ei löydy.")
            view = await self.director.create_player_view(
                story_id, character, outcome, intention, context.get("runtime", {}),
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
                json_schema=pydantic_to_json_schema(ResolverResponse, "authored_reconciliation")
            )
            resolved = ResolverResponse.model_validate(raw)
            outcome = ProseTurnResponse.model_validate(resolved.model_dump() | merge_continuity(resolved, runtime))
            if outcome.state_changes or outcome.truth_access_updates or any(outcome.bible_additions.model_dump().values()):
                raise ValueError("Oman jatkon esikatselu ei vielä tue esineiden, suhteiden tai löytöreittien rakenteisia muutoksia.")
            outcome.prose = prose
            outcome.choices = []
            outcome.image_prompt = ""
            roster = {character.id: character for character in characters}
            if outcome.spawned_characters:
                raise ValueError("Oman jatkon synkronointi ei vielä luo uusia hahmoja. Lisää hahmot ensin tarinaan.")
            for event in outcome.events:
                if not set(event.witnesses) <= roster.keys():
                    raise ValueError("Havainto viittaa tuntemattomaan hahmoon.")
            assign_event_ids(outcome.events, outcome.character_state_updates + ([outcome.location] if outcome.location else []))
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

    async def quick_create_story(self, request: QuickStoryRequest) -> dict[str, Any]:
        description = request.description.strip()
        if not description:
            raise ValueError("Kuvaile luotava tarina.")
        profiles = prompt_loader.list_tone_profiles()
        profile_ids = {profile["id"] for profile in profiles}
        if request.tone_profile and request.tone_profile not in profile_ids:
            raise ValueError("Tuntematon savyprofiili.")
        raw = await self.llm.json_completion(
            messages=[
                {"role": "system", "content": prompt_loader.compose_system_prompt("director/quick_story", include_tone=False)},
                {"role": "user", "content": json.dumps({
                    "description": description, "mode": request.mode, "style": request.style,
                    "tone_profile": request.tone_profile,
                    "available_tone_profiles": [{"id": profile["id"], "title": profile["title"]} for profile in profiles]
                }, ensure_ascii=False)}
            ], role="director", temperature=settings.STORY_INIT_TEMPERATURE,
            reasoning_effort=settings.STORY_INIT_REASONING_EFFORT, max_tokens=3000,
            json_schema=pydantic_to_json_schema(StoryInitRequest, "quick_story")
        )
        generated = StoryInitRequest.model_validate(raw)
        if not generated.title.strip():
            raise ValueError("Pikaluonti ei palauttanut tarinalle nimea.")
        generated.title = generated.title.strip()
        generated.user_role = request.mode or normalize_mode(generated.user_role)
        if request.style and request.style.strip():
            generated.genre = request.style.strip()
        generated.tone_profile = request.tone_profile or generated.tone_profile or "default"
        if generated.tone_profile not in profile_ids:
            raise ValueError("Pikaluonti palautti tuntemattoman savyprofiilin.")
        generated.user_idea = description + "\n\n" + (generated.user_idea or "")
        return await self.initialize_new_story(generated)

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
            assign_event_ids(events, [])
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
            initial_roster = {character.id: character for character in result["characters"]}
            for event in events:
                event.observations = [observation for observation in event.observations
                                      if is_present(initial_roster[observation.character_id], result["scene"])]
            observations = {}
            for character in result["characters"]:
                perceived = []
                for event in events:
                    if character.id in event.witnesses:
                        perceived.append(event.observation_for(character.id))
                observations[character.id] = ("\n".join(perceived) or f"Olet paikassa {result['scene'].location}.") if is_present(character, result["scene"]) else "Ei uusia paikallisia havaintoja; sijainti tuntematon."
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
        request_id: Optional[str] = None, extra_reaction_cycle: bool = False,
        plot_guidance: Optional[str] = None, decision_budget: Optional[int] = None, expected_revision: Optional[int] = None
    ) -> AsyncIterator[dict[str, Any]]:
        db.get_story_dir(story_id)
        request_id = request_id or uuid4().hex
        if mode == "director":
            director_guidance = director_guidance or user_input
            user_input = None
        mode = normalize_mode(mode)
        fingerprint = self._advance_fingerprint(mode, user_input, director_guidance, private_intention, extra_reaction_cycle, plot_guidance, decision_budget)
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            if not db.get_db_path(story_id).exists():
                raise ValueError("Tarinaa ei löydy.")
            previous = await turn_store.get_receipt(story_id, request_id, fingerprint)
            if previous:
                yield {"type": "turn_complete", "data": previous.model_dump()}
                return
            response = None
            pending = []
            async for event in self._advance_cycle_streaming(
                story_id, user_input, mode, director_guidance, private_intention, request_id,
                extra_reaction_cycle=extra_reaction_cycle, plot_guidance=plot_guidance,
                decision_budget=decision_budget, expected_revision=expected_revision
            ):
                if event["type"] == "turn_complete":
                    response = TurnResponse.model_validate(event["data"])
                    pending = event.get("pending_reactions", [])
                else:
                    yield event
            if response is None:
                raise RuntimeError("Vuoro ei valmistunut.")
            if extra_reaction_cycle and pending:
                # A committed first beat is never resumed/replayed, even after cancellation or restart.
                followup_id = "reaction_" + uuid4().hex
                response.followup_request_id = followup_id
                await turn_store.update_receipt_response(story_id, request_id, response)
                yield {"type": "phase", "phase": "extra_reaction", "message": "Uusi tapahtuma vaatii hahmon päätöksen: yksi lisäsykli (1/1)..."}
                try:
                    async for event in self._advance_cycle_streaming(
                        story_id, mode=mode, request_id=followup_id, reaction_decisions=pending
                    ):
                        if event["type"] == "turn_complete":
                            first_warnings = response.warnings
                            response = TurnResponse.model_validate(event["data"])
                            response.warnings = list(dict.fromkeys(first_warnings + response.warnings))
                            await turn_store.update_receipt_response(story_id, response.request_id, response)
                        else:
                            yield event
                except Exception as exc:
                    logger.warning("Extra reaction stopped after committed first beat: %s", exc)
                    response = await turn_store.get_receipt(story_id, request_id) or response
                    response.warnings.append("Ensimmäinen vuoro tallennettiin; lisäreaktio ei valmistunut. Samaa toimintaa ei toisteta.")
                    await turn_store.update_receipt_response(story_id, response.request_id, response)
            yield {"type": "turn_complete", "data": response.model_dump()}

    @staticmethod
    def _advance_fingerprint(mode, user_input, director_guidance, private_intention, extra_reaction_cycle=False, plot_guidance="balanced", decision_budget=4):
        payload = [mode, user_input, director_guidance, private_intention]
        if extra_reaction_cycle:
            payload.append(True)
        if plot_guidance not in {None, "balanced"} or decision_budget not in {None, 4}:
            payload.extend([plot_guidance, decision_budget])
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()

    async def _advance_cycle_streaming(
        self, story_id: str, user_input: Optional[str] = None, mode: str = "novel",
        director_guidance: Optional[str] = None, private_intention: Optional[str] = None,
        request_id: Optional[str] = None, extra_reaction_cycle: bool = False,
        reaction_decisions: Optional[list[dict[str, Any]]] = None,
        plot_guidance: Optional[str] = None, decision_budget: Optional[int] = None, expected_revision: Optional[int] = None
    ) -> AsyncIterator[dict[str, Any]]:
        db.get_story_dir(story_id)
        if mode == "director":
            director_guidance = director_guidance or user_input
            user_input = None
        mode = normalize_mode(mode)
        request_id = request_id or uuid4().hex
        fingerprint = self._advance_fingerprint(mode, user_input, director_guidance, private_intention, extra_reaction_cycle, plot_guidance, decision_budget)
        if not db.get_db_path(story_id).exists():
            raise ValueError("Tarinaa ei löydy.")
        revision = await turn_store.get_revision(story_id)
        if expected_revision is not None and expected_revision != revision:
            raise turn_store.TurnConflictError("Tarina muuttui. Lataa se uudelleen.")
        saved_controls = await turn_store.get_simulation_controls(story_id)
        plot_guidance = plot_guidance if plot_guidance is not None else saved_controls["plot_guidance"]
        decision_budget = decision_budget if decision_budget is not None else saved_controls["decision_budget"]
        if plot_guidance not in {"adaptive", "balanced", "strong"} or isinstance(decision_budget, bool) or not isinstance(decision_budget, int) or not 1 <= decision_budget <= 8:
            raise ValueError("Invalid simulation controls")
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
        before_characters = {identifier: character.model_dump() for identifier, character in roster.items()}
        initial_world = await db.get_planning_world(story_id)
        scene_location_id = scene.location_id or db.location_identifier(scene.location)
        present = [character for character in characters if character.id in scene.active_character_ids
                   and character.status == "active" and character.location_id == scene_location_id]
        turns = await db.get_all_story_turns(story_id)
        last_id = max((turn.id or 0 for turn in turns), default=0)
        turn_index = max((turn.turn_index for turn in turns), default=0) + 1
        runtime = await turn_store.get_runtime(story_id)
        runtime.update(plot_guidance=plot_guidance, decision_budget=decision_budget)
        candidate_record = await turn_store.get_resolver_candidate(story_id, request_id, fingerprint)
        if candidate_record:
            raise turn_store.TurnConflictError("This request has a retained resolver candidate; repair it or use a new request ID, never replay its intentions.")
        await self.director.ensure_story_bible(story_id, scene, characters)
        revision = await turn_store.get_revision(story_id)
        player = next((character for character in present if character.is_player_controlled), None)
        if runtime.get("ended"):
            raise ValueError("Tarina on päätetty; jatka uudessa haarassa.")
        if mode == "roleplay" and player is None:
            raise ValueError("Valitse kohtauksessa oleva toimintakykyinen pelaajahahmo.")
        yield {"type": "phase", "phase": "turn_planning", "message": "Kertoja suunnittelee tilanteen ja hahmojen havainnot..."}
        if reaction_decisions:
            plan = PlannerResponse(
                decision_character_ids=list(dict.fromkeys(item["character_id"] for item in reaction_decisions)),
                direction="EXTRA REACTION (1/1): Resolve only these unresolved choices caused by the preceding committed events: "
                + json.dumps(reaction_decisions, ensure_ascii=False)
                + ". No new player action, historical attempt, world intervention, or automatic clock tick. Stop for any player choice."
            )
        else:
            plan = await self.director.plan_turn(story_id, scene, characters, runtime, mode,
                                                 user_input, director_guidance, private_intention)
        bible = await db.get_story_bible(story_id)
        validate_bible_additions(plan.bible_additions, bible, roster)
        truths = {truth["id"]: truth for truth in bible["secret_truths"]}
        clocks = {clock["id"]: clock for clock in bible["clocks"]}
        offscreen = {agent["id"]: agent for agent in bible["offscreen_agents"]}
        if len({reveal.truth_id for reveal in plan.reveals}) != len(plan.reveals):
            raise ValueError("Samaa salaisuutta ei voi paljastaa kahdesti samalla vuorolla.")
        plan_warnings = []
        for event in plan.events:
            if event.derived_from.startswith("intent:") or (
                event.actor_id in scene.active_character_ids and not director_guidance
            ):
                raise ValueError("Suunnittelija ei saa tehdä hahmon vapaaehtoista päätöstä ennen hahmokutsua.")
        reveal_events = []
        effective_reveals = []
        for reveal in plan.reveals:
            truth = truths.get(reveal.truth_id)
            if not truth:
                raise ValueError("Suunnitelma viittaa tuntemattomaan salaiseen totuuteen.")
            if truth["reveal_state"] == "revealed":
                continue
            effective_reveals.append(reveal)
            # Discovery updates narrator knowledge; only explicit observed events reach characters.
            reveal_events.append(StoryEvent(
                description=reveal.how, observations=[], derived_from="world", change_kind="information"
            ))
        plan.reveals = effective_reveals
        requested_ticks = {}
        for tick in plan.clock_ticks:
            if tick.clock_id not in clocks:
                raise ValueError("Suunnitelma viittaa tuntemattomaan kelloon.")
            requested_ticks[tick.clock_id] = requested_ticks.get(tick.clock_id, 0) + tick.amount
        expired_clock_ids = []
        for clock_id, clock in clocks.items():
            if not reaction_decisions and clock["remaining_beats"] > 0 and clock["remaining_beats"] - (plan.elapsed_time.clock_beats if plan.elapsed_time else 1) - requested_ticks.get(clock_id, 0) <= 0:
                expired_clock_ids.append(clock_id)
                reveal_events.append(StoryEvent(
                    description=clock["on_expire_effect"] or clock["description"],
                    observations=[], derived_from="world", change_kind="risk"
                ))
        for agent_id, move in plan.offscreen_moves.items():
            if agent_id not in offscreen:
                raise ValueError("Suunnitelma viittaa tuntemattomaan sivuhenkilöön.")
            if move.strip():
                reveal_events.append(StoryEvent(
                    description=move, observations=[], derived_from="world"
                ))
        allowed_change_fields = {
            "character": {"location_id", "physical_state", "mental_state", "status", "visibility_state"},
            "item": {"holder_character_id", "location_id", "state"},
            "relationship": {"attitude", "trust", "summary"},
        }
        supported_changes = []
        for change in plan.state_changes:
            if change.entity not in allowed_change_fields or change.field not in allowed_change_fields[change.entity]:
                logger.warning("Discarded unsupported planned state change %s.%s", change.entity, change.field)
                plan_warnings.append(f"Kertojan tukematon tilamuutos ohitettiin ({change.entity}.{change.field}).")
                continue
            supported_changes.append(change)
        plan.state_changes = supported_changes
        validated_changes = []
        for change in plan.state_changes:
            if change.entity == "character" and change.field in {"mental_state", "location_id"} and not director_guidance:
                raise ValueError("Suunnittelija ei saa päättää hahmon mielentilaa tai liikkumista.")
            if change.entity == "item" and not await db.get_item(story_id, change.entity_id):
                logger.warning("Discarded planned state change for unknown item %s", change.entity_id)
                continue
            validated_changes.append(change)
        plan.state_changes = validated_changes
        assign_event_ids(plan.events, plan.state_changes)
        effective_ticks = any(clocks[tick.clock_id]["remaining_beats"] > 0 for tick in plan.clock_ticks)
        changed_offscreen = any(move.strip() and move != offscreen[identifier]["progress"]
                                for identifier, move in plan.offscreen_moves.items())
        planned_state_progress = await apply_resolved_changes(
            story_id, plan.state_changes, roster, scene.active_character_ids, scene.location)
        planned_progress = bool(plan.reveals or expired_clock_ids or effective_ticks
                                or changed_offscreen or planned_state_progress)
        plan.events.extend(reveal_events)
        event_location_id = scene.location_id or db.location_identifier(scene.location)
        present_ids = {
            character.id for character in roster.values()
            if character.id in scene.active_character_ids
            and character.location_id == event_location_id
        }
        for event in plan.events:
            if not set(event.witnesses) <= roster.keys():
                raise ValueError("Suunnitelman havaitsija ei ole tunnettu hahmo.")
            if not set(event.witnesses) <= present_ids:
                logger.warning("Removed out-of-scene witnesses from planned event %s", event.id)
                event.observations = [observation for observation in event.observations if observation.character_id in present_ids]
            event.derived_from = "world"
        characters = list(roster.values())
        present = [character for character in characters if character.id in scene.active_character_ids
                   and character.status == "active" and character.location_id == event_location_id]
        adaptive = plan.interaction_mode == "adaptive" and not reaction_decisions
        if (plan.decision_groups or adaptive) and extra_reaction_cycle:
            # Group planning owns continuation; the legacy extra-cycle path must not add another loop.
            extra_reaction_cycle = False
        if not set(plan.decision_character_ids) <= roster.keys():
            raise ValueError("Suunnitelma pyytää päätöstä tuntemattomalta hahmolta.")
        plan.decision_character_ids = [identifier for identifier in plan.decision_character_ids
                                       if identifier in {character.id for character in present}]
        if mode == "roleplay" and player and player.id in plan.decision_character_ids:
            raise ValueError("Suunnitelma ei saa päättää pelaajan puolesta.")
        if mode == "simulation" and not reaction_decisions and not plan.decision_groups and not adaptive:
            plan.decision_character_ids = [character.id for character in present]
        intentions = []
        if mode == "roleplay" and player and player in present and not reaction_decisions:
            intentions.append({"character_id": player.id, "character_name": player.name,
                               "action": user_input or "Odotan ja tarkkailen.", "speech": "",
                               "private_thought": private_intention or ""})
        semaphore = asyncio.Semaphore(self.max_concurrent_characters)
        progress_queue = asyncio.Queue()

        for intention in intentions:
            intention.setdefault("id", uuid4().hex)
        candidate_private_intentions = list(intentions)

        async def decide(character: Character, observed_starts=None, intermediate=None):
            async with semaphore:
                observation = await turn_store.get_observation(story_id, character.id)
                observed_scene_location = scene.location
                observed_neighbours = visible_neighbours(character, [other for other in roster.values()
                    if other.id in scene.active_character_ids and other.status == "active" and is_present(other, scene)])
                new_observations = [event.observation_for(character.id) for event in plan.events
                                    if character.id in event.witnesses]
                if new_observations:
                    observation += "\n\n" + "\n".join(new_observations)
                for start in observed_starts or []:
                    if character.id in start["observer_ids"]:
                        observation += "\n[OBSERVED START; OUTCOME OPEN] " + start["text"]
                for resolved in intermediate or []:
                    for event in resolved.events:
                        if character.id in event.witnesses:
                            observation += "\n[INTERMEDIATE VERIFIED EVENT] " + event.observation_for(character.id)
                if adaptive:
                    own_prior = [item for item in candidate_private_intentions if item["character_id"] == character.id]
                    if own_prior:
                        observation += "\n[YOUR PREVIOUS PRIVATE CANDIDATE ATTEMPT]\n" + json.dumps(own_prior[-1], ensure_ascii=False)
                    own_commitments = [item for item in runtime.get("commitments", {}).values() if character.id in item.get("participants", [])]
                    if own_commitments:
                        observation += "\n[YOUR CANDIDATE COMMITMENTS]\n" + json.dumps(own_commitments, ensure_ascii=False)
                if reaction_decisions:
                    observation += "\n\nA new verified observation now requires a fresh meaningful choice. Decide your response using only your own observations and knowledge; previous attempts are historical, not new actions."
                agent_character = character.model_copy(update={"is_player_controlled": False}) if mode != "roleplay" else character
                decision = await CharacterAgent(agent_character, interaction_llm if adaptive else self.llm).decide_intention(
                    story_id=story_id, scene_location=observed_scene_location,
                    recent_prose_context=observation, tone_profile=meta.tone_profile,
                    custom_tone_override=meta.custom_tone_override,
                    nearby_characters=observed_neighbours
                )
                decision["context_manifest"]["candidate_event_ids"] = [event.id for event in plan.events if event.observation_for(character.id)]
                decision["context_manifest"]["observed_start_intent_ids"] = [start["intent_id"] for start in observed_starts or [] if character.id in start["observer_ids"]]
                decision["context_manifest"]["intermediate_event_ids"] = [event.id for resolved in intermediate or [] for event in resolved.events if event.observation_for(character.id)]
                group_index = max(0, adaptive_budget.decisions - 1) if adaptive else next((index for index, group in enumerate(groups) if character.id in group.character_ids), 0)
                progress = {"character_id": character.id, "character_name": character.name,
                            "group_index": group_index, "group_count": adaptive_budget.decision_limit if adaptive else len(groups),
                            "group_mode": "adaptive" if adaptive else groups[group_index].mode if groups else "parallel"}
                if mode != "roleplay":
                    progress["character_thought"] = decision["private_thought"]
                progress_queue.put_nowait(progress)
                return {"character_id": character.id, "character_name": character.name, **decision}

        groups = validate_groups(plan, {character.id for character in present},
                                 player.id if mode == "roleplay" and player else None, decision_budget)
        intermediate_outcomes = []
        initial_runtime = json.loads(json.dumps(runtime))
        candidate_world_state = initial_world
        adaptive_budget = InteractionBudget(
            decision_limit=min(settings.SITUATION_DECISION_LIMIT, decision_budget * 4),
            call_limit=settings.SITUATION_CALL_LIMIT, character_limit=settings.SITUATION_CHARACTER_LIMIT,
            seconds=settings.SITUATION_TIME_LIMIT_SECONDS, token_limit=settings.SITUATION_TOKEN_LIMIT)

        from engine.interaction_llm import InteractionLLM
        interaction_llm = InteractionLLM(self.llm, adaptive_budget)

        def advance_runtime(resolved):
            runtime.update(merge_continuity(resolved, runtime))
            runtime.setdefault("attempt_results", {}).update({item.intent_id: item.model_dump() for item in resolved.attempt_results})
            runtime.setdefault("commitments", {}).update({item.id: item.model_dump() for item in resolved.commitments})

        async def resolve_intermediate(group_intentions, starts, _previous):
            candidate = await self.director.synthesize_turn_prose(
                story_id, scene, group_intentions, "", runtime=runtime, characters=list(roster.values()),
                mode=mode, player_character_id=player.id if mode == "roleplay" and player else None,
                turn_plan={"direction": "Resolve only collected intentions before outcome-dependent choices; no new voluntary actions.",
                           "public_starts": starts, "intermediate_resolution": True, "elapsed_clock_policy": "This reaction does not automatically consume a full beat; estimate actual elapsed time, default clock_beats 0"})
            resolved = ProseTurnResponse.model_validate(candidate)
            validate_simulation_outcome(resolved, group_intentions, runtime, roster)
            if resolved.entity_additions.locations or resolved.entity_additions.items or resolved.entity_additions.relationships or resolved.spawned_characters or resolved.location:
                raise ValueError("Intermediate entity/scene creation requires a separate complete turn boundary")
            assign_event_ids(resolved.events, consequence_links(resolved))
            supplied = {intent["id"]: intent for intent in group_intentions}
            for event in resolved.events:
                if event.derived_from.startswith("intent:") and (event.intent_id not in supplied or supplied[event.intent_id]["character_id"] != event.derived_from.split(":", 1)[1]):
                    raise ValueError("Intermediate resolution has an unknown intention")
                event.observations = [observation for observation in event.observations
                                      if observation.character_id in roster and is_present(roster[observation.character_id], scene)]
            await apply_resolved_changes(story_id, resolved.state_changes, roster,
                                         {character.id for character in present}, scene.location)
            for update in resolved.character_state_updates:
                if update.character_id not in roster:
                    raise ValueError("Unknown intermediate character")
                character = roster[update.character_id]
                if character.status == "dead" and update.status not in {None, "dead"}:
                    raise ValueError("Intermediate resolution may not reverse death")
                for field in ("physical_state", "mental_state", "status"):
                    if getattr(update, field) is not None:
                        setattr(character, field, getattr(update, field))
            advance_runtime(resolved)
            return resolved

        async def accept_situation(response, fresh, previous):
            nonlocal candidate_world_state
            resolved = as_outcome(response)
            validate_simulation_outcome(resolved, fresh, runtime, roster)
            supplied = {item["id"]: item for item in fresh}
            for event in resolved.events:
                if any(previous_event.id == event.id for item in previous for previous_event in item.events):
                    raise ValueError("Situation controller may not replay an accepted event")
                if event.derived_from.startswith("intent:") or event.derived_from == "routine":
                    source = supplied.get(event.intent_id)
                    if event.intent_id in {value.intent_id for item in previous for value in item.attempt_results if value.status != "pending"}:
                        raise ValueError("Situation controller cannot replay an already resolved attempt")
                    if not source or event.actor_id != source["character_id"] or (event.derived_from != "routine" and event.derived_from != "intent:" + source["character_id"]):
                        raise ValueError("Situation event must preserve its exact supplied intention")
                elif event.actor_id in roster:
                    raise ValueError("Situation controller cannot invent a character action")
            assign_event_ids(resolved.events, consequence_links(resolved))
            # Reaction and permit references must follow the normalized persistent event IDs.
            original_ids = [event.id for event in response.events]
            remap = dict(zip(original_ids, [event.id for event in resolved.events]))
            if response.next_group:
                for reaction in response.next_group.reactions:
                    reaction.event_id = remap.get(reaction.event_id, reaction.event_id)
            if response.relay_permit:
                response.relay_permit.source_event_id = remap.get(response.relay_permit.source_event_id, response.relay_permit.source_event_id)
            for candidate in resolved.spawned_characters:
                if candidate.id in roster or not candidate.id or len(candidate.id) > 80 or not all(char.isalnum() or char in "_-" for char in candidate.id):
                    raise ValueError("New character collides with existing actor or has an invalid ID")
                roster[candidate.id] = Character(**candidate.model_dump(), status="active")
            candidate_world_state, _ = await normalize_additions(story_id, resolved, roster, candidate_world_state)
            candidate_world_state = {key: list(value.values()) for key, value in candidate_world_state.items()}
            existing_bible = {field: bible[field] + [item.model_dump() for item in getattr(plan.bible_additions, field)]
                              + [addition.model_dump() for item in previous for addition in getattr(item.bible_additions, field)]
                              for field in ("secret_truths", "clocks", "offscreen_agents")}
            validate_bible_additions(resolved.bible_additions, existing_bible, roster)
            known_truths = {item["id"] for item in existing_bible["secret_truths"]} | {item.id for item in resolved.bible_additions.secret_truths}
            if any(item.truth_id not in known_truths for item in resolved.truth_access_updates):
                raise ValueError("Unknown truth access update")
            locations = {identifier: character.location_id for identifier, character in roster.items()}
            for event in resolved.events:
                locations.update({change.entity_id: change.value for change in resolved.state_changes
                                  if change.event_id == event.id and change.entity == "character" and change.field == "location_id"})
                for observation in event.observations:
                    observer = roster.get(observation.character_id)
                    actor = roster.get(event.actor_id)
                    if (observer is None or observer.status != "active" or observer.id not in scene.active_character_ids + [item.id for item in resolved.spawned_characters] or locations[observer.id] is None
                            or locations[observer.id] != (scene.location_id or db.location_identifier(scene.location))
                            or (observation.modality == "saw" and actor and actor.visibility_state == "hidden" and actor.id != observer.id)):
                        raise ValueError("Situation observation crosses presence or visibility boundary")
            world_maps = {key: {item["id"] if key != "relationships" else item["character_a"] + "|" + item["character_b"]: item
                                for item in value} for key, value in candidate_world_state.items()}
            await apply_resolved_changes(story_id, resolved.state_changes, roster,
                                         {key for key, character in roster.items() if is_present(character, scene)}, scene.location, world_maps)
            for change in resolved.state_changes:
                if change.entity in {"item", "relationship"}:
                    item = world_maps["items" if change.entity == "item" else "relationships"][change.entity_id]
                    item[change.field] = change.value
                    if change.entity == "item" and change.field in {"holder_character_id", "location_id"}:
                        item["location_id" if change.field == "holder_character_id" else "holder_character_id"] = None
            for update in resolved.character_state_updates:
                character = roster.get(update.character_id)
                if character is None or (character.status == "dead" and update.status not in {None, "dead"}):
                    raise ValueError("Invalid situation character update")
                for field in ("physical_state", "mental_state", "status"):
                    if getattr(update, field) is not None:
                        setattr(character, field, getattr(update, field))
            if resolved.location:
                scene.location, scene.location_id = resolved.location.name, resolved.location.id
            if resolved.active_character_ids is not None:
                if not set(resolved.active_character_ids) <= roster.keys():
                    raise ValueError("Situation scene contains unknown actor")
                scene.active_character_ids = resolved.active_character_ids
            elif resolved.spawned_characters:
                scene.active_character_ids += [item.id for item in resolved.spawned_characters]
            advance_runtime(resolved)
            return resolved

        async def resolve_situation(fresh, previous, budget):
            progress_queue.put_nowait({"phase": "situation_resolution", "message": "Tilanneohjaaja ratkaisee havainnot ja seuraavat reaktiot..."})
            return await SituationAgent(interaction_llm).resolve(story_id, scene, fresh, previous, runtime,
                roster, candidate_world_state, {"direction": plan.direction, "stop_condition": plan.stop_condition,
                                              "player_id": player.id if mode == "roleplay" and player else None,
                                              "secret_truths": bible["secret_truths"], "clocks": bible["clocks"]}, budget)

        async def checkpoint_chain(chain_intentions, chain_outcomes, budget_audit):
            candidate_private_intentions[:] = chain_intentions
            await turn_store.save_resolver_candidate(story_id, request_id, revision, fingerprint,
                {"revision": revision, "intentions": chain_intentions,
                 "intermediate_outcomes": [item.model_dump() for item in chain_outcomes],
                 "runtime": runtime, "roster": {key: value.model_dump() for key, value in roster.items()},
                 "scene": scene.model_dump(), "budget": budget_audit,
                 "turn_plan": plan.model_dump()}, "collecting")

        if groups:
            yield {"type": "phase", "phase": "characters_thinking", "message": "Bounded decision groups...",
                   "group_index": 0, "group_count": len(groups), "group_mode": groups[0].mode}
        if adaptive:
            if len(groups) > 1:
                raise ValueError("Adaptive planner supplies only the initial group")
            collection_task = asyncio.create_task(collect_adaptive(
                groups[0] if groups else None, decide, resolve_situation, accept_situation, roster, scene,
                player.id if mode == "roleplay" and player else None, adaptive_budget,
                initial_events=plan.events, seed_intentions=intentions, checkpoint=checkpoint_chain))
            progress_task = None
            try:
                while not collection_task.done():
                    progress_task = asyncio.create_task(progress_queue.get())
                    done, _ = await asyncio.wait({collection_task, progress_task}, return_when=asyncio.FIRST_COMPLETED)
                    if progress_task in done:
                        progress = progress_task.result()
                        yield {"type": "phase", "phase": "character_complete", "message": "Aie valmis", **progress}
                    else:
                        progress_task.cancel()
                        await asyncio.gather(progress_task, return_exceptions=True)
                decisions, public_starts, intermediate_outcomes, groups_used, group_player_stop = await collection_task
            finally:
                for task in (collection_task, progress_task):
                    if task and not task.done():
                        task.cancel()
                await asyncio.gather(*[task for task in (collection_task, progress_task) if task], return_exceptions=True)
            intentions = []
            plan_warnings.append("Interaction stopped: " + adaptive_budget.stop_reason)
        else:
            decisions, public_starts, intermediate_outcomes, groups_used, group_player_stop = await collect_groups(
                groups, decide, roster, player.id if mode == "roleplay" and player else None, resolve_intermediate, scene=scene)
        for decision in decisions:
            if decision.get("goal_update"):
                roster[decision["character_id"]].current_goal = decision["goal_update"]
            intentions.append(decision)
        while not progress_queue.empty():
            progress = progress_queue.get_nowait()
            yield {"type": "phase", "phase": "character_complete", "message": "Aie valmis", **progress}
        for intention in intentions:
            intention.setdefault("id", uuid4().hex)
        yield {"type": "phase", "phase": "prose_synthesis", "message": "Kertoja ratkaisee tapahtumat ja kirjoittaa jatkon..."}
        combined_bible = {field: bible[field] + [item.model_dump() for item in getattr(plan.bible_additions, field)]
                          for field in ("secret_truths", "clocks", "offscreen_agents")}
        if adaptive:
            from core.schemas import InteractionProse
            from engine.interaction_history import accepted_outcome
            outcome = accepted_outcome(plan, intermediate_outcomes, initial_runtime, scene)
            from core.schemas import AttemptResult
            resolved_ids = {item.intent_id for item in outcome.attempt_results}
            outcome.attempt_results += [AttemptResult(intent_id=item["id"], status="pending", summary="Open at interaction boundary")
                                        for item in intentions if item["id"] not in resolved_ids]
            draft_audit = {"revision": revision, "intentions": intentions,
                           "intermediate_outcomes": [item.model_dump() for item in intermediate_outcomes],
                           "accepted_candidate": outcome.model_dump(), "budget": adaptive_budget.audit()}
            await turn_store.save_resolver_candidate(story_id, request_id, revision, fingerprint, draft_audit, "rendering")
            for render_attempt in range(2):
                render_runtime = runtime | {"render_validation_error": draft_audit.get("render_error", "")}
                draft = await self.director.render_interaction(story_id, outcome, scene, render_runtime,
                    "\n\n".join(turn.director_prose for turn in turns[-3:]), intentions)
                draft_audit["candidate"] = draft
                await turn_store.save_resolver_candidate(story_id, request_id, revision, fingerprint, draft_audit, "rendering")
                try:
                    rendered = InteractionProse.model_validate(draft)
                    if rendered.consistency_issues:
                        raise ValueError("Narrative contradicts accepted interaction events")
                    break
                except ValueError as error:
                    draft_audit["render_error"] = str(error)
                    if render_attempt:
                        raise
            outcome.prose = rendered.prose
            outcome.choices = rendered.choices
            outcome.chapter_title = runtime.get("chapter_title") or rendered.chapter_title
            outcome.image_prompt = rendered.image_prompt
            raw = outcome.model_dump()
        else:
            raw = await self.director.synthesize_turn_prose(
                story_id=story_id, scene=scene, all_character_intentions=intentions,
                recent_prose_context="\n\n".join(turn.director_prose for turn in turns[-3:])[-12000:],
                director_guidance=director_guidance, tone_profile=meta.tone_profile,
                custom_tone_override=meta.custom_tone_override, mode=mode,
                reader_wish=user_input if mode != "roleplay" else None,
                runtime=runtime, characters=list(roster.values()),
                player_character_id=player.id if mode == "roleplay" and player else None,
                turn_plan=plan.model_dump() | {"reaction_decisions": reaction_decisions,
                    "public_starts": public_starts,
                    "accepted_intermediate_events": [event.model_dump() for item in intermediate_outcomes for event in item.events],
                    "accepted_attempt_results": [result.model_dump() for item in intermediate_outcomes for result in item.attempt_results],
                    "truths": combined_bible["secret_truths"], "clocks": combined_bible["clocks"],
                    "offscreen_agents": combined_bible["offscreen_agents"],
                    "items": initial_world["items"], "relationships": initial_world["relationships"],
                    "locations": initial_world["locations"]})
        candidate_roster = {identifier: character.model_dump() for identifier, character in roster.items()}
        async def validate_candidate(raw):
            nonlocal roster
            roster = {identifier: Character.model_validate(value) for identifier, value in candidate_roster.items()}
            outcome = ProseTurnResponse.model_validate(raw)
            if not outcome.summary:
                for key, value in merge_continuity(outcome, runtime).items():
                    setattr(outcome, key, value)
            assign_event_ids(outcome.events, consequence_links(outcome))
            resolver_event_ids = {event.id for event in outcome.events}
            resolved_intent_ids = {item.intent_id for resolved in intermediate_outcomes for item in resolved.attempt_results if item.status != "pending"}
            if any(event.intent_id in resolved_intent_ids for event in outcome.events if event.intent_id):
                raise ValueError("Final resolver may not replay an already resolved intermediate attempt")
            validate_bible_additions(outcome.bible_additions, combined_bible, roster)
            outcome.scene_location = outcome.scene_location or scene.location
            outcome.scene_goal = outcome.scene_goal or scene.scene_goal
            if runtime.get("chapter_title"):
                outcome.chapter_title = runtime["chapter_title"]
            spawned = []
            for candidate in outcome.spawned_characters:
                if candidate.id in roster or not candidate.id or not all(char.isalnum() or char in "_-" for char in candidate.id):
                    raise ValueError("Kertoja palautti päällekkäisen tai virheellisen hahmotunnisteen.")
                character = Character(**candidate.model_dump(), status="active")
                character.is_player_controlled = False
                if "location_id" not in candidate.model_fields_set:
                    character.location_id = scene.location_id or db.location_identifier(scene.location)
                roster[character.id] = character
                spawned.append(character)
            candidate_world, _entity_mapping = await normalize_additions(story_id, outcome, roster)
            if outcome.location:
                location_id = outcome.location.id
                if location_id != db.location_identifier(outcome.location.name) and not (location_id in candidate_world["locations"] and candidate_world["locations"][location_id]["name"] == outcome.location.name):
                    raise ValueError("Paikan tunniste ei vastaa sen nimea.")
            validate_simulation_outcome(outcome, intentions, runtime, roster)
            if expired_clock_ids and not reaction_decisions:
                elapsed_beats = plan.elapsed_time.clock_beats if plan.elapsed_time else outcome.elapsed_time.clock_beats
                if any(clocks[identifier]["remaining_beats"] - elapsed_beats - requested_ticks.get(identifier, 0) > 0 for identifier in expired_clock_ids):
                    raise ValueError("Elapsed time contradicts an already planned clock expiration")
            current_location_id = scene.location_id or db.location_identifier(scene.location)
            allowed_witnesses = {
                identifier for identifier in set(scene.active_character_ids) | {character.id for character in spawned}
                if roster[identifier].location_id == current_location_id
            }
            intention_ids = {intent["character_id"] for intent in intentions}
            supplied_intentions = {intent["id"]: intent for intent in intentions}
            accepted_events = []
            event_locations = {identifier: character.location_id for identifier, character in roster.items()}
            for event in outcome.events:
                arrivals = {change.entity_id: change.value for change in outcome.state_changes
                            if change.event_id == event.id and change.entity == "character" and change.field == "location_id"}
                event_allowed = {identifier for identifier, location in event_locations.items() if location == current_location_id}
                event_allowed.update(identifier for identifier, location in arrivals.items() if location == current_location_id)
                event_locations.update(arrivals)
                if reaction_decisions and mode == "roleplay" and player and (
                    event.actor_id == player.id or event.derived_from == f"intent:{player.id}"
                ):
                    raise ValueError("Lisäreaktio ei saa luoda pelaajan toimintaa.")
                if not set(event.witnesses) <= roster.keys():
                    raise ValueError("Tapahtuman havaitsija ei ole tunnettu hahmo.")
                if not set(event.witnesses) <= event_allowed:
                    logger.warning("Removed out-of-scene witnesses from resolver event %s", event.id)
                    event.observations = [observation for observation in event.observations if observation.character_id in event_allowed]
                event.observations = [observation for observation in event.observations
                                      if roster[observation.character_id].status not in {"dead", "unconscious"}
                                      and not (observation.modality == "saw" and event.actor_id in roster
                                               and roster[event.actor_id].visibility_state == "hidden"
                                               and event.actor_id != observation.character_id)]
                if event.derived_from.startswith("intent:"):
                    actor_id = event.derived_from.split(":", 1)[1]
                    if actor_id not in intention_ids:
                        raise ValueError("Tapahtuman aikomuslähde ei vastaa hahmokutsua.")
                    if event.actor_id and event.actor_id != actor_id:
                        raise ValueError("Tapahtuman tekijä ei vastaa aikomuslähdettä.")
                    event.actor_id = actor_id
                    supplied = supplied_intentions.get(event.intent_id)
                    if not supplied or supplied["character_id"] != actor_id:
                        raise ValueError("Tapahtuman aieviite ei vastaa taman vuoron aietta.")
                elif event.derived_from == "routine":
                    supplied = supplied_intentions.get(event.intent_id)
                    if not supplied or event.actor_id != supplied["character_id"]:
                        raise ValueError("Rutiini ei vastaa taman vuoron valtuutettua aietta.")
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
            for phase in range(len(intermediate_outcomes) + 1):
                for start in public_starts:
                    if start.get("resolution_phase", len(intermediate_outcomes)) != phase:
                        continue
                    final_events.append(StoryEvent(
                        id=uuid4().hex, description=start["text"], derived_from="intent:" + start["actor_id"],
                        actor_id=start["actor_id"], intent_id=start["intent_id"], change_kind="none",
                        observations=[{"character_id": identifier, "text": start["text"], "modality": start["modality"]}
                                      for identifier in start["observer_ids"]]))
                if phase < len(intermediate_outcomes):
                    final_events.extend(intermediate_outcomes[phase].events)
            final_changes = list(outcome.state_changes)
            final_character_updates = list(outcome.character_state_updates)
            from engine.interaction_history import merge_intermediate_history
            merge_intermediate_history(outcome, intermediate_outcomes, initial_runtime)
            for event in accepted_events:
                if event not in final_events:
                    final_events.append(event)
            outcome.events = final_events
            validate_event_links(outcome.events, consequence_links(outcome))
            mutation_roster = {identifier: Character.model_validate(value) for identifier, value in candidate_roster.items()}
            mutation_roster.update({character.id: character for character in spawned})
            for update in final_character_updates:
                if update.character_id not in roster:
                    raise ValueError("Tilapäivitys viittaa tuntemattomaan hahmoon.")
                character = mutation_roster[update.character_id]
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
            if outcome.scene_location != scene.location:
                final_location_id = outcome.location.id if outcome.location else db.location_identifier(outcome.scene_location)
                for identifier in outcome.active_character_ids:
                    if roster[identifier].location_id is not None:
                        roster[identifier].location_id = final_location_id
            # Each intermediate is validated against its own prior state; final changes are new consequences.
            for identifier, character in mutation_roster.items():
                roster[identifier].physical_state = character.physical_state
                roster[identifier].mental_state = character.mental_state
                roster[identifier].status = character.status
            resolved_progress = await apply_resolved_changes(
                story_id, final_changes, roster, set(allowed_witnesses), outcome.scene_location, candidate_world)
            for access in outcome.truth_access_updates:
                if access.truth_id not in truths:
                    raise ValueError("Löytöreitin päivitys viittaa tuntemattomaan totuuteen.")
                if access.related_location_id is not None and access.related_location_id != db.location_identifier(outcome.scene_location):
                    if access.related_location_id not in candidate_world["locations"] and not await db.location_exists(story_id, access.related_location_id):
                        raise ValueError("Löytöreitin päivitys viittaa tuntemattomaan paikkaan.")
            return outcome, spawned, allowed_witnesses, resolver_event_ids, resolved_progress

        candidate_audit = {"revision": revision, "intentions": intentions, "candidate": raw,
                           "public_starts": public_starts, "intermediate_outcomes": [item.model_dump() for item in intermediate_outcomes],
                           "validation_errors": [], "stages": ["model_call"]}
        for repair_attempt in range(0 if adaptive else 2):
            try:
                outcome, spawned, allowed_witnesses, resolver_event_ids, resolved_progress = await validate_candidate(raw)
                candidate_audit["stages"].extend(["structural_validation", "semantic_validation"])
                break
            except ValueError as error:
                errors = error.errors(include_url=False, include_context=False) if hasattr(error, "errors") else [{"loc": ["response"], "msg": str(error), "type": "contract"}]
                candidate_audit["validation_errors"].append(errors)
                await turn_store.save_resolver_candidate(story_id, request_id, revision, fingerprint, candidate_audit, "failed" if repair_attempt else "repair_pending")
                if repair_attempt:
                    raise
                candidate_audit["stages"].append("repair")
                try:
                    raw = await self.director.repair_turn_response(story_id, candidate_audit, runtime)
                except BaseException as repair_error:
                    candidate_audit["repair_error"] = str(repair_error)
                    await turn_store.save_resolver_candidate(story_id, request_id, revision, fingerprint, candidate_audit, "failed")
                    raise
                candidate_audit["repaired_candidate"] = raw
        if adaptive:
            spawned = [roster[item.id] for item in outcome.spawned_characters]
            allowed_witnesses = {identifier for identifier, character in roster.items() if is_present(character, scene)}
            resolver_event_ids = {event.id for event in outcome.events}
            resolved_progress = bool(outcome.state_changes)
            candidate_audit.update(budget=adaptive_budget.audit(), stages=["accepted_chain", "narrative_render"])
            outcome.scene_stop = True
            outcome.requires_player_input = outcome.requires_player_input or adaptive_budget.stop_reason == "player"
        elif group_player_stop:
            outcome.requires_player_input = True
            outcome.scene_stop = True
        progress_events = outcome.events
        if reaction_decisions:
            prior_descriptions = await turn_store.get_event_descriptions(story_id)
            progress_events = [event for event in outcome.events
                               if event.description.strip().casefold() not in prior_descriptions]
        objective_progress = concrete_progress(
            before_characters, roster, progress_events, planned_progress or resolved_progress)
        if reaction_decisions and not objective_progress:
            yield {"type": "phase", "phase": "extra_reaction_stopped", "message": "Lisäreaktio ei edennyt konkreettisesti; vain ensimmäinen vuoro säilytettiin."}
            return
        pending_reactions = []
        if extra_reaction_cycle:
            prior_descriptions = await turn_store.get_event_descriptions(story_id)
            prior_descriptions.update(event.description.strip().casefold() for event in plan.events)
            pending_reactions = [item.model_dump() for item in eligible_reaction_decisions(
                outcome, roster, scene, mode, objective_progress, resolver_event_ids, prior_descriptions
            )]
        for intention in intentions:
            roster[intention["character_id"]].last_active_turn = turn_index
        player_views = {}
        player_view_statuses = {}
        player_view_errors = {}
        stored_characters = await db.get_all_characters(story_id)
        selected_viewpoint = next((character for character in stored_characters if character.is_player_controlled), None)
        viewpoint_character = roster.get(selected_viewpoint.id) if selected_viewpoint else None
        own_intention = {}
        if viewpoint_character:
            player_view_statuses[viewpoint_character.id] = "view_pending"
            own_intention = next((intention for intention in intentions if intention["character_id"] == viewpoint_character.id), {})
        action = "\n".join(f"[{intention['character_name']}]: {intention['action']} {intention.get('speech', '')}".strip() for intention in intentions)
        monologue = "\n".join(f"[{intention['character_name']}]: {intention['private_thought']}" for intention in intentions)
        response = TurnResponse(
            turn_index=turn_index, mode=mode, request_id=request_id,
            elapsed_time=outcome.elapsed_time.model_dump(), attempt_results=[item.model_dump() for item in outcome.attempt_results],
            commitments=[item.model_dump() for item in outcome.commitments], decision_groups_used=groups_used, scene_stop=outcome.scene_stop,
            extra_reaction_cycles=1 if reaction_decisions else 0,
            acting_character=player.model_dump() if mode == "roleplay" and player and not reaction_decisions else None,
            internal_monologue=monologue, character_action=action, director_prose=outcome.prose,
            choices=outcome.choices, image_prompt=outcome.image_prompt,
            updated_characters=list(roster.values()), spawned_characters=spawned,
            story_text_snippet=outcome.prose, is_chapter_end=outcome.chapter_end,
            requires_player_input=outcome.requires_player_input or mode == "roleplay",
            player_view_status="view_pending" if viewpoint_character else None,
            warnings=list(plan_warnings)
        )
        turn = SceneTurn(scene_id=scene.id, turn_index=turn_index,
                         acting_character_id=player.id if mode == "roleplay" and player and not reaction_decisions else None,
                         internal_monologue=monologue, character_action=action,
                         director_prose=outcome.prose, choices=outcome.choices, image_prompt=outcome.image_prompt)
        yield {"type": "phase", "phase": "saving", "message": "Tarkistetaan vastaus ja tallennetaan vuoro..."}
        await turn_store.commit_turn(story_id, last_id, turn, list(roster.values()), outcome, response, fingerprint,
            {"mode": mode, "user_input": user_input, "private_intention": private_intention,
             "turn_plan": plan.model_dump(),
             "player_views": player_views,
             "player_view_statuses": player_view_statuses,
             "player_view_errors": player_view_errors,
             "objective_progress": objective_progress,
             "extra_reaction_cycle": extra_reaction_cycle,
             "reaction_decisions": reaction_decisions,
             "interaction_budget": adaptive_budget.audit() if adaptive else None,
             "skip_clock_tick": bool(reaction_decisions),
             "director_guidance": director_guidance, "director_model": settings.DIRECTOR_MODEL,
             "character_model": settings.CHARACTER_MODEL, "intentions": intentions,
             "contract_version": 3, "resolver_audit": candidate_audit,
             "context_manifest": {"prose_turn_ids": [turn.id for turn in turns[-3:] if turn.id is not None],
                                  "runtime_fields": ["summary", "world_facts", "plot_threads", "commitments", "attempt_results"],
                                  "location_ids": [item["id"] for item in initial_world["locations"]]},
             "plot_guidance": plot_guidance, "decision_budget": decision_budget,
             "prompt_hashes": {path: hashlib.sha256(prompt_loader.get_raw_prompt(path).encode()).hexdigest()
                for path in ("director/plan_turn.txt", "director/synthesize_prose.txt", "director/player_view.txt", f"director/mode_{mode}.txt", "character/decide_action.txt", "language_directive.txt", "safety_directive.txt", f"tone_profiles/{meta.tone_profile}.txt")}},
            expected_revision=revision)
        response.failure_options = await turn_store.get_failure_options(story_id)
        await turn_store.update_receipt_response(story_id, request_id, response)
        if viewpoint_character:
            yield {"type": "phase", "phase": "player_view", "message": "Vuoro tallennettiin; muodostetaan hahmon tietorajattu näkökulma..."}
            for attempt in range(2):
                try:
                    player_views[viewpoint_character.id] = await self.director.create_player_view(
                        story_id, viewpoint_character, outcome, own_intention, runtime,
                        outcome.scene_location, meta.tone_profile, meta.custom_tone_override)
                    response.player_view_status = "view_ready"
                    break
                except Exception as exc:
                    if attempt == 0:
                        logger.warning("Player view generation failed after committed turn %s; retrying once: %s",
                                       turn_index, exc)
                        continue
                    logger.warning("Player view generation failed after retrying committed turn %s: %s", turn_index, exc)
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
        yield {"type": "turn_complete", "data": response.model_dump(), "pending_reactions": pending_reactions}

    async def advance_turn(self, story_id: str, user_input: Optional[str] = None,
                           mode: str = "novel", director_guidance: Optional[str] = None,
                           private_intention: Optional[str] = None, request_id: Optional[str] = None,
                           extra_reaction_cycle: bool = False, plot_guidance: Optional[str] = None,
                           decision_budget: Optional[int] = None, expected_revision: Optional[int] = None) -> TurnResponse:
        async for event in self.advance_turn_streaming(story_id, user_input, mode, director_guidance, private_intention, request_id, extra_reaction_cycle, plot_guidance, decision_budget, expected_revision):
            if event["type"] == "turn_complete":
                return TurnResponse.model_validate(event["data"])
        raise RuntimeError("Vuoro ei valmistunut.")