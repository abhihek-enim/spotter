# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route. Enter an origin, a destination, a departure time and the load weight. The app:

1. gets up to 3 route options from a routing API;
2. places weather checkpoints every 10, 25 or 50 miles along each route;
3. reads the forecast at each checkpoint **for the hour the truck gets there**;
4. classifies each checkpoint with the brief's risk table and load rules;
5. recommends a route;
6. shows everything on a map, with a weather heatmap along the corridor and a 0–48 hour forecast slider.

- **Live app:** https://weather-truck-routing-omega.vercel.app
- **Walkthrough (Loom):** _link added after recording_

---

## How a trip is computed

```
origin, destination, departure, load (lb), spacing (10/25/50 mi)
        │
        ▼
Routing API ──► up to 3 routes, each with distance and driving time at every point of the line
        │
        ▼
Checkpoints every N miles (+ origin and destination)
   ETA = departure + driving time to that point (interpolated along the route)
        │
        ▼
Open-Meteo hourly forecast, one batched call for all checkpoints
   weather at a checkpoint = the forecast hour that contains its ETA
        │
        ▼
Risk per checkpoint = worst of wind (after load rules), rain, snow
        │
        ▼
Per route: miles at each risk level, mile-weighted average risk, travel time
        │
        ▼
Recommendation (ranking rules below), with a one-line reason
```

The heatmap is a second request, made right after the routes come back. Its job is a grid of cells around all routes, with weather and risk for 49 hourly slots.

- It reuses the routes cached by the first request.
- The page receives all 49 hours at once.
- Moving the slider only changes which hour the map layer reads. There is no refetch and no new data sent to the map.

## Interpretation of the brief (decisions)

The brief leaves a few points open. These are the decisions taken, and where they live in the code.

| # | Question | Decision | Code |
|---|---|---|---|
| 1 | "Sample weather every 10 / 25 / 50 miles" | **A spacing the user picks.** The form has a 10 / 25 / 50 mi switch, default 25. Each trip uses one set of checkpoints. | `sampling.checkpoint_distances` |
| 2 | A value on a shared boundary (rain 0.25 in/hr is in both "0.10–0.25" and "0.25–0.50") | **It goes to the higher band.** See the boundary notes below the table. | `risk.classify_*` |
| 3 | How No Travel ranks | **Any route with No Travel miles ranks below every route without them.** See the ranking rules below. | `recommend.ranking_key` |
| 4 | How many miles a checkpoint stands for | **Each mile takes the risk of its nearest checkpoint.** See the worked example below. | `sampling.coverage` |

Notes on decision 2:
- Each band's lower number counts, so rain 0.25 in/hr is High and wind 35 mph is High.
- No Travel for rain and snow says "more than", so rain at exactly 1.00 in/hr and snow at exactly 3.0 in/hr stay Severe.

Worked example for decision 4: with 25 mi spacing, the checkpoint at mile 50 covers miles 37.5–62.5. The origin and destination cover half a gap each, and the totals add up to the route length.

Other choices:

- **Wind:** sustained wind speed (10 m) is classified. Gusts are shown in the popup but not classified.
- **Rain:** Open-Meteo `rain` + `showers`. Open-Meteo reports large-scale rain and convective showers separately; rain alone would miss thunderstorms.
- **Snow:** Open-Meteo `snowfall`, in inches of snow per hour (not water equivalent).
- **Forecast hour:** Open-Meteo's rain, snow and gust values are totals or maxima over the hour *before* each timestamp. So a checkpoint reached at 14:20 uses the row stamped 15:00, which covers 14:00–15:00.
- **Checkpoint risk:** the worst of wind (after the load rules), rain and snow.
- **Load rules:** apply to wind.
  - ≥ 55 mph is No Travel at any load.
  - 45–54 mph with more than 30,000 lb is No Travel.
  - 35–44 mph with more than 40,000 lb is Severe.
  - "More than" is strict: exactly 30,000 lb does not trigger the rule.
- **Average risk:** levels are scored Low 0, Moderate 1, High 2, Severe 3, No Travel 4, and averaged weighted by miles.
- **Ties:**
  - Miles are compared to 0.1 mi and average risk to 0.01, so rounding noise in the geometry can't pick a route.
  - Real ties fall through to travel time.
- **Departure:**
  - Entered in the viewer's own time zone, which the form names.
  - Allowed from 1 hour ago to 7 days ahead. Open-Meteo forecasts 16 days, and long trips plus the 48 h slider need the room.
