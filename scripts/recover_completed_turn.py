import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiosqlite

from core.schemas import ProseTurnResponse
from core.types import SceneTurn, TurnResponse
from database import db, turn_store


async def recover(args):
    response = TurnResponse.model_validate(json.loads(Path(args.response).read_text(encoding="utf-8-sig"))["data"])
    outcome = ProseTurnResponse.model_validate_json(Path(args.outcome).read_text(encoding="utf-8"))
    outcome.prose = response.director_prose
    outcome.choices = response.choices
    outcome.image_prompt = response.image_prompt
    outcome.chapter_end = response.is_chapter_end
    if response.spawned_characters:
        raise ValueError("Recovering spawned characters requires a complete original recovery bundle.")
    if await turn_store.get_receipt(args.story, response.request_id):
        await turn_store.verify_committed_turn(args.story, response)
        print("Turn is already saved; no changes made.")
        return
    revision = await turn_store.get_revision(args.story)
    if revision != args.revision:
        raise turn_store.TurnConflictError("Story revision changed; recovery cancelled.")
    turns = await db.get_all_story_turns(args.story)
    last = max((turn.id or 0 for turn in turns), default=0)
    if last != args.last_id or response.turn_index != max((turn.turn_index for turn in turns), default=0) + 1:
        raise turn_store.TurnConflictError("Story turn sequence changed; recovery cancelled.")
    scene = await db.get_active_scene(args.story)
    if not scene or scene.id is None:
        raise ValueError("Active scene missing.")
    existing_ids = {character.id for character in await db.get_all_characters(args.story)}
    if {character.id for character in response.updated_characters} != existing_ids:
        raise ValueError("Recovered character roster differs from the stored roster.")
    if not set(outcome.active_character_ids or []) <= existing_ids:
        raise ValueError("Unknown active character.")
    for event in outcome.events:
        if not set(event.witnesses) <= existing_ids:
            raise ValueError("Unknown witness.")
    backup_dir = turn_store.get_recovery_dir(args.story)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    backup = backup_dir / f"before-recovery-{stamp}.db"
    async with aiosqlite.connect(db.get_db_path(args.story)) as source:
        async with aiosqlite.connect(backup) as destination:
            await source.backup(destination)
    runtime = await turn_store.get_runtime(args.story)
    outcome.summary = runtime.get("summary", "") + "\n\n" + outcome.summary
    outcome.world_facts = list(dict.fromkeys(runtime.get("world_facts", []) + outcome.world_facts))
    outcome.plot_threads = list(dict.fromkeys(runtime.get("plot_threads", []) + outcome.plot_threads))
    if len(outcome.summary) > 6000 or len(outcome.world_facts) > 40 or len(outcome.plot_threads) > 20:
        raise ValueError("Recovered continuity exceeds limits; review the outcome before recovery.")
    fingerprint = hashlib.sha256(json.dumps([
        response.mode, args.user_input, None, None
    ], ensure_ascii=False).encode()).hexdigest()
    turn = SceneTurn(scene_id=scene.id, turn_index=response.turn_index,
                     acting_character_id=(response.acting_character or {}).get("id"),
                     internal_monologue=response.internal_monologue or "",
                     character_action=response.character_action or "",
                     director_prose=response.director_prose, choices=response.choices,
                     image_prompt=response.image_prompt)
    await turn_store.commit_turn(args.story, last, turn, response.updated_characters, outcome, response,
                                 fingerprint, {"source": "manual_recovery", "original_response": args.response,
                                               "continuity": "previous state plus reviewed recovery delta",
                                               "backup": str(backup)}, expected_revision=revision)
    await turn_store.rebuild_exports(args.story)
    await turn_store.verify_committed_turn(args.story, response)
    print(f"Recovered turn {response.turn_index}; backup: {backup}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--story", required=True)
    parser.add_argument("--response", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--last-id", required=True, type=int)
    parser.add_argument("--user-input", required=True)
    asyncio.run(recover(parser.parse_args()))