from pathlib import Path


def test_raw_ui_support_assets_are_hidden_by_default() -> None:
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "function isSupportAsset" in source
    assert "!isSupportAsset(asset)" in source
    assert "pointAssets.map" in source


def test_frontend_fetches_and_renders_important_consumer_proxy_markers() -> None:
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "type ConsumerProxyMarker" in source
    assert "IMPORTANT_CONSUMER_LIMIT = 1000" in source
    assert "/grid/consumer-proxies/important?region_key=hong-kong&limit=" in source
    assert "/grid/consumer-proxies\"" not in source
    assert "setConsumerProxies" in source
    assert "visibleConsumerProxies.map" in source
    assert "<MapMarker key={`consumer-${proxy.id}`}" in source
    assert "ConsumerProxyMapMarker" in source
    assert "Consumers" in source
    assert "const POLL_MS = 60000" in source
