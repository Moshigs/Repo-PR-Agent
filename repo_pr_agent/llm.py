from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


class ChatBackend:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "未配置 OPENAI_API_KEY。可复制 .env.example 为 .env，或设置环境变量后再运行。"
            )
        url = base_url if base_url else os.environ.get("OPENAI_BASE_URL")
        self._client = OpenAI(api_key=key, base_url=url) if url else OpenAI(api_key=key)
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        max_completion_tokens: int = 8192,
        temperature: float = 0.2,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        rsp = self._client.chat.completions.create(**kwargs)
        msg = rsp.choices[0].message
        content = getattr(msg, "content", None) or ""
        return content.strip()
