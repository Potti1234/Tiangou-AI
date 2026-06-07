import { useEffect, useRef, useState } from "react"
import { Link } from "@tanstack/react-router"
import { AlertTriangle, ArrowRight, CircleDot, Cross, Factory, Gauge, Loader2, MapPinned, PlugZap } from "lucide-react"

import blackoutFrame01 from "@/assets/landing/spain-blackout-frame-01-lit.png"
import blackoutFrame02 from "@/assets/landing/spain-blackout-frame-02-partial.png"
import blackoutFrame03 from "@/assets/landing/spain-blackout-frame-03-cascade.png"
import blackoutFrame04 from "@/assets/landing/spain-blackout-frame-04-dark.png"
import heroBackground from "@/assets/landing-hero-bg.png"
import symbolHongKongRisk from "@/assets/landing/symbol-hong-kong-risk.png"
import symbolInertia from "@/assets/landing/symbol-inertia.png"
import symbolMethod from "@/assets/landing/symbol-method.png"
import symbolProvenance from "@/assets/landing/symbol-provenance.png"
import tiangouLogo from "@/assets/tiangou-logo-transparent-no-text.png"
import { Button } from "@/components/ui/button"
import { Map as GeoMap, MapMarker, MapRoute, MarkerContent } from "@/components/ui/map"
import { cn } from "@/lib/utils"

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000"
const HONG_KONG_CENTER: [number, number] = [114.1694, 22.3193]

const BLACKOUT_FRAMES = [
  {
    src: blackoutFrame01,
    label: "Fully lit",
    time: "00:00",
    title: "The city is balanced.",
    body: "Frequency holds while generation and demand remain in sync.",
  },
  {
    src: blackoutFrame02,
    label: "First outage",
    time: "00:18",
    title: "The first districts go dark.",
    body: "A low-inertia grid has less time to absorb the disturbance.",
  },
  {
    src: blackoutFrame03,
    label: "Cascade",
    time: "00:42",
    title: "The cascade becomes visible.",
    body: "Critical loads remain, but the wider system is already losing stability.",
  },
  {
    src: blackoutFrame04,
    label: "Blackout",
    time: "01:00",
    title: "Then silence.",
    body: "By the time the lights are off, the physics has already happened.",
  },
]

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

type PowerModelsGen = {
  gen_bus: number
  pmax: number
  resource_type: string
  provenance: string | null
  name?: string | null
  operator?: string | null
  energy_source?: string | null
}

type PowerModelsCase = {
  bus: Record<string, PowerModelsBus>
  branch: Record<string, PowerModelsBranch>
  gen: Record<string, PowerModelsGen>
  _metadata: Record<string, unknown>
}

type DashboardSnapshot = {
  assets: GridAsset[]
  topology: {
    buses: TopologyBus[]
    branches: TopologyBranch[]
  }
  powermodels_case: PowerModelsCase
}

