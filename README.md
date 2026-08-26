# 📜 StorytimeSimulator (Tarinamoottori)

> **Autonomous Multi-Agent AI Roleplaying Simulator & Literary Novel Generator**  
> *Where independent minds, sensory perception, and narrative direction collide to create living literature.*

---

## 🌟 Overview & Core Philosophy

**StorytimeSimulator** (known in Finnish as *Tarinamoottori*) is an advanced multi-agent narrative simulation engine. Unlike conventional text-adventure bots or single-prompt story generators, StorytimeSimulator treats every story as a **living theatre**: an orchestrated simulation where individual characters possess private consciousness, sensory limitations, and emotional memory, guided by an autonomous Master Director Agent (Novelist & Game Master).

---

## ⚡ What Makes StorytimeSimulator Unique?

Most AI storytelling tools (such as AI Dungeon, NovelAI, or SillyTavern) rely on a single LLM prompt predicting the next tokens for all characters at once, leading to hive-mind behavior, broken context, and lack of true dramatic tension. 

StorytimeSimulator introduces an entirely new architecture:

```
                      ┌────────────────────────────────────────┐
                      │    Master Director Agent (Novelist)    │
                      │  - Shared World Lore & Rules           │
                      │  - Secret Overarching Plot & Pivoting  │
                      │  - Condensed Chronicle (Context Keeper)│
                      │  - Rich Literary Prose Synthesizer     │
                      │  - Cinematic Image Prompt Generator    │
                      └──────────────────┬─────────────────────┘
                                         │
                 Perceptual Filtering    │    Sensory Input
                 (Sight, Sound, Lore)    │    (No Telepathy)
                                         ▼
         ┌───────────────────────────────┴───────────────────────────────┐
         │                                                               │
         ▼                                                               ▼
┌─────────────────────────────────┐             ┌─────────────────────────────────┐
│     Character Agent: Alice      │             │      Character Agent: Bob       │
│ - Personality, Age, Bio         │             │ - Personality, Age, Bio         │
│ - Physical & Mental State       │             │ - Physical & Mental State       │
│ - Secret Motive & Hidden Trauma │             │ - Secret Motive & Hidden Trauma │
│ - Private Memory Stream         │             │ - Private Memory Stream         │
│ - Secret Internal Monologue     │             │ - Secret Internal Monologue     │
│ - Public Speech & Physical Action│             │ - Public Speech & Physical Action│
└─────────────────────────────────┘             └─────────────────────────────────┘
```

### 1. 🧠 True Sensory Isolation (No Telepathy or Omniscience)
Characters do **not** know what other characters are secretly thinking, nor do they know the Director's hidden master plot. The Director Agent acts as a **Perceptual Filter**, describing to each character only what their eyes, ears, and previous knowledge allow them to perceive.

### 2. 💭 Private Minds & Episodic Memory Stream
Each character maintains an isolated state:
* **Physical & Emotional Condition:** Fatigue, injuries, fear, excitement, suspicion.
* **Secret Motive & Drive:** Hidden goals kept from companions and enemies.
* **Internal Monologue:** Before taking any action, characters silently reflect in secret.
* **Memory Stream:** Personal history of significant past moments that influence future choices.

### 3. 🎭 Adaptive Director Agent (Novelist & Master Storyteller)
The Director Agent coordinates the simulation:
* **Dynamic Plot Pivoting:** If characters make unexpected decisions that derail the original plot, the Director organically adapts the story, creates dramatic complications, or steers towards new milestones.
* **Kaunokirjallinen Proosa (Literary Prose):** Instead of raw chat logs, the Director synthesizes all character actions, speech, gestures, and world reactions into immersive, book-quality chapters.
* **Context Preservation (Condensed Chronicle):** High-signal event summaries prevent long stories (50,000+ words) from overflowing context limits.
* **Visual Scene Prompts:** Every scene turn automatically generates an artistic text-to-image prompt (Midjourney/Flux/DALL-E style).

### 4. 🎮 Triple User Modes
* 📖 **Reader Mode:** Sit back and read an unfolding novel. Optionally provide creative nudges or plot twists whenever you wish.
* ⚔️ **Player Mode:** Take control of any character. Enter raw actions or dialogue—the engine adapts them to fit the scene and responds in character.
* 🎭 **Director Mode:** Intervene behind the scenes with private directorial instructions (e.g. *"Introduce a mysterious stranger carrying a forged letter"*).

### 5. 📦 Portable Character Cards (Selective Export & Import)
Export characters as portable JSON cards to use across different stories and worlds. Choose exactly what to transfer:
* ✅ Base Persona & Profile (Name, age, appearance, personality, bio)
* ✅ Current Physical/Mental State & Secret Motive
* ✅ Episodic Memory Stream (Memories formed during past adventures)

### 6. 🔒 Ethical Creative Freedom & Minor Safety
StorytimeSimulator supports uncensored, mature, psychologically intense, dark fantasy, cyberpunk, or romance storytelling without arbitrary puritanical constraints. However, it enforces a **hardcoded zero-tolerance safety directive**: Underage characters (< 18) are strictly prohibited from explicit sexual content or gratuitous extreme violence.

