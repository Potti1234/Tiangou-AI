"""
Disturbance event library for HK grid simulation.
Each event is a descriptor dict; GridSimulator.apply_disturbance() interprets it.
"""

DISTURBANCE_EVENTS = {

    "typhoon_wind_loss": {
        "description": "Typhoon Signal 8 — offshore wind farms emergency shutdown",
        "type": "generation_loss",
        "affected_sources": ["HK Offshore Wind Alpha", "HK Offshore Wind Beta"],
        "profile": "ramp",
        "ramp_time_s": 20,          # farms ramp down over ~20 s as signal is given
        "magnitude_mw": -980,       # actual output at time of event (not nameplate)
        "duration_s": None,
        "H_impact": 0.0,            # wind had H=0 anyway
    },

    "datacenter_spike": {
        "description": "New hyperscale datacenter district comes online",
        "type": "demand_increase",
        "profile": "ramp",
        "magnitude_mw": +800,
        "ramp_time_s": 120,
        "duration_s": None,
    },

    "coal_plant_trip": {
        "description": "Lamma Power Station Unit 1 unplanned outage",
        "type": "generation_loss",
        "affected_sources": ["Lamma Power Station Unit 1"],
        "profile": "step",
        "magnitude_mw": -700,
        "H_impact": -700 * 5.0 / 12000,
        "duration_s": None,
    },

    "solar_cloud_ramp": {
        "description": "Heavy cloud cover reduces solar output rapidly",
        "type": "generation_loss",
        "affected_sources": ["HK Solar Array"],
        "profile": "ramp",
        "magnitude_mw": -500,
        "ramp_time_s": 300,
        "duration_s": None,
    },

    "mainland_disconnect": {
        "description": "Daya Bay nuclear import interrupted (mainland grid issue)",
        "type": "generation_loss",
        "affected_sources": ["Daya Bay Import"],
        "profile": "step",
        "magnitude_mw": -1200,
        "H_impact": -1200 * 6.0 / 12000,
        "duration_s": None,
    },

    "combined_stress": {
        "description": "Typhoon + datacenter spike simultaneously (worst case)",
        "type": "combined",
        "sub_events": ["typhoon_wind_loss", "datacenter_spike"],
        "offset_s": 30,     # datacenter spike fires 30s after wind loss
    },
}
