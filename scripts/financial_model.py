"""Illustrative operating scenarios, not actual revenue or externally verified prices.

Run: python scripts/financial_model.py [--scenario base|downside|upside]
All costs are cash operating costs, before taxes/capex/financing. Clients start
at the beginning of a month and pay annually upfront, renewing without churn.
"""

import argparse
import json
import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Assumptions:
    annual_price: float = 1_500_000
    paid_fte: float = 3
    loaded_monthly_pay: float = 250_000
    fixed_infrastructure: float = 50_000
    fixed_other: float = 100_000
    runs_per_client_month: float = 50
    profiles_per_run: float = 200
    variants_per_run: float = 3
    tokens_per_response: float = 1000
    baseline_tokens_per_run: float = 1000
    token_price_per_1k: float = 0.5
    support_hours_per_client_month: float = 8
    delivery_hour_cost: float = 2000
    hosting_per_client_month: float = 10_000
    onboarding_hours: float = 40
    cash_cac_per_client: float = 150_000
    client_studies_month: float = 6
    client_hours_saved_study: float = 12
    client_hour_cost: float = 2500
    client_implementation: float = 200_000


def scenarios():
    return {
        "base": (Assumptions(), [0, 0, 0] + [1, 0, 1] * 7),
        "downside": (
            Assumptions(annual_price=1_200_000, onboarding_hours=80, token_price_per_1k=1),
            [0] * 6 + [1, 0, 0] * 6,
        ),
        "upside": (
            Assumptions(annual_price=1_800_000, onboarding_hours=30),
            [0] * 3 + [1] * 21,
        ),
    }


def forecast(a: Assumptions, new_clients: list[int]) -> list[dict]:
    if any(not math.isfinite(v) or v < 0 for v in asdict(a).values()):
        raise ValueError("Assumptions must be finite and nonnegative")
    if any(type(n) is not int or n < 0 for n in new_clients):
        raise ValueError("New clients must be nonnegative integers")
    active, cash, deferred, rows = 0, 0.0, 0.0, []
    unit_tokens = a.runs_per_client_month * (
        a.profiles_per_run * a.variants_per_run * a.tokens_per_response + a.baseline_tokens_per_run
    )
    fixed = a.paid_fte * a.loaded_monthly_pay + a.fixed_infrastructure + a.fixed_other
    for i, new in enumerate(new_clients):
        active += new
        renewing = sum(new_clients[k] for k in range(i - 12, -1, -12))
        collections = (new + renewing) * a.annual_price
        revenue = active * a.annual_price / 12
        inference = active * unit_tokens / 1000 * a.token_price_per_1k
        support = active * a.support_hours_per_client_month * a.delivery_hour_cost
        hosting = active * a.hosting_per_client_month
        onboarding = new * a.onboarding_hours * a.delivery_hour_cost
        acquisition = new * a.cash_cac_per_client
        costs = fixed + inference + support + hosting + onboarding + acquisition
        operating_result, cash_flow = revenue - costs, collections - costs
        cash += cash_flow
        deferred += collections - revenue
        rows.append(
            dict(
                month=i + 1,
                new=new,
                renewing=renewing,
                active=active,
                collections=collections,
                revenue=revenue,
                inference=inference,
                support=support,
                hosting=hosting,
                fixed=fixed,
                onboarding=onboarding,
                acquisition=acquisition,
                costs=costs,
                operating_result=operating_result,
                cash_flow=cash_flow,
                cash=cash,
                deferred=deferred,
            )
        )
    return rows


def client_effect(
    studies_per_month: float,
    hours_saved: float,
    hour_cost: float,
    annual_price: float,
    implementation: float,
    additional_year_cost: float = 0,
) -> dict:
    """Compare the first-year cost of buying against the value of time freed at the bank."""
    costs = (studies_per_month, hour_cost, annual_price, implementation, additional_year_cost)
    if any(not math.isfinite(v) or v < 0 for v in costs) or not math.isfinite(hours_saved):
        raise ValueError("Client inputs must be finite; only hours saved may be negative.")
    hours_factor = 12 * studies_per_month * hour_cost
    time_value = hours_factor * hours_saved
    cost = annual_price + implementation + additional_year_cost
    subscription_ceiling = time_value - implementation - additional_year_cost
    return {
        "annual_time_value": time_value,
        "first_year_cost": cost,
        "first_year_net_value": time_value - cost,
        "first_year_roi": (time_value - cost) / cost if cost else None,
        "break_even_hours_per_study": cost / hours_factor if hours_factor else None,
        "max_break_even_subscription": subscription_ceiling if subscription_ceiling >= 0 else None,
    }


def summary(a: Assumptions, rows: list[dict]) -> dict:
    unit = forecast(a, [1])[0]
    contribution = a.annual_price / 12 - unit["inference"] - unit["support"] - unit["hosting"]
    effect = client_effect(
        a.client_studies_month,
        a.client_hours_saved_study,
        a.client_hour_cost,
        a.annual_price,
        a.client_implementation,
    )
    return {
        "monthly_contribution": contribution,
        "steady_state_break_even_clients": math.ceil(unit["fixed"] / contribution)
        if contribution > 0
        else None,
        "client_annual_time_value": effect["annual_time_value"],
        "client_first_year_roi": effect["first_year_roi"],
        "cash_funding_needed": max(0, -min([0, *(r["cash"] for r in rows)])),
        "collections": sum(r["collections"] for r in rows),
        "revenue": sum(r["revenue"] for r in rows),
        "operating_result": sum(r["operating_result"] for r in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=scenarios(), default="base")
    parser.add_argument(
        "--client-effect", action="store_true", help="Show only the bank's first-year scenario"
    )
    defaults = {
        "studies_per_month": "client_studies_month",
        "hours_saved": "client_hours_saved_study",
        "hour_cost": "client_hour_cost",
        "annual_price": "annual_price",
        "implementation": "client_implementation",
        "additional_year_cost": None,
    }
    for field in defaults:
        parser.add_argument("--" + field.replace("_", "-"), type=float)
    args = parser.parse_args()
    assumptions, schedule = scenarios()[args.scenario]
    if args.client_effect:
        inputs = {}
        for field, baseline in defaults.items():
            value = getattr(args, field)
            inputs[field] = (
                value if value is not None else (getattr(assumptions, baseline) if baseline else 0)
            )
        try:
            output = {
                "kind": "illustrative_client_effect",
                "scenario": args.scenario,
                "assumptions": inputs,
                "summary": client_effect(**inputs),
            }
            rendered = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)
        except ValueError as exc:
            parser.error(str(exc))
        print(rendered)
        return
    if any(getattr(args, field) is not None for field in defaults):
        parser.error("Client overrides require --client-effect.")
    result = forecast(assumptions, schedule)
    print(
        json.dumps(
            {
                "scenario": args.scenario,
                "assumptions": asdict(assumptions),
                "months": result,
                "summary": summary(assumptions, result),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
