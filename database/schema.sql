-- Tarinaprojektin perustiedot ja maailma
CREATE TABLE IF NOT EXISTS story_revision (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    revision INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO story_revision (id, revision) VALUES (1, 0);

CREATE TABLE IF NOT EXISTS story_runtime (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turn_receipts (
    request_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    response_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS turn_snapshots (
    turn_id INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secret_truths (
    id TEXT PRIMARY KEY,
    fact TEXT NOT NULL,
    discoverable_via TEXT NOT NULL DEFAULT '',
    reveal_state TEXT NOT NULL DEFAULT 'hidden' CHECK (reveal_state IN ('hidden', 'hinted', 'revealed')),
    revealed_at_turn INTEGER,
    related_location_id TEXT
);

CREATE TABLE IF NOT EXISTS clocks (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    remaining_beats INTEGER NOT NULL CHECK (remaining_beats >= 0),
    on_expire_effect TEXT NOT NULL DEFAULT '',
    visible BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS offscreen_agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    goal TEXT NOT NULL,
    progress TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    next_move TEXT NOT NULL DEFAULT '',
    visible_to TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS locations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    connections TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    holder_character_id TEXT,
    location_id TEXT,
    state TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS relationships (
    character_a TEXT NOT NULL,
    character_b TEXT NOT NULL,
    attitude TEXT NOT NULL DEFAULT '',
    trust REAL NOT NULL DEFAULT 0,
    summary TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (character_a, character_b)
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    turn_id INTEGER,
    description TEXT NOT NULL,
    derived_from TEXT NOT NULL,
    actor_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_witnesses (
    event_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    modality TEXT NOT NULL DEFAULT 'saw',
    perceived_text TEXT,
    PRIMARY KEY (event_id, character_id),
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS player_view_artifacts (
    turn_id INTEGER NOT NULL,
    character_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'view_pending',
    view_json TEXT,
    error_message TEXT NOT NULL DEFAULT '',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (turn_id, character_id)
);

CREATE TABLE IF NOT EXISTS prose_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER NOT NULL,
    old_prose TEXT NOT NULL,
    new_prose TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS character_observations (
    character_id TEXT PRIMARY KEY,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_meta (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    genre TEXT DEFAULT 'Seikkailu',
    world_lore TEXT DEFAULT '',
    director_plot_arc TEXT DEFAULT '',
    director_notes TEXT DEFAULT '',
    tone_profile TEXT DEFAULT 'default',
    custom_tone_override TEXT DEFAULT '',
    language TEXT DEFAULT 'fi',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Tiivistetty tapahtumahistoria (Chronicle)
CREATE TABLE IF NOT EXISTS chronicle_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_index INTEGER DEFAULT 1,
    scene_index INTEGER DEFAULT 1,
    summary TEXT NOT NULL,
    world_updates TEXT DEFAULT '',
    repetition_flag BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Hahmot ja niiden tilat
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER DEFAULT 25,
    gender TEXT,
    appearance TEXT DEFAULT '',
    personality TEXT DEFAULT '',
    speech_style TEXT DEFAULT '',
    character_values TEXT DEFAULT '',
    current_goal TEXT DEFAULT '',
    fears TEXT DEFAULT '',
    skills TEXT DEFAULT '',
    limitations TEXT DEFAULT '',
    is_player_controlled BOOLEAN DEFAULT 0,
    physical_state TEXT DEFAULT 'Terve ja hyväkuntoinen',
    mental_state TEXT DEFAULT 'Rauhallinen ja tarkkaavainen',
    secret_motive TEXT DEFAULT '',
    public_bio TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    tier TEXT DEFAULT 'major',
    known_locations TEXT DEFAULT '[]',
    last_active_turn INTEGER,
    represents_group TEXT,
    group_size_hint INTEGER,
    location_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Hahmojen yksityinen muistivirta (Memory Stream)
CREATE TABLE IF NOT EXISTS character_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL,
    scene_index INTEGER DEFAULT 0,
    memory_type TEXT DEFAULT 'observation',
    content TEXT NOT NULL,
    importance_score REAL DEFAULT 1.0,
    source_event_id TEXT,
    last_accessed DATETIME,
    created_at_turn INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(character_id) REFERENCES characters(id) ON DELETE CASCADE
);

-- Kohtaukset ja luvut
CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_number INTEGER DEFAULT 1,
    location TEXT NOT NULL,
    scene_goal TEXT DEFAULT '',
    active_character_ids TEXT DEFAULT '[]', -- JSON-lista hahmojen ID:istä
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Yksittäiset tarinavuorot ja proosakappaleet
CREATE TABLE IF NOT EXISTS scene_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id INTEGER NOT NULL,
    turn_index INTEGER NOT NULL,
    acting_character_id TEXT,
    perceived_context TEXT DEFAULT '',
    internal_monologue TEXT DEFAULT '',
    character_action TEXT DEFAULT '',
    director_prose TEXT NOT NULL,
    choices TEXT DEFAULT '[]',
    image_prompt TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(scene_id) REFERENCES scenes(id) ON DELETE CASCADE
);

-- Rajapintakutsut, token-kulutus ja suoritusajat (Debug & Profilointi)
CREATE TABLE IF NOT EXISTS api_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT,
    role TEXT,
    model TEXT,
    duration_seconds REAL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    cached_tokens INTEGER DEFAULT 0,
    cost_known BOOLEAN DEFAULT 0,
    status TEXT DEFAULT 'success',
    error_message TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
