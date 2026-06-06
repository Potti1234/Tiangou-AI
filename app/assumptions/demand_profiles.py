from app.assumptions.provenance import TABLES_BY_KEY, table_payload


def demand_profile_assumption_tables() -> list[dict]:
    return [
        table_payload(TABLES_BY_KEY["hong_kong_sector_hourly_profiles"]),
        table_payload(TABLES_BY_KEY["weather_sensitivity_profiles"]),
    ]