type DynamicSource = {
  name: string
  source_id?: string
  type: string
  capacity_mw: number
  current_output_mw: number
  H: number
  online: boolean
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

type GridStateFrame = {
  t: number
  A: DynamicState
  B: DynamicState
  intervention_triggered: boolean
  actions_taken: string[]
}

type DynamicSimulationResponse = {
  scenario: string
  duration_s: number
  frames: GridStateFrame[]
  outcome_A: string
  outcome_B: string
  kpis: Record<string, number | string | null>
  pinn_status: {
    checkpoint_loaded: boolean
    H_estimated: number
    checkpoint_status: string
  }
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

type RouteLayer = {
  id: string
  coordinates: [number, number][]
  color: string
  width: number
  opacity: number
  dashArray?: [number, number]
}

type LandingMarker = {
  id: string
  label: string
  longitude: number
  latitude: number
  color: string
  size: number
  kind: "generator" | "hospital" | "ev" | "load"
  state: "normal" | "tripped" | "protected" | "curtailed" | "activated"
}

type Narration = {
  kicker: string
  title: string
  body: string
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function frameOpacity(progress: number, index: number) {
  const center = index / (BLACKOUT_FRAMES.length - 1)
  const distance = Math.abs(progress - center)
  return clamp(1 - distance * 3.25, 0, 1)
}

function formatNumber(value: unknown, digits = 0) {
  if (typeof value !== "number" || Number.isNaN(value)) return "0"
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
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

export function LandingPage() {
  useEffect(() => {
    document.documentElement.classList.add("tiangou-landing-snap")
    return () => document.documentElement.classList.remove("tiangou-landing-snap")
  }, [])

  return (
    <main className="min-h-[100dvh] bg-[#efe8d3] text-[#1d1913]">
      <section className="relative min-h-[100svh] snap-start snap-always overflow-hidden border-b border-[#1d1913]/20">
        <img
          src={heroBackground}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(239,232,211,0.98)_0%,rgba(239,232,211,0.9)_34%,rgba(239,232,211,0.28)_58%,rgba(29,25,19,0.08)_100%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_72%_44%,rgba(206,71,72,0.1),transparent_35%)]" />

        <header className="relative z-[1] mx-auto flex w-full max-w-[1720px] items-center justify-between gap-4 px-5 py-5 sm:px-8 lg:px-10">
          <Link
            to="/"
            className="grid h-14 w-14 place-items-center transition hover:opacity-75"
            aria-label="Tiangou-AI home"
          >
            <img src={tiangouLogo} alt="" aria-hidden="true" className="h-full w-full object-contain" />
          </Link>
          <nav className="hidden items-center gap-8 text-sm font-medium text-[#1d1913]/78 md:flex">
            <Link to="/dashboard" className="transition hover:text-[#8d2024]">
              Dashboard
            </Link>
            <Link to="/dynamic" className="transition hover:text-[#8d2024]">
              Dynamic demo
            </Link>
            <Link to="/analytics" className="transition hover:text-[#8d2024]">
              Analytics
            </Link>
          </nav>
          <Button asChild className="rounded-none bg-[#1d1913] px-5 text-[#fff8e7] hover:bg-[#8d2024]">
            <Link to="/dynamic">
              Run demo
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </header>

        <div className="relative z-[1] mx-auto grid min-h-[calc(100svh-88px)] w-full max-w-[1720px] items-end px-5 pb-8 sm:px-8 lg:grid-cols-[minmax(0,0.82fr)_minmax(340px,0.42fr)] lg:px-10 lg:pb-10">
          <div className="max-w-[880px] pb-[8svh]">
            <div className="mb-8 flex max-w-xl items-center gap-3 border-y border-[#1d1913]/40 py-3 text-sm font-medium text-[#1d1913]/78">
              <Gauge className="size-4 text-[#8d2024]" />
              <span>PINN-estimated inertia on a reconstructed Hong Kong grid</span>
            </div>
            <h1 className="font-['Vercetti',Geist,ui-sans-serif] text-[clamp(4rem,8.7vw,6rem)] leading-[0.9] tracking-[-0.03em] text-[#1d1913]">
              TIANGOU-AI
            </h1>
            <p className="mt-5 max-w-2xl text-[clamp(1.35rem,2.2vw,2.3rem)] leading-[1.08] text-[#8d2024]">
              Hong Kong grid simulation as a moving system.
            </p>
            <p className="mt-7 max-w-[62ch] text-base leading-7 text-[#3b352d] sm:text-lg">
              Precompute a real-grid stress scenario, then scroll through the disturbance as frequency, generators,
              consumers, and intervention state change over time.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Button asChild className="rounded-none bg-[#ce4748] px-6 text-[#fff8e7] hover:bg-[#8d2024]">
                <Link to="/dynamic">
                  Run dynamic demo
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" className="rounded-none border-[#1d1913] bg-[#fff8e7]/70 px-6 text-[#1d1913] hover:bg-[#fff8e7]">
                <Link to="/dashboard">
                  View dashboard
                  <MapPinned className="size-4" />
                </Link>
              </Button>
            </div>
          </div>

          <aside className="mb-10 hidden max-w-sm justify-self-end border border-[#1d1913]/45 bg-[#efe8d3]/86 p-4 shadow-[8px_8px_0_rgba(29,25,19,0.18)] backdrop-blur-[2px] lg:block">
            <div className="flex items-center justify-between border-b border-[#1d1913]/30 pb-3 text-xs font-semibold uppercase tracking-[0.08em] text-[#3b352d]">
              <span>Scroll simulation</span>
              <span>00:00</span>
            </div>
            <div className="mt-4 grid grid-cols-[1fr_auto_1fr] gap-3 text-sm">
              <div>
                <div className="text-[#8d2024]">Uncontrolled</div>
                <div className="mt-2 h-1.5 bg-[#8d2024]" />
                <p className="mt-3 text-xs leading-5 text-[#3b352d]">Frequency collapse, no corrective action.</p>
              </div>
              <div className="h-full w-px bg-[#1d1913]/35" />
              <div>
                <div className="text-[#1f8f54]">Stabilized</div>
                <div className="mt-2 h-1.5 bg-[#1f8f54]" />
                <p className="mt-3 text-xs leading-5 text-[#3b352d]">Producer and load actions hold the system.</p>
              </div>
            </div>
          </aside>
        </div>
      </section>
      <BlackoutColdOpen />
      <DisturbanceSimulation />
      <LandingTextSections />
    </main>
  )
}

function BlackoutColdOpen() {
  const sectionRef = useRef<HTMLElement | null>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const updateProgress = () => {
      const section = sectionRef.current
      if (!section) return
      const rect = section.getBoundingClientRect()
      const travel = Math.max(1, rect.height - window.innerHeight)
      setProgress(clamp(-rect.top / travel, 0, 1))
    }

    updateProgress()
    window.addEventListener("scroll", updateProgress, { passive: true })
    window.addEventListener("resize", updateProgress)
    return () => {
      window.removeEventListener("scroll", updateProgress)
      window.removeEventListener("resize", updateProgress)
    }
  }, [])

  const activeIndex = Math.min(BLACKOUT_FRAMES.length - 1, Math.round(progress * (BLACKOUT_FRAMES.length - 1)))
  const activeFrame = BLACKOUT_FRAMES[activeIndex]

  return (
    <section ref={sectionRef} className="relative h-[420svh] snap-start snap-always bg-[#0f1212] text-[#fff8e7]">
      <div className="sticky top-0 h-[100svh] overflow-hidden">
        {BLACKOUT_FRAMES.map((frame, index) => (
          <img
            key={frame.src}
            src={frame.src}
            alt=""
            aria-hidden="true"
            className="absolute inset-0 h-full w-full object-cover transition-opacity duration-300 ease-out"
            style={{ opacity: frameOpacity(progress, index) }}
          />
        ))}
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(10,12,12,0.9)_0%,rgba(10,12,12,0.64)_36%,rgba(10,12,12,0.22)_68%,rgba(10,12,12,0.58)_100%)]" />
        <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-[#0f1212] to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-36 bg-gradient-to-t from-[#0f1212] to-transparent" />

        <div className="relative z-[1] mx-auto grid h-full w-full max-w-[1720px] grid-rows-[auto_1fr_auto] px-5 py-6 sm:px-8 lg:px-10">
          <div className="flex items-center justify-end gap-4 pb-4">
            <div className="font-['Vercetti',Geist,ui-sans-serif] text-2xl tabular-nums text-[#ce4748]">
              {activeFrame.time}
            </div>
          </div>

          <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,0.72fr)_minmax(320px,0.38fr)]">
            <div className="max-w-[760px]">
              <p className="mb-5 max-w-xl border-l border-[#ce4748] pl-4 text-base leading-7 text-[#fff8e7]/72">
                April 28, 2025. The Iberian Peninsula went dark. Hospitals switched to backup power,
                deaths were reported, and losses were estimated above EUR 1.6B.
              </p>
              <h2 className="font-['Vercetti',Geist,ui-sans-serif] text-[clamp(3.1rem,7.4vw,6rem)] leading-[0.9] tracking-[-0.03em] text-[#fff8e7]">
                This was not an accident.
              </h2>
              <p className="mt-5 text-[clamp(1.8rem,3.2vw,3rem)] leading-[1] text-[#ce4748]">
                It was physics.
              </p>
            </div>

            <aside className="max-w-md border border-[#fff8e7]/28 bg-[#0f1212]/72 p-4 backdrop-blur-[2px]">
              <div className="flex items-center justify-between gap-3 border-b border-[#fff8e7]/20 pb-3">
                <span className="text-sm font-semibold text-[#fff8e7]">{activeFrame.label}</span>
                <span className="text-xs font-medium text-[#fff8e7]/60">
                  {Math.round(progress * 100).toString().padStart(2, "0")}%
                </span>
              </div>
              <h3 className="mt-5 text-2xl leading-tight text-[#fff8e7]">{activeFrame.title}</h3>
              <p className="mt-3 text-sm leading-6 text-[#fff8e7]/72">{activeFrame.body}</p>
              <div className="mt-6 grid grid-cols-4 gap-2">
                {BLACKOUT_FRAMES.map((frame, index) => (
                  <div key={frame.label} className="space-y-2">
                    <div className="h-1 bg-[#fff8e7]/20">
                      <div
                        className="h-full bg-[#ce4748] transition-[width] duration-200"
                        style={{ width: progress >= index / (BLACKOUT_FRAMES.length - 1) ? "100%" : "0%" }}
                      />
                    </div>
                    <div className="text-[0.68rem] leading-tight text-[#fff8e7]/55">{frame.label}</div>
                  </div>
                ))}
              </div>
            </aside>
          </div>

          <div className="grid gap-3 border-t border-[#fff8e7]/24 pt-4 text-sm text-[#fff8e7]/68 md:grid-cols-[1fr_auto] md:items-end">
            <p className="max-w-[72ch] leading-6">
              The pitch starts with darkness because grid instability is not abstract. Once frequency leaves the safe band,
              operators have seconds, not hours.
            </p>
            <div className="font-['Vercetti',Geist,ui-sans-serif] text-xl text-[#ce4748]">
              Scroll to advance time
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function DisturbanceSimulation() {
  const sectionRef = useRef<HTMLElement | null>(null)
  const [progress, setProgress] = useState(0)
  const [dashboard, setDashboard] = useState<DashboardSnapshot | null>(null)
  const [result, setResult] = useState<DynamicSimulationResponse | null>(null)
  const [consumerProxies, setConsumerProxies] = useState<ConsumerProxyMarker[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const updateProgress = () => {
      const section = sectionRef.current
      if (!section) return
      const rect = section.getBoundingClientRect()
      const travel = Math.max(1, rect.height - window.innerHeight)
      setProgress(clamp(-rect.top / travel, 0, 1))
    }

    updateProgress()
    window.addEventListener("scroll", updateProgress, { passive: true })
    window.addEventListener("resize", updateProgress)
    return () => {
      window.removeEventListener("scroll", updateProgress)
      window.removeEventListener("resize", updateProgress)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const loadSimulation = async () => {
      setLoading(true)
      setError(null)
      try {
        const dashboardParams = new URLSearchParams({
          region_key: "hong-kong",
          include_hk_interties: "true",
          solver_include_policy: "demo_full_osm",
          include_synthetic_generator_connections: "true",
          asset_limit: "5000",
        })
        const [dashboardResponse, consumerResponse, simulationResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/grid/dashboard-snapshot?${dashboardParams}`, { signal: controller.signal }),
          fetch(`${API_BASE_URL}/grid/consumer-proxies/important?region_key=hong-kong&limit=500`, { signal: controller.signal }),
          fetch(`${API_BASE_URL}/dynamic/simulate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: controller.signal,
            body: JSON.stringify({
              scenario: "import_loss",
              duration_s: 400,
              demand_snapshot: "peak_16h",
              model_mode: "full_demo",
            }),
          }),
        ])
        if (!dashboardResponse.ok) throw new Error(`Dashboard API returned ${dashboardResponse.status}`)
        if (!consumerResponse.ok) throw new Error(`Consumer proxy API returned ${consumerResponse.status}`)
        if (!simulationResponse.ok) throw new Error(`Simulation API returned ${simulationResponse.status}`)
        setDashboard(await dashboardResponse.json() as DashboardSnapshot)
        setConsumerProxies(await consumerResponse.json() as ConsumerProxyMarker[])
        setResult(await simulationResponse.json() as DynamicSimulationResponse)
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return
        setError(err instanceof Error ? err.message : "Could not preload the grid simulation")
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    void loadSimulation()
    return () => controller.abort()
  }, [])

  const frames = result?.frames ?? []
  const simulationProgress = clamp((progress - 0.08) / 0.78, 0, 1)
  const frameIndex = Math.min(Math.max(frames.length - 1, 0), Math.round(simulationProgress * Math.max(frames.length - 1, 0)))
  const frame = frames[frameIndex]
  const actions = frames.slice(0, frameIndex + 1).flatMap((entry) => entry.actions_taken.map((action) => ({ t: entry.t, action })))
  const narration = narrationForFrame(frame, simulationProgress, actions)
  const chartPoints = frames.map((entry) => ({ t: entry.t, A: entry.A.f, B: entry.B.f }))

  return (
    <section ref={sectionRef} className="relative h-[520svh] snap-start snap-always bg-[#efe8d3] text-[#1d1913]">
      <div className="sticky top-0 h-[100svh] overflow-hidden">
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(239,232,211,1)_0%,rgba(239,232,211,0.94)_36%,rgba(206,71,72,0.12)_100%)]" />
        <div className="relative z-[1] mx-auto grid h-full w-full max-w-[1720px] grid-rows-[auto_1fr] gap-3 px-5 py-5 sm:px-8 lg:px-10">
          <SimulationNarrator narration={narration} frame={frame} actions={actions} loading={loading} error={error} />

          <div className="relative min-h-0">
            <div className="grid h-full min-h-0 gap-3 lg:grid-cols-2">
              <LandingSimulationMap
                title="Uncontrolled"
                subtitle="No corrective action"
                tone="before"
                dashboard={dashboard}
                state={frame?.A}
                compareState={frame?.B}
                consumerProxies={consumerProxies}
                loading={loading}
                progress={simulationProgress}
              />
              <LandingSimulationMap
                title="Tiangou active"
                subtitle="EV charging curtailment active"
                tone="after"
                dashboard={dashboard}
                state={frame?.B}
                compareState={frame?.A}
                consumerProxies={consumerProxies}
                loading={loading}
                progress={simulationProgress}
              />
            </div>

            <div className="pointer-events-none absolute bottom-2 left-1/2 z-[4] w-[min(460px,calc(100%-2rem))] -translate-x-1/2 border border-[#1d1913]/24 bg-[#fff8e7]/90 px-3 py-2 shadow-[6px_6px_0_rgba(29,25,19,0.12)] backdrop-blur-[2px]">
              <FrequencyTrace points={chartPoints} cursor={frameIndex} />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function SimulationNarrator({
  narration,
  frame,
  actions,
  loading,
  error,
}: {
  narration: Narration
  frame?: GridStateFrame
  actions: Array<{ t: number; action: string }>
  loading: boolean
  error: string | null
}) {
  const latestAction = actions.at(-1)

  return (
    <div className="grid min-h-[132px] gap-3 border-b border-[#1d1913]/18 pb-3 xl:grid-cols-[minmax(0,1fr)_minmax(280px,0.34fr)_auto] xl:items-end">
      <div className="max-w-[980px] self-end">
        <p className="text-sm font-semibold text-[#8d2024]">{narration.kicker}</p>
        <h2 className="mt-1 font-['Vercetti',Geist,ui-sans-serif] text-[clamp(2rem,3.8vw,3.7rem)] leading-[0.92] tracking-[-0.03em]">
          {narration.title}
        </h2>
      </div>
      <div className="self-end text-sm leading-6 text-[#3b352d]">
        {loading && (
          <span className="inline-flex items-center gap-2">
            <Loader2 className="size-4 animate-spin text-[#ce4748]" />
            Precomputing one Hong Kong stress scenario.
          </span>
        )}
        {!loading && !error && narration.body}
        {error && <span className="text-[#8d2024]">{error}</span>}
        {latestAction && !error && (
          <div className="mt-1 text-xs font-medium text-[#8d2024]">
            t={latestAction.t}s: {latestAction.action}
          </div>
        )}
      </div>
      <div className="self-end justify-self-start font-['Vercetti',Geist,ui-sans-serif] text-2xl tabular-nums text-[#8d2024] xl:justify-self-end">
        t={formatNumber(frame?.t ?? 0, 0)}s
      </div>
    </div>
  )
}

