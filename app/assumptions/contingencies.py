from __future__ import annotations

from app.assumptions.provenance import TABLES_BY_KEY, read_table_rows, table_payload


def contingency_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY["synthetic_contingency_library"])]


def contingency_library_summary() -> dict[str, int]:
    _, rows = read_table_rows(TABLES_BY_KEY["synthetic_contingency_library"])
    counts: dict[str, int] = {}
    for row in rows:
        contingency_type = row.get("type") or "unknown"
        counts[contingency_type] = counts.get(contingency_type, 0) + 1
    return dict(sorted(counts.items()))
