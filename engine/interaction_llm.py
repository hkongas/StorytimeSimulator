import json

from config import settings


class InteractionTokenLimit(ValueError):
    pass


class InteractionLLM:
    """Reserve estimated input and maximum output before candidate-phase calls."""

    def __init__(self, llm, budget):
        self.llm = llm
        self.budget = budget

    async def json_completion(self, *args, **kwargs):
        messages = kwargs.get("messages", args[0] if args else [])
        schema_text = json.dumps(kwargs.get("json_schema", {}), ensure_ascii=False)
        input_tokens = (len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + len(schema_text.encode("utf-8")) + 2) // 3
        available = self.budget.token_limit - self.budget.tokens - input_tokens
        if available <= 0:
            self.budget.stop_reason = "token_budget"
            raise InteractionTokenLimit("Interaction token budget exhausted before model call")
        role = kwargs.get("role", "character")
        requested = kwargs.get("max_tokens", settings.CHARACTER_MAX_TOKENS if role == "character" else settings.SITUATION_MAX_TOKENS)
        kwargs["max_tokens"] = min(requested, available, 2048 if role == "character" else settings.SITUATION_MAX_TOKENS)
        # This is a conservative estimate, not provider-billed usage. Reserve before awaiting.
        self.budget.tokens += input_tokens + kwargs["max_tokens"]
        return await self.llm.json_completion(*args, **kwargs)
