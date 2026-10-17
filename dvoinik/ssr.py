"""Semantic Similarity Rating (SSR): готовность по смыслу ответа, а не по названному числу.

Метод из работы Maier et al., 2025 (PyMC Labs и Colgate-Palmolive, arXiv:2510.08338):
двойник отвечает короткой фразой от первого лица, фраза сравнивается по эмбеддингам
с эталонными ответами для каждой точки шкалы 1–5, сходства превращаются в распределение.
В исследовании это дало распределения намного ближе к человеческим, чем прямой
вопрос «оцените от 1 до 5», где модели сбиваются к середине шкалы.

Включение: DVOINIK_ELICITATION=ssr и модель эмбеддингов LLM_EMBED_MODEL
(OpenAI-совместимый /embeddings, например bge-m3 или nomic-embed-text в Ollama).
"""

from __future__ import annotations

import hashlib
import math
import os

# Эталонные ответы для точек шкалы 1–5. Несколько наборов усредняются,
# чтобы результат меньше зависел от конкретной формулировки.
REFERENCE_SETS = [
    [
        "Точно не воспользуюсь этим предложением, оно мне совсем не подходит.",
        "Скорее всего не воспользуюсь, есть серьёзные сомнения.",
        "Пока не знаю, может быть, нужно подумать.",
        "Скорее всего воспользуюсь, предложение мне подходит.",
        "Точно воспользуюсь в ближайшее время, это то, что мне нужно.",
    ],
    [
        "Нет, мне это не нужно.",
        "Вряд ли, меня это не очень привлекает.",
        "Не уверен, всё зависит от деталей.",
        "Да, скорее оформлю.",
        "Да, обязательно оформлю.",
    ],
]
EPSILON = 0.01
POINTS = 5


def mode() -> str:
    """Способ получить готовность: probability (модель называет вероятность) или ssr."""
    value = os.getenv("DVOINIK_ELICITATION", "probability").strip().lower()
    if value not in {"probability", "ssr"}:
        raise ValueError("DVOINIK_ELICITATION: допустимы probability или ssr.")
    return value


def embed_model() -> str:
    return os.getenv("LLM_EMBED_MODEL", "bge-m3")


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if not norm:
        raise ValueError("Эмбеддинг не должен быть нулевым.")
    return dot / norm


def pmf(answer: list[float], references: list[list[list[float]]]) -> list[float]:
    """Распределение по шкале 1–5: сходство минус минимум по набору, нормировка, среднее по наборам."""
    if not references:
        raise ValueError("Нужен хотя бы один набор эталонных ответов.")
    total = [0.0] * POINTS
    for reference in references:
        if len(reference) != POINTS:
            raise ValueError("В наборе должно быть 5 эталонных ответов.")
        sims = [cosine(answer, point) for point in reference]
        low = min(sims)
        shifted = [s - low + EPSILON for s in sims]
        norm = sum(shifted)
        for i, value in enumerate(shifted):
            total[i] += value / norm
    return [round(value / len(references), 6) for value in total]


def top_two(distribution: list[float]) -> float:
    """Доля готовых: вероятность ответов «скорее да» и «точно да»."""
    return distribution[3] + distribution[4]


def draw(probability: float, *keys) -> bool:
    """Детерминированное решение по вероятности: тот же профиль и текст дают тот же ответ."""
    digest = hashlib.sha256("|".join(map(str, keys)).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < probability


class References:
    """Эмбеддинги эталонных ответов: считаются один раз на запуск."""

    def __init__(self, sets: list[list[str]] | None = None):
        self.sets = sets or REFERENCE_SETS
        self.value: list[list[list[float]]] | None = None

    async def get(self, client, model: str) -> list[list[list[float]]]:
        if self.value is None:
            flat = [text for reference in self.sets for text in reference]
            vectors = await embed(client, model, flat)
            self.value = [vectors[i : i + POINTS] for i in range(0, len(vectors), POINTS)]
        return self.value


async def embed(client, model: str, texts: list[str]) -> list[list[float]]:
    response = await client.embeddings.create(model=model, input=texts)
    vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
    if len(vectors) != len(texts) or any(not v for v in vectors):
        raise ValueError("Модель эмбеддингов вернула неполный ответ.")
    return vectors
