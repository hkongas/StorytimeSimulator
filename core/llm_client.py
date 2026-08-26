import json
import re
import httpx
from typing import List, Dict, Any, Optional
from config import settings

class LLMClient:
    """Asynkroninen LLM-asiakas, joka tukee xAI Grok-, Azure AI-, OpenAI- ja OpenRouter-rajapintoja."""

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_version: Optional[str] = None
    ):
        self.provider = (provider or settings.LLM_PROVIDER).lower()
        self.api_key = api_key
        self.base_url = base_url
        self.api_version = api_version or settings.AZURE_OPENAI_API_VERSION

        if not self.api_key:
            if self.provider == "xai":
                self.api_key = settings.XAI_API_KEY
                self.base_url = self.base_url or "https://api.x.ai/v1"
            elif self.provider == "azure":
                self.api_key = settings.AZURE_OPENAI_API_KEY
                self.base_url = self.base_url or settings.AZURE_OPENAI_ENDPOINT
            elif self.provider == "openai":
                self.api_key = settings.OPENAI_API_KEY
                self.base_url = self.base_url or "https://api.openai.com/v1"
            elif self.provider == "openrouter":
                self.api_key = settings.OPENROUTER_API_KEY
                self.base_url = self.base_url or "https://openrouter.ai/api/v1"
            elif self.provider == "custom":
                self.api_key = settings.CUSTOM_API_KEY
                self.base_url = self.base_url or settings.CUSTOM_API_BASE
            else:
                self.api_key = settings.XAI_API_KEY
                self.base_url = "https://api.x.ai/v1"

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
        role: str = "director"  # "director" tai "character"
    ) -> str:
        """Suorittaa chat completion -kutsun LLM:lle."""
        if not self.api_key:
            raise ValueError(
                f"API-avain puuttuu palveluntarjoajalle '{self.provider}'. "
                "Aseta API-avain .env-tiedostoon tai käyttöliittymän asetuksissa."
            )

        # Määritetään oletusmallit ja -parametrit roolin mukaan
        if role == "character":
            target_model = model or settings.CHARACTER_MODEL
            target_temp = temperature if temperature is not None else settings.CHARACTER_TEMPERATURE
            target_tokens = max_tokens if max_tokens is not None else settings.CHARACTER_MAX_TOKENS
            target_reasoning = reasoning_effort or settings.CHARACTER_REASONING_EFFORT
        else:
            target_model = model or settings.DIRECTOR_MODEL
            target_temp = temperature if temperature is not None else settings.DIRECTOR_TEMPERATURE
            target_tokens = max_tokens if max_tokens is not None else settings.DIRECTOR_MAX_TOKENS
            target_reasoning = reasoning_effort or settings.DIRECTOR_REASONING_EFFORT

        if not target_model:
            target_model = "grok-2-latest" if self.provider == "xai" else "gpt-4o"

        # Päätepisteen ja otsakkeiden rakennus
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
        }

        if self.provider == "azure":
            clean_base = (self.base_url or "").rstrip("/")
            if "openai.azure.com" in clean_base:
                endpoint = f"{clean_base}/openai/deployments/{target_model}/chat/completions?api-version={self.api_version}"
                headers["api-key"] = self.api_key
            else:
                endpoint = f"{clean_base}/chat/completions"
                headers["api-key"] = self.api_key
                headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
            headers["Authorization"] = f"Bearer {self.api_key}"

        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://storytimesimulator.local"
            headers["X-Title"] = "StorytimeSimulator"

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": target_temp,
        }

        if target_tokens:
            payload["max_tokens"] = target_tokens

        # Reasoning effort -tuki (jos valittu low, medium, high)
        if target_reasoning and target_reasoning.lower() in ["low", "medium", "high"]:
            payload["reasoning_effort"] = target_reasoning.lower()

        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            
            if response.status_code != 200:
                # Jos reasoning_effort aiheuttaa virheen perinteisellä mallilla, yritetään ilman sitä
                if "reasoning_effort" in payload and response.status_code in [400, 422]:
                    payload.pop("reasoning_effort", None)
                    response = await client.post(endpoint, headers=headers, json=payload)

            if response.status_code != 200:
                error_msg = f"LLM API Virhe ({response.status_code}): {response.text}"
                raise RuntimeError(error_msg)

            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def json_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        role: str = "director"
    ) -> Dict[str, Any]:
        """Kutsuu LLM:ää ja parsii vastauksen JSON-objektiksi."""
        raw_text = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            role=role,
            response_format={"type": "json_object"} if self.provider in ["openai", "azure", "openrouter"] else None
        )
        return self._extract_json(raw_text)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Poimii ja parsii JSON-sisällön tekstistä tai koodilohkosta."""
        text = text.strip()
        
        # 1. Suora JSON-yritys
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Markdown ```json ... ``` lohkon etsintä
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 3. Ensimmäisen { ja viimeisen } välinen sisältö
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Ei voitu jäsentää kelvollista JSON-vastausta:\n{text[:500]}...")
