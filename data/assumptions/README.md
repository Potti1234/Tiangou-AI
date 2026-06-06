# Assumption Tables

This directory contains the auditable input tables for future Hong Kong grid-model enrichment. Slice 1 creates schemas only; later slices will add real public observations, public-statistics inference, and synthetic engineering defaults.

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

The tables are intentionally empty in this slice so solver-critical fields are not populated with unreviewed constants. The `/assumptions/summary` API reports schema coverage, row counts, provenance counts, and validation warnings.

## Table Families

- `line_thermal_rating_defaults.csv`: planned thermal-rating defaults for overhead, underground, and submarine corridors.
- `cable_impedance_defaults.csv` and `overhead_line_impedance_defaults.csv`: planned impedance defaults by voltage and asset class.
- `transformer_capacity_defaults.csv` and `transformer_tap_defaults.csv`: planned transformer size, impedance, and tap defaults.
- `demand_profiles/*.csv`: planned hourly sector shape and weather sensitivity tables.
- `data_centers/data_center_site_assumptions.csv`: planned site-level data-center load assumptions.
- `generators/*.csv`: planned generator cost, availability, and dispatch-order assumptions.
- `contingencies/synthetic_contingency_library.csv`: planned synthetic stress and outage cases.
- `imports/cross_border_import_limits.csv`: planned import boundary and derate scenario assumptions.

## Limits

These tables are not real utility data. Public observations must cite the source, inferred values must describe the statistical anchor, and synthetic defaults must state the engineering rule and limitation.
