from database import db


def eligible_reaction_decisions(outcome, roster, scene, mode, objective_progress, resolver_event_ids, prior_descriptions):
    if (not objective_progress or outcome.chapter_end or outcome.scene_stop
            or outcome.requires_player_input or outcome.scene_location != scene.location
            or not outcome.active_character_ids):
        return []
    events = {event.id: event for event in outcome.events if event.id in resolver_event_ids}
    eligible = []
    for pending in outcome.pending_reaction_decisions:
        event = events.get(pending.event_id)
        character = roster.get(pending.character_id)
        if (not event or event.change_kind == "none" or not pending.decision.strip()
                or event.description.strip().casefold() in prior_descriptions
                or not character or character.status != "active"
                or character.id not in outcome.active_character_ids
                or character.id not in scene.active_character_ids
                or character.location_id not in {None, db.location_identifier(scene.location)}
                or character.id not in event.witnesses
                or not event.observation_for(character.id).strip()
                or character.id not in outcome.decision_character_ids):
            return []
        if mode == "roleplay" and character.is_player_controlled:
            return []
        eligible.append(pending)
    if mode == "roleplay" and any(
        roster[identifier].is_player_controlled for identifier in outcome.decision_character_ids
        if identifier in roster
    ):
        return []
    return eligible
