from typing import List, Dict, Any, Optional

class ContextBudgetManager:
    """Valvoo ja optimoi LLM-kontekstin pituutta ja kustannuksia."""

    MAX_SAFE_CONTEXT_TOKENS = 190_000  # Pidetään reilu marginaali xAI:n 200k kalliimpaan porraskynnykseen

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Karkea ja nopea token-arvio (n. 4 merkkiä = 1 token)."""
        if not text:
            return 0
        return max(1, (len(text) + 2) // 3)

    @classmethod
    def calculate_messages_tokens(cls, messages: List[Dict[str, str]]) -> int:
        """Laskee viestilistan arvioidun token-määrän."""
        total = 0
        for m in messages:
            content = m.get("content", "")
            total += cls.estimate_tokens(content) + 4
        return total

    @classmethod
    def is_approaching_tier_limit(cls, messages: List[Dict[str, str]]) -> bool:
        """Tarkistaa onko konteksti lähestymässä 200k rajaa."""
        return cls.calculate_messages_tokens(messages) >= cls.MAX_SAFE_CONTEXT_TOKENS

    @classmethod
    def estimate_turn_cost(
        cls,
        input_tokens: int,
        output_tokens: int,
        provider: str = "xai",
        is_cached: bool = True
    ) -> Dict[str, float]:
        """Laskee arvioidun kutsun hinnan dollareissa."""
        provider = provider.lower()
        if provider == "xai":
            in_rate = 0.50 if is_cached else 2.00
            out_rate = 10.00
        elif provider == "azure" or provider == "openai":
            in_rate = 2.50
            out_rate = 10.00
        else:
            in_rate = 2.00
            out_rate = 8.00

        input_cost = (input_tokens / 1_000_000.0) * in_rate
        output_cost = (output_tokens / 1_000_000.0) * out_rate
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(input_cost + output_cost, 6),
            "is_cached_rate": is_cached
        }

context_budget = ContextBudgetManager()
