import json
from typing import Dict, Any, List, Optional
from core.llm_client import LLMClient
from core.types import StoryMeta, Character, Scene, SceneTurn, ChronicleEntry
from core.safety import UNIVERSAL_SAFETY_DIRECTIVE
import database.db as db

class DirectorAgent:
    """Pääagentti (Ohjaaja / Kirjailija / Pelinjohtaja).
    
    Vastaa maailman luomisesta, juonikaaresta, aistisuodatuksesta,
    vuorojen koordinoinnista ja rikkaan kirjamaisen proosan kirjoittamisesta.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    async def initialize_story(
        self,
        story_id: str,
        title: str,
        genre: str,
        user_idea: str = "",
        player_char_name: Optional[str] = None,
        player_char_details: Optional[str] = None,
        custom_plot_idea: Optional[str] = None
    ) -> Dict[str, Any]:
        """Luo uuden tarinamaailman, salaisen juonisuunnitelman, alkuhahmot ja aloituskappaleen."""
        
        system_prompt = f"""
{UNIVERSAL_SAFETY_DIRECTIVE}

Olet mestarillinen kirjailija ja roolipeliohjaaja (Game Master & Novelist).
Tehtäväsi on luoda uuden tarinan perusasetelma käyttäjän toiveiden pohjalta.
Luot syvällisen, kiehtovan ja elävän maailman, jännittävän salaisen juonikaaren sekä 2-3 moniulotteista hahmoa.

[OHJEET VASTAUKSELLE]
Palauta VAIN JSON-muotoinen vastaus seuraavalla rakenteella:
{{
  "world_lore": "Rikas ja tunnelmallinen kuvaus maailmasta, sen historiasta, kulttuurista, säännöistä ja ilmapiiristä (2-4 kappaletta).",
  "director_plot_arc": "Pääagentin salainen juonisuunnitelma: Pääkonflikti, salaisuudet, suunnitellut käänteet ja pitkän aikavälin päämäärä.",
  "director_notes": "Pääagentin muistiinpanot tarinan teemoista ja tunnelmasta.",
  "initial_characters": [
    {{
      "id": "uniikki_lyhyt_tunniste",
      "name": "Hahmon Nimi",
      "age": 28,
      "gender": "Mies / Nainen / Muu",
      "appearance": "Yksityiskohtainen ja elävä ulkonäkökuvaus.",
      "personality": "Syvällinen persoonallisuus, arvot, luonteenpiirteet ja heikkoudet.",
      "secret_motive": "Salainen henkilökohtainen tavoite tai trauma.",
      "public_bio": "Mitä hahmosta yleisesti tiedetään.",
      "physical_state": "Terve ja hyväkuntoinen",
      "mental_state": "Valpas ja utelias",
      "is_player_controlled": false
    }}
  ],
  "initial_scene": {{
    "location": "Aloituskohtauksen tarkka sijainti ja miljöökuvaus.",
    "scene_goal": "Mitä aloituskohtauksessa on tarkoitus tapahtua / aloitustilanteen jännite.",
    "opening_prose": "Mestarillinen, kaunokirjallinen aloitusproosakappale (kirjamainen, mukaansatempaava suomenkielinen kerronta, 2-4 kappaletta)."
  }}
}}
"""

        user_content = f"""
