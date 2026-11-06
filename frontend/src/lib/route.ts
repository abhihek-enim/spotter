import type { LngLat, Route } from "../api";

/** Where the truck is `seconds` after departure, by interpolating the route's timed line. */
export function positionAt(route: Route, seconds: number): { at: LngLat; arrived: boolean } {
  const times = route.line_times_s;
  const line = route.line;
  if (seconds <= 0) return { at: line[0], arrived: false };
  if (seconds >= times[times.length - 1]) return { at: line[line.length - 1], arrived: true };
  let hi = times.findIndex((t) => t >= seconds);
  if (hi <= 0) hi = 1;
  const lo = hi - 1;
  const span = times[hi] - times[lo];
  const f = span > 0 ? (seconds - times[lo]) / span : 0;
  return {
    at: [line[lo][0] + (line[hi][0] - line[lo][0]) * f, line[lo][1] + (line[hi][1] - line[lo][1]) * f],
    arrived: false,
  };
}

/** Bounding box [[west, south], [east, north]] of all routes. */
export function boundsOf(routes: Route[]): [LngLat, LngLat] {
  let west = 180, south = 90, east = -180, north = -90;
  for (const route of routes) {
    for (const [lon, lat] of route.line) {
      west = Math.min(west, lon);
      east = Math.max(east, lon);
      south = Math.min(south, lat);
      north = Math.max(north, lat);
    }
  }
  return [
    [west, south],
    [east, north],
  ];
}

/** A point halfway along a route, for its letter label. */
export function midpoint(route: Route): LngLat {
  return route.line[Math.floor(route.line.length / 2)];
}
