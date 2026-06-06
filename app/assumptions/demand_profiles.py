from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from typing import Any

from app.assumptions.provenance import TABLES_BY_KEY, read_table_rows, table_payload


DEMAND_PROFILE_TABLE_KEYS = (
    "hong_kong_sector_hourly_profiles",
    "weather_sensitivity_profiles",
)

DEFAULT_SECTOR = "commercial"


def demand_profile_assumption_tables() -> list[dict]:
    return [table_payload(TABLES_BY_KEY[key]) for key in DEMAND_PROFILE_TABLE_KEYS]


@lru_cache(maxsize=1)
def _hourly_profiles_by_sector() -> dict[str, dict[str, Any]]:
    _, rows = read_table_rows(TABLES_BY_KEY["hong_kong_sector_hourly_profiles"])
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["sector"]].append(row)

    profiles: dict[str, dict[str, Any]] = {}
    for sector, sector_rows in grouped.items():
        ordered = sorted(sector_rows, key=lambda row: int(row["hour"]))
        total = sum(float(row["base_share"]) for row in ordered)
        shares = [float(row["base_share"]) / total for row in ordered] if total > 0 else [1.0 / 24.0] * 24
        peak_hour = max(range(len(shares)), key=lambda hour: shares[hour])
        first = ordered[0]
        profiles[sector] = {
            "profile_id": first["profile_id"],
            "sector": sector,
            "shares": shares,
            "peak_hour": peak_hour,
            "weekday_factor": float(first["weekday_factor"]),
            "weekend_factor": float(first["weekend_factor"]),
            "cooling_sensitivity": float(first["cooling_sensitivity"]),
            "profile_provenance": first["provenance"],
            "profile_confidence": float(first["confidence"]),
            "profile_method": first["method"],
            "profile_source": first["source"],
            "profile_assumptions": first["assumptions"],
            "date_or_year": first["date_or_year"],
        }
    return profiles


def hourly_profile_summary() -> dict[str, Any]:
    return {
        sector: {
            key: value
            for key, value in profile.items()
            if key != "shares"
        }
        | {"share_sum": round(sum(profile["shares"]), 6)}
        for sector, profile in _hourly_profiles_by_sector().items()
    }


def hourly_load_metadata(sector: str | None, peak_pd_mw: float | None, fallback_pd_mw: float) -> dict[str, Any]:
    profile = demand_profile_for_sector(sector)
    peak_mw = float(peak_pd_mw if peak_pd_mw is not None and peak_pd_mw > 0 else fallback_pd_mw)
    peak_share = max(profile["shares"]) if profile["shares"] else 1.0
    hourly = [round(peak_mw * share / peak_share, 3) for share in profile["shares"]]
    if hourly:
        peak_hour = max(range(len(hourly)), key=lambda hour: hourly[hour])
    else:
        peak_hour = None

    return {
        "hourly_pd_mw": hourly,
        "peak_hour": peak_hour,
        "load_profile_id": profile["profile_id"],
        "profile_sector": profile["sector"],
        "profile_provenance": profile["profile_provenance"],
        "profile_confidence": profile["profile_confidence"],
        "profile_method": profile["profile_method"],
        "profile_source": profile["profile_source"],
        "profile_assumptions": profile["profile_assumptions"],
        "weekday_factor": profile["weekday_factor"],
        "weekend_factor": profile["weekend_factor"],
        "cooling_sensitivity": profile["cooling_sensitivity"],
    }


def demand_profile_for_sector(sector: str | None) -> dict[str, Any]:
    profiles = _hourly_profiles_by_sector()
    if sector and sector in profiles:
        return profiles[sector]
    return profiles.get(DEFAULT_SECTOR) or next(iter(profiles.values()))
