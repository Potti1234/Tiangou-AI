import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  connectTelemetrySocket,
  fetchLatestTelemetry,
  getTelemetryMode,
  normalizeTelemetrySnapshot,
} from "../services/telemetryClient";

const LIVE_INTERVAL_MS = 1200;
const BUFFER_INTERVAL_MS = 720;
const SIMULATION_INTERVAL_MS = 560;
const HISTORY_LENGTH = 54;
const PREDICTION_POINTS = 20;
const PREDICTION_HORIZON_SEC = 20;
const BUFFER_FRAMES = 5;
const TOTAL_FRAMES = 60;
const DETECTION_FRAME = 6;
const DECISION_FRAME = 10;
const ACTUATION_FRAME = 12;
const STABILIZATION_FRAME = 36;
const SIMULATION_DURATION_SEC = 120;

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
const lerp = (start, end, progress) => start + (end - start) * progress;
const jitter = (range) => (Math.random() - 0.5) * range;
const round = (value, digits = 2) => Number(value.toFixed(digits));
const smoothstep = (value) => {
  const t = clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
};

function padTrace(values, length = HISTORY_LENGTH, fallback = 0) {
  const result = Array.isArray(values) ? [...values] : [];
  while (result.length < length) result.unshift(result[0] ?? fallback);
  return result.slice(-length);
}

function appendTrace(values, value, length = HISTORY_LENGTH) {
  return [...values.slice(-(length - 1)), round(value, 3)];
}

function interpolateArray(start, end, progress) {
  return start.map((value, index) => round(lerp(value, end[index] ?? value, progress), 1));
}

function traceValue(values, progress) {
  if (!values?.length) return 50;
  const clamped = clamp(progress, 0, 1);
  const scaled = clamped * (values.length - 1);
  const lower = Math.floor(scaled);
  const upper = Math.min(lower + 1, values.length - 1);
  return lerp(values[lower], values[upper], scaled - lower);
}

function buildFrequencyPrediction({
  current,
  rocof,
  nadir = current,
  settle = 50,
  inertia = 2.4,
  controlled = false,
}) {
  const effectiveNadir = controlled ? Math.max(49.56, nadir) : nadir;
  const inertiaFactor = clamp((2.45 - inertia) / 1.1, -0.35, 0.85);
  const descentTau = controlled ? 5.4 : 5.9 - inertiaFactor * 0.7;
  const recoveryDelay = controlled ? 2.0 : 7.5;
  const recoveryTau = controlled ? 5.8 : 13.5;
  const boundedRocof = clamp(rocof, -0.45, 0.22);

  return Array.from({ length: PREDICTION_POINTS + 1 }, (_, index) => {
    const seconds = index;
    const descent = (effectiveNadir - current) * (1 - Math.exp(-seconds / descentTau));
    const recoverySeconds = Math.max(0, seconds - recoveryDelay);
    const recovery = (settle - effectiveNadir) * (1 - Math.exp(-recoverySeconds / recoveryTau));
    const rocofImpulse = boundedRocof * Math.min(seconds, 3) * Math.exp(-seconds / 3.4) * 0.30;
    const projected = current + descent + recovery + rocofImpulse;
    return round(controlled ? Math.max(49.56, projected) : projected, 3);
  });
}

function buildStableTelemetry(stableScenario) {
  const base = stableScenario.before;
  const production = base.demand - base.gap;
  const frequencyTrace = padTrace(base.frequencyTrace, HISTORY_LENGTH, base.frequency);
  const inertiaTrace = padTrace(frequencyTrace.map((_, index) => round(base.inertia + Math.sin(index / 4) * 0.018, 3)), HISTORY_LENGTH, base.inertia);
  const demandTrace = padTrace(frequencyTrace.map((_, index) => round(base.demand + Math.sin(index / 5) * 35 + Math.cos(index / 8) * 18, 1)), HISTORY_LENGTH, base.demand);
  const productionTrace = padTrace(demandTrace.map((value, index) => round(value - 6 + Math.sin(index / 3) * 10, 1)), HISTORY_LENGTH, production);
  const frequencyPrediction = buildFrequencyPrediction({
    current: base.frequency,
    rocof: base.rocof,
    nadir: 49.96,
    settle: 50,
    inertia: base.inertia,
    controlled: true,
  });

  return {
    ...base,
    production,
    frequencyTrace,
    inertiaTrace,
    demandTrace,
    productionTrace,
    frequencyPrediction,
    timestamp: Date.now(),
    dataTimestamp: new Date().toISOString(),
    dataSource: getTelemetryMode(),
    status: "Stable",
  };
}

