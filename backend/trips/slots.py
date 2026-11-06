"""Which forecast hour applies at a given moment.

Open-Meteo gives one row per hour. Rain, showers and snowfall in a row are totals for
the hour BEFORE the row's timestamp, and gusts are the maximum over that hour.
So the row stamped 15:00 describes 14:00-15:00, and anything that happens between
14:00 and 15:00 uses that row. In short: use the row stamped at the next full hour.

"Slot k" is the k-th hour of the trip: slot 0 is the hour that contains the departure.
The heatmap slider moves through slots 0..48, and the truck at departure + k hours
is always inside slot k.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

HOUR = timedelta(hours=1)


def ceil_hour(t: datetime) -> datetime:
    """Round up to the next full hour (a full hour stays as it is)."""
    floor = t.replace(minute=0, second=0, microsecond=0)
    return floor if floor == t else floor + HOUR


def first_slot_stamp(departure: datetime) -> datetime:
    """Timestamp of the forecast row for slot 0, in UTC."""
    return ceil_hour(departure.astimezone(UTC))


def slot_for(departure: datetime, moment: datetime) -> int:
    """Index of the forecast hour that contains `moment`, counted from the departure's hour."""
    delta = ceil_hour(moment.astimezone(UTC)) - first_slot_stamp(departure)
    return int(delta / HOUR)
