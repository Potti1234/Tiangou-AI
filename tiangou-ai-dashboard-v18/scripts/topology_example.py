
"""Minimal example topology file consumed by scripts/export_grid_topology.py."""

TOPOLOGY = {
    "nodes": [
        {
            "id": "example-plant",
            "name": "Example Power Station",
            "kind": "plant",
            "owner": "CLP",
            "voltage_kv": 400,
            "source": "gas",
            "lat": 22.377,
            "lon": 113.910,
        },
        {
            "id": "example-substation",
            "name": "Example EHV Substation",
            "kind": "substation",
            "owner": "CLP",
            "voltage_kv": 400,
            "lat": 22.391,
            "lon": 113.975,
        },
    ],
    "edges": [
        {
            "id": "example-circuit",
            "name": "Example 400 kV circuit",
            "owner": "CLP",
            "voltage_kv": 400,
            "cable_type": "overhead / line",
            "from": "example-plant",
            "to": "example-substation",
        }
    ],
}
