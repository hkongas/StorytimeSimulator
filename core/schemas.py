from typing import List, Optional, Dict, Any, Type, Literal
from pydantic import BaseModel, Field

class StoryInitCharacter(BaseModel):
    id: str = Field(description="Unique short id, e.g. elias_korpela")
    name: str = Field(description="Full character name")
    age: int = Field(default=30, description="Age in years")
    gender: Optional[str] = Field(default="Unknown", description="Gender of character")
    appearance: str = Field(default="", description="Visual description, clothing, build")
    personality: str = Field(default="", description="Personality traits, habits, flaws")
    secret_motive: str = Field(default="", description="Hidden objective, trauma, ambition")
    public_bio: str = Field(default="", description="Public knowledge, reputation")
    physical_state: str = Field(default="Healthy and alert", description="Current physical condition")
    mental_state: str = Field(default="Composed", description="Current emotional or cognitive state")
    is_player_controlled: bool = Field(default=False, description="Whether this is player's avatar")
    tier: str = Field(default="major", description="major, supporting, or minor")
    known_locations: List[str] = Field(default_factory=list, description="Locations known by this character")

class StoryEvent(BaseModel):
    description: str = Field(min_length=1, max_length=2000, description="Observable event only, no hidden thoughts or narrator-only facts")
    witnesses: List[str] = Field(description="IDs of characters who actually perceived the event; empty for a secret world event")


class StoryInitScene(BaseModel):
    location: str = Field(description="Specific location of the opening scene")
    scene_goal: str = Field(description="The primary tension or impending catalyst")
    opening_prose: str = Field(description="Exquisite, atmospheric narrative opening in Finnish (2-4 vivid paragraphs)")
    events: List[StoryEvent] = Field(default_factory=list, description="Opening events with explicit witnesses")

class StoryInitResponse(BaseModel):
    world_lore: str = Field(description="Rich and atmospheric description of the world, geography, culture, rules")
    director_plot_arc: str = Field(description="Director's secret plot arc: Core conflict, hidden secrets, planned twists")
    director_notes: str = Field(description="Director's internal notes on themes, pacing, atmosphere")
    initial_characters: List[StoryInitCharacter] = Field(description="2-4 key characters starting the story")
    initial_scene: StoryInitScene = Field(description="The opening scene details and narrative prose")

class CharacterStateUpdate(BaseModel):
    character_id: str = Field(description="The unique id of the character")
    physical_state: Optional[str] = Field(default=None, description="Updated physical condition (e.g. 'Uninjured', 'Bruised', 'Exhausted', 'Bleeding')")
    mental_state: Optional[str] = Field(default=None, description="Updated emotional or cognitive state (e.g. 'Alarmed', 'Relieved', 'Defiant')")
    status: Optional[Literal["active", "unconscious", "dead", "inactive", "archived"]] = None
    new_memory: Optional[str] = Field(default="", description="Key memory trace/observation the character forms from these events")

class ProseTurnResponse(BaseModel):
    chapter_title: str = Field(default="", max_length=160, description="Current chapter title; keep stable until chapter ends")
    director_plan: str = Field(default="", max_length=6000, description="Updated evolving plot arc: completed milestones, current conflict, plausible next developments; not a predetermined outcome")
    director_notes: str = Field(default="", max_length=4000, description="Updated pacing notes, unresolved decisions and consequences to resolve next")
    world_description: str = Field(default="", max_length=6000, description="Updated world description based only on established developments; retain enduring rules")
    prose: str = Field(min_length=1, description="Finished narrative prose in Finnish")
    events: List[StoryEvent] = Field(description="Authoritative events and the characters who perceived each event")
    summary: str = Field(min_length=1, max_length=6000, description="Updated cumulative story summary; retain important earlier developments")
    world_facts: List[str] = Field(default_factory=list, max_length=40)
    plot_threads: List[str] = Field(default_factory=list, max_length=20)
    decision_character_ids: List[str] = Field(default_factory=list, description="Characters needing an independent important decision next turn")
    scene_location: Optional[str] = None
    scene_goal: Optional[str] = None
    chapter_end: bool = False
    requires_player_input: bool = False
    character_state_updates: List[CharacterStateUpdate] = Field(default_factory=list, description="Director's authoritative updates to each character's condition, mental state, and memory based on what happened")
    active_character_ids: Optional[List[str]] = Field(default=None, description="List of character IDs who remain active/present in the scene for next turn")
    choices: List[str] = Field(default_factory=list, description="2-4 interesting choice suggestions for next turn")
    spawned_characters: List[StoryInitCharacter] = Field(default_factory=list, description="New characters with unique IDs, never replacements")
    world_update: Optional[str] = Field(default="", description="Any notable updates to the world state")
    plot_pivot_needed: Optional[bool] = Field(default=False, description="True if director detects plot direction change")
    plot_pivot_note: Optional[str] = Field(default="", description="Note explaining plot change")
    image_prompt: Optional[str] = Field(default="", description="English image generation prompt for illustration")

class TurnPlanResponse(BaseModel):
    events: List[StoryEvent] = Field(default_factory=list)
    character_state_updates: List[CharacterStateUpdate] = Field(default_factory=list)
    spawned_characters: List[StoryInitCharacter] = Field(default_factory=list)
    active_character_ids: List[str]
    decision_character_ids: List[str]
    scene_location: Optional[str] = None
    scene_goal: str = Field(min_length=1, max_length=2000)
    direction: str = Field(min_length=1, max_length=4000)
    requires_player_input: bool = False


class CharacterDecisionResponse(BaseModel):
    internal_monologue: str = Field(description="Private thoughts, emotions and motivations of the character in response to the situation")
    action_and_speech: str = Field(description="What the character attempts or intends to do and say out loud in Finnish")

class PlayerViewResponse(BaseModel):
    prose: str = Field(min_length=1, max_length=12000, description="Limited viewpoint story prose using only supplied private knowledge and perceived events")
    recap: str = Field(min_length=1, max_length=4000, description="Cumulative recap limited to this character's knowledge; preserve uncertainty")
    chapter_title: str = Field(min_length=1, max_length=160, description="Chapter title that reveals no unknown secret")
    choices: List[str] = Field(default_factory=list, max_length=5, description="Possible actions based only on what this character knows; never in prose")

def pydantic_to_json_schema(model: Type[BaseModel], name: Optional[str] = None, strict: bool = False) -> Dict[str, Any]:
    """Muuntaa Pydantic-mallin xAI / OpenAI -yhteensopivaksi response_format: json_schema -rakenteeksi."""
    schema_name = name or model.__name__
    schema_dict = model.model_json_schema()
    
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": strict,
            "schema": schema_dict
        }
    }
