from core.schemas import InteractionProse
from httpx import HTTPError


async def render_accepted_interaction(director, story_id, outcome, scene, runtime, recent_prose, intentions):
    audit = {"attempts": [], "source_repairs": [], "fallback": False}
    feedback = ""
    for _ in range(2):
        try:
            draft = await director.render_interaction(
                story_id, outcome, scene, runtime | {"render_validation_error": feedback}, recent_prose, intentions)
            rendered = InteractionProse.model_validate(draft)
            audit["attempts"].append(rendered.model_dump())
            if not rendered.prose.strip():
                raise ValueError("Finished prose must not be blank")
            if rendered.consistency_issues:
                feedback = "Correct only the new prose, keeping all accepted events unchanged: " + "; ".join(rendered.consistency_issues)
                continue
            audit["source_repairs"] = [item.model_dump() for item in rendered.source_repairs]
            return rendered, audit
        except (ValueError, RuntimeError, HTTPError) as error:
            feedback = str(error)
            audit["attempts"].append({"error": feedback})
    audit["fallback"] = True
    # These descriptions are already accepted narrator facts, not fresh model decisions.
    prose = "\n\n".join(event.description.strip() for event in outcome.events if event.description.strip())
    return InteractionProse(prose=prose or "Tilanne jää odottamaan. Vahvistettuja uusia tapahtumia ei ole."), audit