TARINAN OTSIKKO: {title}
GENRE / TYYLILAJI: {genre}
KÄYTTÄJÄN TOIVE / POHJA-AJATUS: {user_idea or 'Keksi omaperäinen ja koukuttava aloitus asetelmalle.'}
"""
        if custom_plot_idea:
            user_content += f"\nKÄYTTÄJÄN JUONI-IDEA: {custom_plot_idea}\n"

        if player_char_name:
            user_content += f"\nPELAAJAN HAHMO: Nimi '{player_char_name}', lisätiedot: '{player_char_details or 'Ei tarkempia toiveita'}'. Merkitse tämä hahmo 'is_player_controlled': true."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        data = await self.llm.json_completion(messages=messages, temperature=0.85)

        # 1. Tallennetaan StoryMeta tietokantaan
        meta = StoryMeta(
            id=story_id,
            title=title,
            genre=genre,
            world_lore=data.get("world_lore", ""),
            director_plot_arc=data.get("director_plot_arc", ""),
            director_notes=data.get("director_notes", "")
        )
        await db.save_story_meta(story_id, meta)

        # 2. Tallennetaan hahmot
        characters = []
        char_ids = []
        for char_data in data.get("initial_characters", []):
            char_id = char_data.get("id") or char_data.get("name", "char").lower().replace(" ", "_")
            # Varmistetaan että pelaajan valinta ohjaa lippua
            is_player = char_data.get("is_player_controlled", False)
            if player_char_name and player_char_name.lower() in char_data.get("name", "").lower():
                is_player = True

            char = Character(
                id=char_id,
                name=char_data.get("name", "Tuntematon"),
                age=char_data.get("age", 25),
                gender=char_data.get("gender"),
                appearance=char_data.get("appearance", ""),
                personality=char_data.get("personality", ""),
                is_player_controlled=is_player,
                physical_state=char_data.get("physical_state", "Terve"),
                mental_state=char_data.get("mental_state", "Rauhallinen"),
                secret_motive=char_data.get("secret_motive", ""),
                public_bio=char_data.get("public_bio", "")
            )
            await db.save_character(story_id, char)
            characters.append(char)
            char_ids.append(char.id)

        # 3. Luodaan aloituskohtaus
        init_scene = data.get("initial_scene", {})
        scene = Scene(
            chapter_number=1,
            location=init_scene.get("location", "Tuntematon paikka"),
            scene_goal=init_scene.get("scene_goal", "Tarina alkaa"),
            active_character_ids=char_ids,
            is_active=True
        )
        scene_id = await db.create_scene(story_id, scene)

        # 4. Tallennetaan aloitustarinavuoro
        opening_prose = init_scene.get("opening_prose", f"{title} alkaa...")
        first_turn = SceneTurn(
            scene_id=scene_id,
            turn_index=1,
            acting_character_id=None,
            perceived_context="Tarinan aloitushetki",
            internal_monologue="",
            character_action="",
            director_prose=opening_prose,
            image_prompt=f"Cinematic atmospheric opening scene for {genre}, {init_scene.get('location', '')}, dramatic lighting, highly detailed novel illustration"
        )
        await db.add_scene_turn(story_id, first_turn)

        return {
            "meta": meta,
            "characters": characters,
            "scene": scene,
            "opening_prose": opening_prose,
            "image_prompt": first_turn.image_prompt
        }

    async def create_perceptual_context(
        self,
        story_id: str,
        character: Character,
        scene: Scene,
        recent_prose: str,
        other_recent_actions: str
    ) -> str:
        """Suodattaa ja muodostaa aistisyötteen: mitä kyseinen hahmo näkee, kuulee ja tietää tässä hetkessä."""
        
        system_prompt = f"""
{UNIVERSAL_SAFETY_DIRECTIVE}

Olet roolipelisimulaattorin Aistisuodatin (Perceptual Filter).
Tehtäväsi on kuvata roolihahmolle '{character.name}', mitä hän suoraan aistii, näkee, kuulee ja tuntee tilanteessa.

SÄÄNNÖT:
- Älä kerro muiden hahmojen salaisia ajatuksia tai asioita, joita hahmo ei voi nähdä tai kuulla.
- Jos joku puhui tai teki jotain näkyvää/kuuluvaa, kerro se selkeästi.
- Pidä aistikuvaus tiiviinä (2-4 virkettä), suorana ja havainnollisena.
"""
        user_prompt = f"""
HAHMO: {character.name} (Sijainti: {scene.location})
VIIMEISIN TAPAHTUMAPROOSA:
{recent_prose}

MUIDEN HAHMOJEN VIIMEISIMMÄT TOIMET/PUHEET:
{other_recent_actions or 'Ei edeltäviä toimia tällä vuorolla.'}