### 7. 📁 Local-First, Private & File-Centric
* **SQLite Database (`story.db`):** Complete state, character minds, memories, and turns stored locally per story.
* **Live Text Synchronization:** The novel is continuously streamed and written to `story.txt` and `story.md` in real-time. Open and read your story in any text editor at any time.

---

## 🚀 Quickstart & Installation

### Prerequisites
* **Python 3.10+** (Python 3.11, 3.12, 3.13, 3.14 supported)
* **Git**
* An API key for **xAI Grok** (recommended for creative freedom), **OpenAI**, or **OpenRouter**.

### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/hkongas/StorytimeSimulator.git
   cd StorytimeSimulator
   ```

2. **Create and activate a virtual environment:**
   * **Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   * **Linux / macOS:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API keys:**
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your API key:
   ```env
   # xAI Grok (Recommended)
   XAI_API_KEY=xai-your-api-key-here
   LLM_PROVIDER=xai
   DIRECTOR_MODEL=grok-2-latest
   CHARACTER_MODEL=grok-2-latest
   ```
   *(Note: You can also enter and update API keys directly inside the Web UI Settings modal at any time).*

5. **Start the application:**
   ```bash
   python main.py
   ```

6. **Open in browser:**
   Navigate to **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🌐 Multi-Language Support (i18n)

StorytimeSimulator comes with built-in bilingual UI support:
* **Suomi (FI)**
* **English (EN)**

Switch languages on the fly using the **🌐 FI / EN** toggle button in the top header. Your preference is remembered automatically.

---

## 🏗️ Project Architecture

```text
StorytimeSimulator/
├── config.py                 # Environment configuration & model settings
├── main.py                   # Server launcher (FastAPI & Uvicorn)
├── requirements.txt          # Python dependencies
├── .env.example              # Template for API keys
├── .gitignore                # Protects user stories, keys, and databases
│
├── core/
│   ├── llm_client.py         # Async multi-provider LLM client (xAI, OpenAI, OpenRouter)
│   ├── safety.py             # Content guidelines & minor protection rules
│   └── types.py              # Pydantic data schemas
│
├── database/
│   ├── db.py                 # Async SQLite database layer & memory manager
│   └── schema.sql            # Relational database schema
│
├── engine/
│   ├── character_agent.py    # Character Agent (private mind, senses, actions, memories)
│   ├── director_agent.py     # Director Agent (world building, plot, sensory filter, prose)
│   ├── chronicle_manager.py  # Event summarization & context window manager
│   └── story_engine.py       # Simulation loop & live file stream coordinator
│
├── web/
│   ├── api.py                # FastAPI REST endpoints & character export/import
│   └── static/               # Responsive Web UI
│       ├── index.html        # Book reader view, Mind Inspector & modals
│       ├── i18n.js           # Multi-language dictionary (FI / EN)
│       ├── app.js            # UI logic, state management & live rendering
│       └── style.css         # Dark obsidian theme & book typography
│
├── tests/                    # Automated test suites
│   ├── test_engine.py        # Core simulation, memory, and prose tests
│   └── test_api.py           # Web API & character import/export tests
│
└── stories/                  # User stories (Excluded from git for privacy)
    └── [story_name]/
        ├── story.db          # Story SQLite database
        ├── story.txt         # Plain text book export
        └── story.md          # Markdown formatted book export
```

---

## 🧪 Running Automated Tests

Run the engine and API test suites to verify that the environment and agents are operating correctly:

```bash
python tests/test_engine.py
python tests/test_api.py
```

---

<br/>

---

# 🇫🇮 Suomenkielinen Kuvaus (Tarinamoottori)

**Tarinamoottori** on tekoälypohjainen roolipelisimulaattori ja kaunokirjallinen moniagenttitarinankirjoittaja.

### Miksi Tarinamoottori on erilainen kuin muut?
1. **Ei telepatiaa:** Hahmot eivät tiedä toistensa salaisia ajatuksia tai Pääagentin salaista juonta. Pääagentti suodattaa kullekin hahmolle vain sen, mitä hahmo aistii tilanteessa.
2. **Yksityinen mieli:** Jokaisella hahmolla on salainen sisäinen monologi, omat motiivit, fyysinen/henkinen vointi ja oma muistivirta.
3. **Pääagentti (Ohjaaja & Kirjailija):** Ohjaa tarinaa, sopeuttaa juonta hahmojen tekojen mukaan, tiivistää tapahtumia kronikaksi ja kirjoittaa kaunokirjallista, kirjamaista suomenkielistä proosaa.
4. **Kolme käyttäjätilaa:** Lukijatila (automaattinen tarina + toiveet), Pelaajatila (ohjaa yhtä hahmoa) ja Ohjaajatila (salaiset juonikomennot).
5. **Hahmojen vienti ja tuonti:** Voit siirtää suosikkihahmosi tarinasta toiseen valitsemalla, siirretäänkö persoona, nykytila vai koko muistihistoria.
6. **Täysi paikallisuus & tietosuoja:** Kaikki tarinat tallentuvat omalle koneellesi SQLite-tietokantoina ja reaaliaikaisina `.txt`/`.md` -tekstitiedostoina.

### Pika-aloitus
```bash
git clone https://github.com/hkongas/StorytimeSimulator.git
cd StorytimeSimulator
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Avaa selain osoitteessa: **http://127.0.0.1:8000**

---

## 📄 License

MIT License. Developed for open creative exploration and living literature simulation.