function applyLiveSnapshot(previous, stableScenario, snapshot) {
  const base = stableScenario.before;
  const normalized = snapshot ? normalizeTelemetrySnapshot(snapshot, previous) : previous;
  const frequency = snapshot ? normalized.frequency : clamp(previous.frequency + jitter(0.024) + (50 - previous.frequency) * 0.18, 49.96, 50.04);
  const inertia = snapshot ? normalized.inertia : clamp(previous.inertia + jitter(0.018) + (base.inertia - previous.inertia) * 0.14, 2.40, 2.57);
  const demand = snapshot ? normalized.demand : Math.round(clamp(previous.demand + jitter(32), base.demand - 95, base.demand + 110));
  const renewableShare = snapshot ? normalized.renewableShare : round(clamp(previous.renewableShare + jitter(0.9), 29, 34), 1);
  const co2Rate = snapshot ? normalized.co2Rate : Math.round(clamp(previous.co2Rate + jitter(18) - (renewableShare - previous.renewableShare) * 3, 1210, 1315));
  const rocof = snapshot ? normalized.rocof : round((frequency - previous.frequency) / (LIVE_INTERVAL_MS / 1000), 3);
  const gap = snapshot ? normalized.gap : Math.round(clamp(Math.abs(demand - base.demand) * 0.12 + jitter(5), 4, 28));
  const production = snapshot ? normalized.production : Math.round(demand - gap);
  const reserves = snapshot ? normalized.reserves : Math.round(clamp(previous.reserves + jitter(12), 330, 375));
  const stabilityRisk = snapshot ? normalized.stabilityRisk : Math.round(clamp(previous.stabilityRisk + jitter(2.2), 2, 7));
  const overloads = snapshot ? normalized.overloads : previous.overloads.map((value) => round(clamp(value + jitter(4), 34, 58), 1));
  const prediction = snapshot && normalized.frequencyPrediction?.length
    ? normalized.frequencyPrediction
    : buildFrequencyPrediction({
        current: frequency,
        rocof,
        nadir: stabilityRisk > 25 ? 49.72 : 49.96,
        settle: 50,
        inertia,
        controlled: true,
      });

  return {
    ...previous,
    ...normalized,
    frequency: round(frequency, 3),
    inertia: round(inertia, 3),
    rocof: round(rocof, 3),
    co2Rate,
    nadir: round(Math.min(...previous.frequencyTrace.slice(-8), frequency), 2),
    gap,
    reserves,
    stabilityRisk,
    thresholdBreach: Math.max(1, snapshot ? normalized.thresholdBreach : Math.round(stabilityRisk * 0.65)),
    demand,
    production,
    renewableShare,
    overloads,
    frequencyTrace: appendTrace(previous.frequencyTrace, frequency),
    inertiaTrace: appendTrace(previous.inertiaTrace, inertia),
    demandTrace: appendTrace(previous.demandTrace, demand),
    productionTrace: appendTrace(previous.productionTrace, production),
    frequencyPrediction: prediction,
    timestamp: Date.now(),
    dataTimestamp: normalized.dataTimestamp || new Date().toISOString(),
    dataSource: snapshot ? "database-api" : "mock-fallback",
    status: "Stable",
  };
}

