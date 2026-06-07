import React, { useMemo } from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import './HKMap.css'

const HK_CENTER = [22.38, 114.12]
const HK_ZOOM   = 11

const CARTO_TILES = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
const CARTO_ATTR  = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

// Three rows, each node separated by ≥0.14° lon so labels don't overlap
const NODES = [
  // Row 1 — lat 22.47, labels open downward
  { id: 'nuclear_almaraz', label: 'Black Pt SC',     pos: [22.47, 113.96], type: 'nuclear', dir: 'bottom' },
  { id: 'ccgt_besos',      label: 'Black Point',     pos: [22.47, 114.10], type: 'gas',     dir: 'bottom' },
  { id: 'france_link',     label: 'Daya Bay Import', pos: [22.47, 114.28], type: 'nuclear', dir: 'bottom' },
  // Row 2 — lat 22.37, labels open downward
  { id: 'ccgt_madrid',     label: 'Castle Peak',     pos: [22.37, 113.95], type: 'gas',     dir: 'bottom' },
  { id: 'bess',            label: 'Grid Battery',    pos: [22.37, 114.13], type: 'bess',    dir: 'bottom' },
  { id: 'solar_murcia',    label: 'HK Solar',        pos: [22.37, 114.30], type: 'solar',   dir: 'bottom' },
  // Row 3 — lat 22.27, labels open upward
  { id: 'solar_ext',       label: 'Lamma Station',   pos: [22.27, 114.04], type: 'solar',   dir: 'top'    },
  { id: 'wind_castilla',   label: 'Offshore Wind',   pos: [22.27, 114.26], type: 'wind',    dir: 'top'    },
]

const EDGES = [
  ['france_link',     'ccgt_besos'],
  ['france_link',     'ccgt_madrid'],
  ['wind_castilla',   'bess'],
  ['nuclear_almaraz', 'ccgt_madrid'],
  ['ccgt_madrid',     'ccgt_besos'],
  ['ccgt_madrid',     'bess'],
  ['solar_ext',       'bess'],
  ['solar_murcia',    'ccgt_besos'],
]

const SOURCE_NODE_MAP = {
  'Lamma Power Station Unit 1': 'solar_ext',
  'Lamma Power Station Unit 2': 'solar_ext',
  'Castle Peak A':               'ccgt_madrid',
  'Black Point CCGT 1':          'ccgt_besos',
  'Black Point CCGT 2':          'ccgt_besos',
  'Black Point CCGT 3':          'ccgt_besos',
  'Daya Bay Import':             'france_link',
  'HK Offshore Wind Alpha':      'wind_castilla',
  'HK Offshore Wind Beta':       'wind_castilla',
  'HK Solar Array':              'solar_murcia',
  'SC Unit 1':                   'nuclear_almaraz',
  'HK Grid Battery Storage':     'bess',
}

const DEFAULT_CAPACITY = {
  france_link: 1200, wind_castilla: 980, nuclear_almaraz: 2000,
  ccgt_madrid: 1200, ccgt_besos: 1200,  solar_ext: 700,
  solar_murcia: 500, bess: 200,
}

const TYPE_COLORS = {
  nuclear: '#a78bfa',
  wind:    '#38bdf8',
  gas:     '#fb923c',
  solar:   '#fbbf24',
  bess:    '#c084fc',
}

const EDGE_POSITIONS = EDGES.map(([aId, bId]) => {
  const na = NODES.find(n => n.id === aId)
  const nb = NODES.find(n => n.id === bId)
  return [na.pos, nb.pos]
})

export default function HKMap({ side, freq = 50, activeSources = [] }) {
  const isAfter = side === 'after'
  const accent  = isAfter ? '#00e5a0' : '#e74c3c'

  const nodeStates = useMemo(() => {
    const states = {}
    NODES.forEach(n => {
      states[n.id] = { output: DEFAULT_CAPACITY[n.id] ?? 0, capacity: DEFAULT_CAPACITY[n.id] ?? 0, online: true }
    })

    if (activeSources.length > 0) {
      NODES.forEach(n => { states[n.id] = { output: 0, capacity: DEFAULT_CAPACITY[n.id] ?? 0, online: false } })
      activeSources.forEach(src => {
        const nid = SOURCE_NODE_MAP[src.name]
        if (!nid) return
        states[nid].output   += src.current_output_mw || 0
        states[nid].capacity += src.capacity_mw || 0
        states[nid].online    = states[nid].online || src.online
      })
    }
    return states
  }, [activeSources])

  return (
    <div className="hkmap">
      <MapContainer
        center={HK_CENTER}
        zoom={HK_ZOOM}
        zoomControl={false}
        scrollWheelZoom={false}
        dragging={false}
        doubleClickZoom={false}
        keyboard={false}
        attributionControl={true}
        style={{ width: '100%', height: '100%' }}
      >
        <TileLayer url={CARTO_TILES} attribution={CARTO_ATTR} />

        {EDGE_POSITIONS.map((positions, i) => (
          <Polyline key={i} positions={positions} color={accent} weight={2} opacity={0.75} />
        ))}

        {NODES.map(node => {
          const { output, capacity, online } = nodeStates[node.id]
          const isActive = online || output > 0
          const loading  = capacity > 0 ? Math.min(100, Math.round((output / capacity) * 100)) : 0
          const fillColor = isActive ? (TYPE_COLORS[node.type] || accent) : '#555'
          const loadColor = loading >= 90 ? '#ff6b5b' : loading >= 70 ? '#f39c12' : accent

          return (
            <CircleMarker
              key={node.id}
              center={node.pos}
              radius={9}
              pathOptions={{
                color:       accent,
                fillColor,
                fillOpacity: isActive ? 0.88 : 0.3,
                weight:      isActive ? 2 : 1,
              }}
            >
              <Tooltip
                permanent
                direction={node.dir}
                offset={
                  node.dir === 'top'    ? [0, -10] :
                  node.dir === 'bottom' ? [0,  10] :
                  node.dir === 'left'   ? [-10, 0] :
                                         [10,  0]
                }
                className="node-tooltip"
              >
                <div className="node-tooltip-name">{node.label}</div>
                <div className="node-tooltip-mw">
                  {Math.round(output)} / {capacity} MW
                </div>
                <div className="node-tooltip-load" style={{ color: loadColor }}>
                  {capacity > 0 ? `${loading}%` : 'offline'}
                </div>
              </Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>
    </div>
  )
}
