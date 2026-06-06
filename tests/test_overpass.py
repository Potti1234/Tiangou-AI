from app.overpass import POWER_VALUES, build_power_query
from app.regions import REGIONS


def test_hong_kong_query_uses_raw_overpass_area_selectors() -> None:
    query = build_power_query(REGIONS["hong-kong"])

    assert "{{geocodeArea" not in query
    assert '["name"="Hong Kong"]' in query
    assert '["name:en"="Hong Kong"]' in query
    assert 'nwr["power"~' in query
    assert "out body geom" in query


def test_gba_query_includes_core_cities_and_extra_power_assets() -> None:
    query = build_power_query(REGIONS["greater-bay-area"])

    assert '["name"="Shenzhen"]' in query
    assert '["name"="Guangzhou"]' in query
    assert "minor_line" in POWER_VALUES
    assert "pole" in POWER_VALUES
    assert "switchgear" in POWER_VALUES
