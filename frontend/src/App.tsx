import { useEffect, useMemo, useState } from "react"
import {
  Cable,
  CircleDot,
  Factory,
  GitBranch,
  Loader2,
  MapPin,
  RadioTower,
  RotateCcw,
  Search,
  ServerCog,
  Zap,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Map,
  MapControls,
  MapMarker,
  MarkerContent,
  MarkerTooltip,
} from "@/components/ui/map"
import { cn } from "@/lib/utils"

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
  updated_at: string
}

type PowerStyle = {
  label: string
  color: string
  bg: string
  icon: typeof Zap
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000"

const POWER_STYLES: Record<string, PowerStyle> = {
  plant: {
    label: "Plant",
    color: "#b45309",
    bg: "bg-amber-600",
    icon: Factory,
  },
  generator: {
    label: "Generator",
    color: "#ca8a04",
    bg: "bg-yellow-600",
    icon: Zap,
  },
  substation: {
    label: "Substation",
    color: "#2563eb",
    bg: "bg-blue-600",
    icon: ServerCog,
  },
  sub_station: {
    label: "Substation",
    color: "#2563eb",
    bg: "bg-blue-600",
    icon: ServerCog,
  },
  transformer: {
    label: "Transformer",
    color: "#0891b2",
    bg: "bg-cyan-600",
    icon: GitBranch,
  },
  line: {
    label: "Line",
    color: "#16a34a",
    bg: "bg-green-600",
    icon: Cable,
  },
  minor_line: {
    label: "Minor line",
    color: "#65a30d",
    bg: "bg-lime-600",
    icon: Cable,
  },
  cable: {
    label: "Cable",
    color: "#0d9488",
    bg: "bg-teal-600",
    icon: Cable,
  },
  tower: {
    label: "Tower",
    color: "#52525b",
    bg: "bg-zinc-600",
    icon: RadioTower,
  },
  pole: {
    label: "Pole",
    color: "#71717a",
    bg: "bg-zinc-500",
    icon: MapPin,
  },
}

const FALLBACK_STYLE: PowerStyle = {
  label: "Other",
  color: "#475569",
  bg: "bg-slate-600",
  icon: CircleDot,
}

const HONG_KONG_CENTER: [number, number] = [114.1694, 22.3193]

function styleFor(power: string) {
  return POWER_STYLES[power] ?? FALLBACK_STYLE
}

function formatValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "Unknown"
  return value
}

function assetTitle(asset: GridAsset) {
  return asset.name || `${styleFor(asset.power).label} ${asset.osm_type}/${asset.osm_id}`
}

function MarkerIcon({ asset, selected }: { asset: GridAsset; selected: boolean }) {
  const style = styleFor(asset.power)
  const Icon = style.icon

  return (
    <div
      className={cn(
        "group relative grid size-9 place-items-center rounded-full border border-white/80 shadow-[0_10px_24px_-12px_rgba(0,0,0,0.55)] transition duration-200 active:scale-95",
        style.bg,
        selected && "scale-110 ring-4 ring-zinc-950/20",
      )}
    >
      <Icon className="size-4 text-white" strokeWidth={2} />
      <span className="absolute inset-0 rounded-full border border-white/40" />
    </div>
  )
}

function AssetTooltip({ asset }: { asset: GridAsset }) {
  const style = styleFor(asset.power)

  return (
    <div className="w-72 rounded-md border border-zinc-200 bg-white p-3 text-left shadow-[0_18px_60px_-28px_rgba(24,24,27,0.55)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold leading-snug text-zinc-950">
            {assetTitle(asset)}
          </p>
          <p className="mt-1 font-mono text-[11px] text-zinc-500">
            {asset.osm_type}/{asset.osm_id}
          </p>
        </div>
        <span
          className="rounded-full px-2 py-1 text-[11px] font-medium text-white"
          style={{ backgroundColor: style.color }}
        >
          {style.label}
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
        <dt className="text-zinc-500">Voltage</dt>
        <dd className="text-right font-medium text-zinc-900">
          {formatValue(asset.voltage)}
        </dd>
        <dt className="text-zinc-500">Operator</dt>
        <dd className="text-right font-medium text-zinc-900">
          {formatValue(asset.operator)}
        </dd>
        <dt className="text-zinc-500">Frequency</dt>
        <dd className="text-right font-medium text-zinc-900">
          {formatValue(asset.frequency)}
        </dd>
        <dt className="text-zinc-500">Circuits</dt>
        <dd className="text-right font-medium text-zinc-900">
          {formatValue(asset.circuits)}
        </dd>
      </dl>
    </div>
  )
}

