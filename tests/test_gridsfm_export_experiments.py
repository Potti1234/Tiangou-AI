from pathlib import Path

from app import run_gridsfm_export_experiments as experiments


def test_run_gridsfm_export_experiments_writes_variant_manifest(tmp_path, monkeypatch) -> None:
    exported_paths = []

    def fake_export_powermodels_case(**kwargs):
        output_path = Path(kwargs["output_path"])
        output_path.write_text("{}", encoding="utf-8")
        exported_paths.append(output_path)
        return {
            "output_path": str(output_path),
            "validation": {"status": "warning", "errors": []},
            "metadata": {"bus_count": 2, "branch_count": 1},
        }

    def fake_diagnostic(path, output_dir=None):
        report_path = output_dir / f"{path.stem}.gridsfm_diagnostics.json"
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text("{}", encoding="utf-8")
        return {
            "report_path": str(report_path),
            "summary": {"bus_count": 2, "branch_count": 1},
            "likely_ac_feasibility_blockers": [{"code": "large_branch_shunts"}],
        }

    monkeypatch.setattr(experiments, "export_powermodels_case", fake_export_powermodels_case)
    monkeypatch.setattr(experiments, "write_diagnostic_report", fake_diagnostic)

    result = experiments.run_gridsfm_export_experiments(
        database_path=tmp_path / "grid.sqlite3",
        output_root=tmp_path / "experiments",
        run_solver=False,
    )

    assert result["schema"] == "tiangou.gridsfm_export_experiments.v1"
    assert result["variant_count"] == 5
    assert result["status_counts"] == {"skipped": 5}
    assert len(exported_paths) == 5
    for variant in result["variants"]:
        assert Path(variant["raw_path"]).exists()
        assert Path(variant["manifest_path"]).exists()
        assert Path(variant["diagnostic_report_path"]).exists()
        assert variant["solver_status"] == "skipped"


def test_experiment_variants_cover_planned_bisection_cases() -> None:
    names = [variant["name"] for variant in experiments.EXPERIMENT_VARIANTS]

    assert names == [
        "strict_transmission_100kv",
        "strict_transmission_100kv_intertie",
        "demo_full_osm_100kv",
        "demo_full_osm_all_voltage",
        "demo_full_osm_all_voltage_no_synthetic_gen_connections",
    ]
