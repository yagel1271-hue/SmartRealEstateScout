import pytest

from app.analysis import finance


def test_purchase_tax_investor_8_percent_below_bracket():
    assert finance.purchase_tax(1_500_000) == pytest.approx(120_000)


def test_purchase_tax_progressive_above_bracket():
    # 8% of 6,055,070 + 10% of the rest
    expected = 6_055_070 * 0.08 + (7_000_000 - 6_055_070) * 0.10
    assert finance.purchase_tax(7_000_000) == pytest.approx(expected)


def test_gross_yield_spec_formula():
    assert finance.gross_yield(5_000, 1_500_000) == pytest.approx(4.0)
    with pytest.raises(ValueError):
        finance.gross_yield(5_000, 0)


def test_costs_and_net_yield_scenarios_ordered():
    c = finance.purchase_costs(1_500_000, sqm=70, condition="renovated")
    assert c.renovation == 0
    assert c.total_investment == pytest.approx(1_500_000 + 120_000 + 1_500_000 * 0.0059 + 1_500_000 * 0.0236 + 6_000)
    sc = finance.all_scenarios(5_000, c)
    assert sc["conservative"]["net_yield_on_total"] < sc["base"]["net_yield_on_total"] < sc["optimistic"]["net_yield_on_total"]
    base = sc["base"]
    assert base["annual_income"] == round(5_000 * 11.5)
    assert base["gross_yield_on_total"] < base["gross_yield_on_price"]


def test_renovation_cost_needs_renovation():
    assert finance.renovation_cost(80, "needs_renovation") == 80 * 4_500
    assert finance.renovation_cost(None, "needs_renovation") == 0
