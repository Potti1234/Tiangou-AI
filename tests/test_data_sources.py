from pathlib import Path

from app.data_sources.census_statistics import load_monthly_electricity_by_user_type
from app.data_sources.calibration import load_calibration_bundle
from app.data_sources.emsd import load_electricity_consumption_by_sector, load_end_use_shares
from app.data_sources.hk_electric import load_customer_type_consumption, load_district_consumption


RAW_DIR = Path("data/raw")


def test_hk_electric_district_csv_parses_bilingual_headers() -> None:
    records = load_district_consumption(RAW_DIR)

    central = next(
        record
        for record in records
        if record.year == 2025
        and record.period == "second_half"
        and record.district == "central_western"
        and record.sector == "commercial"
    )

    assert central.gwh == 1338
    assert central.provenance == "observed"
    assert {record.district for record in records} >= {"central_western", "eastern", "wan_chai", "southern", "lamma"}


def test_hk_electric_customer_type_csv_parses_sectors() -> None:
    records = load_customer_type_consumption(RAW_DIR)

    overall = next(
        record
        for record in records
        if record.year == 2025 and record.period == "second_half" and record.sector == "overall"
    )

    assert overall.gwh == 5514
    assert overall.customer_count_thousand == 599
    assert overall.average_kwh == 9203


def test_emsd_table12_parses_end_use_percentages() -> None:
    records = load_end_use_shares(RAW_DIR)
    latest = max(records, key=lambda record: record.year)

    assert latest.year == 2023
    assert latest.shares["air_conditioning"] == 0.30
    assert latest.shares["vertical_transport"] == 0.05


def test_emsd_table08_parses_sector_consumption_and_converts_tj_to_gwh() -> None:
    records = load_electricity_consumption_by_sector(RAW_DIR)
    commercial_2023 = next(
        record for record in records if record.year == 2023 and record.sector == "commercial"
    )

    assert commercial_2023.tj == 108524
    assert commercial_2023.gwh == 30145.555556
    assert commercial_2023.provenance == "observed"


def test_census_statistics_parses_annual_and_monthly_electricity_rows() -> None:
    records = load_monthly_electricity_by_user_type(RAW_DIR)
    annual_2025 = next(
        record for record in records if record.year == 2025 and record.month is None and record.user_type == "all_groups"
    )
    january_2025 = next(
        record for record in records if record.year == 2025 and record.month == "Jan" and record.user_type == "residential"
    )

    assert annual_2025.tj == 164433
    assert annual_2025.gwh == 45675.833333
    assert january_2025.tj == 2706
    assert january_2025.gwh == 751.666667


def test_calibration_bundle_uses_latest_complete_year_and_mw_conversion() -> None:
    bundle = load_calibration_bundle(RAW_DIR)

    assert bundle.source_year == 2023
    assert bundle.source_periods == ["first_half", "second_half"]
    assert bundle.is_partial_year is False
    assert bundle.sector_gwh == {"residential": 2401.0, "commercial": 7359.0, "industrial": 287.0}
    assert bundle.district_sector_gwh["lamma"]["residential"] == 18.0
    assert bundle.average_mw_by_sector["commercial"] == 840.068
    assert bundle.peak_mw_by_sector["commercial"] == 1527.396
    assert bundle.snapshot_total_mw["peak_16h"] > bundle.snapshot_total_mw["overnight_04h"]
    assert bundle.end_use_year == 2023
    assert bundle.hk_total_sector_gwh["commercial"] == 30145.556
    assert bundle.inferred_clp_sector_gwh["commercial"] == 22786.556
    assert bundle.inferred_clp_sector_gwh["transport_or_public_services"] == 1047.778
    assert bundle.inferred_clp_total_gwh == 35480.223
    assert bundle.territory_total_validation["status"] == "pass"
    assert "CLP demand inferred from official Hong Kong totals" in bundle.warnings[0]


def test_calibration_bundle_supports_explicit_partial_year() -> None:
    bundle = load_calibration_bundle(RAW_DIR, year=2024)

    assert bundle.source_year == 2024
    assert set(bundle.source_periods) <= {"first_half", "second_half"}
    assert bundle.metadata["provenance"] == "observed_hk_electric_public_consumption"
    assert bundle.clp_inference_method is None
    assert "CLP inference missing public territory totals" in bundle.warnings[-1]
