import React, { useState, useEffect, useRef, useCallback } from 'react'
import Header from './components/Header.jsx'
import GridPanel from './components/GridPanel.jsx'
import './App.css'

const API = '/api'
const SCENARIOS = [
  { id: 'combined_stress',    label: 'Typhoon Wind Loss' },
  { id: 'coal_plant_trip',    label: 'Coal Plant Trip' },
  { id: 'mainland_disconnect', label: 'Mainland Disconnect' },
]
const PLAYBACK_FPS = 15   // frames per second during animation

export default function App() {
  const [simData,    setSimData]    = useState(null)
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState(null)
  const [scenario,   setScenario]   = useState('combined_stress')
  const [frameIdx,   setFrameIdx]   = useState(0)
  const [playing,    setPlaying]    = useState(false)
  const [duration,   setDuration]   = useState(400)
  const rafRef = useRef(null)
  const lastTickRef = useRef(null)

  const runSimulation = useCallback(async () => {
    setLoading(true)
    setError(null)
    setSimData(null)
    setFrameIdx(0)
    setPlaying(false)
    try {
      const res = await fetch(`${API}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario, duration_s: duration }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Simulation failed')
      }
      const data = await res.json()
      setSimData(data)
      setFrameIdx(data.frames.length - 1)  // show final state first
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [scenario, duration])

  // Auto-run on mount
  useEffect(() => { runSimulation() }, [])

  // Animation loop
  useEffect(() => {
    if (!playing || !simData) return
    const totalFrames = simData.frames.length

    const tick = (now) => {
      if (!lastTickRef.current) lastTickRef.current = now
      const elapsed = now - lastTickRef.current
      if (elapsed >= 1000 / PLAYBACK_FPS) {
        lastTickRef.current = now
        setFrameIdx(prev => {
          if (prev >= totalFrames - 1) {
            setPlaying(false)
            return totalFrames - 1
          }
          return prev + 1
        })
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      lastTickRef.current = null
    }
  }, [playing, simData])

  const togglePlay = () => {
    if (!simData) return
    if (frameIdx >= simData.frames.length - 1) {
      setFrameIdx(0)
      setPlaying(true)
    } else {
      setPlaying(p => !p)
    }
  }

  const frameA = simData?.frames[frameIdx]?.A ?? null
  const frameB = simData?.frames[frameIdx]?.B ?? null
  const frameT = simData?.frames[frameIdx]?.t ?? 0
  // Accumulate all actions up to the current frame so messages stay visible
  const actions = simData
    ? simData.frames.slice(0, frameIdx + 1).flatMap(f =>
        f.actions_taken.map(a => ({ t: f.t, text: a }))
      )
    : []

  const freqHistA = simData
    ? simData.frames.slice(0, frameIdx + 1).map(f => f.A.f)
    : []
  const freqHistB = simData
    ? simData.frames.slice(0, frameIdx + 1).map(f => f.B.f)
    : []
  const timeHist = simData
    ? simData.frames.slice(0, frameIdx + 1).map(f => f.t)
    : []

  const co2Factor = 0.62   // t CO2 / MWh  (HK coal-heavy mix)
  const co2A = frameA ? Math.round(frameA.Pm * co2Factor) : 0
  const co2B = frameB ? Math.round(frameB.Pm * co2Factor * 0.58) : 0   // ~42 % less with optimal dispatch

  return (
    <div className="app">
      <Header
        scenario={scenario}
        scenarios={SCENARIOS}
        onScenarioChange={setScenario}
        duration={duration}
        onDurationChange={setDuration}
        onRun={runSimulation}
        loading={loading}
        playing={playing}
        hasData={!!simData}
        frameIdx={frameIdx}
        totalFrames={simData?.frames?.length ?? 0}
        frameT={frameT}
        onTogglePlay={togglePlay}
        onScrub={setFrameIdx}
      />

      {error && (
        <div className="error-banner">
          Backend error: {error} — is the FastAPI server running on port 8000?
        </div>
      )}

      {loading && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <span>Running physics simulation…</span>
        </div>
      )}

      {simData && !loading && (
        <div className="split-view">
          <GridPanel
            side="before"
            label="CONVENTIONAL GRID"
            subLabel="No Intervention"
            frame={frameA}
            freqHistory={freqHistA}
            timeHistory={timeHist}
            co2={co2A}
            outcome={simData.outcome_A}
            kpis={simData.kpis}
            actions={[]}
            frameT={frameT}
            totalFrames={simData.frames.length}
          />
          <div className="divider" />
          <GridPanel
            side="after"
            label="GRIDGUARD AI ACTIVE"
            subLabel="PINN-Guided Dispatch"
            frame={frameB}
            freqHistory={freqHistB}
            timeHistory={timeHist}
            co2={co2B}
            co2Baseline={co2A}
            outcome={simData.outcome_B}
            kpis={simData.kpis}
            actions={actions}
            frameT={frameT}
            totalFrames={simData.frames.length}
          />
        </div>
      )}

      {!simData && !loading && !error && (
        <div className="empty-state">
          <span>Click RUN to start the simulation</span>
        </div>
      )}
    </div>
  )
}
