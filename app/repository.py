import json
import sqlite3
from collections.abc import Iterable
from typing import Any


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _point(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]

    geometry = element.get("geometry")
    if isinstance(geometry, list) and geometry:
        lats = [point["lat"] for point in geometry if "lat" in point]
        lons = [point["lon"] for point in geometry if "lon" in point]
        if lats and lons:
            return sum(lats) / len(lats), sum(lons) / len(lons)

    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return center["lat"], center["lon"]

    return None, None


def create_ingest_run(conn: sqlite3.Connection, region_key: str, query: str) -> int:
    cursor = conn.execute(
        "INSERT INTO ingest_runs (region_key, query) VALUES (?, ?)",
        (region_key, query),
    )
    return int(cursor.lastrowid)


def complete_ingest_run(
    conn: sqlite3.Connection,
    ingest_run_id: int,
    status: str,
    element_count: int,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE ingest_runs
        SET completed_at = datetime('now'), status = ?, element_count = ?, error = ?
        WHERE id = ?
        """,
        (status, element_count, error, ingest_run_id),
    )


def upsert_elements(
    conn: sqlite3.Connection,
    *,
    region_key: str,
    ingest_run_id: int,
    elements: Iterable[dict[str, Any]],
) -> int:
    count = 0
    for element in elements:
        tags = element.get("tags") or {}
        power = tags.get("power")
        if not power:
            continue

        lat, lon = _point(element)
        conn.execute(
            """
            INSERT INTO osm_elements (
                osm_type, osm_id, power, name, voltage, operator, frequency,
                cables, circuits, location, tags_json, geometry_json, lat, lon, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(osm_type, osm_id) DO UPDATE SET
                power = excluded.power,
                name = excluded.name,
                voltage = excluded.voltage,
                operator = excluded.operator,
                frequency = excluded.frequency,
                cables = excluded.cables,
                circuits = excluded.circuits,
                location = excluded.location,
                tags_json = excluded.tags_json,
                geometry_json = excluded.geometry_json,
                lat = excluded.lat,
                lon = excluded.lon,
                updated_at = datetime('now')
            """,
            (
                element["type"],
                element["id"],
                power,
                tags.get("name") or tags.get("name:en"),
                tags.get("voltage"),
                tags.get("operator"),
                tags.get("frequency"),
                tags.get("cables"),
                tags.get("circuits"),
                tags.get("location"),
                _json(tags),
                _json(element.get("geometry")),
                lat,
                lon,
            ),
        )
        conn.execute(
            """
            INSERT INTO element_regions (osm_type, osm_id, region_key, ingest_run_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(osm_type, osm_id, region_key) DO UPDATE SET
                ingest_run_id = excluded.ingest_run_id
            """,
            (element["type"], element["id"], region_key, ingest_run_id),
        )
        count += 1
    return count


def list_elements(
    conn: sqlite3.Connection,
    *,
    region_key: str | None = None,
    power: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[Any] = []
    join = ""
    if region_key:
        join = """
        JOIN element_regions er
            ON er.osm_type = e.osm_type AND er.osm_id = e.osm_id
        """
        clauses.append("er.region_key = ?")
        params.append(region_key)
    if power:
        clauses.append("e.power = ?")
        params.append(power)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    return conn.execute(
        f"""
        SELECT e.osm_type, e.osm_id, e.power, e.name, e.voltage, e.operator,
               e.frequency, e.cables, e.circuits, e.location, e.lat, e.lon,
               e.tags_json, e.geometry_json, e.updated_at
        FROM osm_elements e
        {join}
        {where}
        ORDER BY e.power, e.name, e.osm_type, e.osm_id
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()


def get_element(
    conn: sqlite3.Connection,
    *,
    osm_type: str,
    osm_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM osm_elements
        WHERE osm_type = ? AND osm_id = ?
        """,
        (osm_type, osm_id),
    ).fetchone()


def summarize(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT er.region_key, e.power, COUNT(*) AS count
        FROM osm_elements e
        JOIN element_regions er
            ON er.osm_type = e.osm_type AND er.osm_id = e.osm_id
        GROUP BY er.region_key, e.power
        ORDER BY er.region_key, count DESC, e.power
        """
    ).fetchall()
