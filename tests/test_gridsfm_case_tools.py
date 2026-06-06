from app.gridsfm_case_tools import diagnose_powermodels_case, sanitize_powermodels_case_for_ac


def _case() -> dict:
    return {
        "baseMVA": 100.0,
        "bus": {
            "1": {"bus_i": 1, "index": 1, "bus_type": 3, "type": 3, "base_kv": 400.0},
            "2": {"bus_i": 2, "index": 2, "bus_type": 1, "type": 1, "base_kv": 132.0},
            "3": {"bus_i": 3, "index": 3, "bus_type": 3, "type": 3, "base_kv": 132.0},
            "4": {"bus_i": 4, "index": 4, "bus_type": 1, "type": 1, "base_kv": 132.0},
        },
        "branch": {
            "1": {
                "index": 1,
                "f_bus": 1,
                "t_bus": 2,
                "br_r": 0.001,
                "br_x": 0.01,
                "b_fr": 0.12,
                "b_to": 0.12,
                "rate_a": 100.0,
                "br_status": 1,
                "matched_voltage_kv": 400.0,
                "source_id": "osm:way:1",
                "source_power": "line",
                "circuit_class": "inter_facility",
            },
            "2": {
                "index": 2,
                "f_bus": 3,
                "t_bus": 4,
                "br_r": 0.001,
                "br_x": 0.01,
                "b_fr": 0.1,
                "b_to": 0.1,
                "rate_a": 100.0,
                "br_status": 1,
                "matched_voltage_kv": 132.0,
                "source_id": "synthetic:test",
                "source_power": "cable",
                "circuit_class": "tap",
                "length_km": 2.0,
                "provenance": "synthetic_connection_to_nearest_substation",
            },
        },
        "gen": {
            "1": {"index": 1, "gen_bus": 1, "pmin": 0.0, "pmax": 1.0, "qmin": -0.1, "qmax": 0.1}
        },
        "load": {
            "1": {"index": 1, "load_bus": 2, "pd": 0.2, "qd": 0.05}
        },
    }


def test_diagnose_powermodels_case_reports_ac_blockers() -> None:
    report = diagnose_powermodels_case(_case())

    assert report["summary"]["bus_count"] == 4
    assert report["summary"]["branch_count"] == 2
    assert report["summary"]["passive_island_count"] == 1
    assert report["summary"]["voltage_mismatch_count"] == 1
    assert report["summary"]["extreme_shunt_branch_count"] == 2
    assert {blocker["code"] for blocker in report["likely_ac_feasibility_blockers"]} >= {
        "passive_islands",
        "large_branch_shunts",
        "voltage_mismatch_branches",
    }


def test_sanitize_powermodels_case_for_ac_is_auditable() -> None:
    sanitized = sanitize_powermodels_case_for_ac(_case())

    assert sanitized["_metadata"]["solver_sanitized"] is True
    assert sanitized["solver_sanitized"] is True
    assert "3" not in {str(bus["bus_i"]) for bus in sanitized["bus"].values()}
    assert "2" not in sanitized["branch"]
    assert sanitized["branch"]["1"]["b_fr"] == 0.04
    assert sanitized["branch"]["1"]["b_to"] == 0.04
    assert sanitized["gen"]["1"]["qmin"] == -1.0
    assert sanitized["gen"]["1"]["qmax"] == 1.0
    actions = sanitized["_metadata"]["sanitization_action_counts"]
    assert actions["remove_passive_islands"] == 1
    assert actions["cap_branch_shunt"] == 1
    assert actions["widen_generator_q_range"] == 1
