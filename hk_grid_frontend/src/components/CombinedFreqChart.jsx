import React, { useMemo } from 'react'
import './CombinedFreqChart.css'

const W = 1080
const H = 100
const PAD = { top: 8, right: 16, bottom: 22, left: 42 }
const CHART_W = W - PAD.left - PAD.right
const CHART_H = H - PAD.top - PAD.bottom

const F_MAX          = 51.0
const F_MIN_NORMAL   = 47.5
const F_MIN_COLLAPSE = 0.0

function formatT(t) {
  if (t < 60) return `${t}s`
  return `${Math.floor(t / 60)}m${(t % 60).toString().padStart(2, '0')}s`
}

export default function CombinedFreqChart({ freqHistA = [], freqHistB = [], timeHistory = [] }) {
  const totalDur = timeHistory.length > 0 ? timeHistory[timeHistory.length - 1] : 1
  const currentA = freqHistA[freqHistA.length - 1] ?? 50
  const currentB = freqHistB[freqHistB.length - 1] ?? 50

  const collapseMode = Math.min(currentA, currentB) < F_MIN_NORMAL
  const F_MIN   = collapseMode ? F_MIN_COLLAPSE : F_MIN_NORMAL
  const F_RANGE = F_MAX - F_MIN

  function fy(f) {
    return PAD.top + CHART_H * (1 - (f - F_MIN) / F_RANGE)
  }

  function buildPoints(hist) {
    if (!hist.length) return ''
    return hist.map((f, i) => {
      const t  = timeHistory[i] ?? i
      const px = PAD.left + (t / Math.max(totalDur, 1)) * CHART_W
      const py = fy(f)
      return `${px},${py}`
    }).join(' ')
  }

  const pointsA = useMemo(
    () => buildPoints(freqHistA),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [freqHistA, timeHistory, totalDur, collapseMode]
  )
  const pointsB = useMemo(
    () => buildPoints(freqHistB),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [freqHistB, timeHistory, totalDur, collapseMode]
  )

  const yTicks = collapseMode ? [0, 20, 40, 50] : [47.5, 48.5, 49.0, 50.0, 51.0]

  return (
    <div className="combined-chart">
      <div className="combined-chart-header">
        <span className="combined-chart-title">FREQUENCY TRAJECTORY</span>
        <div className="combined-chart-legend">
          <span className="legend-a">● NO INTERVENTION</span>
          <span className="legend-b">● TIANGOU AI ACTIVE</span>
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="combined-chart-svg">
        <defs>
          <clipPath id="clip-combined">
            <rect x={PAD.left} y={PAD.top} width={CHART_W} height={CHART_H} />
          </clipPath>
        </defs>

        {/* safety bands — normal mode */}
        {!collapseMode && <>
          <rect x={PAD.left} y={fy(51)}   width={CHART_W} height={fy(50.2) - fy(51)}   fill="rgba(0,229,160,0.04)"/>
          <rect x={PAD.left} y={fy(50.2)} width={CHART_W} height={fy(49.8) - fy(50.2)} fill="rgba(0,229,160,0.07)"/>
          <rect x={PAD.left} y={fy(49.8)} width={CHART_W} height={fy(49.5) - fy(49.8)} fill="rgba(243,156,18,0.06)"/>
          <rect x={PAD.left} y={fy(49.5)} width={CHART_W} height={fy(49.0) - fy(49.5)} fill="rgba(231,76,60,0.07)"/>
          <rect x={PAD.left} y={fy(49.0)} width={CHART_W} height={fy(F_MIN) - fy(49.0)} fill="rgba(231,76,60,0.12)"/>
        </>}

        {/* collapse background */}
        {collapseMode && (
          <rect x={PAD.left} y={fy(50)} width={CHART_W} height={fy(0) - fy(50)}
                fill="rgba(120,0,0,0.18)"/>
        )}

        {/* 50 Hz reference */}
        <line x1={PAD.left} y1={fy(50)} x2={PAD.left + CHART_W} y2={fy(50)}
              stroke="rgba(255,255,255,0.15)" strokeWidth="1" strokeDasharray="4 3"/>

        {!collapseMode && <>
          <line x1={PAD.left} y1={fy(49.8)} x2={PAD.left + CHART_W} y2={fy(49.8)}
                stroke="rgba(0,229,160,0.4)" strokeWidth="0.7" strokeDasharray="3 3"/>
          <line x1={PAD.left} y1={fy(49.0)} x2={PAD.left + CHART_W} y2={fy(49.0)}
                stroke="rgba(231,76,60,0.5)" strokeWidth="0.7" strokeDasharray="3 3"/>
        </>}

        {/* Y labels */}
        {yTicks.map(f => (
          <text key={f} x={PAD.left - 4} y={fy(f) + 3.5}
                textAnchor="end" fontSize="8"
                fontFamily="JetBrains Mono, monospace"
                fill="rgba(136,153,170,0.8)">
            {f.toFixed(collapseMode ? 0 : 1)}
          </text>
        ))}

        {/* Timeline A — no intervention (red) */}
        {pointsA && (
          <polyline points={pointsA} fill="none" stroke="#e74c3c" strokeWidth="1.8"
                    strokeLinejoin="round" clipPath="url(#clip-combined)" opacity="0.85"/>
        )}

        {/* Timeline B — Tiangou AI (green) */}
        {pointsB && (
          <polyline points={pointsB} fill="none" stroke="#00e5a0" strokeWidth="1.8"
                    strokeLinejoin="round" clipPath="url(#clip-combined)"/>
        )}

        {/* Current value dots */}
        {freqHistA.length > 0 && (() => {
          const lastT = timeHistory[timeHistory.length - 1] ?? freqHistA.length - 1
          const px = PAD.left + (lastT / Math.max(totalDur, 1)) * CHART_W
          const py = fy(currentA)
          if (py < PAD.top || py > PAD.top + CHART_H) return null
          return (
            <circle cx={px} cy={py} r="3.5" fill="#e74c3c" opacity="0.9">
              <animate attributeName="r" values="3.5;5;3.5" dur="1.5s" repeatCount="indefinite"/>
            </circle>
          )
        })()}
        {freqHistB.length > 0 && (() => {
          const lastT = timeHistory[timeHistory.length - 1] ?? freqHistB.length - 1
          const px = PAD.left + (lastT / Math.max(totalDur, 1)) * CHART_W
          const py = fy(currentB)
          if (py < PAD.top || py > PAD.top + CHART_H) return null
          return (
            <circle cx={px} cy={py} r="3.5" fill="#00e5a0">
              <animate attributeName="r" values="3.5;5;3.5" dur="1.5s" repeatCount="indefinite"/>
            </circle>
          )
        })()}

        {/* X labels */}
        {[0, 0.25, 0.5, 0.75, 1.0].map(frac => {
          const t  = Math.round(frac * (totalDur || 0))
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

        {/* BLACKOUT label */}
        {collapseMode && (
          <text x={PAD.left + 4} y={PAD.top + 10}
                fontSize="9" fontFamily="Inter, sans-serif" fontWeight="700"
                fill="rgba(255,80,80,0.85)" letterSpacing="0.1em">
            BLACKOUT
          </text>
        )}
      </svg>
    </div>
  )
}
