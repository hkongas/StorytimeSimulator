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

        user_content = f"TAPAHTUMAT JA TOIMET:\n{turns_text}"
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
                world_updates=data.get("world_updates", "")
            )
            await db.add_chronicle_entry(story_id, entry)

            # Jos tuli maailmanpäivityksiä, liitetään ne story_metaan
            world_updates = data.get("world_updates")
            if world_updates:
                meta = await db.get_story_meta(story_id)
                if meta:
                    meta.world_lore = f"{meta.world_lore}\n\n[Päivitys luku {chapter_index}]: {world_updates}".strip()
                    await db.save_story_meta(story_id, meta)

            return entry
        except Exception:
            entry = ChronicleEntry(
                chapter_index=chapter_index,
                scene_index=scene_index,
                summary="Kohtauksen tapahtumat vietiin päätökseen.",
                world_updates=""
            )
            await db.add_chronicle_entry(story_id, entry)
            return entry
