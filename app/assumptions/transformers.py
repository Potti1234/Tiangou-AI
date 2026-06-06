from app.assumptions.provenance import TABLES_BY_KEY, table_payload


def transformer_assumption_tables() -> list[dict]:
    return [
        table_payload(TABLES_BY_KEY["transformer_capacity_defaults"]),
        table_payload(TABLES_BY_KEY["transformer_tap_defaults"]),
    ]
