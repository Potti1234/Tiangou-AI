import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  AlertTriangle,
  Building2,
  Cable,
  CircleDot,
  Cross,
  Database,
  Factory,
  GitBranch,
  Layers3,
  Loader2,
  MapPinned,
  Plane,
  PlugZap,
  RadioTower,
  RotateCcw,
  ServerCog,
  Ship,
  TrainFront,
  X,
  Zap,
} from "lucide-react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts"
import { Link } from "@tanstack/react-router"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  Map,
  MapControls,
  MapMarker,
  MapRoute,
  MarkerContent,
  MarkerTooltip,
} from "@/components/ui/map"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

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
  frequency: string | null
  cables: string | null
  circuits: string | null
  location: string | null
  lat: number | null
  lon: number | null
  tags: Record<string, string>
  geometry: OSMGeometryPoint[] | null
  updated_at: string
}

type TopologyBus = {
  id: string
  name: string | null
  power: string
  lat: number | null
  lon: number | null
  base_kv: number | null
  service_territory: string | null
  provenance: string | null
  confidence: number | null
}

type TopologyBranch = {
  id: string
  name: string | null
  power: string
  from_bus_id: string | null
  to_bus_id: string | null
  voltage_kv: number | null
  length_km: number | null
  provenance: string | null
  confidence: number | null
  circuit_class?: string | null
  circuit_count?: number | null
  parameter_defaults?: { matched_voltage_kv?: number; rate_mva?: number }
}

type TopologyPreview = {
  metadata: Record<string, unknown>
  quality: Record<string, unknown>
  buses: TopologyBus[]
  branches: TopologyBranch[]
  generators: TopologyGenerator[]
}

type TopologyGenerator = {
  id: string
  bus_id: string
  name: string | null
  source: string | null
  pmax_mw: number | null
  capacity_tag: string | null
  provenance: string | null
  confidence: number | null
}

type PowerModelsBus = {
  bus_i: number
  bus_type: number
  base_kv: number
  source_id: string
  service_territory: string | null
  provenance: string | null
}

type PowerModelsBranch = {
  f_bus: number
  t_bus: number
  source_id: string
  transformer: boolean
  rate_a: number
  matched_voltage_kv?: number
  circuit_class?: string | null
  circuit_count?: number | null
  provenance: string | null
  retention_policy?: string | null
  solver_retention_reason?: string | null
  confidence: number | null
}

type PowerModelsLoad = {
  load_bus: number
  pd: number
  qd: number
  service_territory: string | null
  district?: string | null
  sector?: string | null
  provenance?: string | null
  source_year?: number | null
  source_period?: string | null
  source_energy_gwh?: number | null
}

type PowerModelsGen = {
  gen_bus: number
  pmax: number
  resource_type: string
  provenance: string | null
  provenance_chain?: string[] | null
  service_territory: string | null
  name?: string | null
  operator?: string | null
  source_osm_type?: string | null
  source_osm_id?: number | null
  energy_source?: string | null
  capacity_tag?: string | null
  capacity_raw?: string | null
  confidence?: number | null
  connection_method?: string | null
  assigned_bus_id?: string | null
  original_bus_id?: string | null
}

type PowerModelsCase = {
  bus: Record<string, PowerModelsBus>
  branch: Record<string, PowerModelsBranch>
  load: Record<string, PowerModelsLoad>
  gen: Record<string, PowerModelsGen>
  _metadata: Record<string, unknown>
}

type ValidationPayload = {
  status: StageStatus
  errors: Array<Record<string, unknown>>
  warnings: Array<Record<string, unknown>>
  metrics: Record<string, unknown>
  voltage_mismatches: Array<{ source_id?: string | null }>
}

type TopologyDiagnosticBranch = {
  solver_branch_id: string
  source_id: string | null
  provenance: string | null
  category: string
  recommended_action: string
  from_bus_name?: string | null
  to_bus_name?: string | null
  from_base_kv?: number | null
  to_base_kv?: number | null
  branch_matched_voltage_kv?: number | null
  rate_mva?: number | null
  severe?: boolean
  endpoints?: Array<{ bus_source_id?: string | null; bus_base_kv?: number | null; relative_difference: number }>
}

type TopologyDiagnostics = {
  summary: Record<string, number>
  synthetic_branches: TopologyDiagnosticBranch[]
  voltage_mismatches: TopologyDiagnosticBranch[]
  recommended_next_fixes: Array<{ category: string; recommended_action: string; count: number }>
}

type ReconciliationAsset = {
  raw_id?: string
  generator_id?: string
  name: string | null
  power: string
  status: string
  reason: string
  parsed_pmax_mw?: number | null
  mapped_bus_id?: string | null
  reconstructed_branch_id?: string | null
  solver_branch_id?: string | null
}

type AssetReconciliation = {
  summary: Record<string, unknown>
  top_generation_assets: ReconciliationAsset[]
  top_linear_assets: ReconciliationAsset[]
  top_dropped_or_aggregated_assets: ReconciliationAsset[]
}

type BaselineRiskItem = {
  branch_id?: string
  bus_id?: string
  source_id?: string | null
  risk_score: number
  reasons: string[]
}

type BaselineWeakSpots = {
  schema: string
  study_type: string
  system_summary: {
    total_demand_mw: number
    total_pmax_mw: number
    reserve_margin_estimate: number | null
    synthetic_branch_share: number
    synthetic_branch_count: number
    inferred_voltage_count: number
    promoted_generator_count: number
    warning_count: number
    top_10_risky_branches: BaselineRiskItem[]
    top_10_risky_buses: BaselineRiskItem[]
    warnings: string[]
  }
}

type PipelineSummary = {
  stage_status: Record<string, StageStatus>
  raw_osm_counts_by_power: Record<string, number>
  topology_metadata: Record<string, unknown>
  quality: Record<string, unknown>
  solver_metadata: Record<string, unknown>
  validation: ValidationPayload
  diagnostics?: TopologyDiagnostics
  baseline_weak_spots?: BaselineWeakSpots
  asset_reconciliation?: AssetReconciliation
  handoff_artifacts: Record<string, string>
}

type DashboardSnapshot = {
  assets: GridAsset[]
  topology: TopologyPreview
  powermodels_case: PowerModelsCase
  summary: PipelineSummary
}

type AnalyticsCountRow = {
  key: string
  label: string
  count?: number
  mw?: number
  value?: number
}

type AnalyticsRiskRow = BaselineRiskItem & {
  connected_load_mw?: number
  load_proximity_mw?: number
}

type AnalyticsDashboardPayload = {
  schema: string
  metadata_cards: {
    buses: number
    branches: number
    loads: number
    generators: number
    total_demand_mw: number
    total_pmax_mw: number
    reserve_margin: number | null
    island_count: number
    synthetic_branch_share: number
    severe_voltage_mismatch_count: number
    observed_inferred_synthetic_row_counts: Record<string, number>
  }
  charts: {
    load_by_sector: AnalyticsCountRow[]
    load_by_provenance_class: AnalyticsCountRow[]
    generation_capacity_by_source: Array<{ energy_source: string; resource_type: string; pmax_mw: number }>
    branch_by_voltage_level: Array<{ voltage_level: string; branch_count: number; thermal_rating_mva: number }>
    branch_provenance_counts: AnalyticsCountRow[]
    bus_provenance_counts: AnalyticsCountRow[]
    weak_spot_risk_top_branches: AnalyticsRiskRow[]
    weak_spot_risk_top_buses: AnalyticsRiskRow[]
    low_confidence_assumption_counts: Array<{ category: string; count: number; example?: { assumption?: string; confidence?: number } | null }>
    consumer_proxy_counts_by_category: AnalyticsCountRow[]
    data_center_estimated_mw_top_sites: Array<{ id: string; name: string; estimated_facility_mw: number; estimated_it_mw: number; provenance: string; confidence: number }>
    demand_snapshots: Array<{ snapshot: string; total_demand_mw: number; total_pmax_mw: number; reserve_margin: number | null }>
  }
  transparency: {
    provenance_classes: Record<string, string>
    synthetic_note: string
  }
  solver_artifacts: {
    status: StageStatus
    raw_powermodels_export_generated: boolean
    gridsfm_relaxed_solvable_json_generated: boolean
    pyg_export_generated: boolean
    scenario_files_generated: boolean
    manifest_path: string
    manifest_exists: boolean
    manifest_export_count: number
    freshness: {
      raw_exports_fresh: boolean
      solvable_exports_fresh: boolean
      pyg_exports_fresh: boolean
      scenario_artifacts_fresh: boolean
      stale_codes: string[]
      error_codes: string[]
    }
    verification: {
      status: string
      metrics: Record<string, number>
      errors: Array<{ code: string; path?: string; stale_count?: number }>
    } | null
    latest_raw_powermodels_export: {
      status: string
      output_path: string | null
      output_exists: boolean
      demand_snapshot: string | null
      bus_count: number | null
      branch_count: number | null
      load_count?: number | null
      gen_count?: number | null
      total_pd_mw?: number | null
      total_pmax_mw?: number | null
    } | null
    feasibility_warning: string
  }
  model_parameters: {
    include_hk_interties: boolean
    solver_include_policy: string
    include_synthetic_generator_connections: boolean
    min_voltage_kv: number | null
    demand_snapshot: string
    hk_intertie_derate: number
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
    estimated_it_mw: number
    estimated_facility_mw: number
    pue: number
    method: string
    provenance: string
    confidence: number
  } | null
}

type AssumptionTable = {
  key: string
  category: string
  row_count: number
  provenance_counts: Record<string, number>
  rows: Array<Record<string, string>>
}

type AssumptionSummary = {
  status: StageStatus
  table_count: number
  row_count: number
  provenance_counts: Record<string, number>
  warnings: Array<Record<string, unknown>>
  errors: Array<Record<string, unknown>>
  tables: Array<{
    key: string
    category: string
    row_count: number
    status: string
    provenance_counts: Record<string, number>
  }>
}

type AssumptionTransparency = {
  summary: AssumptionSummary
  tables: AssumptionTable[]
}

type StageStatus = "not_run" | "running" | "warning" | "error" | "complete" | "ok"
type Mode = "raw" | "reconstructed" | "solver" | "validation" | "handoff"

type PowerStyle = {
  label: string
  color: string
  marker: string
  icon: typeof Zap
}

type ConsumerProxyStyle = {
  label: string
  color: string
  icon: typeof Zap
}

type RouteLayer = {
  id: string
  label: string
  coordinates: [number, number][]
  color: string
  width: number
  opacity: number
  dashArray?: [number, number]
}

