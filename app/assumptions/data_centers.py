from app.assumptions.provenance import TABLES_BY_KEY, table_payload


def data_center_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY["data_center_site_assumptions"])]
