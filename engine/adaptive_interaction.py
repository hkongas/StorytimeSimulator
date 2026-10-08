import asyncio
import copy
import time
from collections import Counter
from dataclasses import dataclass, field
from uuid import uuid4

from core.schemas import (AttemptResult, ProseTurnResponse, ReactionGroup, SituationResponse,
                          StoryEvent)
from engine.simulation_contract import is_present
from engine.interaction_llm import InteractionTokenLimit


def as_outcome(response):
    data = response.model_dump(exclude={"next_group", "relay_permit", "stop_reason", "reason"})
    return ProseTurnResponse(prose="Candidate events; not narrative history", **data,
                             scene_stop=response.stop_reason in {"ended", "waiting", "frame_exhausted"},
                             requires_player_input=response.stop_reason == "player")


@dataclass
class InteractionBudget:
    decision_limit: int = 12
    call_limit: int = 8
    character_limit: int = 4
    seconds: float = 120
    token_limit: int = 48000
    decisions: int = 0
    calls: int = 0
    tokens: int = 0
    started: float = field(default_factory=time.monotonic)
    per_character: Counter = field(default_factory=Counter)
    stop_reason: str = ""

    def allow(self, actors=(), controller=False):
        if time.monotonic() - self.started >= self.seconds:
            self.stop_reason = "time_budget"
        elif self.tokens >= self.token_limit:
            self.stop_reason = "token_budget"
        elif controller and self.calls >= self.call_limit:
            self.stop_reason = "controller_budget"
        elif self.decisions + len(actors) > self.decision_limit:
            self.stop_reason = "decision_budget"
        elif any(self.per_character[actor] >= self.character_limit for actor in actors):
            self.stop_reason = "character_budget"
        return not self.stop_reason

    def audit(self):
        return {"decisions": self.decisions, "controller_calls": self.calls,
                "tokens": self.tokens, "elapsed_seconds": time.monotonic() - self.started,
                "stop_reason": self.stop_reason, "per_character": dict(self.per_character)}


def environment_signature(roster, scene):
    return (scene.location_id, scene.location, tuple(scene.active_character_ids),
            tuple((key, item.location_id, item.status, item.visibility_state)
                  for key, item in sorted(roster.items())))


def validate_reactions(group, events, consumed, roster, scene):
    if group is None:
        return []
    actors = []
    for reaction in group.reactions:
        event = events.get(reaction.event_id)
        actor = roster.get(reaction.character_id)
        key = (reaction.character_id, reaction.event_id)
        if actor is None or event is None or not event.observation_for(reaction.character_id):
            raise ValueError("Reaction requires a verified observation for its actor")
        if key in consumed or reaction.character_id in actors:
            raise ValueError("Reaction stimulus already consumed or duplicate group actor")
        if actor.status != "active" or actor.id not in scene.active_character_ids or not is_present(actor, scene):
            raise ValueError("Reaction actor is absent or incapable")
        actors.append(actor.id)
    return actors


def verify_permit(permit, events, roster, scene):
    source = events.get(permit.source_event_id)
    participants = permit.participant_ids
    if len(set(participants)) != len(participants) or source is None:
        raise ValueError("Relay permit has duplicate participants or unknown source")
    for identifier in participants:
        actor = roster.get(identifier)
        if (actor is None or actor.status != "active" or actor.id not in scene.active_character_ids
                or not is_present(actor, scene) or actor.visibility_state != "visible"
                or not source.observation_for(identifier)):
            raise ValueError("Relay permit requires present visible participants with verified source observations")
    if any(observation.modality != "heard" for observation in source.observations
           if observation.character_id in participants):
        raise ValueError("Relay source must verify the hearing channel")


def relay_response(decisions, permit, signature, roster, scene):
    if not permit or environment_signature(roster, scene) != signature or len(decisions) != 1:
        return None
    decision = decisions[0]
    if (decision.get("interaction_kind") != "speech" or decision.get("resolution_hint", True)
            or not decision.get("speech") or decision.get("public_start")
            or decision.get("volume", "normal") != permit.volume
            or decision["character_id"] not in permit.participant_ids
            or not set(decision.get("suggested_recipient_ids", [])) <= set(permit.participant_ids)):
        return None
    # The permit, not the actor's suggestions, determines the actual listeners.
    event = StoryEvent(description=decision["speech"], actor_id=decision["character_id"],
                       intent_id=decision["id"], derived_from="intent:" + decision["character_id"],
                       observations=[{"character_id": identifier, "text": decision["speech"], "modality": "heard"}
                                     for identifier in permit.participant_ids])
    receivers = [identifier for identifier in permit.participant_ids if identifier != decision["character_id"]]
    return SituationResponse(events=[event], attempt_results=[AttemptResult(
        intent_id=decision["id"], event_id=event.id, status="succeeded", summary="Complete utterance delivered")],
        next_group=ReactionGroup(reactions=[{"decision_kind": "meaningful_choice", "event_id": event.id,
                                            "character_id": identifier, "decision": "Respond or remain silent to the new utterance"}
                                           for identifier in receivers]), stop_reason="continue",
        recap_delta=decision["speech"][:1200])