function deriveScenarioFrame({ stable, scenario, frame, priorBefore, priorAfter }) {
  const progress = clamp(frame / (TOTAL_FRAMES - 1), 0, 1);
  const dropProgress = smoothstep(progress / 0.68);
  const recoveryProgress = smoothstep((progress - 0.68) / 0.32);
  const actionProgress = smoothstep((frame - ACTUATION_FRAME) / Math.max(STABILIZATION_FRAME - ACTUATION_FRAME, 1));

  const beforeTarget = scenario.before;
  const afterTarget = scenario.after;
  const lastConventionalFrequency = beforeTarget.frequencyTrace?.at(-1) ?? beforeTarget.frequency;
  const conventionalRecoveryTarget = Math.max(beforeTarget.nadir, lastConventionalFrequency);

  const conventionalAtNadir = lerp(stable.frequency, beforeTarget.nadir, dropProgress);
  const conventionalFrequency = round(
    lerp(conventionalAtNadir, conventionalRecoveryTarget, recoveryProgress * 0.42),
    3
  );

  const protectedFloor = Math.max(49.56, Math.min(afterTarget.nadir, afterTarget.frequency));
  const aiFrequency = frame < ACTUATION_FRAME
    ? conventionalFrequency
    : round(
        Math.max(
          protectedFloor,
          lerp(conventionalFrequency, Math.max(afterTarget.frequency, protectedFloor), actionProgress)
        ),
        3
      );

  const demandAmplitude =
    scenario.id === "dataCenter" ? 105 :
    scenario.id === "typhoon" ? 44 :
    scenario.id === "importDrop" ? 28 : 18;

  const demandBaseProgress = smoothstep(progress / 0.76);
  const demandWave = Math.sin(frame * 0.34) * 17 + Math.sin(frame * 0.11) * 9;
  const scenarioRamp = demandAmplitude * Math.sin(Math.PI * clamp(progress / 0.96, 0, 1));
  const demand = Math.round(
    lerp(stable.demand, beforeTarget.demand, demandBaseProgress) + demandWave + scenarioRamp
  );

  const conventionalGapPeak = lerp(stable.gap, beforeTarget.gap, dropProgress);
  const conventionalGap = Math.max(
    0,
    Math.round(conventionalGapPeak * (1 - 0.12 * recoveryProgress) + Math.abs(Math.sin(frame * 0.29)) * 11)
  );
  const aiGap = frame < ACTUATION_FRAME
    ? conventionalGap
    : Math.max(0, Math.round(lerp(conventionalGap, afterTarget.gap, actionProgress)));

  const conventionalProduction = demand - conventionalGap;
  const aiProduction = demand - aiGap;

  const conventionalInertia = round(lerp(stable.inertia, beforeTarget.inertia, dropProgress), 3);
  const aiInertia = frame < ACTUATION_FRAME
    ? conventionalInertia
    : round(Math.max(conventionalInertia, lerp(conventionalInertia, afterTarget.inertia, actionProgress)), 3);

  const conventionalRocof = round(
    lerp(stable.rocof, beforeTarget.rocof, dropProgress * (1 - 0.34 * recoveryProgress)),
    3
  );
  const aiRocof = frame < ACTUATION_FRAME
    ? conventionalRocof
    : round(lerp(conventionalRocof, afterTarget.rocof, actionProgress), 3);

  const conventionalRisk = Math.round(
    lerp(stable.stabilityRisk, beforeTarget.stabilityRisk, dropProgress * (1 - 0.10 * recoveryProgress))
  );
  const aiRisk = frame < ACTUATION_FRAME
    ? conventionalRisk
    : Math.min(conventionalRisk, Math.round(lerp(conventionalRisk, afterTarget.stabilityRisk, actionProgress)));

  const conventionalCo2 = Math.round(lerp(stable.co2Rate, beforeTarget.co2Rate, demandBaseProgress));
  const aiCo2 = frame < ACTUATION_FRAME
    ? conventionalCo2
    : Math.min(conventionalCo2, Math.round(lerp(conventionalCo2, afterTarget.co2Rate, actionProgress)));

  const conventionalReserves = Math.round(
    lerp(stable.reserves, beforeTarget.reserves, dropProgress * (1 - 0.10 * recoveryProgress))
  );
  const aiReserves = frame < ACTUATION_FRAME
    ? conventionalReserves
    : Math.max(conventionalReserves, Math.round(lerp(conventionalReserves, afterTarget.reserves, actionProgress)));

  const conventionalRenewableShare = round(
    lerp(stable.renewableShare, beforeTarget.renewableShare, demandBaseProgress),
    1
  );
  const aiRenewableShare = frame < ACTUATION_FRAME
    ? conventionalRenewableShare
    : round(Math.max(conventionalRenewableShare, lerp(conventionalRenewableShare, afterTarget.renewableShare, actionProgress)), 1);

  const predictedNadirConventional = round(
    Math.min(conventionalFrequency, beforeTarget.nadir + (1 - dropProgress) * 0.70),
    2
  );
  const predictedNadirAi = frame < DECISION_FRAME
    ? predictedNadirConventional
    : round(Math.max(protectedFloor, lerp(predictedNadirConventional, afterTarget.nadir, smoothstep((frame - DECISION_FRAME) / Math.max(STABILIZATION_FRAME - DECISION_FRAME, 1)))), 2);

  const conventionalOverloads = interpolateArray(stable.overloads, beforeTarget.overloads, dropProgress);
  const aiOverloads = frame < ACTUATION_FRAME
    ? conventionalOverloads
    : interpolateArray(conventionalOverloads, afterTarget.overloads, actionProgress);

  const before = {
    ...stable,
    ...beforeTarget,
    frequency: conventionalFrequency,
    inertia: conventionalInertia,
    rocof: conventionalRocof,
    co2Rate: conventionalCo2,
    nadir: predictedNadirConventional,
    predictedNadir: predictedNadirConventional,
    gap: conventionalGap,
    reserves: conventionalReserves,
    stabilityRisk: conventionalRisk,
    thresholdBreach: Math.round(lerp(stable.thresholdBreach, beforeTarget.thresholdBreach, dropProgress)),
    demand,
    production: conventionalProduction,
    synchronous: Math.round(lerp(stable.synchronous, beforeTarget.synchronous, dropProgress)),
    nonSynchronous: Math.round(lerp(stable.nonSynchronous, beforeTarget.nonSynchronous, demandBaseProgress)),
    imports: Math.round(lerp(stable.imports, beforeTarget.imports, demandBaseProgress)),
    renewableShare: conventionalRenewableShare,
    overloads: conventionalOverloads,
    frequencyTrace: appendTrace(priorBefore.frequencyTrace, conventionalFrequency),
    inertiaTrace: appendTrace(priorBefore.inertiaTrace, conventionalInertia),
    demandTrace: appendTrace(priorBefore.demandTrace, demand),
    productionTrace: appendTrace(priorBefore.productionTrace, conventionalProduction),
    frequencyPrediction: buildFrequencyPrediction({
      current: conventionalFrequency,
      rocof: conventionalRocof,
      nadir: beforeTarget.nadir,
      settle: conventionalRecoveryTarget,
      inertia: conventionalInertia,
      controlled: false,
    }),
    status: progress < 0.18 ? "Stable" : progress < 0.48 ? "Warning" : beforeTarget.status,
    timestamp: Date.now(),
    dataSource: "digital-twin",
  };

  const after = {
    ...stable,
    ...afterTarget,
    frequency: aiFrequency,
    inertia: aiInertia,
    rocof: aiRocof,
    co2Rate: aiCo2,
    nadir: predictedNadirAi,
    predictedNadir: predictedNadirAi,
    gap: aiGap,
    reserves: aiReserves,
    stabilityRisk: aiRisk,
    thresholdBreach: frame < ACTUATION_FRAME
      ? before.thresholdBreach
      : Math.min(before.thresholdBreach, Math.round(lerp(before.thresholdBreach, afterTarget.thresholdBreach, actionProgress))),
    demand,
    production: aiProduction,
    synchronous: frame < ACTUATION_FRAME
      ? before.synchronous
      : Math.round(Math.max(before.synchronous, lerp(before.synchronous, before.synchronous + (scenario.action?.synchronousReserve ?? 0), actionProgress))),
    nonSynchronous: frame < ACTUATION_FRAME
      ? before.nonSynchronous
      : Math.round(Math.max(before.nonSynchronous, lerp(before.nonSynchronous, before.nonSynchronous + 70, actionProgress))),
    imports: before.imports,
    renewableShare: aiRenewableShare,
    overloads: aiOverloads,
    co2Reduction: round(frame < ACTUATION_FRAME ? 0 : lerp(0, afterTarget.co2Reduction ?? 0, actionProgress), 1),
    renewableIncrease: round(frame < ACTUATION_FRAME ? 0 : lerp(0, afterTarget.renewableIncrease ?? 0, actionProgress), 1),
    savings: round(frame < ACTUATION_FRAME ? 0 : lerp(0, afterTarget.savings ?? 0, actionProgress), 2),
    frequencyTrace: appendTrace(priorAfter.frequencyTrace, aiFrequency),
    inertiaTrace: appendTrace(priorAfter.inertiaTrace, aiInertia),
    demandTrace: appendTrace(priorAfter.demandTrace, demand),
    productionTrace: appendTrace(priorAfter.productionTrace, aiProduction),
    frequencyPrediction: buildFrequencyPrediction({
      current: aiFrequency,
      rocof: aiRocof,
      nadir: protectedFloor,
      settle: Math.max(afterTarget.frequency, 49.86),
      inertia: aiInertia,
      controlled: true,
    }),
    status: frame < DECISION_FRAME ? before.status : frame < STABILIZATION_FRAME ? "Preventing" : afterTarget.status,
    timestamp: Date.now(),
    dataSource: "digital-twin",
  };

  return { before, after };
}

