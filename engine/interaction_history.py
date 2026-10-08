from core.schemas import ProseTurnResponse
from engine.turn_contract import merge_continuity, validate_event_links
from engine.simulation_contract import consequence_links


def merge_intermediate_history(outcome, intermediate, runtime):
    if not intermediate:
        return
    for field in ("state_changes", "character_state_updates", "attempt_results", "commitments",
                  "truth_access_updates", "spawned_characters"):
        setattr(outcome, field, [value for item in intermediate for value in getattr(item, field)] + getattr(outcome, field))
    for field in ("locations", "items", "relationships"):
        setattr(outcome.entity_additions, field,
                [value for item in intermediate for value in getattr(item.entity_additions, field)]
                + getattr(outcome.entity_additions, field))
    for field in ("secret_truths", "clocks", "offscreen_agents"):
        setattr(outcome.bible_additions, field,
                [value for item in intermediate for value in getattr(item.bible_additions, field)]
                + getattr(outcome.bible_additions, field))
    units = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}
    for item in intermediate:
        outcome.elapsed_time.amount += item.elapsed_time.amount * units[item.elapsed_time.unit] / units[outcome.elapsed_time.unit]
        outcome.elapsed_time.clock_beats += item.elapsed_time.clock_beats
    state = dict(runtime)
    for item in [*intermediate, outcome]:
        state.update(merge_continuity(item, state))
    outcome.summary = outcome.summary or state["summary"]
    outcome.world_facts = state["world_facts"]
    outcome.plot_threads = state["plot_threads"]
    outcome.recap_delta = "\n".join(item.recap_delta for item in [*intermediate, outcome] if item.recap_delta)


def accepted_outcome(plan, intermediate, runtime, scene):
    outcome = ProseTurnResponse(prose="Candidate awaiting narrative", events=list(plan.events),
                                elapsed_time=plan.elapsed_time or {"clock_beats": 0})
    outcome.events += [event for item in intermediate for event in item.events]
    if intermediate:
        merge_intermediate_history(outcome, intermediate, runtime)
    else:
        for key, value in merge_continuity(outcome, runtime).items():
            setattr(outcome, key, value)
    outcome.scene_location = scene.location
    outcome.scene_goal = scene.scene_goal
    outcome.active_character_ids = list(scene.active_character_ids)
    if intermediate:
        last = intermediate[-1]
        outcome.scene_stop = last.scene_stop
        outcome.failure_policy = last.failure_policy
        outcome.chapter_end = last.chapter_end
        outcome.requires_player_input = last.requires_player_input
        outcome.pending_reaction_decisions = last.pending_reaction_decisions
        outcome.location = next((item.location for item in reversed(intermediate) if item.location), None)
    validate_event_links(outcome.events, consequence_links(outcome))
    return outcome
