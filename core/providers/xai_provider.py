import json
import logging
import time
import httpx
from typing import List, Dict, Any, Optional, AsyncIterator
from core.providers.base import LLMProvider, TruncatedResponseError

logger = logging.getLogger(__name__)

class XAIProvider(LLMProvider):
    """xAI (Grok) -palveluntarjoaja."""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        super().__init__(api_key=api_key, base_url=base_url or "https://api.x.ai/v1")

    def supports_prompt_caching(self) -> bool:
        return True

    def supports_structured_output(self) -> bool:
        return True

    def get_pricing_info(self, model: str) -> Dict[str, float]:
        # Grok-hinnoittelu (alle 200k konteksti)
        return {
            "input_per_million": 2.00,
            "cached_input_per_million": 0.50,
            "output_per_million": 10.00,
            "context_tier_threshold": 200_000
        }

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.85,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout: float = 180.0,
        **kwargs
    ) -> str:
        if not self.api_key:
            raise ValueError("xAI API-avain (XAI_API_KEY) puuttuu.")

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if reasoning_effort and reasoning_effort.lower() in ["low", "medium", "high"]:
            payload["reasoning_effort"] = reasoning_effort.lower()

        if response_format:
            payload["response_format"] = response_format

        start_time = time.perf_counter()
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            
            if response.status_code in (400, 422) and "reasoning_effort" in payload:
                # Kokeillaan ilman reasoning_effortia jos malli ei tue sitä
                payload.pop("reasoning_effort", None)
                response = await client.post(endpoint, headers=headers, json=payload)

            # Jos json_schema hylättiin, kokeillaan json_object-muodolla
            if response.status_code in (400, 422) and response_format and response_format.get("type") == "json_schema":
                logger.warning("xAI hylkäsi json_schema-muodon, yritetään type: json_object...")
                payload["response_format"] = {"type": "json_object"}
                response = await client.post(endpoint, headers=headers, json=payload)

            duration = time.perf_counter() - start_time

            if response.status_code != 200:
                self.last_usage = {
                    "duration_seconds": round(duration, 3),
                    "model": model,
                    "status": "error"
                }
                raise RuntimeError(f"xAI API Virhe ({response.status_code}): {response.text}")

            return self._read_response(response.json(), model, duration)

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
            raise ValueError("xAI API-avain (XAI_API_KEY) puuttuu.")

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if reasoning_effort and reasoning_effort.lower() in ["low", "medium", "high"]:
            payload["reasoning_effort"] = reasoning_effort.lower()

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(f"xAI Streaming Virhe ({response.status_code}): {body.decode('utf-8', errors='ignore')}")

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
