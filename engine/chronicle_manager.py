import json
from typing import Dict, Any, List, Optional
from core.llm_client import LLMClient
from core.types import ChronicleEntry, SceneTurn
from core.prompt_loader import prompt_loader
import database.db as db

class ChronicleManager:
    """Ylläpitää tiivistettyä tapahtumahistoriaa (Chronicle), jotta tarinan laajuus
    voi kasvaa rajattomasti ilman konteksti-ikkunan ylittymistä.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    async def summarize_scene_or_turns(
        self,
        story_id: str,
        chapter_index: int,
        scene_index: int,
        recent_turns: List[SceneTurn],
        tone_profile: str = "default",
        custom_tone_override: Optional[str] = None
    ) -> Optional[ChronicleEntry]:
        """Luo tiiviin, tarkan kronikkakirjauksen viimeaikaisista tarinavuoroista."""
        if not recent_turns:
            return None

        turns_text = "\n\n".join([
            f"[Vuoro {t.turn_index} - {t.acting_character_id or 'Kertomus'}]:\n"
            f"Teot: {t.character_action}\n"
            f"Proosa: {t.director_prose}"
            for t in recent_turns
        ])

        system_prompt = prompt_loader.compose_system_prompt(
            prompt_name="chronicle/summarize",
            tone_profile=tone_profile,
            custom_tone_override=custom_tone_override
        )

        source_turn_ids = [turn.id for turn in recent_turns if turn.id is not None]
        sources = await db.get_events_for_turns(story_id, source_turn_ids)
        user_content = f"TAPAHTUMAT JA TOIMET:\n{turns_text}\nREALIZED EVENTS:\n" + json.dumps(sources, ensure_ascii=False)
        system_prompt += "\nOriginal accepted prose is permanent. Summaries are derivative, never new world facts. Preserve old commitments and source meaning. Distinguish attempted actions from realized events."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            data = await self.llm.json_completion(messages=messages, temperature=0.5, role="director", story_id=story_id)
            entry = ChronicleEntry(
                chapter_index=chapter_index,
                scene_index=scene_index,
                summary=data.get("summary", "Kohtaus eteni."),
                world_updates=data.get("world_updates", ""),
                source_turn_ids=source_turn_ids, source_event_ids=[event["id"] for event in sources]
            )
            await db.add_chronicle_entry(story_id, entry)

            return entry
        except Exception:
            # Failed summarization never invents a replacement history.
            return None
