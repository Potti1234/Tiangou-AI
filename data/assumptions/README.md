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
- `demand_profiles/*.csv`: planned hourly sector shape and weather sensitivity tables.
- `data_centers/data_center_site_assumptions.csv`: planned site-level data-center load assumptions.
- `generators/*.csv`: planned generator cost, availability, and dispatch-order assumptions.
- `contingencies/synthetic_contingency_library.csv`: planned synthetic stress and outage cases.
- `imports/cross_border_import_limits.csv`: planned import boundary and derate scenario assumptions.

## Limits

These tables are not real utility data. Public observations must cite the source, inferred values must describe the statistical anchor, and synthetic defaults must state the engineering rule and limitation.

Line, cable, and transformer values are intentionally conservative synthetic engineering defaults anchored to public Hong Kong voltage classes and OSM topology tags. They should be replaced by observed public project ratings or equipment data when such data is available.
