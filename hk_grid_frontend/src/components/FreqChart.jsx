import React, { useMemo } from 'react'
import './FreqChart.css'

const W = 520
const H = 90
const PAD = { top: 6, right: 10, bottom: 22, left: 42 }
const CHART_W = W - PAD.left - PAD.right
const CHART_H = H - PAD.top - PAD.bottom

const F_MAX          = 51.0
const F_MIN_NORMAL   = 47.5   // normal view floor
const F_MIN_COLLAPSE = 0.0    // collapse view floor — shows full 0-51 Hz

function formatT(t) {
  if (t < 60) return `${t}s`
  return `${Math.floor(t / 60)}m${(t % 60).toString().padStart(2, '0')}s`
}

export default function FreqChart({ freqHistory = [], timeHistory = [], side }) {
  const isAfter  = side === 'after'
  const color    = isAfter ? '#00e5a0' : '#e74c3c'
  const fillStop = isAfter ? 'rgba(0,229,160,0.18)' : 'rgba(231,76,60,0.18)'

  const totalDur  = timeHistory.length > 0 ? timeHistory[timeHistory.length - 1] : 1
  const currentF  = freqHistory[freqHistory.length - 1] ?? 50

  // Switch to full 0-51 Hz range once frequency falls below normal chart floor
  const collapseMode = !isAfter && currentF < F_MIN_NORMAL
  const F_MIN   = collapseMode ? F_MIN_COLLAPSE : F_MIN_NORMAL
  const F_RANGE = F_MAX - F_MIN

  // fy must be a closure so it picks up the dynamic F_MIN / F_RANGE
  function fy(f) {
    return PAD.top + CHART_H * (1 - (f - F_MIN) / F_RANGE)
  }

  const points = useMemo(() => {
    if (!freqHistory.length) return ''
    return freqHistory.map((f, i) => {
      const t   = timeHistory[i] ?? i
      const px  = PAD.left + (t / Math.max(totalDur, 1)) * CHART_W
      const py  = fy(f)
      return `${px},${py}`
    }).join(' ')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [freqHistory, timeHistory, totalDur, collapseMode])

  const areaPoints = (!collapseMode && points)
    ? `${PAD.left},${fy(F_MIN)} ${points} ${PAD.left + CHART_W * (timeHistory[timeHistory.length - 1] ?? 0) / Math.max(totalDur, 1)},${fy(F_MIN)}`
    : ''

  // Y-axis ticks
  const yTicks = collapseMode
    ? [0, 20, 40, 50.0]
    : [47.5, 48.5, 49.0, 50.0, 51.0]

  // Blackout countdown — only in normal mode while frequency is still on chart
  const showBlackout = !isAfter && !collapseMode && currentF < 49.0 && currentF >= F_MIN_NORMAL

  return (
    <div className="freq-chart">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="freq-chart-svg">
        <defs>
          <linearGradient id={`fill-${side}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={color} stopOpacity="0.25"/>
            <stop offset="100%" stopColor={color} stopOpacity="0"/>
          </linearGradient>
          <clipPath id={`clip-${side}`}>
            <rect x={PAD.left} y={PAD.top} width={CHART_W} height={CHART_H}/>
          </clipPath>
        </defs>

        {/* safety bands — normal mode only */}
        {!collapseMode && <>
          <rect x={PAD.left} y={fy(51)}   width={CHART_W} height={fy(50.2) - fy(51)}   fill="rgba(0,229,160,0.04)"/>
          <rect x={PAD.left} y={fy(50.2)} width={CHART_W} height={fy(49.8) - fy(50.2)} fill="rgba(0,229,160,0.07)"/>
          <rect x={PAD.left} y={fy(49.8)} width={CHART_W} height={fy(49.5) - fy(49.8)} fill="rgba(243,156,18,0.06)"/>
          <rect x={PAD.left} y={fy(49.5)} width={CHART_W} height={fy(49.0) - fy(49.5)} fill="rgba(231,76,60,0.07)"/>
          <rect x={PAD.left} y={fy(49.0)} width={CHART_W} height={fy(F_MIN) - fy(49.0)} fill="rgba(231,76,60,0.12)"/>
        </>}

        {/* collapse mode: dark-red background fill below 50 Hz */}
        {collapseMode && (
          <rect x={PAD.left} y={fy(50)} width={CHART_W} height={fy(0) - fy(50)}
                fill="rgba(120,0,0,0.18)"/>
        )}

        {/* 50 Hz reference */}
        <line x1={PAD.left} y1={fy(50)} x2={PAD.left + CHART_W} y2={fy(50)}
              stroke="rgba(255,255,255,0.15)" strokeWidth="1" strokeDasharray="4 3"/>

        {/* 49.8 Hz floor — normal mode only */}
        {!collapseMode && (
          <line x1={PAD.left} y1={fy(49.8)} x2={PAD.left + CHART_W} y2={fy(49.8)}
                stroke="rgba(0,229,160,0.4)" strokeWidth="0.7" strokeDasharray="3 3"/>
        )}

        {/* 49.0 Hz UFLS line — normal mode only */}
        {!collapseMode && (
          <line x1={PAD.left} y1={fy(49.0)} x2={PAD.left + CHART_W} y2={fy(49.0)}
                stroke="rgba(231,76,60,0.5)" strokeWidth="0.7" strokeDasharray="3 3"/>
        )}

        {/* 0 Hz line — collapse mode only */}
        {collapseMode && (
          <line x1={PAD.left} y1={fy(0)} x2={PAD.left + CHART_W} y2={fy(0)}
                stroke="rgba(255,50,50,0.4)" strokeWidth="0.8" strokeDasharray="3 3"/>
        )}

        {/* Y labels */}
        {yTicks.map(f => (
          <text key={f}
            x={PAD.left - 4} y={fy(f) + 3.5}
            textAnchor="end"
            fontSize="8"
            fontFamily="JetBrains Mono, monospace"
            fill="rgba(136,153,170,0.8)"
          >{f.toFixed(collapseMode ? 0 : 1)}</text>
        ))}

        {/* area fill — normal mode only */}
        {areaPoints && (
          <polygon
            points={areaPoints}
            fill={`url(#fill-${side})`}
            clipPath={`url(#clip-${side})`}
          />
        )}

        {/* frequency line */}
        {points && (
          <polyline
            points={points}
            fill="none"
            stroke={color}
            strokeWidth="1.8"
            strokeLinejoin="round"
            clipPath={`url(#clip-${side})`}
          />
        )}

        {/* current value dot */}
        {freqHistory.length > 0 && (() => {
          const lastT = timeHistory[timeHistory.length - 1] ?? freqHistory.length - 1
          const px = PAD.left + (lastT / Math.max(totalDur, 1)) * CHART_W
          const py = fy(currentF)
          if (py < PAD.top || py > PAD.top + CHART_H) return null
          return (
            <circle cx={px} cy={py} r="3.5" fill={color}>
              <animate attributeName="r" values="3.5;5;3.5" dur="1.5s" repeatCount="indefinite"/>
            </circle>
          )
        })()}

        {/* collapse mode: "BLACKOUT" label top-left */}
        {collapseMode && (
          <text x={PAD.left + 4} y={PAD.top + 10}
                fontSize="9" fontFamily="Inter, sans-serif" fontWeight="700"
                fill="rgba(255,80,80,0.85)" letterSpacing="0.1em">
            BLACKOUT
          </text>
        )}

        {/* X axis labels */}
        {[0, 0.25, 0.5, 0.75, 1.0].map(frac => {
          const t = Math.round(frac * (totalDur || 0))
          const px = PAD.left + frac * CHART_W
          return (
            <text key={frac} x={px} y={H - 5}
                  textAnchor="middle" fontSize="8"
                  fontFamily="JetBrains Mono, monospace"
                  fill="rgba(136,153,170,0.7)">
              {formatT(t)}
            </text>
          )
        })}

        {/* blackout countdown — normal mode only */}
        {showBlackout && (
          <g>
            <rect x={W - 110} y={PAD.top} width={102} height={32}
                  rx="4" fill="rgba(231,76,60,0.2)" stroke="rgba(231,76,60,0.5)" strokeWidth="1"/>
            <text x={W - 60} y={PAD.top + 12}
                  textAnchor="middle" fontSize="8.5"
                  fontFamily="Inter, sans-serif" fontWeight="600"
                  fill="#ff6b5b">BLACKOUT IN</text>
            <text x={W - 60} y={PAD.top + 26}
                  textAnchor="middle" fontSize="13"
                  fontFamily="JetBrains Mono, monospace" fontWeight="700"
                  fill="#ff4444">
              {(() => {
                if (freqHistory.length < 5) return '—'
                const rocof = (freqHistory[freqHistory.length-1] - freqHistory[freqHistory.length-6]) / 5
                if (rocof >= 0) return '—'
                const secsLeft = Math.max(0, (currentF - 47.0) / (-rocof))
                const m = Math.floor(secsLeft / 60)
                const s = Math.floor(secsLeft % 60)
                return `${m}:${String(s).padStart(2,'0')}`
              })()}
            </text>
          </g>
        )}
      </svg>
    </div>
  )
}
