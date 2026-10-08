import asyncio
from uuid import uuid4

from core.schemas import DecisionGroup, ProseTurnResponse
from database import db


def is_present(character, scene):
    return character.location_id is not None and character.location_id == (scene.location_id or db.location_identifier(scene.location))


def visible_neighbours(observer, present):
    return [other.name for other in present if other.id != observer.id and other.visibility_state == "visible"]


def validate_groups(plan, eligible_ids, player_id, budget):
    groups = plan.decision_groups or ([DecisionGroup(id="default", character_ids=plan.decision_character_ids)]
                                     if plan.decision_character_ids else [])
    if len(groups) > budget:
        raise ValueError("Decision group budget exceeded")
    seen, actors = set(), set()
    for group in groups:
        if group.id in seen or not set(group.depends_on) <= seen:
            raise ValueError("Decision groups have duplicate, forward or cyclic dependencies")
        if len(set(group.character_ids)) != len(group.character_ids) or actors.intersection(group.character_ids):
            raise ValueError("A character may decide only once per bounded turn")
        if not set(group.character_ids) <= eligible_ids | ({player_id} if player_id else set()):
            raise ValueError("Decision group contains an absent or incapable actor")
        if player_id in group.character_ids and not group.stop_for_player:
            raise ValueError("Decision group may not choose for the player")
        seen.add(group.id)
        actors.update(group.character_ids)
    return groups


async def collect_groups(groups, decide, roster, player_id=None, resolve_intermediate=None, scene=None):
    intentions, starts, intermediate, used = [], [], [], 0
    stopped = False
    resolved_count = 0
    all_starts = []
    for group in groups:
        if group.stop_for_player or player_id in group.character_ids:
            stopped = True
            break
        if group.requires_resolved_outcome:
            if not resolve_intermediate or not intentions:
                raise ValueError("Outcome-dependent choice requires an intermediate resolution")
            resolved = await resolve_intermediate(intentions[resolved_count:], starts, intermediate)
            resolved_count = len(intentions)
            intermediate.append(resolved)
            all_starts.extend(starts)
            starts = []
            if resolved.scene_stop or resolved.requires_player_input or resolved.chapter_end:
                stopped = True
                break
        if any(roster[identifier].status != "active" or roster[identifier].location_id is None
               or (scene is not None and (identifier not in scene.active_character_ids
                                          or not is_present(roster[identifier], scene)))
               for identifier in group.character_ids):
            stopped = True
            break
        used += 1
        if group.mode == "parallel":
            locked_starts = list(starts)
            tasks = [asyncio.create_task(decide(roster[identifier], locked_starts, intermediate)) for identifier in group.character_ids]
            try:
                decisions = await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        else:
            decisions = []
            for identifier in group.character_ids:
                decision = await decide(roster[identifier], list(starts), intermediate)
                decisions.append(decision)
                add_public_start(decision, starts, roster)
        for decision in decisions:
            decision.setdefault("id", uuid4().hex)
            intentions.append(decision)
            if group.mode == "parallel":
                add_public_start(decision, starts, roster)
    return intentions, all_starts + starts, intermediate, used, stopped


def add_public_start(decision, starts, roster):
    start = decision.get("public_start")
    if not start:
        return
    actor = roster[decision["character_id"]]
    observers = []
    for identifier in start.get("observer_ids", []):
        observer = roster.get(identifier)
        if observer is None:
            raise ValueError("Public start references an unknown observer")
        if observer.status != "active" or observer.location_id is None or observer.location_id != actor.location_id:
            continue
        if start.get("modality", "heard") == "saw" and actor.visibility_state == "hidden" and identifier != actor.id:
            continue
        observers.append(identifier)
    starts.append({"intent_id": decision.setdefault("id", uuid4().hex), "actor_id": actor.id,
                   "text": start["text"], "modality": start.get("modality", "heard"), "observer_ids": observers})


