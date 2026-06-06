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


def test_frontend_restarts_dashboard_load_when_previous_request_is_in_flight() -> None:
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "if (loadInFlight.current) dashboardAbort.current?.abort()" in source
    assert "if (dashboardAbort.current === controller) {" in source
    assert "loadInFlight.current = false" in source


def test_frontend_fetches_and_renders_assumption_transparency() -> None:
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "type AssumptionTransparency" in source
    assert "setAssumptions" in source
    assert "/assumptions/summary" in source
    assert "/assumptions/demand-profiles" in source
    assert "/assumptions/imports" in source
    assert "Assumption transparency" in source
    assert "Lowest-confidence assumptions" in source
    assert "Top assumed data-center loads" in source
    assert "Generator availability summary" in source
    assert "Import constraints" in source


def test_frontend_uses_shadcn_charts_for_analytics_dashboard() -> None:
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    chart_source = Path("frontend/src/components/ui/chart.tsx").read_text(encoding="utf-8")

    assert "ChartContainer" in source
    assert "ChartTooltip" in source
    assert "ChartTooltipContent" in source
    assert "ChartLegend" in source
    assert "ChartLegendContent" in source
    assert "/grid/analytics-dashboard" in source
    assert "const POLL_MS = 60000" in source
    assert "Card, CardContent, CardHeader, CardTitle" in source
    assert "Badge" in source
    assert "TabsTrigger value=\"overview\"" in source
    assert "TabsTrigger value=\"assumptions\"" in source
    assert "accessibilityLayer" in source
    assert "h-[220px] min-h-[220px]" in source or "h-[210px] min-h-[210px]" in source
    assert "recharts" in chart_source
    assert "ResponsiveContainer" in chart_source
