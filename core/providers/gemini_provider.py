from core.providers.openai_provider import OpenAIProvider


class GeminiProvider(OpenAIProvider):
    """Gemini Developer API through Google's OpenAI-compatible endpoint."""

    def __init__(self, api_key: str, base_url: str | None = None):
        super().__init__(api_key, base_url or "https://generativelanguage.googleapis.com/v1beta/openai")

    def _build_payload(self, messages, model, temperature, max_tokens, reasoning_effort):
        if not self.api_key:
            raise ValueError("Google AI Studio API-avain (GEMINI_API_KEY) puuttuu.")
        payload = {"model": model, "messages": messages, "temperature": temperature}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if reasoning_effort and reasoning_effort.lower() in {"none", "minimal", "low", "medium", "high"}:
            effort = reasoning_effort.lower()
            if effort == "none" and (not model.startswith("gemini-2.5-") or model.startswith("gemini-2.5-pro")):
                raise ValueError("Ajattelua ei voi poistaa kaytosta talle Gemini-mallille. Valitse low, medium tai high.")
            payload["reasoning_effort"] = effort
        return payload