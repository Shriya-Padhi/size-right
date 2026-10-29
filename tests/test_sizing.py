import sys
from pathlib import Path

import pytest

# Let tests import sizing.py from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sizing import (  # noqa: E402
    Home,
    calculate_loads,
    capacity_at,
    design_conditions,
    recommend,
    size_home,
)


def test_city_lookup_with_and_without_state():
    assert design_conditions("Minneapolis, MN")["heating_design_f"] == -11
    assert design_conditions("minneapolis")["city"] == "Minneapolis, MN"


def test_unknown_city_suggests_matches():
    with pytest.raises(ValueError, match="Did you mean"):
        design_conditions("Minneapolos")


def test_colder_climate_needs_more_heat():
    home = Home(floor_area_ft2=1800)
    cold = calculate_loads(home, -11, 89)["heating_btuh"]
    mild = calculate_loads(home, 25, 92)["heating_btuh"]
    assert cold > mild > 0


def test_better_envelope_lowers_load():
    poor = calculate_loads(Home(1800, insulation="poor", air_tightness="leaky"), 0, 90)
    good = calculate_loads(Home(1800, insulation="good", air_tightness="tight"), 0, 90)
    assert good["heating_btuh"] < poor["heating_btuh"] / 2


def test_breakdown_sums_to_total():
    loads = calculate_loads(Home(2000, stories=2), 10, 88)
    assert abs(sum(loads["heating_breakdown_btuh"].values()) - loads["heating_btuh"]) <= 5


def test_capacity_curve_points():
    assert capacity_at(47, 36000, 0.7) == 36000
    assert capacity_at(5, 36000, 0.7) == pytest.approx(25200)
    assert capacity_at(60, 36000, 0.7) == 36000
    assert capacity_at(-200, 36000, 0.7) == 0


def test_recommendation_covers_load_or_reports_backup():
    rec = recommend(30000, 20000, heating_design_f=5)
    assert rec["sizing_basis"] == "heating"
    assert rec["capacity_at_design_btuh"] >= 30000 or rec["backup_heat_kw"] > 0


def test_cooling_led_in_hot_climate():
    result = size_home(Home(1800), city="Phoenix, AZ")
    assert result["recommendation"]["sizing_basis"] == "cooling"


def test_invalid_input_rejected():
    with pytest.raises(ValueError):
        calculate_loads(Home(50), 0, 90)
    with pytest.raises(ValueError):
        size_home(Home(1500))