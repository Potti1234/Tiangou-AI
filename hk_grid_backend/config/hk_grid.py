"""
Hong Kong grid baseline configuration.
All capacities in MW, H in seconds, ramp rates in MW/min.
"""
import copy

HK_GRID_BASELINE = {
    "coal_plants": [
        {
            "name": "Lamma Power Station Unit 1",
            "type": "coal",
            "capacity_mw": 700,
            "H": 5.0,
            "online": True,
            "ramp_rate_mw_per_min": 30,
            "current_output_mw": 700,
            "weather_dependent": False,
        },
        {
            "name": "Lamma Power Station Unit 2",
            "type": "coal",
            "capacity_mw": 700,
            "H": 5.0,
            "online": True,
            "ramp_rate_mw_per_min": 30,
            "current_output_mw": 700,
            "weather_dependent": False,
        },
        {
            "name": "Castle Peak A",
            "type": "coal",
            "capacity_mw": 600,
            "H": 5.0,
            "online": True,
            "ramp_rate_mw_per_min": 25,
            "current_output_mw": 600,
            "weather_dependent": False,
        },
    ],
    "gas_ccgt": [
        {
            "name": "Black Point CCGT 1",
            "type": "gas_ccgt",
            "capacity_mw": 400,
            "H": 4.0,
            "online": True,
            "ramp_rate_mw_per_min": 80,
            "current_output_mw": 400,
            "weather_dependent": False,
        },
        {
            "name": "Black Point CCGT 2",
            "type": "gas_ccgt",
            "capacity_mw": 400,
            "H": 4.0,
            "online": False,       # spinning reserve
            "ramp_rate_mw_per_min": 80,
            "current_output_mw": 0,
            "weather_dependent": False,
        },
        {
            "name": "Black Point CCGT 3",
            "type": "gas_ccgt",
            "capacity_mw": 400,
            "H": 4.0,
            "online": False,       # spinning reserve
            "ramp_rate_mw_per_min": 80,
            "current_output_mw": 0,
            "weather_dependent": False,
        },
    ],
    "offshore_wind": [
        {
            "name": "HK Offshore Wind Alpha",
            "type": "offshore_wind",
            "capacity_mw": 800,
            "H": 0.0,
            "online": True,
            "weather_dependent": True,
            "current_output_mw": 560,   # ~70% capacity factor
        },
        {
            "name": "HK Offshore Wind Beta",
            "type": "offshore_wind",
            "capacity_mw": 600,
            "H": 0.0,
            "online": True,
            "weather_dependent": True,
            "current_output_mw": 420,
        },
    ],
    "solar_pv": [
        {
            "name": "HK Solar Array",
            "type": "solar_pv",
            "capacity_mw": 500,
            "H": 0.0,
            "online": True,
            "weather_dependent": True,
            "current_output_mw": 250,   # ~50% average capacity factor
        },
    ],
    "nuclear": [
        {
            "name": "Daya Bay Import",
            "type": "nuclear",
            "capacity_mw": 1200,
            "H": 6.0,
            "online": True,
            "ramp_rate_mw_per_min": 5,
            "current_output_mw": 1200,
            "weather_dependent": False,
        },
    ],
    "synchronous_condensers": [
        {
            "name": "SC Unit 1",
            "type": "synchronous_condenser",
            "capacity_mw": 0,       # no generation
            "H": 4.0,
            "online": False,
            "current_output_mw": 0,
            "inertia_mva": 800,     # 800 MVA equivalent for H calculation
            "weather_dependent": False,
        },
    ],
}

# Typical HK weekday demand profile [hour -> MW]
# Scaled to 65 % of published peak so the configured generation fleet
# (coal 2 000 MW + CCGT 1 200 MW + nuclear 1 200 MW + wind 1 400 MW +
#  solar 500 MW = ~6 300 MW at peak CF) can meet demand with spinning
# reserve headroom — essential for governor primary-frequency response.
HK_DEMAND_PROFILE = {
    0:  3380, 1:  3185, 2:  3055, 3:  2990, 4:  2990, 5:  3120,
    6:  3445, 7:  3965, 8:  4420, 9:  4680, 10: 4875, 11: 4940,
    12: 4810, 13: 4680, 14: 4745, 15: 4875, 16: 4940, 17: 4810,
    18: 4615, 19: 4550, 20: 4485, 21: 4355, 22: 4095, 23: 3770,
}

# EV charging stations — from data.gov.hk CLP dataset proxy
# ~150 stations, 0.15 MW each = 22.5 MW total sheddable load
EV_CHARGING_STATIONS = [
    {
        "id": f"EV_{i:03d}",
        "location": "HK",
        "max_load_mw": 0.15,
        "active": True,
    }
    for i in range(150)
]


def get_baseline_copy() -> dict:
    """Return a deep copy of the baseline config safe for mutation."""
    return copy.deepcopy(HK_GRID_BASELINE)


def get_ev_stations_copy() -> list:
    return copy.deepcopy(EV_CHARGING_STATIONS)


def get_all_sources(grid: dict) -> list:
    """Flatten all generation sources from a grid config dict."""
    sources = []
    for category in grid.values():
        sources.extend(category)
    return sources
