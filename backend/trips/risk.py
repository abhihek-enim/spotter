"""Weather risk rules from the brief.

Every function here is pure: numbers in, a risk level out. No network, no Django.

Boundary rule (decision 2 in the README): a value that sits on a shared boundary
goes to the HIGHER band. So each band's lower number is inclusive:
rain 0.25 in/hr is High, wind 35 mph is High. The "No Travel" column for rain and
snow says "> 1.00" and "> 3.0", so exactly 1.00 in/hr rain and 3.0 in/hr snow stay Severe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Risk(IntEnum):
    """Risk levels. The number is the score used for "average risk"."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


def classify_wind(mph: float) -> Risk:
    """Wind table: Low < 25, Moderate 25-34, High 35-44, Severe 45-54, No Travel >= 55 mph."""
    if mph >= 55:
        return Risk.NO_TRAVEL
    if mph >= 45:
        return Risk.SEVERE
    if mph >= 35:
        return Risk.HIGH
    if mph >= 25:
        return Risk.MODERATE
    return Risk.LOW


def classify_rain(inches_per_hour: float) -> Risk:
    """Rain table: Low < 0.10, Moderate 0.10-0.25, High 0.25-0.50, Severe 0.50-1.00, No Travel > 1.00."""
    if inches_per_hour > 1.00:
        return Risk.NO_TRAVEL
    if inches_per_hour >= 0.50:
        return Risk.SEVERE
    if inches_per_hour >= 0.25:
        return Risk.HIGH
    if inches_per_hour >= 0.10:
        return Risk.MODERATE
    return Risk.LOW


def classify_snow(inches_per_hour: float) -> Risk:
    """Snow table: Low < 0.5, Moderate 0.5-1.0, High 1.0-2.0, Severe 2.0-3.0, No Travel > 3.0."""
    if inches_per_hour > 3.0:
        return Risk.NO_TRAVEL
    if inches_per_hour >= 2.0:
        return Risk.SEVERE
    if inches_per_hour >= 1.0:
        return Risk.HIGH
    if inches_per_hour >= 0.5:
        return Risk.MODERATE
    return Risk.LOW


def load_rule(wind_mph: float, load_lb: float) -> Risk | None:
    """Load rules: heavier loads are less stable in strong wind.

    - >= 55 mph: No Travel for any load (already in the wind table).
    - 45-54 mph with more than 30,000 lb: No Travel.
    - 35-44 mph with more than 40,000 lb: Severe.

    Returns the level the rule forces, or None when no rule applies.
    """
    if wind_mph >= 55:
        return Risk.NO_TRAVEL
    if wind_mph >= 45 and load_lb > 30_000:
        return Risk.NO_TRAVEL
    if wind_mph >= 35 and load_lb > 40_000:
        return Risk.SEVERE
    return None


def wind_level(mph: float, load_lb: float) -> Risk:
    """Wind level after the load rules (a rule can only raise the level)."""
    forced = load_rule(mph, load_lb)
    from_table = classify_wind(mph)
    return max(from_table, forced) if forced is not None else from_table


@dataclass(frozen=True)
class Weather:
    """Weather for one place and one forecast hour, in the brief's units."""

    wind_mph: float
    gust_mph: float
    rain_in_hr: float  # rain + showers over the hour
    snow_in_hr: float  # snowfall (inches of snow, not water) over the hour


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk  # after the load rules
    rain: Risk
    snow: Risk
    load_rule_applied: bool
    reason: str


def assess(weather: Weather, load_lb: float) -> Assessment:
    """Risk at one checkpoint: the worst of wind (after load rules), rain and snow.

    Wind uses the sustained speed (decision in the README); gusts are shown, not classified.
    """
    wind = wind_level(weather.wind_mph, load_lb)
    rain = classify_rain(weather.rain_in_hr)
    snow = classify_snow(weather.snow_in_hr)
    level = max(wind, rain, snow)
    load_rule_applied = wind > classify_wind(weather.wind_mph)
    return Assessment(
        level=level,
        wind=wind,
        rain=rain,
        snow=snow,
        load_rule_applied=load_rule_applied,
        reason=_reason(weather, load_lb, level, wind, rain, snow, load_rule_applied),
    )


def level_only(weather: Weather, load_lb: float) -> Risk:
    """Same level as assess(), without the explanation. Used for the many heatmap cells."""
    return max(
        wind_level(weather.wind_mph, load_lb),
        classify_rain(weather.rain_in_hr),
        classify_snow(weather.snow_in_hr),
    )


def _reason(
    weather: Weather,
    load_lb: float,
    level: Risk,
    wind: Risk,
    rain: Risk,
    snow: Risk,
    load_rule_applied: bool,
) -> str:
    """One short sentence naming what set the level, e.g. 'Wind 47 mph with a 35,000 lb load'."""
    if level == Risk.LOW:
        return "Calm: all conditions Low"
    causes = []
    if wind == level:
        text = f"wind {weather.wind_mph:.0f} mph"
        if load_rule_applied:
            text += f" with a {load_lb:,.0f} lb load"
        causes.append(text)
    if rain == level:
        causes.append(f"rain {weather.rain_in_hr:.2f} in/hr")
    if snow == level:
        causes.append(f"snow {weather.snow_in_hr:.1f} in/hr")
    sentence = " and ".join(causes)
    return sentence[0].upper() + sentence[1:]
