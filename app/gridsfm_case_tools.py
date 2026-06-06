from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


BASE_MVA_FALLBACK = 100.0
DEFAULT_SHUNT_CAP_PU = 0.08
SHORT_SYNTHETIC_BRANCH_KM = 6.0


def load_powermodels_case(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_diagnostic_report(case_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    case = load_powermodels_case(case_path)
    report = diagnose_powermodels_case(case, source_path=case_path)
    target_dir = output_dir or case_path.parent / "diagnostics"
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / f"{case_path.stem}.gridsfm_diagnostics.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return {**report, "report_path": str(report_path)}


def diagnose_powermodels_case(case: Mapping[str, Any], *, source_path: Path | None = None) -> dict[str, Any]:
    buses = _dict_values(case.get("bus"))
    branches = _dict_values(case.get("branch"))
    gens = _dict_values(case.get("gen"))
    loads = _dict_values(case.get("load"))
    base_mva = float(case.get("baseMVA") or BASE_MVA_FALLBACK)
    islands = _island_report(buses, branches, gens, loads, base_mva)
    voltage_mismatches = _voltage_mismatches(buses, branches)
    shunt_rows = [_branch_shunt_row(branch) for branch in branches]
    impedance_rows = [_branch_impedance_row(branch) for branch in branches]
    diagnostics = {
        "source_path": str(source_path) if source_path is not None else None,
        "summary": {
            "bus_count": len(buses),
            "branch_count": len(branches),
            "gen_count": len(gens),
            "load_count": len(loads),
            "component_count": len(islands),
            "passive_island_count": sum(1 for island in islands if island["load_count"] == 0 and island["gen_count"] == 0),
            "voltage_mismatch_count": len(voltage_mismatches),
            "extreme_shunt_branch_count": sum(1 for row in shunt_rows if row["abs_total_b_pu"] > DEFAULT_SHUNT_CAP_PU),
            "invalid_generator_range_count": len(_generator_range_issues(gens)),
            "unrealistic_base_kv_bus_count": len(_unrealistic_base_kv_buses(buses)),
            "total_abs_branch_shunt_b_pu": round(sum(row["abs_total_b_pu"] for row in shunt_rows), 8),
        },
        "islands": islands,
        "passive_islands": [island for island in islands if island["load_count"] == 0 and island["gen_count"] == 0],
        "voltage_mismatches": voltage_mismatches,
        "extreme_parameters": {
            "low_resistance": _top_rows(impedance_rows, "br_r", reverse=False),
            "low_reactance": _top_rows(impedance_rows, "br_x", reverse=False),
            "high_shunt": _top_rows(shunt_rows, "abs_total_b_pu", reverse=True),
            "low_rate": _top_rows(impedance_rows, "rate_a", reverse=False),
        },
        "transformers": [_transformer_row(branch) for branch in branches if branch.get("transformer") or float(branch.get("tap") or 1.0) != 1.0],
        "generator_range_issues": _generator_range_issues(gens),
        "unrealistic_base_kv_buses": _unrealistic_base_kv_buses(buses),
        "branch_charging_by_voltage_and_class": _branch_charging_groups(branches),
        "top_branch_shunts": _top_rows(shunt_rows, "abs_total_b_pu", reverse=True),
        "top_impedance_extremes": _top_impedance_extremes(impedance_rows),
        "likely_ac_feasibility_blockers": _likely_blockers(islands, voltage_mismatches, shunt_rows, gens, buses),
    }
    return diagnostics


def sanitize_powermodels_case_for_ac(case: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = copy.deepcopy(dict(case))
    actions: list[dict[str, Any]] = []
    _remove_passive_islands(sanitized, actions)
    _sanitize_branch_shunts(sanitized, actions)
    _widen_generator_q_ranges(sanitized, actions)
    _ensure_reference_buses(sanitized, actions)
    action_counts = Counter(action["action"] for action in actions)
    metadata = sanitized.setdefault("_metadata", {})
    metadata["solver_sanitized"] = True
    metadata["sanitization_actions"] = actions
    metadata["sanitization_action_counts"] = dict(sorted(action_counts.items()))
    metadata["solver_sanitization_summary"] = {
        "solver_sanitized": True,
        "action_count": len(actions),
        "action_counts": dict(sorted(action_counts.items())),
        "bus_count": len(sanitized.get("bus") or {}),
        "branch_count": len(sanitized.get("branch") or {}),
        "gen_count": len(sanitized.get("gen") or {}),
        "load_count": len(sanitized.get("load") or {}),
    }
    sanitized["solver_sanitized"] = True
    sanitized["sanitization_actions"] = actions
    return sanitized


def _dict_values(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(item) for item in value.values() if isinstance(item, Mapping)]
    return []


def _island_report(
    buses: list[Mapping[str, Any]],
    branches: list[Mapping[str, Any]],
    gens: list[Mapping[str, Any]],
    loads: list[Mapping[str, Any]],
    base_mva: float,
) -> list[dict[str, Any]]:
    adjacency = {int(bus["bus_i"]): set() for bus in buses if "bus_i" in bus}
    for branch in branches:
        if int(branch.get("br_status", 1)) == 0:
            continue
        f_bus = int(branch["f_bus"])
        t_bus = int(branch["t_bus"])
        if f_bus in adjacency and t_bus in adjacency:
            adjacency[f_bus].add(t_bus)
            adjacency[t_bus].add(f_bus)
    load_by_bus = Counter(int(load["load_bus"]) for load in loads)
    gen_by_bus = Counter(int(gen["gen_bus"]) for gen in gens)
    pd_by_bus: dict[int, float] = defaultdict(float)
    pmax_by_bus: dict[int, float] = defaultdict(float)
    for load in loads:
        pd_by_bus[int(load["load_bus"])] += float(load.get("pd") or 0.0) * base_mva
    for gen in gens:
        pmax_by_bus[int(gen["gen_bus"])] += float(gen.get("pmax") or 0.0) * base_mva
    seen: set[int] = set()
    islands = []
    for bus_id in sorted(adjacency):
        if bus_id in seen:
            continue
        stack = [bus_id]
        component: set[int] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency[current] - component)
        seen.update(component)
        islands.append(
            {
                "bus_ids": sorted(component),
                "bus_count": len(component),
                "load_count": sum(load_by_bus[bus] for bus in component),
                "gen_count": sum(gen_by_bus[bus] for bus in component),
                "pd_mw": round(sum(pd_by_bus[bus] for bus in component), 3),
                "pmax_mw": round(sum(pmax_by_bus[bus] for bus in component), 3),
            }
        )
    return islands


def _voltage_mismatches(buses: list[Mapping[str, Any]], branches: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    bus_by_i = {int(bus["bus_i"]): bus for bus in buses if "bus_i" in bus}
    rows = []
    for branch in branches:
        if branch.get("transformer"):
            continue
        matched_voltage = branch.get("matched_voltage_kv")
        if matched_voltage is None:
            continue
        endpoints = []
        for field in ("f_bus", "t_bus"):
            bus = bus_by_i.get(int(branch[field]))
            base_kv = bus.get("base_kv") if bus else None
            if base_kv is None:
                continue
            relative = abs(float(base_kv) - float(matched_voltage)) / max(float(matched_voltage), 1e-9)
            if relative > 0.15:
                endpoints.append({"endpoint": field, "bus_i": int(branch[field]), "bus_base_kv": base_kv, "relative_difference": round(relative, 6)})
        if endpoints:
            rows.append({"branch_id": str(branch.get("index")), "source_id": branch.get("source_id"), "matched_voltage_kv": matched_voltage, "endpoints": endpoints})
    return rows


def _branch_shunt_row(branch: Mapping[str, Any]) -> dict[str, Any]:
    b_fr = float(branch.get("b_fr") or 0.0)
    b_to = float(branch.get("b_to") or 0.0)
    return {
        "branch_id": str(branch.get("index")),
        "source_id": branch.get("source_id"),
        "source_power": branch.get("source_power"),
        "circuit_class": branch.get("circuit_class"),
        "matched_voltage_kv": branch.get("matched_voltage_kv"),
        "length_km": branch.get("length_km"),
        "b_fr": b_fr,
        "b_to": b_to,
        "abs_total_b_pu": round(abs(b_fr) + abs(b_to), 8),
        "parameter_source": branch.get("parameter_source"),
        "provenance": branch.get("provenance"),
    }


def _branch_impedance_row(branch: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "branch_id": str(branch.get("index")),
        "source_id": branch.get("source_id"),
        "br_r": float(branch.get("br_r") or 0.0),
        "br_x": float(branch.get("br_x") or 0.0),
        "rate_a": float(branch.get("rate_a") or 0.0),
        "length_km": branch.get("length_km"),
        "source_power": branch.get("source_power"),
        "circuit_class": branch.get("circuit_class"),
        "transformer": bool(branch.get("transformer")),
    }


def _top_rows(rows: list[dict[str, Any]], key: str, *, reverse: bool) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: float(row.get(key) or 0.0), reverse=reverse)[:20]


def _top_impedance_extremes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: min(abs(float(row["br_r"])), abs(float(row["br_x"]))))
    return ranked[:20]


def _transformer_row(branch: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "branch_id": str(branch.get("index")),
        "source_id": branch.get("source_id"),
        "tap": branch.get("tap"),
        "tap_side": branch.get("tap_side"),
        "tap_min": branch.get("tap_min"),
        "tap_max": branch.get("tap_max"),
        "matched_primary_kv": branch.get("matched_primary_kv"),
        "matched_secondary_kv": branch.get("matched_secondary_kv"),
        "transformer_inference": branch.get("transformer_inference"),
    }


def _generator_range_issues(gens: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    for gen in gens:
        pmin = float(gen.get("pmin") or 0.0)
        pmax = float(gen.get("pmax") or 0.0)
        qmin = float(gen.get("qmin") or 0.0)
        qmax = float(gen.get("qmax") or 0.0)
        if pmax <= 0 or pmin > pmax or qmin >= qmax:
            issues.append({"gen_id": str(gen.get("index")), "source_id": gen.get("source_id"), "pmin": pmin, "pmax": pmax, "qmin": qmin, "qmax": qmax})
    return issues


def _unrealistic_base_kv_buses(buses: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for bus in buses:
        base_kv = bus.get("base_kv")
        if base_kv is None or float(base_kv) <= 0 or float(base_kv) > 800:
            rows.append({"bus_id": str(bus.get("bus_i")), "source_id": bus.get("source_id"), "base_kv": base_kv})
    return rows


def _branch_charging_groups(branches: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any], dict[str, Any]] = {}
    for branch in branches:
        key = (branch.get("matched_voltage_kv"), branch.get("circuit_class") or branch.get("source_power"))
        row = grouped.setdefault(key, {"matched_voltage_kv": key[0], "class": key[1], "branch_count": 0, "abs_total_b_pu": 0.0})
        row["branch_count"] += 1
        row["abs_total_b_pu"] += abs(float(branch.get("b_fr") or 0.0)) + abs(float(branch.get("b_to") or 0.0))
    return sorted(({**row, "abs_total_b_pu": round(row["abs_total_b_pu"], 8)} for row in grouped.values()), key=lambda row: row["abs_total_b_pu"], reverse=True)


def _likely_blockers(
    islands: list[Mapping[str, Any]],
    voltage_mismatches: list[Mapping[str, Any]],
    shunt_rows: list[Mapping[str, Any]],
    gens: list[Mapping[str, Any]],
    buses: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    blockers = []
    passive = [island for island in islands if island["load_count"] == 0 and island["gen_count"] == 0]
    if passive:
        blockers.append({"code": "passive_islands", "severity": "warning", "count": len(passive), "message": "Disconnected islands with no load or generation can confuse AC handoff checks."})
    high_shunt = [row for row in shunt_rows if float(row["abs_total_b_pu"]) > DEFAULT_SHUNT_CAP_PU]
    if high_shunt:
        blockers.append({"code": "large_branch_shunts", "severity": "warning", "count": len(high_shunt), "message": "Large inferred branch charging can drive reactive infeasibility in the AC relaxation."})
    if voltage_mismatches:
        blockers.append({"code": "voltage_mismatch_branches", "severity": "warning", "count": len(voltage_mismatches), "message": "Non-transformer branches connect buses whose base_kv differs from the matched branch voltage."})
    range_issues = _generator_range_issues(gens)
    if range_issues:
        blockers.append({"code": "invalid_generator_ranges", "severity": "error", "count": len(range_issues), "message": "Generator operating ranges are structurally invalid."})
    bad_kv = _unrealistic_base_kv_buses(buses)
    if bad_kv:
        blockers.append({"code": "unrealistic_base_kv", "severity": "error", "count": len(bad_kv), "message": "Buses have missing, non-positive, or implausibly high base_kv."})
    return blockers


def _remove_passive_islands(case: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    buses = _dict_values(case.get("bus"))
    branches = _dict_values(case.get("branch"))
    gens = _dict_values(case.get("gen"))
    loads = _dict_values(case.get("load"))
    islands = _island_report(buses, branches, gens, loads, float(case.get("baseMVA") or BASE_MVA_FALLBACK))
    passive_bus_ids = {bus_id for island in islands if island["load_count"] == 0 and island["gen_count"] == 0 for bus_id in island["bus_ids"]}
    if not passive_bus_ids:
        return
    bus = case.get("bus") or {}
    branch = case.get("branch") or {}
    removed_buses = [key for key, value in bus.items() if int(value["bus_i"]) in passive_bus_ids]
    removed_branches = [key for key, value in branch.items() if int(value["f_bus"]) in passive_bus_ids or int(value["t_bus"]) in passive_bus_ids]
    for key in removed_branches:
        branch.pop(key, None)
    for key in removed_buses:
        bus.pop(key, None)
    actions.append({"action": "remove_passive_islands", "reason": "Component has no load and no generation.", "affected_bus_ids": sorted(passive_bus_ids), "affected_branch_ids": removed_branches})


def _sanitize_branch_shunts(case: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    for branch_id, branch in (case.get("branch") or {}).items():
        total = abs(float(branch.get("b_fr") or 0.0)) + abs(float(branch.get("b_to") or 0.0))
        if total == 0.0:
            continue
        synthetic = str(branch.get("provenance") or "").startswith("synthetic") or str(branch.get("source_id") or "").startswith("synthetic:")
        short_synthetic = synthetic and float(branch.get("length_km") or 0.0) <= SHORT_SYNTHETIC_BRANCH_KM
        over_cap = total > DEFAULT_SHUNT_CAP_PU
        if short_synthetic:
            old = {"b_fr": branch.get("b_fr"), "b_to": branch.get("b_to")}
            branch["b_fr"] = 0.0
            branch["b_to"] = 0.0
            actions.append({"action": "zero_short_synthetic_branch_shunt", "branch_id": branch_id, "source_id": branch.get("source_id"), "reason": "Synthetic short connector charging is not physically sourced.", "old": old})
        elif over_cap:
            scale = DEFAULT_SHUNT_CAP_PU / total
            old = {"b_fr": branch.get("b_fr"), "b_to": branch.get("b_to")}
            branch["b_fr"] = round(float(branch.get("b_fr") or 0.0) * scale, 8)
            branch["b_to"] = round(float(branch.get("b_to") or 0.0) * scale, 8)
            actions.append({"action": "cap_branch_shunt", "branch_id": branch_id, "source_id": branch.get("source_id"), "reason": "Absolute branch shunt exceeded solver AC cap for inferred defaults.", "old": old, "new": {"b_fr": branch["b_fr"], "b_to": branch["b_to"]}, "cap_abs_total_b_pu": DEFAULT_SHUNT_CAP_PU})


def _widen_generator_q_ranges(case: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    for gen_id, gen in (case.get("gen") or {}).items():
        pmax = abs(float(gen.get("pmax") or 0.0))
        target = max(pmax, abs(float(gen.get("qmax") or 0.0)), abs(float(gen.get("qmin") or 0.0)))
        if target <= 0:
            continue
        if float(gen.get("qmax") or 0.0) < target or float(gen.get("qmin") or 0.0) > -target:
            old = {"qmin": gen.get("qmin"), "qmax": gen.get("qmax")}
            gen["qmax"] = round(target, 6)
            gen["qmin"] = round(-target, 6)
            actions.append({"action": "widen_generator_q_range", "gen_id": gen_id, "source_id": gen.get("source_id"), "reason": "Relaxed AC handoff needs symmetric reactive headroom for inferred demo generators.", "old": old, "new": {"qmin": gen["qmin"], "qmax": gen["qmax"]}})


def _ensure_reference_buses(case: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    buses = case.get("bus") or {}
    branches = _dict_values(case.get("branch"))
    gens = _dict_values(case.get("gen"))
    loads = _dict_values(case.get("load"))
    islands = _island_report(_dict_values(buses), branches, gens, loads, float(case.get("baseMVA") or BASE_MVA_FALLBACK))
    bus_by_i = {int(bus["bus_i"]): key for key, bus in buses.items()}
    for island in islands:
        reference_ids = [bus_id for bus_id in island["bus_ids"] if int(buses[bus_by_i[bus_id]].get("bus_type", 1)) == 3]
        if len(reference_ids) == 1:
            continue
        candidates = [bus_id for bus_id in island["bus_ids"] if bus_id in bus_by_i]
        if not candidates:
            continue
        chosen = max(candidates, key=lambda bus_id: float(buses[bus_by_i[bus_id]].get("base_kv") or 0.0))
        for bus_id in candidates:
            buses[bus_by_i[bus_id]]["bus_type"] = 3 if bus_id == chosen else 1
            buses[bus_by_i[bus_id]]["type"] = buses[bus_by_i[bus_id]]["bus_type"]
        actions.append({"action": "normalize_reference_bus", "reason": "Each connected component should have exactly one reference bus.", "component_bus_ids": candidates, "reference_bus_id": chosen, "previous_reference_bus_ids": reference_ids})
