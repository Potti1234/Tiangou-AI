import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchLiveState, runSimulation, connectLiveSocket } from "../services/backendClient";
import { getTelemetryMode } from "../services/telemetryClient";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const LIVE_INTERVAL_MS = 1200;
const SIMULATION_INTERVAL_MS = 50;
const HISTORY_LENGTH = 54;
const PREDICTION_HORIZON_SEC = 20;
const BUFFER_FRAMES = 5;
const BUFFER_INTERVAL_MS = 720;
// Fallback constants used when backend is unavailable (mirrored from useLiveSimulation)
const FALLBACK_TOTAL_FRAMES = 60;
const FALLBACK_SIMULATION_DURATION_SEC = 120;
const FALLBACK_DETECTION_FRAME = 6;
const FALLBACK_DECISION_FRAME = 10;
const FALLBACK_ACTUATION_FRAME = 12;
const FALLBACK_STABILIZATION_FRAME = 36;

// Scenario id mapping: v18 id → backend scenario string
const SCENARIO_BACKEND_MAP = {
  generatorTrip: "coal_plant_trip",
  dataCenter: "combined_stress",
  importDrop: "mainland_disconnect",
  typhoon: "combined_stress",
};

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------
const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
const jitter = (range) => (Math.random() - 0.5) * range;
const round = (value, digits = 2) => Number(Number(value).toFixed(digits));

function padTrace(values, length = HISTORY_LENGTH, fallback = 0) {
  const result = Array.isArray(values) ? [...values] : [];
  while (result.length < length) result.unshift(result[0] ?? fallback);
  return result.slice(-length);
}

function appendTrace(values, value, length = HISTORY_LENGTH) {
  return [...values.slice(-(length - 1)), round(value, 3)];
}

function riskLevelToStatus(level) {
  if (level === "CRITICAL") return "Critical";
  if (level === "ALERT") return "Warning";
  if (level === "WATCH") return "Warning";
  return "Stable";
}

function gridStateToTelemetry(gs, prev) {
  const f = gs.f ?? gs.frequency_hz ?? prev.frequency;
  const H = gs.H_physical ?? gs.inertia_seconds ?? prev.inertia;
  const Pm = gs.Pm_eff ?? gs.Pm ?? gs.production_mw ?? prev.production;
  const Pe = gs.Pe ?? gs.demand_mw ?? prev.demand;
  const rf = gs.renewable_fraction ?? gs.renewable_frac ?? (prev.renewableShare / 100);
  const risk = gs.risk_score ?? (prev.stabilityRisk / 100);
  const traj = gs.trajectory_60s ?? gs.frequency_prediction_hz ?? prev.frequencyPrediction ?? [];

  return {
    frequency: round(f, 3),
    inertia: round(H, 3),
    criticalInertia: 2.0,
    rocof: round(gs.df_dt ?? 0, 3),
    co2Rate: Math.round((1 - rf) * Math.max(Pm, 0) * 0.49),
    gap: Math.max(0, Math.round(Pe - Pm)),
    reserves: Math.max(0, Math.round(Pm - Pe)),
    stabilityRisk: Math.round(risk * 100),
    thresholdBreach: Math.round(risk * 100),
    demand: Math.round(Pe),
    production: Math.round(Pm),
    synchronous: Math.round((1 - rf) * Pm),
    nonSynchronous: Math.round(rf * Pm),
    imports: 0,
    batteryFlex: 200,
    evFlex: 22.5,
    flexibleDemand: 200,
    curtailment: 0,
    renewableShare: round(rf * 100, 1),
    overloads: prev.overloads ?? [48, 42, 51, 44, 39, 46],
    frequencyPrediction: Array.isArray(traj) ? traj.slice(0, 21).map((v) => round(v, 3)) : prev.frequencyPrediction ?? [],
    nadir: Array.isArray(traj) && traj.length ? round(Math.min(...traj), 2) : round(f, 2),
    predictedNadir: Array.isArray(traj) && traj.length ? round(Math.min(...traj), 2) : round(f, 2),
    status: riskLevelToStatus(gs.risk_level ?? "NORMAL"),
    dataSource: "backend",
  };
}

