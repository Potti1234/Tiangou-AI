# HONESTY.md

Mandatory disclosure for the hackathon. This file lives at the root of the repository. Judges can cross-check it against the code, git history, README, generated artifacts, and technical video.

---

## 1. Team - who did what

This section combines the human team list from the submission with the handles visible in this repository history. `git shortlog -sn --all` currently shows contributions from `Potti1234`, `Justus Pansch`, and `busynessman`.

| Member | GitHub handle | Main contributions |
|---|---|---|
| Lukas Pottner | `Potti1234` | Main FastAPI backend, OSM ingestion, SQLite persistence, Hong Kong topology reconstruction, load allocation, assumption tables, PowerModels export, GridSFM handoff integration, diagnostics, dynamic simulation integration, main React dashboard, landing page, documentation, and most tests. |
| Justus Pansch | `Justus Pansch` | Dynamic simulation work, PINN implementation/training work, and prototype/backend simulation components visible in the repository history. |
| Simone Albanese | `busynessman` | Dashboard/prototype contribution visible in git history and pitch deck support. |
| Alberto Gil | not visible in current git shortlog | Video generation and pitching support. |

---

## 2. What is fully working

Features that run end-to-end on the live app, with real code and explicit data/provenance handling.

- **OpenStreetMap power-grid ingest.** The backend builds raw Overpass queries for Hong Kong and the Greater Bay Area, calls the real Overpass API, normalizes power assets, and stores them in SQLite. Endpoints include `POST /ingest/{region_key}`, `GET /grid/assets`, `GET /grid/summary`, and `GET /overpass-query/{region_key}`.
- **Consumer/load-proxy ingest.** The backend can query OSM for buildings, hospitals, EV chargers, railway/public-transport assets, airports, industrial/commercial proxies, and data-center-like features. Endpoints include `POST /ingest/consumer-proxies/{region_key}`, `POST /ingest/hong-kong-consumer-proxies`, `GET /overpass-query/{region_key}/consumer-proxies`, `GET /grid/consumer-proxies`, and `GET /grid/consumer-proxies/important`.
- **Public data calibration.** The model reads committed public CSVs from `data/raw/`: HK Electric consumption by customer type and district, EMSD electricity/end-use tables, and Hong Kong Census and Statistics monthly electricity/gas consumption. HK Electric demand uses observed public data; CLP-side demand is inferred from official Hong Kong totals minus HK Electric public totals where those tables are available.
- **Topology reconstruction.** `app/topology.py` reconstructs buses, branches, voltage levels, merged circuits, inferred transformer branches, tagged generators, equivalent capacity sources, synthetic service-territory backbones, and synthetic generator connections from OSM-derived rows. The topology is exposed through `/grid/topology/preview`, `/grid/topology/powermodels-preview`, `/grid/topology/validation`, `/topology/diagnostics`, and `/topology/asset-reconciliation`.
- **Auditable assumption registry.** CSV assumption tables under `data/assumptions/` define line/cable ratings and impedances, transformer defaults, hourly demand profiles, weather sensitivity, data-center load archetypes, generator costs/availability, contingency scenarios, and import constraints. `/assumptions/summary` validates row counts, schemas, provenance classes, confidence values, warnings, and errors.
- **PowerModels/GridSFM export.** `python -m app.export_powermodels ...` writes raw demo PowerModels JSON, solver-sanitized JSON, a manifest, a PowerShell handoff script, and GridSFM grid lists. Raw demo exports preserve visual topology; solver-sanitized exports are explicitly labeled and used for Julia handoff.
- **Embedded GridSFM solver handoff.** `third_party/gridsfm_solver/` contains a minimal MIT-licensed copy of the GridSFM Julia topology solver/export/scenario pipeline. `python -m app.gridsfm_solver run data/processed/hong_kong_phase1_manifest.json` runs the vendored Julia scripts against the solver-sanitized Hong Kong exports when Julia and the required packages are available.
- **Handoff verification and diagnostics.** `python -m app.verify_gridsfm_handoff ...` checks raw, solvable, PyG, and scenario artifacts for existence and freshness. `python -m app.diagnose_gridsfm_case ...` reports AC-feasibility blockers such as passive islands, voltage mismatches, branch shunts, and generator range issues.
- **GridSFM export bisection runner.** `python -m app.run_gridsfm_export_experiments ...` exports planned variants, runs diagnostics, optionally runs the solver, and writes an experiment manifest to identify which modeling choices break or relax the solver handoff.
- **Dynamic grid configuration.** `GET /dynamic/config` derives a dynamic model from the PowerModels case: generator/source mapping, default inertia constants, ramp-rate assumptions, demand profiles, EV charging proxies, data-center proxies, and provenance metadata.
- **Dynamic scenario API.** `GET /dynamic/scenarios` builds scenarios from the assembled grid, including largest generator trip, import/equivalent-source loss, renewable weather loss, data-center spike, and combined stress when the required source types are present.
- **Dual-timeline simulation.** `POST /dynamic/simulate` runs request/response swing-equation simulations for Timeline A without intervention and Timeline B with dispatch actions. The API default duration is 400 seconds and accepts 1-3600 seconds.
- **PINN frequency trajectory prediction.** `app/dynamic/pinn_model.py` defines a 12,930-parameter PyTorch PINN with learned effective inertia `H`. `app/dynamic/pinn_predict.py` rolls out 60-second frequency forecasts during simulation. If PyTorch or the checkpoint is unavailable, the API reports that status and uses a small fallback model instead of hiding the failure.
- **Baseline weak-spot study.** `/studies/baseline-weak-spots` computes deterministic heuristic risk rankings for branches and buses from the assembled case. This is real code, but it is not a full N-1, hosting-capacity, or OPF security study.
- **Main React dashboard.** The `frontend/` app uses React, Vite, MapLibre, TanStack Router, Recharts, Tailwind, Lucide icons, and local shadcn-style UI primitives. It shows raw/reconstructed/solver map layers, important consumer markers, assumption transparency, analytics charts, weak spots, dynamic simulation, and solver artifact status.
- **Tests/build.** The repository contains pytest coverage for API endpoints, assumptions, data sources, topology, PowerModels export, GridSFM handoff utilities, dynamic simulation, and frontend source contracts. The main frontend has a real `npm run build` script.

