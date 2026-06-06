from app.assumptions.provenance import TABLES_BY_KEY, table_payload


def generator_assumption_tables() -> list[dict]:
    return [
        table_payload(TABLES_BY_KEY["generator_cost_availability_defaults"]),
        table_payload(TABLES_BY_KEY["generator_dispatch_merit_order"]),
    ]
