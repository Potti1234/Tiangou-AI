# Tiangou-AI

FastAPI backend for collecting OpenStreetMap electricity grid data for Hong Kong first, with Greater Bay Area support built into the same ingestion path.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Run

```powershell
uvicorn app.main:app --reload
```

The SQLite database defaults to `data/tiangou.sqlite3`. Override it with:

```powershell
$env:TIANGOU_DATABASE_PATH="data/custom.sqlite3"
```

## Docker Test Deployment

Build and run the backend plus frontend proxy locally:

```powershell
docker compose up --build
```

Open `http://localhost:8080`. The frontend is served by nginx and proxies `/api/*` to the FastAPI service, so a single Cloudflare Tunnel/Dokploy public route can point at the `frontend` service on port `80`.

The containerized SQLite database is stored in the named Docker volume `tiangou-data`. The backend uses `/data/tiangou.sqlite3` through `TIANGOU_DATABASE_PATH`.

For Dokploy, deploy this repository with Docker Compose and expose only the `frontend` service. The `api` service stays internal on the Compose network.

## Ingest OpenStreetMap Power Data

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/ingest/hong-kong
```

For the Greater Bay Area:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/ingest/greater-bay-area
```

The backend uses raw Overpass QL. The `{{geocodeArea:...}}` macro works in Overpass Turbo, but raw API clients need ordinary Overpass area selectors instead.

## Build a Topology Preview

After ingesting a region, inspect the inferred bus-branch model:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/grid/topology/preview
```

Generate a first PowerModels-style solver handoff JSON:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/grid/topology/powermodels-preview
```

Run structural validation before solver handoff:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/grid/topology/validation
```

Validation returns structural errors separately from research-model quality metrics such as `low_confidence_counts`, `provenance_summary`, and branch-to-bus voltage mismatch diagnostics. Severe branch voltage mismatches are surfaced as warnings before solver handoff.

Write the preview to a file for the downstream Julia solver pipeline:

```powershell
python -m app.export_powermodels data/processed/hong_kong_16h_model.json
```

For a transmission-level handoff, drop known lower-voltage distribution assets before export:

```powershell
python -m app.export_powermodels data/processed/hong_kong_16h_model.json --min-voltage-kv 100
```

Export an additional representative snapshot such as shoulder demand or high-temperature cooling stress:

```powershell
python -m app.export_powermodels data/processed/hong_kong_18h_cooling_model.json --demand-snapshot cooling_peak_18h
```

Add the public 720 MVA CLP-HK Electric interconnection when building an optimization case:

```powershell
python -m app.export_powermodels data/processed/hong_kong_16h_model.json --include-hk-interties
```

Derate that interconnection for transfer-stress cases:

```powershell
python -m app.export_powermodels data/processed/hong_kong_16h_model.json --include-hk-interties --hk-intertie-derate 0.5
```

Write both Phase 1 Hong Kong snapshots plus a manifest:

```powershell
python -m app.export_powermodels data/processed --hong-kong-phase1-bundle --include-hk-interties --n-per-mode 3
```

Write a Phase 1 stress bundle with multiple CLP-HK Electric intertie transfer limits:

```powershell
python -m app.export_powermodels data/processed --hong-kong-phase1-bundle --include-hk-interties --intertie-derate-scenarios 1.0,0.75,0.5 --n-per-mode 3
```

Include additional demand snapshots in a bundle when you want load-stress cases:

```powershell
python -m app.export_powermodels data/processed --hong-kong-phase1-bundle --bundle-demand-snapshots peak_16h,overnight_04h,shoulder_10h,cooling_peak_18h
```

The bundle also writes `run_hong_kong_solver_pipeline.ps1` and `grids_solvable.txt` for the downstream Julia solve/export/base-verify/scenario steps. The script preflights a runnable `julia` command and the expected solver scripts, then verifies each `.solvable.json`, `.pyg.json`, and scenario output before moving on. Pass the cloned solver path when running it if needed:

```powershell
.\data\processed\run_hong_kong_solver_pipeline.ps1 -SolverPipeline "..\GridSFM\power_grid\US\topology_solver_pipeline"
```

Verify the generated raw/solvable/PyG/scenario artifacts after the Julia handoff:

```powershell
python -m app.verify_gridsfm_handoff data/processed/hong_kong_phase1_manifest.json
```

Current Hong Kong Phase 1 smoke status, using `--include-hk-interties --min-voltage-kv 100 --n-per-mode 1`:

- Tiangou validation is `ok` for both `hong_kong_16h_model.json` and `hong_kong_04h_model.json`.
- The exported solver case has 37 buses, 50 inter-facility branches, 16 loads, 3 generators/imports, one connected island, and zero severe branch-voltage mismatches.
- Reconstruction includes 2 merged OSM circuits, 1 inferred multi-voltage facility transformer, and 8 transparent service-territory backbone branches in the retained solver case.
- GridSFM `solve_topo_json.jl` solves both snapshots at `L0` strict.
- `export_gridsfm_data.jl` writes both `.pyg.json` files.
- `solve_pyg_json.jl` reports `RESOLVE ok` for both base PyG exports.
- `gen_perturbed_data.jl` with `n_per_mode=1` writes 12 feasible scenario JSON files across the two snapshots.

This preview uses OSM geometry, voltage-class impedance and charging defaults, public Hong Kong peak-demand anchors, and territory-level equivalent generators. Treat it as an upstream topology-builder artifact for the Julia relaxation/export pipeline, not as an operational grid model.
Exported buses, branches, loads, and generators retain `provenance` and `confidence` annotations, with aggregate counts in `_metadata.provenance_summary`, so inferred values can be audited before scenario generation.
Demand is allocated within each service territory using a voltage-weighted substation proxy and a 0.95 assumed load power factor while preserving the public CLP/HK Electric snapshot totals.
Generators also carry `energy_source`, `resource_type`, and `cost_class` metadata so tagged local plants and territory-level capacity equivalents remain distinguishable after export.
For solver handoff, passive disconnected components and no-load generation-only fragments are pruned, load-bearing components are connected with transparent `synthetic_service_territory_backbone` branches where sparse OSM topology requires it, and every retained load-bearing island receives an equivalent capacity source.
