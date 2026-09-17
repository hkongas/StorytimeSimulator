import json
import logging
import re
from contextvars import ContextVar
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator

logger = logging.getLogger(__name__)

class TruncatedResponseError(RuntimeError):
    """Heitetään kun LLM:n vastaus katkesi kesken (finish_reason == 'length')."""
    def __init__(self, message: str, partial_text: str = "", finish_reason: str = "length"):
        super().__init__(message)
        self.partial_text = partial_text
        self.finish_reason = finish_reason

class LLMProvider(ABC):
    """Abstrakti pohjaluokka LLM-palveluntarjoajille."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_version: Optional[str] = None
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.api_version = api_version
        self._usage: ContextVar[Dict[str, Any]] = ContextVar("llm_usage", default={})

    @property
    def last_usage(self) -> Dict[str, Any]:
        return self._usage.get()

    @last_usage.setter
    def last_usage(self, value: Dict[str, Any]):
        self._usage.set(value)

    def _read_response(self, data: Dict[str, Any], model: str, duration: float) -> str:
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        completion_details = usage.get("completion_tokens_details") or {}
        cost = usage.get("cost")
        choice = data["choices"][0]
        self.last_usage = {
            "model": data.get("model", model), "duration_seconds": duration,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "cached_tokens": details.get("cached_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "reasoning_tokens": completion_details.get("reasoning_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "cost_usd": cost if isinstance(cost, (int, float)) else 0.0,
            "cost_known": isinstance(cost, (int, float)), "status": "success"
        }
        content = choice.get("message", {}).get("content")
        if choice.get("finish_reason") == "length":
            raise TruncatedResponseError("Mallin vastaus katkesi tokenrajaan.", partial_text=content or "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Malli ei palauttanut tekstivastausta.")
        return content

    @abstractmethod
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
        """Suorittaa ei-striimaavan chat completion -kutsun ja palauttaa vastauksen merkkijonona."""
        pass

    @abstractmethod
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
        """Striimaa vastaustokenit asynkronisena generaattorina."""
        pass

    async def json_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.85,
        max_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        timeout: float = 120.0,
        json_schema: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Kutsuu mallia ja jäsentää vastauksen vikasietoisesti JSON-objektiksi."""
        if json_schema and self.supports_structured_output():
            resp_fmt = json_schema
        elif self.supports_structured_output():
            resp_fmt = {"type": "json_object"}
        else:
            resp_fmt = None

        raw_text = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            response_format=resp_fmt,
            timeout=timeout,
            **kwargs
        )
        return self._extract_json(raw_text)

    def supports_prompt_caching(self) -> bool:
        """Kertoo tukeeko rajapinta automaattista prompt cachingia."""
        return False

    def supports_structured_output(self) -> bool:
        """Kertoo tukeeko rajapinta response_format: type: json_object / json_schema -ohjausta."""
        return True

    def get_pricing_info(self, model: str) -> Dict[str, float]:
        """Palauttaa hintatiedot per 1M tokenia (input, cached_input, output)."""
        return {"input_per_million": 2.00, "cached_input_per_million": 0.50, "output_per_million": 10.00}

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Poimii ja parsii JSON-sisällön tekstistä tai markdown-koodilohkosta."""
        text = text.strip()
        
        # 1. Suora JSON-yritys
        try:
            result = json.loads(text)
            if not isinstance(result, dict):
                raise ValueError("Mallin vastauksen on oltava JSON-objekti.")
            return result
        except json.JSONDecodeError:
            pass

        # 2. Markdown ```json ... ``` lohkon etsintä
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                result = json.loads(match.group(1).strip())
                if not isinstance(result, dict):
                    raise ValueError("Mallin vastauksen on oltava JSON-objekti.")
                return result
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

        raise ValueError("Mallin vastaus ei ole kokonainen JSON-objekti.")

    def _repair_truncated_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Yrittää sulkea katkenneen JSON-rakenteen parsimiskelpoiseksi."""
        start = text.find("{")
        if start == -1:
            return None
        candidate = text[start:].strip()

        # Jos merkkijono on avoinna (pariton määrä lainausmerkkejä ilman escapea)
        # Suljetaan avoin merkkijono
        in_string = False
        escape = False
        open_brackets = []  # list of '{' or '['

        for char in candidate:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char in ("{", "["):
                    open_brackets.append(char)
                elif char == "}":
                    if open_brackets and open_brackets[-1] == "{":
                        open_brackets.pop()
                elif char == "]":
                    if open_brackets and open_brackets[-1] == "[":
                        open_brackets.pop()

        # Korjataan loppu
        fixed = candidate
        if in_string:
            fixed += '"'

        # Suljetaan sulut päinvastaisessa järjestyksessä
        for b in reversed(open_brackets):
            # Jos ennen sulkua on pilkku tai kaksoispiste, poistetaan tai paikataan
            fixed = fixed.rstrip()
            if fixed.endswith(":"):
                fixed += '""'
            elif fixed.endswith(","):
                fixed = fixed[:-1]
            if b == "{":
                fixed += "}"
            elif b == "[":
                fixed += "]"

        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            # Yritetään vielä poistaa viimeinen keskeneräinen kenttä
            # Esim: {"a": 1, "b": "katkennut -> {"a": 1}
            last_comma = candidate.rfind(",")
            if last_comma != -1:
                sub_candidate = candidate[:last_comma].strip()
                # Lasketaan sulut uudestaan
                ob = []
                ins = False
                esc = False
                for c in sub_candidate:
                    if esc:
                        esc = False
                        continue
                    if c == "\\":
                        esc = True
                        continue
                    if c == '"':
                        ins = not ins
                        continue
                    if not ins:
                        if c in ("{", "["):
                            ob.append(c)
                        elif c == "}":
                            if ob and ob[-1] == "{":
                                ob.pop()
                        elif c == "]":
                            if ob and ob[-1] == "[":
                                ob.pop()
                if not ins:
                    fixed_sub = sub_candidate
                    for b in reversed(ob):
                        fixed_sub = fixed_sub.rstrip().rstrip(",")
                        fixed_sub += "}" if b == "{" else "]"
                    try:
                        return json.loads(fixed_sub)
                    except json.JSONDecodeError:
                        pass
            return None
