import React from 'react'
import './Header.css'

export default function Header({
  scenario, scenarios, onScenarioChange,
  duration, onDurationChange,
  onRun, loading, playing, hasData,
  frameIdx, totalFrames, frameT,
  onTogglePlay, onScrub,
}) {
  const progress = totalFrames > 0 ? (frameIdx / (totalFrames - 1)) * 100 : 0

  return (
    <header className="header">
      <div className="header-left">
        <div className="logo">
          <div className="logo-icon">
            <svg viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="2"/>
              <path d="M16 6 L20 14 L16 12 L20 22 L12 14 L16 16 Z"
                    fill="currentColor" opacity="0.9"/>
            </svg>
          </div>
          <span className="logo-text">GridGuard AI</span>
        </div>
      </div>

      <div className="header-center">
        <h1 className="title">
          GridGuard AI — Conventional Grid vs Physics-Informed Digital Twin
        </h1>
      </div>

      <div className="header-right">
        <select
          className="control-select"
          value={scenario}
          onChange={e => onScenarioChange(e.target.value)}
          disabled={loading}
        >
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>

        <select
          className="control-select"
          value={duration}
          onChange={e => onDurationChange(Number(e.target.value))}
          disabled={loading}
        >
          <option value={200}>200 s</option>
          <option value={400}>400 s</option>
          <option value={600}>600 s</option>
        </select>

        <button
          className={`btn-run ${loading ? 'loading' : ''}`}
          onClick={onRun}
          disabled={loading}
        >
          {loading ? 'Running…' : 'RUN'}
        </button>

        {hasData && (
          <button
            className={`btn-play ${playing ? 'active' : ''}`}
            onClick={onTogglePlay}
            disabled={loading}
          >
            {playing ? '⏸' : (frameIdx >= totalFrames - 1 ? '↺' : '▶')}
          </button>
        )}
      </div>

      {hasData && (
        <div className="timeline-bar">
          <span className="timeline-label">t = {frameT}s</span>
          <input
            type="range"
            className="timeline-slider"
            min={0}
            max={totalFrames - 1}
            value={frameIdx}
            onChange={e => onScrub(Number(e.target.value))}
          />
          <span className="timeline-label">{totalFrames}s</span>
        </div>
      )}
    </header>
  )
}
