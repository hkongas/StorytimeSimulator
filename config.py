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
    
    # API-avaimet ja päätepisteet
    XAI_API_KEY: str = os.getenv("XAI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Azure AI / Azure OpenAI
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_API_VERSION: str = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
    AZURE_DEPLOYMENT_NAME: str = os.getenv("AZURE_DEPLOYMENT_NAME", "")

    # Mukautettu OpenAI-yhteensopiva API (Ollama / vLLM jne.)
    CUSTOM_API_BASE: str = os.getenv("CUSTOM_API_BASE", "")
    CUSTOM_API_KEY: str = os.getenv("CUSTOM_API_KEY", "")

    # LLM-asetukset (xai, azure, openai, openrouter, gemini, custom)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "xai")
    
    # Kertojan / Pääagentin hienosäädöt (Director & Novelist)
    DIRECTOR_MODEL: str = os.getenv("DIRECTOR_MODEL", "grok-4.6")
    DIRECTOR_MAX_TOKENS: int = int(os.getenv("DIRECTOR_MAX_TOKENS", "32000" if LLM_PROVIDER == "azure" else "3500"))
    DIRECTOR_TEMPERATURE: float = float(os.getenv("DIRECTOR_TEMPERATURE", "0.85"))
    DIRECTOR_REASONING_EFFORT: str = os.getenv("DIRECTOR_REASONING_EFFORT", "medium")

    # Hahmoagenttien hienosäädöt (Character Agents)
    CHARACTER_MODEL: str = os.getenv("CHARACTER_MODEL", "grok-4.3")
    CHARACTER_MAX_TOKENS: int = int(os.getenv("CHARACTER_MAX_TOKENS", "16000" if LLM_PROVIDER == "azure" else "1200"))
    CHARACTER_TEMPERATURE: float = float(os.getenv("CHARACTER_TEMPERATURE", "0.75"))
    CHARACTER_REASONING_EFFORT: str = os.getenv("CHARACTER_REASONING_EFFORT", "none")
    MAX_INPUT_TOKENS: int = int(os.getenv("MAX_INPUT_TOKENS", "64000"))

    # Palvelimen asetukset
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Pääsäännöt ja suojaukset
    STRICT_MINOR_SAFETY: bool = True

settings = Settings()

# Varmistetaan että tarinakansio on olemassa
settings.STORIES_DIR.mkdir(parents=True, exist_ok=True)