async def collect_adaptive(initial, decide, resolve, accept, roster, scene, player_id=None,
                           budget=None, initial_events=(), seed_intentions=(), checkpoint=None):
    budget = budget or InteractionBudget()
    intentions, outcomes, events = list(seed_intentions), [], {event.id: event for event in initial_events}
    consumed = set()
    permit, permit_signature, permit_remaining = None, None, 0
    group = initial
    reactions = None
    batches = 0
    stopped = False

    async def save():
        if checkpoint:
            await checkpoint(intentions, outcomes, budget.audit() | {
                "next_group": reactions.model_dump() if reactions else None,
                "consumed_stimuli": sorted(consumed),
                "relay_permit": permit.model_dump() if permit else None,
                "relay_remaining": permit_remaining,
                "initial_group": group.model_dump() if group else None})

    async def run_resolution(fresh):
        nonlocal permit, permit_signature, permit_remaining, reactions, stopped
        if not budget.allow(controller=True):
            stopped = True
            return
        budget.calls += 1
        remaining = max(0.001, budget.seconds - (time.monotonic() - budget.started))
        try:
            response = SituationResponse.model_validate(await asyncio.wait_for(resolve(fresh, outcomes, budget), remaining))
        except (TimeoutError, InteractionTokenLimit) as error:
            budget.stop_reason = "token_budget" if isinstance(error, InteractionTokenLimit) else "time_budget"
            stopped = True
            await save()
            return
        outcome = await accept(response, fresh, outcomes)
        outcomes.append(outcome)
        events.update({event.id: event for event in outcome.events})
        reactions = response.next_group
        if response.relay_permit:
            verify_permit(response.relay_permit, events, roster, scene)
            permit = response.relay_permit
            permit_signature = environment_signature(roster, scene)
            permit_remaining = permit.max_utterances
        else:
            permit = None
        if response.stop_reason == "continue" and response.next_group is None:
            raise ValueError("Continuing situation requires a next reaction group")
        stopped = response.stop_reason != "continue" or response.chapter_end or response.failure_policy != "continue"
        if stopped:
            budget.stop_reason = response.stop_reason
        await save()

    if seed_intentions:
        await save()
        await run_resolution(list(seed_intentions))
        if reactions:
            group = None
    while not stopped and (group is not None or reactions is not None):
        if reactions:
            actors = validate_reactions(reactions, events, consumed, roster, scene)
            mode = reactions.mode
        else:
            actors = list(group.character_ids)
            mode = group.mode
        if mode == "sequential" and len(actors) > 1:
            raise ValueError("Adaptive sequential groups contain one actor; select the next actor after verified outcomes")
        if (group and group.stop_for_player) or player_id in actors:
            budget.stop_reason = "player"
            stopped = True
            break
        if any(identifier not in roster or roster[identifier].status != "active"
               or identifier not in scene.active_character_ids or not is_present(roster[identifier], scene)
               for identifier in actors):
            budget.stop_reason = "ineligible"
            stopped = True
            break
        if not budget.allow(actors) or (not permit_remaining and not budget.allow(controller=True)):
            stopped = True
            break
        if reactions:
            consumed.update((item.character_id, item.event_id) for item in reactions.reactions)
        budget.decisions += len(actors)
        budget.per_character.update(actors)
        batches += 1
        # Lock both the roster and all observations before starting any concurrent call.
        locked_roster = {identifier: roster[identifier].model_copy(deep=True) for identifier in actors}
        locked_outcomes = copy.deepcopy(outcomes)
        async def call(identifier):
            remaining = max(0.001, budget.seconds - (time.monotonic() - budget.started))
            visible_outcomes = [ProseTurnResponse(prose="Observation-only candidate view", events=[
                event.model_copy(update={"description": event.observation_for(identifier),
                    "observations": [observation for observation in event.observations if observation.character_id == identifier]}, deep=True)
                for event in item.events if event.observation_for(identifier)]) for item in locked_outcomes]
            decision = await asyncio.wait_for(decide(locked_roster[identifier], [], visible_outcomes), remaining)
            decision.setdefault("id", uuid4().hex)
            return decision
        await save()
        tasks = [asyncio.create_task(call(identifier)) for identifier in actors] if mode == "parallel" else []
        try:
            fresh = await asyncio.gather(*tasks) if tasks else [await call(identifier) for identifier in actors]
        except (TimeoutError, InteractionTokenLimit) as error:
            budget.stop_reason = "token_budget" if isinstance(error, InteractionTokenLimit) else "time_budget"
            stopped = True
            break
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        intentions.extend(fresh)
        await save()
        response = relay_response(fresh, permit if permit_remaining else None, permit_signature, roster, scene)
        if response is not None:
            permit_remaining -= 1
            outcome = await accept(response, fresh, outcomes)
            outcomes.append(outcome)
            events.update({event.id: event for event in outcome.events})
            reactions = response.next_group
            await save()
        else:
            await run_resolution(fresh)
        group = None
    if not budget.stop_reason:
        budget.stop_reason = "ended"
    if reactions and outcomes:
        outcomes[-1].pending_reaction_decisions = reactions.reactions
    await save()
    return intentions, [], outcomes, batches, stopped
