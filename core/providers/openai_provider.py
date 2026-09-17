import json
import logging
import httpx
from typing import List, Dict, Any, Optional, AsyncIterator
from core.providers.base import LLMProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(LLMProvider):
    """OpenAI -palveluntarjoaja (GPT-4o, o1, o3-mini jne.)."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        super().__init__(api_key=api_key, base_url=base_url or "https://api.openai.com/v1")

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
            raise ValueError("OpenAI API-avain (OPENAI_API_KEY) puuttuu.")

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        is_reasoning = model.startswith("o1") or model.startswith("o3") or model.startswith("gpt-5")
        token_param = "max_completion_tokens" if is_reasoning else "max_tokens"
        target_temp = 1.0 if is_reasoning else temperature

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": target_temp
        }

        if max_tokens:
            payload[token_param] = max_tokens

        if is_reasoning and reasoning_effort and reasoning_effort.lower() in ["low", "medium", "high"]:
            payload["reasoning_effort"] = reasoning_effort.lower()

        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI API Virhe ({response.status_code}): {response.text}")
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
            raise ValueError("OpenAI API-avain (OPENAI_API_KEY) puuttuu.")

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        is_reasoning = model.startswith("o1") or model.startswith("o3") or model.startswith("gpt-5")
        token_param = "max_completion_tokens" if is_reasoning else "max_tokens"
        target_temp = 1.0 if is_reasoning else temperature

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": target_temp,
            "stream": True
        }

        if max_tokens:
            payload[token_param] = max_tokens

        if is_reasoning and reasoning_effort and reasoning_effort.lower() in ["low", "medium", "high"]:
            payload["reasoning_effort"] = reasoning_effort.lower()

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(f"OpenAI Streaming Virhe ({response.status_code}): {body.decode('utf-8', errors='ignore')}")

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
