from pathlib import Path

from app.data_sources.calibration import load_calibration_bundle
from app.data_sources.emsd import load_end_use_shares
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


def test_calibration_bundle_uses_latest_complete_year_and_mw_conversion() -> None:
    bundle = load_calibration_bundle(RAW_DIR)

    assert bundle.source_year == 2025
    assert bundle.source_periods == ["first_half", "second_half"]
    assert bundle.is_partial_year is False
    assert bundle.sector_gwh == {"residential": 2387.0, "commercial": 7250.0, "industrial": 277.0}
    assert bundle.district_sector_gwh["lamma"]["residential"] == 19.0
    assert bundle.average_mw_by_sector["commercial"] == 827.626
    assert bundle.peak_mw_by_sector["commercial"] == 1504.775
    assert bundle.snapshot_total_mw["peak_16h"] > bundle.snapshot_total_mw["overnight_04h"]
    assert bundle.end_use_year == 2023
    assert "CLP territory demand is currently synthetic/inferred" in bundle.warnings[0]


def test_calibration_bundle_supports_explicit_partial_year() -> None:
    bundle = load_calibration_bundle(RAW_DIR, year=2024)

    assert bundle.source_year == 2024
    assert set(bundle.source_periods) <= {"first_half", "second_half"}
    assert bundle.metadata["provenance"] == "observed_hk_electric_public_consumption"
