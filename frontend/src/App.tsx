import { useEffect, useMemo, useState } from "react"
import {
  Cable,
  CircleDot,
  Factory,
  GitBranch,
  Loader2,
  RadioTower,
  RotateCcw,
  ServerCog,
  X,
  Zap,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Map,
  MapControls,
  MapMarker,
  MapRoute,
  MarkerContent,
  MarkerTooltip,
} from "@/components/ui/map"
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

type PowerStyle = {
  label: string
  color: string
  marker: string
  icon: typeof Zap
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000"

const HONG_KONG_CENTER: [number, number] = [114.1694, 22.3193]

const POWER_STYLES: Record<string, PowerStyle> = {
  plant: { label: "Plant", color: "#a16207", marker: "bg-amber-700", icon: Factory },
  generator: { label: "Generator", color: "#ca8a04", marker: "bg-yellow-600", icon: Zap },
  substation: { label: "Substation", color: "#b84336", marker: "bg-red-600", icon: ServerCog },
  sub_station: { label: "Substation", color: "#b84336", marker: "bg-red-600", icon: ServerCog },
  transformer: { label: "Transformer", color: "#2563eb", marker: "bg-blue-600", icon: GitBranch },
  line: { label: "Line", color: "#a8661f", marker: "bg-stone-700", icon: Cable },
  minor_line: { label: "Minor line", color: "#a8661f", marker: "bg-stone-600", icon: Cable },
  cable: { label: "Cable", color: "#7f6a62", marker: "bg-stone-500", icon: Cable },
  tower: { label: "Tower", color: "#30343b", marker: "bg-zinc-800", icon: RadioTower },
  pole: { label: "Pole", color: "#3f3f46", marker: "bg-zinc-700", icon: CircleDot },
}

const FALLBACK_STYLE: PowerStyle = {
  label: "Other",
  color: "#52525b",
  marker: "bg-zinc-700",
  icon: CircleDot,
}

const TOOLTIP_KEYS: Array<[keyof GridAsset, string]> = [
  ["voltage", "Voltage"],
  ["operator", "Operator"],
  ["frequency", "Frequency"],
  ["cables", "Cables"],
  ["circuits", "Circuits"],
  ["location", "Location"],
]

const IMPORTANT_TAGS = [
  "name",
  "name:en",
  "power",
  "substation",
  "generator:source",
  "generator:method",
  "voltage",
  "operator",
  "frequency",
  "cables",
  "circuits",
  "location",
  "ref",
]

function styleFor(power: string) {
  return POWER_STYLES[power] ?? FALLBACK_STYLE
}

function assetKey(asset: GridAsset) {
  return `${asset.osm_type}-${asset.osm_id}`
}

function assetTitle(asset: GridAsset) {
  return asset.name || asset.tags["name:en"] || `${styleFor(asset.power).label} ${asset.osm_id}`
}

function populatedFields(asset: GridAsset) {
  const baseFields = TOOLTIP_KEYS.flatMap(([key, label]) => {
    const value = asset[key]
    return value ? [{ label, value: String(value) }] : []
  })

  const tagFields = IMPORTANT_TAGS.flatMap((key) => {
    if (TOOLTIP_KEYS.some(([field]) => field === key)) return []
    const value = asset.tags[key]
    return value ? [{ label: key, value }] : []
  })

  return [...baseFields, ...tagFields]
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

function routeCoordinates(asset: GridAsset): [number, number][] {
  return (asset.geometry ?? []).map((point) => [point.lon, point.lat])
}

function MarkerDot({ asset, selected }: { asset: GridAsset; selected: boolean }) {
  const style = styleFor(asset.power)
  const Icon = style.icon
  const named = Boolean(asset.name || asset.tags["name:en"])
  const compact = asset.power === "tower" || asset.power === "pole"

  return (
    <div className="relative flex items-center gap-1.5">
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
      {named && !compact && (
        <span className="max-w-44 rounded-[2px] bg-white/88 px-1.5 py-0.5 text-[12px] font-medium leading-tight text-zinc-800 shadow-sm">
          {assetTitle(asset)}
        </span>
      )}
    </div>
  )
}

function AssetTooltip({ asset }: { asset: GridAsset }) {
  const fields = populatedFields(asset)
  const style = styleFor(asset.power)

  return (
    <div className="w-80 rounded-[3px] border border-zinc-300 bg-white/95 p-2.5 text-left shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold leading-snug text-zinc-950">
            {assetTitle(asset)}
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-zinc-500">
            {asset.osm_type}/{asset.osm_id}
          </p>
        </div>
        <span
          className="rounded-[2px] px-1.5 py-0.5 text-[11px] font-medium text-white"
          style={{ backgroundColor: style.color }}
        >
          {style.label}
        </span>
      </div>
      {fields.length > 0 ? (
        <dl className="mt-2 grid grid-cols-[88px_minmax(0,1fr)] gap-x-2 gap-y-1 text-xs">
          {fields.slice(0, 8).map((field) => (
            <div key={field.label} className="contents">
              <dt className="text-zinc-500">{field.label}</dt>
              <dd className="truncate font-medium text-zinc-900">{field.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-2 text-xs text-zinc-500">No descriptive tags in this API item.</p>
      )}
    </div>
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
  const fields = populatedFields(asset)

  return (
    <aside className="absolute bottom-4 right-4 top-4 z-[2] flex w-[420px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-[4px] border border-zinc-300 bg-white/96 shadow-[0_20px_80px_-40px_rgba(24,24,27,0.65)]">
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
      <div className="space-y-4 overflow-auto p-3">
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            Populated fields
          </h2>
          <dl className="mt-2 divide-y divide-zinc-100 rounded-[3px] border border-zinc-200">
            {fields.length > 0 ? (
              fields.map((field) => (
                <div key={field.label} className="grid grid-cols-[120px_minmax(0,1fr)] gap-2 px-2 py-1.5 text-xs">
                  <dt className="text-zinc-500">{field.label}</dt>
                  <dd className="break-words font-medium text-zinc-900">{field.value}</dd>
                </div>
              ))
            ) : (
              <div className="px-2 py-2 text-xs text-zinc-500">No populated fields beyond ids and type.</div>
            )}
          </dl>
        </section>
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            Raw API JSON
          </h2>
          <pre className="mt-2 max-h-[48dvh] overflow-auto rounded-[3px] bg-zinc-950 p-3 font-mono text-[11px] leading-5 text-zinc-100">
            {JSON.stringify(asset, null, 2)}
          </pre>
        </section>
      </div>
    </aside>
  )
}

function App() {
  const [assets, setAssets] = useState<GridAsset[]>([])
  const [selectedPower, setSelectedPower] = useState("all")
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
      if (!response.ok) throw new Error(`API returned ${response.status}`)
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

  const linearAssets = useMemo(
    () => filteredAssets.filter(isLinearAsset),
    [filteredAssets],
  )

  const pointAssets = useMemo(
    () => filteredAssets.filter((asset) => !isLinearAsset(asset)),
    [filteredAssets],
  )

  const selectedAsset = useMemo(
    () => assetsWithLocation.find((asset) => assetKey(asset) === selectedAssetId) ?? null,
    [assetsWithLocation, selectedAssetId],
  )

  return (
    <main className="h-[100dvh] overflow-hidden bg-[#d9dee1] text-zinc-950">
      <div className="relative h-full">
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
          {linearAssets.map((asset) => (
            <MapRoute
              key={assetKey(asset)}
              id={assetKey(asset)}
              coordinates={routeCoordinates(asset)}
              color={styleFor(asset.power).color}
              width={asset.power === "cable" ? 3 : 4}
              opacity={asset.power === "cable" ? 0.55 : 0.88}
              dashArray={asset.power === "cable" ? [2, 2] : undefined}
              onClick={() => setSelectedAssetId(assetKey(asset))}
            />
          ))}
          {pointAssets.map((asset) => {
            if (asset.lat === null || asset.lon === null) return null
            const key = assetKey(asset)
            return (
              <MapMarker
                key={key}
                longitude={asset.lon}
                latitude={asset.lat}
                onClick={() => setSelectedAssetId(key)}
              >
                <MarkerContent>
                  <MarkerDot asset={asset} selected={selectedAssetId === key} />
                </MarkerContent>
                <MarkerTooltip>
                  <AssetTooltip asset={asset} />
                </MarkerTooltip>
              </MapMarker>
            )
          })}
        </Map>

        <header className="absolute left-3 top-3 z-[2] max-w-[calc(100vw-1.5rem)] rounded-[4px] border border-zinc-300 bg-white/92 p-3 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="rounded-[3px] bg-zinc-950 px-2 py-1 text-white">
              Tiangou OSM power layer
            </Badge>
            <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white/80 px-2 py-1">
              {filteredAssets.length} visible
            </Badge>
            <Badge variant="outline" className="rounded-[3px] border-zinc-300 bg-white/80 px-2 py-1">
              {linearAssets.length} lines
            </Badge>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setSelectedPower("all")}
              className={cn(
                "rounded-[3px] border px-2 py-1 text-xs transition active:scale-[0.98]",
                selectedPower === "all"
                  ? "border-zinc-950 bg-zinc-950 text-white"
                  : "border-zinc-300 bg-white/85 text-zinc-700 hover:bg-white",
              )}
            >
              All {assetsWithLocation.length}
            </button>
            {powerCounts.map(([power, count]) => (
              <button
                key={power}
                type="button"
                onClick={() => setSelectedPower(power)}
                className={cn(
                  "rounded-[3px] border px-2 py-1 text-xs transition active:scale-[0.98]",
                  selectedPower === power
                    ? "border-zinc-950 bg-zinc-950 text-white"
                    : "border-zinc-300 bg-white/85 text-zinc-700 hover:bg-white",
                )}
              >
                {styleFor(power).label} {count}
              </button>
            ))}
          </div>
        </header>

        <div className="absolute bottom-3 left-3 z-[2] flex max-w-[calc(100vw-1.5rem)] flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => void loadAssets()}
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

        {!loading && filteredAssets.length === 0 && (
          <div className="absolute left-1/2 top-1/2 z-[2] w-[360px] max-w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-[4px] border border-zinc-300 bg-white p-4 text-center shadow-lg">
            <h1 className="text-base font-semibold text-zinc-950">No mapped OSM power data</h1>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              Run the Hong Kong ingest to populate this development layer.
            </p>
            <Button
              type="button"
              onClick={() => void ingestHongKong()}
              disabled={ingesting}
              className="mt-4 rounded-[4px] bg-zinc-950 text-white hover:bg-zinc-800"
            >
              {ingesting ? <Loader2 className="size-4 animate-spin" /> : <Zap className="size-4" />}
              Ingest now
            </Button>
          </div>
        )}

        <RawPanel asset={selectedAsset} onClose={() => setSelectedAssetId(null)} />
      </div>
    </main>
  )
}

export default App
