# HONESTY.md


## 1. Team — who did what

| Member | GitHub handle | Main contributions |
|---|---|---|
| Justus Pansch | Justus2802 | PowerModels case generation, dynamic simulation API, PINN implementation and training |
| Simone Albanese | busynessman | Dashboard development, pitch deck |
| Lukas Pottner | Potti1234 | Hong Kong grid data, dashboard, and landing page |
| Alberto Gil | | Video generation, pitching |

---

## 2. What is fully working

- **OSM power-grid ingestion** — `POST /ingest/hong-kong` fetches real power-infrastructure elements (substations, generators, transmission lines, towers) from OpenStreetMap via the Overpass API and stores them in SQLite. 1,850 elements for Hong Kong.
- **Consumer proxy ingestion** — `POST /ingest/consumer-proxies/hong-kong` fetches 135,000+ buildings, hospitals, data centres, transport nodes, and industrial sites from OSM to estimate spatial demand distribution.
- **PowerModels topology builder** — Converts raw OSM elements into a bus/branch/generator/load graph with voltage snapping, circuit reconstruction, inertia assignment, and demand calibration against public EMSD and HK Electric statistics.
- **Dynamic grid configuration** — `GET /dynamic/config` derives merit-order dispatch, inertia constants, ramp rates, and EV/data-centre load proxies from the OSM-derived grid case.
- **Dual-timeline simulation** — `POST /dynamic/simulate` runs two 400-second swing-equation simulations in parallel: Timeline A (no intervention) and Timeline B (AI-guided dispatch). Uses real OSM generator parameters.
- **PINN frequency trajectory prediction** — 12,930-parameter physics-informed neural network estimates effective system inertia H and rolls out a 60-second frequency forecast each simulation step using the swing equation.


---

## 3. What is mocked, stubbed, or hardcoded

| What is faked | Where (file:line or folder) | Why we mocked it | What the real version would do |
|---|---|---|---|
| AC optimal power flow (OPF) solve | `app/dynamic/adapter.py` — `_apply_merit_order_dispatch()` | Requires Julia + GridSFM solver which is not in the container environment | Julia GridSFM OPF would solve for actual pg values at each generator, giving physically correct dispatch with line-flow constraints |
| Generator inertia constants H | `app/dynamic/adapter.py` — `_inertia_default()` | No public per-unit inertia data available for HK generators | Real H values would come from utility equipment specifications or system identification |
| Generator ramp rates | `app/dynamic/adapter.py` — `_ramp_rate_default()` | No public ramp-rate data available | Real ramp rates from generator technical limits |
| Synthetic capacity-equivalent generator | `app/topology.py` lines 3125–3138 | PowerModels needs generation ≥ demand to be feasible without OPF; a "slack" equivalent generator closes the balance | Would be replaced by real OPF solution and actual import capacity data |
| EV station loads | `app/dynamic/adapter.py` — `_ev_stations_from_proxies()` | No per-station load metering; estimated at 0.15 MW per OSM charging_station tag | Real smart-meter or SCADA data per station |
| Data centre loads | `app/assumptions/data_centers.py` | No public per-facility load data; estimated from building size, telecom tags, and public proxy tables | Actual utility billing or smart-meter data |
| Hourly demand profile shape | `app/assumptions/demand_profiles.py` | Uses sector-level public statistics (EMSD); district-level hourly shape assumed commercial-sector typical | Utility SCADA load-flow data at substation level |
| AI dispatch action set | `app/dynamic/dispatch.py` — `_build_actions()` | Hardcoded action list (−800 MW demand curtailment, named dispatchable units); not a real optimiser | Real economic dispatch or MILP optimiser over available reserves |
| PINN trained on synthetic HK data | `hk_grid_backend/pinn/train.py`; checkpoint `app/dynamic/pinn_checkpoint.pt` | The Spain 28-Apr-2025 dataset is present in the repo but the deployed checkpoint (`H_estimate = 1.567 s`) matches the synthetic HK typhoon training target well — the Spain data was used as well for training | Train on real grid frequency measurements with confirmed H from system identification |

---

## 4. External APIs, services & data sources

| Service / API / dataset | Used for | Real call or mocked? |  Auth |
|---|---|---|---|
| OpenStreetMap Overpass API (`overpass-api.de`) | Fetch real power infrastructure and consumer proxy OSM elements | **Real call** — live HTTP fetch at ingest time | None (public API, rate-limited) |
| EMSD Energy End-Use Data (data.gov.hk) | Calibrate sector-level demand and load-shape assumptions | Real CSV downloaded; included in `data/raw/emsd/` | None (open data) |
| HK Electric open data (data.gov.hk) | District-level consumption calibration for HK Island / Lamma territory | Real CSV downloaded; included in `data/raw/hk_electric/` | None (open data) |
| CLP open data (data.gov.hk) | District-level consumption calibration for Kowloon / New Territories | Real CSV downloaded; included in `data/raw/clp/` | None (open data) |
| Spain 28-Apr-2025 Blackout Dataset (Excel) | Intended primary PINN training data | File present at `pinn/data/Spain_Blackout_28Apr2025_Dataset.xlsx` — see §3 for disclosure that deployed checkpoint uses synthetic HK fallback | None |

---

## 5. Pre-existing code

| Item | Source | Roughly how much | License |
|---|---|---|---|
| `hk_grid_backend/` — HK-specific simulation backend including swing-equation simulator, PINN architecture, grid-state dataclass, risk scoring, and `hk_grid_frontend/` React dashboard | Written by the team in the hackathon as the starting point for this project; only standard library calls are used for the PINN and simulator | ~3,000 lines Python + ~2,500 lines React | — |
| `app/` generic OSM pipeline (ingestion, topology, PowerModels builder, dynamic adapter) | Written during the hackathon | ~8,000 lines Python | — |

---

## 6. Known limitations & next steps


- **PINN checkpoint trained on synthetic data** — The PINN is partially trained on synthetic grid frequency measurements of shutdowns in Hong Kong. Real training would require PMU/SCADA records from an actual disturbance event.
- **Cascade dynamics too stable in OSM-derived simulation** — The real HK coal fleet (Castle Peak 4,108 MW, Lamma 3,736 MW) has high inertia (H ≈ 5 s), so the governor naturally stabilises a single generator trip without cascade. We switched here to simulate a future Hong Kong with a higher share of renewable energy, resulting in lower H.
- **Import loss scenario unavailable** — Hong Kong's OSM data does not tag the China Southern Power Grid DC link explicitly; the import_loss scenario shows "unavailable" in the API.
- **No real-time streaming** — The `app/` backend is request/response only. Live monitoring on the dashboard holds a static initial state rather than streaming from SCADA.
- **Next steps** — Integrate Julia GridSFM for real OPF; train PINN on more blackout data (current dataset already in repo); add UFLS (under-frequency load shedding) relay model to simulator; source real generator inertia and ramp-rate data from public utility reports.