function narrationForFrame(frame: GridStateFrame | undefined, progress: number, actions: Array<{ t: number; action: string }>) {
  if (!frame) {
    return {
      kicker: "Preload",
      title: "The scenario is prepared before you arrive.",
      body: "The page runs one backend simulation before this section enters view.",
    }
  }
  if (progress < 0.12) {
    return {
      kicker: "Stable start",
      title: "Both grids begin in balance.",
      body: "Same Hong Kong grid, same initial frequency, same demand.",
    }
  }
  if (progress < 0.28) {
    return {
      kicker: "Generator trip",
      title: "One plant drops out.",
      body: "The left side receives no correction. The right side starts preparing flexible demand.",
    }
  }
  if (progress < 0.52) {
    return {
      kicker: "Frequency drops",
      title: "The unstable case starts to lose balance.",
      body: `The uncontrolled system falls toward ${formatNumber(frame.A.f, 3)} Hz. The protected case keeps monitoring inertia and mismatch.`,
    }
  }
  if (actions.length > 0 && progress < 0.78) {
    return {
      kicker: "Intervention",
      title: "EV charging is curtailed first.",
      body: "Hospitals stay protected while EV charging loads switch off one by one.",
    }
  }
  return {
    kicker: "Outcome",
    title: frame.B.f >= 49.5 ? "The protected grid keeps operating." : "The system is still under stress.",
    body: `At this point the uncontrolled case is at ${formatNumber(frame.A.f, 3)} Hz, while the Tiangou case is at ${formatNumber(frame.B.f, 3)} Hz with ${formatNumber(actions.length)} corrective actions triggered.`,
  }
}