// Build initial stable telemetry from scenarios.stable
function buildStableTelemetry(stableScenario) {
  const base = stableScenario.before;
  const production = base.demand - base.gap;
  const frequencyTrace = padTrace(base.frequencyTrace, HISTORY_LENGTH, base.frequency);
  const inertiaTrace = padTrace(
    frequencyTrace.map((_, i) => round(base.inertia + Math.sin(i / 4) * 0.018, 3)),
    HISTORY_LENGTH,
    base.inertia
  );
  const demandTrace = padTrace(
    frequencyTrace.map((_, i) => round(base.demand + Math.sin(i / 5) * 35 + Math.cos(i / 8) * 18, 1)),
    HISTORY_LENGTH,
    base.demand
  );
  const productionTrace = padTrace(
    demandTrace.map((v, i) => round(v - 6 + Math.sin(i / 3) * 10, 1)),
    HISTORY_LENGTH,
    production
  );

  return {
    ...base,
    production,
    frequencyTrace,
    inertiaTrace,
    demandTrace,
    productionTrace,
    frequencyPrediction: base.frequencyTrace ? [...base.frequencyTrace] : [],
    timestamp: Date.now(),
    dataTimestamp: new Date().toISOString(),
    dataSource: "mock-fallback",
    status: "Stable",
  };
}

// Apply a live backend snapshot to the current state
function applyBackendSnapshot(previous, snapshot) {
  const mapped = gridStateToTelemetry(snapshot, previous);
  // Jitter frequency slightly to look live
  const f = round(mapped.frequency + jitter(0.004), 3);

  return {
    ...previous,
    ...mapped,
    frequency: f,
    frequencyTrace: appendTrace(previous.frequencyTrace, f),
    inertiaTrace: appendTrace(previous.inertiaTrace, mapped.inertia),
    demandTrace: appendTrace(previous.demandTrace, mapped.demand),
    productionTrace: appendTrace(previous.productionTrace, mapped.production),
    timestamp: Date.now(),
    dataTimestamp: new Date().toISOString(),
  };
}

// Apply mock jitter in the absence of backend data (same as useLiveSimulation fallback)
function applyMockLive(previous, stableScenario) {
  const base = stableScenario.before;
  const frequency = clamp(previous.frequency + jitter(0.024) + (50 - previous.frequency) * 0.18, 49.96, 50.04);
  const inertia = clamp(previous.inertia + jitter(0.018) + (base.inertia - previous.inertia) * 0.14, 2.40, 2.57);
  const demand = Math.round(clamp(previous.demand + jitter(32), base.demand - 95, base.demand + 110));
  const renewableShare = round(clamp(previous.renewableShare + jitter(0.9), 29, 34), 1);
  const production = Math.round(demand - Math.max(0, Math.round(Math.abs(demand - base.demand) * 0.12 + jitter(5))));

  return {
    ...previous,
    frequency: round(frequency, 3),
    inertia: round(inertia, 3),
    demand,
    production,
    renewableShare,
    frequencyTrace: appendTrace(previous.frequencyTrace, frequency),
    inertiaTrace: appendTrace(previous.inertiaTrace, inertia),
    demandTrace: appendTrace(previous.demandTrace, demand),
    productionTrace: appendTrace(previous.productionTrace, production),
    timestamp: Date.now(),
    dataTimestamp: new Date().toISOString(),
    dataSource: "mock-fallback",
    status: "Stable",
  };
}

