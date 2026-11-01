from pathlib import Path

import pandas as pd
import pytest

from tn2030.pipeline import saving_cost_step
from tn2030.saving_cost import ac_saving_costs, compare_with_value, cost_of_saved_energy
from tn2030.toy import annuity

REGISTER = Path(__file__).parents[1] / "data" / "assumptions_register.xlsx"


def test_cost_of_saved_energy_by_hand():
    # 48 US$ more for a unit that uses 90 kWh less a year, paid back over 10.5 years at 7.1%
    cost = cost_of_saved_energy(48, 90, 0.071, 10.5)
    assert cost == pytest.approx(48 * annuity(0.071, 10.5) / 90)
    assert cost == pytest.approx(0.0738, abs=1e-4)


def test_cost_of_saved_energy_needs_a_saving():
    with pytest.raises(ValueError):
        cost_of_saved_energy(48, 0, 0.071, 10.5)


def test_ac_saving_costs_from_register(reg):
    costs = ac_saving_costs(reg)
    assert list(costs.index) == ["cool_eu", "cool_best", "rev_eu", "rev_best"]
    assert (costs.extra_price_usd > 0).all() and (costs.kwh_saved_per_year > 0).all()
    # cooling-only at the EU standard: 48 US$ for 90 kWh a year (LBNL Table 11)
    assert costs.at["cool_eu", "cost_eur_per_mwh"] == pytest.approx(
        48 * annuity(reg["discount_rate"], 10.5) / 90 * 1000 / reg["usd_per_eur_2021"])
    # the best units save more but cost more per kWh saved
    assert costs.at["cool_best", "cost_eur_per_mwh"] > costs.at["cool_eu", "cost_eur_per_mwh"]
    assert costs.at["rev_best", "cost_eur_per_mwh"] > costs.at["rev_eu", "cost_eur_per_mwh"]


def test_compare_with_value(reg):
    table = compare_with_value(ac_saving_costs(reg), 70.0, reg)
    # a MWh saved at the meter also avoids the grid losses that would have carried it
    assert table.value_eur_per_mwh.iloc[0] == pytest.approx(70.0 / (1 - reg["grid_losses"]))
    assert table.net_eur_per_mwh.tolist() == pytest.approx((table.value_eur_per_mwh - table.cost_eur_per_mwh).tolist())
    assert table.pays_for_system.tolist() == (table.net_eur_per_mwh > 0).tolist()
    assert table.pays_for_owner.all()  # owners pay the top tariff blocks, above every saving cost here


def test_saving_cost_step(tmp_path):
    summary = pd.DataFrame({"scenario": ["S0", "S1-15C"], "year": [2030, 2030], "demand_twh": [27.0, 23.0]})
    avoided = pd.DataFrame({"scenario": ["S1-15C", "S1-15C"], "reference": ["S0", "S0"], "year": ["2030", "2027-2030"],
                            "cost_eur_per_mwh": [99.0, 70.0]})
    summary.to_csv(tmp_path / "summary.csv", index=False)
    avoided.to_csv(tmp_path / "avoided.csv", index=False)
    saving_cost_step(REGISTER, tmp_path / "summary.csv", tmp_path / "avoided.csv", tmp_path / "out.csv")

    out = pd.read_csv(tmp_path / "out.csv", index_col=0)
    assert list(out.index) == ["cool_eu", "cool_best", "rev_eu", "rev_best"]
    assert out.value_eur_per_mwh.iloc[0] == pytest.approx(70.0 / (1 - 0.18))  # the whole-plan value, not 2030's
    # the EU standard saves 287 GWh at the meter in 2030: 0.35 TWh at the plants, of the 4 TWh S1-15C saves
    assert out.at["cool_eu", "standard_share_of_saving"] == pytest.approx(0.287 / (1 - 0.18) / 4.0)
    assert out.at["rev_best", "standard_share_of_saving"] == pytest.approx(0.841 / (1 - 0.18) / 4.0)
