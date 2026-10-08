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
| Simulation | Capable characters present make independent decisions in narrator-selected sequential or parallel groups. | Resolves conflicting intentions and their consequences. Not every character needs to speak in the same moment. |
| Roleplay | The player's action goes directly to the narrator. Other characters present make their own decisions. | Preserves the player's attempt, resolves its consequences, and pauses before the player's next significant choice. |

The mode can be changed during a story. **Play as character** on a character card switches to roleplay. The character must be active in the current scene and able to act.

- **Private intention** gives the player's plan to the narrator, not to other characters.
- **Change the world** gives the narrator a world change for the next turn. Characters receive its observable consequences in their next decisions, not the original instruction.
- Novel and simulation modes support a limited automatic continuation of up to ten turns. Each continuation may make paid model calls.
- **Stop** ends work in progress. It does not undo a turn that has already been committed.
- **Show secrets** reveals private director and character information. This is a reading preference, not an access-control boundary between users.

## Reading Views And Evolving Plot

The reading toolbar separates omniscient narrator prose from the selected player character's limited view. Roleplay displays the limited view; switching to novel or simulation returns to the narrator view. The narrator can incorporate characters' supplied private thoughts. Limited prose and recaps are generated from only that character's public profile, memories, intention and witnessed events, never from shared omniscient prose. The canonical turn commits first; a failed limited-view call is recorded as `view_failed` and can be retried without undoing the turn. Witness attribution remains model-dependent; this is not multi-user access control.

Viewpoint and chapter navigation stay visible above the scrolling reading area. A fixed 320-pixel tail after the prose holds the writing hint, generation progress or choices; long contents scroll within it. The authored continuation editor can expand beyond this height. Character memories have a keyboard-focusable scrolling list capped at 240 pixels. Turn and API-log timestamps use the computer's browser-local timezone, including daylight saving; database timestamps remain UTC. Chapter navigation uses stable titles. Optional recaps and titles follow the selected viewpoint. Legacy turns or turns belonging to another selected character have an explicit unavailable-view marker rather than a guessed or omniscient fallback. When the latest view is absent, the player reading view offers an optional character catch-up with a separate paid-call confirmation. One logical model call summarizes only the character's memories, observations and own latest intention. The stored note is separate from historical prose and does not modify events or memories. It is reused only while the story revision remains unchanged; state changes hide stale notes. Pending or failed normal viewpoint generation uses its existing retry action instead. The prose editor edits only narrator text and does not rewrite the limited version. TXT/Markdown exports remain narrator prose.

The narrator world panel also displays read-only items (holder or location and state) and directed character relationships (attitude, trust and summary). Saving the secret-bible editor preserves these arrays. This panel requires **Show secrets** and stays unavailable in roleplay, since full locations and other characters' attitudes could disclose unknown information.

Secret truths, clocks and offscreen agents are optional (zero or more). Initialization creates them only when warranted by the premise or user request. An empty bible stays empty. The narrator may add supported new entries through `bible_additions`; users can edit them in the bible editor. New truths start hidden and cannot overwrite existing facts. Reveals and clock expiry remain narrator-only until explicit per-character observations establish perception. Quiet stories need no mysteries, hazards or deadlines.

Model contracts are phase-specific. Character responses have one action, speech and private thought, without duplicate compatibility fields. The planner cannot return scene movement or character-state updates. The resolver returns this beat's `recap_delta` and continuity fact/thread additions and removals, not a rewritten cumulative history. The engine merges these deltas and periodically compresses long history in a separate model call. State consequences reference a verified `event_id`; voluntary actions and authorized routines reference the exact current `intent_id`. Events use one `observations` list with each observer's text, and locations separate identity from display name with `location: {event_id, id, name}`.

## Simulation contracts and orchestration

The [simulation plan (Finnish)](SUUNNITELMA_SIMULAATIO.md) records the design and acceptance criteria. An unknown character location (`location_id: null`) means absence from the local scene. Hidden presence is separate: a hidden character must not be disclosed through another character's nearby-name list. Remote perception needs an explicitly established information channel; it does not follow from an unknown location.

