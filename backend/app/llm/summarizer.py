"""LLM summarization of competitor changes (OpenAI-compatible API)."""

import json
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

SYSTEM_PROMPT = (
    "Ты аналитик конкурентов. По списку изменений напиши "
    "1-3 предложения вывода на русском. Без воды."
)


async def summarize(changes: list[dict[str, Any]], competitor_name: str) -> str:
    """Summarize a list of changes for a competitor; return the LLM text."""
    client = AsyncOpenAI(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        timeout=60,
    )
    response = await client.chat.completions.create(
        model=settings.ai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {"competitor": competitor_name, "changes": changes},
                    ensure_ascii=False,
                ),
            },
        ],
        max_tokens=300,
    )
    return response.choices[0].message.content or ""