type PointLayer = {
  id: string
  label: string
  longitude: number
  latitude: number
  color: string
  size: number
  icon: typeof CircleDot
  meta: Array<[string, string]>
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000"

const HONG_KONG_CENTER: [number, number] = [114.1694, 22.3193]
const POLL_MS = 60000
const IMPORTANT_CONSUMER_LIMIT = 1000

const MODES: Array<{ id: Mode; label: string; stage: string; icon: typeof Layers3 }> = [
  { id: "raw", label: "Raw OSM", stage: "raw_osm", icon: Database },
  { id: "reconstructed", label: "Reconstructed circuits", stage: "reconstructed_circuits", icon: Cable },
  { id: "solver", label: "Solver topology", stage: "solver_topology", icon: GitBranch },
  { id: "validation", label: "Validation", stage: "validation", icon: AlertTriangle },
  { id: "handoff", label: "Handoff artifacts", stage: "handoff_artifacts", icon: MapPinned },
]

const POWER_STYLES: Record<string, PowerStyle> = {
  plant: { label: "Plant", color: "#a16207", marker: "bg-amber-700", icon: Factory },
  generator: { label: "Generator", color: "#ca8a04", marker: "bg-yellow-600", icon: Zap },
  substation: { label: "Substation", color: "#b84336", marker: "bg-red-600", icon: ServerCog },
  sub_station: { label: "Substation", color: "#b84336", marker: "bg-red-600", icon: ServerCog },
  transformer: { label: "Transformer", color: "#2563eb", marker: "bg-blue-600", icon: GitBranch },
  line: { label: "Line", color: "#7a5a28", marker: "bg-stone-700", icon: Cable },
  minor_line: { label: "Minor line", color: "#7a5a28", marker: "bg-stone-600", icon: Cable },
  cable: { label: "Cable", color: "#6d6875", marker: "bg-stone-500", icon: Cable },
  tower: { label: "Tower", color: "#30343b", marker: "bg-zinc-800", icon: RadioTower },
  pole: { label: "Pole", color: "#3f3f46", marker: "bg-zinc-700", icon: CircleDot },
}

const FALLBACK_STYLE: PowerStyle = {
  label: "Other",
  color: "#52525b",
  marker: "bg-zinc-700",
  icon: CircleDot,
}

const CONSUMER_PROXY_STYLES: Record<string, ConsumerProxyStyle> = {
  data_center: { label: "Data center", color: "#2563eb", icon: Database },
  hospital: { label: "Hospital", color: "#dc2626", icon: Cross },
  charging_station: { label: "EV charger", color: "#16a34a", icon: PlugZap },
  station: { label: "Station", color: "#0891b2", icon: TrainFront },
  ferry_terminal: { label: "Ferry terminal", color: "#0284c7", icon: Ship },
  airport: { label: "Airport", color: "#0f766e", icon: Plane },
  terminal: { label: "Terminal", color: "#0f766e", icon: Plane },
  industrial_infrastructure: { label: "Industrial infrastructure", color: "#ea580c", icon: Factory },
  large_industrial_proxy: { label: "Large industrial proxy", color: "#c2410c", icon: Factory },
  large_commercial_proxy: { label: "Large commercial proxy", color: "#a16207", icon: Building2 },
}

const FALLBACK_CONSUMER_PROXY_STYLE: ConsumerProxyStyle = {
  label: "Consumer proxy",
  color: "#7c3aed",
  icon: CircleDot,
}

function styleFor(power: string) {
  return POWER_STYLES[power] ?? FALLBACK_STYLE
}

function consumerProxyStyleFor(reason: string) {
  return CONSUMER_PROXY_STYLES[reason] ?? FALLBACK_CONSUMER_PROXY_STYLE
}

function assetKey(asset: GridAsset) {
  return `${asset.osm_type}-${asset.osm_id}`
}

function assetSourceId(asset: GridAsset) {
  return `osm:${asset.osm_type}:${asset.osm_id}`
}

function assetTitle(asset: GridAsset) {
  return asset.name || asset.tags["name:en"] || `${styleFor(asset.power).label} ${asset.osm_id}`
}

function consumerProxyTitle(proxy: ConsumerProxyMarker) {
  return proxy.name || `${consumerProxyStyleFor(proxy.reason).label} ${proxy.id}`
}

function statusLabel(status: StageStatus | undefined) {
  if (!status) return "not run"
  return status === "ok" ? "complete" : status.replaceAll("_", " ")
}

function statusClass(status: StageStatus | undefined) {
  if (status === "complete" || status === "ok") return "border-emerald-700/30 bg-emerald-50 text-emerald-800"
  if (status === "running") return "border-blue-700/30 bg-blue-50 text-blue-800"
  if (status === "warning") return "border-amber-700/30 bg-amber-50 text-amber-800"
  if (status === "error") return "border-red-700/30 bg-red-50 text-red-800"
  return "border-zinc-300 bg-zinc-100 text-zinc-600"
}

function isLinearAsset(asset: GridAsset) {
  return (
    (asset.power === "line" ||
      asset.power === "minor_line" ||
      asset.power === "cable") &&
    asset.geometry &&
    asset.geometry.length > 1
  )
}

function isGenerationAsset(asset: GridAsset) {
  return asset.power === "plant" || asset.power === "generator"
}

function isSupportAsset(asset: GridAsset) {
  return asset.power === "tower" || asset.power === "pole" || asset.power === "portal" || asset.power === "insulator"
}

function reconstructedRouteStyle(branch: TopologyBranch, retainedInSolver: boolean): Pick<RouteLayer, "color" | "width" | "opacity" | "dashArray"> {
  const synthetic = branch.provenance?.includes("public") || branch.id.startsWith("synthetic:")
  const inferredTransformer = branch.provenance === "inferred_multi_voltage_facility_transformer"
  if (inferredTransformer) {
    return { color: "#2563eb", width: 3, opacity: retainedInSolver ? 0.82 : 0.34, dashArray: [4, 2] }
  }
  if (synthetic) {
    return { color: "#2563eb", width: 3, opacity: retainedInSolver ? 0.76 : 0.3, dashArray: [3, 2] }
  }
  if (branch.circuit_class && branch.circuit_class !== "inter_facility") {
    return {
      color: branch.circuit_class === "tap" ? "#a16207" : "#71717a",
      width: 2,
      opacity: 0.38,
      dashArray: [2, 3],
    }
  }
  return {
    color: retainedInSolver ? "#15803d" : branch.power === "cable" ? "#6d6875" : "#b45309",
    width: retainedInSolver ? 5 : 3,
    opacity: retainedInSolver ? 0.92 : 0.32,
    dashArray: undefined,
  }
}

function routeCoordinates(asset: GridAsset): [number, number][] {
  return (asset.geometry ?? []).map((point) => [point.lon, point.lat])
}

function formatNumber(value: unknown, digits = 0) {
  if (typeof value !== "number" || Number.isNaN(value)) return "0"
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function metric(summary: PipelineSummary | null, key: string) {
  const value = summary?.validation.metrics[key]
  return typeof value === "number" ? value : undefined
}

function metadataRecord(source: Record<string, unknown> | undefined, key: string) {
  const value = source?.[key]
  if (!value || typeof value !== "object" || Array.isArray(value)) return {}
  return value as Record<string, number>
}

function unknownRecord(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {}
  return value as Record<string, unknown>
}

function numericRecord(value: unknown) {
  const record = unknownRecord(value)
  return Object.fromEntries(
    Object.entries(record).filter((entry): entry is [string, number] => typeof entry[1] === "number"),
  )
}

function assumptionRows(assumptions: AssumptionTransparency | null, tableKey: string) {
  return assumptions?.tables.find((table) => table.key === tableKey)?.rows ?? []
}

function lowConfidenceAssumptionRows(assumptions: AssumptionTransparency | null) {
  return (assumptions?.tables ?? [])
    .flatMap((table) =>
      table.rows.map((row) => ({
        table: table.key,
        row,
        confidence: Number(row.confidence ?? 1),
      })),
    )
    .filter((item) => Number.isFinite(item.confidence))
    .sort((left, right) => left.confidence - right.confidence)
    .slice(0, 5)
}

function provenanceClass(provenance: string | null | undefined) {
  if (provenance?.startsWith("observed")) return "observed"
  if (provenance?.startsWith("inferred")) return "inferred"
  if (provenance?.startsWith("synthetic")) return "synthetic"
  return "unknown"
}

function provenanceColor(provenance: string | null | undefined) {
  const className = provenanceClass(provenance)
  if (className === "observed") return "#15803d"
  if (className === "inferred") return "#2563eb"
  if (className === "synthetic") return "#a16207"
  return "#71717a"
}

function MetadataRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-zinc-200/70 py-1.5 text-xs">
      <span className="text-zinc-500">{label}</span>
      <span className="max-w-[190px] truncate font-medium tabular-nums text-zinc-900">
        {typeof value === "number" ? formatNumber(value, 3) : String(value ?? "n/a")}
      </span>
    </div>
  )
}

function CountBadges({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts)
  if (!entries.length) return <p className="text-xs text-zinc-500">No counts reported.</p>
  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(([label, count]) => (
        <Badge key={label} variant="outline" className="rounded-[3px] border-zinc-300 bg-white/75">
          {label} {formatNumber(count)}
        </Badge>
      ))}
    </div>
  )
}

function statusCounts(source: Record<string, unknown> | undefined, key: string) {
  const value = source?.[key]
  if (!value || typeof value !== "object" || Array.isArray(value)) return {}
  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, number] => typeof entry[1] === "number"),
  )
}

