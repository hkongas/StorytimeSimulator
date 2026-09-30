# Tarinamoottori / StorytimeSimulator

[Suomenkielinen versio](README.md)

> **Work in progress:** this application is still under development. It has not been broadly or independently tested, nor validated for production use. The included automated tests and limited development-time browser checks do not guarantee correct operation.

A browser-based story engine that stores data locally. The same story can continue as a novel, a simulation of autonomous characters, or a roleplay controlled through one character. The world can be influenced in any mode.

## Getting Started

Python 3.10 or newer and an API key for an LLM service are required. The development environment has been tested with Python 3.14. The browser UI does not require Node.js or a separate build step.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Open http://127.0.0.1:8000. Configure the API key and models in the UI or in the project's `.env` file, using `.env.example` as a template. Run a single server process. Automatic code reload is disabled so editing does not interrupt generation.

If the port is already in use:

```powershell
python -m uvicorn web.api:app --host 127.0.0.1 --port 8001
```

## Three Modes

| Mode | Character decisions | Narrator's role |
| --- | --- | --- |
| Novel | Character agents are called only at significant decision points identified by the previous turn. | Continues routine actions and transitions smoothly, then pauses before the next important independent decision. |
| Simulation | Every active character present makes an independent decision. Up to five calls run concurrently; other characters are not dropped. | Resolves conflicting intentions and their consequences. Not every character needs to speak. |
| Roleplay | The player's action goes directly to the narrator. Other characters present make their own decisions. | Preserves the player's attempt, resolves its consequences, and pauses before the player's next significant choice. |

The mode can be changed during a story. **Play as character** on a character card switches to roleplay. The character must be active in the current scene and able to act.

- **Private intention** gives the player's plan to the narrator, not to other characters.
- **Change the world** gives the narrator a world change for the next turn. Characters receive its observable consequences in their next decisions, not the original instruction.
- Novel and simulation modes support a limited automatic continuation of up to ten turns. Each continuation may make paid model calls.
- **Stop** ends work in progress. It does not undo a turn that has already been committed.
- **Show secrets** reveals private director and character information. This is a reading preference, not an access-control boundary between users.

## Turn Data Flow

```text
Story state and revision
  -> characters selected for the mode + their own observations and memories
  -> independent intentions / direct player action
  -> narrator: events, witnesses, consequences, continuity, and prose
  -> local schema and identifier validation
  -> revision check and one database transaction
  -> completed turn receipt and regenerable text exports
```

**Prose is not a shared source of character knowledge.** The narrator returns separate events and their witnesses. The engine gives each character only the events that character witnessed. The director's plot, other characters' thoughts, and omniscient narration are not passed directly into character prompts.

Memory retrieval combines recent memories with older memories that are verbally related to the location or motif and marked as important. The narrator maintains a cumulative summary, persistent facts, open plot threads, and the next decision-makers. This is bounded text memory, not an unlimited or infallible memory system.

## Storage and Recovery

- Each story has its own SQLite database at `stories/<id>/story.db`.
- Character changes, observations, memories, scene, prose, continuity state, and request receipt are committed together in one transaction.
- A state revision prevents generation based on stale state from overwriting an intervening edit.
- Resubmitting the same request ID returns the committed response. Do not reuse an ID for different content.
- The browser tracks server-side background work. Reloading the page does not start another turn. The in-progress request ID is kept in the tab's `sessionStorage`.
- Restarting the server interrupts in-progress work. Completed receipts remain in the database. **Reconnect** resumes the same request.
- Truncated or invalid model responses are rejected; they are not turned into an invented fallback story.
- `story.txt` and `story.md` are exports generated from the database. Manual edits to them do not update story state and will be overwritten by the next export.

An old database is migrated when opened. Before a version 4 migration, an existing database is backed up to `story.pre-v4.db` using SQLite's backup mechanism. Keep additional backups of important stories. Do not use the same story directory from multiple computers at once through cloud sync.

## Privacy and Configuration

Storage is local, but when using a cloud model, its prompts, character information, and story excerpts are sent to the selected provider. The application is therefore not automatically fully local or offline.

API keys are stored in the server-side `.env` and `.provider-profiles.json` files. They are not returned by the settings GET endpoint or saved to new browser profiles. Keys in older browser profiles are migrated to the server before being removed from browser storage. These files are **unencrypted** and excluded from Git; protect the user account, directory, and backups appropriately.

The application is a local, single-owner tool. It has no login or multi-user support and is not intended for internet deployment. The service accepts localhost hosts and rejects requests from foreign browser origins. Story and prompt paths are confined to their own directories. Model output and imported character-card text are not executed as HTML.

Settings provide a shared provider and separate narrator and character models. The code supports xAI, Azure, OpenAI, OpenRouter, and OpenAI-compatible endpoints; the current browser profile view covers xAI and Azure. Other providers can be configured through environment settings. API features may vary by model.

The API log includes input, output, reasoning, and cached tokens when reported by the service. Cached tokens are a subset of input tokens. A price is shown only when reported by the service, and the summary indicates how many calls have price data. A missing price does not mean a call was free.

`MAX_INPUT_TOKENS` limits the estimated input size (default: 64000). The estimate is character-based, not the model's exact tokenizer. Exceeding the limit stops the request before the network call; content is not silently truncated.

## Project Structure

- `engine/story_engine.py`: mode-specific turn flow and commit logic.
- `engine/director_agent.py`, `engine/character_agent.py`: agent inputs and validated responses.
- `database/turn_store.py`: turn transaction, observations, continuity, and request receipts.
- `database/db.py`: other database operations, memory retrieval, and versioned migrations.
- `core/schemas.py`: data contracts for model responses.
- `core/llm_client.py`, `core/providers/`: model interfaces, responses, and logging.
- `core/profile_store.py`: server-side key profiles.
- `web/api.py`: local API and background turn jobs.
- `web/static/app.js`: story, character, prompt, and settings views.
- `web/static/turns.js`: turn request tracking, recovery, and cancellation.
- `prompts/`: default prompts; `prompts/custom/`: custom overrides.

Legacy chronicle, perceptual-filter, and watchdog functions remain in the source for compatibility. The active turn path uses events and narrator continuity state, not a separate chronicle or watchdog call every fourth or sixth turn. Legacy API mode names are mapped as follows: `reader -> novel`, `player -> roleplay`, `director -> simulation`.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary directories and fake models, not the user's stories or real model calls. They cover, among other things, information boundaries, mode differences, player actions, storage integrity, request replay, edit conflicts, memory retrieval, migrations, background jobs, and path confinement. The test suite is limited and does not cover every usage scenario.

The UI has been tried during development at desktop and mobile widths, but comprehensive browser or user testing has not been done. Assessing prose quality and long-story recall requires separate experiments with real models.

## Current Limitations

Witness filtering prevents direct leakage of shared prose context. The narrator is still a language model and may produce an incorrect account of who witnessed an event or an inconsistent consequence. Schema validation does not prove that events are semantically correct. Decision points and paragraph pacing depend on the model and prompts.

Turn undo, story branches, post-editing prose, image generation, and a multi-process server job queue are not implemented. Illustration prompts can still be generated. These features should build on the committed event and state model rather than bypass it.