"""Strict JSON payloads at the HTTP boundary."""

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr


class Body(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Login(Body):
    username: StrictStr
    password: StrictStr


class Preview(Body):
    population: dict
    n: StrictInt


class Estimate(Body):
    scenario: dict
    n: StrictInt
    concurrency: StrictInt = 16


class Run(Body):
    scenario_key: StrictStr
    scenario: dict
    n: StrictInt = 200
    mock: StrictBool = True
    seed: StrictInt = 42
    concurrency: StrictInt = 16


class Import(Body):
    content: StrictStr


class Compare(Body):
    left_id: StrictStr
    right_id: StrictStr


class Survey(Body):
    csv: StrictStr


class Validation(Survey):
    base_validation: dict | None


class Export(Body):
    format: StrictStr = "json"
    kind: StrictStr = "record"
    preview_id: StrictStr | None = None


class RecordExport(Export):
    record_id: StrictStr


class Insights(Body):
    record_id: StrictStr
    segment: StrictStr = "all"


class Rewrite(Body):
    record_id: StrictStr
    hypothesis_id: StrictStr


class Active(Body):
    active: StrictBool
