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


def upsert_consumer_proxy_elements(
    conn: sqlite3.Connection,
    *,
    proxies: Iterable[dict[str, Any]],
) -> int:
    count = 0
    for proxy in proxies:
        if proxy.get("lat") is None or proxy.get("lon") is None:
            continue
        conn.execute(
            """
            INSERT INTO consumer_proxy_elements (
                osm_type, osm_id, region_key, proxy_type, sector, weight, weight_method,
                confidence, name, tags_json, geometry_json, lat, lon, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(osm_type, osm_id, region_key, proxy_type) DO UPDATE SET
                sector = excluded.sector,
                weight = excluded.weight,
                weight_method = excluded.weight_method,
                confidence = excluded.confidence,
                name = excluded.name,
                tags_json = excluded.tags_json,
                geometry_json = excluded.geometry_json,
                lat = excluded.lat,
                lon = excluded.lon,
                updated_at = datetime('now')
            """,
            (
                proxy["osm_type"],
                int(proxy["osm_id"]),
                proxy["region_key"],
                proxy["proxy_type"],
                proxy["sector"],
                float(proxy["weight"]),
                proxy.get("weight_method"),
                proxy.get("confidence"),
                proxy.get("name"),
                _json(proxy.get("tags") or {}),
                _json(proxy.get("geometry")),
                proxy.get("lat"),
                proxy.get("lon"),
            ),
        )
        count += 1
    return count


def list_consumer_proxy_elements(
    conn: sqlite3.Connection,
    *,
    region_key: str | None = None,
    sector: str | None = None,
    limit: int = 100000,
    offset: int = 0,
) -> list[sqlite3.Row]:
    clauses = []
    params: list[Any] = []
    if region_key:
        clauses.append("region_key = ?")
        params.append(region_key)
    if sector:
        clauses.append("sector = ?")
        params.append(sector)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    return conn.execute(
        f"""
        SELECT osm_type, osm_id, region_key, proxy_type, sector, weight, weight_method,
               confidence, name, tags_json, geometry_json, lat, lon, updated_at
        FROM consumer_proxy_elements
        {where}
        ORDER BY sector, weight DESC, proxy_type, osm_type, osm_id
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()


def list_consumer_proxy_allocation_rows(
    conn: sqlite3.Connection,
    *,
    region_key: str,
    limit: int = 100000,
    offset: int = 0,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT sector, proxy_type, weight, confidence, lat, lon
        FROM consumer_proxy_elements
        WHERE region_key = ?
          AND lat IS NOT NULL
          AND lon IS NOT NULL
          AND weight > 0
        ORDER BY rowid
        LIMIT ? OFFSET ?
        """,
        (region_key, limit, offset),
    ).fetchall()


def list_consumer_proxy_marker_rows(
    conn: sqlite3.Connection,
    *,
    region_key: str,
    limit: int = 10000,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT osm_type, osm_id, region_key, proxy_type, sector, weight, confidence,
               name, tags_json, lat, lon
        FROM consumer_proxy_elements
        WHERE region_key = ?
          AND lat IS NOT NULL
          AND lon IS NOT NULL
        ORDER BY weight DESC, proxy_type, osm_type, osm_id
        LIMIT ?
        """,
        (region_key, limit),
    ).fetchall()


def list_important_consumer_proxy_marker_rows(
    conn: sqlite3.Connection,
    *,
    region_key: str,
    category_limits: dict[str, int],
) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for reason, limit in category_limits.items():
        if limit <= 0:
            continue
        rows.extend(_list_consumer_proxy_marker_rows_by_reason(conn, region_key=region_key, reason=reason, limit=limit))
    return rows


def _list_consumer_proxy_marker_rows_by_reason(
    conn: sqlite3.Connection,
    *,
    region_key: str,
    reason: str,
    limit: int,
) -> list[sqlite3.Row]:
    text = "lower(coalesce(tags_json, '') || ' ' || coalesce(name, ''))"
    base_where = """
        region_key = ?
        AND lat IS NOT NULL
        AND lon IS NOT NULL
    """
    params: list[Any] = [region_key]
    if reason == "data_center":
        where = f"""
            {base_where}
            AND (
                proxy_type = 'data_center'
                OR {text} LIKE '%data_center%'
                OR {text} LIKE '%data center%'
                OR {text} LIKE '%data_centre%'
                OR {text} LIKE '%data centre%'
                OR {text} LIKE '%"telecom": "data_center"%'
            )
        """
    elif reason == "hospital":
        where = f"""
            {base_where}
            AND (
                proxy_type = 'hospital'
                OR {text} LIKE '%"amenity": "hospital"%'
                OR {text} LIKE '%"building": "hospital"%'
                OR {text} LIKE '%hospital%'
            )
        """
    elif reason == "charging_station":
        where = f"""
            {base_where}
            AND (
                proxy_type = 'charging_station'
                OR {text} LIKE '%"amenity": "charging_station"%'
            )
        """
    elif reason == "transport":
        where = f"""
            {base_where}
            AND proxy_type IN ('station', 'ferry_terminal', 'aerodrome', 'terminal')
        """
    elif reason == "industrial_infrastructure":
        where = f"""
            {base_where}
            AND proxy_type IN ('works', 'water_works', 'wastewater_plant')
        """
    elif reason == "large_industrial_proxy":
        where = f"""
            {base_where}
            AND sector = 'industrial'
            AND proxy_type IN ('building', 'landuse')
        """
    elif reason == "large_commercial_proxy":
        where = f"""
            {base_where}
            AND sector = 'commercial'
            AND proxy_type IN ('building', 'landuse', 'office', 'mall')
        """
    else:
        raise ValueError(f"Unknown important consumer proxy marker reason: {reason}")

    params.append(limit)
    return conn.execute(
        f"""
        SELECT osm_type, osm_id, region_key, proxy_type, sector, weight, confidence,
               name, lat, lon, ? AS reason
        FROM consumer_proxy_elements
        WHERE {where}
        ORDER BY weight DESC, proxy_type, osm_type, osm_id
        LIMIT ?
        """,
        [reason, *params],
    ).fetchall()


def consumer_proxy_signature(conn: sqlite3.Connection, region_key: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count, MAX(updated_at) AS latest_updated_at
        FROM consumer_proxy_elements
        WHERE region_key = ?
        """,
        (region_key,),
    ).fetchone()
    return {
        "count": int(row["count"] or 0),
        "latest_updated_at": row["latest_updated_at"],
    }


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


def latest_ingest_run(conn: sqlite3.Connection, region_key: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, region_key, started_at, completed_at, element_count, status, error
        FROM ingest_runs
        WHERE region_key = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (region_key,),
    ).fetchone()