function FrequencyTrace({ points, cursor }: { points: Array<{ t: number; A: number; B: number }>; cursor: number }) {
  const width = 320
  const height = 132
  const minY = 47
  const maxY = 53
  const visiblePoints = points.slice(0, Math.max(cursor + 1, 2))
  const visibleMaxT = Math.max(visiblePoints.at(-1)?.t ?? 1, 1)
  const toX = (t: number) => (t / visibleMaxT) * width
  const toY = (f: number) => height - ((f - minY) / (maxY - minY)) * height
  const pathFor = (key: "A" | "B") =>
    visiblePoints.map((point, index) => `${index === 0 ? "M" : "L"} ${toX(point.t).toFixed(2)} ${toY(point[key]).toFixed(2)}`).join(" ")
  const cursorX = visiblePoints.at(-1) ? toX(visiblePoints.at(-1)?.t ?? 0) : 0

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[0.68rem] text-[#3b352d]">
        <span>Frequency</span>
        <span className="tabular-nums">47-53 Hz scale</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Frequency trace comparing uncontrolled and Tiangou stabilization" className="h-[132px] w-full overflow-hidden">
        <rect x="0" y="0" width={width} height={height} fill="#fff8e7" opacity="0.38" />
        <line x1="0" x2={width} y1={toY(50)} y2={toY(50)} stroke="#1d1913" opacity="0.28" />
        <line x1="0" x2={width} y1={toY(49.5)} y2={toY(49.5)} stroke="#8d2024" strokeDasharray="5 4" opacity="0.45" />
        <line x1="0" x2={width} y1={toY(49.0)} y2={toY(49.0)} stroke="#8d2024" strokeDasharray="5 4" opacity="0.72" />
        <line x1="0" x2={width} y1={toY(47)} y2={toY(47)} stroke="#1d1913" opacity="0.28" />
        <path d={pathFor("A")} fill="none" stroke="#8d2024" strokeWidth="4" strokeLinecap="round" />
        <path d={pathFor("B")} fill="none" stroke="#1f8f54" strokeWidth="4" strokeLinecap="round" />
        <line x1={cursorX} x2={cursorX} y1="0" y2={height} stroke="#1d1913" strokeWidth="1.5" />
        <text x="4" y="11" fill="#3b352d" fontSize="9">53</text>
        <text x="4" y={toY(50) - 3} fill="#3b352d" fontSize="9">50</text>
        <text x="4" y={height - 4} fill="#3b352d" fontSize="9">47</text>
      </svg>
    </div>
  )
}

