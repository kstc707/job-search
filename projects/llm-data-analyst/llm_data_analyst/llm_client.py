import os

import anthropic

DEFAULT_MODEL = "claude-sonnet-5"


class LLMClient:
    """Minimal wrapper so the agent depends on a `complete(system, user) -> str`
    interface instead of the Anthropic SDK directly, which keeps it swappable and
    trivially fakeable in tests."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self.client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
