import React, { useMemo } from 'react'
import './HKMap.css'

/*
  Generation nodes — one per physical site in the HK grid.
  Positions approximate real HK geography in SVG 600×370.

  Backend source → node mapping
*/
const SOURCE_NODE_MAP = {
  'Lamma Power Station Unit 1': 'lamma',
  'Lamma Power Station Unit 2': 'lamma',
  'Castle Peak A':               'castle_peak',
  'Black Point CCGT 1':          'black_point',
  'Black Point CCGT 2':          'black_point',
  'Black Point CCGT 3':          'black_point',
  'Daya Bay Import':             'daya_bay',
  'HK Offshore Wind Alpha':      'offshore',
  'HK Offshore Wind Beta':       'offshore',
  'HK Solar Array':              'solar',
  'SC Unit 1':                   'sc',
  'HK Grid Battery Storage':     'bess',
}

const NODES = [
  { id: 'black_point',  label: 'Black Point\nCCGT',   x: 175, y:  82, type: 'gas'     },
  { id: 'castle_peak',  label: 'Castle Peak',          x:  55, y: 210, type: 'coal'    },
  { id: 'daya_bay',     label: 'Daya Bay\nImport',     x: 540, y:  55, type: 'nuclear' },
  { id: 'offshore',     label: 'Offshore Wind',        x: 340, y:  28, type: 'wind'    },
  { id: 'lamma',        label: 'Lamma PS',             x:  90, y: 310, type: 'coal'    },
  { id: 'solar',        label: 'HK Solar',             x: 370, y: 240, type: 'solar'   },
  { id: 'sc',           label: 'Stonecutters\nSC',     x: 245, y: 190, type: 'sc'      },
  { id: 'bess',         label: 'Grid Battery\nBESS',   x: 480, y: 160, type: 'bess'    },
]

const EDGES = [
  ['offshore',    'black_point'],
  ['daya_bay',    'black_point'],
  ['black_point', 'castle_peak'],
  ['castle_peak', 'sc'],
  ['sc',          'solar'],
  ['sc',          'lamma'],
  ['solar',       'daya_bay'],
  ['sc',          'bess'],
]

const TYPE_ICON = {
  gas: '⚡', coal: '⚡', nuclear: '⚛', wind: '🌬',
  solar: '☀', sc: '◎', bess: '🔋',
}

const HK_OUTLINE = `
  M 55 135 L 128 82 L 222 68 L 312 48 L 422 52 L 512 68 L 558 112 L 558 162
  L 512 182 L 492 232 L 472 262 L 432 292 L 372 312 L 312 332 L 252 337
  L 192 332 L 142 312 L 102 282 L 76 252 L 56 212 Z
`
const HK_ISLANDS = `
  M 145 295 L 172 284 L 198 292 L 193 322 L 162 327 Z
  M 258 332 L 308 327 L 338 337 L 328 357 L 268 352 Z
`

/* Default fallback data when activeSources not yet loaded */
const DEFAULT_CAPACITIES = {
  black_point: 1200, castle_peak: 600, daya_bay: 1200,
  offshore: 1400, lamma: 1400, solar: 500, sc: 0, bess: 200,
}

