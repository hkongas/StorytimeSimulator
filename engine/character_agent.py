import json
from typing import Dict, Any, List, Optional
from core.llm_client import LLMClient
from core.types import Character, CharacterMemory
from core.prompt_loader import prompt_loader
from core.schemas import CharacterDecisionResponse, pydantic_to_json_schema
import database.db as db

class CharacterAgent:
    """Yksittäistä tarinan hahmoa simuloiva agentti.
    
    Hahmolla on oma salainen mieli, persoonallisuus, motiivit, tunteet,
    oma muistivirta ja rajattu aistihavaintokyky ilman telepatiaa.
    
    Hahmo ilmaisee AIKEENSA — Kertoja päättää lopputuloksen.
    """

    def __init__(self, character: Character, llm_client: Optional[LLMClient] = None):
        self.character = character
        self.llm = llm_client or LLMClient()

    async def decide_intention(
        self,
        story_id: str,
        scene_location: str,
        recent_prose_context: str,
        tone_profile: str = "default",
        custom_tone_override: Optional[str] = None,
        director_nudge: Optional[str] = None,
        player_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generoi hahmon aikeen: mitä hahmo yrittää/aikoo tehdä ja sisäisen monologin.
        
        Hahmo ei enää päätä omasta tilastaan tai muistista — Kertoja tekee sen.
        """
        
        # Jos hahmo on tajuton tai kuollut, se ei tee itsenäisiä tekoja
        if self.character.status == "unconscious":
            return {
                "internal_monologue": "(Hahmo on tajuton ja tiedoton ympäristöstään.)",
                "action_and_speech": f"{self.character.name} makaa tajuttomana eikä reagoi tilanteeseen."
            }
        elif self.character.status == "dead":
            return {
                "internal_monologue": "(Hahmo on kuollut.)",
                "action_and_speech": f"{self.character.name} on eloton."
            }

        # Haetaan hahmon aiemmat muistit tietokannasta (laajennettu raja pitkiin tarinoihin)
        memory_limit = 20 if self.character.tier == "major" else 10
        past_memories: List[CharacterMemory] = await db.get_relevant_memories(
            story_id, self.character.id, f"{scene_location} {self.character.secret_motive}", limit=memory_limit
        )
        memory_text = "\n".join([f"- ({m.memory_type}): {m.content}" for m in past_memories]) if past_memories else "Ei vielä aiempia muistikuvia."

        system_prompt = prompt_loader.compose_system_prompt(
            prompt_name="character/decide_action",
            tone_profile=tone_profile,
            custom_tone_override=custom_tone_override,
            character_name=self.character.name,
            character_age=self.character.age,
            character_gender=self.character.gender or "Määrittelemätön",
            character_appearance=self.character.appearance or "Tavallinen olemus",
            character_personality=self.character.personality or "Moniulotteinen",
            character_secret_motive=self.character.secret_motive or "Selviytyä ja edistää omia tavoitteitaan",
            character_public_bio=self.character.public_bio or "Ei laajasti tunnettu",
            character_physical_state=self.character.physical_state,
            character_mental_state=self.character.mental_state,
            character_tier=self.character.tier,
            character_memories=memory_text
        )

        user_content = f"""
[CURRENT LOCATION]
{scene_location}

[YOUR VERIFIED OBSERVATIONS - NOT OMNISCIENT NARRATION]
{recent_prose_context[-3000:] if len(recent_prose_context) > 3000 else recent_prose_context}
"""

        if self.character.is_player_controlled and player_instruction:
            user_content += f"\n[PLAYER INPUT / INTENDED ACTION]: {player_instruction}\n(Express this through your authentic voice, personality, and physical capabilities in Finnish)."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        result = await self.llm.json_completion(
            messages=messages, role="character", story_id=story_id,
            json_schema=pydantic_to_json_schema(CharacterDecisionResponse, "character_decision")
        )

        # Hahmo EI enää päivitä omaa tilaansa — Kertoja tekee sen synthesize_turn_prose -kutsussa
        return CharacterDecisionResponse.model_validate(result).model_dump()

    # Säilytetään vanha nimi aliasmäppäyksenä yhteensopivuuden vuoksi
    async def decide_action(self, *args, **kwargs) -> Dict[str, Any]:
        """Vanhentunut alias: käytä decide_intention() uudessa koodissa."""
        return await self.decide_intention(*args, **kwargs)