The narrator is not limited to a predefined location list. A new world entity and its consequences are validated together. Field-specific mutation contracts separate free-form descriptions from persisted identities, values, and event references. A bounded resolver repair preserves original character intentions rather than replaying the complete turn, and the corrected result must pass validation before commit.

The planner can request `interaction_mode: adaptive` and supply only one opening group (or none). A lightweight situation controller resolves fresh intentions and chooses subsequent groups from observed events and open attempts. New observations allow A → B → A and an initially unplanned C to react; each character–event stimulus is consumed once. An omitted mode defaults to `static`, preserving existing fake-model and old-schema behavior. Static groups can be sequential or parallel. Parallel decisions share a locked starting state without seeing each other's fresh responses. Adaptive mode and explicit static groups disable the legacy extra-reaction loop.

A bounded controller-issued `RelayPermit` can relay complete speech-only utterances without another controller call. It fixes visible colocated listeners, verified source hearing, volume, channel and utterance count. **The fast path relies on the controller's correct semantic speech-only, privacy and interruption authorization; character `resolution_hint` and field checks are not semantic proof.** Missing or invalidated permission returns to the controller. Private thoughts and guaranteed outcomes of unfinished attempts never become other characters' observations.

Candidate-phase limits cover character decisions, controller calls, per-character decisions, elapsed time and token reservations. The provisional budget is 48000 reserved tokens: UTF-8 bytes/3 estimates message input plus schema, with the output ceiling reserved separately. This estimator is not a hard bound on actual tokens, billed usage, or a whole-request limit. Planning, final prose and player-view calls are outside these limits. `frame_exhausted` stops rather than automatically replanning. Interruption recovery stores the candidate chain, pending boundary stimuli and next group, and blocks replay of the same request's intentions; autonomous continuation after restart is not implemented.

Intermediate events, continuity, attempt results, commitments and elapsed time are merged in order. The separate `InteractionProse` schema has no event or state fields: prose renders the immutable accepted chain, and narrative plus candidate state commit atomically. Background discrepancies are corrected in the new prose and audited without blocking the turn. Only remaining new-prose contradictions trigger a bounded retry with precise feedback; malformed output or rendering-service failure falls back to accepted event descriptions without rerunning decisions. Exact summary lines and selected reflection memories can be repaired using cited events; memory replacement uses only that character's observations. Repairs are audited and committed atomically with rollback support; old prose and belief memories remain unchanged. This applies to the adaptive rendering path, not the static compatibility resolver, and does not prove semantic correctness or repair the entire history. New world entities and characters may be added at the controller stage, not the prose stage; dedicated character-creation tests are still missing. Provider routing baseline passed 10/10, and the new situation-specific test passed separately, 1/1. Automated tests do not establish literary quality or cost savings. See the [interaction plan (Finnish)](SUUNNITELMA_VUOROVAIKUTUS.md) for implementation details and limitations.

Story guidance uses three presets: **Adaptive**, **Balanced**, and **Strong**. They control world pressure and plan persistence, not voluntary player choices. Attempt outcomes, commitments, and elapsed time remain in continuity. When the current player can no longer act, continuation may end the story, switch to an eligible character, or create a separate retry story from a snapshot without rewriting the original history.

Legacy unknown locations require a preview, explicit mapping, and current revision. Do not automatically accept every suggestion: an old null location may have an ambiguous meaning.

Conventional model calls remain the transport. No Realtime sessions are opened. The [Realtime follow-up design (Finnish)](SUUNNITELMA_REALTIME.md) documents dedicated model/endpoint restrictions, actor sessions, player interruption and token/cache billing. Keeping a connection open does not mean the growing conversation context is billed only once.

## Text Editing

