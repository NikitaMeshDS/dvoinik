import pytest

from scripts import financial_model
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


def test_client_effect_distinguishes_value_of_time_from_break_even_price():
    effect = financial_model.client_effect(6, 4, 2500, 1_500_000, 200_000)
    assert effect["annual_time_value"] == 720_000
    assert effect["first_year_cost"] == 1_700_000
    assert effect["first_year_net_value"] == -980_000
    assert effect["first_year_roi"] == pytest.approx(-0.576470588)
    assert effect["break_even_hours_per_study"] == pytest.approx(9.4444444)
    assert effect["max_break_even_subscription"] == 520_000


def test_client_effect_accounts_for_costs_and_cannot_break_even_without_volume():
    effect = financial_model.client_effect(6, 4, 2500, 1_500_000, 200_000, 600_000)
    assert effect["first_year_cost"] == 2_300_000
    assert effect["max_break_even_subscription"] is None
    effect = financial_model.client_effect(0, 4, 2500, 0, 0)
    assert effect["break_even_hours_per_study"] is None
    assert effect["first_year_roi"] is None
    assert financial_model.client_effect(6, -1, 2500, 0, 0)["annual_time_value"] == -180_000
    with pytest.raises(ValueError):
        financial_model.client_effect(6, float("nan"), 2500, 0, 0)