export default function HKMap({ side, freq = 50, activeSources = [] }) {
  const isAfter = side === 'after'
  const accent  = isAfter ? '#00e5a0' : '#e74c3c'
  const lineDim = isAfter ? 'rgba(0,229,160,0.35)' : 'rgba(231,76,60,0.35)'
  const bgFill  = isAfter ? 'rgba(0,229,160,0.10)' : 'rgba(231,76,60,0.10)'

  /* Aggregate backend sources into per-node totals */
  const nodes = useMemo(() => {
    const agg = {}
    NODES.forEach(n => { agg[n.id] = { cap: DEFAULT_CAPACITIES[n.id] || 0, out: 0, online: false } })

    if (activeSources.length > 0) {
      // reset capacities when we have real data
      NODES.forEach(n => { agg[n.id].cap = 0 })
      activeSources.forEach(src => {
        const nid = SOURCE_NODE_MAP[src.name]
        if (!nid) return
        agg[nid].cap    += src.capacity_mw      || 0
        agg[nid].out    += src.current_output_mw || 0
        agg[nid].online  = agg[nid].online || src.online
      })
    }

    return NODES.map(n => {
      const { cap, out, online } = agg[n.id]
      const loading = cap > 0 ? Math.min(100, Math.round((out / cap) * 100)) : 0
      return { ...n, capacity: cap, output: Math.round(out), loading, online: online || cap === 0 }
    })
  }, [activeSources])

  const glowId    = `glow-${side}`
  const nodeGlowId = `nglow-${side}`

  return (
    <div className="hkmap">
      <svg className="hkmap-svg" viewBox="0 0 600 370" preserveAspectRatio="xMidYMid meet">
        <defs>
          <filter id={glowId} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3" result="blur"/>
            <feComposite in="SourceGraphic" in2="blur" operator="over"/>
          </filter>
          <filter id={nodeGlowId} x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="6" result="blur"/>
            <feComposite in="SourceGraphic" in2="blur" operator="over"/>
          </filter>
          <radialGradient id={`bg-${side}`} cx="50%" cy="50%" r="60%">
            <stop offset="0%"   stopColor={isAfter ? '#081410' : '#140808'}/>
            <stop offset="100%" stopColor="#07090f"/>
          </radialGradient>
        </defs>

        {/* background */}
        <rect width="600" height="370" fill={`url(#bg-${side})`}/>

        {/* HK territory */}
        <path d={HK_OUTLINE} fill={bgFill} stroke={accent} strokeWidth="0.7" opacity="0.3"/>
        <path d={HK_ISLANDS} fill={bgFill} stroke={accent} strokeWidth="0.5" opacity="0.2"/>

        {/* subtle grid */}
        {[100,200,300].map(y => (
          <line key={y} x1="0" y1={y} x2="600" y2={y}
                stroke={accent} strokeWidth="0.3" opacity="0.07"/>
        ))}
        {[150,300,450].map(x => (
          <line key={x} x1={x} y1="0" x2={x} y2="370"
                stroke={accent} strokeWidth="0.3" opacity="0.07"/>
        ))}

        {/* ── transmission lines ── */}
        {EDGES.map(([a, b]) => {
          const na = nodes.find(n => n.id === a)
          const nb = nodes.find(n => n.id === b)
          if (!na || !nb) return null
          const active = na.output > 0 && nb.output > 0
          return (
            <g key={`${a}-${b}`}>
              <line x1={na.x} y1={na.y} x2={nb.x} y2={nb.y}
                    stroke={accent} strokeWidth="2" opacity="0.12"
                    filter={`url(#${glowId})`}/>
              <line x1={na.x} y1={na.y} x2={nb.x} y2={nb.y}
                    stroke={lineDim} strokeWidth="1.2"
                    strokeDasharray={active ? 'none' : '4 3'}/>
              {active && (
                <circle r="2.5" fill={accent} opacity="0.75">
                  <animateMotion
                    path={`M${na.x},${na.y} L${nb.x},${nb.y}`}
                    dur={`${2 + Math.abs(na.x - nb.x) / 200}s`}
                    repeatCount="indefinite"/>
                </circle>
              )}
            </g>
          )
        })}

        {/* ── nodes ── */}
        {nodes.map(node => {
          const isLow  = node.output === 0 && node.capacity > 0
          const nodeColor = isLow ? '#888' : accent
          return (
            <g key={node.id}>
              {/* outer ring — pulses when low output */}
              <circle cx={node.x} cy={node.y} r={20}
                      fill="none" stroke={nodeColor} strokeWidth="1" opacity={isLow ? 0.2 : 0.28}>
                {isLow && (
                  <animate attributeName="opacity" values="0.2;0.05;0.2"
                           dur="2s" repeatCount="indefinite"/>
                )}
              </circle>

              {/* inner circle */}
              <circle cx={node.x} cy={node.y} r={13}
                      fill={isLow
                        ? 'rgba(100,100,100,0.15)'
                        : isAfter ? 'rgba(0,229,160,0.15)' : 'rgba(231,76,60,0.2)'}
                      stroke={nodeColor} strokeWidth="1.6"
                      filter={`url(#${nodeGlowId})`}/>

              {/* icon */}
              <text x={node.x} y={node.y + 5}
                    textAnchor="middle" fontSize="12"
                    fill={nodeColor} opacity={isLow ? 0.4 : 0.9}>
                {TYPE_ICON[node.type] || '⚡'}
              </text>

              <NodeLabel node={node} accent={nodeColor} isLow={isLow}/>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/* Smart label placement — push away from nearest edge */
function NodeLabel({ node, accent, isLow }) {
  const { x, y, label, capacity, output, loading } = node
  const lines = label.split('\n')

  let lx = x, ly = y
  if      (x < 140)  lx = x + 52
  else if (x > 460)  lx = x - 52
  else if (y < 100)  ly = y + 48
  else if (y > 280)  ly = y - 44
  else               ly = y + 46

  const boxW = 110
  const lineH = 12
  const boxH  = 14 + lines.length * lineH + 26
  const bx = lx - boxW / 2
  const by = ly - 8

  const loadColor = loading >= 90 ? '#ff6b5b' : loading >= 70 ? '#f39c12' : accent
  const mwDisplay = capacity > 0 ? `${output} / ${capacity} MW` : '— MW'

  return (
    <g opacity={isLow ? 0.6 : 1}>
      <line x1={x} y1={y} x2={lx} y2={ly - 4}
            stroke={accent} strokeWidth="0.7" opacity="0.35" strokeDasharray="3 2"/>
      <rect x={bx} y={by} width={boxW} height={boxH}
            rx="5" fill="rgba(7,9,15,0.88)"
            stroke={accent} strokeWidth={loading >= 90 ? 1.2 : 0.6} opacity="0.95"/>
      {lines.map((line, i) => (
        <text key={i} x={lx} y={by + 13 + i * lineH}
              textAnchor="middle" fontSize="9" fontFamily="Inter,sans-serif"
              fontWeight="600" fill="#c8d4e0" letterSpacing="0.4">
          {line}
        </text>
      ))}
      <text x={lx} y={by + 13 + lines.length * lineH + 2}
            textAnchor="middle" fontSize="11"
            fontFamily="JetBrains Mono,monospace" fontWeight="700" fill="#e8edf5">
        {mwDisplay}
      </text>
      <text x={lx} y={by + 13 + lines.length * lineH + 16}
            textAnchor="middle" fontSize="12"
            fontFamily="JetBrains Mono,monospace" fontWeight="700" fill={loadColor}>
        {capacity > 0 ? `${loading}%` : 'offline'}
      </text>
    </g>
  )
}
