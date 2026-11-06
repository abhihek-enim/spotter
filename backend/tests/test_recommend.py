from trips.geo import METERS_PER_MILE
from trips.recommend import recommend, summarize
from trips.risk import Risk

MILE = METERS_PER_MILE
L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


def route(route_id, hours, *segments):
    """segments: (level, miles) pairs."""
    total = sum(miles for _, miles in segments) * MILE
    return summarize(route_id, total, hours * 3600, [(lvl, miles * MILE) for lvl, miles in segments])


def test_summary_adds_miles_and_weights_the_average_by_miles():
    s = route("A", 10, (L, 75), (S, 25))
    assert s.miles(L) == 75
    assert s.miles(S) == 25
    assert s.average_risk == 0.75  # (0 * 75 + 3 * 25) / 100
    assert s.worst == S


def test_fewest_severe_miles_wins_even_if_slower():
    fast = route("A", 9, (L, 80), (S, 20))
    slow = route("B", 11, (L, 70), (H, 30))
    rec = recommend([fast, slow])
    assert rec.route_id == "B"
    assert rec.reason == "Fewest Severe miles (0 vs 20)."


def test_then_fewest_high_miles():
    a = route("A", 9, (L, 80), (H, 20))
    b = route("B", 10, (L, 90), (H, 10))
    assert recommend([a, b]).route_id == "B"


def test_then_lowest_average_risk():
    a = route("A", 9, (L, 50), (M, 50))
    b = route("B", 10, (L, 90), (M, 10))
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert rec.reason == "Lowest average risk (0.10 vs 0.50)."


def test_then_shortest_time():
    a = route("A", 10, (L, 100))
    b = route("B", 9, (L, 120))
    rec = recommend([a, b])
    assert rec.route_id == "B"
    assert rec.reason == "Same weather risk; fastest (9 h 00 min vs 10 h 00 min)."


def test_any_no_travel_ranks_below_routes_without_it():
    # A has one No Travel mile but otherwise looks better than B.
    a = route("A", 8, (L, 99), (N, 1))
    b = route("B", 12, (L, 50), (S, 50))
    rec = recommend([a, b])
    assert rec.ranking == ["B", "A"]
    assert rec.reason == "Only route B avoids No Travel conditions."
    assert not rec.all_routes_have_no_travel


def test_when_all_have_no_travel_fewest_no_travel_miles_wins_and_flags_it():
    a = route("A", 8, (L, 90), (N, 10))
    b = route("B", 9, (L, 95), (N, 5))
    c = route("C", 7, (L, 80), (N, 20))
    rec = recommend([a, b, c])
    assert rec.ranking == ["B", "A", "C"]
    assert rec.all_routes_have_no_travel
    assert rec.reason == "Fewest No Travel miles (5 vs 10)."


def test_tiny_differences_count_as_ties():
    a = route("A", 10, (L, 99.99), (S, 10.01))
    b = route("B", 9, (L, 100), (S, 10.0))
    assert recommend([a, b]).route_id == "B"  # 10.01 and 10.0 round to the same 0.1 mile


def test_single_route():
    rec = recommend([route("A", 5, (L, 100))])
    assert rec.route_id == "A"
    assert rec.reason == "Only one route was found."
