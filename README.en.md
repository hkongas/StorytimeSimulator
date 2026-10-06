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

## Reading Views And Evolving Plot

The reading toolbar separates omniscient narrator prose from the selected player character's limited view. Roleplay displays the limited view; switching to novel or simulation returns to the narrator view. The narrator can incorporate characters' supplied private thoughts. Limited prose and recaps are generated from only that character's public profile, memories, intention and witnessed events, never from shared omniscient prose. The canonical turn commits first; a failed limited-view call is recorded as `view_failed` and can be retried without undoing the turn. Witness attribution remains model-dependent; this is not multi-user access control.

Viewpoint and chapter navigation stay visible above the scrolling reading area. A fixed 320-pixel tail after the prose holds the writing hint, generation progress or choices; long contents scroll within it. The authored continuation editor can expand beyond this height. Character memories have a keyboard-focusable scrolling list capped at 240 pixels. Turn and API-log timestamps use the computer's browser-local timezone, including daylight saving; database timestamps remain UTC. Chapter navigation uses stable titles. Optional recaps and titles follow the selected viewpoint. Legacy turns or turns belonging to another selected character have an explicit unavailable-view marker rather than a guessed or omniscient fallback. The prose editor edits only narrator text and does not rewrite the limited version. TXT/Markdown exports remain narrator prose.

Secret truths, clocks and offscreen agents are optional (zero or more). Initialization creates them only when warranted by the premise or user request. An empty bible stays empty. The narrator may add supported new entries through `bible_additions`; users can edit them in the bible editor. New truths start hidden and cannot overwrite existing facts. Reveals and clock expiry remain narrator-only until explicit per-character observations establish perception. Quiet stories need no mysteries, hazards or deadlines.

Model contracts are phase-specific. Character responses have one action, speech and private thought, without duplicate compatibility fields. The planner cannot return scene movement or character-state updates. The resolver returns this beat's `recap_delta` and continuity fact/thread additions and removals, not a rewritten cumulative history. The engine merges these deltas and periodically compresses long history in a separate model call. State consequences reference a verified `event_id`; voluntary actions and authorized routines reference the exact current `intent_id`. Events use one `observations` list with each observer's text, and locations separate identity from display name with `location: {event_id, id, name}`.

## Text Editing

The pencil button opens each turn's prose editor. Saving changes the text and both exports without model calls. Recent edited prose reaches the narrator's next context. Revision checks reject stale saves. Old and new text are retained in the `prose_edits` table; a history restore UI is not implemented.

Text editing does not update events, observations, memories or continuity summaries. Use it for wording and style, not plot changes. Automatic reconciliation is not implemented; `sync_state: true` is rejected without saving. Earlier prose can be edited, but later state is not rewritten.

**Oma jatkokappale** adds an authored continuation without rewriting its prose. Analyze it using the narrator model, review the proposed events, witnesses, character states and continuity, then approve the atomic save. Approval makes no additional model call. Preview does not change story state and expires after 30 minutes or a server restart. Changes made meanwhile invalidate approval. New authored turns support undo. The initial version accepts up to 20,000 characters and does not create new characters; add required characters first. Existing prose-edit reconciliation is still not implemented. Turn input fields are disabled while generating, and failed or cancelled turns retain the input text.

Undo restores characters, memories, observations, scenes and runtime from the last turn's snapshot. Only turns generated by this version have snapshots; opening and legacy turns cannot be undone. Later state edits block undo, while prose edits do not. Model costs are retained. Editor opening and undo stop automatic continuation.

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

Memory retrieval is stable and combines recency, importance, and keyword relevance while keeping high-importance memories. Memories link to source events; narrator-written interpretation is not inserted as first-person character memory. Recap deltas are merged by the engine and bounded deterministically.

## Storage and Recovery

- Each story has its own SQLite database at `stories/<id>/story.db`; current development schema 9 includes a `story_branches` foundation and the default `main` branch.
- Character changes, observations, memories, scene, prose, continuity state, and request receipt are committed together in one transaction.
- A state revision prevents generation based on stale state from overwriting an intervening edit.
- Resubmitting the same request ID returns the committed response. Do not reuse an ID for different content.
- The browser tracks server-side background work. Reloading the page does not start another turn. The in-progress request ID is kept in the tab's `sessionStorage`.
- Restarting the server interrupts in-progress work. Completed receipts remain in the database. **Reconnect** resumes the same request.
- Truncated or invalid model responses are rejected; they are not turned into an invented fallback story.
- `story.txt` and `story.md` are exports generated from the database. Manual edits to them do not update story state and will be overwritten by the next export.

