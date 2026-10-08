from typing import List, Optional, Dict, Any, Type, Literal
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator, model_validator
import math


class CharacterCatchup(BaseModel):
    recap: str = Field(min_length=1, max_length=4000)

    @field_validator("recap")
    @classmethod
    def nonempty_recap(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Recap must not be blank")
        return value.strip()


class SecretTruth(BaseModel):
    id: str
    fact: str
    discoverable_via: str = ""
    reveal_state: Literal["hidden", "hinted", "revealed"] = "hidden"
    related_location_id: Optional[str] = None


class StoryClock(BaseModel):
    id: str
    description: str
    remaining_beats: int = Field(ge=0)
    on_expire_effect: str = ""
    visible: bool = False


class OffscreenAgent(BaseModel):
    id: str
    name: str
    goal: str
    progress: str = ""
    location: str = ""
    next_move: str = ""
    visible_to: List[str] = Field(default_factory=list)


class RelationshipSeed(BaseModel):
    character_a: str
    character_b: str
    attitude: str = ""
    trust: float = Field(default=0, ge=-1, le=1)
    summary: str = ""


class StoryBibleResponse(BaseModel):
    secret_truths: List[SecretTruth] = Field(default_factory=list)
    clocks: List[StoryClock] = Field(default_factory=list)
    offscreen_agents: List[OffscreenAgent] = Field(default_factory=list)


class RevealDecision(BaseModel):
    truth_id: str
    how: str


class TruthAccessUpdate(BaseModel):
    event_id: str
    truth_id: str
    discoverable_via: str = Field(description="Current evidence or access route after world changes; preserve uncertainty and the original truth")
    related_location_id: Optional[str] = None


class ClockTick(BaseModel):
    clock_id: str
    amount: int = Field(default=1, ge=1)


class StateChange(BaseModel):
    event_id: str
    entity: str = Field(description="character, item or relationship")
    entity_id: str
    field: str
    value: Any

    @model_validator(mode="after")
    def typed_value(self):
        fields = {
            "character": {"location_id", "physical_state", "mental_state", "status", "visibility_state"},
            "item": {"holder_character_id", "location_id", "state"},
            "relationship": {"attitude", "trust", "summary"},
        }
        # Unsupported planner fields remain discardable for compatibility; never executable.
        if self.field not in fields.get(self.entity, set()):
            return self
        if self.field in {"location_id", "holder_character_id"}:
            if self.value is not None and (not isinstance(self.value, str) or not self.value.strip()):
                raise ValueError("value must be a nonempty identifier or null")
        elif self.field == "trust":
            if isinstance(self.value, bool) or not isinstance(self.value, (float, int)) or not math.isfinite(self.value) or not -1 <= self.value <= 1:
                raise ValueError("value must be a finite number between -1 and 1")
        elif not isinstance(self.value, str):
            raise ValueError("value must be text")
        if self.field == "status" and self.value not in {"active", "unconscious", "dead", "inactive", "archived"}:
            raise ValueError("invalid character status")
        if self.field == "visibility_state" and self.value not in {"visible", "hidden"}:
            raise ValueError("invalid visibility state")
        return self

class StoryInitCharacter(BaseModel):
    id: str = Field(description="Unique short id, e.g. elias_korpela")
    name: str = Field(description="Full character name")
    age: int = Field(default=30, description="Age in years")
    gender: Optional[str] = Field(default="Unknown", description="Gender of character")
    appearance: str = Field(default="", description="Visual description, clothing, build")
    personality: str = Field(default="", description="Personality traits, habits, flaws")
    speech_style: str = Field(default="", description="Distinct voice and speech habits")
    values: str = Field(default="", description="Personal values that may conflict with others")
    current_goal: str = Field(default="", description="Immediate personal goal")
    fears: str = Field(default="", description="Specific fears and vulnerabilities")
    skills: str = Field(default="", description="Useful capabilities")
    limitations: str = Field(default="", description="Physical, social, or practical constraints")
    secret_motive: str = Field(default="", description="Hidden objective, trauma, ambition")
    public_bio: str = Field(default="", description="Public knowledge, reputation")
    physical_state: str = Field(default="Healthy and alert", description="Current physical condition")
    mental_state: str = Field(default="Composed", description="Current emotional or cognitive state")
    is_player_controlled: bool = Field(default=False, description="Whether this is player's avatar")
    tier: str = Field(default="major", description="major, supporting, or minor")
    known_locations: List[str] = Field(default_factory=list, description="Locations known by this character")
    location_id: Optional[str] = Field(default=None, description="Null means unknown/absent; omitted opening location defaults to opening scene")
    visibility_state: Literal["visible", "hidden"] = "visible"


class StoryInitItem(BaseModel):
    id: str
    name: str
    holder_character_id: Optional[str] = None
    location_id: Optional[str] = None
    state: str = ""


class StoryObservation(BaseModel):
    character_id: str
    text: str = Field(min_length=1, description="Only what this character perceived; no hidden thoughts or narrator knowledge")
    modality: Literal["saw", "heard", "faintly_heard", "felt"] = "saw"


class StoryEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex, description="Unique event ID used by consequence updates")
    description: str = Field(min_length=1, max_length=2000, description="Observable event only, no hidden thoughts or narrator-only facts")
    observations: List[StoryObservation] = Field(default_factory=list, description="One account per actual observer; empty for a secret event")
    derived_from: str = Field(description="intent:<character_id>, consequence, routine, or world")
    actor_id: Optional[str] = None
    intent_id: Optional[str] = Field(default=None, description="Exact supplied intention ID for voluntary actions and authorized routines")
    change_kind: Literal["none", "information", "location", "possession", "relationship", "risk", "goal"] = Field(
        default="none", description="Concrete new outcome; none for unchanged observations or repeated information")

    @property
    def witnesses(self) -> List[str]:
        return [observation.character_id for observation in self.observations]

    def observation_for(self, character_id: str) -> str:
        return next((observation.text for observation in self.observations
                     if observation.character_id == character_id), "")

    @field_validator("observations")
    @classmethod
    def unique_observers(cls, value):
        if len({observation.character_id for observation in value}) != len(value):
            raise ValueError("An event must have one observation per character")
        return value

    @field_validator("derived_from")
    @classmethod
    def valid_provenance(cls, value):
        if value not in {"consequence", "routine", "world"} and not value.startswith("intent:"):
            raise ValueError("derived_from must identify an intent or a world/consequence source")
        if value.startswith("intent:") and not value.removeprefix("intent:").strip():
            raise ValueError("intent provenance requires a character id")
        return value


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
    secret_truths: List[SecretTruth] = Field(default_factory=list)
    clocks: List[StoryClock] = Field(default_factory=list)
    offscreen_agents: List[OffscreenAgent] = Field(default_factory=list)
    initial_relationships: List[RelationshipSeed] = Field(default_factory=list, max_length=12)
    initial_items: List[StoryInitItem] = Field(default_factory=list, max_length=30)

