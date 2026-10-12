"""Генерация популяции цифровых двойников по сегментам.

Каждый двойник — персонаж с атрибутами (возраст, регион, доход, привычки, отношение к банкам).
Доли и атрибуты — экспертные предположения для прототипа, а не калиброванная банковская
выборка. Перед пилотом их нужно проверить на данных целевой аудитории.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import asdict, dataclass

SEGMENTS = {
    "student_msk": {
        "name": "Студенты 18–22, Москва",
        "age": (18, 22),
        "region": ["Москва"],
        "income": ["до 30 тыс. ₽", "30–60 тыс. ₽"],
        "habits": ["такси и доставка еды", "подписки на сервисы", "переводы друзьям", "онлайн-шопинг"],
        "attitude": ["ценит выгоду и скорость", "сравнивает банки в соцсетях", "не любит скрытые условия"],
    },
    "student_reg": {
        "name": "Студенты регионов",
        "age": (18, 23),
        "region": ["Казань", "Самара", "Омск", "Екатеринбург", "Воронеж"],
        "income": ["до 20 тыс. ₽", "20–40 тыс. ₽"],
        "habits": ["общественный транспорт", "продуктовые магазины", "переводы от родителей"],
        "attitude": ["очень чувствителен к плате за обслуживание", "доверяет крупным банкам"],
    },
    "teen": {
        "name": "Подростки 14–17 (решение с родителем)",
        "age": (14, 17),
        "region": ["Москва", "Санкт-Петербург", "Новосибирск", "Краснодар"],
        "income": ["карманные деньги"],
        "habits": ["игры и донаты", "фастфуд", "покупки в маркетплейсах"],
        "attitude": ["важно мнение друзей", "родитель контролирует траты"],
    },
    "young_family": {
        "name": "Молодые семьи с детьми",
        "age": (26, 38),
        "region": ["Москва", "Подмосковье", "Нижний Новгород", "Тюмень"],
        "income": ["80–150 тыс. ₽ на семью", "150–250 тыс. ₽ на семью"],
        "habits": ["ипотека", "детские товары", "совместный бюджет"],
        "attitude": ["экономит время", "боится долговой нагрузки"],
    },
    "senior": {
        "name": "Пенсионеры 60+",
        "age": (60, 78),
        "region": ["Тула", "Саратов", "Москва", "Пермь"],
        "income": ["пенсия 20–35 тыс. ₽"],
        "habits": ["оплата ЖКХ", "аптеки", "вклады"],
        "attitude": ["осторожен с новым", "предпочитает отделение", "боится мошенников"],
    },
    "self_employed": {
        "name": "Самозанятые и микробизнес",
        "age": (22, 45),
        "region": ["Москва", "Санкт-Петербург", "Казань", "Ростов-на-Дону"],
        "income": ["нерегулярный, 50–200 тыс. ₽"],
        "habits": ["приём оплат от клиентов", "чеки в «Мой налог»", "кассовые разрывы"],
        "attitude": ["считает каждую комиссию", "ценит простую отчётность"],
    },
    "nonresident": {
        "name": "Иностранные студенты и мигранты",
        "age": (19, 35),
        "region": ["Москва", "Санкт-Петербург", "Казань"],
        "income": ["до 40 тыс. ₽", "40–80 тыс. ₽"],
        "habits": ["переводы на родину", "оплата учёбы или жилья"],
        "attitude": ["плохо понимает банковские термины на русском", "важен язык интерфейса"],
    },
}

FIRST = [
    "Алина",
    "Тимур",
    "Даша",
    "Илья",
    "Маша",
    "Артём",
    "Соня",
    "Кирилл",
    "Ольга",
    "Сергей",
    "Валентина",
    "Николай",
    "Айгуль",
    "Руслан",
    "Ли Вэй",
    "Амир",
    "Нгуен",
    "Дильноза",
]


@dataclass
class Twin:
    id: int
    segment: str
    name: str
    age: int
    region: str
    income: str
    habits: list[str]
    attitude: str

    def profile(self) -> str:
        return (
            f"{self.name}, {self.age} лет, {self.region}. Доход: {self.income}. "
            f"Привычки: {', '.join(self.habits)}. Отношение к банкам: {self.attitude}."
        )

    def to_dict(self):
        return asdict(self)


def build_population(n: int, segments: dict[str, float], seed: int = 42) -> list[Twin]:
    """Стратифицированная популяция: доли нормируются, остатки распределяются по величине."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("Размер популяции должен быть положительным целым числом.")
    if not segments or any(s not in SEGMENTS for s in segments):
        raise ValueError("Выберите известные сегменты аудитории.")
    if (
        any(
            isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0
            for w in segments.values()
        )
        or sum(segments.values()) <= 0
    ):
        raise ValueError("Доли сегментов должны быть неотрицательными, а их сумма — больше нуля.")
    rng = random.Random(seed)
    total = sum(segments.values())
    expected = {s: n * w / total for s, w in segments.items()}
    counts = Counter({s: math.floor(value) for s, value in expected.items()})
    for sid in sorted(expected, key=lambda s: expected[s] - counts[s], reverse=True)[
        : n - sum(counts.values())
    ]:
        counts[sid] += 1
    assignments = [s for s, count in counts.items() for _ in range(count)]
    rng.shuffle(assignments)
    twins = []
    for i, sid in enumerate(assignments):
        s = SEGMENTS[sid]
        twins.append(
            Twin(
                id=i,
                segment=sid,
                name=rng.choice(FIRST),
                age=rng.randint(*s["age"]),
                region=rng.choice(s["region"]),
                income=rng.choice(s["income"]),
                habits=rng.sample(s["habits"], k=min(2, len(s["habits"]))),
                attitude=rng.choice(s["attitude"]),
            )
        )
    return twins
