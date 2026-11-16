import pytest

from scripts.financial_model import Assumptions, forecast


def test_annual_prepayment_is_not_immediate_revenue():
    rows = forecast(Assumptions(), [1] + [0] * 23)
    assert rows[0]["collections"] == 1_500_000
    assert rows[0]["revenue"] == 125_000
    assert rows[0]["deferred"] == 1_375_000
    assert rows[11]["deferred"] == 0
    assert rows[12]["collections"] == 1_500_000
    assert rows[12]["active"] == 1
    assert sum(r["collections"] for r in rows) == sum(r["revenue"] for r in rows)


def test_cash_reconciles_and_capacity_costs_scale():
    assumptions = Assumptions()
    rows = forecast(assumptions, [0, 2, 0])
    assert rows[0]["inference"] == 0
    assert rows[1]["inference"] == 30_050
    assert rows[1]["onboarding"] == 160_000
    assert rows[1]["acquisition"] == 300_000
    assert rows[-1]["cash"] == sum(r["cash_flow"] for r in rows)
    assert rows[-1]["deferred"] == sum(r["collections"] - r["revenue"] for r in rows)


@pytest.mark.parametrize("schedule", [[-1], [0.5], [True]])
def test_invalid_acquisition_schedule_is_rejected(schedule):
    with pytest.raises(ValueError):
        forecast(Assumptions(), schedule)


def test_zero_price_and_inference_price_are_permitted_but_nonfinite_is_not():
    rows = forecast(Assumptions(annual_price=0, token_price_per_1k=0), [1])
    assert rows[0]["revenue"] == rows[0]["inference"] == 0
    with pytest.raises(ValueError):
        forecast(Assumptions(annual_price=float("nan")), [1])