export default function useLiveSimulation({ scenarios, selectedScenario, onEvent }) {
  const stableScenario = scenarios.stable;
  const initialStable = useMemo(() => buildStableTelemetry(stableScenario), [stableScenario]);
  const [phase, setPhase] = useState("live");
  const [frame, setFrame] = useState(0);
  const [bufferFrame, setBufferFrame] = useState(0);
  const [stableSnapshot, setStableSnapshot] = useState(initialStable);
  const [live, setLive] = useState(initialStable);
  const [before, setBefore] = useState(initialStable);
  const [after, setAfter] = useState(initialStable);
  const [activeScenario, setActiveScenario] = useState(selectedScenario);
  const lastSocketSnapshot = useRef(null);
  const pairRef = useRef({ before: initialStable, after: initialStable });

  useEffect(() => {
    const disconnect = connectTelemetrySocket((snapshot) => {
      lastSocketSnapshot.current = snapshot;
    });

    return typeof disconnect === "function" ? disconnect : undefined;
  }, []);

  useEffect(() => {
    if (phase !== "live") return undefined;
    let cancelled = false;
    const update = async () => {
      let snapshot = lastSocketSnapshot.current;
      lastSocketSnapshot.current = null;
      if (!snapshot && getTelemetryMode() === "database-api") {
        try { snapshot = await fetchLatestTelemetry(); } catch { snapshot = null; }
      }
      if (!cancelled) setLive((current) => applyLiveSnapshot(current, stableScenario, snapshot));
    };
    update();
    const timer = window.setInterval(update, LIVE_INTERVAL_MS);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [phase, stableScenario]);

  useEffect(() => {
    if (phase !== "buffering") return undefined;
    const timer = window.setInterval(() => {
      setBufferFrame((currentFrame) => {
        const nextFrame = currentFrame + 1;
        setBefore((current) => {
          const next = applyLiveSnapshot(current, stableScenario, null);
          pairRef.current = { before: next, after: next };
          setAfter(next);
          setLive(next);
          return next;
        });
        if (nextFrame >= BUFFER_FRAMES) {
          setFrame(0);
          setPhase("running");
          onEvent?.({ severity: activeScenario.severity, type: "Disturbance injected", event: `Stable buffer complete. Disturbance begins: ${activeScenario.label}`, source: "Digital twin" });
          return BUFFER_FRAMES;
        }
        return nextFrame;
      });
    }, BUFFER_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [phase, stableScenario, activeScenario, onEvent]);

  useEffect(() => {
    if (phase !== "running") return undefined;
    const timer = window.setInterval(() => {
      setFrame((currentFrame) => Math.min(currentFrame + 1, TOTAL_FRAMES - 1));
    }, SIMULATION_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [phase]);

  useEffect(() => {
    if (phase !== "running") return;
    const next = deriveScenarioFrame({
      stable: stableSnapshot,
      scenario: activeScenario,
      frame,
      priorBefore: pairRef.current.before,
      priorAfter: pairRef.current.after,
    });
    pairRef.current = next;
    setBefore(next.before);
    setAfter(next.after);
    setLive(next.after);

    if (frame === DECISION_FRAME) onEvent?.({ severity: "warning", type: "AI decision", event: `PINN warning converted into a corrective recommendation: ${activeScenario.label}`, source: "Decision engine" });
    if (frame >= TOTAL_FRAMES - 1) {
      setPhase("complete");
      onEvent?.({ severity: "stable", type: "Simulation complete", event: `Extended physics-validated comparison completed: ${activeScenario.label}`, source: "Digital twin" });
    }
  }, [phase, frame, activeScenario, stableSnapshot, onEvent]);

  const startSimulation = useCallback((scenarioOverride) => {
    const scenario = scenarioOverride || selectedScenario;
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
    setPhase("buffering");
    onEvent?.({ severity: "stable", type: "Stable buffer started", event: `Scenario queued after stable-grid buffer: ${scenario.label}`, source: "Simulation controls" });
  }, [live, selectedScenario, onEvent]);

  const resetLive = useCallback(() => {
    const fresh = buildStableTelemetry(stableScenario);
    pairRef.current = { before: fresh, after: fresh };
    setLive(fresh);
    setBefore(fresh);
    setAfter(fresh);
    setStableSnapshot(fresh);
    setFrame(0);
    setBufferFrame(0);
    setPhase("live");
    onEvent?.({ severity: "stable", type: "Live monitoring", event: "Returned to stable live telemetry", source: "Simulation controls" });
  }, [stableScenario, onEvent]);

  const togglePause = useCallback(() => {
    setPhase((current) => {
      if (current === "running" || current === "buffering") return "paused";
      if (current === "paused") return frame === 0 ? "buffering" : "running";
      return current;
    });
  }, [frame]);

  const progress = phase === "live" ? 0 : phase === "buffering" ? Math.round((bufferFrame / BUFFER_FRAMES) * 10) : 10 + Math.round((frame / (TOTAL_FRAMES - 1)) * 90);
  const secondsElapsed = phase === "live" ? 0 : Math.round((frame / Math.max(TOTAL_FRAMES - 1, 1)) * SIMULATION_DURATION_SEC);
  const warningActive = phase === "running" && frame >= DETECTION_FRAME;
  const warning = warningActive ? {
    id: `${activeScenario.id}-warning`,
    severity: activeScenario.severity,
    popup: true,
    title: `${activeScenario.short}: preventive action required`,
    message: `PINN forecast identifies a ${activeScenario.before.nadir.toFixed(2)} Hz nadir risk within ${PREDICTION_HORIZON_SEC}s. Review the validated intervention.`,
  } : null;

  return {
    phase,
    frame,
    totalFrames: TOTAL_FRAMES,
    progress: Math.min(progress, 100),
    secondsElapsed,
    simulationDurationSec: SIMULATION_DURATION_SEC,
    predictionHorizonSec: PREDICTION_HORIZON_SEC,
    detectionSecond: Math.round((DETECTION_FRAME / (TOTAL_FRAMES - 1)) * SIMULATION_DURATION_SEC),
    decisionSecond: Math.round((DECISION_FRAME / (TOTAL_FRAMES - 1)) * SIMULATION_DURATION_SEC),
    actuationSecond: Math.round((ACTUATION_FRAME / (TOTAL_FRAMES - 1)) * SIMULATION_DURATION_SEC),
    stabilizationSecond: Math.round((STABILIZATION_FRAME / (TOTAL_FRAMES - 1)) * SIMULATION_DURATION_SEC),
    decisionTaken: frame >= DECISION_FRAME,
    decisionTraceIndex: frame >= DECISION_FRAME
      ? Math.max(0, HISTORY_LENGTH - 1 - (frame - DECISION_FRAME))
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