---

## 3. What is mocked, stubbed, hardcoded, or approximated

Every known shortcut is listed here. These are not hidden mocks; they are explicit modeling approximations used because real utility planning data is not public.

| What is faked or approximated | Where (file:line or folder) | Why we mocked it | What the real version would do |
|---|---|---|---|
| Engineering defaults for line/cable ratings and impedances | `data/assumptions/line_thermal_rating_defaults.csv`, `data/assumptions/cable_impedance_defaults.csv`, `data/assumptions/overhead_line_impedance_defaults.csv`, used by `app/assumptions/lines.py` and `app/topology.py` | OSM does not provide conductor/cable type, exact ampacity, impedance, or charging values for most assets. | Use utility/public project equipment ratings, conductor/cable types, actual circuit counts, and measured impedance/thermal limits. |
| Transformer capacities, impedance, and tap defaults | `data/assumptions/transformer_capacity_defaults.csv`, `data/assumptions/transformer_tap_defaults.csv`, used by `app/assumptions/transformers.py` | OSM rarely exposes transformer nameplate ratings or tap settings. | Use actual substation transformer inventory, MVA ratings, vector groups, impedances, tap positions/ranges, and voltage-control settings. |
| Synthetic hourly load profiles and weather sensitivity | `data/assumptions/demand_profiles/` and `app/assumptions/demand_profiles.py` | Public data gives annual/monthly/sector energy, not feeder-level hourly load curves. | Use utility AMI/SCADA/feeder measurements or published hourly demand profiles by service territory and customer class. |
| CLP-side demand spatial allocation | `app/topology.py` load allocation functions and `app/data_sources/calibration.py` | CLP public feeder/customer-level demand was not available. CLP demand is inferred from official Hong Kong totals minus HK Electric public data and allocated to OSM/substation/load proxies. | Use CLP feeder/substation load, customer count, district demand, or operator-published load allocation data. |
| Consumer proxy load weights | `app/load_proxies.py`, `app/repository.py`, `app/topology.py` | OSM contains buildings/POIs/landuse, not real electric loads. | Use real customer meters, building energy benchmarks, floor area records, feeder assignments, and sector-specific load profiles. |
| EV charging-station loads | `app/dynamic/adapter.py` `_ev_stations_from_proxies()` | No per-station load metering is public. The dynamic model estimates charging-station load from OSM proxy weight and clamps it between 0.15 MW and 2.0 MW. | Use charging-station telemetry, utility interconnection records, charger counts/ratings, or smart-meter data. |
| Data-center load estimates | `data/assumptions/data_centers/data_center_site_assumptions.csv`, `app/assumptions/data_centers.py`, `app/dynamic/adapter.py` | Public OSM features do not include verified IT load, PUE, contracted capacity, or site capacity for most sites. | Use operator/public capacity disclosures, grid connection applications, facility floor area, PUE, contracted demand, and measured load. |
| Generator cost, availability, emissions, ramp, pmin defaults | `data/assumptions/generators/`, `app/assumptions/generators.py`, `app/topology.py`, `app/dynamic/adapter.py` | OSM/public tags often give plant names/capacity/source but not dispatch economics, availability, ramp rates, or unit limits. | Use plant heat rates, fuel contracts/prices, forced outage statistics, ramp rates, unit commitment constraints, and actual dispatch data. |
| Generator inertia constants `H` | `app/dynamic/adapter.py` `_inertia_default()` | Public per-unit inertia data for Hong Kong generators/import equivalents is not available. | Use utility equipment specifications, PMU/SCADA disturbance records, or system identification. |
| Dynamic dispatch action set | `app/dynamic/dispatch.py` `_build_actions()` | Timeline B uses deterministic demo actions: EV/load curtailment, a fixed -800 MW flexible-demand action, and fast redispatch of up to six dispatchable/equivalent sources. | Use real reserve products, economic dispatch, unit commitment, MILP/OPF constraints, operator rules, and verified response times. |
| Dynamic simulation physics | `app/dynamic/simulator.py`, `app/dynamic/dual_timeline.py`, `app/dynamic/validator.py` | The simulator is a request/response swing-equation demo with simplified governor/dispatch behavior, not a validated transient-stability model. | Use validated dynamic models with generator controls, protection, UFLS/UVLS, relays, detailed load models, and real disturbance playback. |
| PINN checkpoint/training data | `app/dynamic/pinn_checkpoint.pt`, `app/dynamic/pinn_model.py`, `hk_grid_backend/pinn/train.py`, `pinn/src/` | The deployed checkpoint is a local artifact and the repository also contains synthetic HK/Spain-blackout exploration code. Real Hong Kong PMU/SCADA disturbance data is not public. | Train and validate on measured frequency, power imbalance, inertia, and event data with documented splits and uncertainty. |
| Equivalent generators/import/local supply | `app/topology.py` equivalent generator functions | Sparse OSM topology and public data do not fully describe every local/import source needed to balance a solver case. | Model actual generating units, imports, contracted capacity, spinning reserve, and cross-border transfer constraints. |
| Synthetic generator connections | `app/topology.py` `_promote_generators_to_active_buses` and `_synthetic_generator_connection_branch` | Some OSM generators/plants are not topologically connected to the reconstructed solver network, but need to be visible in the demo/solver model. | Use real substation interconnection points, generator step-up transformers, busbars, and connection circuits. |
| Synthetic service-territory backbone branches | `app/topology.py` `_synthetic_service_territory_backbone` | OSM grid mapping is incomplete, so load-bearing islands can be disconnected. | Use the real network connectivity, missing cables/lines, switching topology, and interconnection substations. |
| Public CLP-HK Electric intertie represented as an equivalent branch | `data/assumptions/imports/cross_border_import_limits.csv`, `app/assumptions/imports.py`, `app/topology.py` `_hk_intertie_branches` | A public 720 MVA interconnection reference exists, but the exact physical topology and impedance are not modeled from utility data. | Model the actual interconnector circuits, terminals, protection/operational limits, impedance, and dispatch rules. |
| Synthetic import scenarios and contingency library | `data/assumptions/imports/`, `data/assumptions/contingencies/`, `app/assumptions/contingencies.py` | Real outage history, import contracts, operating limits, and contingency lists are not public. | Use real N-1/N-k planning contingencies, outage records, import contracts, transfer limits, and reliability criteria. |
| Solver sanitization | `app/gridsfm_case_tools.py`, `app/export_powermodels.py` | The visually complete raw OSM-derived model is not always AC-feasible. Solver exports remove/relax passive islands, large inferred shunts, short synthetic-branch charging, generator Q ranges, and reference buses. | Make the raw model AC-feasible using real topology, real equipment parameters, correct voltage conversion, actual shunts/reactive devices, and validated generator controls. |
| Baseline weak-spot scoring | `app/studies/baseline.py` | We needed an explainable demo risk signal before implementing full contingency/hosting-capacity solvers. | Run power-flow/OPF-based N-1 security analysis, thermal overload studies, voltage stability studies, hosting-capacity sweeps, and uncertainty analysis. |
| Generated processed artifacts are local outputs, not source data | `data/processed/` | Solver JSON, PyG, diagnostics, scenarios, and experiment outputs are generated from the app and ignored by git. | Recompute artifacts from committed code/data during reproducible runs or publish immutable releases separately. |