The pencil button opens each turn's prose editor. Saving changes the text and both exports without model calls. Recent edited prose reaches the narrator's next context. Revision checks reject stale saves. Old and new text are retained in the `prose_edits` table; a history restore UI is not implemented.

Text editing does not update events, observations, memories or continuity summaries. Use it for wording and style, not plot changes. Automatic reconciliation is not implemented; `sync_state: true` is rejected without saving. Earlier prose can be edited, but later state is not rewritten.

**Oma jatkokappale** adds an authored continuation without rewriting its prose. Analyze it using the narrator model, review the proposed events, witnesses, character states and continuity, then approve the atomic save. Approval makes no additional model call. Preview does not change story state and expires after 30 minutes or a server restart. Changes made meanwhile invalidate approval. New authored turns support undo. The initial version accepts up to 20,000 characters and does not create new characters; add required characters first. Existing prose-edit reconciliation is still not implemented. Turn input fields are disabled while generating, and failed or cancelled turns retain the input text.

Undo restores characters, memories, observations, scenes and runtime from the last turn's snapshot. Only turns generated by this version have snapshots; opening and legacy turns cannot be undone. Later state edits block undo, while prose edits do not. Model costs are retained. Editor opening and undo stop automatic continuation.

## Optional Extra Reaction

**One extra reaction if needed** is a default-off legacy feature for the static path without explicit groups, including roleplay. The request option is `extra_reaction_cycle: true`. Adaptive reactions do not require it; adaptive mode and explicit decision groups suppress the duplicate extra cycle. After the resolver produces a material new event, it must identify an unresolved meaningful choice for a present, active AI character who observed that exact event. The engine checks event references, newness, progress, decision candidates and character eligibility. Possible reactions alone do not trigger it. Player decisions, scene/chapter stops, scene movement, invalid eligibility, no concrete progress, cancellation and the one-cycle cap stop automatic continuation.

The followup skips world planning and clock ticks, calls only eligible AI characters and resolves their fresh intentions. It never submits another player action, repeats the original action or reuses the world intervention. Both cycles share one locked, SSE-monitored cancellable job, with at most one extra decision/consequence cycle. Model calls can increase latency and cost; semantic event/choice quality still needs real-model evaluation.

Each cycle commits a separate atomic turn with its own receipt, recovery record, snapshot and player view. The first receipt links to the followup before it starts. Replaying the original request returns the committed followup if available, otherwise the first turn; interrupted or failed followups are never automatically resumed. Cancellation preserves committed turns. A followup without concrete progress is discarded. Undo removes the latest cycle only (undo twice to remove both); replay after undo is rejected. Default-off request fingerprints remain compatible with earlier receipts.

## Turn Data Flow

The static compatibility path resolves intentions and writes prose in the same response. In planner-requested adaptive mode, character decisions alternate with lightweight situation resolution, followed by a separate prose call that cannot modify the accepted event chain. Both paths preserve atomic commit and per-character observation boundaries.

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

During development, run only test methods, classes or modules related to the change, combined in one command. For example, for database schema validation changes:

```powershell
python -m unittest -v tests.test_engine.StorageTests.test_current_schema_initialization_is_repeatable tests.test_engine.StorageTests.test_legacy_database_is_rejected_without_migration tests.test_engine.StorageTests.test_incomplete_database_is_rejected_without_repair
```

Parent-reported final targeted validation:

