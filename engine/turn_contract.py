from database import db
from uuid import uuid4


def merge_continuity(response, runtime):
    def merge(previous, added, removed):
        return list(dict.fromkeys([value for value in previous if value not in removed] + added))

    summary = "\n".join(value for value in (runtime.get("summary", ""), response.recap_delta) if value)
    return {
        "summary": summary,
        "world_facts": merge(runtime.get("world_facts", []), response.continuity.facts_added, response.continuity.facts_removed),
        "plot_threads": merge(runtime.get("plot_threads", []), response.continuity.threads_added, response.continuity.threads_removed),
        "scene_location": response.location.name if response.location else None,
    }


def validate_event_links(events, updates):
    identifiers = {event.id for event in events}
    if len(identifiers) != len(events):
        raise ValueError("Tapahtumatunnisteiden on oltava yksilollisia.")
    for update in updates:
        if update.event_id not in identifiers:
            raise ValueError("Tilamuutoksen tapahtumaviite ei vastaa toteutunutta tapahtumaa.")


def assign_event_ids(events, updates):
    validate_event_links(events, updates)
    identifiers = {event.id: uuid4().hex for event in events}
    for update in updates:
        update.event_id = identifiers[update.event_id]
    for event in events:
        event.id = identifiers[event.id]


def validate_bible_additions(additions, bible, roster):
    for field, values in (("secret_truths", additions.secret_truths), ("clocks", additions.clocks),
                          ("offscreen_agents", additions.offscreen_agents)):
        existing = {item["id"] for item in bible[field]}
        identifiers = [item.id for item in values]
        if len(set(identifiers)) != len(identifiers) or existing.intersection(identifiers):
            raise ValueError("Tarinaraamatun lisays kayttaa olemassa olevaa tai toistuvaa tunnistetta.")
        if any(not identifier or len(identifier) > 80 or not all(char.isalnum() or char in "_-" for char in identifier)
               for identifier in identifiers):
            raise ValueError("Tarinaraamatun lisayksen tunniste on virheellinen.")
    for agent in additions.offscreen_agents:
        if not set(agent.visible_to) <= roster.keys():
            raise ValueError("Sivuhenkilon havaitsija on tuntematon.")
    if any(truth.reveal_state != "hidden" for truth in additions.secret_truths):
        raise ValueError("Uusi salaisuus ei saa automaattisesti paljastua hahmoille.")


def concrete_progress(before, after, events, world_changed=False):
    if world_changed:
        return True
    for identifier, character in after.items():
        previous = before.get(identifier)
        if previous is None or any(previous[field] != getattr(character, field)
                                   for field in ("location_id", "status")):
            return True
    return any(event.change_kind != "none" for event in events)


async def apply_resolved_changes(story_id, changes, roster, present_ids, scene_location):
    allowed = {
        "character": {"location_id", "physical_state", "mental_state", "status"},
        "item": {"holder_character_id", "location_id", "state"},
        "relationship": {"attitude", "trust", "summary"},
    }
    changed = False
    for change in changes:
        if change.entity not in allowed or change.field not in allowed[change.entity]:
            raise ValueError("Ratkaisijan tilamuutos käyttää tukematonta kohdetta tai kenttää.")
        if change.entity == "character":
            character = roster.get(change.entity_id)
            if character is None:
                raise ValueError("Ratkaisijan tilamuutos viittaa tuntemattomaan hahmoon.")
            if change.field == "status":
                if change.value not in {"active", "unconscious", "dead", "inactive", "archived"}:
                    raise ValueError("Hahmon tila on virheellinen.")
                if character.status == "dead" and change.value != "dead":
                    raise ValueError("Ratkaisija ei saa perua kuolemaa.")
            elif not isinstance(change.value, str):
                raise ValueError("Hahmon tilamuutoksen arvon on oltava tekstiä.")
            previous = getattr(character, change.field)
        elif change.entity == "item":
            item = await db.get_item(story_id, change.entity_id)
            if item is None:
                raise ValueError("Ratkaisijan tilamuutos viittaa tuntemattomaan esineeseen.")
            if change.field == "holder_character_id" and change.value is not None and change.value not in present_ids:
                raise ValueError("Esineen vastaanottajan on oltava paikalla.")
            if change.value is not None and not isinstance(change.value, str):
                raise ValueError("Esineen tilamuutoksen arvon on oltava tekstiä.")
            if change.field == "state" and change.value is None:
                raise ValueError("Esineen tila ei voi olla tyhjä.")
            previous = item[change.field]
            if change.field in {"holder_character_id", "location_id"}:
                counterpart = "location_id" if change.field == "holder_character_id" else "holder_character_id"
                changed |= item[counterpart] is not None
        else:
            identifiers = change.entity_id.split("|", 1)
            if len(identifiers) != 2 or not await db.relationship_exists(story_id, *identifiers):
                raise ValueError("Ratkaisijan tilamuutos viittaa tuntemattomaan suhteeseen.")
            if change.field == "trust":
                if isinstance(change.value, bool) or not isinstance(change.value, (int, float)) or not -1 <= change.value <= 1:
                    raise ValueError("Suhteen luottamuksen on oltava välillä -1 ja 1.")
            elif not isinstance(change.value, str):
                raise ValueError("Suhteen tilamuutoksen arvon on oltava tekstiä.")
            world = await db.get_planning_world(story_id)
            relation = next(item for item in world["relationships"]
                            if item["character_a"] == identifiers[0] and item["character_b"] == identifiers[1])
            previous = relation[change.field]
        if change.field == "location_id" and change.value is not None:
            if change.value != db.location_identifier(scene_location) and not await db.location_exists(story_id, change.value):
                raise ValueError("Ratkaisijan sijaintimuutos viittaa tuntemattomaan paikkaan.")
        if change.field not in {"mental_state", "physical_state"}:
            changed |= previous != change.value
        if change.entity == "character":
            setattr(roster[change.entity_id], change.field, change.value)
    return changed