class CharacterStateUpdate(BaseModel):
    event_id: str
    character_id: str = Field(description="The unique id of the character")
    physical_state: Optional[str] = Field(default=None, description="Updated physical condition (e.g. 'Uninjured', 'Bruised', 'Exhausted', 'Bleeding')")
    mental_state: Optional[str] = Field(default=None, description="Updated emotional or cognitive state (e.g. 'Alarmed', 'Relieved', 'Defiant')")
    status: Optional[Literal["active", "unconscious", "dead", "inactive", "archived"]] = None

class ContinuityDelta(BaseModel):
    facts_added: List[str] = Field(default_factory=list)
    facts_removed: List[str] = Field(default_factory=list)
    threads_added: List[str] = Field(default_factory=list)
    threads_removed: List[str] = Field(default_factory=list)


class ContinuitySummary(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)


class SceneLocation(BaseModel):
    event_id: str
    id: str
    name: str


class PendingReactionDecision(BaseModel):
    decision_kind: Literal["meaningful_choice"]
    event_id: str = Field(description="ID of a material new resolver event that caused this unresolved decision")
    character_id: str
    decision: str = Field(min_length=1, max_length=1200, description="The unresolved meaningful choice, not a possible reaction, routine, or already completed action")


class LocationAddition(BaseModel):
    event_id: str
    id: str = Field(min_length=1, max_length=80, description="Response-local reference; engine assigns persistent ID")
    name: str = Field(min_length=1)
    description: str = ""