---

## 4. External APIs, services, and data sources

Everything the project calls or uses as input. "Real call" means the code actually calls the service or reads the dataset; "local file" means committed data is read from disk.

| Service / API / dataset | Used for | Real call or mocked? | Auth |
|---|---|---|---|
| OpenStreetMap Overpass API | Fetch power infrastructure and consumer/load proxy features for Hong Kong/GBA ingest. | Real HTTP call via `app/overpass.py` when ingest endpoints are run. | None. |
| HK Electric Open Data / data.gov.hk consumption by customer type | Observed HK Electric sector energy calibration. | Real local CSV in `data/raw/hk_electric/consumption_by_customer_type.csv`. | None. |
| HK Electric Open Data / data.gov.hk consumption by district and customer type | District/sector allocation for HK Electric service territory. | Real local CSV in `data/raw/hk_electric/consumption_by_district_and_customer_type.csv`. | None. |
| EMSD Hong Kong Energy End-use Data Table 08 | Territory-wide electricity consumption by sector; used to infer CLP-side demand. | Real local CSV in `data/raw/emsd/electricity_consumption_by_sector_table08.csv`. | None. |
| EMSD Hong Kong Energy End-use Data Table 12 | End-use shares for calibration and load-shape assumptions. | Real local CSV in `data/raw/emsd/energy_end_use_table12.csv`. | None. |
| Hong Kong Census and Statistics Department table 915-91201 | Monthly/annual validation of electricity consumption by user type. | Real local CSV in `data/raw/census_statistics/monthly_electricity_gas_by_user_type_915_91201.csv`. | None. |
| CLP public/open data | Placeholder folder only. | No direct CLP consumption CSV is currently committed; CLP demand is inferred from other public totals. | None. |
| Public data-center source folder | Placeholder for future public data-center evidence. | Not populated with real capacity data; data-center loads use assumption table defaults. | None. |
| Spain 28-Apr-2025 blackout dataset | PINN/data exploration artifact. | Real local Excel file at `pinn/data/Spain_Blackout_28Apr2025_Dataset.xlsx`; not a substitute for measured Hong Kong disturbance data. | None. |
| SQLite | Local persistence for OSM elements, ingest runs, element regions, and consumer proxies. | Real local database, default `data/tiangou.sqlite3`, ignored by git. | None. |
| GridSFM Julia solver pipeline / PowerModels.jl / Ipopt dependencies | Solve sanitized PowerModels cases, export PyG JSON, generate scenarios. | Real local Julia execution if Julia 1.11+ and packages are installed/instantiated. | None. |
| PyTorch | Dynamic PINN checkpoint loading and model execution. | Real dependency in `pyproject.toml`; fallback path is disclosed when unavailable. | None. |
| MapLibre GL | Browser map rendering. | Real frontend library. | None. |
| Recharts / shadcn chart pattern | Browser analytics charts. | Real frontend library/component code. | None. |
| TanStack Router | Frontend routing. | Real frontend library. | None. |
| Docker Compose / nginx frontend proxy | Optional local deployment path. | Real local deployment configuration. | None. |

