import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link } from "@tanstack/react-router"
import { Activity, AlertTriangle, CircleDot, Cpu, Factory, Loader2, Play, PlugZap, RotateCcw, Zap } from "lucide-react"
import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Map as GeoMap, MapControls, MapMarker, MapRoute, MarkerContent, MarkerTooltip } from "@/components/ui/map"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ??
  "/api"

const HONG_KONG_CENTER: [number, number] = [114.1694, 22.3193]
const IMPORTANT_CONSUMER_LIMIT = 1000

type DynamicScenario = {
  id: string
  description: string
  type: string
  affected_sources: string[]
  affected_source_ids?: string[]
  affected_loads?: Array<{ id: string; name: string; estimated_facility_mw: number }>
  magnitude_mw: number
  profile: string
  available: boolean
  unavailable_reason?: string
  provenance: string
  assumptions: string
}

type GridStateFrame = {
  t: number
  A: DynamicState
  B: DynamicState
  intervention_triggered: boolean
  actions_taken: string[]
}

type DynamicState = {
  f: number
  H_physical: number
  H_pinn: number
  Pm: number
  Pe: number
  df_dt: number
  risk_level: string
  freq_band: string
  demand_extra_mw: number
  renewable_fraction: number
  active_sources: DynamicSource[]
}

type DynamicSource = {
  name: string
  source_id?: string
  type: string
  capacity_mw: number
  current_output_mw: number
  H: number
  online: boolean
  provenance?: string
  confidence?: number
}

type DynamicSimulationResponse = {
  scenario: string
  duration_s: number
  frames: GridStateFrame[]
  outcome_A: string
  outcome_B: string
  kpis: Record<string, number | string | null>
  scenario_payload: DynamicScenario
  grid_source: {
    schema: string
    source: string
    provenance_summary: {
      total_demand_mw: number
      synthetic_or_inferred_source_count: number
      assumptions: string[]
    }
    source_mapping: {
      generator_count: number
      types: Record<string, number>
    }
    synthetic_assumption_counts: Record<string, number>
  }
  pinn_status: PinnStatus
}

type PinnStatus = {
  checkpoint_loaded: boolean
  checkpoint_path: string
  checkpoint_status: string
  H_estimated: number
  model_params: number
  startup_training: boolean
  training_data_dependency?: string
}

type ScenarioPayload = {
  scenarios: DynamicScenario[]
  grid_source: DynamicSimulationResponse["grid_source"]
}

type OSMGeometryPoint = {
  lat: number
  lon: number
}

type GridAsset = {
  osm_type: string
  osm_id: number
  power: string
  name: string | null
  voltage: string | null
  operator: string | null
  lat: number | null
  lon: number | null
  tags: Record<string, string>
  geometry: OSMGeometryPoint[] | null
}

type TopologyBus = {
  id: string
  name: string | null
  power: string
  lat: number | null
  lon: number | null
  base_kv: number | null
  provenance: string | null
}

type TopologyBranch = {
  id: string
  name: string | null
  power: string
  from_bus_id: string | null
  to_bus_id: string | null
  voltage_kv: number | null
  provenance: string | null
}

type TopologyPreview = {
  buses: TopologyBus[]
  branches: TopologyBranch[]
}

type PowerModelsBus = {
  bus_i: number
  base_kv: number
  source_id: string
  provenance: string | null
}

type PowerModelsBranch = {
  f_bus: number
  t_bus: number
  source_id: string
  transformer: boolean
  rate_a: number
  matched_voltage_kv?: number
  provenance: string | null
}

type PowerModelsLoad = {
  load_bus: number
  pd: number
  service_territory: string | null
  district?: string | null
  sector?: string | null
  provenance?: string | null
}

type PowerModelsGen = {
  gen_bus: number
  pmax: number
  resource_type: string
  provenance: string | null
  name?: string | null
  operator?: string | null
  energy_source?: string | null
  confidence?: number | null
}

type PowerModelsCase = {
  bus: Record<string, PowerModelsBus>
  branch: Record<string, PowerModelsBranch>
  load: Record<string, PowerModelsLoad>
  gen: Record<string, PowerModelsGen>
  _metadata: Record<string, unknown>
}

type DashboardSnapshot = {
  assets: GridAsset[]
  topology: TopologyPreview
  powermodels_case: PowerModelsCase
}