function App() {
  const [assets, setAssets] = useState<GridAsset[]>([])
  const [selectedPower, setSelectedPower] = useState<string>("all")
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [ingesting, setIngesting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadAssets = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(
        `${API_BASE_URL}/grid/assets?region_key=hong-kong&limit=1000`,
      )
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`)
      }
      setAssets(await response.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load assets")
    } finally {
      setLoading(false)
    }
  }

  const ingestHongKong = async () => {
    setIngesting(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/ingest/hong-kong`, {
        method: "POST",
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail ?? `Ingest returned ${response.status}`)
      }
      await loadAssets()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not ingest data")
    } finally {
      setIngesting(false)
    }
  }

  useEffect(() => {
    void loadAssets()
  }, [])

  const assetsWithLocation = useMemo(
    () => assets.filter((asset) => asset.lat !== null && asset.lon !== null),
    [assets],
  )

  const powerCounts = useMemo(() => {
    const counts = new globalThis.Map<string, number>()
    for (const asset of assetsWithLocation) {
      counts.set(asset.power, (counts.get(asset.power) ?? 0) + 1)
    }
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1])
  }, [assetsWithLocation])

  const filteredAssets = useMemo(
    () =>
      selectedPower === "all"
        ? assetsWithLocation
        : assetsWithLocation.filter((asset) => asset.power === selectedPower),
    [assetsWithLocation, selectedPower],
  )

  const selectedAsset = useMemo(
    () =>
      assetsWithLocation.find(
        (asset) => `${asset.osm_type}-${asset.osm_id}` === selectedAssetId,
      ) ?? null,
    [assetsWithLocation, selectedAssetId],
  )

  const namedAssets = useMemo(
    () => filteredAssets.filter((asset) => asset.name).slice(0, 8),
    [filteredAssets],
  )

  return (
    <main className="min-h-[100dvh] bg-zinc-100 text-zinc-950">
      <div className="grid min-h-[100dvh] grid-cols-1 lg:grid-cols-[390px_minmax(0,1fr)]">
        <aside className="order-2 border-t border-zinc-200 bg-white/92 p-4 lg:order-1 lg:border-r lg:border-t-0 lg:p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.16em] text-zinc-500">
                Tiangou grid model
              </p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950">
                Hong Kong power assets
              </h1>
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => void loadAssets()}
              disabled={loading || ingesting}
              aria-label="Refresh assets"
              className="shrink-0"
            >
              <RotateCcw className={cn("size-4", loading && "animate-spin")} />
            </Button>
          </div>

          <div className="mt-5 grid grid-cols-3 gap-2">
            <Card className="rounded-md border-zinc-200 shadow-none">
              <CardHeader className="px-3 pb-1 pt-3">
                <CardTitle className="text-xs font-medium text-zinc-500">
                  Stored
                </CardTitle>
              </CardHeader>
              <CardContent className="px-3 pb-3 font-mono text-xl font-semibold">
                {assets.length}
              </CardContent>
            </Card>
            <Card className="rounded-md border-zinc-200 shadow-none">
              <CardHeader className="px-3 pb-1 pt-3">
                <CardTitle className="text-xs font-medium text-zinc-500">
                  Mapped
                </CardTitle>
              </CardHeader>
              <CardContent className="px-3 pb-3 font-mono text-xl font-semibold">
                {assetsWithLocation.length}
              </CardContent>
            </Card>
            <Card className="rounded-md border-zinc-200 shadow-none">
              <CardHeader className="px-3 pb-1 pt-3">
                <CardTitle className="text-xs font-medium text-zinc-500">
                  Types
                </CardTitle>
              </CardHeader>
              <CardContent className="px-3 pb-3 font-mono text-xl font-semibold">
                {powerCounts.length}
              </CardContent>
            </Card>
          </div>

          <div className="mt-5 flex gap-2">
            <Button
              type="button"
              onClick={() => void ingestHongKong()}
              disabled={ingesting}
              className="flex-1 bg-zinc-950 text-white hover:bg-zinc-800"
            >
              {ingesting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Zap className="size-4" />
              )}
              Ingest Hong Kong
            </Button>
          </div>

          {error && (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <section className="mt-6">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-zinc-700">
              <Search className="size-4" />
              Asset filters
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setSelectedPower("all")}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-sm transition active:scale-[0.98]",
                  selectedPower === "all"
                    ? "border-zinc-950 bg-zinc-950 text-white"
                    : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-400",
                )}
              >
                All {assetsWithLocation.length}
              </button>
              {powerCounts.map(([power, count]) => {
                const style = styleFor(power)
                const Icon = style.icon
                return (
                  <button
                    key={power}
                    type="button"
                    onClick={() => setSelectedPower(power)}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition active:scale-[0.98]",
                      selectedPower === power
                        ? "border-zinc-950 bg-zinc-950 text-white"
                        : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-400",
                    )}
                  >
                    <Icon className="size-3.5" />
                    {style.label} {count}
                  </button>
                )
              })}
            </div>
          </section>

          <section className="mt-6">
            <h2 className="text-sm font-medium text-zinc-700">Visible sample</h2>
            <div className="mt-3 divide-y divide-zinc-100 rounded-md border border-zinc-200 bg-white">
              {loading ? (
                Array.from({ length: 5 }).map((_, index) => (
                  <div key={index} className="flex items-center gap-3 p-3">
                    <div className="size-8 animate-pulse rounded-full bg-zinc-200" />
                    <div className="flex-1 space-y-2">
                      <div className="h-3 w-2/3 animate-pulse rounded bg-zinc-200" />
                      <div className="h-2 w-1/3 animate-pulse rounded bg-zinc-100" />
                    </div>
                  </div>
                ))
              ) : namedAssets.length > 0 ? (
                namedAssets.map((asset) => {
                  const style = styleFor(asset.power)
                  const Icon = style.icon
                  return (
                    <button
                      key={`${asset.osm_type}-${asset.osm_id}`}
                      type="button"
                      onClick={() =>
                        setSelectedAssetId(`${asset.osm_type}-${asset.osm_id}`)
                      }
                      className="flex w-full items-center gap-3 p-3 text-left transition hover:bg-zinc-50 active:bg-zinc-100"
                    >
                      <span
                        className={cn(
                          "grid size-8 place-items-center rounded-full text-white",
                          style.bg,
                        )}
                      >
                        <Icon className="size-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-zinc-900">
                          {assetTitle(asset)}
                        </span>
                        <span className="block font-mono text-xs text-zinc-500">
                          {asset.power} · {formatValue(asset.voltage)}
                        </span>
                      </span>
                    </button>
                  )
                })
              ) : (
                <div className="p-4 text-sm text-zinc-500">
                  No named assets for this filter yet.
                </div>
              )}
            </div>
          </section>
        </aside>

        <section className="order-1 min-h-[68dvh] p-3 lg:order-2 lg:min-h-[100dvh] lg:p-4">
          <div className="relative h-[68dvh] overflow-hidden rounded-md border border-zinc-200 bg-zinc-200 shadow-[0_22px_80px_-48px_rgba(24,24,27,0.6)] lg:h-[calc(100dvh-2rem)]">
            <Map
              center={
                selectedAsset?.lon && selectedAsset?.lat
                  ? [selectedAsset.lon, selectedAsset.lat]
                  : HONG_KONG_CENTER
              }
              zoom={selectedAsset ? 13 : 10}
              theme="light"
              loading={loading}
              className="h-full w-full"
            >
              <MapControls position="top-right" />
              {filteredAssets.map((asset) => {
                if (asset.lat === null || asset.lon === null) return null
                const markerId = `${asset.osm_type}-${asset.osm_id}`
                return (
                  <MapMarker
                    key={markerId}
                    longitude={asset.lon}
                    latitude={asset.lat}
                    onClick={() => setSelectedAssetId(markerId)}
                  >
                    <MarkerContent>
                      <MarkerIcon
                        asset={asset}
                        selected={selectedAssetId === markerId}
                      />
                    </MarkerContent>
                    <MarkerTooltip>
                      <AssetTooltip asset={asset} />
                    </MarkerTooltip>
                  </MapMarker>
                )
              })}
            </Map>

            <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-2">
              <Badge className="rounded-full bg-white/95 px-3 py-1 text-zinc-800 shadow-sm">
                {filteredAssets.length} visible
              </Badge>
              <Badge
                variant="outline"
                className="rounded-full border-zinc-200 bg-white/95 px-3 py-1 text-zinc-600 shadow-sm"
              >
                OSM power layer
              </Badge>
            </div>

            {!loading && filteredAssets.length === 0 && (
              <div className="absolute inset-x-4 top-1/2 mx-auto max-w-md -translate-y-1/2 rounded-md border border-zinc-200 bg-white p-5 text-center shadow-xl">
                <h2 className="text-lg font-semibold text-zinc-950">
                  No mapped assets yet
                </h2>
                <p className="mt-2 text-sm leading-6 text-zinc-600">
                  Ingest Hong Kong from OpenStreetMap, then this map will show
                  substations, lines, cables, towers, generators, and related
                  power infrastructure.
                </p>
                <Button
                  type="button"
                  onClick={() => void ingestHongKong()}
                  disabled={ingesting}
                  className="mt-4 bg-zinc-950 text-white hover:bg-zinc-800"
                >
                  {ingesting ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Zap className="size-4" />
                  )}
                  Ingest now
                </Button>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}

export default App
