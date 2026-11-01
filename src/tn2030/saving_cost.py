"""What it costs to save a MWh, against what the saved MWh avoids.

The model values a saved MWh but treats the saving itself as free. Air conditioners are the one Tunisian case
priced per kWh in a published study (LBNL 2023, rows ac_* of the register): a more efficient unit costs more
to buy and uses less electricity every year. Spreading the extra price over the unit's life like a loan gives
the cost of each kWh it saves, which can be set against what that kWh is worth to the power system.
"""

import pandas as pd

from tn2030.toy import annuity

# (register prefix, level): cooling-only or reversible units, at the EU 2014 standard or the best available
AC_MEASURES = (("cool", "eu"), ("cool", "best"), ("rev", "eu"), ("rev", "best"))
LABELS = {
    "cool_eu": "Cooling-only AC, EU 2014 standard",
    "cool_best": "Cooling-only AC, best available",
    "rev_eu": "Reversible AC, EU 2014 standard",
    "rev_best": "Reversible AC, best available",
}


def cost_of_saved_energy(extra_price: float, kwh_saved_per_year: float, rate: float, lifetime_years: float) -> float:
    """Cost of one kWh saved: the extra purchase price as a yearly payment, divided by the kWh saved each year."""
    if kwh_saved_per_year <= 0:
        raise ValueError("the efficient unit must use less electricity than the one it replaces")
    return extra_price * annuity(rate, lifetime_years) / kwh_saved_per_year


def ac_saving_costs(r: dict) -> pd.DataFrame:
    """One row per AC measure, against today's market average: extra price, kWh saved a year and EUR per MWh saved.

    Uses the model's discount rate (LBNL used 6.3%, the lending rate), so plants and savings are annualised alike.
    """
    rows = {}
    for kind, level in AC_MEASURES:
        extra = r[f"ac_{kind}_price_{level}_usd"] - r[f"ac_{kind}_price_bau_usd"]
        saved = r[f"ac_{kind}_kwh_bau"] - r[f"ac_{kind}_kwh_{level}"]
        usd_per_kwh = cost_of_saved_energy(extra, saved, r["discount_rate"], r["ac_lifetime_years"])
        rows[f"{kind}_{level}"] = {"measure": LABELS[f"{kind}_{level}"], "extra_price_usd": extra,
                                   "kwh_saved_per_year": saved,
                                   "cost_eur_per_mwh": usd_per_kwh * 1000 / r["usd_per_eur_2021"]}
    return pd.DataFrame(rows).T.infer_objects()


def compare_with_value(costs: pd.DataFrame, value_eur_per_mwh: float, r: dict) -> pd.DataFrame:
    """Add what a MWh saved at the meter is worth to the power system and to the AC owner.

    The model's demand includes grid losses, so a MWh saved at the meter avoids 1 / (1 - losses) MWh there.
    """
    out = costs.copy()
    out["value_eur_per_mwh"] = value_eur_per_mwh / (1 - r["grid_losses"])
    out["tariff_eur_per_mwh"] = r["ac_tariff_usd_per_kwh"] * 1000 / r["usd_per_eur_2021"]
    out["net_eur_per_mwh"] = out.value_eur_per_mwh - out.cost_eur_per_mwh
    out["pays_for_system"] = out.net_eur_per_mwh > 0
    out["pays_for_owner"] = out.tariff_eur_per_mwh > out.cost_eur_per_mwh
    return out