- **Slider:** hour 0 is the hour that contains the departure. The truck marker shows where the selected route's truck is at departure + k hours, and checkpoints reached during that hour are drawn larger.
- **Places:** search covers the US and Canada, because the units are miles, lb and in/hr.
- **Rest breaks:** ETAs are driving time only. Hours-of-service rest breaks are not added (see Limitations).
- **Truck speed:** ETAs assume a truck **governed at 65 mph** (TomTom `vehicleMaxSpeed=105` km/h).
  - Without a top speed, TomTom's truck mode came out as fast as its car mode: Dallas → Chicago took 13.5 h for the truck and 13.6 h for the car, about 72 mph on average.
  - Most fleets fit speed limiters, and 65 mph is the most common setting in ATRI's fleet surveys. There is no federal mandate; a proposed one was withdrawn in July 2025.
  - TomTom still applies lower speed limits and traffic below the cap, so it only matters on fast highways. With the cap, Dallas → Chicago takes 15.2 h, which moves later checkpoints by 1–2 forecast hours.

## Ranking rules (recommendation)

Smaller is better, compared in this order (`recommend.ranking_key`):

1. has any No Travel miles (routes without come first)
2. No Travel miles
3. Severe miles
4. High miles
5. average risk
6. travel time

The reason shown in the app names the first rule that separates the winner from the runner-up, for example "Fewest Severe miles (0 vs 20)". If every route has No Travel miles, the app says so and suggests another departure time.

## APIs

| Need | Service | Key | Why |
|---|---|---|---|
| Routes | **TomTom Routing API** (`travelMode=truck`) | free key, no card | Real truck routing. Up to 5 alternatives (we ask for 2 + the best). `departAt` for time-aware travel times. `progress` gives distance and time at route points, which is how ETAs are exact. Checked with real replies on 6 Nov: 3 routes on every test trip. |
| Routes, no key | **OSRM demo server** | none | Lets the app run with zero setup. Car profile and often only 2 routes. The app says so in a note. |
| Place search | TomTom Search (with key), Open-Meteo Geocoding (without) | — | Called through Django, so the key never reaches the browser. |
| Weather | **Open-Meteo** forecast | none | Hourly wind, gusts, rain, showers and snowfall in mph and inches. Many points per call. 16-day range. |
| Map tiles | **OpenFreeMap** (MapLibre GL) | none | Free vector tiles with no key or usage limits. |

Not chosen:
- **OpenRouteService:** its public API allows alternative routes only up to about 100 km.
- **OSRM as the main router:** it has no truck profile, and in tests it returned only 2 routes for Dallas → Chicago and Denver → Salt Lake City.

## Performance

**Map:**
- Routes, risk-coloured route segments, checkpoints and heatmap cells are GPU map layers, not one HTML marker per point.
- Only the start and end pins and the truck are HTML markers.

**Heatmap:**
- Every cell carries all 49 hourly values as feature properties (`r0..r48`, `w0..w48`, …).
- The slider swaps the property name in the layer's paint expression.
- Measured in development mode: a slider step takes 4–6 ms. The side panels are memoised, so they don't re-render on slider moves.

**Size:**
- A Dallas → Chicago trip is about 24 KB gzipped for routes and 19 KB for the heatmap.
- Route lines are simplified (Douglas-Peucker, 25 m) for display only; every calculation uses the full line.

**Caching** (in-process, one server process):

| What | How long | Shared by |
|---|---|---|
| Weather | 1 hour per point (rounded to ~1 km) and per day-long window | overlapping trips |
| Routes | 10 minutes | the trip request and the heatmap request |
| Place searches | 1 day | all users |

**Call budget:**
- The heatmap grid sits on a fixed lat/lon lattice and grows coarser on long trips, up to 200 cells. Dallas → Chicago uses 0.4° cells (about 44 km); shorter trips get finer cells.
- Open-Meteo's free plan counts **every point as one call** and allows 600 calls a minute. A trip's checkpoints use at most 350 new points, and its heatmap at most 200, so one trip always fits in a minute. On very long trips at 10-mile spacing, nearby checkpoints share one forecast point, and the app shows a note saying so.
- Weather is fetched in batches of 50 points, 3 at a time. In tests, 50 points answered in about 1.5 s, and Open-Meteo dropped connections at 8 parallel requests.

