"""Deterministic financial calculations. No AI. Fully unit-tested."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.analysis import assumptions as A


def purchase_tax(price: float, brackets: list[tuple[float, float]] | None = None) -> float:
    """Progressive purchase tax for an additional apartment."""
    brackets = brackets or A.PURCHASE_TAX_BRACKETS
    tax, lower = 0.0, 0.0
    for upper, rate in brackets:
        if price <= lower:
            break
        taxable = min(price, upper) - lower
        tax += taxable * rate
        lower = upper
    return round(tax, 2)


@dataclass
class PurchaseCosts:
    price: float
    purchase_tax: float
    lawyer: float
    broker: float
    other: float
    renovation: float

    @property
    def total_investment(self) -> float:
        return self.price + self.purchase_tax + self.lawyer + self.broker + self.other + self.renovation

    def as_dict(self) -> dict:
        d = asdict(self)
        d["total_investment"] = round(self.total_investment)
        return {k: round(v) if isinstance(v, float) else v for k, v in d.items()}


def renovation_cost(sqm: float | None, condition: str | None, overrides: dict | None = None) -> float:
    if not sqm:
        return 0.0
    if condition == "needs_renovation":
        return sqm * A.value("renovation_full_per_sqm", overrides)
    if condition in (None, "good"):
        return sqm * A.value("renovation_light_per_sqm", overrides) * 0.5  # light refresh allowance
    return 0.0


def purchase_costs(price: float, sqm: float | None = None, condition: str | None = None,
                   with_broker: bool = True, overrides: dict | None = None) -> PurchaseCosts:
    return PurchaseCosts(
        price=price,
        purchase_tax=purchase_tax(price),
        lawyer=price * A.value("lawyer_pct", overrides),
        broker=price * A.value("broker_pct", overrides) if with_broker else 0.0,
        other=A.value("appraiser_fixed", overrides),
        renovation=renovation_cost(sqm, condition, overrides),
    )


def gross_yield(monthly_rent: float, price: float) -> float:
    """Spec formula: (monthly rent x 12) / purchase price x 100."""
    if price <= 0:
        raise ValueError("price must be positive")
    return monthly_rent * 12 / price * 100


def net_yield(monthly_rent: float, costs: PurchaseCosts, scenario: str = "base",
              overrides: dict | None = None) -> dict:
    sc = A.SCENARIOS[scenario]
    rent = monthly_rent * sc["rent_factor"]
    vacancy_m = A.value("vacancy_months", overrides) * sc["vacancy_factor"]
    income = rent * (12 - vacancy_m)
    expenses = (
        rent * 12 * A.value("maintenance_pct_rent", overrides)
        + A.value("insurance_yearly", overrides)
        + rent * 12 * A.value("management_pct_rent", overrides)
    )
    noi = income - expenses
    return {
        "scenario": scenario,
        "label": sc["label"],
        "monthly_rent": round(rent),
        "vacancy_months": round(vacancy_m, 2),
        "annual_income": round(income),
        "annual_expenses": round(expenses),
        "noi": round(noi),
        "gross_yield_on_price": round(gross_yield(rent, costs.price), 2),
        "gross_yield_on_total": round(rent * 12 / costs.total_investment * 100, 2),
        "net_yield_on_total": round(noi / costs.total_investment * 100, 2),
    }


def all_scenarios(monthly_rent: float, costs: PurchaseCosts, overrides: dict | None = None) -> dict:
    return {name: net_yield(monthly_rent, costs, name, overrides) for name in A.SCENARIOS}