// Map a backend frame's grid side (A = before/conventional, B = after/AI) to telemetry shape,
// also carrying trace history forward.
function applyFrameSide(gs, priorTelemetry) {
  const mapped = gridStateToTelemetry(gs, priorTelemetry);
  return {
    ...priorTelemetry,
    ...mapped,
    frequencyTrace: appendTrace(priorTelemetry.frequencyTrace, mapped.frequency),
    inertiaTrace: appendTrace(priorTelemetry.inertiaTrace, mapped.inertia),
    demandTrace: appendTrace(priorTelemetry.demandTrace, mapped.demand),
    productionTrace: appendTrace(priorTelemetry.productionTrace, mapped.production),
    timestamp: Date.now(),
    dataTimestamp: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export default function useBackendSimulation({ scenarios, selectedScenario, onEvent }) {
  const stableScenario = scenarios.stable;
  const initialStable = useMemo(() => buildStableTelemetry(stableScenario), [stableScenario]);

  const [phase, setPhase] = useState("live");
  const [frame, setFrame] = useState(0);
  const [bufferFrame, setBufferFrame] = useState(0);
  const [live, setLive] = useState(initialStable);
  const [before, setBefore] = useState(initialStable);
  const [after, setAfter] = useState(initialStable);
  const [activeScenario, setActiveScenario] = useState(selectedScenario);
  const [backendFrames, setBackendFrames] = useState(null); // array from POST /simulate
  const [stableSnapshot, setStableSnapshot] = useState(initialStable);

  const lastSocketSnapshot = useRef(null);
  const pairRef = useRef({ before: initialStable, after: initialStable });

  // Derived constants that depend on whether we have real backend frames
  const totalFrames = backendFrames ? backendFrames.length : FALLBACK_TOTAL_FRAMES;
  const simulationDurationSec = backendFrames
    ? (backendFrames[backendFrames.length - 1]?.t ?? FALLBACK_SIMULATION_DURATION_SEC)
    : FALLBACK_SIMULATION_DURATION_SEC;

  // Derive decision/actuation/stabilization frames from backend data
  const decisionFrameIndex = useMemo(() => {
    if (!backendFrames) return FALLBACK_DECISION_FRAME;
    const idx = backendFrames.findIndex((f) => f.actions_taken && f.actions_taken.length > 0);
    return idx >= 0 ? idx : FALLBACK_DECISION_FRAME;
  }, [backendFrames]);

  const detectionFrameIndex = useMemo(() => {
    if (!backendFrames) return FALLBACK_DETECTION_FRAME;
    // Detection: first frame where A's risk_level is ALERT or CRITICAL
    const idx = backendFrames.findIndex(
      (f) => f.A?.risk_level === "ALERT" || f.A?.risk_level === "CRITICAL"
    );
    return idx >= 0 ? idx : Math.max(0, decisionFrameIndex - 4);
  }, [backendFrames, decisionFrameIndex]);

  const actuationFrameIndex = useMemo(() => {
    if (!backendFrames) return FALLBACK_ACTUATION_FRAME;
    return Math.min(decisionFrameIndex + 2, totalFrames - 1);
  }, [backendFrames, decisionFrameIndex, totalFrames]);

  const stabilizationFrameIndex = useMemo(() => {
    if (!backendFrames) return FALLBACK_STABILIZATION_FRAME;
    // Stabilization: first frame after actuation where B's frequency recovers above 49.8 Hz
    for (let i = actuationFrameIndex; i < backendFrames.length; i++) {
      if ((backendFrames[i].B?.f ?? 0) >= 49.8) return i;
    }
    return Math.round(totalFrames * 0.6);
  }, [backendFrames, actuationFrameIndex, totalFrames]);

  // -------------------------------------------------------------------------
  // WS live connection
  // -------------------------------------------------------------------------
  useEffect(() => {
    const disconnect = connectLiveSocket(
      (snapshot) => { lastSocketSnapshot.current = snapshot; },
      () => { /* silently ignore WS errors; polling will cover */ }
    );
    return typeof disconnect === "function" ? disconnect : undefined;
  }, []);

  // -------------------------------------------------------------------------
  // Live phase polling
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (phase !== "live") return undefined;
    let cancelled = false;

    const update = async () => {
      // Prefer WS snapshot if available
      const ws = lastSocketSnapshot.current;
      lastSocketSnapshot.current = null;

      if (ws) {
        if (!cancelled) setLive((current) => applyBackendSnapshot(current, ws));
        return;
      }

      // Fall back to REST polling
      try {
        const state = await fetchLiveState();
        if (!cancelled) setLive((current) => applyBackendSnapshot(current, state));
      } catch {
        // Backend unavailable — apply mock jitter so the display keeps moving
        if (!cancelled) setLive((current) => applyMockLive(current, stableScenario));
      }
    };

    update();
    const timer = window.setInterval(update, LIVE_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [phase, stableScenario]);

  // -------------------------------------------------------------------------
  // Buffering phase (stable bridge before simulation starts)
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (phase !== "buffering") return undefined;
    const timer = window.setInterval(() => {
      setBufferFrame((currentBuffer) => {
        const next = currentBuffer + 1;
        setBefore((current) => {
          const updated = applyMockLive(current, stableScenario);
          pairRef.current = { before: updated, after: updated };
          setAfter(updated);
          setLive(updated);
          return updated;
        });
        if (next >= BUFFER_FRAMES) {
          setFrame(0);
          setPhase("running");
          onEvent?.({
            severity: activeScenario.severity,
            type: "Disturbance injected",
            event: `Simulation data received. Disturbance begins: ${activeScenario.label}`,
            source: "Backend simulation",
          });
          return BUFFER_FRAMES;
        }
        return next;
      });
    }, BUFFER_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [phase, stableScenario, activeScenario, onEvent]);

  // -------------------------------------------------------------------------
  // Running phase — advance frame index
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (phase !== "running") return undefined;
    const timer = window.setInterval(() => {
      setFrame((currentFrame) => Math.min(currentFrame + 1, totalFrames - 1));
    }, SIMULATION_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [phase, totalFrames]);

  // -------------------------------------------------------------------------
  // Running phase — apply current frame to before/after
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (phase !== "running" || !backendFrames) return;
    const frameData = backendFrames[frame];
    if (!frameData) return;

    const nextBefore = applyFrameSide(frameData.A, pairRef.current.before);
    const nextAfter = applyFrameSide(frameData.B, pairRef.current.after);
    pairRef.current = { before: nextBefore, after: nextAfter };
    setBefore(nextBefore);
    setAfter(nextAfter);
    setLive(nextAfter);

    // Events
    if (frame === detectionFrameIndex) {
      onEvent?.({
        severity: "warning",
        type: "AI detection",
        event: `Disturbance detected by PINN: ${activeScenario.label}`,
        source: "PINN decision layer",
      });
    }
    if (frame === decisionFrameIndex) {
      const action = frameData.actions_taken?.[0] ?? `Corrective action issued: ${activeScenario.label}`;
      onEvent?.({
        severity: "warning",
        type: "AI decision",
        event: action,
        source: "Decision engine",
      });
    }
    // BLACKOUT event
    if (frameData.outcome_A === "BLACKOUT" && frame === totalFrames - 1) {
      onEvent?.({
        severity: "critical",
        type: "Blackout",
        event: `Uncontrolled outcome: BLACKOUT in conventional path — ${activeScenario.label}`,
        source: "Backend simulation",
      });
    }
    // B recovery above 49.8 Hz
    if (frame === stabilizationFrameIndex) {
      onEvent?.({
        severity: "stable",
        type: "Frequency recovery",
        event: `AI-controlled path stabilized above 49.8 Hz: ${activeScenario.label}`,
        source: "Backend simulation",
      });
    }
    // Simulation complete
    if (frame >= totalFrames - 1) {
      setPhase("complete");
      onEvent?.({
        severity: "stable",
        type: "Simulation complete",
        event: `Backend simulation completed: ${activeScenario.label}`,
        source: "Backend simulation",
      });
    }
  }, [
    phase,
    frame,
    backendFrames,
    activeScenario,
    decisionFrameIndex,
    detectionFrameIndex,
    stabilizationFrameIndex,
    totalFrames,
    onEvent,
  ]);

  // -------------------------------------------------------------------------
  // startSimulation
  // -------------------------------------------------------------------------
  const startSimulation = useCallback(
    async (scenarioOverride) => {
      const scenario = scenarioOverride || selectedScenario;

      // Stable scenario — just remain in live phase
      if (scenario.id === "stable") {
        onEvent?.({
          severity: "stable",
          type: "Live monitoring",
          event: "Stable scenario selected — continuing live monitoring",
          source: "Simulation controls",
        });
        return;
      }

      const backendScenario = SCENARIO_BACKEND_MAP[scenario.id] ?? "combined_stress";
      const stable = {
        ...live,
        frequencyTrace: padTrace(live.frequencyTrace, HISTORY_LENGTH, live.frequency),
        inertiaTrace: padTrace(live.inertiaTrace, HISTORY_LENGTH, live.inertia),
        demandTrace: padTrace(live.demandTrace, HISTORY_LENGTH, live.demand),
        productionTrace: padTrace(live.productionTrace, HISTORY_LENGTH, live.production),
        status: "Stable",
      };

      setActiveScenario(scenario);
      setStableSnapshot(stable);
      pairRef.current = { before: stable, after: stable };
      setBefore(stable);
      setAfter(stable);
      setFrame(0);
      setBufferFrame(0);
      setBackendFrames(null);

      onEvent?.({
        severity: "stable",
        type: "Simulation started",
        event: `Requesting backend simulation: ${scenario.label} (${backendScenario})`,
        source: "Backend simulation",
      });

      try {
        const result = await runSimulation(backendScenario, 400);
        const frames = result.frames ?? [];
        if (!frames.length) throw new Error("Backend returned 0 frames");
        setBackendFrames(frames);
        setPhase("buffering");
        onEvent?.({
          severity: "stable",
          type: "Stable buffer started",
          event: `Scenario queued after stable-grid buffer: ${scenario.label}`,
          source: "Simulation controls",
        });
      } catch (err) {
        // Backend unavailable — fall back gracefully: stay in live phase and notify
        console.warn("[useBackendSimulation] POST /simulate failed, staying in live phase:", err);
        setBackendFrames(null);
        setPhase("live");
        onEvent?.({
          severity: "warning",
          type: "Backend unavailable",
          event: `Could not reach simulation backend (${err.message}). Displaying live telemetry.`,
          source: "Simulation controls",
        });
      }
    },
    [live, selectedScenario, onEvent]
  );

  // -------------------------------------------------------------------------
  // resetLive
  // -------------------------------------------------------------------------
  const resetLive = useCallback(() => {
    const fresh = buildStableTelemetry(stableScenario);
    pairRef.current = { before: fresh, after: fresh };
    setLive(fresh);
    setBefore(fresh);
    setAfter(fresh);
    setStableSnapshot(fresh);
    setBackendFrames(null);
    setFrame(0);
    setBufferFrame(0);
    setPhase("live");
    onEvent?.({
      severity: "stable",
      type: "Live monitoring",
      event: "Returned to stable live telemetry",
      source: "Simulation controls",
    });
  }, [stableScenario, onEvent]);

  // -------------------------------------------------------------------------
  // togglePause
  // -------------------------------------------------------------------------
  const togglePause = useCallback(() => {
    setPhase((current) => {
      if (current === "running" || current === "buffering") return "paused";
      if (current === "paused") return frame === 0 ? "buffering" : "running";
      return current;
    });
  }, [frame]);

  // -------------------------------------------------------------------------
  // Derived values
  // -------------------------------------------------------------------------
  const progress =
    phase === "live"
      ? 0
      : phase === "buffering"
      ? Math.round((bufferFrame / BUFFER_FRAMES) * 10)
      : 10 + Math.round((frame / Math.max(totalFrames - 1, 1)) * 90);

  const secondsElapsed =
    phase === "live"
      ? 0
      : backendFrames && backendFrames[frame]
      ? backendFrames[frame].t
      : Math.round((frame / Math.max(totalFrames - 1, 1)) * simulationDurationSec);

  // Warning: show when before.risk_level is ALERT or CRITICAL during running phase
  const currentFrameData = backendFrames && phase === "running" ? backendFrames[frame] : null;
  const riskLevel = currentFrameData?.A?.risk_level ?? null;
  const warningActive =
    phase === "running" &&
    (riskLevel === "ALERT" || riskLevel === "CRITICAL" || frame >= detectionFrameIndex);
  const warning = warningActive
    ? {
        id: `${activeScenario.id}-warning`,
        severity: activeScenario.severity,
        popup: true,
        title: `${activeScenario.short}: preventive action required`,
        message: `PINN forecast identifies a ${(before.nadir ?? activeScenario.before.nadir ?? 49.5).toFixed(2)} Hz nadir risk within ${PREDICTION_HORIZON_SEC}s. Review the validated intervention.`,
      }
    : null;

  // Compute time-based constants for return shape
  const totalSec = simulationDurationSec;
  const detectionSecond = backendFrames
    ? (backendFrames[detectionFrameIndex]?.t ?? Math.round((detectionFrameIndex / Math.max(totalFrames - 1, 1)) * totalSec))
    : Math.round((FALLBACK_DETECTION_FRAME / (FALLBACK_TOTAL_FRAMES - 1)) * FALLBACK_SIMULATION_DURATION_SEC);
  const decisionSecond = backendFrames
    ? (backendFrames[decisionFrameIndex]?.t ?? Math.round((decisionFrameIndex / Math.max(totalFrames - 1, 1)) * totalSec))
    : Math.round((FALLBACK_DECISION_FRAME / (FALLBACK_TOTAL_FRAMES - 1)) * FALLBACK_SIMULATION_DURATION_SEC);
  const actuationSecond = backendFrames
    ? (backendFrames[actuationFrameIndex]?.t ?? Math.round((actuationFrameIndex / Math.max(totalFrames - 1, 1)) * totalSec))
    : Math.round((FALLBACK_ACTUATION_FRAME / (FALLBACK_TOTAL_FRAMES - 1)) * FALLBACK_SIMULATION_DURATION_SEC);
  const stabilizationSecond = backendFrames
    ? (backendFrames[stabilizationFrameIndex]?.t ?? Math.round((stabilizationFrameIndex / Math.max(totalFrames - 1, 1)) * totalSec))
    : Math.round((FALLBACK_STABILIZATION_FRAME / (FALLBACK_TOTAL_FRAMES - 1)) * FALLBACK_SIMULATION_DURATION_SEC);

  return {
    phase,
    frame,
    totalFrames,
    progress: Math.min(progress, 100),
    secondsElapsed,
    simulationDurationSec,
    predictionHorizonSec: PREDICTION_HORIZON_SEC,
    detectionSecond,
    decisionSecond,
    actuationSecond,
    stabilizationSecond,
    decisionTaken: frame >= decisionFrameIndex,
    decisionTraceIndex:
      frame >= decisionFrameIndex
        ? Math.max(0, HISTORY_LENGTH - 1 - (frame - decisionFrameIndex))
        : null,
    warning,
    live,
    before,
    after,
    activeScenario,
    selectedScenario,
    startSimulation,
    resetLive,
    togglePause,
    updatedAgo: Math.max(0, Math.floor((Date.now() - live.timestamp) / 1000)),
    dataSource: live.dataSource || getTelemetryMode(),
  };
}