function ReconciliationList({ title, items }: { title: string; items: ReconciliationAsset[] }) {
  if (!items.length) {
    return (
      <div>
        <p className="mb-1 text-[11px] font-medium text-zinc-500">{title}</p>
        <p className="rounded-[4px] border border-zinc-200 bg-white/70 px-2 py-1.5 text-xs text-zinc-500">No assets reported.</p>
      </div>
    )
  }
  return (
    <div>
      <p className="mb-1 text-[11px] font-medium text-zinc-500">{title}</p>
      <div className="space-y-1.5">
        {items.slice(0, 5).map((item) => (
          <div key={`${item.raw_id ?? item.generator_id ?? item.name}-${item.status}`} className="rounded-[4px] border border-zinc-200 bg-white/75 p-2">
            <div className="flex items-start justify-between gap-2">
              <p className="min-w-0 truncate text-[11px] font-semibold text-zinc-950">{item.name ?? item.raw_id ?? item.generator_id}</p>
              <Badge variant="outline" className="shrink-0 rounded-[3px] border-zinc-300 bg-zinc-50 text-[10px]">
                {item.status.replaceAll("_", " ")}
              </Badge>
            </div>
            <p className="mt-1 text-xs leading-5 text-zinc-600">{item.reason}</p>
            {typeof item.parsed_pmax_mw === "number" && (
              <p className="mt-1 text-[11px] font-medium tabular-nums text-zinc-500">{formatNumber(item.parsed_pmax_mw, 1)} MW candidate capacity</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function DiagnosticIssueList({ title, items }: { title: string; items: TopologyDiagnosticBranch[] }) {
  if (!items.length) {
    return (
      <div>
        <p className="mb-1 text-[11px] font-medium text-zinc-500">{title}</p>
        <p className="rounded-[4px] border border-zinc-200 bg-white/70 px-2 py-1.5 text-xs text-zinc-500">No issues reported.</p>
      </div>
    )
  }
  return (
    <div>
      <p className="mb-1 text-[11px] font-medium text-zinc-500">{title}</p>
      <div className="space-y-1.5">
        {items.slice(0, 5).map((item) => (
          <div key={`${item.solver_branch_id}-${item.category}`} className="rounded-[4px] border border-zinc-200 bg-white/75 p-2">
            <div className="flex items-start justify-between gap-2">
              <p className="min-w-0 truncate font-mono text-[11px] font-semibold text-zinc-950">{item.source_id ?? item.solver_branch_id}</p>
              <Badge variant="outline" className="shrink-0 rounded-[3px] border-zinc-300 bg-zinc-50 text-[10px]">
                {item.category}
              </Badge>
            </div>
            <p className="mt-1 text-xs text-zinc-600">{item.recommended_action}</p>
            <p className="mt-1 truncate text-[11px] text-zinc-500">
              {formatNumber(item.from_base_kv, 1)} kV to {formatNumber(item.to_base_kv, 1)} kV
              {typeof item.branch_matched_voltage_kv === "number" ? `, branch ${formatNumber(item.branch_matched_voltage_kv, 1)} kV` : ""}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

function BaselineRiskList({ title, items }: { title: string; items: BaselineRiskItem[] }) {
  if (!items.length) {
    return (
      <div>
        <p className="mb-1 text-[11px] font-medium text-zinc-500">{title}</p>
        <p className="rounded-[4px] border border-zinc-200 bg-white/70 px-2 py-1.5 text-xs text-zinc-500">No weak spots reported.</p>
      </div>
    )
  }
  return (
    <div>
      <p className="mb-1 text-[11px] font-medium text-zinc-500">{title}</p>
      <div className="space-y-1.5">
        {items.slice(0, 5).map((item) => (
          <div key={`${item.branch_id ?? item.bus_id}-${item.source_id ?? "source"}`} className="rounded-[4px] border border-zinc-200 bg-white/75 p-2">
            <div className="flex items-center justify-between gap-2">
              <p className="min-w-0 truncate font-mono text-[11px] font-semibold text-zinc-950">{item.source_id ?? item.branch_id ?? item.bus_id}</p>
              <Badge variant="outline" className="shrink-0 rounded-[3px] border-amber-300 bg-amber-50 text-[10px] text-amber-900">
                {formatNumber(item.risk_score, 0)}
              </Badge>
            </div>
            <p className="mt-1 truncate text-xs text-zinc-600">{item.reasons.slice(0, 2).join(", ")}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

const chartPalette = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
]

const demandChartConfig = {
  total_demand_mw: { label: "Demand MW", color: "var(--chart-1)" },
  total_pmax_mw: { label: "Pmax MW", color: "var(--chart-2)" },
} satisfies ChartConfig

const valueChartConfig = {
  mw: { label: "MW", color: "var(--chart-1)" },
  count: { label: "Count", color: "var(--chart-3)" },
  pmax_mw: { label: "Pmax MW", color: "var(--chart-2)" },
  branch_count: { label: "Branches", color: "var(--chart-4)" },
  thermal_rating_mva: { label: "Thermal MVA", color: "var(--chart-5)" },
  risk_score: { label: "Risk score", color: "var(--chart-1)" },
  estimated_facility_mw: { label: "Facility MW", color: "var(--chart-3)" },
} satisfies ChartConfig

function formatPercent(value: unknown, digits = 1) {
  if (typeof value !== "number" || Number.isNaN(value)) return "n/a"
  return `${formatNumber(value * 100, digits)}%`
}

function metricHelp(text: string) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="grid size-4 place-items-center rounded-full border border-zinc-300 text-[10px] text-zinc-500">
          ?
        </button>
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  )
}

function KpiCard({ label, value, help }: { label: string; value: string; help?: string }) {
  return (
    <Card size="sm" className="rounded-[6px] bg-white/78 py-3">
      <CardHeader className="px-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-[11px] font-medium uppercase tracking-[0.08em] text-zinc-500">{label}</CardTitle>
          {help ? metricHelp(help) : null}
        </div>
      </CardHeader>
      <CardContent className="px-3">
        <p className="text-lg font-semibold tabular-nums text-zinc-950">{value}</p>
      </CardContent>
    </Card>
  )
}

function ChartPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card size="sm" className="rounded-[6px] bg-white/78">
      <CardHeader className="px-3">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="px-3">
        {children}
      </CardContent>
    </Card>
  )
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="grid h-[180px] place-items-center rounded-[4px] border border-zinc-200 bg-zinc-50 text-xs text-zinc-500">
      {label}
    </div>
  )
}

function AnalyticsBarChart({
  data,
  dataKey,
  labelKey = "label",
  layout = "horizontal",
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  labelKey?: string
  layout?: "horizontal" | "vertical"
}) {
  if (!data.length) return <EmptyChart label="No chart rows available." />
  const vertical = layout === "vertical"
  return (
    <ChartContainer config={valueChartConfig} className="h-[210px] min-h-[210px] w-full">
      <BarChart accessibilityLayer data={data} layout={vertical ? "vertical" : "horizontal"} margin={{ left: vertical ? 8 : 0, right: 8, top: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={!vertical} vertical={vertical} />
        {vertical ? (
          <>
            <XAxis type="number" hide />
            <YAxis dataKey={labelKey} type="category" width={96} tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
          </>
        ) : (
          <>
            <XAxis dataKey={labelKey} tickLine={false} axisLine={false} tick={{ fontSize: 10 }} interval={0} tickFormatter={(value) => String(value).slice(0, 12)} />
            <YAxis width={36} tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
          </>
        )}
        <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
        <Bar dataKey={dataKey} fill={`var(--color-${dataKey})`} radius={vertical ? [0, 4, 4, 0] : [4, 4, 0, 0]} />
      </BarChart>
    </ChartContainer>
  )
}

function AnalyticsPieChart({ data }: { data: AnalyticsCountRow[] }) {
  if (!data.length) return <EmptyChart label="No provenance rows available." />
  return (
    <ChartContainer config={valueChartConfig} className="h-[210px] min-h-[210px] w-full">
      <PieChart accessibilityLayer>
        <ChartTooltip content={<ChartTooltipContent nameKey="label" />} />
        <Pie data={data} dataKey="count" nameKey="label" innerRadius={46} outerRadius={78} paddingAngle={2}>
          {data.map((entry, index) => (
            <Cell key={entry.key} fill={chartPalette[index % chartPalette.length]} />
          ))}
        </Pie>
        <ChartLegend content={<ChartLegendContent nameKey="label" />} />
      </PieChart>
    </ChartContainer>
  )
}

function AnalyticsDashboardTabs({ analytics }: { analytics: AnalyticsDashboardPayload | null }) {
  if (!analytics) {
    return (
      <Card size="sm" className="rounded-[6px] bg-white/78">
        <CardContent className="px-3 py-3 text-xs text-zinc-500">Analytics payload is loading.</CardContent>
      </Card>
    )
  }

  const cards = analytics.metadata_cards
  const branchRisks = analytics.charts.weak_spot_risk_top_branches.map((item) => ({
    ...item,
    label: item.source_id ?? item.branch_id ?? "branch",
  }))
  const busRisks = analytics.charts.weak_spot_risk_top_buses.map((item) => ({
    ...item,
    label: item.source_id ?? item.bus_id ?? "bus",
  }))
  const generationRows = analytics.charts.generation_capacity_by_source.map((row) => ({
    ...row,
    label: `${row.energy_source} ${row.resource_type}`.replaceAll("_", " "),
  }))
  const artifactRows: Array<[string, boolean, string]> = [
    ["Raw PowerModels export", analytics.solver_artifacts.raw_powermodels_export_generated, "fresh"],
    ["GridSFM relaxed/solvable JSON", analytics.solver_artifacts.gridsfm_relaxed_solvable_json_generated, "fresh"],
    ["PyG export", analytics.solver_artifacts.pyg_export_generated, "fresh"],
    ["Scenario files", analytics.solver_artifacts.scenario_files_generated, "fresh"],
  ]
  const latestExport = analytics.solver_artifacts.latest_raw_powermodels_export
  const staleCodes = analytics.solver_artifacts.freshness.stale_codes
  const modelParameters = analytics.model_parameters

  return (
    <TooltipProvider>
      <Tabs defaultValue="overview" className="gap-3">
        <TabsList className="grid w-full grid-cols-3 gap-0 sm:grid-cols-6">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="demand">Demand</TabsTrigger>
          <TabsTrigger value="generation">Generation</TabsTrigger>
          <TabsTrigger value="network">Network</TabsTrigger>
          <TabsTrigger value="weak-spots">Weak Spots</TabsTrigger>
          <TabsTrigger value="assumptions">Assumptions</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <KpiCard label="Buses" value={formatNumber(cards.buses)} />
            <KpiCard label="Branches" value={formatNumber(cards.branches)} />
            <KpiCard label="Demand" value={`${formatNumber(cards.total_demand_mw, 1)} MW`} />
            <KpiCard label="Reserve" value={formatPercent(cards.reserve_margin)} help="Estimated Pmax minus demand, divided by demand." />
          </div>
          <ChartPanel title="Demand snapshots">
            <ChartContainer config={demandChartConfig} className="h-[220px] min-h-[220px] w-full">
              <AreaChart accessibilityLayer data={analytics.charts.demand_snapshots} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="snapshot" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} tickFormatter={(value) => String(value).replace("_", " ")} />
                <YAxis width={44} tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Area type="monotone" dataKey="total_pmax_mw" stroke="var(--color-total_pmax_mw)" fill="var(--color-total_pmax_mw)" fillOpacity={0.18} />
                <Area type="monotone" dataKey="total_demand_mw" stroke="var(--color-total_demand_mw)" fill="var(--color-total_demand_mw)" fillOpacity={0.26} />
                <ChartLegend content={<ChartLegendContent />} />
              </AreaChart>
            </ChartContainer>
          </ChartPanel>
          <ChartPanel title="Load by provenance">
            <AnalyticsPieChart data={analytics.charts.load_by_provenance_class.map((row) => ({ ...row, count: Math.round(row.mw ?? 0) }))} />
          </ChartPanel>
        </TabsContent>

        <TabsContent value="demand" className="space-y-3">
          <ChartPanel title="Sector load">
            <AnalyticsBarChart data={analytics.charts.load_by_sector} dataKey="mw" layout="vertical" />
          </ChartPanel>
          <ChartPanel title="Consumer proxy categories">
            <AnalyticsBarChart data={analytics.charts.consumer_proxy_counts_by_category} dataKey="count" layout="vertical" />
          </ChartPanel>
          <ChartPanel title="Top data-center estimated facility MW">
            <AnalyticsBarChart data={analytics.charts.data_center_estimated_mw_top_sites.map((row) => ({ ...row, label: row.name }))} dataKey="estimated_facility_mw" layout="vertical" />
          </ChartPanel>
        </TabsContent>

        <TabsContent value="generation" className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <KpiCard label="Generators" value={formatNumber(cards.generators)} />
            <KpiCard label="Pmax" value={`${formatNumber(cards.total_pmax_mw, 1)} MW`} />
          </div>
          <ChartPanel title="Generation capacity by source">
            <AnalyticsBarChart data={generationRows} dataKey="pmax_mw" layout="vertical" />
          </ChartPanel>
        </TabsContent>

        <TabsContent value="network" className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <KpiCard label="Islands" value={formatNumber(cards.island_count)} />
            <KpiCard label="Synthetic share" value={formatPercent(cards.synthetic_branch_share)} />
          </div>
          <ChartPanel title="Branch count by voltage">
            <AnalyticsBarChart data={analytics.charts.branch_by_voltage_level.map((row) => ({ ...row, label: row.voltage_level }))} dataKey="branch_count" />
          </ChartPanel>
          <ChartPanel title="Branch provenance">
            <AnalyticsPieChart data={analytics.charts.branch_provenance_counts} />
          </ChartPanel>
          <ChartPanel title="Bus provenance">
            <AnalyticsPieChart data={analytics.charts.bus_provenance_counts} />
          </ChartPanel>
        </TabsContent>

        <TabsContent value="weak-spots" className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <KpiCard label="Severe mismatches" value={formatNumber(cards.severe_voltage_mismatch_count)} />
            <KpiCard label="Synthetic branches" value={formatPercent(cards.synthetic_branch_share)} />
          </div>
          <ChartPanel title="Top weak branches">
            <AnalyticsBarChart data={branchRisks} dataKey="risk_score" layout="vertical" />
          </ChartPanel>
          <ChartPanel title="Top weak buses">
            <AnalyticsBarChart data={busRisks} dataKey="risk_score" layout="vertical" />
          </ChartPanel>
        </TabsContent>

        <TabsContent value="assumptions" className="space-y-3">
          <ChartPanel title="Observed, inferred, synthetic rows">
            <div className="space-y-2">
              <CountBadges counts={cards.observed_inferred_synthetic_row_counts} />
              <p className="text-xs leading-5 text-zinc-600">{analytics.transparency.synthetic_note}</p>
            </div>
          </ChartPanel>
          <ChartPanel title="Low-confidence assumptions by category">
            <AnalyticsBarChart data={analytics.charts.low_confidence_assumption_counts.map((row) => ({ ...row, label: row.category }))} dataKey="count" layout="vertical" />
          </ChartPanel>
          <ChartPanel title="Solver artifact status">
            <div className="space-y-1.5">
              <div className="rounded-[4px] border border-zinc-200 bg-zinc-50 px-2 py-1.5 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-zinc-700">Dashboard model</span>
                  <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white text-zinc-800">
                    {modelParameters.solver_include_policy === "demo_full_osm" ? "Full demo grid" : "Transmission"}
                  </Badge>
                </div>
                <p className="mt-1 text-zinc-600">
                  {modelParameters.include_hk_interties ? "HK interties included" : "HK interties excluded"}, {modelParameters.include_synthetic_generator_connections ? "synthetic generator ties included" : "synthetic generator ties excluded"}
                </p>
              </div>
              {latestExport && (
                <div className="rounded-[4px] border border-zinc-200 bg-zinc-50 px-2 py-1.5 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-zinc-700">Latest raw PowerModels export</span>
                    <Badge variant="outline" className={cn("rounded-[3px]", latestExport.output_exists ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-amber-300 bg-amber-50 text-amber-900")}>
                      {latestExport.status.replaceAll("_", " ")}
                    </Badge>
                  </div>
                  <p className="mt-1 truncate font-mono text-[11px] text-zinc-500">{latestExport.output_path ?? "No output path in manifest"}</p>
                  <p className="mt-1 text-zinc-600">
                    {latestExport.demand_snapshot ?? "unknown snapshot"}, {formatNumber(latestExport.bus_count)} buses, {formatNumber(latestExport.branch_count)} branches
                  </p>
                </div>
              )}
              {artifactRows.map(([label, ok, readyLabel]) => (
                <div key={label} className="flex items-center justify-between gap-2 rounded-[4px] border border-zinc-200 bg-zinc-50 px-2 py-1.5 text-xs">
                  <span className="text-zinc-600">{label}</span>
                  <Badge variant="outline" className={cn("rounded-[3px]", ok ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-amber-300 bg-amber-50 text-amber-900")}>
                    {ok ? readyLabel : "missing or stale"}
                  </Badge>
                </div>
              ))}
              {staleCodes.length > 0 && (
                <div className="rounded-[4px] border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
                  Stale artifacts: {staleCodes.map((code) => code.replaceAll("_", " ")).join(", ")}
                </div>
              )}
              <p className="text-xs leading-5 text-amber-900">{analytics.solver_artifacts.feasibility_warning}</p>
            </div>
          </ChartPanel>
        </TabsContent>
      </Tabs>
    </TooltipProvider>
  )
}

function RawMarker({ asset, selected }: { asset: GridAsset; selected: boolean }) {
  const style = styleFor(asset.power)
  const Icon = style.icon
  const compact = asset.power === "tower" || asset.power === "pole"

  return (
    <div
      className={cn(
        "grid place-items-center rounded-full border border-zinc-950/70 shadow-sm transition active:scale-95",
        compact ? "size-2.5 bg-zinc-800" : "size-5 border-white",
        !compact && style.marker,
        selected && "scale-125 ring-4 ring-zinc-950/20",
      )}
    >
      {!compact && <Icon className="size-3 text-white" strokeWidth={2} />}
    </div>
  )
}

function PointMarker({ point }: { point: PointLayer }) {
  const Icon = point.icon
  return (
    <div
      className="grid place-items-center rounded-full border border-white shadow-[0_8px_28px_-12px_rgba(24,24,27,0.8)]"
      style={{ width: point.size, height: point.size, backgroundColor: point.color }}
    >
      <Icon className="size-3.5 text-white" strokeWidth={2.2} />
    </div>
  )
}

function ConsumerProxyMapMarker({ proxy }: { proxy: ConsumerProxyMarker }) {
  const style = consumerProxyStyleFor(proxy.reason)
  const Icon = style.icon
  const size = Math.max(16, Math.min(28, 14 + Math.sqrt(Math.max(proxy.weight, 1)) / 34))
  return (
    <div
      className="grid place-items-center rounded-[5px] border border-white shadow-[0_10px_30px_-14px_rgba(24,24,27,0.9)] ring-1 ring-zinc-950/20"
      style={{ width: size, height: size, backgroundColor: style.color }}
    >
      <Icon className="size-3.5 text-white" strokeWidth={2.25} />
    </div>
  )
}

function MapLegend({ mode }: { mode: Mode }) {
  if (mode !== "reconstructed") return null
  const entries = [
    ["#ca8a04", "Raw plant/generator candidate"],
    ["#111827", "Retained solver generator"],
    ["#2563eb", "Equivalent capacity source"],
    ["#15803d", "Branch retained in solver"],
    ["#71717a", "Branch dropped before solver"],
    ["#2563eb", "Synthetic/equivalent branch"],
  ]
  return (
    <div className="absolute right-[405px] top-3 z-[2] max-w-[270px] rounded-[6px] border border-zinc-300 bg-[#fbfbfa]/95 p-2 shadow-sm">
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500">Reconstructed legend</p>
      <div className="space-y-1">
        {entries.map(([color, label]) => (
          <div key={label} className="flex items-center gap-2 text-xs text-zinc-700">
            <span className="size-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="truncate">{label}</span>
          </div>
        ))}
      </div>
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

function DiagnosticsPanel({
  summary,
  assumptions,
  consumerProxies,
  mode,
}: {
  summary: PipelineSummary | null
  assumptions: AssumptionTransparency | null
  consumerProxies: ConsumerProxyMarker[]
  mode: Mode
}) {
  const counts = summary?.raw_osm_counts_by_power ?? {}
  const artifacts = summary?.handoff_artifacts ?? {}
  const voltageInference = metadataRecord(summary?.solver_metadata, "voltage_inference")
  const circuitClasses = metadataRecord(summary?.topology_metadata, "circuit_class_counts")
  const solverCircuitClasses = metadataRecord(summary?.solver_metadata, "solver_circuit_class_counts")
  const branchProvenance = metadataRecord(
    metadataRecord(summary?.solver_metadata, "provenance_summary"),
    "branch",
  )
  const solverCalibration = unknownRecord(summary?.solver_metadata.calibration)
  const validationCalibration = unknownRecord(summary?.validation.metrics.calibration)
  const sectorGwh = numericRecord(solverCalibration.sector_gwh)
  const inferredClpSectorGwh = numericRecord(solverCalibration.inferred_clp_sector_gwh)
  const endUseShares = numericRecord(solverCalibration.end_use_shares)
  const snapshotTotals = numericRecord(solverCalibration.snapshot_total_mw)
  const clpSnapshotTotals = numericRecord(solverCalibration.clp_snapshot_total_mw)
  const provenanceShares = numericRecord(unknownRecord(validationCalibration.load_provenance_class_share))
  const hkTerritory = unknownRecord(validationCalibration.hk_electric_territory)
  const officialTotal = unknownRecord(validationCalibration.official_total_source_energy)
  const hkTotalSource = unknownRecord(solverCalibration.hk_total_sector_source)
  const territoryValidation = unknownRecord(solverCalibration.territory_total_validation)
  const officialHongKongGwh = officialTotal.official_gwh ?? territoryValidation.emsd_total_gwh
  const loadAllocation = unknownRecord(summary?.topology_metadata.load_allocation_validation ?? summary?.solver_metadata.load_allocation_validation)
  const proxyCountBySector = numericRecord(loadAllocation.proxy_count_by_sector)
  const topLoadedBuses = Array.isArray(loadAllocation.top_buses_by_allocated_demand)
    ? loadAllocation.top_buses_by_allocated_demand.map(unknownRecord).slice(0, 5)
    : []
  const topLoadedSectors = Array.isArray(loadAllocation.top_sectors_by_allocated_demand)
    ? loadAllocation.top_sectors_by_allocated_demand.map(unknownRecord).slice(0, 5)
    : []
  const calibrationWarnings = Array.isArray(summary?.solver_metadata.calibration_warnings)
    ? summary.solver_metadata.calibration_warnings.filter((warning): warning is string => typeof warning === "string")
    : []
  const topologyDiagnostics = summary?.diagnostics
  const diagnosticSummary = topologyDiagnostics?.summary ?? {}
  const severeVoltageMismatches = (topologyDiagnostics?.voltage_mismatches ?? []).filter((item) => item.severe)
  const baseline = summary?.baseline_weak_spots
  const baselineSystem = baseline?.system_summary
  const reconciliation = summary?.asset_reconciliation
  const reconciliationSummary = reconciliation?.summary
  const linearStatusCounts = statusCounts(reconciliationSummary, "linear_status_counts")
  const generationStatusCounts = statusCounts(reconciliationSummary, "generation_status_counts")
  const lowConfidenceAssumptions = lowConfidenceAssumptionRows(assumptions)
  const dataCenterEstimates = consumerProxies
    .filter((proxy) => proxy.reason === "data_center" && proxy.data_center_load_estimate)
    .sort((left, right) => (right.data_center_load_estimate?.estimated_facility_mw ?? 0) - (left.data_center_load_estimate?.estimated_facility_mw ?? 0))
    .slice(0, 5)
  const generatorRows = assumptionRows(assumptions, "generator_cost_availability_defaults")
  const contingencyRows = assumptionRows(assumptions, "synthetic_contingency_library")
  const importRows = assumptionRows(assumptions, "cross_border_import_limits")
  const averageGeneratorAvailability = generatorRows.length
    ? generatorRows.reduce((sum, row) => sum + Number(row.availability_factor ?? 0), 0) / generatorRows.length
    : 0

  return (
    <aside className="absolute bottom-3 right-3 top-3 z-[2] flex w-[390px] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-[6px] border border-zinc-300 bg-[#fbfbfa]/95 shadow-[0_22px_70px_-42px_rgba(24,24,27,0.75)]">
      <div className="border-b border-zinc-200 p-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-zinc-950">Pipeline diagnostics</p>
            <p className="mt-0.5 text-xs text-zinc-500">Mode: {MODES.find((item) => item.id === mode)?.label}</p>
          </div>
          <Badge className={cn("rounded-[3px] border px-2 py-1", statusClass(summary?.validation.status))}>
            {statusLabel(summary?.validation.status)}
          </Badge>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-3">
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Stage status</h2>
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            {MODES.map((item) => {
              const Icon = item.icon
              const status = summary?.stage_status[item.stage]
              return (
                <div key={item.id} className={cn("rounded-[4px] border px-2 py-1.5", statusClass(status))}>
                  <div className="flex items-center gap-1.5">
                    <Icon className="size-3.5" />
                    <span className="truncate text-[11px] font-semibold">{item.label}</span>
                  </div>
                  <p className="mt-0.5 text-[11px]">{statusLabel(status)}</p>
                </div>
              )
            })}
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Core metrics</h2>
          <div className="mt-2 rounded-[4px] border border-zinc-200 bg-white/70 px-2">
            <MetadataRow label="Raw assets" value={Object.values(counts).reduce((sum, count) => sum + count, 0)} />
            <MetadataRow label="Raw lines/cables" value={reconciliationSummary?.raw_linear_count} />
            <MetadataRow label="Raw plant/generator" value={reconciliationSummary?.raw_generation_count} />
            <MetadataRow label="Preview buses" value={summary?.topology_metadata.bus_count} />
            <MetadataRow label="Preview branches" value={summary?.topology_metadata.branch_count} />
            <MetadataRow label="Preview generators" value={reconciliationSummary?.preview_generator_count} />
            <MetadataRow label="Solver buses" value={summary?.solver_metadata.bus_count} />
            <MetadataRow label="Solver branches" value={summary?.solver_metadata.branch_count} />
            <MetadataRow label="Loads" value={summary?.solver_metadata.load_count} />
            <MetadataRow label="Generators/imports" value={summary?.solver_metadata.gen_count} />
            <MetadataRow label="Total demand MW" value={metric(summary, "total_pd_mw")} />
            <MetadataRow label="Total Pmax MW" value={metric(summary, "total_pmax_mw")} />
            <MetadataRow label="Island count" value={metric(summary, "island_count")} />
            <MetadataRow label="Load components" value={metric(summary, "load_bearing_component_count")} />
            <MetadataRow label="Largest bus share" value={summary?.solver_metadata.largest_component_bus_share} />
            <MetadataRow label="Severe mismatches" value={metric(summary, "severe_branch_voltage_mismatch_count")} />
            <MetadataRow label="Dropped passive buses" value={summary?.solver_metadata.dropped_passive_bus_count} />
            <MetadataRow label="Dropped non-OPF branches" value={summary?.solver_metadata.dropped_non_interfacility_branch_count} />
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Assumption transparency</h2>
          <div className="mt-2 rounded-[4px] border border-zinc-200 bg-white/70 px-2">
            <MetadataRow label="Assumption status" value={assumptions?.summary.status ?? "not loaded"} />
            <MetadataRow label="Tables" value={assumptions?.summary.table_count} />
            <MetadataRow label="Rows" value={assumptions?.summary.row_count} />
            <MetadataRow label="Warnings" value={assumptions?.summary.warnings.length} />
            <MetadataRow label="Errors" value={assumptions?.summary.errors.length} />
            <MetadataRow label="Generator availability" value={averageGeneratorAvailability ? `${formatNumber(averageGeneratorAvailability * 100, 1)}% avg` : "n/a"} />
            <MetadataRow label="Contingency cases" value={contingencyRows.length} />
            <MetadataRow label="Import scenarios" value={importRows.length} />
          </div>
          <div className="mt-2 space-y-2">
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Observed, inferred, synthetic rows</p>
              <CountBadges counts={assumptions?.summary.provenance_counts ?? {}} />
            </div>
            {lowConfidenceAssumptions.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium text-zinc-500">Lowest-confidence assumptions</p>
                <div className="space-y-1.5">
                  {lowConfidenceAssumptions.map((item) => (
                    <div key={`${item.table}-${item.row.source}-${item.row.method}-${item.confidence}`} className="rounded-[4px] border border-zinc-200 bg-white/75 p-2">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 truncate text-[11px] font-semibold text-zinc-950">{item.table.replaceAll("_", " ")}</p>
                        <Badge variant="outline" className="shrink-0 rounded-[3px] border-zinc-300 bg-zinc-50 text-[10px]">
                          {formatNumber(item.confidence, 2)}
                        </Badge>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-600">{item.row.assumptions ?? item.row.method ?? "No assumption text"}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {dataCenterEstimates.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium text-zinc-500">Top assumed data-center loads</p>
                <div className="space-y-1.5">
                  {dataCenterEstimates.map((proxy) => (
                    <div key={proxy.id} className="rounded-[4px] border border-zinc-200 bg-white/75 p-2">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 truncate text-[11px] font-semibold text-zinc-950">{consumerProxyTitle(proxy)}</p>
                        <Badge variant="outline" className="shrink-0 rounded-[3px] border-blue-300 bg-blue-50 text-[10px] text-blue-900">
                          {formatNumber(proxy.data_center_load_estimate?.estimated_facility_mw, 1)} MW
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-zinc-600">
                        IT {formatNumber(proxy.data_center_load_estimate?.estimated_it_mw, 1)} MW, PUE {formatNumber(proxy.data_center_load_estimate?.pue, 2)}, {proxy.data_center_load_estimate?.provenance}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {generatorRows.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium text-zinc-500">Generator availability summary</p>
                <CountBadges counts={Object.fromEntries(generatorRows.slice(0, 6).map((row) => [String(row.energy_source), Math.round(Number(row.availability_factor ?? 0) * 100)]))} />
              </div>
            )}
            {importRows.length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium text-zinc-500">Import constraints</p>
                <div className="space-y-1.5">
                  {importRows.slice(0, 4).map((row) => (
                    <div key={row.boundary_id} className="rounded-[4px] border border-zinc-200 bg-white/75 p-2">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 truncate text-[11px] font-semibold text-zinc-950">{row.boundary_id?.replaceAll("_", " ")}</p>
                        <Badge variant="outline" className="shrink-0 rounded-[3px] border-zinc-300 bg-zinc-50 text-[10px]">
                          {formatNumber(Number(row.nominal_mw), 0)} MW
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs leading-5 text-zinc-600">Derates {row.derate_scenarios}, {row.provenance}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Baseline weak spots</h2>
          <div className="mt-2 rounded-[4px] border border-zinc-200 bg-white/70 px-2">
            <MetadataRow
              label="Reserve margin"
              value={typeof baselineSystem?.reserve_margin_estimate === "number" ? `${formatNumber(baselineSystem.reserve_margin_estimate * 100, 1)}%` : "n/a"}
            />
            <MetadataRow
              label="Synthetic dependency"
              value={typeof baselineSystem?.synthetic_branch_share === "number" ? `${formatNumber(baselineSystem.synthetic_branch_share * 100, 1)}%` : "n/a"}
            />
            <MetadataRow label="Promoted generators" value={baselineSystem?.promoted_generator_count} />
            <MetadataRow label="Inferred voltages" value={baselineSystem?.inferred_voltage_count} />
            <MetadataRow label="Study warnings" value={baselineSystem?.warning_count} />
          </div>
          <div className="mt-2 space-y-2">
            <BaselineRiskList title="Top weak branches" items={baselineSystem?.top_10_risky_branches ?? []} />
            <BaselineRiskList title="Top weak buses" items={baselineSystem?.top_10_risky_buses ?? []} />
            {(baselineSystem?.warnings.length ?? 0) > 0 && (
              <div className="rounded-[4px] border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs leading-5 text-amber-900">
                {baselineSystem?.warnings[0]}
              </div>
            )}
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Asset reconciliation</h2>
          <div className="mt-2 space-y-2">
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Line and cable status</p>
              <CountBadges counts={linearStatusCounts} />
            </div>
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Plant and generator status</p>
              <CountBadges counts={generationStatusCounts} />
            </div>
            <ReconciliationList title="Top generation candidates" items={reconciliation?.top_generation_assets ?? []} />
            <ReconciliationList title="Dropped or aggregated assets" items={reconciliation?.top_dropped_or_aggregated_assets ?? []} />
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Calibration</h2>
          <div className="mt-2 rounded-[4px] border border-zinc-200 bg-white/70 px-2">
            <MetadataRow label="HK Electric source" value={solverCalibration.source_year} />
            <MetadataRow label="Source periods" value={Array.isArray(solverCalibration.source_periods) ? solverCalibration.source_periods.join(", ") : "n/a"} />
            <MetadataRow label="Official HK GWh" value={officialHongKongGwh} />
            <MetadataRow label="Observed HKE GWh" value={solverCalibration.observed_hk_electric_total_gwh} />
            <MetadataRow label="Inferred CLP GWh" value={solverCalibration.inferred_clp_total_gwh} />
            <MetadataRow label="Modeled HKE GWh" value={hkTerritory.modeled_gwh} />
            <MetadataRow label="HKE total error %" value={hkTerritory.error_pct} />
            <MetadataRow label="Official total error %" value={officialTotal.error_pct} />
            <MetadataRow label="Cooling share" value={typeof endUseShares.air_conditioning === "number" ? `${formatNumber(endUseShares.air_conditioning * 100, 1)}%` : "n/a"} />
            <MetadataRow label="HKE snapshot MW" value={snapshotTotals[summary?.solver_metadata.demand_snapshot as string]} />
            <MetadataRow label="CLP snapshot MW" value={clpSnapshotTotals[summary?.solver_metadata.demand_snapshot as string]} />
            <MetadataRow label="HK total source" value={typeof hkTotalSource.source === "string" ? hkTotalSource.source : "n/a"} />
            <MetadataRow label="CLP method" value={solverCalibration.clp_inference_method} />
          </div>
          <div className="mt-2 space-y-2">
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Observed HK Electric sector energy (GWh)</p>
              <CountBadges counts={sectorGwh} />
            </div>
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Inferred CLP sector energy (GWh)</p>
              <CountBadges counts={inferredClpSectorGwh} />
            </div>
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Load provenance share</p>
              <div className="grid grid-cols-3 gap-1.5">
                {(["observed", "inferred", "synthetic"] as const).map((item) => (
                  <div key={item} className="rounded-[4px] border border-zinc-200 bg-white/70 p-2">
                    <div className="flex items-center gap-1.5">
                      <span className="size-2 rounded-full" style={{ backgroundColor: provenanceColor(item) }} />
                      <span className="text-[11px] font-medium capitalize text-zinc-600">{item}</span>
                    </div>
                    <p className="mt-1 text-sm font-semibold tabular-nums text-zinc-950">
                      {formatNumber((provenanceShares[item] ?? 0) * 100, 1)}%
                    </p>
                  </div>
                ))}
              </div>
            </div>
            {calibrationWarnings.length > 0 && (
              <div className="rounded-[4px] border border-blue-300 bg-blue-50 px-2 py-1.5 text-xs leading-5 text-blue-900">
                {calibrationWarnings[0]}
              </div>
            )}
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Proxy allocation</h2>
          <div className="mt-2 rounded-[4px] border border-zinc-200 bg-white/70 px-2">
            <MetadataRow label="Method" value={loadAllocation.method} />
            <MetadataRow label="Proxy share" value={typeof loadAllocation.proxy_allocation_share === "number" ? `${formatNumber(loadAllocation.proxy_allocation_share * 100, 1)}%` : "n/a"} />
            <MetadataRow label="Fallback share" value={typeof loadAllocation.fallback_allocation_share === "number" ? `${formatNumber(loadAllocation.fallback_allocation_share * 100, 1)}%` : "n/a"} />
            <MetadataRow label="Average distance km" value={loadAllocation.average_proxy_to_bus_distance_km} />
            <MetadataRow label="Median distance km" value={loadAllocation.median_proxy_to_bus_distance_km} />
          </div>
          <div className="mt-2">
            <p className="mb-1 text-[11px] font-medium text-zinc-500">Proxy count by sector</p>
            <CountBadges counts={proxyCountBySector} />
          </div>
          {topLoadedBuses.length > 0 && (
            <div className="mt-2">
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Top loaded buses</p>
              <CountBadges counts={Object.fromEntries(topLoadedBuses.map((item) => [String(item.bus_id ?? "unknown"), Number(item.pd_mw ?? 0)]))} />
            </div>
          )}
          {topLoadedSectors.length > 0 && (
            <div className="mt-2">
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Top loaded sectors</p>
              <CountBadges counts={Object.fromEntries(topLoadedSectors.map((item) => [String(item.sector ?? "unknown"), Number(item.pd_mw ?? 0)]))} />
            </div>
          )}
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Solver diagnostics</h2>
          <div className="mt-2 rounded-[4px] border border-zinc-200 bg-white/70 px-2">
            <MetadataRow label="Synthetic branches" value={diagnosticSummary.synthetic_branch_count} />
            <MetadataRow label="Synthetic share" value={typeof diagnosticSummary.synthetic_branch_share === "number" ? `${formatNumber(diagnosticSummary.synthetic_branch_share * 100, 1)}%` : "n/a"} />
            <MetadataRow label="Voltage mismatches" value={diagnosticSummary.voltage_mismatch_count} />
            <MetadataRow label="Severe mismatches" value={diagnosticSummary.severe_voltage_mismatch_count} />
            <MetadataRow label="Missing provenance" value={diagnosticSummary.missing_provenance_count} />
          </div>
          <div className="mt-2 space-y-2">
            <DiagnosticIssueList title="Top synthetic branches" items={topologyDiagnostics?.synthetic_branches ?? []} />
            <DiagnosticIssueList title="Top severe voltage mismatches" items={severeVoltageMismatches} />
            {(topologyDiagnostics?.recommended_next_fixes ?? []).length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-medium text-zinc-500">Recommended next fixes</p>
                <CountBadges counts={Object.fromEntries((topologyDiagnostics?.recommended_next_fixes ?? []).map((item) => [`${item.category}: ${item.recommended_action}`, item.count]))} />
              </div>
            )}
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Reconstruction</h2>
          <div className="mt-2 space-y-2">
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Voltage inference</p>
              <CountBadges counts={voltageInference} />
            </div>
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Preview circuit classes</p>
              <CountBadges counts={circuitClasses} />
            </div>
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Solver circuit classes</p>
              <CountBadges counts={solverCircuitClasses} />
            </div>
            <div>
              <p className="mb-1 text-[11px] font-medium text-zinc-500">Solver branch provenance</p>
              <CountBadges counts={branchProvenance} />
            </div>
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Raw OSM counts</h2>
          <div className="mt-2">
            <CountBadges counts={Object.fromEntries(Object.entries(counts).map(([power, count]) => [styleFor(power).label, count]))} />
          </div>
        </section>

        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-zinc-500">Handoff artifacts</h2>
          <div className="mt-2 rounded-[4px] border border-zinc-200 bg-zinc-950 p-2 font-mono text-[11px] leading-5 text-zinc-100">
            {Object.entries(artifacts).map(([key, value]) => (
              <div key={key} className="truncate">
                <span className="text-zinc-400">{key}</span> {value}
              </div>
            ))}
          </div>
        </section>
      </div>
    </aside>
  )
}

function RawPanel({
  asset,
  onClose,
}: {
  asset: GridAsset | null
  onClose: () => void
}) {
  if (!asset) return null
  const fields: Array<[string, string]> = [
    ["Voltage", asset.voltage ?? ""],
    ["Operator", asset.operator ?? ""],
    ["Frequency", asset.frequency ?? ""],
    ["Cables", asset.cables ?? ""],
    ["Circuits", asset.circuits ?? ""],
  ].filter((field): field is [string, string] => Boolean(field[1]))

  return (
    <aside className="absolute bottom-3 left-3 z-[3] max-h-[48dvh] w-[420px] max-w-[calc(100vw-1.5rem)] overflow-hidden rounded-[6px] border border-zinc-300 bg-white/96 shadow-[0_20px_80px_-40px_rgba(24,24,27,0.65)]">
      <div className="flex items-start justify-between gap-3 border-b border-zinc-200 p-3">
        <div>
          <p className="text-sm font-semibold text-zinc-950">{assetTitle(asset)}</p>
          <p className="font-mono text-[11px] text-zinc-500">
            {asset.osm_type}/{asset.osm_id}
          </p>
        </div>
        <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close raw JSON">
          <X className="size-4" />
        </Button>
      </div>
      <div className="overflow-auto p-3">
        <MarkerTip title="Selected raw OSM asset" rows={fields.length ? fields : [["Tags", "No descriptive tags"]]} />
        <pre className="mt-3 max-h-[26dvh] overflow-auto rounded-[4px] bg-zinc-950 p-3 font-mono text-[11px] leading-5 text-zinc-100">
          {JSON.stringify(asset, null, 2)}
        </pre>
      </div>
    </aside>
  )
}

type AnalyticsModelMode = "full_demo" | "transmission"

function AnalyticsHeader({
  loading,
  modelMode,
  onModeChange,
  onRefresh,
}: {
  loading: boolean
  modelMode: AnalyticsModelMode
  onModeChange: (mode: AnalyticsModelMode) => void
  onRefresh: () => void
}) {
  return (
    <header className="sticky top-0 z-10 border-b border-zinc-200 bg-[#e5e7e3]/95 px-4 py-3 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="rounded-[3px] bg-zinc-950 px-2 py-1 text-white">Tiangou analytics</Badge>
            <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white/75 px-2 py-1">
              polling {POLL_MS / 1000}s
            </Badge>
          </div>
          <p className="mt-1 text-xs text-zinc-600">KPIs, weak spots, provenance, demand, generation, network, and solver artifact status.</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Tabs value={modelMode} onValueChange={(value) => onModeChange(value as AnalyticsModelMode)}>
            <TabsList className="h-8 bg-white/75">
              <TabsTrigger value="full_demo">Full demo grid</TabsTrigger>
              <TabsTrigger value="transmission">Transmission</TabsTrigger>
            </TabsList>
          </Tabs>
          <Button asChild variant="outline" className="rounded-[4px] border-zinc-300 bg-white/92">
            <Link to="/">Map</Link>
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

export function AnalyticsPage() {
  const [analytics, setAnalytics] = useState<AnalyticsDashboardPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [modelMode, setModelMode] = useState<AnalyticsModelMode>("full_demo")
  const loadInFlight = useRef(false)
  const analyticsAbort = useRef<AbortController | null>(null)
  const query = useMemo(() => {
    const params = new URLSearchParams({
      region_key: "hong-kong",
      include_hk_interties: modelMode === "full_demo" ? "true" : "false",
      solver_include_policy: modelMode === "full_demo" ? "demo_full_osm" : "strict_transmission",
      include_synthetic_generator_connections: modelMode === "full_demo" ? "true" : "false",
    })
    if (modelMode === "transmission") {
      params.set("min_voltage_kv", "100")
    }
    return params.toString()
  }, [modelMode])

  const loadAnalytics = useCallback(async (showLoading = true) => {
    if (loadInFlight.current) analyticsAbort.current?.abort()
    loadInFlight.current = true
    const controller = new AbortController()
    analyticsAbort.current = controller
    if (showLoading) setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/grid/analytics-dashboard?${query}`, {
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`Analytics API returned ${response.status}`)
      setAnalytics(await response.json() as AnalyticsDashboardPayload)
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return
      setError(err instanceof Error ? err.message : "Could not load analytics data")
    } finally {
      if (analyticsAbort.current === controller) {
        loadInFlight.current = false
        analyticsAbort.current = null
        if (showLoading) setLoading(false)
      }
    }
  }, [query])

  useEffect(() => {
    void loadAnalytics()
    return () => analyticsAbort.current?.abort()
  }, [loadAnalytics])

  useEffect(() => {
    const id = window.setInterval(() => {
      void loadAnalytics(false)
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [loadAnalytics])

  return (
    <main className="min-h-[100dvh] bg-[#e5e7e3] text-zinc-950">
      <AnalyticsHeader loading={loading} modelMode={modelMode} onModeChange={setModelMode} onRefresh={() => void loadAnalytics()} />
      <div className="mx-auto max-w-7xl px-4 py-4">
        {error && (
          <div className="mb-3 rounded-[4px] border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <AnalyticsDashboardTabs analytics={analytics} />
      </div>
    </main>
  )
}

function App() {
  const [assets, setAssets] = useState<GridAsset[]>([])
  const [consumerProxies, setConsumerProxies] = useState<ConsumerProxyMarker[]>([])
  const [assumptions, setAssumptions] = useState<AssumptionTransparency | null>(null)
  const [showConsumerProxies, setShowConsumerProxies] = useState(true)
  const [topology, setTopology] = useState<TopologyPreview | null>(null)
  const [caseData, setCaseData] = useState<PowerModelsCase | null>(null)
  const [summary, setSummary] = useState<PipelineSummary | null>(null)
  const [mode, setMode] = useState<Mode>("raw")
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [ingesting, setIngesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const loadInFlight = useRef(false)
  const dashboardAbort = useRef<AbortController | null>(null)

  const query = "region_key=hong-kong&include_hk_interties=true&solver_include_policy=demo_full_osm&include_synthetic_generator_connections=true&asset_limit=5000"

  const loadDashboard = async (showLoading = true) => {
    if (loadInFlight.current) dashboardAbort.current?.abort()
    loadInFlight.current = true
    const controller = new AbortController()
    dashboardAbort.current = controller
    if (showLoading) setLoading(true)
    setError(null)
    try {
      const [
        response,
        consumerResponse,
        assumptionSummaryResponse,
        assumptionLinesResponse,
        assumptionTransformersResponse,
        assumptionDemandProfilesResponse,
        assumptionDataCentersResponse,
        assumptionGeneratorsResponse,
        assumptionContingenciesResponse,
        assumptionImportsResponse,
      ] = await Promise.all([
        fetch(`${API_BASE_URL}/grid/dashboard-snapshot?${query}`, {
          signal: controller.signal,
        }),
        fetch(`${API_BASE_URL}/grid/consumer-proxies/important?region_key=hong-kong&limit=${IMPORTANT_CONSUMER_LIMIT}`, {
          signal: controller.signal,
        }),
        fetch(`${API_BASE_URL}/assumptions/summary`, { signal: controller.signal }),
        fetch(`${API_BASE_URL}/assumptions/lines`, { signal: controller.signal }),
        fetch(`${API_BASE_URL}/assumptions/transformers`, { signal: controller.signal }),
        fetch(`${API_BASE_URL}/assumptions/demand-profiles`, { signal: controller.signal }),
        fetch(`${API_BASE_URL}/assumptions/data-centers`, { signal: controller.signal }),
        fetch(`${API_BASE_URL}/assumptions/generators`, { signal: controller.signal }),
        fetch(`${API_BASE_URL}/assumptions/contingencies`, { signal: controller.signal }),
        fetch(`${API_BASE_URL}/assumptions/imports`, { signal: controller.signal }),
      ])
      if (!response.ok) throw new Error(`API returned ${response.status}`)
      if (!consumerResponse.ok) throw new Error(`Consumer proxy API returned ${consumerResponse.status}`)
      const assumptionResponses = [
        assumptionSummaryResponse,
        assumptionLinesResponse,
        assumptionTransformersResponse,
        assumptionDemandProfilesResponse,
        assumptionDataCentersResponse,
        assumptionGeneratorsResponse,
        assumptionContingenciesResponse,
        assumptionImportsResponse,
      ]
      if (assumptionResponses.some((item) => !item.ok)) throw new Error("Assumption API returned an error")
      const snapshot = await response.json() as DashboardSnapshot
      const importantConsumerProxies = await consumerResponse.json() as ConsumerProxyMarker[]
      const assumptionSummary = await assumptionSummaryResponse.json() as AssumptionSummary
      const assumptionTableGroups = await Promise.all([
        assumptionLinesResponse.json() as Promise<AssumptionTable[]>,
        assumptionTransformersResponse.json() as Promise<AssumptionTable[]>,
        assumptionDemandProfilesResponse.json() as Promise<AssumptionTable[]>,
        assumptionDataCentersResponse.json() as Promise<AssumptionTable[]>,
        assumptionGeneratorsResponse.json() as Promise<AssumptionTable[]>,
        assumptionContingenciesResponse.json() as Promise<AssumptionTable[]>,
        assumptionImportsResponse.json() as Promise<AssumptionTable[]>,
      ])
      const assumptionTables = assumptionTableGroups.flat()
      setAssets(snapshot.assets)
      setConsumerProxies(importantConsumerProxies)
      setAssumptions({ summary: assumptionSummary, tables: assumptionTables })
      setTopology(snapshot.topology)
      setCaseData(snapshot.powermodels_case)
      setSummary(snapshot.summary)
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return
      setError(err instanceof Error ? err.message : "Could not load dashboard data")
    } finally {
      if (dashboardAbort.current === controller) {
        loadInFlight.current = false
        dashboardAbort.current = null
        if (showLoading) setLoading(false)
      }
    }
  }

  const ingestHongKong = async () => {
    setIngesting(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/ingest/hong-kong`, { method: "POST" })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail ?? `Ingest returned ${response.status}`)
      }
      await loadDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not ingest data")
    } finally {
      setIngesting(false)
    }
  }

  useEffect(() => {
    void loadDashboard()
    return () => dashboardAbort.current?.abort()
  }, [])

  useEffect(() => {
    const id = window.setInterval(() => {
      void loadDashboard(false)
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [])

  const assetsWithLocation = useMemo(
    () => assets.filter((asset) => asset.lat !== null && asset.lon !== null),
    [assets],
  )

  const busBySourceId = useMemo(() => {
    const map = new globalThis.Map<string, TopologyBus>()
    for (const bus of topology?.buses ?? []) map.set(bus.id, bus)
    return map
  }, [topology])

  const previewBranchById = useMemo(() => {
    const map = new globalThis.Map<string, TopologyBranch>()
    for (const branch of topology?.branches ?? []) map.set(branch.id, branch)
    return map
  }, [topology])

  const rawRouteBySourceId = useMemo(() => {
    const map = new globalThis.Map<string, [number, number][]>()
    for (const asset of assets) {
      if (isLinearAsset(asset)) map.set(assetSourceId(asset), routeCoordinates(asset))
    }
    return map
  }, [assets])

  const caseBusByNumber = useMemo(() => {
    const map = new globalThis.Map<number, PowerModelsBus>()
    for (const bus of Object.values(caseData?.bus ?? {})) map.set(bus.bus_i, bus)
    return map
  }, [caseData])

  const solverBranchSourceIds = useMemo(() => {
    return new Set(Object.values(caseData?.branch ?? {}).map((branch) => branch.source_id))
  }, [caseData])

  const voltageMismatchSourceIds = useMemo(() => {
    const ids = new Set<string>()
    for (const mismatch of summary?.validation.voltage_mismatches ?? []) {
      if (mismatch.source_id) ids.add(mismatch.source_id)
    }
    return ids
  }, [summary])

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

  const routeLayers = useMemo<RouteLayer[]>(() => {
    if (mode === "raw") {
      return assets.filter(isLinearAsset).map((asset) => ({
        id: assetKey(asset),
        label: assetTitle(asset),
        coordinates: routeCoordinates(asset),
        color: styleFor(asset.power).color,
        width: asset.power === "cable" ? 3 : 4,
        opacity: asset.power === "cable" ? 0.58 : 0.88,
        dashArray: asset.power === "cable" ? [2, 2] : undefined,
      }))
    }

    if (mode === "reconstructed") {
      return (topology?.branches ?? []).flatMap((branch) => {
        const coordinates = branchCoordinates(branch)
        if (coordinates.length < 2) return []
        const retainedInSolver = solverBranchSourceIds.has(branch.id)
        const style = reconstructedRouteStyle(branch, retainedInSolver)
        return [{
          id: branch.id,
          label: `${branch.name ?? branch.id} (${retainedInSolver ? "solver" : branch.circuit_class ?? "dropped"})`,
          coordinates,
          ...style,
        }]
      })
    }

    return Object.entries(caseData?.branch ?? {}).flatMap(([id, branch]) => {
      const coordinates = solverBranchCoordinates(branch)
      if (coordinates.length < 2) return []
      const mismatch = voltageMismatchSourceIds.has(branch.source_id)
      const synthetic = branch.provenance?.includes("public") || branch.provenance?.includes("synthetic") || branch.source_id.startsWith("synthetic:")
      const generatorConnection = branch.provenance === "synthetic_connection_to_nearest_substation"
      return [{
        id: `solver-${id}`,
        label: generatorConnection ? "Synthetic generator connection" : branch.source_id,
        coordinates,
        color: mode === "validation" && mismatch ? "#dc2626" : generatorConnection ? "#7c3aed" : synthetic ? "#2563eb" : "#15803d",
        width: mode === "validation" && mismatch ? 6 : 4,
        opacity: mode === "handoff" ? 0.45 : generatorConnection ? 0.72 : 0.9,
        dashArray: branch.transformer || synthetic ? [3, 2] as [number, number] : undefined,
      }]
    })
  }, [assets, caseData, mode, solverBranchSourceIds, topology, voltageMismatchSourceIds])

  const pointLayers = useMemo<PointLayer[]>(() => {
    if (mode === "raw") return []
    const points: PointLayer[] = []

    if (mode === "reconstructed") {
      for (const bus of topology?.buses ?? []) {
        if (bus.lat === null || bus.lon === null) continue
        points.push({
          id: `preview-bus-${bus.id}`,
          label: bus.name ?? bus.id,
          longitude: bus.lon,
          latitude: bus.lat,
          color: "#52525b",
          size: bus.provenance?.startsWith("synthetic") ? 8 : 10,
          icon: CircleDot,
          meta: [
            ["Layer", "Preview bus"],
            ["Voltage", bus.base_kv ? `${formatNumber(bus.base_kv, 1)} kV` : "n/a"],
            ["Power", styleFor(bus.power).label],
          ],
        })
      }

      for (const asset of assetsWithLocation.filter(isGenerationAsset)) {
        if (asset.lat === null || asset.lon === null) continue
        const outputTag = asset.tags["generator:output:electricity"] ?? asset.tags["plant:output:electricity"] ?? asset.tags["output:electricity"] ?? "n/a"
        points.push({
          id: `raw-generation-${assetKey(asset)}`,
          label: assetTitle(asset),
          longitude: asset.lon,
          latitude: asset.lat,
          color: asset.power === "plant" ? "#ca8a04" : "#eab308",
          size: asset.power === "plant" ? 22 : 18,
          icon: asset.power === "plant" ? Factory : Zap,
          meta: [
            ["Layer", "Raw generation candidate"],
            ["Type", styleFor(asset.power).label],
            ["Output", outputTag],
            ["Operator", asset.operator ?? "n/a"],
          ],
        })
      }
    }

    for (const [id, load] of Object.entries(caseData?.load ?? {})) {
      const bus = caseBusByNumber.get(load.load_bus)
      const coord = coordinateForBus(bus?.source_id)
      if (!coord) continue
      const pdMw = load.pd * 100
      points.push({
        id: `load-${id}`,
        label: `${load.service_territory ?? "unknown"} load`,
        longitude: coord[0],
        latitude: coord[1],
        color: provenanceColor(load.provenance),
        size: Math.max(12, Math.min(34, 10 + Math.sqrt(pdMw) / 2)),
        icon: CircleDot,
        meta: [
          ["MW", formatNumber(pdMw, 1)],
          ["Bus", String(load.load_bus)],
          ["Sector", load.sector ?? "aggregate"],
          ["District", load.district ?? "n/a"],
          ["Provenance", provenanceClass(load.provenance)],
          ["Source year", load.source_year ? String(load.source_year) : "n/a"],
        ],
      })
    }

    for (const [id, gen] of Object.entries(caseData?.gen ?? {})) {
      const bus = caseBusByNumber.get(gen.gen_bus)
      const coord = coordinateForBus(bus?.source_id)
      if (!coord) continue
      const pmaxMw = gen.pmax * 100
      const equivalent = gen.resource_type.includes("equivalent")
      points.push({
        id: `gen-${id}`,
        label: gen.name ?? (equivalent ? gen.resource_type : (gen.energy_source ? `${gen.energy_source} generator` : "OSM generator")),
        longitude: coord[0],
        latitude: coord[1],
        color: equivalent ? "#2563eb" : gen.provenance === "inferred_generator_connection" ? "#7c2d12" : "#111827",
        size: Math.max(16, Math.min(40, 12 + Math.sqrt(pmaxMw) / 2)),
        icon: equivalent ? Database : gen.energy_source === "wind" ? Zap : Factory,
        meta: [
          ["Layer", "Solver generator"],
          ["Name", gen.name ?? "n/a"],
          ["Pmax MW", formatNumber(pmaxMw, pmaxMw < 10 ? 2 : 1)],
          ["Source", gen.energy_source ?? "n/a"],
          ["Operator", gen.operator ?? "n/a"],
          ["Capacity tag", gen.capacity_tag ?? "n/a"],
          ["Capacity raw", gen.capacity_raw ?? "n/a"],
          ["Connection", gen.connection_method ?? "direct"],
          ["Provenance", gen.provenance ?? "n/a"],
          ["Provenance chain", gen.provenance_chain?.join(", ") ?? "n/a"],
          ["Confidence", gen.confidence === null || gen.confidence === undefined ? "n/a" : formatNumber(gen.confidence, 2)],
          ["Bus", String(gen.gen_bus)],
        ],
      })
    }
    return points
  }, [assetsWithLocation, caseBusByNumber, caseData, mode, topology])

  const visibleConsumerProxies = useMemo(
    () => showConsumerProxies ? consumerProxies.filter((proxy) => Number.isFinite(proxy.lat) && Number.isFinite(proxy.lon)) : [],
    [consumerProxies, showConsumerProxies],
  )

  const pointAssets = useMemo(
    () => assetsWithLocation.filter((asset) => !isLinearAsset(asset) && !isSupportAsset(asset)),
    [assetsWithLocation],
  )
  const solverPolicy = String(caseData?._metadata?.solver_include_policy ?? "demo_full_osm")
  const solverPolicyLabel = solverPolicy === "demo_full_osm" ? "Demo full OSM" : "Strict transmission"

  const selectedAsset = useMemo(
    () => assetsWithLocation.find((asset) => assetKey(asset) === selectedAssetId) ?? null,
    [assetsWithLocation, selectedAssetId],
  )

  return (
    <main className="h-[100dvh] overflow-hidden bg-[#e5e7e3] text-zinc-950">
      <div className="relative h-full">
        <Map
          center={selectedAsset?.lon && selectedAsset?.lat ? [selectedAsset.lon, selectedAsset.lat] : HONG_KONG_CENTER}
          zoom={selectedAsset ? 13 : 10}
          theme="light"
          loading={loading}
          className="h-full w-full"
        >
          <MapControls position="top-right" />
          {routeLayers.map((route) => (
            <MapRoute
              key={route.id}
              id={route.id}
              coordinates={route.coordinates}
              color={route.color}
              width={route.width}
              opacity={route.opacity}
              dashArray={route.dashArray}
            />
          ))}

          {mode === "raw" &&
            pointAssets.map((asset) => {
              if (asset.lat === null || asset.lon === null) return null
              const key = assetKey(asset)
              return (
                <MapMarker key={key} longitude={asset.lon} latitude={asset.lat} onClick={() => setSelectedAssetId(key)}>
                  <MarkerContent>
                    <RawMarker asset={asset} selected={selectedAssetId === key} />
                  </MarkerContent>
                  <MarkerTooltip>
                    <MarkerTip
                      title={assetTitle(asset)}
                      rows={[
                        ["Type", styleFor(asset.power).label],
                        ["Voltage", asset.voltage ?? "n/a"],
                        ["Operator", asset.operator ?? "n/a"],
                      ]}
                    />
                  </MarkerTooltip>
                </MapMarker>
              )
            })}

          {pointLayers.map((point) => (
              <MapMarker key={point.id} longitude={point.longitude} latitude={point.latitude}>
                <MarkerContent>
                  <PointMarker point={point} />
                </MarkerContent>
                <MarkerTooltip>
                  <MarkerTip title={point.label} rows={point.meta} />
                </MarkerTooltip>
              </MapMarker>
            ))}

          {visibleConsumerProxies.map((proxy) => {
            const style = consumerProxyStyleFor(proxy.reason)
            return (
              <MapMarker key={`consumer-${proxy.id}`} longitude={proxy.lon} latitude={proxy.lat}>
                <MarkerContent>
                  <ConsumerProxyMapMarker proxy={proxy} />
                </MarkerContent>
                <MarkerTooltip>
                  <MarkerTip
                    title={consumerProxyTitle(proxy)}
                    rows={[
                      ["Category", style.label],
                      ["Reason", proxy.reason.replaceAll("_", " ")],
                      ["Type", proxy.proxy_type.replaceAll("_", " ")],
                      ["Sector", proxy.sector.replaceAll("_", " ")],
                      ["Weight", formatNumber(proxy.weight, 1)],
                      ["Confidence", proxy.confidence === null ? "n/a" : formatNumber(proxy.confidence, 2)],
                    ]}
                  />
                </MarkerTooltip>
              </MapMarker>
            )
          })}
        </Map>

        <MapLegend mode={mode} />

        <header className="absolute left-3 top-3 z-[2] max-w-[calc(100vw-420px-2rem)] rounded-[6px] border border-zinc-300 bg-[#fbfbfa]/95 p-3 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="rounded-[3px] bg-zinc-950 px-2 py-1 text-white">Tiangou GridSFM dashboard</Badge>
            <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white/75 px-2 py-1">
              {formatNumber(routeLayers.length)} map lines
            </Badge>
            <Badge variant="outline" className="rounded-[3px] border-emerald-700/30 bg-emerald-50/90 px-2 py-1 text-emerald-900">
              Solver policy: {solverPolicyLabel}
            </Badge>
            {showConsumerProxies && (
              <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white/75 px-2 py-1">
                {formatNumber(visibleConsumerProxies.length)} consumers
              </Badge>
            )}
            <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white/75 px-2 py-1">
              polling {POLL_MS / 1000}s
            </Badge>
            <Button asChild size="sm" variant="outline" className="h-6 rounded-[4px] border-zinc-300 bg-white/85 px-2 text-xs">
              <Link to="/analytics">Analytics</Link>
            </Button>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {MODES.map((item) => {
              const Icon = item.icon
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setMode(item.id)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 text-xs font-medium transition active:scale-[0.98]",
                    mode === item.id
                      ? "border-zinc-950 bg-zinc-950 text-white"
                      : "border-zinc-300 bg-white/85 text-zinc-700 hover:bg-white",
                  )}
                >
                  <Icon className="size-3.5" />
                  {item.label}
                </button>
              )
            })}
            <button
              type="button"
              onClick={() => setShowConsumerProxies((value) => !value)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[4px] border px-2.5 py-1.5 text-xs font-medium transition active:scale-[0.98]",
                showConsumerProxies
                  ? "border-violet-800 bg-violet-800 text-white"
                  : "border-zinc-300 bg-white/85 text-zinc-700 hover:bg-white",
              )}
              aria-pressed={showConsumerProxies}
            >
              <Building2 className="size-3.5" />
              {showConsumerProxies ? `Consumers ${formatNumber(visibleConsumerProxies.length)}` : "Consumers"}
            </button>
          </div>
        </header>

        <div className="absolute bottom-3 left-3 z-[2] flex max-w-[calc(100vw-420px-2rem)] flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => void loadDashboard()}
            disabled={loading || ingesting}
            className="rounded-[4px] border-zinc-300 bg-white/92 shadow-sm"
          >
            <RotateCcw className={cn("size-4", loading && "animate-spin")} />
            Refresh
          </Button>
          <Button
            type="button"
            onClick={() => void ingestHongKong()}
            disabled={ingesting}
            className="rounded-[4px] bg-zinc-950 text-white shadow-sm hover:bg-zinc-800"
          >
            {ingesting ? <Loader2 className="size-4 animate-spin" /> : <Zap className="size-4" />}
            Ingest Hong Kong
          </Button>
          {error && (
            <div className="rounded-[4px] border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 shadow-sm">
              {error}
            </div>
          )}
        </div>

        {!loading && assets.length === 0 && (
          <div className="absolute left-1/2 top-1/2 z-[2] w-[360px] max-w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-[6px] border border-zinc-300 bg-white p-4 text-center shadow-lg">
            <h1 className="text-base font-semibold text-zinc-950">No ingested grid assets</h1>
            <p className="mt-2 text-sm leading-6 text-zinc-600">Run the Hong Kong ingest to populate the pipeline dashboard.</p>
            <Button type="button" onClick={() => void ingestHongKong()} disabled={ingesting} className="mt-4 rounded-[4px] bg-zinc-950 text-white hover:bg-zinc-800">
              {ingesting ? <Loader2 className="size-4 animate-spin" /> : <Zap className="size-4" />}
              Ingest now
            </Button>
          </div>
        )}

        <DiagnosticsPanel summary={summary} assumptions={assumptions} consumerProxies={consumerProxies} mode={mode} />
        <RawPanel asset={selectedAsset} onClose={() => setSelectedAssetId(null)} />
      </div>
    </main>
  )
}

export default App