**Free-quota protection:**
- Rate limits of 60 trip calls an hour and 120 place searches a minute per client.
- If Open-Meteo's per-minute limit is hit anyway (several trips in one minute), the app says so plainly instead of retrying, and the heatmap gets a Retry button.
- Slow outside services get a fixed time limit, then one retry, then a clear message: 15 s for weather and place search, 30 s for TomTom routing (a 1,000-mile truck route with alternatives measured up to 17 s). There is never a silent endless wait, and after 10 s the page explains that long trips can take up to a minute the first time.

## Project layout

```
backend/                      Django + Django REST Framework
  config/                     settings (all from environment variables), urls
  trips/
    risk.py                   risk table + load rules (pure functions)
    sampling.py               route profile, checkpoints, ETA, miles per checkpoint
    slots.py                  which forecast hour applies at a moment
    recommend.py              route summaries + ranking + reason
    corridor.py               heatmap grid around the routes
    display.py                simplified lines and risk-coloured segments for the map
    service.py                plan_trip() and corridor_heatmap(): the pipeline
    providers/                the only code that calls other services
      tomtom.py  osrm.py  open_meteo.py  http.py (timeouts, retries, safe errors)
    serializers.py  views.py  urls.py
  tests/                      pytest: rules, boundaries, sampling, ranking, providers, API
frontend/                     React + TypeScript + Vite, MapLibre via react-map-gl
  src/components/             TripForm, PlaceInput, RouteCards, CheckpointTable, MapView, TimeControls
  src/lib/                    heatmap layer building, risk colours, truck position, formatting (+ tests)
```

## Run locally

You need Python 3.12+ with [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
# API on http://127.0.0.1:8000
cd backend
cp .env.example .env          # optional: add TOMTOM_API_KEY for truck routing
uv sync
uv run python manage.py runserver

# Web app on http://localhost:5173 (proxies /api to the API)
cd frontend
npm install
npm run dev
```

Without `TOMTOM_API_KEY` the app uses the OSRM demo server and Open-Meteo place search, so it works with no keys at all.

### Tests

```bash
cd backend && uv run pytest && uv run ruff check .
cd frontend && npm test && npm run build
```

The backend tests run offline. TomTom and Open-Meteo replies are either recorded or faked, so the tests never need a key or the network. They cover:
- every boundary in the risk table and the load rules;
- checkpoint placement, ETA and miles per checkpoint;
- the ranking rules, including No Travel and ties;
- forecast-hour selection across time zones;
- parsing of the TomTom, OSRM and Open-Meteo responses, including a recorded real TomTom reply;
- the weather budget: when nearby checkpoints share a forecast point, and the per-minute limit message;
- full trips through the API, including "a storm on the fast route sends the truck the other way".

## Deploy

| Part | Where | How |
|---|---|---|
| API | AWS EC2 (Ubuntu), behind Nginx with a Let's Encrypt certificate | `deploy/ec2/` |
| Web app | Vercel | root directory `frontend/`; `vercel.json` forwards `/api/*` to the API host |

The browser only ever talks to the Vercel address. Vercel forwards `/api/*` to the API over HTTPS, so there is no CORS setup and the TomTom key stays on the server.

On the server:

- **`spotter-api.service`** (systemd) runs gunicorn on `127.0.0.1:8001`. It runs as its own unprivileged user, with a 400 MB memory cap, because the machine runs other services.
- **`nginx-spotter.conf`** serves only `/api/`. certbot adds the HTTPS block and the redirect.
- **`update.sh`** pulls the latest commit, installs requirements and restarts the service.

Settings live in a root-owned `/etc/spotter/env` (never committed):

| Variable | Value |
|---|---|
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | a long random string |
| `DJANGO_ALLOWED_HOSTS` | the API host name |
| `TOMTOM_API_KEY` | the TomTom key |

## Limitations and next steps

- **Rest breaks:** ETAs are driving time. Hours-of-service rest breaks (30 min after 8 h of driving, 10 h off after 11 h) would shift ETAs on long trips; this is the next thing to add.
- **Load weight:** used by the risk rules only. Sending it to TomTom as vehicle weight would also avoid weight-restricted roads, but needs the truck's empty weight as well.
- **Weather detail:** forecasts are per model grid cell (1.5–13 km), and checkpoints are rounded to about 1 km. Very local conditions such as bridges and mountain passes are not modelled.
- **Truck speed:** one 65 mph cap for every truck. A form field for the truck's own governed speed would be easy to add.
- **Wind:** sustained wind is classified. A stricter mode could classify gusts.
- **Cache:** it lives in one server process. More servers would need a shared cache such as Redis.
