"""Thin async client for the Nebius Token Factory (OpenAI-compatible) chat API."""
import json
import re

import httpx

from . import config


class LLMError(RuntimeError):
    pass


_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json(text: str) -> dict:
    """Pull the JSON object out of a model reply (tolerates think tags and code fences)."""
    text = _THINK.sub("", text or "").strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError(f"no JSON object in reply: {text[:200]!r}")
    return json.loads(text[start : end + 1])


class TokenFactory:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        think: bool = False,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: float = 60,
    ) -> str:
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if not think:
            # Skips the reasoning trace: ~10x fewer tokens and 2-3x faster on Nemotron 3.
            body["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            r = await self.client.post(
                f"{config.NEBIUS_BASE_URL}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {config.NEBIUS_API_KEY}"},
                timeout=timeout,
            )
        except httpx.HTTPError as e:
            raise LLMError(f"{model}: {type(e).__name__}") from e
        if r.status_code != 200:
            raise LLMError(f"{model}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()["choices"][0]["message"].get("content") or ""

    async def chat_json(self, model: str, system: str, user: str | list, **kw) -> dict:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        reply = await self.chat(model, messages, **kw)
        try:
            return parse_json(reply)
        except (LLMError, json.JSONDecodeError):
            # One retry with an explicit nudge; small models occasionally add prose.
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": "Return only the JSON object, nothing else."},
            ]
            return parse_json(await self.chat(model, messages, **kw))
