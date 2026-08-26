import json
from typing import Dict, Any, List, Optional
from core.llm_client import LLMClient
from core.types import Character, CharacterMemory
from core.safety import UNIVERSAL_SAFETY_DIRECTIVE
import database.db as db

class CharacterAgent:
    """Yksittäistä tarinan hahmoa simuloiva agentti.
    
    Hahmolla on oma salainen mieli, persoonallisuus, motiivit, tunteet,
    oma muistivirta ja rajattu aistihavaintokyky ilman telepatiaa.
    """

    def __init__(self, character: Character, llm_client: Optional[LLMClient] = None):
        self.character = character
        self.llm = llm_client or LLMClient()

    async def decide_action(
        self,
        story_id: str,
        scene_location: str,
        perceived_context: str,
        director_nudge: Optional[str] = None,
        player_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generoi hahmon sisäisen monologin, teot/puheen ja päivittää hahmon tilan ja muistin."""
        
        # 1. Haetaan hahmon aiemmat muistit tietokannasta
        past_memories: List[CharacterMemory] = await db.get_character_memories(story_id, self.character.id, limit=10)
        memory_text = "\n".join([f"- ({m.memory_type}): {m.content}" for m in past_memories]) if past_memories else "Ei vielä aiempia muistikuvia."

        system_prompt = f"""
{UNIVERSAL_SAFETY_DIRECTIVE}

Olet roolihahmo '{self.character.name}' interaktiivisessa tarinassa/roolipelissä.
Eläydy täydellisesti hahmoosi. Sinulla on oma itsenäinen mieli, tunteet ja motiivit.
Et ole kaikkitietävä: tiedät vain sen, mitä aistit tässä hetkessä tai muistat aiemmin.

[PROFIILISI]
- Nimi: {self.character.name}
- Ikä: {self.character.age}
- Ulkonäkö: {self.character.appearance}
- Persoonallisuus & Arvot: {self.character.personality}
- Salainen motiivi / Päätavoite: {self.character.secret_motive}
- Julkinen maine: {self.character.public_bio}
- Nykyinen fyysinen vointi: {self.character.physical_state}
- Nykyinen henkinen tila: {self.character.mental_state}

[MUISTIKUVASI AIEMMASTA]
{memory_text}

[OHJEET VASTAUKSELLE]
Palauta VAIN JSON-muotoinen vastaus seuraavalla rakenteella:
{{
  "internal_monologue": "Salainen ajatuksesi, tunteesi ja sisäinen reaktiosi tilanteeseen (vain sinun tietoon).",
  "action_and_speech": "Mitä konkreettisesti teet ja sanot ääneen. Voit käyttää suoraa puhetta lainausmerkeissä ja kuvata fyysistä toimintaasi.",
  "updated_physical_state": "Päivitetty fyysinen vointisi tämän vuoron jälkeen.",
  "updated_mental_state": "Päivitetty henkinen/emotionaalinen tilasi tämän vuoron jälkeen.",
  "new_memory": "Tiivis 1-2 lauseen muistijälki, jonka tallennat omaan mieleesi tästä hetkestä."
}}
"""

        user_content = f"""
[NYKYINEN SIJAINTI]
{scene_location}

[MITÄ AISTIT JA NÄET NYT]
{perceived_context}
"""
        if director_nudge:
            user_content += f"\n[VAISTO / TILANNEVIHJE]: {director_nudge}\n"

        if self.character.is_player_controlled and player_instruction:
            user_content += f"\n[PELAAJAN TOIVE/SYÖTE]: {player_instruction}\n(Muotoile tämä hahmosi luonteen ja puhetavan mukaiseksi teoksi ja puheeksi)."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            result = await self.llm.json_completion(messages=messages, role="character")
        except Exception as e:
            # Fallback jos JSON-jäsennys epäonnistuu
            result = {
                "internal_monologue": f"(Ajattelee tilannetta kuumeisesti: {str(e)})",
                "action_and_speech": f"{self.character.name} katsoo ympärilleen ja miettii seuraavaa siirtoaan.",
                "updated_physical_state": self.character.physical_state,
                "updated_mental_state": self.character.mental_state,
                "new_memory": "Tilanne oli sekava ja nopea."
            }

        # Päivitetään hahmon tila tietokantaan
        self.character.physical_state = result.get("updated_physical_state", self.character.physical_state)
        self.character.mental_state = result.get("updated_mental_state", self.character.mental_state)
        await db.update_character_state(
            story_id, self.character.id, self.character.physical_state, self.character.mental_state
        )

        # Tallennetaan uusi muisto
        new_memory_text = result.get("new_memory")
        if new_memory_text:
            memory_item = CharacterMemory(
                character_id=self.character.id,
                memory_type="observation",
                content=new_memory_text,
                importance_score=1.0
            )
            await db.add_character_memory(story_id, memory_item)

        return result
