import json
from typing import Any

import httpx

from app.config import settings
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


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_power_query(region: Region, timeout_seconds: int = 120) -> str:
    area_blocks = []
    area_refs = []
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
        area_refs.append(ref)

    area_union = "\n".join(area_refs)
    power_regex = "|".join(POWER_VALUES)

    return f"""[out:json][timeout:{timeout_seconds}];
{chr(10).join(area_blocks)}
(
{area_union}
)->.searchAreas;
(
  nwr["power"~"^({power_regex})$"](area.searchAreas);
  nwr["voltage"](area.searchAreas);
  nwr["substation"](area.searchAreas);
  nwr["generator:source"](area.searchAreas);
  nwr["generator:method"](area.searchAreas);
);
out body geom;
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
            response = await client.post(self.url, data={"data": query})
            response.raise_for_status()
            return response.json()
