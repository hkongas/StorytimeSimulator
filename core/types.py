from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class Character(BaseModel):
    id: str
    name: str
    age: int
    gender: Optional[str] = None
    appearance: str
    personality: str
    is_player_controlled: bool = False
    physical_state: str = "Terve ja hyväkuntoinen"
    mental_state: str = "Rauhallinen ja tarkkaavainen"
    secret_motive: str = ""
    public_bio: str = ""
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
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class ChronicleEntry(BaseModel):
    id: Optional[int] = None
    chapter_index: int = 1
    scene_index: int = 1
    summary: str
    world_updates: Optional[str] = ""
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
    image_prompt: Optional[str] = ""
    created_at: Optional[str] = None

# API Request ja Response mallit

class StoryInitRequest(BaseModel):
    title: str
    genre: Optional[str] = "Fantasia / Seikkailu"
    user_idea: Optional[str] = ""
    user_role: str = "reader"  # reader, player, director
    player_character_name: Optional[str] = None
    player_character_details: Optional[str] = None
    custom_plot_idea: Optional[str] = None
    temperature: Optional[float] = 0.85

class AdvanceStoryRequest(BaseModel):
    user_input: Optional[str] = None  # Toiminta pelaajana tai ohje lukijana/ohjaajana
    mode: str = "reader"              # reader, player, director
    scene_id: Optional[int] = None
    temperature: Optional[float] = 0.85

class TurnResponse(BaseModel):
    turn_index: int
    acting_character: Optional[Dict[str, Any]] = None
    internal_monologue: Optional[str] = None
    character_action: Optional[str] = None
    director_prose: str
    image_prompt: Optional[str] = None
    updated_characters: List[Character] = []
    story_text_snippet: str
    is_chapter_end: bool = False
