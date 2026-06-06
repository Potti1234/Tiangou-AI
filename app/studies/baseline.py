from __future__ import annotations

from typing import Any, Mapping


def build_baseline_weak_spots(
    case: Mapping[str, Any],
    validation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic demo weak-spot metrics from a PowerModels case."""

    validation = validation or {}
    metadata = dict(case.get("_metadata") or {})
    buses = {str(key): dict(value) for key, value in (case.get("bus") or {}).items()}
    branches = {str(key): dict(value) for key, value in (case.get("branch") or {}).items()}
    loads = {str(key): dict(value) for key, value in (case.get("load") or {}).items()}
    generators = {str(key): dict(value) for key, value in (case.get("gen") or {}).items()}

    load_by_bus = _sum_by_bus(loads, "load_bus", "pd", scale=100.0)
    gen_by_bus = _sum_by_bus(generators, "gen_bus", "pmax", scale=100.0)
    incident_count: dict[int, int] = {}
    for branch in branches.values():
        for key in ("f_bus", "t_bus"):
            bus = _int_or_none(branch.get(key))
            if bus is not None:
                incident_count[bus] = incident_count.get(bus, 0) + 1

    mismatch_source_ids = {
        str(item.get("source_id"))
        for item in validation.get("voltage_mismatches", [])
        if isinstance(item, Mapping) and item.get("source_id") is not None
    }

    branch_risks = [
        _branch_risk(branch_id, branch, buses, load_by_bus, mismatch_source_ids)
        for branch_id, branch in branches.items()
    ]
    bus_risks = [
        _bus_risk(bus_id, bus, load_by_bus, gen_by_bus, incident_count)
        for bus_id, bus in buses.items()
    ]

    branch_risks.sort(key=lambda item: (-item["risk_score"], item["branch_id"]))
    bus_risks.sort(key=lambda item: (-item["risk_score"], item["bus_id"]))

    total_demand_mw = _metadata_float(metadata, "total_pd_mw", sum(load_by_bus.values()))
    total_pmax_mw = _metadata_float(metadata, "total_pmax_mw", sum(gen_by_bus.values()))
    branch_count = max(len(branches), 1)
    provenance_summary = metadata.get("provenance_summary") if isinstance(metadata.get("provenance_summary"), Mapping) else {}
    branch_provenance = provenance_summary.get("branch") if isinstance(provenance_summary.get("branch"), Mapping) else {}
    synthetic_branch_count = sum(
        int(count)
        for provenance, count in branch_provenance.items()
        if "synthetic" in str(provenance)
    )
    inferred_voltage_count = _metadata_nested_int(metadata, "voltage_inference", "inferred")

    return {
        "schema": "tiangou.study.baseline_weak_spots.v1",
        "study_type": "heuristic_research_demo",
        "system_summary": {
            "total_demand_mw": round(total_demand_mw, 3),
            "total_pmax_mw": round(total_pmax_mw, 3),
            "reserve_margin_estimate": round((total_pmax_mw - total_demand_mw) / total_demand_mw, 6) if total_demand_mw > 0 else None,
            "synthetic_branch_share": round(synthetic_branch_count / branch_count, 6),
            "synthetic_branch_count": synthetic_branch_count,
            "inferred_voltage_count": inferred_voltage_count,
            "promoted_generator_count": int(metadata.get("tagged_gen_count") or 0),
            "warning_count": len(validation.get("warnings") or []),
            "top_10_risky_branches": branch_risks[:10],
            "top_10_risky_buses": bus_risks[:10],
            "warnings": [
                "Heuristic research/demo scores only; no OPF, hosting-capacity, site-ranking, or N-1 optimization is performed.",
                "Load proximity uses directly connected bus demand only when downstream topology is not available.",
            ],
        },
        "branch_risks": branch_risks,
        "bus_risks": bus_risks,
    }


def _sum_by_bus(items: Mapping[str, Mapping[str, Any]], bus_key: str, value_key: str, *, scale: float) -> dict[int, float]:
    totals: dict[int, float] = {}
    for item in items.values():
        bus = _int_or_none(item.get(bus_key))
        value = _float_or_none(item.get(value_key))
        if bus is None or value is None:
            continue
        totals[bus] = totals.get(bus, 0.0) + value * scale
    return totals


def _branch_risk(
    branch_id: str,
    branch: Mapping[str, Any],
    buses: Mapping[str, Mapping[str, Any]],
    load_by_bus: Mapping[int, float],
    mismatch_source_ids: set[str],
) -> dict[str, Any]:
    f_bus = _int_or_none(branch.get("f_bus"))
    t_bus = _int_or_none(branch.get("t_bus"))
    connected_load_mw = (load_by_bus.get(f_bus or -1, 0.0) + load_by_bus.get(t_bus or -1, 0.0))
    rate_mva = _float_or_none(branch.get("rate_a")) or 0.0
    source_id = str(branch.get("source_id") or branch_id)
    provenance = str(branch.get("provenance") or "unknown")
    confidence = _float_or_none(branch.get("confidence"))
    voltage_kv = _float_or_none(branch.get("matched_voltage_kv"))
    generator_connection = provenance == "synthetic_connection_to_nearest_substation"
    synthetic = "synthetic" in provenance or source_id.startswith("synthetic:")
    inferred_voltage = "inferred" in provenance or branch.get("voltage_inferred") is True
    voltage_mismatch = source_id in mismatch_source_ids

    score = 0.0
    reasons: list[str] = []
    if confidence is not None and confidence < 0.5:
        score += 18.0
        reasons.append("low confidence")
    if synthetic:
        score += 18.0
        reasons.append("synthetic branch")
    if generator_connection:
        score += 14.0
        reasons.append("synthetic generator connection")
    if inferred_voltage:
        score += 12.0
        reasons.append("inferred voltage")
    if connected_load_mw >= 500:
        score += min(22.0, connected_load_mw / 75.0)
        reasons.append("high connected demand")
    if rate_mva > 0 and connected_load_mw / rate_mva > 0.8:
        score += min(20.0, (connected_load_mw / rate_mva - 0.8) * 25.0)
        reasons.append("low rate relative to connected demand")
    if voltage_mismatch:
        score += 22.0
        reasons.append("voltage mismatch")

    return {
        "branch_id": branch_id,
        "source_id": source_id,
        "from_bus": f_bus,
        "to_bus": t_bus,
        "from_bus_source_id": _bus_source_id(buses, f_bus),
        "to_bus_source_id": _bus_source_id(buses, t_bus),
        "voltage_kv": voltage_kv,
        "rate_mva": rate_mva,
        "provenance": provenance,
        "confidence": confidence,
        "length_km": _float_or_none(branch.get("length_km")),
        "load_proximity_mw": round(connected_load_mw, 3),
        "generator_connection": generator_connection,
        "voltage_mismatch": voltage_mismatch,
        "risk_score": round(min(100.0, score), 2),
        "reasons": reasons or ["no major heuristic flags"],
    }


def _bus_risk(
    bus_id: str,
    bus: Mapping[str, Any],
    load_by_bus: Mapping[int, float],
    gen_by_bus: Mapping[int, float],
    incident_count: Mapping[int, int],
) -> dict[str, Any]:
    bus_number = _int_or_none(bus.get("bus_i")) or _int_or_none(bus_id) or 0
    connected_load_mw = load_by_bus.get(bus_number, 0.0)
    connected_gen_mw = gen_by_bus.get(bus_number, 0.0)
    incidents = incident_count.get(bus_number, 0)
    provenance = str(bus.get("provenance") or "unknown")
    confidence = _float_or_none(bus.get("confidence"))

    score = 0.0
    reasons: list[str] = []
    if connected_load_mw >= 500:
        score += min(28.0, connected_load_mw / 55.0)
        reasons.append("high connected load")
    if connected_load_mw > 0 and connected_gen_mw <= 0:
        score += 14.0
        reasons.append("no local generator at bus")
    if connected_load_mw > 0 and incidents <= 1:
        score += 24.0
        reasons.append("single-branch radial connection")
    elif connected_load_mw > 0 and incidents <= 2:
        score += 12.0
        reasons.append("few incident branches")
    if confidence is not None and confidence < 0.5:
        score += 14.0
        reasons.append("low confidence")
    if "synthetic" in provenance or "inferred" in provenance:
        score += 10.0
        reasons.append("synthetic or inferred dependency")

    return {
        "bus_id": bus_id,
        "source_id": bus.get("source_id"),
        "connected_load_mw": round(connected_load_mw, 3),
        "connected_generator_pmax_mw": round(connected_gen_mw, 3),
        "incident_branch_count": incidents,
        "voltage_kv": _float_or_none(bus.get("base_kv")),
        "service_territory": bus.get("service_territory"),
        "consumer_proxy_density": None,
        "provenance": provenance,
        "confidence": confidence,
        "risk_score": round(min(100.0, score), 2),
        "reasons": reasons or ["no major heuristic flags"],
    }


def _bus_source_id(buses: Mapping[str, Mapping[str, Any]], bus_number: int | None) -> Any:
    if bus_number is None:
        return None
    bus = buses.get(str(bus_number))
    return bus.get("source_id") if bus else None


def _metadata_float(metadata: Mapping[str, Any], key: str, fallback: float) -> float:
    value = _float_or_none(metadata.get(key))
    return fallback if value is None else value


def _metadata_nested_int(metadata: Mapping[str, Any], key: str, nested_key: str) -> int:
    nested = metadata.get(key)
    if not isinstance(nested, Mapping):
        return 0
    value = nested.get(nested_key)
    return int(value) if isinstance(value, int | float) else 0


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