---

## 5. Pre-existing code

Anything brought into this project from existing sources or templates.

| Item | Source (URL or description) | Roughly how much | License |
|---|---|---|---|
| Vendored GridSFM solver pipeline | Minimal copy of GridSFM `power_grid/US/topology_solver_pipeline` under `third_party/gridsfm_solver/`; see `third_party/gridsfm_solver/NOTICE.md`. https://arxiv.org/pdf/2605.04289 https://github.com/microsoft/GridSFM | Several Julia scripts plus GridSFM README/manifest/license files needed for solve/export/scenario handoff. | MIT, copied in `third_party/gridsfm_solver/LICENSE`. |

---

## 6. Known limitations and next steps

- **Most electrical parameters are synthetic engineering defaults.** Line/cable ratings, impedances, transformer parameters, generator costs, ramp rates, inertia, data-center load, contingencies, and import limits should be replaced with real utility/equipment/project data when available.
- **CLP demand is inferred, not observed directly.** HK Electric data is public and observed; CLP-side demand is inferred from official Hong Kong totals minus HK Electric data and spatially allocated using OSM/substation/load proxies.
- **OSM topology is incomplete.** Missing underground/submarine cables, busbars, switches, transformer details, and exact substation internals require inferred branches, merged circuits, synthetic backbones, and synthetic generator connections.
- **Raw demo exports are not guaranteed AC-feasible.** The project intentionally separates raw demo exports from solver-sanitized exports. The sanitized GridSFM handoff is auditable, but it is not the same as proving the raw visual model solves unchanged.
- **Dynamic simulation is a simplified demo.** It uses simplified swing-equation dynamics, deterministic response actions, assumed inertia/ramp values, and a PINN/fallback model. It is not validated transient-stability or operator-control software.
- **The PINN checkpoint is not trained on real Hong Kong PMU/SCADA disturbance data.** Real training would require measured frequency and power imbalance data from actual events, plus documented validation. It is trained on the data of the Spanish blackout instead
- **Import/equivalent-source scenarios depend on inferred equivalent sources.** When the assembled dynamic case has no suitable import/equivalent source, the API correctly marks the import-loss scenario unavailable.
- **Weak-spot results are heuristic.** Current baseline weak spots are deterministic scores from model metadata/load/generation/branch features, not full N-1 contingency analysis or hosting-capacity optimization.
- **No real outage history is used.** Contingency rows are synthetic stress selectors, not historical outage records.
- **No real-time SCADA streaming exists.** The backend is request/response. Frontend polling and simulation views do not represent live utility telemetry.
- **Greater Bay Area support is structurally present but Hong Kong is the worked-through demo.** GBA ingest/query paths exist, but calibration and validation are much weaker outside Hong Kong without comparable public load/network data.
- **Performance can still improve.** The frontend bundle is large after adding maps, charts, routing, and simulation views; code-splitting heavy routes would reduce initial load size.
- **Next technical steps:** add real equipment ratings where available, improve voltage/topology inference, add solver-grade comparisons between raw and sanitized cases, build real OPF/N-1/hosting-capacity studies, add uncertainty bands around synthetic assumptions, train/validate the PINN on measured disturbance data, add UFLS/relay models, and decide whether to integrate or archive the prototype folders.
