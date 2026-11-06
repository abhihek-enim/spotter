from datetime import UTC, datetime, timedelta, timezone

from trips.corridor import corridor_cells
from trips.slots import ceil_hour, first_slot_stamp, slot_for

IST = timezone(timedelta(hours=5, minutes=30))


def test_ceil_hour():
    assert ceil_hour(datetime(2026, 11, 4, 14, 20, tzinfo=UTC)) == datetime(2026, 11, 4, 15, tzinfo=UTC)
    assert ceil_hour(datetime(2026, 11, 4, 14, 0, tzinfo=UTC)) == datetime(2026, 11, 4, 14, tzinfo=UTC)


def test_slot_zero_is_the_hour_containing_departure():
    dep = datetime(2026, 11, 4, 14, 20, tzinfo=UTC)
    assert first_slot_stamp(dep) == datetime(2026, 11, 4, 15, tzinfo=UTC)
    assert slot_for(dep, dep) == 0
    assert slot_for(dep, datetime(2026, 11, 4, 14, 59, tzinfo=UTC)) == 0
    assert slot_for(dep, datetime(2026, 11, 4, 15, 1, tzinfo=UTC)) == 1


def test_truck_k_hours_after_departure_is_in_slot_k():
    dep = datetime(2026, 11, 4, 14, 20, tzinfo=UTC)
    for k in range(49):
        assert slot_for(dep, dep + timedelta(hours=k)) == k


def test_slots_work_across_time_zones():
    dep_ist = datetime(2026, 11, 4, 19, 50, tzinfo=IST)  # = 14:20 UTC
    assert first_slot_stamp(dep_ist) == datetime(2026, 11, 4, 15, tzinfo=UTC)


def test_corridor_covers_the_route_on_a_fixed_lattice():
    route = [(35.0, -100.0), (35.0, -99.0)]  # about 91 km
    corridor = corridor_cells([route], buffer_m=20_000, max_cells=500)
    assert corridor.step_deg == 0.1
    lats = {lat for lat, _ in corridor.cells}
    lons = {lon for _, lon in corridor.cells}
    assert 35.0 in lats and -100.0 in lons and -99.0 in lons
    # Every cell center is a multiple of the step.
    assert all(abs(lat * 10 - round(lat * 10)) < 1e-6 for lat in lats)
    # The band is about 2 x 20 km wide: 0.1 deg of latitude is about 11 km.
    assert max(lats) - min(lats) <= 0.4


def test_long_trips_get_a_coarser_grid_within_the_cell_limit():
    route = [(32.8, -96.8), (41.9, -87.6)]  # Dallas to Chicago, straight line
    corridor = corridor_cells([route], buffer_m=40_000, max_cells=300)
    assert corridor.step_deg > 0.1
    assert len(corridor.cells) <= 300
