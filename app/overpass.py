import json
from typing import Any

import httpx

from app.config import settings
from app.load_proxies import consumer_proxy_query_filters
from app.regions import Region


POWER_VALUES = (
    "plant",
    "generator",
    "substation",
    "sub_station",
    "transformer",
    "line",
    "minor_line",
    "cable",
    "tower",
    "pole",
    "portal",
    "switch",
    "switchgear",
    "terminal",
    "converter",
    "compensator",
    "busbar",
    "bay",
    "insulator",
)


class OverpassError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_power_query(region: Region, timeout_seconds: int = 120) -> str:
    area_blocks = []
    query_lines = []
    for index, area_name in enumerate(region.area_names):
        ref = f".area{index}"
        escaped_name = _quote(area_name)
        area_blocks.append(
            "\n".join(
                (
                    "(",
                    f'  area["boundary"="administrative"]["name"={escaped_name}];',
                    f'  area["boundary"="administrative"]["name:en"={escaped_name}];',
                    f")->{ref};",
                )
            )
        )

    power_regex = "|".join(POWER_VALUES)
    for index in range(len(region.area_names)):
        area_ref = f"area.area{index}"
        query_lines.extend(
            (
                f'  nwr["power"~"^({power_regex})$"]({area_ref});',
                f'  nwr["voltage"]({area_ref});',
                f'  nwr["substation"]({area_ref});',
                f'  nwr["generator:source"]({area_ref});',
                f'  nwr["generator:method"]({area_ref});',
            )
        )

    return f"""[out:json][timeout:{timeout_seconds}];
{chr(10).join(area_blocks)}
(
{chr(10).join(query_lines)}
);
out body geom;
"""


def build_consumer_proxy_query(region: Region, *, group: str | None = None, timeout_seconds: int = 180) -> str:
    area_blocks = []
    query_lines = []
    filters = consumer_proxy_query_filters(group)
    for index, area_name in enumerate(region.area_names):
        ref = f".area{index}"
        escaped_name = _quote(area_name)
        area_blocks.append(
            "\n".join(
                (
                    "(",
                    f'  area["boundary"="administrative"]["name"={escaped_name}];',
                    f'  area["boundary"="administrative"]["name:en"={escaped_name}];',
                    f")->{ref};",
                )
            )
        )
    for index in range(len(region.area_names)):
        area_ref = f"area.area{index}"
        for key, value in filters:
            if value is None:
                query_lines.append(f'  nwr["{key}"]({area_ref});')
            else:
                query_lines.append(f'  nwr["{key}"="{value}"]({area_ref});')
    return f"""[out:json][timeout:{timeout_seconds}];
{chr(10).join(area_blocks)}
(
{chr(10).join(query_lines)}
);
out body center geom;
"""


class OverpassClient:
    def __init__(
        self,
        url: str = settings.overpass_url,
        timeout_seconds: float = settings.overpass_timeout_seconds,
    ) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def fetch(self, query: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                self.url,
                data={"data": query},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "TiangouAI/0.1 hackathon grid ingestion",
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                body = response.text.strip()
                detail = body[:800] if body else str(exc)
                raise OverpassError(
                    f"Overpass returned HTTP {response.status_code}: {detail}",
                    status_code=response.status_code,
                ) from exc
            return response.json()
