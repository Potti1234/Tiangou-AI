from app.assumptions.provenance import TABLES_BY_KEY, table_payload


def contingency_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY["synthetic_contingency_library"])]
