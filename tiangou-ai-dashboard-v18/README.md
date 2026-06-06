
# Tiangou AI Dashboard v10

React/Vite demonstrator for a physics-informed Hong Kong grid-stability decision-support platform.

## v10 consolidated update

### Landing page
- Fixed-height KPI rows with centred icons.
- Stable number / unit alignment so values remain readable.
- Expanded frequency, inertia, demand and production plotting area.
- Larger axis labels, legends and annotations.
- Real Hong Kong OpenStreetMap tile mosaic beneath the topology overlay.
- Non-overlapping node label boxes with leader lines.
- Icons added to the four bottom KPI boxes.
- Live, buffering, scenario and validated states keep the same layout.

### Subpages
- Larger fonts and icons.
- Minimal hover animations for cards and icons.
- All subpages are visible directly in the desktop top menu.

### Resource Mix
- Dynamic donut chart for synchronous generation, inverter-based generation and imports.
- New weather and climate intelligence section:
  - Current Hong Kong conditions from Open-Meteo.
  - 12-hour wind, cloud and precipitation forecast.
  - Solar-disruption and wind-disruption heuristic indicators.
  - Hong Kong Observatory warning summary.
  - Automatic refresh every 10 minutes.
  - Manual refresh control.
  - Fallback demonstrator values if weather APIs are unavailable.

## External data sources
- Forecast and current model conditions: Open-Meteo Forecast API.
- Official weather warnings: Hong Kong Observatory Open Data API.
- Map background: OpenStreetMap tiles.

## Run locally

```powershell
npm install
npm run dev
```

Open:

```text
http://localhost:5173/
```

## Notes
- The weather disruption scores are demonstrator heuristics. They are not utility operating limits.
- The OpenStreetMap background and weather data require an internet connection. Grid overlays and scenario logic continue to work offline.


## v11 layout correction

- Removed the scenario dropdown from the top-right header. Scenario control remains on the Overview page.
- Increased the left KPI column width and fixed the height of every KPI row.
- Centred all KPI icons and protected numeric values from overlapping their units.
- Reallocated space from topology to the plotting area.
- Moved the topology table below the map on wide screens.
- Replaced the ineffective map tile background with a clear Hong Kong base map loaded from Wikimedia Commons.
- Increased live-chart and scenario-chart height, line width, legend size, axis-label size and annotation size.

## v12 operator-grade architecture update

### PINN prediction and simulation timeline
- Charts now include a 20-second forward frequency forecast computed by the PINN layer.
- Extended digital-twin scenarios run for 110 simulated seconds.
- The comparison chart marks the AI decision point explicitly.
- The Impact page reports detection time, AI-decision time, actuation delay and recovery time.

### Backend / database integration
The browser never connects directly to an operational database. For final delivery, configure the frontend to call a backend API or historian adapter:

```bash
cp .env.example .env
```

```text
VITE_TELEMETRY_MODE=api
VITE_TELEMETRY_API_URL=https://your-backend.example.com/api
VITE_TELEMETRY_WS_URL=wss://your-backend.example.com/ws/telemetry
```

Expected REST endpoint:

```text
GET /telemetry/latest?include=forecast,resources,zones
```

The adapter accepts fields such as `frequency_hz`, `inertia_seconds`, `rocof_hz_s`, `demand_mw`, `production_mw`, `fast_reserve_mw`, `stability_risk_pct`, `zone_loading_pct[]`, and `forecast.frequency_hz[]`. Mock telemetry remains the fallback when the backend is not configured or temporarily unavailable.

### Public infrastructure reference map
- Operator overlay loads public power infrastructure through the OpenStreetMap Overpass API when available.
- The detail toggle opens OpenInfraMap, which visualises public infrastructure mapped in OpenStreetMap.
- Voltage filters include 400 kV, 275 kV and 132 kV, matching the two-grid context in Hong Kong.
- The map distinguishes CLP and HK Electric where public tags or geographic inference allow it.
- For operational deployment, the public layer must be replaced or supplemented by authorised utility GIS data.


## v12.2 startup reliability hotfix

- The development server now uses port `5173` strictly. If an old server is still using that port, Vite reports an explicit terminal error instead of silently moving the dashboard to another URL.
- `index.html` now contains a visible startup diagnostic panel. If React fails before rendering, the browser displays an actionable error message instead of an empty blue page.
- The application entry point removes the diagnostic panel after a successful React mount.
- Alternative command: `npm run dev:5174` when port 5173 is intentionally occupied.


## v12.3 runtime hotfix

- Fixed React StrictMode cleanup failure (`destroy is not a function`) when no telemetry WebSocket URL is configured.
- WebSocket subscription effects now return either a cleanup function or `undefined`, never `null`.