Kirjoita aistikuvaus suoraan hahmolle '{character.name}'.
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            return await self.llm.chat_completion(messages=messages, temperature=0.7, max_tokens=300)
        except Exception:
            return f"Olet tilassa {scene.location}. Havaitset ympärilläsi olevat hahmot ja tilanteen kehittyvän."

    async def synthesize_turn_prose(
        self,
        story_id: str,
        scene: Scene,
        acting_character: Optional[Character],
        action_and_speech: str,
        internal_monologue: str,
        recent_prose_context: str,
        director_guidance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Kirjoittaa toiminnasta ja puheesta rikkaan, kirjamaisen suomenkielisen proosakappaleen sekä kuvauspromptin."""
        
        meta = await db.get_story_meta(story_id)
        chronicle = await db.get_chronicle(story_id)
        chronicle_summary = "\n".join([f"- {c.summary}" for c in chronicle[-3:]]) if chronicle else "Tarina on alussa."

        system_prompt = f"""
{UNIVERSAL_SAFETY_DIRECTIVE}

Olet palkittu, mestarillinen kirjailija ja tarinankertoja.
Kirjoitat tarinaa '{meta.title if meta else 'Tarina'}' (Genre: {meta.genre if meta else 'Seikkailu'}).

TEHTÄVÄSI:
Kirjoita seuraava rikas, elävä, kaunokirjallinen proosakappale suomeksi.
Yhdistä hahmon teot ja vuorosanat saumattomasti tarinan jatkumoon.
Kuvata ympäristöä, ääniä, eleitä, ilmeitä ja jännitettä.
Pidä kieli luontevana, elävänä ja nautittavana ilman kliseitä.

[MAAILMAN TAUSTAT]
{meta.world_lore if meta else ''}

[VIIMEAIKAISET TAPAHTUMAT (CHRONICLE)]
{chronicle_summary}

[SALAISEN JUONEN SUUNTA]
{meta.director_plot_arc if meta else ''}

[OHJEET VASTAUKSELLE]
Palauta VAIN JSON seuraavassa muodossa:
{{
  "prose": "Kirjamainen, huoliteltu ja kuvaileva tarinakappale suomeksi (1-3 laadukasta kappaletta).",
  "world_update": "Jos tapahtumassa paljastui merkittävä uusi maailman tieto, kirjaa se lyhyesti tähän (muuten tyhjä).",
  "plot_pivot_needed": false,
  "plot_pivot_note": "Jos hahmon toimet muuttivat juonen suuntaa, kirjaa miten Pääagentti sopeuttaa tarinaa jatkossa.",
  "image_prompt": "Detailed cinematic prompt in English for text-to-image AI capturing this scene, style: artistic atmospheric digital painting."
}}
"""

        user_content = f"""
SIJAINTI: {scene.location}
TOIMIVA HAHMO: {acting_character.name if acting_character else 'Yleinen maailmantapahtuma'}
HAHMON TEKO JA PUHE:
{action_and_speech}

HAHMON SALAINEN AJATUS (voit hyödyntää kaikkitietävänä kertojana tunnelmassa):
{internal_monologue}

EDELTÄVÄ TARINATEKSTI:
{recent_prose_context[-1500:] if len(recent_prose_context) > 1500 else recent_prose_context}
"""
        if director_guidance:
            user_content += f"\n[OHJAAJAN ERIKOISOHJE]: {director_guidance}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            data = await self.llm.json_completion(messages=messages, temperature=0.85)
        except Exception as e:
            # Varalogiikka jos JSON pettää
            raw_text = await self.llm.chat_completion(messages=messages, temperature=0.85)
            data = {
                "prose": raw_text,
                "world_update": "",
                "plot_pivot_needed": False,
                "plot_pivot_note": "",
                "image_prompt": f"Dramatic scene in {scene.location}"
            }

        # Jos juonimuutos tarvitaan, päivitetään director_notes
        if data.get("plot_pivot_needed") and data.get("plot_pivot_note") and meta:
            meta.director_notes = f"{meta.director_notes}\n[Juonimuutos]: {data.get('plot_pivot_note')}".strip()
            await db.save_story_meta(story_id, meta)

        return data
