"""Simplified heat pump sizing engine.

Educational load estimate using the UA x delta-T method.
Not a replacement for an ACCA Manual J calculation.
"""

from __future__ import annotations

import csv
import difflib
import math
from dataclasses import asdict, dataclass
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "design_temps.csv"

# Envelope U-values, Btu/(h·ft²·°F), by construction quality
U_VALUES = {
    "poor":    {"wall": 0.25, "roof": 0.10,  "floor": 0.10,  "window": 0.90},
    "average": {"wall": 0.08, "roof": 0.04,  "floor": 0.05,  "window": 0.50},
    "good":    {"wall": 0.05, "roof": 0.026, "floor": 0.033, "window": 0.30},
}

# Natural air changes per hour (ACH) by air tightness
ACH = {"leaky": 1.0, "average": 0.5, "tight": 0.25}

INDOOR_HEATING_F = 70.0
INDOOR_COOLING_F = 75.0
SOLAR_GAIN_BTUH_PER_FT2 = 30.0   # mean window solar gain at cooling design
PERSON_SENSIBLE_BTUH = 230.0
APPLIANCE_BTUH = 1200.0
LATENT_MULTIPLIER = 1.3          # sensible -> total cooling load
BTUH_PER_TON = 12000.0
BTUH_PER_KW = 3412.0
SIZE_LADDER_TONS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]


@dataclass
class Home:
    floor_area_ft2: float
    stories: int = 1
    ceiling_height_ft: float = 8.0
    insulation: str = "average"      # poor | average | good
    air_tightness: str = "average"   # leaky | average | tight
    window_fraction: float = 0.15    # glazing share of gross wall area
    occupants: int = 3

    def validate(self) -> None:
        if not 300 <= self.floor_area_ft2 <= 10000:
            raise ValueError("floor_area_ft2 must be between 300 and 10,000")
        if not 1 <= self.stories <= 4:
            raise ValueError("stories must be between 1 and 4")
        if not 7 <= self.ceiling_height_ft <= 14:
            raise ValueError("ceiling_height_ft must be between 7 and 14")
        if self.insulation not in U_VALUES:
            raise ValueError(f"insulation must be one of {sorted(U_VALUES)}")
        if self.air_tightness not in ACH:
            raise ValueError(f"air_tightness must be one of {sorted(ACH)}")
        if not 0.05 <= self.window_fraction <= 0.5:
            raise ValueError("window_fraction must be between 0.05 and 0.5")
        if not 1 <= self.occupants <= 12:
            raise ValueError("occupants must be between 1 and 12")


def load_cities() -> dict[str, dict]:
    with DATA_FILE.open(newline="") as f:
        return {row["city"].lower(): row for row in csv.DictReader(f)}


def design_conditions(city: str) -> dict:
    """Look up approximate design temperatures for a city, e.g. "Minneapolis, MN"."""
    cities = load_cities()
    key = city.strip().lower()
    match = cities.get(key)
    if match is None:
        # Allow the city name without the state, e.g. "Minneapolis"
        starts = [c for c in cities if c.split(",")[0] == key.split(",")[0]]
        if len(starts) == 1:
            match = cities[starts[0]]
    if match is None:
        close = difflib.get_close_matches(key, list(cities), n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(cities[c]['city'] for c in close)}?" if close else ""
        raise ValueError(
            f"No design data for '{city}'.{hint} You can also give the design temperatures directly."
        )
    return {
        "city": match["city"],
        "heating_design_f": float(match["heating_design_f"]),
        "cooling_design_f": float(match["cooling_design_f"]),
        "climate_zone": match["climate_zone"],
    }


def calculate_loads(home: Home, heating_design_f: float, cooling_design_f: float) -> dict:
    """Design heating and cooling loads in Btu/h with a component breakdown."""
    home.validate()
    u = U_VALUES[home.insulation]

    # Geometry (square footprint assumption)
    footprint = home.floor_area_ft2 / home.stories
    perimeter = 4 * math.sqrt(footprint)
    wall_gross = perimeter * home.ceiling_height_ft * home.stories
    window = wall_gross * home.window_fraction
    wall_net = wall_gross - window
    volume = home.floor_area_ft2 * home.ceiling_height_ft
    cfm = ACH[home.air_tightness] * volume / 60

    # Heating: conduction + infiltration at the winter design temperature
    dt_heat = max(INDOOR_HEATING_F - heating_design_f, 0)
    heat = {
        "walls": u["wall"] * wall_net * dt_heat,
        "windows": u["window"] * window * dt_heat,
        "roof": u["roof"] * footprint * dt_heat,
        "floor": u["floor"] * footprint * dt_heat,
        "infiltration": 1.08 * cfm * dt_heat,
    }

    # Cooling: conduction + solar + internal gains + infiltration (sensible)
    dt_cool = max(cooling_design_f - INDOOR_COOLING_F, 0)
    cool_sensible = {
        "walls": u["wall"] * wall_net * dt_cool,
        "windows": u["window"] * window * dt_cool,
        "roof": u["roof"] * footprint * dt_cool,
        "solar": SOLAR_GAIN_BTUH_PER_FT2 * window,
        "people_and_appliances": home.occupants * PERSON_SENSIBLE_BTUH + APPLIANCE_BTUH,
        "infiltration": 1.08 * cfm * dt_cool,
    }

    heating = sum(heat.values())
    cooling = sum(cool_sensible.values()) * LATENT_MULTIPLIER
    return {
        "heating_btuh": round(heating),
        "cooling_btuh": round(cooling),
        "heating_breakdown_btuh": {k: round(v) for k, v in heat.items()},
        "cooling_sensible_breakdown_btuh": {k: round(v) for k, v in cool_sensible.items()},
        "geometry": {
            "wall_net_ft2": round(wall_net),
            "window_ft2": round(window),
            "roof_ft2": round(footprint),
            "volume_ft3": round(volume),
            "infiltration_cfm": round(cfm),
        },
    }


