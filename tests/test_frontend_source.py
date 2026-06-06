from pathlib import Path


def test_raw_ui_support_assets_are_hidden_by_default() -> None:
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "function isSupportAsset" in source
    assert "!isSupportAsset(asset)" in source
    assert "pointAssets.map" in source