type ConsumerProxyMarker = {
  id: string
  name: string | null
  proxy_type: string
  sector: string
  weight: number
  confidence: number | null
  lat: number
  lon: number
  reason: string
  data_center_load_estimate?: {
    estimated_facility_mw: number
    confidence: number
  } | null
}

type ModelMode = "full_demo" | "transmission"

type RouteLayer = {
  id: string
  label: string
  coordinates: [number, number][]
  color: string
  width: number
  opacity: number
  dashArray?: [number, number]
}

type MarkerPoint = {
  id: string
  label: string
  longitude: number
  latitude: number
  size: number
  color: string
  kind: "generator" | "load" | "consumer"
  rows: Array<[string, string]>
  state?: "normal" | "tripped" | "activated" | "stressed"
}

const chartConfig = {
  A: { label: "No stabilization", color: "#b91c1c" },
  B: { label: "Tiangou stabilization", color: "#15803d" },
} satisfies ChartConfig

function formatNumber(value: unknown, digits = 0) {
  if (typeof value !== "number" || Number.isNaN(value)) return "0"
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function outcomeClass(outcome: string | undefined) {
  if (outcome === "STABLE") return "border-emerald-700/30 bg-emerald-50 text-emerald-800"
  if (outcome === "DEGRADED") return "border-amber-700/30 bg-amber-50 text-amber-800"
  return "border-red-700/30 bg-red-50 text-red-800"
}

function pinnStatusClass(status: PinnStatus | null) {
  if (!status) return "border-zinc-300 bg-zinc-100 text-zinc-600"
  if (status.checkpoint_loaded) return "border-emerald-700/30 bg-emerald-50 text-emerald-800"
  return "border-amber-700/30 bg-amber-50 text-amber-800"
}

function routeCoordinates(asset: GridAsset): [number, number][] {
  return (asset.geometry ?? []).map((point) => [point.lon, point.lat])
}

function assetSourceId(asset: GridAsset) {
  return `osm:${asset.osm_type}:${asset.osm_id}`
}

function isLinearAsset(asset: GridAsset) {
  return (asset.power === "line" || asset.power === "minor_line" || asset.power === "cable") && (asset.geometry?.length ?? 0) > 1
}

function provenanceColor(provenance: string | null | undefined) {
  const value = String(provenance ?? "").toLowerCase()
  if (value.includes("observed")) return "#15803d"
  if (value.includes("inferred")) return "#a16207"
  if (value.includes("synthetic") || value.includes("equivalent")) return "#2563eb"
  return "#52525b"
}

function consumerColor(reason: string) {
  if (reason === "data_center") return "#2563eb"
  if (reason === "charging_station") return "#16a34a"
  if (reason === "hospital") return "#dc2626"
  if (reason.includes("industrial")) return "#ea580c"
  return "#7c3aed"
}

function DynamicHeader({
  loading,
  modelMode,
  onModeChange,
  onRefresh,
}: {
  loading: boolean
  modelMode: ModelMode
  onModeChange: (mode: ModelMode) => void
  onRefresh: () => void
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-zinc-200 bg-[#e5e7e3]/95 px-4 py-2 backdrop-blur">
      <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Badge className="rounded-[3px] bg-zinc-950 px-2 py-1 text-white">Dynamic grid comparison</Badge>
          <Badge variant="outline" className="rounded-[3px] border-emerald-700/30 bg-emerald-50 px-2 py-1 text-emerald-900">
            Real dashboard grid
          </Badge>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Tabs value={modelMode} onValueChange={(value) => onModeChange(value as ModelMode)}>
            <TabsList className="h-8 bg-white/75">
              <TabsTrigger value="full_demo">Full demo grid</TabsTrigger>
              <TabsTrigger value="transmission">Transmission</TabsTrigger>
            </TabsList>
          </Tabs>
          <Button asChild variant="outline" className="h-8 rounded-[4px] border-zinc-300 bg-white/92">
            <Link to="/dashboard">Map</Link>
          </Button>
          <Button asChild variant="outline" className="h-8 rounded-[4px] border-zinc-300 bg-white/92">
            <Link to="/analytics">Analytics</Link>
          </Button>
          <Button type="button" variant="outline" onClick={onRefresh} disabled={loading} className="h-8 rounded-[4px] border-zinc-300 bg-white/92">
            <RotateCcw className={cn("size-4", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>
    </header>
  )
}

export function DynamicSimulationPage() {
  const [scenarios, setScenarios] = useState<DynamicScenario[]>([])
  const [gridSource, setGridSource] = useState<ScenarioPayload["grid_source"] | null>(null)
  const [selectedScenario, setSelectedScenario] = useState("import_loss")
  const [duration, setDuration] = useState(400)
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [modelMode, setModelMode] = useState<ModelMode>("full_demo")
  const [result, setResult] = useState<DynamicSimulationResponse | null>(null)
  const [pinnStatus, setPinnStatus] = useState<PinnStatus | null>(null)
  const [dashboard, setDashboard] = useState<DashboardSnapshot | null>(null)
  const [consumerProxies, setConsumerProxies] = useState<ConsumerProxyMarker[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const autoRanRef = useRef(false)

  const dashboardQuery = useMemo(() => {
    const params = new URLSearchParams({
      region_key: "hong-kong",
      include_hk_interties: modelMode === "full_demo" ? "true" : "false",
      solver_include_policy: modelMode === "full_demo" ? "demo_full_osm" : "strict_transmission",
      include_synthetic_generator_connections: modelMode === "full_demo" ? "true" : "false",
      asset_limit: "5000",
    })
    if (modelMode === "transmission") params.set("min_voltage_kv", "100")
    return params.toString()
  }, [modelMode])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const scenarioParams = new URLSearchParams({ model_mode: modelMode })
      const [scenarioResponse, dashboardResponse, consumerResponse, pinnResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/dynamic/scenarios?${scenarioParams}`),
        fetch(`${API_BASE_URL}/grid/dashboard-snapshot?${dashboardQuery}`),
        fetch(`${API_BASE_URL}/grid/consumer-proxies/important?region_key=hong-kong&limit=${IMPORTANT_CONSUMER_LIMIT}`),
        fetch(`${API_BASE_URL}/dynamic/pinn-status`),
      ])
      if (!scenarioResponse.ok) throw new Error(`Dynamic scenarios API returned ${scenarioResponse.status}`)
      if (!dashboardResponse.ok) throw new Error(`Dashboard snapshot API returned ${dashboardResponse.status}`)
      if (!consumerResponse.ok) throw new Error(`Consumer proxy API returned ${consumerResponse.status}`)
      if (!pinnResponse.ok) throw new Error(`PINN status API returned ${pinnResponse.status}`)
      const scenarioPayload = await scenarioResponse.json() as ScenarioPayload
      setScenarios(scenarioPayload.scenarios)
      setGridSource(scenarioPayload.grid_source)
      setDashboard(await dashboardResponse.json() as DashboardSnapshot)
      setConsumerProxies(await consumerResponse.json() as ConsumerProxyMarker[])
      setPinnStatus(await pinnResponse.json() as PinnStatus)
      const availableIds = new Set(scenarioPayload.scenarios.filter((scenario) => scenario.available).map((scenario) => scenario.id))
      if (!availableIds.has(selectedScenario)) {
        setSelectedScenario(availableIds.has("import_loss") ? "import_loss" : availableIds.has("largest_generator_trip") ? "largest_generator_trip" : [...availableIds][0] ?? "")
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load dynamic grid data")
    } finally {
      setLoading(false)
    }
  }, [dashboardQuery, modelMode, selectedScenario])

  const runSimulation = useCallback(async () => {
    if (!selectedScenario) return
    setRunning(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/dynamic/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario: selectedScenario,
          duration_s: duration,
          demand_snapshot: "peak_16h",
          model_mode: modelMode,
        }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail ?? `Dynamic simulation API returned ${response.status}`)
      }
      const payload = await response.json() as DynamicSimulationResponse
      setResult(payload)
      setGridSource(payload.grid_source)
      setPinnStatus(payload.pinn_status)
      setCursor(Math.min(30, Math.max(payload.frames.length - 1, 0)))
      setPlaying(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run dynamic simulation")
    } finally {
      setRunning(false)
    }
  }, [duration, modelMode, selectedScenario])

  useEffect(() => {
    autoRanRef.current = false
    setResult(null)
    void loadData()
  }, [loadData])

  useEffect(() => {
    if (autoRanRef.current || loading || !dashboard || !scenarios.length || !selectedScenario) return
    autoRanRef.current = true
    void runSimulation()
  }, [dashboard, loading, runSimulation, scenarios.length, selectedScenario])

  useEffect(() => {
    if (!playing || !result?.frames.length) return
    const id = window.setInterval(() => {
      setCursor((value) => {
        if (value >= result.frames.length - 1) {
          window.clearInterval(id)
          setPlaying(false)
          return value
        }
        return value + 1
      })
    }, 80)
    return () => window.clearInterval(id)
  }, [playing, result])

  const selected = scenarios.find((scenario) => scenario.id === selectedScenario)
  const frames = result?.frames ?? []
  const currentFrame = frames[Math.min(cursor, Math.max(frames.length - 1, 0))]
  const actions = useMemo(() => frames.slice(0, cursor + 1).flatMap((frame) => frame.actions_taken.map((action) => ({ t: frame.t, action }))), [cursor, frames])
  const chartData = useMemo(() => frames.map((frame) => ({
    t: frame.t,
    A: Number(frame.A.f.toFixed(3)),
    B: Number(frame.B.f.toFixed(3)),
  })), [frames])

  return (
    <main className="min-h-[100dvh] bg-[#e5e7e3] text-zinc-950">
      <DynamicHeader loading={loading || running} modelMode={modelMode} onModeChange={setModelMode} onRefresh={() => void loadData()} />
      <div className="mx-auto grid max-w-[1800px] gap-3 px-3 py-3 xl:grid-cols-[320px_1fr]">
        <aside className="space-y-3">
          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Zap className="size-4" />
                Simulation
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <label className="grid gap-1 text-sm font-medium">
                Scenario
                <select
                  value={selectedScenario}
                  onChange={(event) => setSelectedScenario(event.target.value)}
                  className="h-9 rounded-[4px] border border-zinc-300 bg-white px-2 text-sm"
                >
                  {scenarios.map((scenario) => (
                    <option key={scenario.id} value={scenario.id} disabled={!scenario.available}>
                      {scenario.id.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm font-medium">
                Duration
                <input
                  type="number"
                  min={60}
                  max={1200}
                  step={20}
                  value={duration}
                  onChange={(event) => setDuration(Number(event.target.value))}
                  className="h-9 rounded-[4px] border border-zinc-300 bg-white px-2 text-sm"
                />
              </label>
              <Button type="button" onClick={() => void runSimulation()} disabled={running || loading || !selectedScenario} className="w-full rounded-[4px] bg-zinc-950 text-white hover:bg-zinc-800">
                {running ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
                Run simulation
              </Button>
              {error && (
                <div className="rounded-[4px] border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-2">
            <OutcomePanel label="No stabilization" outcome={result?.outcome_A} state={currentFrame?.A} />
            <OutcomePanel label="Tiangou active" outcome={result?.outcome_B} state={currentFrame?.B} />
          </div>

          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Cpu className="size-4" />
                PINN model
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Badge variant="outline" className={cn("rounded-[3px] px-2 py-1", pinnStatusClass(pinnStatus))}>
                {pinnStatus?.checkpoint_loaded ? "checkpoint loaded" : pinnStatus?.checkpoint_status?.replaceAll("_", " ") ?? "loading"}
              </Badge>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Metric label="Estimated H" value={`${formatNumber(pinnStatus?.H_estimated, 3)} s`} />
                <Metric label="Params" value={formatNumber(pinnStatus?.model_params)} />
                <Metric label="Startup train" value={pinnStatus?.startup_training ? "yes" : "no"} />
                <Metric label="Checkpoint" value={pinnStatus?.checkpoint_path?.split(/[\\/]/).pop() ?? "n/a"} />
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity className="size-4" />
                Frequency timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ChartContainer config={chartConfig} className="h-[150px] min-h-[150px] w-full">
                <LineChart data={chartData} accessibilityLayer margin={{ left: 0, right: 10, top: 8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="t" tickLine={false} axisLine={false} tickMargin={6} />
                  <YAxis domain={[48.5, 50.3]} tickLine={false} axisLine={false} width={34} />
                  <ReferenceLine y={49.5} stroke="#b45309" strokeDasharray="4 3" />
                  <ReferenceLine y={49.0} stroke="#b91c1c" strokeDasharray="4 3" />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Line type="monotone" dataKey="A" stroke="var(--color-A)" strokeWidth={2} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="B" stroke="var(--color-B)" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ChartContainer>
              <div className="mt-3 flex items-center gap-2">
                <Button type="button" size="sm" variant="outline" onClick={() => setPlaying((value) => !value)} disabled={!frames.length} className="h-8 rounded-[4px] border-zinc-300 bg-white">
                  <Play className="size-4" />
                  {playing ? "Pause" : "Play"}
                </Button>
                <input
                  aria-label="Simulation timeline"
                  type="range"
                  min={0}
                  max={Math.max(frames.length - 1, 0)}
                  value={cursor}
                  onChange={(event) => setCursor(Number(event.target.value))}
                  className="min-w-0 flex-1"
                />
                <span className="font-mono text-xs tabular-nums text-zinc-600">{currentFrame?.t ?? 0}s</span>
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="size-4" />
                Actions
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Metric label="Scenario MW" value={`${formatNumber(selected?.magnitude_mw, 1)} MW`} />
                <Metric label="Interventions" value={formatNumber(result?.kpis.intervention_count)} />
                <Metric label="Real generators" value={formatNumber(gridSource?.source_mapping.generator_count)} />
                <Metric label="Consumers" value={formatNumber(consumerProxies.length)} />
              </div>
              <div className="max-h-44 space-y-1.5 overflow-auto pr-1">
                {actions.length ? actions.map((entry, index) => (
                  <div key={`${entry.t}-${index}`} className="grid grid-cols-[42px_1fr] gap-2 rounded-[4px] border border-zinc-200 bg-white px-2 py-1.5 text-xs">
                    <span className="font-mono tabular-nums text-zinc-500">{entry.t}s</span>
                    <span>{entry.action}</span>
                  </div>
                )) : (
                  <div className="rounded-[4px] border border-zinc-200 bg-white px-2 py-2 text-xs text-zinc-600">
                    Run the simulation to show producer redispatch and consumer curtailment.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </aside>

        <section className="grid min-h-[calc(100dvh-92px)] gap-3 2xl:grid-cols-2">
          <RealGridMapPanel
            title="No stabilization"
            subtitle="Disturbance propagates without corrective action"
            tone="before"
            outcome={result?.outcome_A}
            state={currentFrame?.A}
            compareState={currentFrame?.B}
            dashboard={dashboard}
            consumerProxies={consumerProxies}
            loading={loading || running}
            actions={[]}
          />
          <RealGridMapPanel
            title="Tiangou stabilization active"
            subtitle="Fast producer redispatch and flexible load control"
            tone="after"
            outcome={result?.outcome_B}
            state={currentFrame?.B}
            compareState={currentFrame?.A}
            dashboard={dashboard}
            consumerProxies={consumerProxies}
            loading={loading || running}
            actions={actions}
          />
        </section>
      </div>
    </main>
  )
}

function RealGridMapPanel({
  title,
  subtitle,
  tone,
  outcome,
  state,
  compareState,
  dashboard,
  consumerProxies,
  loading,
  actions,
}: {
  title: string
  subtitle: string
  tone: "before" | "after"
  outcome?: string
  state?: DynamicState
  compareState?: DynamicState
  dashboard: DashboardSnapshot | null
  consumerProxies: ConsumerProxyMarker[]
  loading: boolean
  actions: Array<{ t: number; action: string }>
}) {
  const { routes, markers } = useRealGridLayers(dashboard, state, compareState, consumerProxies, tone)
  const accent = tone === "after" ? "#15803d" : "#b91c1c"
  const critical = (state?.f ?? 50) < 49 || outcome === "BLACKOUT"
  const stable = outcome === "STABLE" && (state?.f ?? 0) >= 49.5

  return (
    <Card className="min-h-[640px] overflow-hidden rounded-[8px] bg-[#fbfbfa]">
      <div className="flex items-start justify-between gap-3 border-b border-zinc-200 px-3 py-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">{title}</CardTitle>
            <Badge variant="outline" className={cn("rounded-[3px] px-2 py-1", outcomeClass(outcome))}>
              {outcome ?? "PENDING"}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-zinc-600">{subtitle}</p>
        </div>
        <div className="grid grid-cols-3 gap-1.5 text-xs">
          <Metric label="Hz" value={state ? formatNumber(state.f, 3) : "n/a"} />
          <Metric label="Pm" value={`${formatNumber(state?.Pm, 0)} MW`} />
          <Metric label="Pe" value={`${formatNumber(state?.Pe, 0)} MW`} />
        </div>
      </div>

      <div className="relative h-[calc(100%-73px)] min-h-[560px]">
        <GeoMap
          center={HONG_KONG_CENTER}
          zoom={10}
          theme="light"
          loading={loading}
          className="h-full w-full"
        >
          <MapControls position="top-right" />
          {routes.map((route) => (
            <MapRoute
              key={route.id}
              id={`${tone}-${route.id}`}
              coordinates={route.coordinates}
              color={route.color}
              width={route.width}
              opacity={route.opacity}
              dashArray={route.dashArray}
            />
          ))}
          {markers.map((point) => (
            <MapMarker key={`${tone}-${point.id}`} longitude={point.longitude} latitude={point.latitude}>
              <MarkerContent>
                <DynamicPointMarker point={point} />
              </MarkerContent>
              <MarkerTooltip>
                <MarkerTip title={point.label} rows={point.rows} />
              </MarkerTooltip>
            </MapMarker>
          ))}
        </GeoMap>

        <div className="pointer-events-none absolute left-3 top-3 z-[2] max-w-[calc(100%-1.5rem)] rounded-[6px] border border-zinc-300 bg-[#fbfbfa]/95 p-2 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="rounded-[3px] px-2 py-1 text-white" style={{ backgroundColor: accent }}>
              {tone === "after" ? "protected timeline" : "uncontrolled timeline"}
            </Badge>
            <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white/85 px-2 py-1">
              {formatNumber(routes.length)} solver branches
            </Badge>
            <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white/85 px-2 py-1">
              {formatNumber(markers.length)} grid markers
            </Badge>
          </div>
        </div>

        {(critical || stable) && (
          <div className={cn(
            "pointer-events-none absolute bottom-3 left-3 right-3 z-[2] rounded-[6px] border px-3 py-2 shadow-sm",
            critical ? "border-red-300 bg-red-50/95 text-red-900" : "border-emerald-300 bg-emerald-50/95 text-emerald-900",
          )}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold">
                {critical ? "Blackout cascade: frequency collapse" : "System held: corrective actions active"}
              </div>
              <div className="font-mono text-xs tabular-nums">
                f={formatNumber(state?.f, 3)} Hz, RoCoF={formatNumber(state?.df_dt, 4)} Hz/s
              </div>
            </div>
            {tone === "after" && actions.length > 0 && (
              <div className="mt-1 line-clamp-2 text-xs">
                {actions.slice(-3).map((entry) => `t=${entry.t}s ${entry.action}`).join(" | ")}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

function useRealGridLayers(
  dashboard: DashboardSnapshot | null,
  state: DynamicState | undefined,
  compareState: DynamicState | undefined,
  consumerProxies: ConsumerProxyMarker[],
  tone: "before" | "after",
) {
  return useMemo(() => {
    const caseData = dashboard?.powermodels_case
    const topology = dashboard?.topology
    if (!dashboard || !caseData || !topology) return { routes: [] as RouteLayer[], markers: [] as MarkerPoint[] }

    const busBySourceId = new globalThis.Map<string, TopologyBus>()
    for (const bus of topology.buses ?? []) busBySourceId.set(bus.id, bus)

    const previewBranchById = new globalThis.Map<string, TopologyBranch>()
    for (const branch of topology.branches ?? []) previewBranchById.set(branch.id, branch)

    const rawRouteBySourceId = new globalThis.Map<string, [number, number][]>()
    for (const asset of dashboard.assets ?? []) {
      if (isLinearAsset(asset)) rawRouteBySourceId.set(assetSourceId(asset), routeCoordinates(asset))
    }

    const caseBusByNumber = new globalThis.Map<number, PowerModelsBus>()
    for (const bus of Object.values(caseData.bus ?? {})) caseBusByNumber.set(bus.bus_i, bus)

    const coordinateForBus = (sourceId: string | undefined): [number, number] | null => {
      if (!sourceId) return null
      const bus = busBySourceId.get(sourceId)
      if (!bus || bus.lat === null || bus.lon === null) return null
      return [bus.lon, bus.lat]
    }

    const branchCoordinates = (branch: TopologyBranch): [number, number][] => {
      const rawRoute = rawRouteBySourceId.get(branch.id)
      if (rawRoute && rawRoute.length > 1) return rawRoute
      const from = coordinateForBus(branch.from_bus_id ?? undefined)
      const to = coordinateForBus(branch.to_bus_id ?? undefined)
      return from && to ? [from, to] : []
    }

    const solverBranchCoordinates = (branch: PowerModelsBranch): [number, number][] => {
      const preview = previewBranchById.get(branch.source_id)
      if (preview) return branchCoordinates(preview)
      const from = coordinateForBus(caseBusByNumber.get(branch.f_bus)?.source_id)
      const to = coordinateForBus(caseBusByNumber.get(branch.t_bus)?.source_id)
      return from && to ? [from, to] : []
    }

    const routes = Object.entries(caseData.branch ?? {}).flatMap(([id, branch]) => {
      const coordinates = solverBranchCoordinates(branch)
      if (coordinates.length < 2) return []
      const synthetic = branch.provenance?.includes("public") || branch.provenance?.includes("synthetic") || branch.source_id.startsWith("synthetic:")
      return [{
        id: `solver-${id}`,
        label: branch.source_id,
        coordinates,
        color: synthetic ? "#2563eb" : tone === "after" ? "#15803d" : "#b91c1c",
        width: synthetic ? 3 : 4,
        opacity: synthetic ? 0.48 : 0.72,
        dashArray: branch.transformer || synthetic ? [3, 2] as [number, number] : undefined,
      }]
    })

    const sourceById = new globalThis.Map<string, DynamicSource>()
    const compareSourceById = new globalThis.Map<string, DynamicSource>()
    for (const source of state?.active_sources ?? []) {
      if (source.source_id) sourceById.set(source.source_id, source)
      sourceById.set(source.name, source)
    }
    for (const source of compareState?.active_sources ?? []) {
      if (source.source_id) compareSourceById.set(source.source_id, source)
      compareSourceById.set(source.name, source)
    }

    const markers: MarkerPoint[] = []

    for (const [id, gen] of Object.entries(caseData.gen ?? {})) {
      const bus = caseBusByNumber.get(gen.gen_bus)
      const coord = coordinateForBus(bus?.source_id)
      if (!coord) continue
      const pmaxMw = gen.pmax * 100
      const dynamic = sourceById.get(id) ?? (gen.name ? sourceById.get(gen.name) : undefined)
      const compare = compareSourceById.get(id) ?? (gen.name ? compareSourceById.get(gen.name) : undefined)
      const output = dynamic?.current_output_mw ?? 0
      const compareOutput = compare?.current_output_mw ?? 0
      const tripped = dynamic ? !dynamic.online || output <= 0.01 : false
      const activated = tone === "after" && output > compareOutput + 1
      markers.push({
        id: `gen-${id}`,
        label: gen.name ?? gen.resource_type,
        longitude: coord[0],
        latitude: coord[1],
        size: Math.max(20, Math.min(48, 14 + Math.sqrt(Math.max(pmaxMw, 1)) / 2)),
        color: tripped ? "#991b1b" : activated ? "#15803d" : provenanceColor(gen.provenance),
        kind: "generator",
        state: tripped ? "tripped" : activated ? "activated" : "normal",
        rows: [
          ["Layer", "Solver generator"],
          ["Pmax MW", formatNumber(pmaxMw, pmaxMw < 10 ? 2 : 1)],
          ["Output MW", formatNumber(output, output < 10 ? 2 : 1)],
          ["Source", gen.energy_source ?? gen.resource_type],
          ["Operator", gen.operator ?? "n/a"],
          ["Provenance", gen.provenance ?? "n/a"],
        ],
      })
    }

    for (const [id, load] of Object.entries(caseData.load ?? {})) {
      const bus = caseBusByNumber.get(load.load_bus)
      const coord = coordinateForBus(bus?.source_id)
      if (!coord) continue
      const pdMw = load.pd * 100
      markers.push({
        id: `load-${id}`,
        label: `${load.service_territory ?? "unknown"} load`,
        longitude: coord[0],
        latitude: coord[1],
        size: Math.max(12, Math.min(30, 10 + Math.sqrt(Math.max(pdMw, 1)) / 2)),
        color: provenanceColor(load.provenance),
        kind: "load",
        state: tone === "after" && (state?.demand_extra_mw ?? 0) < 0 ? "activated" : "normal",
        rows: [
          ["Layer", "Solver load"],
          ["MW", formatNumber(pdMw, 1)],
          ["Sector", load.sector ?? "aggregate"],
          ["District", load.district ?? "n/a"],
          ["Provenance", load.provenance ?? "n/a"],
        ],
      })
    }

    for (const proxy of consumerProxies.filter((proxy) => Number.isFinite(proxy.lat) && Number.isFinite(proxy.lon)).slice(0, 220)) {
      markers.push({
        id: `consumer-${proxy.id}`,
        label: proxy.name || proxy.reason.replaceAll("_", " "),
        longitude: proxy.lon,
        latitude: proxy.lat,
        size: Math.max(12, Math.min(24, 11 + Math.sqrt(Math.max(proxy.weight, 1)) / 48)),
        color: consumerColor(proxy.reason),
        kind: "consumer",
        state: tone === "after" && (proxy.reason === "charging_station" || proxy.reason === "data_center") && (state?.demand_extra_mw ?? 0) < 0 ? "activated" : "normal",
        rows: [
          ["Layer", "Important consumer"],
          ["Category", proxy.reason.replaceAll("_", " ")],
          ["Sector", proxy.sector.replaceAll("_", " ")],
          ["Weight", formatNumber(proxy.weight, 1)],
          ["Confidence", proxy.confidence === null ? "n/a" : formatNumber(proxy.confidence, 2)],
          ["Facility MW", proxy.data_center_load_estimate ? formatNumber(proxy.data_center_load_estimate.estimated_facility_mw, 1) : "n/a"],
        ],
      })
    }

    return { routes, markers }
  }, [compareState, consumerProxies, dashboard, state, tone])
}

function DynamicPointMarker({ point }: { point: MarkerPoint }) {
  const Icon = point.kind === "generator" ? Factory : point.kind === "consumer" ? PlugZap : CircleDot
  return (
    <div
      className={cn(
        "grid place-items-center rounded-full border shadow-[0_10px_30px_-14px_rgba(24,24,27,0.9)] transition",
        point.kind === "consumer" && "rounded-[5px]",
        point.state === "tripped" ? "border-red-100 ring-4 ring-red-600/25" : "border-white",
        point.state === "activated" && "ring-4 ring-emerald-600/25",
      )}
      style={{ width: point.size, height: point.size, backgroundColor: point.color }}
    >
      {point.state === "tripped" ? (
        <AlertTriangle className="size-3.5 text-white" strokeWidth={2.3} />
      ) : (
        <Icon className="size-3.5 text-white" strokeWidth={2.3} />
      )}
    </div>
  )
}

function MarkerTip({ title, rows }: { title: string; rows: Array<[string, string]> }) {
  return (
    <div className="w-72 rounded-[4px] border border-zinc-300 bg-white/96 p-2.5 text-left shadow-lg">
      <p className="text-sm font-semibold leading-snug text-zinc-950">{title}</p>
      <dl className="mt-2 grid grid-cols-[88px_minmax(0,1fr)] gap-x-2 gap-y-1 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-zinc-500">{label}</dt>
            <dd className="truncate font-medium text-zinc-900">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[4px] border border-zinc-200 bg-white px-2 py-1.5">
      <div className="text-[0.68rem] text-zinc-500">{label}</div>
      <div className="mt-0.5 truncate font-medium tabular-nums text-zinc-950">{value}</div>
    </div>
  )
}

function OutcomePanel({ label, outcome, state }: { label: string; outcome?: string; state?: DynamicState }) {
  return (
    <Card className="rounded-[8px] bg-[#fbfbfa]">
      <CardContent className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold">{label}</span>
          <Badge variant="outline" className={cn("rounded-[3px] px-2 py-1", outcomeClass(outcome))}>
            {outcome ?? "PENDING"}
          </Badge>
        </div>
        <div className="grid grid-cols-2 gap-1.5 text-xs">
          <Metric label="Frequency" value={`${formatNumber(state?.f, 3)} Hz`} />
          <Metric label="Inertia H" value={`${formatNumber(state?.H_physical, 3)} s`} />
          <Metric label="PINN H" value={`${formatNumber(state?.H_pinn, 3)} s`} />
          <Metric label="Band" value={state?.freq_band ?? "n/a"} />
        </div>
      </CardContent>
    </Card>
  )
}
