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

# Опорные открытые данные: с чем сверены атрибуты сегментов и что остаётся допущением.
# Это не калибровка выборки: цифры показывают, на что опираться при проверке профилей.
SEGMENT_SOURCES = {
    "senior": [
        {
            "fact": "Средний размер пенсии на 1 мая 2026 года — 25 399 ₽",
            "use": "Диапазон дохода в профилях «пенсия 20–35 тыс. ₽» включает среднее значение.",
            "status": "согласуется",
            "source": "Социальный фонд России, по данным РИА Новости",
            "date": "июнь 2026",
            "url": "https://finance.mail.ru/article/srednij-razmer-pensii-rossiyan-v-mae-2026-goda-sostavil-svyshe-253-tys-rublej-69213814/",
        },
        {
            "fact": "24% людей старше 60 полностью самостоятельно пользуются мобильным банком; 54% не пользуются интернетом",
            "use": "Поддерживает установки «предпочитает отделение» и «осторожен с новым».",
            "status": "ориентир",
            "source": "Опрос «ИнтерПенсионер», август 2025, более 1,5 тыс. человек 60+ из регионов с городами-миллионниками",
            "date": "октябрь 2025",
            "url": "https://ecomhub.ru/pensioners-digital-isolation-internet-messengers-russia-2025-interpensioner/",
        },
    ],
    "self_employed": [
        {
            "fact": "17,26 млн плательщиков налога на профессиональный доход (август 2026)",
            "use": "Сегмент массовый; доля в аудитории задаётся исследователем.",
            "status": "ориентир",
            "source": "ФНС России, по данным Sostav",
            "date": "август 2026",
            "url": "https://www.sostav.ru/publication/chislo-samozanyatykh-v-rossii-prevysilo-17-2-mln-86292.html",
        },
        {
            "fact": "Лимит дохода самозанятого — 2,4 млн ₽ в год",
            "use": "Верхняя граница «50–200 тыс. ₽» в месяц соответствует лимиту режима.",
            "status": "согласуется",
            "source": "Правила режима НПД, по материалу ИА «Амител»",
            "date": "май 2026",
            "url": "https://www.amic.ru/news/chislo-samozanyatyh-v-rossii-prevysilo-15-millionov-chelovek-583259",
        },
    ],
    "nonresident": [
        {
            "fact": "Более 400 тыс. иностранных студентов в 2025 году — 8,5% всех студентов; больше всего из Казахстана, Туркменистана, Китая, Узбекистана и Индии",
            "use": "Ориентир для доли сегмента в студенческих сценариях и для языков интерфейса.",
            "status": "ориентир",
            "source": "Минобрнауки России, по данным «Коммерсанта» и RTVI",
            "date": "февраль 2026",
            "url": "https://rtvi.com/news/ot-kazahstana-do-kitaya-stalo-izvestno-kolichestvo-inostrannyh-studentov-v-rossii/",
        },
    ],
    "teen": [
        {
            "fact": "59% подростков 14–17 лет имеют личную банковскую карту, 56% пользуются мобильным банком",
            "use": "Подтверждает, что сегмент уже пользуется картами; данные 2021 года нужно обновить.",
            "status": "устарело",
            "source": "НАФИ, опрос июня 2021 года, по данным Sostav",
            "date": "сентябрь 2021",
            "url": "https://www.sostav.ru/publication/detskij-banking-50185.html",
        },
    ],
}
SOURCE_GAPS = (
    "Для студентов Москвы и регионов и для молодых семей открытых опорных цифр пока не подобрано: "
    "доходы, привычки и установки этих сегментов — экспертные допущения."
)


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


def allocate_population(n: int, segments: dict[str, float]) -> dict[str, int]:
    """Точные размеры сегментов методом наибольших остатков, без генерации профилей."""
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
    total = sum(segments.values())
    expected = {s: n * w / total for s, w in segments.items()}
    counts = Counter({s: math.floor(value) for s, value in expected.items()})
    for sid in sorted(expected, key=lambda s: expected[s] - counts[s], reverse=True)[
        : n - sum(counts.values())
    ]:
        counts[sid] += 1
    return dict(counts)


def build_population(n: int, segments: dict[str, float], seed: int = 42) -> list[Twin]:
    """Стратифицированная популяция: доли нормируются, остатки распределяются по величине."""
    counts = allocate_population(n, segments)
    rng = random.Random(seed)
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