function LandingSimulationMap({
  title,
  subtitle,
  tone,
  dashboard,
  state,
  compareState,
  consumerProxies,
  loading,
  progress,
}: {
  title: string
  subtitle: string
  tone: "before" | "after"
  dashboard: DashboardSnapshot | null
  state?: DynamicState
  compareState?: DynamicState
  consumerProxies: ConsumerProxyMarker[]
  loading: boolean
  progress: number
}) {
  const { routes, markers } = useLandingGridLayers(dashboard, state, compareState, consumerProxies, tone, progress)
  const accent = tone === "after" ? "#1f8f54" : "#8d2024"

  return (
    <div className="relative min-h-[620px] overflow-hidden border border-[#1d1913]/28 bg-[#efe8d3]">
      <GeoMap
        center={HONG_KONG_CENTER}
        zoom={10}
        theme="light"
        loading={loading}
        className="h-full min-h-[620px] w-full"
        scrollZoom={false}
        dragPan={false}
        dragRotate={false}
        doubleClickZoom={false}
        keyboard={false}
        touchZoomRotate={false}
      >
        {routes.map((route) => (
          <MapRoute
            key={route.id}
            id={`${tone}-landing-${route.id}`}
            coordinates={route.coordinates}
            color={route.color}
            width={route.width}
            opacity={route.opacity}
            dashArray={route.dashArray}
          />
        ))}
        {markers.map((marker) => (
          <MapMarker key={`${tone}-${marker.id}`} longitude={marker.longitude} latitude={marker.latitude}>
            <MarkerContent className="cursor-default">
              <LandingMapMarker marker={marker} />
            </MarkerContent>
          </MapMarker>
        ))}
      </GeoMap>
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(239,232,211,0.12)_0%,rgba(239,232,211,0)_48%,rgba(239,232,211,0.22)_100%)]" />
      <div className="pointer-events-none absolute left-3 right-3 top-3 flex flex-wrap items-start justify-between gap-3">
        <div className="border border-[#1d1913]/24 bg-[#fff8e7]/88 px-3 py-2 text-[#1d1913] backdrop-blur-[2px]">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5" style={{ backgroundColor: accent }} />
            <h3 className="text-base font-semibold">{title}</h3>
          </div>
          <p className="mt-1 text-xs text-[#3b352d]">{subtitle}</p>
        </div>
        <div className="border border-[#1d1913]/24 bg-[#fff8e7]/88 px-3 py-2 text-right text-[#1d1913] backdrop-blur-[2px]">
          <div className="font-['Vercetti',Geist,ui-sans-serif] text-2xl tabular-nums">{state ? formatNumber(state.f, 3) : "50.000"}</div>
          <div className="text-xs text-[#3b352d]">Hz</div>
        </div>
      </div>
    </div>
  )
}