class ItemAddition(StoryInitItem):
    event_id: str


class RelationshipAddition(RelationshipSeed):
    event_id: str


class EntityAdditions(BaseModel):
    locations: List[LocationAddition] = Field(default_factory=list, max_length=20)
    items: List[ItemAddition] = Field(default_factory=list, max_length=30)
    relationships: List[RelationshipAddition] = Field(default_factory=list, max_length=30)


class DecisionGroup(BaseModel):
    id: str = Field(min_length=1)
    mode: Literal["sequential", "parallel"] = "parallel"
    character_ids: List[str] = Field(min_length=1, max_length=20)
    depends_on: List[str] = Field(default_factory=list)
    requires_resolved_outcome: bool = False
    stop_for_player: bool = False


class PublicStart(BaseModel):
    text: str = Field(min_length=1, max_length=1200)
    observer_ids: List[str] = Field(default_factory=list)
    modality: Literal["saw", "heard", "faintly_heard", "felt"] = "heard"


class ElapsedTime(BaseModel):
    amount: float = Field(default=0, ge=0, allow_inf_nan=False)
    unit: Literal["seconds", "minutes", "hours", "days"] = "seconds"
    clock_beats: int = Field(default=1, ge=0, le=10000)
    next_meaningful_moment: str = ""


class AttemptResult(BaseModel):
    intent_id: str
    status: Literal["succeeded", "failed", "interrupted", "pending"]
    event_id: Optional[str] = None
    summary: str = ""


class Commitment(BaseModel):
    id: str
    event_id: str
    description: str = Field(min_length=1)
    participants: List[str] = Field(default_factory=list)
    conditions: str = ""
    deadline: Optional[str] = None
    status: Literal["pending", "fulfilled", "failed", "abandoned"] = "pending"


class ResolverResponse(BaseModel):
    entity_additions: EntityAdditions = Field(default_factory=EntityAdditions)
    elapsed_time: ElapsedTime = Field(default_factory=ElapsedTime)
    attempt_results: List[AttemptResult] = Field(default_factory=list)
    commitments: List[Commitment] = Field(default_factory=list)
    repetition_assessment: str = ""
    consistency_issues: List[str] = Field(default_factory=list, description="Detected material prose/event/state contradictions; never accept these")
    failure_policy: Literal["continue", "end", "switch_or_retry"] = "continue"
    chapter_title: str = Field(default="", max_length=160, description="Current chapter title; keep stable until chapter ends")
    director_plan: str = Field(default="", max_length=6000, description="Updated evolving plot arc: completed milestones, current conflict, plausible next developments; not a predetermined outcome")
    director_notes: str = Field(default="", max_length=4000, description="Updated pacing notes, unresolved decisions and consequences to resolve next")
    world_description: str = Field(default="", max_length=6000, description="Updated world description based only on established developments; retain enduring rules")
    prose: str = Field(min_length=1, description="Finished narrative prose in Finnish")
    events: List[StoryEvent] = Field(description="Authoritative events and the characters who perceived each event")
    recap_delta: str = Field(default="", max_length=1200, description="One to four sentences describing only this new beat")
    continuity: ContinuityDelta = Field(default_factory=ContinuityDelta)
    decision_character_ids: List[str] = Field(default_factory=list, description="Characters needing an independent important decision next turn")
    pending_reaction_decisions: List[PendingReactionDecision] = Field(default_factory=list, max_length=20)
    scene_stop: bool = Field(default=False, description="Stop at a meaningful scene boundary rather than automatically continuing")
    location: Optional[SceneLocation] = None
    scene_goal: Optional[str] = None
    chapter_end: bool = False
    requires_player_input: bool = False
    character_state_updates: List[CharacterStateUpdate] = Field(default_factory=list, description="Director's authoritative updates to each character's condition, mental state, and memory based on what happened")
    active_character_ids: Optional[List[str]] = Field(default=None, description="List of character IDs who remain active/present in the scene for next turn")
    choices: List[str] = Field(default_factory=list, description="2-4 interesting choice suggestions for next turn")
    spawned_characters: List[StoryInitCharacter] = Field(default_factory=list, description="New characters with unique IDs, never replacements")
    truth_access_updates: List[TruthAccessUpdate] = Field(default_factory=list, description="Update obsolete discovery routes when evidence moves or access is destroyed; do not alter the secret fact")
    state_changes: List[StateChange] = Field(default_factory=list, description="Realized consequences for existing items, relationships and character locations; never pending intentions")
    bible_additions: StoryBibleResponse = Field(default_factory=StoryBibleResponse)
    image_prompt: Optional[str] = Field(default="", description="English image generation prompt for illustration")