## v13 professional interface update

- New Home page with the platform explanation, module guide and workflow.
- Live overview simplified to two blocks: left KPI column and plots; full-width interactive map below.
- Duplicate bottom navigation shortcuts removed.
- Footer removed.
- Aptos typography with Segoe UI fallback.
- Scenario demand and production traces move continuously.
- Tiangou response is constrained to remain better than the unmitigated case after the decision point.
- Impact page prioritises savings, emissions avoided, stability risk and renewable share.
- Infrastructure map replaced by a responsive, MapCN-inspired MapLibre view with zoom, pan, fullscreen, popups and filters.


## v14 operator refinement

- Corrected light-mode colours on the Home page and map controls.
- Removed the infrastructure map from Live Overview.
- Retained maps only in Grid Stability and Resource Mix.
- Replaced the street basemap with a responsive, interactive minimal land/water MapLibre layer.
- Added a permanent map legend for assets, voltage classes and cable types.
- Removed moving endpoint dots from plots.
- Harmonised chart colours across both themes.
- Restored smooth dynamic demand and production during scenarios.
- Constrained the Tiangou response to remain operationally better than the conventional counterfactual after action.
- Reordered the Decision Engine: priority outcome KPIs first, action levers second, timing information last.


## v15 compact simulation repair

- Removed icon boxes from live and comparison KPI columns.
- Reworked simulation KPI cards to prevent collisions and label overlap.
- Reduced chart height so the frequency and energy-balance charts fit in one operator snapshot.
- Added visible horizontal and vertical grids and consistent axes.
- Added distinct moving conventional-demand and Tiangou-demand traces.
- Replaced the stale nested state update with an atomic before/after simulation pair.
- Rebuilt scenario trajectories so the Tiangou intervention is never worse than the conventional counterfactual after actuation.
- Kept line-only charts and the visible AI-decision marker.


## v16 simulation comparison repair

- Removed the duplicate Tiangou-demand trajectory: the energy chart now has one physical demand line.
- Added separate conventional-production and Tiangou-production traces.
- Added both conventional and Tiangou 20-second PINN forecast lines.
- Moved AI detection, decision and actuation earlier so the controlled trajectory remains above the safety threshold.
- Added a moving AI-decision timestamp marker anchored to the rolling frequency window.
- Increased simulation KPI values and removed the `Conv.` abbreviation.
- Added two compact live topology maps on the right during simulations:
  - Conventional counterfactual grid
  - Tiangou AI protected grid
- Extended both stable live plots to the same width.
- Rebalanced the professional palette for light and dark themes.


## v17 map and topology refinement

- Replaced the schematic geospatial background in Grid Stability and Resource Mix with a real, minimal, interactive OpenFreeMap vector basemap sourced from OpenStreetMap.
- Removed roads and place labels while retaining land, water, coastline and administrative context.
- Improved public circuit geometry extraction through the Overpass API and added a second public endpoint fallback.
- Added voltage-aware detailed transmission overlays and line pop-ups.
- Added an external OpenInfraMap detail link for public infrastructure exploration.
- Upgraded the two Live Overview comparison maps:
  - real Hong Kong base map background;
  - boxed non-overlapping node labels;
  - blacked-out regions when the underlying loading exceeds 100%;
  - capped operator-facing display using `OUTAGE` rather than raw values above 100%;
  - one stacked resource-mix line below each map.
- Forced validated Tiangou AI KPI styling to green at the end of a completed simulation.


## v18 outage marker and Python-topology adapter

- Reduced the blackout marker in the two compact simulation maps to the same radius as normal nodes.
- Reworked the compact simulation resource-mix lines:
  - conventional overloads above 100% now trigger a black `Tripped` capacity segment;
  - the conventional available capacity decreases during outage conditions;
  - the Tiangou AI case retains the protected available resource mix;
  - each map displays the remaining available MW and the tripped MW.
- Added support for topology extracted from the team's Python files:
  - export script: `scripts/export_grid_topology.py`
  - example input: `scripts/topology_example.py`
  - generated browser asset: `public/grid-topology.json`
  - frontend selection: `VITE_GRID_TOPOLOGY_MODE=auto|python|osm`
  - frontend URL: `VITE_GRID_TOPOLOGY_URL=/grid-topology.json`

### Python topology workflow

```powershell
python scripts/export_grid_topology.py "C:\path\to\your_team_topology.py"
npm run dev
```

The React frontend cannot execute arbitrary `.py` files inside the browser. The exporter converts the Python topology to a stable JSON contract consumed by both the Grid Stability and Resource Mix maps. In `auto` mode, the dashboard falls back to public OSM geometry and then to its curated demonstrator topology when the JSON file is absent.
