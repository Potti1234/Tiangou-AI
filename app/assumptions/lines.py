from app.assumptions.provenance import TABLES_BY_KEY, table_payload


def line_assumption_tables() -> list[dict]:
    return [
        table_payload(TABLES_BY_KEY["line_thermal_rating_defaults"]),
        table_payload(TABLES_BY_KEY["cable_impedance_defaults"]),
        table_payload(TABLES_BY_KEY["overhead_line_impedance_defaults"]),
    ]