class ProseTurnResponse(ResolverResponse):
    summary: str = ""
    world_facts: List[str] = Field(default_factory=list)
    plot_threads: List[str] = Field(default_factory=list)
    scene_location: Optional[str] = None

    @field_validator("summary", mode="before")
    @classmethod
    def bound_summary(cls, value):
        if isinstance(value, str) and len(value) > 6000:
            return value[:5997].rsplit(" ", 1)[0] + "..."
        return value

class PlannerResponse(BaseModel):
    interaction_mode: Literal["static", "adaptive"] = Field(default="static", description="Adaptive: supply only the initial group; situation controller chooses subsequent reactions")
    elapsed_time: Optional[ElapsedTime] = None
    decision_groups: List[DecisionGroup] = Field(default_factory=list, max_length=8)
    stop_condition: str = ""
    plot_guidance_reason: str = ""
    events: List[StoryEvent] = Field(default_factory=list)
    decision_character_ids: List[str]
    direction: str = Field(min_length=1, max_length=4000)
    reveals: List[RevealDecision] = Field(default_factory=list)
    clock_ticks: List[ClockTick] = Field(default_factory=list)
    offscreen_moves: Dict[str, str] = Field(default_factory=dict)
    state_changes: List[StateChange] = Field(default_factory=list)
    bible_additions: StoryBibleResponse = Field(default_factory=StoryBibleResponse)


class ReactionGroup(BaseModel):
    mode: Literal["sequential", "parallel"] = "parallel"
    reactions: List[PendingReactionDecision] = Field(min_length=1, max_length=20)


class RelayPermit(BaseModel):
    source_event_id: str
    participant_ids: List[str] = Field(min_length=2, max_length=20)
    max_utterances: int = Field(ge=1, le=6)
    volume: Literal["whisper", "normal", "shout"] = "normal"
    modality: Literal["heard"] = "heard"


class NarrativeSourceRepair(BaseModel):
    model_config = {"extra": "forbid"}
    target: Literal["summary", "memory"]
    original_text: str = Field(min_length=1)
    memory_id: Optional[int] = None
    event_ids: List[str] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=600)


class InteractionProse(BaseModel):
    model_config = {"extra": "forbid"}
    prose: str = Field(min_length=1)
    choices: List[str] = Field(default_factory=list, max_length=5)
    chapter_title: str = Field(default="", max_length=160)
    image_prompt: str = ""
    consistency_issues: List[str] = Field(default_factory=list, description="Remaining contradictions in the NEW prose only; correct these before returning")
    source_issues: List[str] = Field(default_factory=list, description="Background contradictions already avoided in the finished prose; non-blocking audit")
    source_repairs: List[NarrativeSourceRepair] = Field(default_factory=list, max_length=20)