def capacity_at(temp_f: float, rated_btuh: float, retention_at_5f: float) -> float:
    """Heat pump heating capacity vs outdoor temperature.

    Linear between rated capacity at 47F and retention x rated at 5F,
    extrapolated with the same slope below 5F, floored at zero.
    """
    if temp_f >= 47:
        return rated_btuh
    slope = rated_btuh * (1 - retention_at_5f) / 42.0
    return max(rated_btuh - slope * (47 - temp_f), 0.0)


def balance_point_f(heating_btuh: float, heating_design_f: float,
                    rated_btuh: float, retention_at_5f: float) -> float:
    """Outdoor temperature where heat pump capacity equals the home's heat loss."""
    span = INDOOR_HEATING_F - heating_design_f
    if span <= 0:
        return heating_design_f
    t = 65.0
    while t > -40:
        load = heating_btuh * (INDOOR_HEATING_F - t) / span
        if capacity_at(t, rated_btuh, retention_at_5f) < load:
            return round(t + 0.5, 1)
        t -= 0.5
    return -40.0


def recommend(heating_btuh: float, cooling_btuh: float, heating_design_f: float,
              retention_at_5f: float = 0.70) -> dict:
    """Pick a nominal size from a standard ladder and report backup heat needs."""
    if not 0.3 <= retention_at_5f <= 1.0:
        raise ValueError("retention_at_5f must be between 0.3 and 1.0")
    heating_led = heating_btuh > cooling_btuh
    chosen = SIZE_LADDER_TONS[-1]
    for tons in SIZE_LADDER_TONS:
        rated = tons * BTUH_PER_TON
        if heating_led and capacity_at(heating_design_f, rated, retention_at_5f) >= heating_btuh:
            chosen = tons
            break
        if not heating_led and rated >= cooling_btuh:
            chosen = tons
            break

    rated = chosen * BTUH_PER_TON
    cap_design = capacity_at(heating_design_f, rated, retention_at_5f)
    backup_kw = max(heating_btuh - cap_design, 0) / BTUH_PER_KW

    notes = []
    if backup_kw > 0:
        notes.append(f"Plan about {backup_kw:.1f} kW of backup heat for the coldest hours.")
    if rated > 1.5 * cooling_btuh:
        notes.append("Sized for heating; choose a variable-speed unit so it doesn't short-cycle in summer.")
    if chosen == SIZE_LADDER_TONS[-1] and backup_kw > 0:
        notes.append("Load exceeds a single 5-ton unit; consider envelope upgrades or multiple systems.")

    return {
        "nominal_tons": chosen,
        "rated_capacity_btuh": round(rated),
        "capacity_at_design_btuh": round(cap_design),
        "sizing_basis": "heating" if heating_led else "cooling",
        "balance_point_f": balance_point_f(heating_btuh, heating_design_f, rated, retention_at_5f),
        "backup_heat_kw": round(backup_kw, 1),
        "assumed_retention_at_5f": retention_at_5f,
        "notes": notes,
    }


def size_home(home: Home, city: str | None = None, heating_design_f: float | None = None,
              cooling_design_f: float | None = None, retention_at_5f: float = 0.70) -> dict:
    """End-to-end: design conditions -> loads -> recommendation."""
    if city:
        climate = design_conditions(city)
    elif heating_design_f is not None and cooling_design_f is not None:
        climate = {"city": "custom", "heating_design_f": heating_design_f,
                   "cooling_design_f": cooling_design_f, "climate_zone": "unknown"}
    else:
        raise ValueError("Provide a city or both design temperatures.")

    loads = calculate_loads(home, climate["heating_design_f"], climate["cooling_design_f"])
    rec = recommend(loads["heating_btuh"], loads["cooling_btuh"],
                    climate["heating_design_f"], retention_at_5f)
    return {
        "home": asdict(home),
        "climate": climate,
        "loads": loads,
        "recommendation": rec,
        "disclaimer": "Educational estimate, not a Manual J. Confirm with a licensed contractor.",
    }