from app.assumptions.provenance import TABLES_BY_KEY, table_payload


def import_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY["cross_border_import_limits"])]
