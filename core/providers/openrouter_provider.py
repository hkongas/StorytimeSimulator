import json
import logging
import httpx
from typing import List, Dict, Any, Optional, AsyncIterator
from core.providers.base import LLMProvider

logger = logging.getLogger(__name__)

class OpenRouterProvider(LLMProvider):
    """OpenRouter API -palveluntarjoaja (tukee satoja avoimia ja kaupallisia malleja)."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        super().__init__(api_key=api_key, base_url=base_url or "https://openrouter.ai/api/v1")

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.85,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
        **kwargs
    ) -> str:
        if not self.api_key:
            raise ValueError("OpenRouter API-avain (OPENROUTER_API_KEY) puuttuu.")

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://storytimesimulator.local",
            "X-Title": "StorytimeSimulator"
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"OpenRouter API Virhe ({response.status_code}): {response.text}")
            return self._read_response(response.json(), model, response.elapsed.total_seconds())

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.85,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        timeout: float = 120.0,
        **kwargs
    ) -> AsyncIterator[str]:
        if not self.api_key:
            raise ValueError("OpenRouter API-avain (OPENROUTER_API_KEY) puuttuu.")

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://storytimesimulator.local",
            "X-Title": "StorytimeSimulator"
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(f"OpenRouter Streaming Virhe ({response.status_code}): {body.decode('utf-8', errors='ignore')}")

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue

class CustomProvider(LLMProvider):
    """Paikallinen tai räätälöity OpenAI-yhteensopiva palvelin (Ollama, vLLM, LM Studio)."""

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        super().__init__(api_key=api_key or "not_needed", base_url=base_url)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.85,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
        **kwargs
    ) -> str:
        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "not_needed":
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"Custom LLM API Virhe ({response.status_code}): {response.text}")
            return self._read_response(response.json(), model, response.elapsed.total_seconds())

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.85,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        timeout: float = 120.0,
        **kwargs
    ) -> AsyncIterator[str]:
        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "not_needed":
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(f"Custom LLM Streaming Virhe ({response.status_code}): {body.decode('utf-8', errors='ignore')}")

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue
