import pytest

from trips.risk import (
    Risk,
    Weather,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
    load_rule,
)

L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


@pytest.mark.parametrize(
    ("mph", "expected"),
    [
        (0, L),
        (24.9, L),
        (25, M),
        (34, M),
        (34.9, M),  # 25-34
        (35, H),
        (44.9, H),  # 35-44; a shared boundary goes to the higher band
        (45, S),
        (54.9, S),  # 45-54
        (55, N),
        (80, N),  # >= 55
    ],
)
def test_wind_bands(mph, expected):
    assert classify_wind(mph) == expected


@pytest.mark.parametrize(
    ("rate", "expected"),
    [
        (0, L),
        (0.099, L),
        (0.10, M),
        (0.249, M),
        (0.25, H),
        (0.499, H),  # 0.25 is in "0.10-0.25" and "0.25-0.50": higher band wins
        (0.50, S),
        (1.00, S),  # No Travel is "> 1.00", so 1.00 itself is Severe
        (1.001, N),
        (2.5, N),
    ],
)
def test_rain_bands(rate, expected):
    assert classify_rain(rate) == expected


@pytest.mark.parametrize(
    ("rate", "expected"),
    [
        (0, L),
        (0.49, L),
        (0.5, M),
        (0.99, M),
        (1.0, H),
        (1.99, H),
        (2.0, S),
        (3.0, S),  # No Travel is "> 3.0"
        (3.01, N),
    ],
)
def test_snow_bands(rate, expected):
    assert classify_snow(rate) == expected


@pytest.mark.parametrize(
    ("mph", "load", "expected"),
    [
        (60, 0, N),  # >= 55 mph: No Travel for any load
        (55, 10_000, N),
        (50, 30_000, None),  # exactly 30,000 lb is not "more than 30,000"
        (50, 30_001, N),  # 45-54 mph + > 30,000 lb
        (45, 45_000, N),
        (44.9, 45_000, S),  # 35-44 mph + > 40,000 lb
        (35, 40_001, S),
        (40, 40_000, None),  # exactly 40,000 lb is not "more than 40,000"
        (34.9, 80_000, None),  # below 35 mph no load rule applies
    ],
)
def test_load_rules(mph, load, expected):
    assert load_rule(mph, load) == expected


def calm(**overrides):
    values = {"wind_mph": 5, "gust_mph": 10, "rain_in_hr": 0, "snow_in_hr": 0} | overrides
    return Weather(**values)


def test_assess_takes_the_worst_condition():
    result = assess(calm(wind_mph=30, rain_in_hr=0.6), load_lb=10_000)
    assert result.wind == M
    assert result.rain == S
    assert result.level == S
    assert result.reason == "Rain 0.60 in/hr"


def test_load_rule_raises_wind_level_and_says_so():
    result = assess(calm(wind_mph=47), load_lb=35_000)
    assert result.level == N
    assert result.load_rule_applied
    assert result.reason == "Wind 47 mph with a 35,000 lb load"


def test_light_load_in_the_same_wind_stays_severe():
    result = assess(calm(wind_mph=47), load_lb=20_000)
    assert result.level == S
    assert not result.load_rule_applied


def test_gusts_are_not_classified():
    assert assess(calm(gust_mph=70), load_lb=0).level == L


def test_calm_weather_reason():
    assert assess(calm(), load_lb=0).reason == "Calm: all conditions Low"


def test_two_causes_at_the_same_level():
    result = assess(calm(wind_mph=36, snow_in_hr=1.2), load_lb=0)
    assert result.level == H
    assert result.reason == "Wind 36 mph and snow 1.2 in/hr"
