import React from 'react'
import HKMap from './HKMap.jsx'
import FreqChart from './FreqChart.jsx'
import './GridPanel.css'

const DISTURBANCE_T = 30

function fmtFreq(f) { return f != null ? f.toFixed(2) : '—' }
function fmtHz(f)   { return f != null ? f.toFixed(3) : '—' }

function statusInfo(level, side) {
  if (side === 'before') {
    if (level === 'CRITICAL') return { text: 'CRITICAL', cls: 'status-critical' }
    if (level === 'ALERT')    return { text: 'ALERT',    cls: 'status-alert' }
    if (level === 'WATCH')    return { text: 'WATCH',    cls: 'status-watch' }
    return { text: 'NORMAL', cls: 'status-normal' }
  }
  // after side: show outcome
  if (level === 'CRITICAL') return { text: 'CRITICAL', cls: 'status-critical' }
  if (level === 'ALERT')    return { text: 'ACTIVE',   cls: 'status-alert' }
  return { text: 'STABLE', cls: 'status-stable' }
}

function blackoutEta(freqHistory, totalFrames, frameT) {
  if (!freqHistory?.length) return null
  const f = freqHistory[freqHistory.length - 1]
  if (f >= 49.0) return null
  const rocof = freqHistory.length > 5
    ? (freqHistory[freqHistory.length - 1] - freqHistory[freqHistory.length - 6]) / 5
    : -0.05
  if (rocof >= 0) return null
  const secsLeft = Math.max(0, (f - 47.0) / (-rocof))
  const m = Math.floor(secsLeft / 60)
  const s = Math.floor(secsLeft % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export default function GridPanel({
  side, label, subLabel,
  frame, freqHistory, timeHistory, co2, co2Baseline,
  outcome, kpis, actions, frameT, totalFrames,
}) {
  const isAfter = side === 'after'
  const f  = frame?.f ?? 50
  const rl = frame?.risk_level ?? 'NORMAL'
  const Pm = frame?.Pm ?? 0
  const Pe = frame?.Pe ?? 0
  const H  = frame?.H_physical ?? 0
  const Hp = frame?.H_pinn ?? 0
  const rf = frame?.renewable_fraction ?? 0
  const rocof = Math.abs(frame?.df_dt ?? 0)

  const isBlackout = !isAfter && f < 1.0
  const status   = isBlackout
    ? { text: 'BLACKOUT', cls: 'status-critical' }
    : statusInfo(rl, side)
  const eta      = !isAfter && !isBlackout ? blackoutEta(freqHistory, totalFrames, frameT) : null
  const finalBad = !isAfter && outcome === 'BLACKOUT'

  const co2Pct   = isAfter && co2Baseline > 0
    ? Math.round((1 - co2 / co2Baseline) * 100)
    : 42
  const renewable = Math.round(rf * 100)

  return (
    <div className={`grid-panel grid-panel--${side}`}>

      {/* ── panel header ─────────────────────────── */}
      <div className="panel-header">
        <span className={`panel-badge panel-badge--${side}`}>
          {isAfter ? 'AFTER' : 'BEFORE'}
        </span>
        <div className="panel-titles">
          <div className="panel-label">{label}</div>
          <div className="panel-sublabel">{subLabel}</div>
        </div>
      </div>

      {/* ── status row ───────────────────────────── */}
      <div className="stat-row">
        <div className="stat-card">
          <div className="stat-name">FREQUENCY</div>
          <div className={`stat-value ${f < 49.5 ? 'stat-red' : f < 49.8 ? 'stat-amber' : isAfter ? 'stat-green' : 'stat-white'}`}>
            {fmtFreq(f)} <span className="stat-unit">Hz</span>
          </div>
          <FreqSparkline f={f} />
        </div>

        <div className={`stat-card stat-card--status ${status.cls}`}>
          <div className="stat-name">STATUS</div>
          <div className={`status-text ${status.cls}`}>{status.text}</div>
          <div className="status-icon">
            {status.cls === 'status-stable' && <span>✓</span>}
            {status.cls === 'status-critical' && <span>⚠</span>}
            {status.cls === 'status-alert' && <span>⚡</span>}
            {status.cls === 'status-watch' && <span>◎</span>}
            {status.cls === 'status-normal' && <span>○</span>}
          </div>
        </div>

      </div>

      {/* ── alert / stable banner ────────────────── */}
      {isBlackout && (
        <div className="alert-banner alert-banner--blackout">
          <span className="alert-icon">☠</span>
          <strong>TOTAL GRID BLACKOUT</strong> — Cascade relay failure — frequency collapsed to 0 Hz
        </div>
      )}
      {!isAfter && !isBlackout && (eta || f < 49.5) && (
        <div className="alert-banner alert-banner--critical">
          <span className="alert-icon">⚠</span>
          {eta
            ? <><strong>BLACKOUT IN {eta}</strong> — Insufficient inertia to absorb generation loss</>
            : <><strong>FREQUENCY CRITICAL</strong> — {fmtFreq(f)} Hz — cascade risk</>
          }
        </div>
      )}
      {!isAfter && !isBlackout && f >= 49.5 && f < 49.8 && (
        <div className="alert-banner alert-banner--warn">
          <span className="alert-icon">◎</span>
          <strong>FREQUENCY ALERT</strong> — {fmtFreq(f)} Hz — primary response active
        </div>
      )}
      {isAfter && (outcome === 'STABLE' || f >= 49.8) && (
        <div className="alert-banner alert-banner--stable">
          <span className="alert-icon">✓</span>
          <strong>STABLE</strong> — Optimal dispatch active, blackout prevented
        </div>
      )}
      {isAfter && actions.length > 0 && (
        <div className="action-banner">
          <span className="action-icon">⚡</span>
          {actions.slice(0, 2).join(' · ')}
          {actions.length > 2 && ` + ${actions.length - 2} more`}
        </div>
      )}

      {/* ── HK map ───────────────────────────────── */}
      <div className="map-container">
        <HKMap
          side={side}
          freq={f}
          activeSources={frame?.active_sources ?? []}
        />
      </div>

      {/* ── bottom section ───────────────────────── */}
      <div className="panel-bottom">
        <div className="freq-chart-wrap">
          <div className="section-title">
            {isAfter
              ? 'AI RESPONSE — Frequency stabilised'
              : isBlackout
                ? 'GRID BLACKOUT — Cascade collapse'
                : 'FREQUENCY TRAJECTORY'
            }
            <span className="section-subtitle">
              {isAfter
                ? ' GridGuard dispatch active'
                : isBlackout
                  ? ' All generators tripped — frequency collapsed to 0 Hz'
                  : ' Real-time frequency decline'
              }
            </span>
          </div>
          <FreqChart
            freqHistory={freqHistory}
            timeHistory={timeHistory}
            side={side}
          />
          {isAfter && (
            <div className="kpi-strip">
              <span className="kpi-strip-item">🌿 <strong>-{co2Pct}%</strong> CO₂</span>
              <span className="kpi-strip-item">⚡ <strong>+{renewable}%</strong> renewable</span>
              <span className="kpi-strip-item">$ <strong>{kpis?.cost_saved_usd ? '$' + (kpis.cost_saved_usd / 1000).toFixed(1) + 'K' : '—'}</strong> saved</span>
            </div>
          )}
        </div>

        {/* ── physics readouts ─────────────────────── */}
        <div className="physics-row">
          <PhysicsItem label="H (phys)" value={H.toFixed(3)} unit="s" />
          {isAfter && <PhysicsItem label="H (PINN)" value={Hp.toFixed(3)} unit="s" color="var(--amber)" />}
          <PhysicsItem label="RoCoF" value={rocof.toFixed(3)} unit="Hz/s" alert={rocof > 0.3} />
          <PhysicsItem label="Pm" value={Math.round(Pm)} unit="MW" />
          <PhysicsItem label="Pe" value={Math.round(Pe)} unit="MW" />
          <PhysicsItem
            label="ΔP"
            value={Math.round(Pm - Pe)}
            unit="MW"
            alert={(Pm - Pe) < -200}
            positive={(Pm - Pe) > 0}
          />
        </div>
      </div>
    </div>
  )
}

function FreqSparkline({ f }) {
  const fSafe = f ?? 50
  const pct = Math.max(0, Math.min(100, ((fSafe - 47) / 4) * 100))
  const color = fSafe < 49.0 ? 'var(--red)' : fSafe < 49.8 ? 'var(--amber)' : 'var(--green)'
  return (
    <div className="freq-sparkline">
      <div className="sparkline-bar">
        <div className="sparkline-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}


function KpiBox({ icon, value, label, color }) {
  return (
    <div className="kpi-box" style={{ '--kpi-color': color }}>
      <div className="kpi-icon">{icon}</div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{label}</div>
    </div>
  )
}

function PhysicsItem({ label, value, unit, alert, positive, color }) {
  const cls = alert ? 'phys-alert' : positive ? 'phys-positive' : ''
  return (
    <div className={`phys-item ${cls}`} style={color ? { '--phys-color': color } : {}}>
      <span className="phys-label">{label}</span>
      <span className="phys-value" style={color ? { color } : {}}>
        {value}<span className="phys-unit"> {unit}</span>
      </span>
    </div>
  )
}