class SituationResponse(BaseModel):
    model_config = {"extra": "forbid"}
    events: List[StoryEvent] = Field(default_factory=list, max_length=30)
    state_changes: List[StateChange] = Field(default_factory=list)
    character_state_updates: List[CharacterStateUpdate] = Field(default_factory=list)
    entity_additions: EntityAdditions = Field(default_factory=EntityAdditions)
    spawned_characters: List[StoryInitCharacter] = Field(default_factory=list)
    location: Optional[SceneLocation] = None
    active_character_ids: Optional[List[str]] = None
    truth_access_updates: List[TruthAccessUpdate] = Field(default_factory=list)
    bible_additions: StoryBibleResponse = Field(default_factory=StoryBibleResponse)
    attempt_results: List[AttemptResult] = Field(default_factory=list)
    commitments: List[Commitment] = Field(default_factory=list)
    elapsed_time: ElapsedTime = Field(default_factory=lambda: ElapsedTime(clock_beats=0))
    continuity: ContinuityDelta = Field(default_factory=ContinuityDelta)
    recap_delta: str = Field(default="", max_length=1200)
    next_group: Optional[ReactionGroup] = None
    relay_permit: Optional[RelayPermit] = None
    failure_policy: Literal["continue", "end", "switch_or_retry"] = "continue"
    chapter_end: bool = False
    stop_reason: Literal["continue", "player", "ended", "waiting", "frame_exhausted"] = "ended"
    reason: str = Field(default="", max_length=600)
    consistency_issues: List[str] = Field(default_factory=list)


class CharacterDecisionResponse(BaseModel):
    interaction_kind: Literal["attempt", "speech", "wait"] = Field(default="attempt", description="Speech-only means this complete utterance has no concurrent action; a hint, not permission to choose observers")
    suggested_recipient_ids: List[str] = Field(default_factory=list)
    resolution_hint: bool = Field(default=True, description="Hint only; the controller or a verified relay permit authorizes delivery")
    public_start: Optional[PublicStart] = Field(default=None, description="Only currently observable onset or complete utterance, never intended outcomes or private plans")
    goal: str = Field(description="The character's current goal")
    time_horizon: str = Field(description="How long this goal-level action should take")
    action: str = Field(description="One consequential goal-level action the character intends")
    speech: str
    target: Optional[str] = None
    volume: Literal["whisper", "normal", "shout"] = "normal"
    if_interrupted: str
    private_thought: str
    memory: Optional[str] = None
    importance: int = Field(ge=1, le=10)
    belief_updates: List[str] = Field(default_factory=list)
    goal_update: Optional[str] = None

class PlayerViewDraft(BaseModel):
    prose: str = Field(min_length=1, max_length=12000, description="Limited viewpoint story prose using only supplied private knowledge and perceived events")
    recap_delta: str = Field(default="", max_length=1200, description="One to four new viewpoint-limited sentences")
    chapter_title: str = Field(min_length=1, max_length=160, description="Chapter title that reveals no unknown secret")
    choices: List[str] = Field(default_factory=list, max_length=5, description="Possible actions based only on what this character knows; never in prose")


class PlayerViewResponse(PlayerViewDraft):
    recap: str = ""

    @field_validator("recap", mode="before")
    @classmethod
    def bound_recap(cls, value):
        if isinstance(value, str) and len(value) > 4000:
            return value[:3997].rsplit(" ", 1)[0] + "..."
        return value

    @field_validator("recap_delta", mode="before")
    @classmethod
    def bound_recap_delta(cls, value):
        if isinstance(value, str) and len(value) > 1200:
            return value[:1197].rsplit(" ", 1)[0] + "..."
        return value

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