This is an unpublished development version. Old databases are not migrated or automatically repaired; recreate stories using the current schema. Existing files are not automatically deleted. Do not use the same story directory from multiple computers at once through cloud sync.

## Privacy and Configuration

Storage is local, but when using a cloud model, its prompts, character information, and story excerpts are sent to the selected provider. The application is therefore not automatically fully local or offline.

API keys are stored in the server-side `.env` and `.provider-profiles.json` files. They are not returned by the settings GET endpoint or saved to new browser profiles. Keys in older browser profiles are migrated to the server before being removed from browser storage. These files are **unencrypted** and excluded from Git; protect the user account, directory, and backups appropriately.

The application is a local, single-owner tool. It has no login or multi-user support and is not intended for internet deployment. The service accepts localhost hosts and rejects requests from foreign browser origins. Story and prompt paths are confined to their own directories. Model output and imported character-card text are not executed as HTML.

Settings provide a shared provider and separate narrator and character models. Planning, prose, story initialization, characters and player views have separate temperature/token/reasoning settings (`DIRECTOR_PLAN_*`, `PROSE_*`, `STORY_INIT_*`, `CHARACTER_*`, `PLAYER_VIEW_*`). The code supports xAI, Azure, Gemini, OpenAI, OpenRouter, and OpenAI-compatible endpoints; the browser profile view covers xAI, Azure and Google AI Studio. Gemini uses Google's OpenAI-compatible text endpoint. Configure `GEMINI_API_KEY` and `LLM_PROVIDER=gemini` or create a browser profile. Model names are editable. Google's current documentation restricts 2.5 models to previous users, so new profiles default to the documented newer Flash and Flash-Lite models. See the [Gemini assessment (Finnish)](ARVIO_GEMINI.md). Other providers can be configured through environment settings.

The API log includes input, output, reasoning, and cached tokens when reported by the service. Cached tokens are a subset of input tokens. A price is shown only when reported by the service, and the summary indicates how many calls have price data. A missing price does not mean a call was free.

Full prompt and response content can be retained gzip-compressed in the local `api_calls` table with `LLM_CALL_CONTENT_LOGGING=true`. The log viewer's **Content** action opens an individual request and response. This is disabled by default because prompts contain private story material. `LLM_CALL_RETENTION_DAYS` defaults to 30.

`MAX_INPUT_TOKENS` limits the estimated input size (default: 64000). The estimate is character-based, not the model's exact tokenizer. Exceeding the limit stops the request before the network call; content is not silently truncated.

Output budgets default to 128000 tokens for the director and prose, and 64000 for character agents and structured planning/player-view responses. Saved browser profiles and `.env` values override these defaults and are not changed automatically. The model or provider's own output limit still applies. Azure v1 uses `max_completion_tokens`, which may include reasoning tokens; truncation retries can increase the requested budget, so these values are not hard cost caps.

## Project Structure

- `engine/story_engine.py`: mode-specific turn flow and commit logic.
- `engine/director_agent.py`, `engine/character_agent.py`: agent inputs and validated responses.
- `database/turn_store.py`: turn transaction, observations, continuity, and request receipts.
- `database/db.py`: other database operations, memory retrieval, and current-schema initialization.
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

Frontend timestamp and structure regressions can run separately with Node.js (only for testing, not application use):

```powershell
node --test tests\test_frontend.cjs
```

Tests use temporary directories and fake models, not the user's stories or real model calls. They cover, among other things, information boundaries, mode differences, player actions, storage integrity, request replay, edit conflicts, memory retrieval, schema validation, background jobs, and path confinement. The test suite is limited and does not cover every usage scenario.

The UI has been tried during development at desktop and mobile widths, but comprehensive browser or user testing has not been done. Assessing prose quality and long-story recall requires separate experiments with real models.

## Current Limitations

Witness filtering prevents direct leakage of shared prose context. The narrator is still a language model and may produce an incorrect account of who witnessed an event or an inconsistent consequence. Schema validation does not prove that events are semantically correct. Decision points and paragraph pacing depend on the model and prompts.

Branch storage and branch-aware turn/snapshot identifiers are present, but branch creation and UI are not implemented. Automatic reconciliation of prose edits, image generation, and a multi-process server job queue are also not implemented. Illustration prompts can still be generated. These features should build on the committed event and state model rather than bypass it.