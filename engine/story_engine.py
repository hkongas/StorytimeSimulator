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

    async def create_character_catchup(self, story_id: str, character_id: str, expected_revision: int) -> dict:
        async with self._locks.setdefault(story_id, asyncio.Lock()):
            revision = await turn_store.get_revision(story_id)
            if revision != expected_revision:
                raise turn_store.TurnConflictError("Tarina muuttui. Lataa se uudelleen.")
            character = await db.get_character(story_id, character_id)
            scene = await db.get_active_scene(story_id)
            if not character or not character.is_player_controlled or character.status != "active" or not scene or character_id not in scene.active_character_ids:
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
            observations = {}
            for character in result["characters"]:
                perceived = []
                for event in events:
                    if character.id in event.witnesses:
                        perceived.append(event.observation_for(character.id))
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
        request_id: Optional[str] = None, extra_reaction_cycle: bool = False
    ) -> AsyncIterator[dict[str, Any]]:
        db.get_story_dir(story_id)
        request_id = request_id or uuid4().hex
        if mode == "director":
            director_guidance = director_guidance or user_input
            user_input = None
        mode = normalize_mode(mode)
        fingerprint = self._advance_fingerprint(mode, user_input, director_guidance, private_intention, extra_reaction_cycle)
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
                extra_reaction_cycle=extra_reaction_cycle
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
    def _advance_fingerprint(mode, user_input, director_guidance, private_intention, extra_reaction_cycle=False):
        payload = [mode, user_input, director_guidance, private_intention]
        if extra_reaction_cycle:
            payload.append(True)
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()

    async def _advance_cycle_streaming(
        self, story_id: str, user_input: Optional[str] = None, mode: str = "novel",
        director_guidance: Optional[str] = None, private_intention: Optional[str] = None,
        request_id: Optional[str] = None, extra_reaction_cycle: bool = False,
        reaction_decisions: Optional[list[dict[str, Any]]] = None
    ) -> AsyncIterator[dict[str, Any]]:
        db.get_story_dir(story_id)
        if mode == "director":
            director_guidance = director_guidance or user_input
            user_input = None
        mode = normalize_mode(mode)
        request_id = request_id or uuid4().hex
        fingerprint = self._advance_fingerprint(mode, user_input, director_guidance, private_intention, extra_reaction_cycle)
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
        before_characters = {identifier: character.model_dump() for identifier, character in roster.items()}
        initial_world = await db.get_planning_world(story_id)
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
            if not reaction_decisions and clock["remaining_beats"] > 0 and clock["remaining_beats"] - 1 - requested_ticks.get(clock_id, 0) <= 0:
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
            "character": {"location_id", "physical_state", "mental_state", "status"},
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
        event_location_id = db.location_identifier(scene.location)
        present_ids = {
            character.id for character in roster.values()
            if character.id in scene.active_character_ids
            and character.location_id in {None, event_location_id}
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
                   and character.status == "active" and character.location_id in {None, event_location_id}]
        if not set(plan.decision_character_ids) <= {character.id for character in present}:
            raise ValueError("Suunnitelma pyytää päätöstä toimintakyvyttömältä hahmolta.")
        if mode == "roleplay" and player and player.id in plan.decision_character_ids:
            raise ValueError("Suunnitelma ei saa päättää pelaajan puolesta.")
        if mode == "simulation" and not reaction_decisions:
            plan.decision_character_ids = [character.id for character in present]
        intentions = []
        if mode == "roleplay" and player and player in present and not reaction_decisions:
            intentions.append({"character_id": player.id, "character_name": player.name,
                               "action": user_input or "Odotan ja tarkkailen.", "speech": "",
                               "private_thought": private_intention or ""})
        decision_ids = set(plan.decision_character_ids)
        acting = [character for character in present
                  if not (mode == "roleplay" and character.is_player_controlled)
                  and character.id in decision_ids]
        semaphore = asyncio.Semaphore(self.max_concurrent_characters)
        progress_queue = asyncio.Queue()

        async def decide(character: Character):
            async with semaphore:
                observation = await turn_store.get_observation(story_id, character.id)
                new_observations = [event.observation_for(character.id) for event in plan.events
                                    if character.id in event.witnesses]
                if new_observations:
                    observation += "\n\n" + "\n".join(new_observations)
                if reaction_decisions:
                    observation += "\n\nA new verified observation now requires a fresh meaningful choice. Decide your response using only your own observations and knowledge; previous attempts are historical, not new actions."
                agent_character = character.model_copy(update={"is_player_controlled": False}) if mode != "roleplay" else character
                decision = await CharacterAgent(agent_character, self.llm).decide_intention(
                    story_id=story_id, scene_location=scene.location,
                    recent_prose_context=observation, tone_profile=meta.tone_profile,
                    custom_tone_override=meta.custom_tone_override,
                    nearby_characters=[other.name for other in present if other.id != character.id]
                )
                progress = {"character_id": character.id, "character_name": character.name}
                if mode != "roleplay":
                    progress["character_thought"] = decision["private_thought"]
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
        for intention in intentions:
            intention["id"] = uuid4().hex
        yield {"type": "phase", "phase": "prose_synthesis", "message": "Kertoja ratkaisee tapahtumat ja kirjoittaa jatkon..."}
        combined_bible = {field: bible[field] + [item.model_dump() for item in getattr(plan.bible_additions, field)]
                          for field in ("secret_truths", "clocks", "offscreen_agents")}
        raw = await self.director.synthesize_turn_prose(
            story_id=story_id, scene=scene, all_character_intentions=intentions,
            recent_prose_context="\n\n".join(turn.director_prose for turn in turns[-3:])[-12000:],
            director_guidance=director_guidance, tone_profile=meta.tone_profile,
            custom_tone_override=meta.custom_tone_override, mode=mode,
            reader_wish=user_input if mode != "roleplay" else None,
            runtime=runtime, characters=characters,
            player_character_id=player.id if mode == "roleplay" and player else None,
            turn_plan=plan.model_dump() | {"reaction_decisions": reaction_decisions,
                                            "truths": combined_bible["secret_truths"], "clocks": combined_bible["clocks"],
                                            "offscreen_agents": combined_bible["offscreen_agents"],
                                            "items": initial_world["items"], "relationships": initial_world["relationships"],
                                            "locations": initial_world["locations"]}
        )
        outcome = ProseTurnResponse.model_validate(raw)
        assign_event_ids(outcome.events, outcome.character_state_updates + outcome.state_changes + outcome.truth_access_updates
                         + ([outcome.location] if outcome.location else []) + outcome.pending_reaction_decisions)
        resolver_event_ids = {event.id for event in outcome.events}
        validate_bible_additions(outcome.bible_additions, combined_bible, roster)
        if outcome.location:
            location_id = outcome.location.id
            if location_id != db.location_identifier(outcome.location.name):
                raise ValueError("Paikan tunniste ei vastaa sen nimea.")
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
            character.location_id = db.location_identifier(scene.location)
            roster[character.id] = character
            spawned.append(character)
        current_location_id = db.location_identifier(scene.location)
        allowed_witnesses = {
            identifier for identifier in set(scene.active_character_ids) | {character.id for character in spawned}
            if roster[identifier].location_id in {None, current_location_id}
        }
        intention_ids = {intent["character_id"] for intent in intentions}
        supplied_intentions = {intent["id"]: intent for intent in intentions}
        accepted_events = []
        for event in outcome.events:
            if reaction_decisions and mode == "roleplay" and player and (
                event.actor_id == player.id or event.derived_from == f"intent:{player.id}"
            ):
                raise ValueError("Lisäreaktio ei saa luoda pelaajan toimintaa.")
            if not set(event.witnesses) <= roster.keys():
                raise ValueError("Tapahtuman havaitsija ei ole tunnettu hahmo.")
            if not set(event.witnesses) <= allowed_witnesses:
                logger.warning("Removed out-of-scene witnesses from resolver event %s", event.id)
                event.observations = [observation for observation in event.observations if observation.character_id in allowed_witnesses]
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
        for event in accepted_events:
            if event not in final_events:
                final_events.append(event)
        outcome.events = final_events
        validate_event_links(outcome.events, outcome.character_state_updates + outcome.state_changes + outcome.truth_access_updates
                             + ([outcome.location] if outcome.location else []))
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
        if outcome.scene_location != scene.location:
            final_location_id = db.location_identifier(outcome.scene_location)
            for identifier in outcome.active_character_ids:
                roster[identifier].location_id = final_location_id
        resolved_progress = await apply_resolved_changes(
            story_id, outcome.state_changes, roster, set(allowed_witnesses), outcome.scene_location)
        for access in outcome.truth_access_updates:
            if access.truth_id not in truths:
                raise ValueError("Löytöreitin päivitys viittaa tuntemattomaan totuuteen.")
            if access.related_location_id is not None and access.related_location_id != db.location_identifier(outcome.scene_location):
                if not await db.location_exists(story_id, access.related_location_id):
                    raise ValueError("Löytöreitin päivitys viittaa tuntemattomaan paikkaan.")
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
             "skip_clock_tick": bool(reaction_decisions),
             "director_guidance": director_guidance, "director_model": settings.DIRECTOR_MODEL,
             "character_model": settings.CHARACTER_MODEL, "intentions": intentions,
             "contract_version": 2,
             "prompt_hashes": {path: hashlib.sha256(prompt_loader.get_raw_prompt(path).encode()).hexdigest()
                for path in ("director/plan_turn.txt", "director/synthesize_prose.txt", "director/player_view.txt", f"director/mode_{mode}.txt", "character/decide_action.txt", "language_directive.txt", "safety_directive.txt", f"tone_profiles/{meta.tone_profile}.txt")}},
            expected_revision=revision)
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
                           extra_reaction_cycle: bool = False) -> TurnResponse:
        async for event in self.advance_turn_streaming(story_id, user_input, mode, director_guidance, private_intention, request_id, extra_reaction_cycle):
            if event["type"] == "turn_complete":
                return TurnResponse.model_validate(event["data"])
        raise RuntimeError("Vuoro ei valmistunut.")