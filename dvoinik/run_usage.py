"""Счётчики обращений к SDK в пределах одного запуска исследования."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass


@dataclass
class RunUsage:
    sdk_calls: int = 0
    calls_with_usage: int = 0
    reported_tokens: int | None = None
    cache_hits: int = 0

    def snapshot(self, concurrency):
        result = asdict(self)
        if self.sdk_calls == 0:
            result["reported_tokens"] = 0
        return {"concurrency": concurrency, **result}


_current = ContextVar[RunUsage | None]("dvoinik_run_usage", default=None)


@contextmanager
def collect_usage():
    usage = RunUsage()
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)


async def measure_call(request):
    usage = _current.get()
    if usage is None:
        return await request
    usage.sdk_calls += 1
    response = await request
    total = getattr(getattr(response, "usage", None), "total_tokens", None)
    if type(total) is int and total >= 0:
        usage.calls_with_usage += 1
        usage.reported_tokens = (usage.reported_tokens or 0) + total
    return response


def count_cache_hit():
    if (usage := _current.get()) is not None:
        usage.cache_hits += 1