function useLandingGridLayers(
  dashboard: DashboardSnapshot | null,
  state: DynamicState | undefined,
  compareState: DynamicState | undefined,
  consumerProxies: ConsumerProxyMarker[],
  tone: "before" | "after",
  progress: number,
) {
  if (!dashboard || !state) return { routes: [] as RouteLayer[], markers: [] as LandingMarker[] }

  const busBySourceId = new globalThis.Map<string, TopologyBus>()
  for (const bus of dashboard.topology.buses ?? []) busBySourceId.set(bus.id, bus)

  const previewBranchById = new globalThis.Map<string, TopologyBranch>()
  for (const branch of dashboard.topology.branches ?? []) previewBranchById.set(branch.id, branch)

  const rawRouteBySourceId = new globalThis.Map<string, [number, number][]>()
  for (const asset of dashboard.assets ?? []) {
    if (isLinearAsset(asset)) rawRouteBySourceId.set(assetSourceId(asset), routeCoordinates(asset))
  }

  const caseBusByNumber = new globalThis.Map<number, PowerModelsBus>()
  for (const bus of Object.values(dashboard.powermodels_case.bus ?? {})) caseBusByNumber.set(bus.bus_i, bus)

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

  const routes = Object.entries(dashboard.powermodels_case.branch ?? {})
    .flatMap(([id, branch]) => {
      const coordinates = solverBranchCoordinates(branch)
      if (coordinates.length < 2) return []
      return [{ id, branch, coordinates }]
    })
    .sort((left, right) => {
      const leftScore = (left.branch.matched_voltage_kv ?? 0) * 10 + (left.branch.rate_a ?? 0)
      const rightScore = (right.branch.matched_voltage_kv ?? 0) * 10 + (right.branch.rate_a ?? 0)
      return rightScore - leftScore
    })
    .slice(0, 95)
    .map(({ id, branch, coordinates }, index) => {
      const synthetic = branch.provenance?.includes("public") || branch.provenance?.includes("synthetic") || branch.source_id.startsWith("synthetic:")
      const earlyStable = progress < 0.14
      const plantTrip = progress >= 0.14
      const collapse = progress >= 0.3
      const recovering = tone === "after" && progress >= 0.24
      const animatedWave = progress > index / 95
      return {
        id: `branch-${id}`,
        coordinates,
        color: earlyStable ? "#1f8f54" : tone === "before" && collapse && animatedWave ? "#ce4748" : recovering && animatedWave ? "#1f8f54" : plantTrip ? "#8d2024" : "#1f8f54",
        width: synthetic ? 2.2 : 3.5,
        opacity: synthetic ? 0.36 : animatedWave || earlyStable ? 0.8 : 0.48,
        dashArray: synthetic || branch.transformer ? [3, 3] as [number, number] : undefined,
      }
    })

  const sourceById = new globalThis.Map<string, DynamicSource>()
  const compareSourceById = new globalThis.Map<string, DynamicSource>()
  for (const source of state.active_sources ?? []) {
    if (source.source_id) sourceById.set(source.source_id, source)
    sourceById.set(source.name, source)
  }
  for (const source of compareState?.active_sources ?? []) {
    if (source.source_id) compareSourceById.set(source.source_id, source)
    compareSourceById.set(source.name, source)
  }

  const markers: LandingMarker[] = []
  for (const [index, [id, gen]] of Object.entries(dashboard.powermodels_case.gen ?? {})
    .sort(([, left], [, right]) => (right.pmax ?? 0) - (left.pmax ?? 0))
    .slice(0, 8)
    .entries()) {
    const bus = caseBusByNumber.get(gen.gen_bus)
    const coord = coordinateForBus(bus?.source_id)
    if (!coord) continue
    const dynamic = sourceById.get(id) ?? (gen.name ? sourceById.get(gen.name) : undefined)
    const compare = compareSourceById.get(id) ?? (gen.name ? compareSourceById.get(gen.name) : undefined)
    const output = dynamic?.current_output_mw ?? 0
    const compareOutput = compare?.current_output_mw ?? 0
    const forcedTrip = tone === "before" && index === 0 && progress >= 0.14
    const tripped = forcedTrip || (dynamic ? !dynamic.online || output <= 0.01 : false)
    const activated = tone === "after" && progress >= 0.28 && (output > compareOutput + 1 || index < 3)
    markers.push({
      id: `gen-${id}`,
      label: gen.name ?? gen.resource_type,
      longitude: coord[0],
      latitude: coord[1],
      color: tripped ? "#8d2024" : activated ? "#1f8f54" : progress < 0.14 ? "#1f8f54" : "#fff8e7",
      size: Math.max(18, Math.min(34, 16 + Math.sqrt(Math.max(gen.pmax * 100, 1)) / 3)),
      kind: "generator",
      state: tripped ? "tripped" : activated ? "activated" : "normal",
    })
  }

  const hospitalProxies = consumerProxies.filter((proxy) => proxy.reason === "hospital").slice(0, 10)
  const evProxies = consumerProxies.filter((proxy) => proxy.reason === "charging_station").slice(0, 22)
  const curtailedEvCount = tone === "after" ? Math.floor(clamp((progress - 0.26) / 0.42, 0, 1) * evProxies.length) : 0
  for (const [index, proxy] of [...hospitalProxies, ...evProxies].entries()) {
    if (!Number.isFinite(proxy.lat) || !Number.isFinite(proxy.lon)) continue
    const hospital = proxy.reason === "hospital"
    const evIndex = index - hospitalProxies.length
    const curtailed = !hospital && evIndex >= 0 && evIndex < curtailedEvCount
    markers.push({
      id: `consumer-${proxy.id}`,
      label: proxy.name || proxy.reason.replaceAll("_", " "),
      longitude: proxy.lon,
      latitude: proxy.lat,
      color: hospital ? "#1f8f54" : curtailed ? "#8d2024" : "#2777b8",
      size: hospital ? 18 : 14,
      kind: hospital ? "hospital" : "ev",
      state: hospital ? "protected" : curtailed ? "curtailed" : "normal",
    })
  }

  return { routes, markers }
}

function LandingMapMarker({ marker }: { marker: LandingMarker }) {
  const Icon = marker.kind === "generator" ? Factory : marker.kind === "hospital" ? Cross : marker.kind === "ev" ? PlugZap : CircleDot
  return (
    <div
      className={cn(
        "grid place-items-center border border-[#fff8e7] shadow-[0_0_24px_rgba(255,248,231,0.2)]",
        marker.kind === "ev" ? "rounded-[3px]" : "rounded-full",
        marker.state === "tripped" && "ring-4 ring-[#ce4748]/28",
        marker.state === "protected" && "ring-4 ring-[#1f8f54]/28",
        marker.state === "curtailed" && "opacity-55 ring-4 ring-[#8d2024]/30",
        marker.state === "activated" && "ring-4 ring-[#1f8f54]/36",
      )}
      title={marker.label}
      style={{ width: marker.size, height: marker.size, backgroundColor: marker.color }}
    >
      {marker.state === "tripped" ? (
        <AlertTriangle className="size-3.5 text-[#fff8e7]" strokeWidth={2.4} />
      ) : (
        <Icon className="size-3.5 text-[#0f1212]" strokeWidth={2.4} />
      )}
    </div>
  )
}

