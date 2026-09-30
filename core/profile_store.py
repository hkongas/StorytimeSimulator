import json

from config import settings

KEY_FIELDS = {"xai_api_key", "azure_openai_api_key", "openai_api_key", "openrouter_api_key", "gemini_api_key"}


def load_profiles() -> dict:
    path = settings.BASE_DIR / ".provider-profiles.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_profile_keys(profiles: list[dict]):
    stored = load_profiles()
    for profile in profiles:
        identifier = profile.get("id")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 100:
            raise ValueError("Virheellinen profiilitunniste.")
        keys = {name: value for name, value in profile.items() if name in KEY_FIELDS and isinstance(value, str) and value}
        stored.setdefault(identifier, {}).update(keys)
    path = settings.BASE_DIR / ".provider-profiles.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)