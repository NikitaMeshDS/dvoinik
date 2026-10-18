"""Единый запуск эксперимента для UI и CLI; не зависит от Streamlit."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from .engine import baseline_estimate, simulate
from .experiments import normalize_scenario
from .population import build_population
from .reporting import make_record


@dataclass(frozen=True)
class RunSettings:
    n: int = 200
    mock: bool = True
    seed: int = 42
    concurrency: int = 16

    def __post_init__(self):
        for label, value, minimum, maximum in [
            ("Размер аудитории", self.n, 1, 10000),
            ("Seed", self.seed, 0, 999999),
            ("Параллельность", self.concurrency, 1, 64),
        ]:
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{label}: нужно целое число от {minimum} до {maximum}.")
        if type(self.mock) is not bool:
            raise ValueError("Режим демо должен быть true или false.")


def run_experiment(
    key: str,
    scenario: dict,
    settings: RunSettings,
    *,
    progress: Callable[[int, int], None] | None = None,
    guard: Callable[[], None] | None = None,
) -> dict:
    """Снимок создаётся только после нормализации и проверки действующего доступа."""
    checked = normalize_scenario(scenario)
    check_access = guard or (lambda: None)
    check_access()
    started = time.perf_counter()
    twins = build_population(settings.n, checked["population"], seed=settings.seed)

    def advance(done: int, total: int):
        check_access()
        if progress:
            progress(done, total)

    report = simulate(
        twins,
        checked,
        mock=settings.mock,
        seed=settings.seed,
        concurrency=settings.concurrency,
        progress=advance,
        guard=check_access,
    )
    check_access()
    baseline = baseline_estimate(checked, mock=settings.mock)
    check_access()
    return make_record(
        key,
        checked,
        settings.n,
        settings.mock,
        settings.seed,
        report,
        twins,
        time.perf_counter() - started,
        baseline=baseline,
    )


def seed_robustness(key: str, scenario: dict, settings: RunSettings, repeats: int) -> dict:
    """Повторяет запуск с соседними seed: другая выборка профилей и ответов.

    Показывает, насколько лидер зависит от случайной популяции. Формулировки,
    модель и состав сегментов не меняются; точность прогноза людей не проверяется.
    """
    if type(repeats) is not int or not 2 <= repeats <= 20:
        raise ValueError("Повторов: нужно целое число от 2 до 20.")
    leaders: dict[str, int] = {}
    runs = []
    for offset in range(repeats):
        seed = (settings.seed + offset) % 1_000_000
        record = run_experiment(key, scenario, replace(settings, seed=seed))
        rates = {v: r["conversion"] for v, r in record["report"].items() if r["n"]}
        best = max(rates.values()) if rates else None
        top = sorted(v for v, rate in rates.items() if rate == best)
        label = "=".join(top) if top else "—"
        leaders[label] = leaders.get(label, 0) + 1
        runs.append({"seed": seed, "leaders": top, "rates": rates})
    return {"repeats": repeats, "leaders": leaders, "runs": runs}
