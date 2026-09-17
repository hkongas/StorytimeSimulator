from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

StoryMode = Literal["novel", "simulation", "roleplay", "reader", "player", "director"]


def normalize_mode(mode: str) -> str:
    normalized = {"reader": "novel", "player": "roleplay", "director": "simulation"}.get(mode, mode)
    if normalized not in {"novel", "simulation", "roleplay"}:
        raise ValueError("Tuntematon tarinatila.")
    return normalized

class Character(BaseModel):
    id: str
    name: str
    age: int
    gender: Optional[str] = None
    appearance: str = ""
    personality: str = ""
    is_player_controlled: bool = False
    physical_state: str = "Terve ja hyväkuntoinen"
    mental_state: str = "Rauhallinen ja tarkkaavainen"
    secret_motive: str = ""
    public_bio: str = ""
    status: str = "active"  # active, inactive, archived, unconscious, dead
    tier: str = "major"     # major, supporting, minor, crowd_representative
    known_locations: List[str] = []
    last_active_turn: Optional[int] = None
    represents_group: Optional[str] = None
    group_size_hint: Optional[int] = None
    created_at: Optional[str] = None

class CharacterMemory(BaseModel):
    id: Optional[int] = None
    character_id: str
    scene_index: Optional[int] = 0
    memory_type: str = "observation"  # observation, thought, event, sentiment
    content: str
    importance_score: float = 1.0
    created_at: Optional[str] = None

class StoryMeta(BaseModel):
    id: str
    title: str
    genre: str = "Yleinen seikkailu"
    world_lore: str = ""
    director_plot_arc: str = ""
    director_notes: str = ""
    tone_profile: str = "default"
    custom_tone_override: Optional[str] = ""
    language: str = "fi"
    theme_color: Optional[str] = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class ChronicleEntry(BaseModel):
    id: Optional[int] = None
    chapter_index: int = 1
    scene_index: int = 1
    summary: str
    world_updates: Optional[str] = ""
    repetition_flag: bool = False
    created_at: Optional[str] = None

class Scene(BaseModel):
    id: Optional[int] = None
    chapter_number: int = 1
    location: str
    scene_goal: str
    active_character_ids: List[str] = []
    is_active: bool = True
    created_at: Optional[str] = None

class SceneTurn(BaseModel):
    id: Optional[int] = None
    scene_id: int
    turn_index: int
    acting_character_id: Optional[str] = None
    perceived_context: str = ""
    internal_monologue: str = ""
    character_action: str = ""
    director_prose: str
    choices: List[str] = []
    image_prompt: Optional[str] = ""
    created_at: Optional[str] = None

# API Request ja Response mallit

class StoryInitRequest(BaseModel):
    title: str
    genre: Optional[str] = "Fantasia / Seikkailu"
    user_idea: Optional[str] = ""
    user_role: StoryMode = "novel"
    player_character_name: Optional[str] = None
    player_character_details: Optional[str] = None
    custom_plot_idea: Optional[str] = None
    tone_profile: Optional[str] = "default"
    custom_tone_override: Optional[str] = None
    temperature: Optional[float] = 0.85

class AdvanceStoryRequest(BaseModel):
    user_input: Optional[str] = None  # Toiminta pelaajana tai ohje lukijana/ohjaajana
    mode: StoryMode = "novel"
    private_intention: Optional[str] = Field(default=None, max_length=4000)
    request_id: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    scene_id: Optional[int] = None
    custom_guidance: Optional[str] = None
    temperature: Optional[float] = 0.85

class TurnResponse(BaseModel):
    turn_index: int
    mode: str = "novel"
    request_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    acting_character: Optional[Dict[str, Any]] = None
    internal_monologue: Optional[str] = None
    character_action: Optional[str] = None
    director_prose: str
    choices: List[str] = []
    image_prompt: Optional[str] = None
    updated_characters: List[Character] = []
    spawned_characters: List[Character] = []
    story_text_snippet: str
    is_chapter_end: bool = False
    watchdog_note: Optional[str] = None
