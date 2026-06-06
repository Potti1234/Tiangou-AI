# Assumption Tables

This directory contains the auditable input tables for Hong Kong grid-model enrichment. The tables separate public observations, public-statistics inference, and synthetic engineering defaults so solver-critical values can be inspected without treating them as confidential utility data.

Every row added to these tables must keep the common provenance fields:

- `unit`
- `source`
- `provenance`
- `confidence`
- `method`
- `assumptions`
- `date_or_year`

Allowed `provenance` values are:

- `observed_public`
- `inferred_from_public_statistics`
- `synthetic_engineering_default`

The `/assumptions/summary` API reports schema coverage, row counts, provenance counts, and validation warnings. Empty future-slice tables are reported as warnings until they are populated.

## Table Families

- `line_thermal_rating_defaults.csv`: populated thermal-rating defaults for overhead, underground, and submarine corridors. Ratings are MVA per circuit and are scaled by OSM `circuits`, `cables`, or multi-voltage inference.
- `cable_impedance_defaults.csv` and `overhead_line_impedance_defaults.csv`: populated impedance defaults by voltage and asset class. Resistance/reactance are stored in ohm/km. Capacitance is stored as nF/km and converted to charging susceptance at 50 Hz during PowerModels export.
- `transformer_capacity_defaults.csv` and `transformer_tap_defaults.csv`: populated transformer size, impedance, and tap defaults by voltage pair and facility class. Inferred transformer branches export the matched capacity, per-unit impedance, neutral tap, tap range, method, source, confidence, and provenance.
- `demand_profiles/*.csv`: populated hourly sector shape and weather sensitivity tables. Runtime load records keep the current snapshot `pd_mw` unchanged and add `hourly_pd_mw`, `peak_hour`, `load_profile_id`, `profile_provenance`, `profile_confidence`, and profile method/source fields for transparency.
- `data_centers/data_center_site_assumptions.csv`: populated data-center load-estimation archetypes. OSM data-center proxies are estimated from floor-area evidence when available (`IT MW = gross floor area * utilization factor * kW/m2 / 1000`), otherwise named/small archetype defaults are used; facility MW is IT MW times PUE and IT load is capped at 120 MW.
- `generators/*.csv`: populated generator cost, availability, outage, emissions, ramp, pmin, and dispatch-order assumptions by fuel/equivalent-supply class. Exported generators carry variable cost, startup cost, availability factor, forced outage rate, emissions factor, ramp rate, dispatch priority, cost method/source, assumptions, and provenance.
- `contingencies/synthetic_contingency_library.csv`: planned synthetic stress and outage cases.
- `imports/cross_border_import_limits.csv`: planned import boundary and derate scenario assumptions.

## Limits

These tables are not real utility data. Public observations must cite the source, inferred values must describe the statistical anchor, and synthetic defaults must state the engineering rule and limitation.

Line, cable, transformer, demand-profile, data-center, and generator values are intentionally conservative synthetic engineering defaults anchored to public Hong Kong voltage classes, OSM topology tags, public sector consumption totals, and public fuel/source context. They should be replaced by observed public project ratings, equipment data, feeder-level hourly demand data, operator-published data-center capacity evidence, or plant heat-rate/availability data when such data is available.
