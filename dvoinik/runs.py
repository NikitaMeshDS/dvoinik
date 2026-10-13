"""Единый запуск эксперимента для UI и CLI; не зависит от Streamlit."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .engine import simulate
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
    )
    check_access()
    return make_record(
        key, checked, settings.n, settings.mock, settings.seed, report, twins, time.perf_counter() - started
    )
