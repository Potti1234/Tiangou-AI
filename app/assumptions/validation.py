from __future__ import annotations

from typing import Any

from app.assumptions.provenance import ASSUMPTION_TABLES, ProvenanceClass, read_table_rows, summarize_by_provenance


def _warning(code: str, table_key: str, message: str, row_number: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "table": table_key, "message": message}
    if row_number is not None:
        payload["row_number"] = row_number
    return payload


def build_assumption_validation_summary() -> dict[str, Any]:
    tables = []
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    aggregate_provenance_counts = {provenance.value: 0 for provenance in ProvenanceClass}
    total_rows = 0

    for table in ASSUMPTION_TABLES:
        if not table.path.exists():
            errors.append(_warning("missing_table_file", table.key, f"Missing assumption table at {table.path.as_posix()}"))
            tables.append(
                {
                    "key": table.key,
                    "category": table.category,
                    "path": table.path.as_posix(),
                    "row_count": 0,
                    "status": "error",
                    "provenance_counts": {},
                    "missing_columns": list(table.required_columns),
                }
            )
            continue

        fieldnames, rows = read_table_rows(table)
        missing_columns = [column for column in table.required_columns if column not in fieldnames]
        table_status = "ok"
        if missing_columns:
            errors.append(
                _warning(
                    "missing_required_columns",
                    table.key,
                    f"Missing required columns: {', '.join(missing_columns)}",
                )
            )
            table_status = "error"

        for index, row in enumerate(rows, start=2):
            provenance = row.get("provenance", "")
            if provenance not in {item.value for item in ProvenanceClass}:
                errors.append(_warning("invalid_provenance", table.key, f"Invalid provenance '{provenance}'", index))
                table_status = "error"
            confidence_raw = row.get("confidence", "")
            try:
                confidence = float(confidence_raw)
            except ValueError:
                errors.append(_warning("invalid_confidence", table.key, f"Invalid confidence '{confidence_raw}'", index))
                table_status = "error"
            else:
                if confidence < 0.0 or confidence > 1.0:
                    errors.append(_warning("confidence_out_of_range", table.key, "Confidence must be within 0 and 1", index))
                    table_status = "error"

            for column in table.value_columns:
                raw_value = row.get(column, "")
                if raw_value == "":
                    errors.append(_warning("missing_value", table.key, f"Missing value for {column}", index))
                    table_status = "error"
                    continue
                try:
                    value = float(raw_value)
                except ValueError:
                    errors.append(_warning("non_numeric_value", table.key, f"{column} must be numeric", index))
                    table_status = "error"
                else:
                    if value < 0.0:
                        errors.append(_warning("negative_value", table.key, f"{column} must be non-negative", index))
                        table_status = "error"

        provenance_counts = summarize_by_provenance(rows)
        for provenance, count in provenance_counts.items():
            aggregate_provenance_counts[provenance] = aggregate_provenance_counts.get(provenance, 0) + count
        total_rows += len(rows)
        tables.append(
            {
                "key": table.key,
                "category": table.category,
                "path": table.path.as_posix(),
                "row_count": len(rows),
                "status": table_status,
                "provenance_counts": provenance_counts,
                "missing_columns": missing_columns,
            }
        )

    if total_rows == 0:
        warnings.append(
            {
                "code": "scaffold_only",
                "message": "Assumption tables are present with schemas but do not yet contain enrichment rows.",
            }
        )

    return {
        "schema": "tiangou.assumptions.validation_summary.v1",
        "status": "error" if errors else "warning" if warnings else "ok",
        "table_count": len(ASSUMPTION_TABLES),
        "row_count": total_rows,
        "provenance_classes": [provenance.value for provenance in ProvenanceClass],
        "provenance_counts": {key: value for key, value in aggregate_provenance_counts.items() if value},
        "tables": tables,
        "warnings": warnings,
        "errors": errors,
    }
