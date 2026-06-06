import argparse
import asyncio
import json
from typing import Any

import httpx

from app.database import get_db, init_db
from app.load_proxies import PROXY_GROUPS, normalize_consumer_proxy_element
from app.overpass import OverpassClient, OverpassError, build_consumer_proxy_query
from app.regions import get_region
from app.repository import complete_ingest_run, create_ingest_run, upsert_consumer_proxy_elements


async def ingest_consumer_proxies(region_key: str, *, groups: tuple[str, ...] | None = None) -> dict[str, Any]:
    init_db()
    region = get_region(region_key)
    selected_groups = groups or tuple(PROXY_GROUPS)
    client = OverpassClient()
    total_fetched = 0
    total_stored = 0
    results = []
    errors = []
    for group in selected_groups:
        query = build_consumer_proxy_query(region, group=group)
        with get_db() as conn:
            ingest_run_id = create_ingest_run(conn, region.key, query)
        try:
            payload = await client.fetch(query)
            elements = payload.get("elements", [])
            proxies = [
                proxy
                for element in elements
                if (proxy := normalize_consumer_proxy_element(element, region_key=region.key)) is not None
            ]
            with get_db() as conn:
                stored_count = upsert_consumer_proxy_elements(conn, proxies=proxies)
                complete_ingest_run(conn, ingest_run_id, "completed", stored_count)
            total_fetched += len(elements)
            total_stored += stored_count
            results.append({"group": group, "ingest_run_id": ingest_run_id, "status": "completed", "fetched_count": len(elements), "stored_count": stored_count})
        except (OverpassError, httpx.HTTPError) as exc:
            error = str(exc)
            with get_db() as conn:
                complete_ingest_run(conn, ingest_run_id, "failed", 0, error)
            errors.append({"group": group, "error": error})
            results.append({"group": group, "ingest_run_id": ingest_run_id, "status": "failed", "fetched_count": 0, "stored_count": 0, "error": error})
    return {
        "region_key": region.key,
        "status": "partial" if errors and total_stored else "failed" if errors else "completed",
        "fetched_count": total_fetched,
        "stored_count": total_stored,
        "groups": results,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest OSM consumer/load proxy features for a region.")
    parser.add_argument("region_key")
    parser.add_argument("--groups", help=f"Comma-separated groups. Known groups: {', '.join(PROXY_GROUPS)}")
    args = parser.parse_args()
    groups = tuple(token.strip() for token in args.groups.split(",") if token.strip()) if args.groups else None
    result = asyncio.run(ingest_consumer_proxies(args.region_key, groups=groups))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
