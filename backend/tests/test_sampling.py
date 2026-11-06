import pytest

from trips.geo import METERS_PER_MILE, cumulative_distances, haversine_m, simplify
from trips.sampling import (
    checkpoint_distances,
    coverage,
    place_checkpoints,
    profile_from_anchors,
    profile_from_segments,
)

MILE = METERS_PER_MILE


def straight_line(n=11, lat=35.0, lon0=-100.0, lon1=-99.0):
    """A route due east along one latitude, with n evenly spaced points."""
    return [(lat, lon0 + (lon1 - lon0) * k / (n - 1)) for k in range(n)]


def test_haversine_one_degree_of_latitude():
    assert haversine_m((35.0, -100.0), (36.0, -100.0)) == pytest.approx(111_195, rel=1e-3)


def test_checkpoint_distances_include_origin_and_destination():
    assert checkpoint_distances(60 * MILE, 25 * MILE) == pytest.approx([0, 25 * MILE, 50 * MILE, 60 * MILE])


def test_destination_is_not_sampled_twice():
    assert checkpoint_distances(50 * MILE, 25 * MILE) == pytest.approx([0, 25 * MILE, 50 * MILE])


def test_short_trip_has_origin_and_destination_only():
    assert checkpoint_distances(5 * MILE, 10 * MILE) == pytest.approx([0, 5 * MILE])


def test_coverage_is_nearest_checkpoint_and_adds_up():
    distances = [0, 25, 50, 60]
    assert coverage(distances) == [12.5, 25, 17.5, 5]
    assert sum(coverage(distances)) == 60


def test_profile_from_segments():
    points = straight_line(3)
    profile = profile_from_segments(points, [100, 300], [10, 20])
    assert profile.cum_m == [0, 100, 400]
    assert profile.cum_s == [0, 10, 30]
    assert profile.time_at_distance(250) == pytest.approx(20)
    assert profile.distance_at_time(20) == pytest.approx(250)


def test_profile_from_sparse_anchors_spreads_time_by_distance():
    points = straight_line(11)
    geo = cumulative_distances(points)
    # The API gave time only at the first, middle and last point; the second half is slower.
    profile = profile_from_anchors(points, [(0, 0, 0), (5, geo[5], 1000), (10, geo[10], 3000)])
    assert profile.cum_s[5] == pytest.approx(1000)
    assert profile.cum_s[2] == pytest.approx(400)
    assert profile.cum_s[8] == pytest.approx(2200)
    assert profile.duration_s == 3000


def test_profile_from_anchors_needs_both_ends():
    with pytest.raises(ValueError):
        profile_from_anchors(straight_line(3), [(0, 0, 0), (1, 10, 1)])


def test_place_checkpoints_gives_position_eta_and_coverage():
    points = straight_line(11)
    geo = cumulative_distances(points)
    # Constant speed: 1 meter per second.
    profile = profile_from_anchors(points, [(0, 0, 0), (10, geo[10], geo[10])])
    spacing = 10 * MILE
    cps = place_checkpoints(profile, spacing)
    total = profile.distance_m
    assert [round(c.distance_m) for c in cps[:3]] == [0, round(spacing), round(2 * spacing)]
    assert cps[-1].distance_m == pytest.approx(total)
    assert cps[1].time_s == pytest.approx(spacing)
    assert cps[1].lat == pytest.approx(35.0)
    assert sum(c.covers_m for c in cps) == pytest.approx(total)
    assert cps[0].lon == pytest.approx(-100.0)
    assert cps[-1].lon == pytest.approx(-99.0)


def test_simplify_drops_points_on_a_straight_line():
    points = straight_line(50)
    assert simplify(points, tolerance_m=5) == [0, 49]


def test_simplify_keeps_a_corner():
    points = [(35.0, -100.0), (35.0, -99.5), (35.0, -99.0), (35.5, -99.0), (36.0, -99.0)]
    assert simplify(points, tolerance_m=50) == [0, 2, 4]
