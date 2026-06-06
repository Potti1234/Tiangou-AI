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

Inspect the assumption-table provenance validation summary:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/assumptions/summary
```

The tables live under `data/assumptions/` and define auditable CSV inputs for line, transformer, demand-profile, data-center, generator, contingency, and import assumptions. Line/cable thermal ratings, line/cable impedances, transformer capacity defaults, and transformer tap defaults are populated and exported into solver branches with `parameter_source`, `parameter_method`, `parameter_provenance`, `parameter_confidence`, source detail, and assumption text. Remaining future-slice tables are still surfaced as empty-table warnings until populated. Drilldown endpoints are available at `/assumptions/lines`, `/assumptions/transformers`, `/assumptions/data-centers`, `/assumptions/generators`, `/assumptions/contingencies`, and `/assumptions/imports`.

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

The bundle also writes `run_hong_kong_solver_pipeline.ps1` and `grids_solvable.txt` for the downstream Julia solve/export/base-verify/scenario steps. The minimal GridSFM Julia solver pipeline is vendored in `third_party/gridsfm_solver`, so the default workflow is self-contained once Julia is available:

```powershell
julia --project=third_party/gridsfm_solver -e "using Pkg; Pkg.instantiate(); Pkg.precompile()"
python -m app.export_powermodels data/processed --hong-kong-phase1-bundle --min-voltage-kv 100 --include-hk-interties
python -m app.gridsfm_solver check
python -m app.gridsfm_solver run data/processed/hong_kong_phase1_manifest.json
```

The generated PowerShell handoff is still available and defaults to `third_party\gridsfm_solver`:

```powershell
.\data\processed\run_hong_kong_solver_pipeline.ps1
```

Pass `-SolverPipeline "C:\custom\solver"` only when intentionally testing another solver checkout.

Verify the generated raw/solvable/PyG/scenario artifacts after the Julia handoff:

```powershell
python -m app.verify_gridsfm_handoff data/processed/hong_kong_phase1_manifest.json
```

The embedded solver files under `third_party/gridsfm_solver` are a minimal MIT-licensed copy of GridSFM's `power_grid/US/topology_solver_pipeline`; see `third_party/gridsfm_solver/LICENSE` and `third_party/gridsfm_solver/NOTICE.md`.

Current Hong Kong Phase 1 smoke status, using `--include-hk-interties --min-voltage-kv 100 --solver-include-policy demo_full_osm --include-synthetic-generator-connections --n-per-mode 1`:

- Tiangou validation is `warning` for both `hong_kong_16h_model.json` and `hong_kong_04h_model.json`, with zero structural errors and zero severe branch-voltage mismatches.
- The exported demo solver case has 51 buses, 60 solver branches, 55 loads, 7 generators/imports, 5 islands, about 9,492 MW peak demand, and about 23,032 MW total Pmax.
- Processed artifacts were regenerated after full OSM generator promotion with `solver_include_policy=demo_full_osm`, `min_solver_generator_mw=0.5`, and synthetic generator connections enabled.
- Promoted OSM generators include Lamma Power Station, Lamma Winds, Castle Peak Power Station, and Black Point Power Station; the tagged OSM generator total is about 10,646 MW, with Lamma Power Station at 3,736 MW and Lamma Winds at 0.8 MW.
- Warnings include documented synthetic generator connections, inferred voltages, passive no-load islands retained by the demo policy, and CLP spatial demand inferred from public territory totals.
- GridSFM `solve_topo_json.jl` writes documented `L5` relaxed handoff files for both snapshots after cold-strict checks fail with `NORM_LIMIT`.
- `export_gridsfm_data.jl` writes both `.pyg.json` files with a relaxed-handoff warning and `NORM_LIMIT` termination metadata.
- `solve_pyg_json.jl` reports objective-matching round trips for both base PyG exports.
- `gen_perturbed_data.jl` with `n_per_mode=1` writes 12 scenario JSON files across the two snapshots; current scenario solves are marked infeasible and should be treated as diagnostic artifacts, not operationally feasible dispatch cases.

The dashboard and API now default solver previews to `solver_include_policy=demo_full_osm` for visual completeness. A current Hong Kong demo preview audit retains 51 solver buses, 60 branches, 55 loads, 7 generators/imports, and 6 tagged OSM generators, including Lamma Power Station at 3736 MW and Lamma Winds at 0.8 MW. Demo-retained inferred assets are tagged with explicit provenance and validation warnings, while `strict_transmission` remains available for conservative export comparison.

This preview uses OSM geometry, table-backed voltage-class impedance/charging/rating defaults, public Hong Kong peak-demand anchors, and territory-level equivalent generators. Treat it as an upstream topology-builder artifact for the Julia relaxation/export pipeline, not as an operational grid model.
Exported buses, branches, loads, and generators retain `provenance` and `confidence` annotations, with aggregate counts in `_metadata.provenance_summary`, so inferred values can be audited before scenario generation.
Demand is allocated within each service territory using a voltage-weighted substation proxy and a 0.95 assumed load power factor while preserving the public CLP/HK Electric snapshot totals.
Generators also carry source OSM id, name, operator, `energy_source`, parsed capacity tags, connection method, `resource_type`, and `cost_class` metadata so tagged local plants, synthetic generator connections, and territory-level capacity equivalents remain distinguishable after export.
For strict solver handoff, passive disconnected components and no-load generation-only fragments are pruned. For `demo_full_osm`, usable passive branch components and major isolated/tap branches are retained with transparent retention reasons; load-bearing components are still connected with `synthetic_service_territory_backbone` branches where sparse OSM topology requires it, and every retained load-bearing island receives an equivalent capacity source.
