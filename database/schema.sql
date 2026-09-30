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