function LandingTextSections() {
  return (
    <>
      <TextImageSection
        image={symbolInertia}
        imageAlt=""
        title="Grids fail when physics runs out of margin."
        lead="Frequency is the visible signal. Inertia is the hidden buffer."
        body={[
          "Large rotating generators behave like heavy wheels. They slow down frequency changes after a shock. As coal and gas units retire, the same disturbance can move frequency faster.",
          "Tiangou treats the grid as a physical system first. The model estimates inertia from frequency dynamics, then tests whether the operating state can absorb the next disturbance.",
        ]}
        facts={[
          "Stable frequency is not the same as safe frequency.",
          "Low inertia reduces the time operators have to act.",
          "A useful warning has to arrive before the cascade is visible.",
        ]}
      />

      <TextImageSection
        image={symbolHongKongRisk}
        imageAlt=""
        title="Hong Kong is the right first grid to prove it."
        lead="Dense load, weather exposure, imported energy, and critical infrastructure sit on the same island-scale system."
        body={[
          "The risk is not only more renewable energy. It is renewable energy arriving at the same time as data-center demand, EV charging, hospitals, transport, and typhoon exposure.",
          "Our current model already brings those layers into one view: reconstructed grid topology, generators, demand assumptions, hospitals, EV charging stations, and other consumer proxies.",
        ]}
        facts={[
          "Coal generation is planned to phase out by 2035.",
          "Hospitals and transport loads need protected behavior.",
          "Flexible demand, such as EV charging, can become a stabilizing tool.",
        ]}
        reverse
      />

      <section className="snap-start bg-[#ce4748] text-[#fff8e7]">
        <div className="mx-auto grid min-h-[100svh] w-full max-w-[1720px] items-center gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:px-10">
          <div>
            <img
              src={symbolMethod}
              alt=""
              aria-hidden="true"
              loading="lazy"
              className="mx-auto max-h-[440px] w-full max-w-[520px] object-contain mix-blend-multiply"
            />
          </div>
          <div className="max-w-3xl">
            <p className="text-base font-semibold text-[#fff8e7]/78">What the platform does</p>
            <h2 className="mt-4 font-['Vercetti',Geist,ui-sans-serif] text-[clamp(3rem,6vw,5.6rem)] leading-[0.9] tracking-[-0.03em]">
              Estimate. Stress. Intervene.
            </h2>
            <div className="mt-10 grid gap-5">
              <ProofLine
                title="Estimate inertia from frequency dynamics."
                body="The PINN layer loads the trained checkpoint when available and exposes the estimated inertia used by the dynamic demo."
              />
              <ProofLine
                title="Run stress cases on the reconstructed Hong Kong grid."
                body="The landing simulation calls the same backend scenario and dashboard snapshot endpoints as the working demo."
              />
              <ProofLine
                title="Show corrective actions as grid state changes."
                body="The story highlights generator state, protected hospital loads, and EV charging curtailment as the scenario advances."
              />
            </div>
            <div className="mt-9 flex flex-wrap gap-3">
              <Button asChild className="rounded-none bg-[#fff8e7] px-6 text-[#8d2024] hover:bg-white">
                <Link to="/dynamic">
                  Run dynamic demo
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" className="rounded-none border-[#fff8e7] bg-transparent px-6 text-[#fff8e7] hover:bg-[#fff8e7]/10">
                <Link to="/analytics">View analytics</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="snap-start bg-[#efe8d3] text-[#1d1913]">
        <div className="mx-auto grid min-h-[100svh] w-full max-w-[1720px] items-center gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[1fr_1fr] lg:px-10">
          <div className="max-w-3xl">
            <p className="text-base font-semibold text-[#8d2024]">Optimization target</p>
            <h2 className="mt-4 font-['Vercetti',Geist,ui-sans-serif] text-[clamp(3rem,6vw,5.6rem)] leading-[0.9] tracking-[-0.03em]">
              Same stability. Less fuel.
            </h2>
            <p className="mt-7 max-w-[64ch] text-lg leading-8 text-[#3b352d]">
              The long-term operating question is precise: what is the minimum conventional generation needed to keep the grid stable while maximizing renewable energy?
            </p>
            <p className="mt-5 max-w-[64ch] text-base leading-7 text-[#3b352d]">
              Today the demo shows stress response and corrective action logic. The next solver layer turns that into dispatch recommendations: when to hold inertia support, when to curtail flexible demand, and when renewable output can safely carry more load.
            </p>
          </div>
          <div className="border border-[#1d1913]/28 bg-[#fff8e7]/72 p-5">
            <DispatchComparison />
          </div>
        </div>
      </section>

      <TextImageSection
        image={symbolProvenance}
        imageAlt=""
        title="The assumptions stay visible."
        lead="A useful grid model has to show what is measured, inferred, and synthetic."
        body={[
          "The repo is built around that distinction. Raw OSM assets, reconstructed circuits, solver handoff artifacts, consumer proxies, and validation warnings all remain inspectable.",
          "That honesty matters for a judge and for a grid operator. A model can be ambitious without pretending every cable rating, transformer setting, and demand profile is already public data.",
        ]}
        facts={[
          "Observed public data is separated from inferred topology.",
          "Synthetic assumptions are counted and surfaced.",
          "Solver artifacts can be inspected from the dashboard.",
        ]}
      />

      <section className="snap-start bg-[#1d1913] text-[#fff8e7]">
        <div className="mx-auto grid min-h-[100svh] w-full max-w-[1720px] items-center gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[0.9fr_1.1fr] lg:px-10">
          <div className="max-w-xl">
            <p className="text-base font-semibold text-[#ce4748]">Implementation path</p>
            <h2 className="mt-4 font-['Vercetti',Geist,ui-sans-serif] text-[clamp(3rem,6vw,5.6rem)] leading-[0.9] tracking-[-0.03em]">
              Hong Kong first. Greater Bay Area next.
            </h2>
          </div>
          <div className="grid gap-4">
            <MarketStep title="Build in Hong Kong" body="Use local grid topology, renewable generation, weather exposure, consumer proxies, and frequency data as the validation base." />
            <MarketStep title="Validate with operators and infrastructure partners" body="Turn the demo pipeline into a repeatable planning tool: scenario generation, dynamic stability screening, and assumption review." />
            <MarketStep title="Scale into Mainland China" body="Apply the same workflow to larger renewable-heavy systems where low-inertia operation is becoming a national priority." />
          </div>
        </div>
      </section>

      <section className="snap-start bg-[#ce4748] text-[#fff8e7]">
        <div className="mx-auto flex min-h-[100svh] w-full max-w-[1720px] flex-col justify-between px-5 py-8 sm:px-8 lg:px-10">
          <div className="flex items-center justify-between">
            <img src={tiangouLogo} alt="" aria-hidden="true" className="h-14 w-14 invert" />
            <Button asChild className="rounded-none bg-[#fff8e7] px-6 text-[#8d2024] hover:bg-white">
              <Link to="/dynamic">
                Run demo
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
          <div className="max-w-6xl pb-10">
            <h2 className="font-['Vercetti',Geist,ui-sans-serif] text-[clamp(4rem,10vw,6rem)] leading-[0.88] tracking-[-0.03em]">
              Spain happened. Hong Kong won't.
            </h2>
            <p className="mt-8 max-w-2xl text-[clamp(1.5rem,2.5vw,2.4rem)] leading-tight text-[#fff8e7]/86">
              In the legend, people made noise to bring the light back. Today, Tiangou keeps the lights on.
            </p>
          </div>
        </div>
      </section>
    </>
  )
}

function TextImageSection({
  image,
  imageAlt,
  title,
  lead,
  body,
  facts,
  reverse = false,
}: {
  image: string
  imageAlt: string
  title: string
  lead: string
  body: string[]
  facts: string[]
  reverse?: boolean
}) {
  return (
    <section className="snap-start bg-[#efe8d3] text-[#1d1913]">
      <div className={cn("mx-auto grid min-h-[100svh] w-full max-w-[1720px] items-center gap-12 px-5 py-20 sm:px-8 lg:grid-cols-[1.05fr_0.95fr] lg:px-10", reverse && "lg:grid-cols-[0.95fr_1.05fr]")}>
        <div className={cn("max-w-3xl", reverse && "lg:order-2")}>
          <h2 className="font-['Vercetti',Geist,ui-sans-serif] text-[clamp(3rem,6vw,5.6rem)] leading-[0.9] tracking-[-0.03em]">
            {title}
          </h2>
          <p className="mt-6 max-w-[62ch] text-[clamp(1.25rem,2vw,1.75rem)] leading-tight text-[#8d2024]">
            {lead}
          </p>
          <div className="mt-8 grid max-w-[70ch] gap-5 text-base leading-7 text-[#3b352d]">
            {body.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
          <div className="mt-10 grid gap-3">
            {facts.map((fact) => (
              <div key={fact} className="grid grid-cols-[16px_1fr] gap-3 border-t border-[#1d1913]/22 pt-3 text-sm leading-6 text-[#3b352d]">
                <span className="mt-2 h-2 w-2 bg-[#ce4748]" />
                <span>{fact}</span>
              </div>
            ))}
          </div>
        </div>
        <div className={cn("flex justify-center", reverse && "lg:order-1")}>
          <img
            src={image}
            alt={imageAlt}
            loading="lazy"
            className="w-full max-w-[520px] object-contain mix-blend-multiply"
          />
        </div>
      </div>
    </section>
  )
}

function ProofLine({ title, body }: { title: string; body: string }) {
  return (
    <div className="border-t border-[#fff8e7]/30 pt-4">
      <h3 className="text-xl font-semibold leading-tight">{title}</h3>
      <p className="mt-2 max-w-[64ch] text-base leading-7 text-[#fff8e7]/76">{body}</p>
    </div>
  )
}

function DispatchComparison() {
  const rows = [
    { label: "Conventional baseline", gas: 80, wind: 12, flexible: 0, color: "#8d2024" },
    { label: "Tiangou target state", gas: 15, wind: 58, flexible: 27, color: "#1f8f54" },
  ]

  return (
    <div>
      <div className="flex items-end justify-between gap-4 border-b border-[#1d1913]/24 pb-4">
        <div>
          <h3 className="text-2xl font-semibold">Dispatch comparison</h3>
          <p className="mt-1 text-sm leading-6 text-[#3b352d]">Illustrative target logic for the next solver layer.</p>
        </div>
        <span className="font-['Vercetti',Geist,ui-sans-serif] text-3xl text-[#8d2024]">15%</span>
      </div>
      <div className="mt-7 grid gap-8">
        {rows.map((row) => (
          <div key={row.label}>
            <div className="mb-3 flex items-center justify-between gap-4 text-sm">
              <span className="font-semibold">{row.label}</span>
              <span className="text-[#3b352d]">gas turbine support</span>
            </div>
            <div className="flex h-12 overflow-hidden border border-[#1d1913]/24">
              <div className="grid place-items-center text-xs font-semibold text-[#fff8e7]" style={{ width: `${row.gas}%`, backgroundColor: row.color }}>Gas</div>
              <div className="grid place-items-center text-xs font-semibold text-[#1d1913]" style={{ width: `${row.wind}%`, backgroundColor: "#1f8f54" }}>Wind</div>
              <div className="grid place-items-center text-xs font-semibold text-[#1d1913]" style={{ width: `${row.flexible}%`, backgroundColor: "#2777b8" }}>Flex</div>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-7 text-sm leading-6 text-[#3b352d]">
        This section is deliberately framed as a target outcome. The current repo demonstrates real-grid stress simulation and action visualization; dispatch optimization is the next solver integration layer.
      </p>
    </div>
  )
}

function MarketStep({ title, body }: { title: string; body: string }) {
  return (
    <div className="border border-[#fff8e7]/24 p-5">
      <h3 className="text-2xl font-semibold leading-tight">{title}</h3>
      <p className="mt-3 max-w-[70ch] text-base leading-7 text-[#fff8e7]/72">{body}</p>
    </div>
  )
}
