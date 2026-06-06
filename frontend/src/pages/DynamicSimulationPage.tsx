import { useCallback, useEffect, useMemo, useState } from "react"
import { Link } from "@tanstack/react-router"
import { Activity, AlertTriangle, Loader2, Play, RotateCcw, Zap } from "lucide-react"
import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000"

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
  pinn_status: {
    checkpoint_loaded: boolean
    H_estimated: number
    startup_training: boolean
    checkpoint_status: string
  }
}

type ScenarioPayload = {
  scenarios: DynamicScenario[]
  grid_source: DynamicSimulationResponse["grid_source"]
}

type ModelMode = "full_demo" | "transmission"

const chartConfig = {
  A: { label: "Before intervention", color: "#b91c1c" },
  B: { label: "After PINN dispatch", color: "#15803d" },
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
    <header className="sticky top-0 z-10 border-b border-zinc-200 bg-[#e5e7e3]/95 px-4 py-3 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="rounded-[3px] bg-zinc-950 px-2 py-1 text-white">Tiangou dynamic simulation</Badge>
            <Badge variant="outline" className="rounded-[3px] border-emerald-700/30 bg-emerald-50 px-2 py-1 text-emerald-900">
              Real grid derived
            </Badge>
          </div>
          <p className="mt-1 text-xs text-zinc-600">Frequency dynamics, PINN inertia estimate, scenario provenance, and before/after intervention timelines.</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Tabs value={modelMode} onValueChange={(value) => onModeChange(value as ModelMode)}>
            <TabsList className="h-8 bg-white/75">
              <TabsTrigger value="full_demo">Full demo grid</TabsTrigger>
              <TabsTrigger value="transmission">Transmission</TabsTrigger>
            </TabsList>
          </Tabs>
          <Button asChild variant="outline" className="rounded-[4px] border-zinc-300 bg-white/92">
            <Link to="/">Map</Link>
          </Button>
          <Button asChild variant="outline" className="rounded-[4px] border-zinc-300 bg-white/92">
            <Link to="/analytics">Analytics</Link>
          </Button>
          <Button type="button" variant="outline" onClick={onRefresh} disabled={loading} className="rounded-[4px] border-zinc-300 bg-white/92">
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
  const [selectedScenario, setSelectedScenario] = useState("combined_stress")
  const [duration, setDuration] = useState(400)
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [modelMode, setModelMode] = useState<ModelMode>("full_demo")
  const [result, setResult] = useState<DynamicSimulationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadScenarios = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ model_mode: modelMode })
      const response = await fetch(`${API_BASE_URL}/dynamic/scenarios?${params}`)
      if (!response.ok) throw new Error(`Dynamic scenarios API returned ${response.status}`)
      const payload = await response.json() as ScenarioPayload
      setScenarios(payload.scenarios)
      setGridSource(payload.grid_source)
      const availableIds = new Set(payload.scenarios.filter((scenario) => scenario.available).map((scenario) => scenario.id))
      if (!availableIds.has(selectedScenario)) {
        setSelectedScenario(availableIds.has("combined_stress") ? "combined_stress" : [...availableIds][0] ?? "")
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load dynamic scenarios")
    } finally {
      setLoading(false)
    }
  }, [modelMode, selectedScenario])

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
      setCursor(0)
      setPlaying(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run dynamic simulation")
    } finally {
      setRunning(false)
    }
  }, [duration, modelMode, selectedScenario])

  useEffect(() => {
    void loadScenarios()
  }, [loadScenarios])

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
  const chartData = useMemo(() => frames.map((frame) => ({
    t: frame.t,
    A: Number(frame.A.f.toFixed(3)),
    B: Number(frame.B.f.toFixed(3)),
  })), [frames])
  const actions = useMemo(() => frames.flatMap((frame) => frame.actions_taken.map((action) => ({ t: frame.t, action }))), [frames])

  return (
    <main className="min-h-[100dvh] bg-[#e5e7e3] text-zinc-950">
      <DynamicHeader loading={loading} modelMode={modelMode} onModeChange={setModelMode} onRefresh={() => void loadScenarios()} />
      <div className="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[340px_1fr]">
        <section className="space-y-4">
          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="size-4" />
                Scenario controls
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
              <Button type="button" onClick={() => void runSimulation()} disabled={running || !selectedScenario} className="w-full rounded-[4px] bg-zinc-950 text-white hover:bg-zinc-800">
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

          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader>
              <CardTitle>Scenario provenance</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <div className="font-medium text-zinc-950">{selected?.description ?? "No scenario selected"}</div>
                <div className="mt-1 text-zinc-600">{selected?.assumptions ?? "Dynamic scenario metadata is loading."}</div>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Metric label="Magnitude" value={`${formatNumber(selected?.magnitude_mw, 1)} MW`} />
                <Metric label="Profile" value={selected?.profile ?? "n/a"} />
                <Metric label="Sources" value={formatNumber(selected?.affected_sources?.length ?? 0)} />
                <Metric label="Type" value={selected?.type ?? "n/a"} />
              </div>
              <div className="space-y-1">
                {(selected?.affected_sources ?? []).slice(0, 4).map((source) => (
                  <Badge key={source} variant="outline" className="mr-1 rounded-[3px] border-zinc-300 bg-white">
                    {source}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader>
              <CardTitle>Assumption counts</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-2 text-xs">
              <Metric label="Generators" value={formatNumber(gridSource?.source_mapping.generator_count)} />
              <Metric label="Inferred sources" value={formatNumber(gridSource?.synthetic_assumption_counts.synthetic_or_inferred_source_count)} />
              <Metric label="EV proxies" value={formatNumber(gridSource?.synthetic_assumption_counts.ev_station_count)} />
              <Metric label="Data centers" value={formatNumber(gridSource?.synthetic_assumption_counts.data_center_count)} />
            </CardContent>
          </Card>
        </section>

        <section className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <OutcomePanel label="Before intervention" outcome={result?.outcome_A} state={currentFrame?.A} />
            <OutcomePanel label="After PINN dispatch" outcome={result?.outcome_B} state={currentFrame?.B} />
          </div>

          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="size-4" />
                Frequency timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ChartContainer config={chartConfig} className="h-[320px] min-h-[320px] w-full">
                <LineChart data={chartData} accessibilityLayer margin={{ left: 8, right: 16, top: 12, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="t" tickLine={false} axisLine={false} tickMargin={8} />
                  <YAxis domain={[48.5, 50.3]} tickLine={false} axisLine={false} tickMargin={8} />
                  <ReferenceLine y={49.5} stroke="#b45309" strokeDasharray="4 3" />
                  <ReferenceLine y={49.0} stroke="#b91c1c" strokeDasharray="4 3" />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Line type="monotone" dataKey="A" stroke="var(--color-A)" strokeWidth={2} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="B" stroke="var(--color-B)" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ChartContainer>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" onClick={() => setPlaying((value) => !value)} disabled={!frames.length} className="rounded-[4px] border-zinc-300 bg-white">
                  <Play className="size-4" />
                  {playing ? "Pause timeline" : "Play timeline"}
                </Button>
                <input
                  aria-label="Simulation timeline"
                  type="range"
                  min={0}
                  max={Math.max(frames.length - 1, 0)}
                  value={cursor}
                  onChange={(event) => setCursor(Number(event.target.value))}
                  className="min-w-56 flex-1"
                />
                <span className="font-mono text-xs tabular-nums text-zinc-600">t={currentFrame?.t ?? 0}s</span>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-3 md:grid-cols-3">
            <KpiCard label="Min frequency A" value={`${formatNumber(result?.kpis.min_frequency_A, 3)} Hz`} />
            <KpiCard label="Min frequency B" value={`${formatNumber(result?.kpis.min_frequency_B, 3)} Hz`} />
            <KpiCard label="Max RoCoF B" value={`${formatNumber(result?.kpis.max_rocof_B, 4)} Hz/s`} />
            <KpiCard label="H min B" value={`${formatNumber(result?.kpis.H_min_B, 3)} s`} />
            <KpiCard label="Interventions" value={formatNumber(result?.kpis.intervention_count)} />
            <KpiCard label="Cost/CO2 proxy" value={`$${formatNumber(result?.kpis.cost_saved_usd)} / ${formatNumber(result?.kpis.co2_avoided_kg)} kg`} />
          </div>

          <Card className="rounded-[8px] bg-[#fbfbfa]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="size-4" />
                Action log
              </CardTitle>
            </CardHeader>
            <CardContent>
              {actions.length ? (
                <div className="max-h-48 space-y-2 overflow-auto pr-1">
                  {actions.map((entry, index) => (
                    <div key={`${entry.t}-${index}`} className="grid grid-cols-[52px_1fr] gap-3 rounded-[4px] border border-zinc-200 bg-white px-3 py-2 text-sm">
                      <span className="font-mono text-xs tabular-nums text-zinc-500">{entry.t}s</span>
                      <span>{entry.action}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-[4px] border border-zinc-200 bg-white px-3 py-3 text-sm text-zinc-600">
                  Run a simulation to populate PINN intervention actions.
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[4px] border border-zinc-200 bg-white px-2 py-2">
      <div className="text-[0.72rem] text-zinc-500">{label}</div>
      <div className="mt-0.5 truncate font-medium text-zinc-950">{value}</div>
    </div>
  )
}

function OutcomePanel({ label, outcome, state }: { label: string; outcome?: string; state?: DynamicState }) {
  return (
    <Card className="rounded-[8px] bg-[#fbfbfa]">
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span>{label}</span>
          <Badge variant="outline" className={cn("rounded-[3px] px-2 py-1", outcomeClass(outcome))}>
            {outcome ?? "PENDING"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-2 text-xs">
        <Metric label="Frequency" value={`${formatNumber(state?.f, 3)} Hz`} />
        <Metric label="Inertia H" value={`${formatNumber(state?.H_physical, 3)} s`} />
        <Metric label="PINN H" value={`${formatNumber(state?.H_pinn, 3)} s`} />
        <Metric label="Band" value={state?.freq_band ?? "n/a"} />
      </CardContent>
    </Card>
  )
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <Card className="rounded-[8px] bg-[#fbfbfa]">
      <CardContent className="py-3">
        <div className="text-xs text-zinc-500">{label}</div>
        <div className="mt-1 text-lg font-semibold tabular-nums text-zinc-950">{value}</div>
      </CardContent>
    </Card>
  )
}