async def normalize_additions(story_id, outcome, roster):
    world = await db.get_planning_world(story_id)
    locations = {item["id"]: item for item in world["locations"]}
    items = {item["id"]: item for item in world["items"]}
    relationships = {item["character_a"] + "|" + item["character_b"]: item for item in world["relationships"]}
    mapping = {}
    for kind, additions, existing in (("location", outcome.entity_additions.locations, locations),
                                      ("item", outcome.entity_additions.items, items)):
        local_ids = set()
        for addition in additions:
            if addition.id in local_ids or addition.id in existing:
                raise ValueError("Entity creation collides with an existing or response-local identifier")
            local_ids.add(addition.id)
            persistent = kind + "_" + uuid4().hex
            mapping[kind, addition.id] = persistent
            addition.id = persistent
    for addition in outcome.entity_additions.locations:
        locations[addition.id] = addition.model_dump()
    for addition in outcome.entity_additions.items:
        addition.location_id = mapping.get(("location", addition.location_id), addition.location_id)
        if addition.holder_character_id and addition.location_id:
            raise ValueError("New item cannot have both a holder and a location")
        if addition.holder_character_id and addition.holder_character_id not in roster:
            raise ValueError("New item references an unknown holder")
        if addition.location_id and addition.location_id not in locations:
            raise ValueError("New item references an unknown location")
        items[addition.id] = addition.model_dump()
    for addition in outcome.entity_additions.relationships:
        if addition.character_a not in roster or addition.character_b not in roster or addition.character_a == addition.character_b:
            raise ValueError("New relationship references unknown or identical characters")
        key = addition.character_a + "|" + addition.character_b
        if key in relationships:
            raise ValueError("Relationship creation collides with an existing relationship")
        relationships[key] = addition.model_dump()
    for change in outcome.state_changes:
        change.entity_id = mapping.get((change.entity, change.entity_id), change.entity_id)
        if change.field == "location_id":
            change.value = mapping.get(("location", change.value), change.value)
    for character in roster.values():
        character.location_id = mapping.get(("location", character.location_id), character.location_id)
    if outcome.location:
        outcome.location.id = mapping.get(("location", outcome.location.id), outcome.location.id)
        known = locations.get(outcome.location.id)
        if known and known["name"] != outcome.location.name:
            raise ValueError("Scene location name conflicts with its entity")
    for access in outcome.truth_access_updates:
        access.related_location_id = mapping.get(("location", access.related_location_id), access.related_location_id)
    return {"locations": locations, "items": items, "relationships": relationships}, mapping


def validate_simulation_outcome(outcome, intentions, runtime, roster):
    if outcome.consistency_issues:
        raise ValueError("Material prose/event/state inconsistency: " + "; ".join(outcome.consistency_issues))
    supplied = {item["id"] for item in intentions}
    prior = runtime.get("attempt_results", {})
    seen = set()
    for result in outcome.attempt_results:
        if result.intent_id in seen or (result.intent_id not in supplied and result.intent_id not in prior):
            raise ValueError("Attempt result references an unknown or duplicate intention")
        if prior.get(result.intent_id, {}).get("status") in {"succeeded", "failed", "interrupted"}:
            raise ValueError("A resolved attempt cannot be resolved again")
        if result.status != "pending" and not result.event_id:
            raise ValueError("A resolved attempt requires a source event")
        seen.add(result.intent_id)
    commitments = runtime.get("commitments", {})
    seen = set()
    for commitment in outcome.commitments:
        if commitment.id in seen or not set(commitment.participants) <= roster.keys():
            raise ValueError("Commitment has duplicate ID or unknown participants")
        if commitments.get(commitment.id, {}).get("status") in {"fulfilled", "failed", "abandoned"}:
            raise ValueError("A completed commitment cannot be reopened")
        seen.add(commitment.id)


def consequence_links(outcome):
    return (outcome.character_state_updates + outcome.state_changes + outcome.truth_access_updates
            + ([outcome.location] if outcome.location else []) + outcome.pending_reaction_decisions
            + outcome.entity_additions.locations + outcome.entity_additions.items + outcome.entity_additions.relationships
            + [result for result in outcome.attempt_results if result.event_id] + outcome.commitments)
