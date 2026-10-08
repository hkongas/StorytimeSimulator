import json

from config import settings
from core.schemas import SituationResponse, pydantic_to_json_schema


class SituationAgent:
    def __init__(self, llm):
        self.llm = llm

    async def resolve(self, story_id, scene, intentions, outcomes, runtime, roster, world, frame, budget):
        compact_roster = [{key: getattr(character, key) for key in
                           ("id", "name", "location_id", "visibility_state", "status", "physical_state", "mental_state")}
                          for character in roster.values()]
        proposed = [{key: value for key, value in item.items() if key not in {"private_thought", "memory", "belief_updates", "context_manifest"}} for item in intentions]
        payload = {"frame": frame, "scene": {"location": scene.location, "location_id": scene.location_id,
                    "active_character_ids": scene.active_character_ids}, "roster": compact_roster,
                   "fresh_intentions": proposed,
                   "accepted_recent_events": [event.model_dump() for outcome in outcomes[-2:] for event in outcome.events],
                   "open_attempts": [value for value in runtime.get("attempt_results", {}).values()
                                     if value["status"] == "pending"],
                   "commitments": list(runtime.get("commitments", {}).values()),
                   "current_facts": runtime.get("world_facts", []), "world": world,
                   "budget": budget.audit()}
        system = (
            "You are the situation controller, not the prose writer or a character. Return only the small supplied schema. "
            "Resolve fresh attempts, their timing and actual observers; select the next reaction group dynamically from "
            "verified observations and open attempts. Each next reaction requires an exact source event ID perceived by "
            "that actor. Use one actor in a sequential group or multiple actors in a parallel group at one locked moment. The same actor may respond again to a NEW stimulus. Never rerun a resolved attempt or force a "
            "response just because a previous attempt failed. Waiting, silence, failure and ending are valid. "
            "Do not invent voluntary actions, success, consent or speech absent an exact supplied intention. "
            "Speech alone is not automatically heard: resolve actual hearing. Proposed recipients and resolution hints "
            "are suggestions, not authority. Private thoughts never become another actor's observations. "
            "Null location means unknown and absent. Hidden actors are not revealed by a roster. No remote shortcut. "
            "Every state change, result and commitment references its causing event. New entities may be defined and "
            "referenced in this same response. Return only NEW events and continuity deltas, not prior history or prose. "
            "Stop before a meaningful player choice; never choose a player's reaction. stop_reason continue requires "
            "a next_group. frame_exhausted stops automation; do not silently replan. "
            "A relay_permit authorizes ONLY complete speech-only utterances by its visible colocated participants, "
            "at its fixed hearing channel and volume, with no simultaneous action or interruption risk. Verify its "
            "source hearing event for all participants. Everyone in participant_ids hears the permitted utterances; "
            "authorize a private group only if excluded actors cannot hear. Omit permission when uncertain. "
            "Use clock_beats 0 unless actual elapsed time warrants advancing clocks."
        )
        return await self.llm.json_completion(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}],
            role="situation", story_id=story_id,
            json_schema=pydantic_to_json_schema(SituationResponse, "situation_resolution"),
            temperature=settings.SITUATION_TEMPERATURE,
            reasoning_effort=settings.SITUATION_REASONING_EFFORT,
            max_tokens=min(settings.SITUATION_MAX_TOKENS, max(1, budget.token_limit - budget.tokens)))
