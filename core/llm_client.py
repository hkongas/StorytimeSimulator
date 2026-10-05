import logging
from typing import List, Dict, Any, Optional, AsyncIterator
from config import settings
from core.context_budget import context_budget
from core.providers import (
    LLMProvider,
    TruncatedResponseError,
    XAIProvider,
    AzureProvider,
    OpenAIProvider,
    GeminiProvider,
    OpenRouterProvider,
    CustomProvider
)
import database.db as db

logger = logging.getLogger(__name__)

class LLMClient:
    """Asynkroninen LLM-asiakasfasadi, joka hallitsee tarjoajainstanssit ja reitittää kutsut."""

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_version: Optional[str] = None,
        deployment_name: Optional[str] = None,
        story_id: Optional[str] = None
    ):
        self.provider_name = (provider or settings.LLM_PROVIDER).lower()
        self.api_key = api_key
        self.base_url = base_url
        self.api_version = api_version or settings.AZURE_OPENAI_API_VERSION
        self.deployment_name = deployment_name or settings.AZURE_DEPLOYMENT_NAME
        self.story_id = story_id
        self._provider_instance: Optional[LLMProvider] = None

    def _get_provider(self) -> LLMProvider:
        """Luo tai palauttaa konfiguroidun LLMProvider-instanssin."""
        if self._provider_instance:
            return self._provider_instance

        p_name = self.provider_name
        if p_name == "xai":
            key = self.api_key or settings.XAI_API_KEY
            url = self.base_url or "https://api.x.ai/v1"
            self._provider_instance = XAIProvider(api_key=key, base_url=url)
        elif p_name == "azure":
            key = self.api_key or settings.AZURE_OPENAI_API_KEY
            endpoint = self.base_url or settings.AZURE_OPENAI_ENDPOINT
            ver = self.api_version or settings.AZURE_OPENAI_API_VERSION
            dep = self.deployment_name or settings.AZURE_DEPLOYMENT_NAME
            self._provider_instance = AzureProvider(api_key=key, endpoint=endpoint, api_version=ver, deployment_name=dep)
        elif p_name == "openai":
            key = self.api_key or settings.OPENAI_API_KEY
            url = self.base_url or "https://api.openai.com/v1"
            self._provider_instance = OpenAIProvider(api_key=key, base_url=url)
        elif p_name == "gemini":
            self._provider_instance = GeminiProvider(api_key=self.api_key or settings.GEMINI_API_KEY, base_url=self.base_url)
        elif p_name == "openrouter":
            key = self.api_key or settings.OPENROUTER_API_KEY
            url = self.base_url or "https://openrouter.ai/api/v1"
            self._provider_instance = OpenRouterProvider(api_key=key, base_url=url)
        elif p_name == "custom":
            key = self.api_key or settings.CUSTOM_API_KEY
            url = self.base_url or settings.CUSTOM_API_BASE
            self._provider_instance = CustomProvider(base_url=url, api_key=key)
        else:
            key = self.api_key or settings.XAI_API_KEY
            self._provider_instance = XAIProvider(api_key=key)

        return self._provider_instance

    def _check_context(self, messages: List[Dict[str, str]]):
        if context_budget.calculate_messages_tokens(messages) > settings.MAX_INPUT_TOKENS:
            raise ValueError("Tarinan syöte ylittää asetetun kontekstibudjetin. Tiivistä maailman tietoja tai promptteja.")

    def _resolve_params(
        self,
        role: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None
    ) -> tuple[str, float, int, Optional[str]]:
        """Määrittää mallin, lämpötilan ja token-rajat roolin perusteella."""
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
            target_model = "grok-2-latest" if self.provider_name == "xai" else "gpt-4o"

        return target_model, target_temp, target_tokens, target_reasoning

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
        timeout: float = 120.0,
        role: str = "director",
        story_id: Optional[str] = None
    ) -> str:
        """Suorittaa chat completion -kutsun aktiiviselle providerille ja lokittaa käytön."""
        self._check_context(messages)
        provider = self._get_provider()
        provider.last_usage = {}
        target_model, target_temp, target_tokens, target_reasoning = self._resolve_params(
            role=role, model=model, temperature=temperature, max_tokens=max_tokens, reasoning_effort=reasoning_effort
        )
        sid = story_id or self.story_id
        try:
            content = await provider.chat_completion(
                messages=messages,
                model=target_model,
                temperature=target_temp,
                max_tokens=target_tokens,
                reasoning_effort=target_reasoning,
                response_format=response_format,
                timeout=timeout
            )
            if sid:
                u = getattr(provider, "last_usage", {})
                await db.log_api_call(
                    story_id=sid,
                    role=role,
                    model=u.get("model", target_model),
                    duration_seconds=u.get("duration_seconds", 0.0),
                    prompt_tokens=u.get("prompt_tokens", 0),
                    completion_tokens=u.get("completion_tokens", 0),
                    reasoning_tokens=u.get("reasoning_tokens", 0),
                    total_tokens=u.get("total_tokens", 0),
                    cost_usd=u.get("cost_usd", 0.0),
                    cached_tokens=u.get("cached_tokens", 0),
                    cost_known=u.get("cost_known", False),
                    status=u.get("status", "success"),
                    error_message="", prompt_data=messages, response_data=content
                )
            return content
        except Exception as e:
            if sid:
                u = getattr(provider, "last_usage", {})
                await db.log_api_call(
                    story_id=sid,
                    role=role,
                    model=u.get("model", target_model),
                    duration_seconds=u.get("duration_seconds", 0.0),
                    prompt_tokens=0,
                    completion_tokens=0,
                    reasoning_tokens=0,
                    total_tokens=0,
                    cost_usd=0.0,
                    status="error",
                    error_message=str(e)[:500], prompt_data=messages
                )
            raise

    async def json_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        timeout: float = 180.0,
        role: str = "director",
        json_schema: Optional[Dict[str, Any]] = None,
        story_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Kutsuu LLM:ää ja jäsentää vastauksen JSON-objektiksi automaattisella katkeamisen uusintayrityksellä."""
        self._check_context(messages)
        provider = self._get_provider()
        provider.last_usage = {}
        target_model, target_temp, target_tokens, target_reasoning = self._resolve_params(
            role=role, model=model, temperature=temperature, max_tokens=max_tokens, reasoning_effort=reasoning_effort
        )
        sid = story_id or self.story_id

        logger.info(
            f"LLM JSON-kutsu ({role}): provider={self.provider_name}, model={target_model}, "
            f"max_tokens={target_tokens}, temp={target_temp}, schema={'yes' if json_schema else 'no'}"
        )

        # Ensimmäinen yritys ja mahdollinen korotetun token-määrän uusintayritys
        attempts = 2
        current_max_tokens = target_tokens

        for attempt in range(1, attempts + 1):
            try:
                res = await provider.json_completion(
                    messages=messages,
                    model=target_model,
                    temperature=target_temp,
                    max_tokens=current_max_tokens,
                    reasoning_effort=target_reasoning,
                    timeout=timeout,
                    json_schema=json_schema
                )
                if sid:
                    u = getattr(provider, "last_usage", {})
                    await db.log_api_call(
                        story_id=sid,
                        role=role,
                        model=u.get("model", target_model),
                        duration_seconds=u.get("duration_seconds", 0.0),
                        prompt_tokens=u.get("prompt_tokens", 0),
                        completion_tokens=u.get("completion_tokens", 0),
                        reasoning_tokens=u.get("reasoning_tokens", 0),
                        total_tokens=u.get("total_tokens", 0),
                        cost_usd=u.get("cost_usd", 0.0),
                        cached_tokens=u.get("cached_tokens", 0),
                        cost_known=u.get("cost_known", False),
                        status=u.get("status", "success"),
                        error_message="", prompt_data={"messages": messages, "json_schema": json_schema},
                        response_data=res
                    )
                return res
            except TruncatedResponseError as tre:
                logger.warning(
                    f"LLM-vastaus katkesi kesken (yritys {attempt}/{attempts}, max_tokens={current_max_tokens}): {tre}"
                )
                if sid:
                    u = getattr(provider, "last_usage", {})
                    await db.log_api_call(
                        story_id=sid,
                        role=role,
                        model=u.get("model", target_model),
                        duration_seconds=u.get("duration_seconds", 0.0),
                        prompt_tokens=u.get("prompt_tokens", 0),
                        completion_tokens=u.get("completion_tokens", 0),
                        reasoning_tokens=u.get("reasoning_tokens", 0),
                        total_tokens=u.get("total_tokens", 0),
                        cost_usd=u.get("cost_usd", 0.0),
                        status="truncated",
                        cached_tokens=u.get("cached_tokens", 0),
                        cost_known=u.get("cost_known", False),
                        error_message=str(tre)[:500],
                        prompt_data={"messages": messages, "json_schema": json_schema},
                        response_data={"partial_text": tre.partial_text, "finish_reason": tre.finish_reason}
                    )
                if attempt < attempts:
                    # Korotetaan token-budjettia merkittävästi toiselle yritykselle
                    current_max_tokens = max(current_max_tokens * 2, 8000)
                    logger.info(f"Yritetään uudelleen korotetulla token-rajalla: {current_max_tokens}...")
                    continue
                
                raise RuntimeError(
                    f"Tekoälymallin ({target_model}) vastaus katkesi kahdesti liian pienen token-rajan vuoksi. "
                    f"Kokeile kasvattaa 'Ohjaajan max tokens' -asetusta asetuspaneelista."
                ) from tre
            except ValueError as ve:
                logger.error(f"JSON-parsintavirhe LLM-vastauksesta: {ve}")
                if sid:
                    usage = provider.last_usage
                    await db.log_api_call(sid, role, target_model, usage.get("duration_seconds", 0.0),
                        prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0), cached_tokens=usage.get("cached_tokens", 0),
                        status="error", error_message=str(ve)[:500],
                        prompt_data={"messages": messages, "json_schema": json_schema})
                if attempt < attempts:
                    logger.info("Yritetään uudelleen JSON-kutsulla...")
                    continue
                raise

            except Exception as error:
                if sid:
                    await db.log_api_call(sid, role, target_model, provider.last_usage.get("duration_seconds", 0.0),
                                          status="error", error_message=str(error)[:500],
                                          prompt_data={"messages": messages, "json_schema": json_schema})
                raise

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        timeout: float = 120.0,
        role: str = "director"
    ) -> AsyncIterator[str]:
        """Striimaa vastaustokenit generaattorina."""
        self._check_context(messages)
        provider = self._get_provider()
        target_model, target_temp, target_tokens, target_reasoning = self._resolve_params(
            role=role, model=model, temperature=temperature, max_tokens=max_tokens, reasoning_effort=reasoning_effort
        )
        async for token in provider.stream_completion(
            messages=messages,
            model=target_model,
            temperature=target_temp,
            max_tokens=target_tokens,
            reasoning_effort=target_reasoning,
            timeout=timeout
        ):
            yield token