| Run / selector | Result | Runner / wall |
| --- | --- | --- |
| `tests.test_adaptive_interaction` (completed module) | 18/18 passed | 5.331 s / 5.764 s |
| Adaptive interaction, simulation and turn contract (before the module's latest three tests; selectors below) | 26/26 passed | 8.682 s / 9.101 s |
| Provider/Azure/API routing baseline (selectors below) | 10/10 passed | 0.714 s / 2.909 s |
| `node --test tests\test_simulation_frontend.cjs tests\test_frontend.cjs` | 10/10 passed | 0.440 s / 0.525 s |

Combined-run selectors: `tests.test_adaptive_interaction`, `tests.test_simulation_plan.SimulationUnitTests`, `tests.test_simulation_plan.SimulationStorageTests.test_integrated_intermediate_resolution_is_atomic`, `tests.test_simulation_plan.SimulationStorageTests.test_same_response_creation_elapsed_attempt_and_commitment`, `tests.test_turn_contract.TurnContractTests.test_history_compression_is_separate_from_resolver`, and `tests.test_turn_contract.TurnContractTests.test_expired_clock_fires_once_without_omniscient_observers`.

Routing baseline: `tests.test_engine.ProviderTests`, `tests.test_engine.AzureTransportTests`, `tests.test_api.ApiTests.test_profile_secrets_are_not_returned`, and `tests.test_api.ApiTests.test_gemini_profile_key_stays_server_side`. The completed adaptive module covers the situation role model and defaults.

Earlier regressions were fixed and these runs passed; no full-project regression run is claimed, and overlapping tests are not summed. Storage tests isolate a 48000 budget from the user's `.env`. Module coverage includes public SSE phases during collection, unchanged events on prose retry, cancellation cleanup, and player seed → NPC → new player choice without a generated player answer, with the pending reaction persisted. An adaptive sequential group contains exactly one actor; multiple actors are allowed only in a parallel group sharing a locked moment. Final prose returns no event/state fields and retains tone guidance, not full resolver instructions. Dedicated new-character tests and real-model quality/savings comparisons remain outstanding. No tests were run for this documentation update.

A whole class: `python -m unittest -v tests.test_engine.StorageTests`. A module: `python -m unittest -v tests.test_turn_contract`. On Windows, invoke the virtual environment directly with `& .\venv\Scripts\python.exe -m unittest -v <tests>`.

The parent agent coordinates validation: subagents report required tests and do not duplicate runs unless explicitly assigned. Report selectors and elapsed time. Change a test only when its expectation is proven incorrect or requirements change, never to conceal a failure. Run the full suite at a separately agreed regression checkpoint or when targeted results show a wider need:

```powershell
python -m unittest discover -s tests -v
```

The reference schema is cached by SQL contents. Already validated databases use a lightweight schema/version query instead of full validation on ordinary data writes. Changes to the schema, version, schema file or database file identity trigger full validation. Legacy and incomplete database rejection tests remain necessary; they do not imply support for old schemas.

Environment: use the project virtual environment and a local SSD. Cloud-synced project folders can slow source and package reads; a local clone and local virtual environment avoid this overhead. `tempfile` tests use the system temporary directory: keep `TEMP`/`TMP` on a local disk. Do not disable security software; measure scanning overhead before any organization-approved scoped adjustments. Test classes modify the shared `settings.STORIES_DIR`, so do not parallelize them within one process; parallel runs require separate processes and storage directories.

Frontend timestamp and structure regressions can run separately with Node.js (only for testing, not application use):

```powershell
node --test tests\test_frontend.cjs tests\test_bible_frontend.cjs tests\test_simulation_frontend.cjs
```

Tests use temporary directories and fake models, not the user's stories or real model calls. They cover, among other things, information boundaries, mode differences, player actions, storage integrity, request replay, edit conflicts, memory retrieval, schema validation, background jobs, and path confinement. The test suite is limited and does not cover every usage scenario.

The UI has been tried during development at desktop and mobile widths, but comprehensive browser or user testing has not been done. Assessing prose quality and long-story recall requires separate experiments with real models.

## Current Limitations

Witness filtering prevents direct leakage of shared prose context. The narrator is still a language model and may produce an incorrect account of who witnessed an event or an inconsistent consequence. Schema validation does not prove that events are semantically correct. Decision points and paragraph pacing depend on the model and prompts.

Automatic reconciliation of prose edits, image generation, Realtime sessions, and a multi-process server job queue are not implemented. A snapshot retry branch is not a general branch-merging or historical-reconciliation feature. Illustration prompts can still be generated. These features should build on the committed event and state model rather than bypass it.