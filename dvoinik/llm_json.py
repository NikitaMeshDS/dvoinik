"""JSON-ответы от разных OpenAI-совместимых серверов.

Ollama и vLLM понимают response_format={"type": "json_object"}, LM Studio его отклоняет
(принимает только json_schema или text). В режиме auto первый отказ из-за response_format
переключает процесс на обычный текст: JSON просит системный промпт, а ответ очищается от
блоков рассуждений <think> и обёрток ```json.

LLM_JSON_MODE: auto (по умолчанию) | json_object | text.
LLM_NO_THINK=1 добавляет к последнему сообщению «/no_think» — мягкое отключение рассуждений
у моделей Qwen3.x: короткий JSON не требует размышлений, а с ними запрос идёт в разы дольше.
"""

from __future__ import annotations

import os
import re

_STATE = {"text": None}
_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def mode() -> str:
    value = os.getenv("LLM_JSON_MODE", "auto").strip().lower()
    if value not in {"auto", "json_object", "text"}:
        raise ValueError("LLM_JSON_MODE: допустимы auto, json_object или text.")
    return value


def reset():
    _STATE["text"] = None


def extract(content) -> str:
    """Оставляет только JSON-объект: без рассуждений, обёрток и текста вокруг."""
    if not isinstance(content, str):
        raise ValueError("Модель вернула пустой ответ.")
    text = _FENCE.sub("", _THINK.sub("", content).strip()).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else text


def _rejects_format(exc) -> bool:
    status = getattr(exc, "status_code", None)
    return status in {400, 422} and "response_format" in str(exc).lower()


def _no_think(messages: list[dict]) -> list[dict]:
    if os.getenv("LLM_NO_THINK") != "1" or not messages:
        return messages
    last = messages[-1]
    return [*messages[:-1], {**last, "content": f"{last['content']}\n/no_think"}]


async def chat_json(client, model: str, messages: list[dict], temperature: float) -> str:
    """Запрос с ожиданием JSON; возвращает текст объекта для json.loads."""
    messages = _no_think(messages)
    current = mode()
    use_text = current == "text" or (current == "auto" and _STATE["text"])
    if not use_text:
        try:
            r = await client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=messages,
            )
            return extract(r.choices[0].message.content)
        except Exception as exc:
            if current != "auto" or not _rejects_format(exc):
                raise
            _STATE["text"] = True
    r = await client.chat.completions.create(model=model, temperature=temperature, messages=messages)
    return extract(r.choices[0].message.content)
