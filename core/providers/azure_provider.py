import json
import logging
import httpx
from typing import List, Dict, Any, Optional, AsyncIterator
from core.providers.base import LLMProvider

logger = logging.getLogger(__name__)

class AzureProvider(LLMProvider):
    """Azure AI Foundry ja Azure OpenAI -palveluntarjoaja."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        api_version: str = "2024-10-21",
        deployment_name: Optional[str] = None
    ):
        super().__init__(api_key=api_key, base_url=endpoint, api_version=api_version)
        self.deployment_name = deployment_name

    def _resolve_endpoint_and_headers(self, model: str) -> tuple[str, Dict[str, str], bool]:
        clean_base = (self.base_url or "").rstrip("/")
        azure_foundry_v1 = clean_base.lower().endswith("/openai/v1")

        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key or ""
        }

        if azure_foundry_v1:
            endpoint = f"{clean_base}/chat/completions"
        else:
            deployment = self.deployment_name or model
            endpoint = f"{clean_base}/openai/deployments/{deployment}/chat/completions?api-version={self.api_version}"

        return endpoint, headers, azure_foundry_v1

    def _build_payload(self, messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: Optional[int], reasoning_effort: Optional[str], azure_foundry_v1: bool, stream: bool = False) -> Dict[str, Any]:
        norm_model = model.lower()
        is_gpt5 = norm_model.startswith("gpt-5") or norm_model.startswith("o1") or norm_model.startswith("o3")
        
        target_temp = 1.0 if is_gpt5 else temperature
        token_param = "max_completion_tokens" if is_gpt5 else "max_tokens"

        payload: Dict[str, Any] = {
            "messages": messages,
            "temperature": target_temp,
        }

        if stream:
            payload["stream"] = True

        if azure_foundry_v1:
            payload["model"] = model

        if max_tokens:
            payload[token_param] = max_tokens

        if reasoning_effort and is_gpt5 and reasoning_effort.lower() in ["low", "medium", "high"]:
            payload["reasoning_effort"] = reasoning_effort.lower()

        return payload

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
        if not self.api_key or not self.base_url:
            raise ValueError("Azure API-avain tai Endpoint puuttuu.")

        endpoint, headers, is_foundry = self._resolve_endpoint_and_headers(model)
        payload = self._build_payload(messages, model, temperature, max_tokens, reasoning_effort, is_foundry, stream=False)

        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)

            if response.status_code != 200 and "reasoning_effort" in payload:
                payload.pop("reasoning_effort", None)
                response = await client.post(endpoint, headers=headers, json=payload)

            if response.status_code != 200:
                raise RuntimeError(f"Azure API Virhe ({response.status_code}): {response.text}")

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
        if not self.api_key or not self.base_url:
            raise ValueError("Azure API-avain tai Endpoint puuttuu.")

        endpoint, headers, is_foundry = self._resolve_endpoint_and_headers(model)
        payload = self._build_payload(messages, model, temperature, max_tokens, reasoning_effort, is_foundry, stream=True)

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(f"Azure Streaming Virhe ({response.status_code}): {body.decode('utf-8', errors='ignore')}")

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
