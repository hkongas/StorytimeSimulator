import os
from pathlib import Path
from dotenv import load_dotenv

# Lataa .env tiedosto jos olemassa
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    # Perushakemistot
    BASE_DIR: Path = BASE_DIR
    STORIES_DIR: Path = BASE_DIR / "stories"
    
    # API-avaimet
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    CUSTOM_API_BASE: str = os.getenv("CUSTOM_API_BASE", "")
    CUSTOM_API_KEY: str = os.getenv("CUSTOM_API_KEY", "")

    # LLM-asetukset
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "xai")
    DIRECTOR_MODEL: str = os.getenv("DIRECTOR_MODEL", "grok-2-latest")
    CHARACTER_MODEL: str = os.getenv("CHARACTER_MODEL", "grok-2-latest")

    # Palvelimen asetukset
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Pääsäännöt ja suojaukset
    STRICT_MINOR_SAFETY: bool = True

settings = Settings()

# Varmistetaan että tarinakansio on olemassa
settings.STORIES_DIR.mkdir(parents=True, exist_ok=True)
