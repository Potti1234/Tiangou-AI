import React from "react";
import { Activity, AlertTriangle, Clock3, Gauge, ShieldCheck, TrendingDown, Zap } from "lucide-react";
import GridInfrastructureMap from "../components/GridInfrastructureMap";
import { ComparisonFrequencyChart, LiveTelemetryChart, SectionTitle, StatCard, StatusBadge } from "../components/ui";

export default function StabilityPage({ scenario, navigate, simulation }) {
  const liveMode = simulation.phase === "live";
  const before = liveMode ? simulation.live : simulation.before;
  const after = liveMode ? simulation.live : simulation.after;
  const activeScenario = liveMode ? scenario : simulation.activeScenario;
  const margin = ((before.inertia - before.criticalInertia) / before.criticalInertia) * 100;
  const afterMargin = ((after.inertia - after.criticalInertia) / after.criticalInertia) * 100;

  return <>
    <section className="page-hero page-hero--compact"><div><p className="eyebrow">Physical state · PINN decision layer</p><h1>Grid stability</h1><p>Track observed telemetry, the 20-second PINN frequency forecast and the detailed public-infrastructure reference map.</p></div><StatusBadge severity={liveMode ? "stable" : activeScenario.severity}>{liveMode ? "Live monitoring" : activeScenario.label}</StatusBadge></section>

    <div className="metric-grid metric-grid--4">
      <StatCard label="Equivalent inertia" value={before.inertia.toFixed(3)} unit="s" icon={Gauge} tone={margin < 0 ? "critical" : margin < 10 ? "warning" : "good"} footnote={`Configured threshold: ${before.criticalInertia.toFixed(2)} s`} />
      <StatCard label="Inertia margin" value={`${margin > 0 ? "+" : ""}${margin.toFixed(1)}`} unit="%" icon={ShieldCheck} tone={margin < 0 ? "critical" : margin < 10 ? "warning" : "good"} footnote={liveMode ? "Continuously estimated" : `With prevention: +${afterMargin.toFixed(1)}%`} />
      <StatCard label="Current RoCoF" value={before.rocof.toFixed(3)} unit="Hz/s" icon={TrendingDown} tone={Math.abs(before.rocof) > 0.3 ? "critical" : Math.abs(before.rocof) > 0.15 ? "warning" : "good"} footnote={liveMode ? "Live rate of change" : `Tiangou AI: ${after.rocof.toFixed(3)} Hz/s`} />
      <StatCard label="PINN forecast horizon" value={`+${simulation.predictionHorizonSec}`} unit="s" icon={Activity} tone="good" footnote="Forward frequency trajectory shown on the chart" />
    </div>

    <section className="stability-main-grid">
      <div className="stability-chart-panel">
        {liveMode ? <LiveTelemetryChart frequencyValues={before.frequencyTrace} inertiaValues={before.inertiaTrace} demandValues={before.demandTrace} productionValues={before.productionTrace} demandCurrent={before.demand} productionCurrent={before.production} predictionValues={before.frequencyPrediction} predictionHorizonSec={simulation.predictionHorizonSec} /> : <ComparisonFrequencyChart before={before.frequencyTrace} after={after.frequencyTrace} beforePrediction={before.frequencyPrediction} afterPrediction={after.frequencyPrediction} beforeCurrent={before.frequency} afterCurrent={after.frequency} progress={simulation.progress} decisionIndex={Math.max(0, after.frequencyTrace.length - Math.max(0, simulation.frame - 15) - 1)} decisionTaken={simulation.decisionTaken} predictionHorizonSec={simulation.predictionHorizonSec} />}
      </div>
      <aside className="side-panel stability-risk-panel">
        <SectionTitle eyebrow={liveMode ? "Continuous estimation" : "Early warning"} title={liveMode ? "Live status" : "Risk interpretation"} />
        <div className={liveMode ? "risk-score risk-score--stable" : "risk-score"}><span>Stability-risk score</span><strong>{before.stabilityRisk}%</strong><small>{liveMode ? "Stable operating envelope" : `With prevention: ${after.stabilityRisk}%`}</small></div>
        <div className="side-panel__list">
          <div><Clock3 size={18} /><span>{liveMode ? "Forecast horizon" : "Issue detected"}</span><strong>{liveMode ? `+${simulation.predictionHorizonSec}s` : `+${simulation.detectionSecond}s`}</strong></div>
          <div><AlertTriangle size={18} /><span>Threshold-breach probability</span><strong>{before.thresholdBreach}%</strong></div>
          <div><Zap size={18} /><span>Demand-generation gap</span><strong>{before.gap} MW</strong></div>
          <div><ShieldCheck size={18} /><span>Model confidence</span><strong>{activeScenario.confidence}%</strong></div>
        </div>
        <button className="primary-btn" onClick={() => navigate(liveMode ? "scenarios" : "actions")}>{liveMode ? "Open scenario library" : "Review corrective action"}</button>
      </aside>
    </section>

    <GridInfrastructureMap title="Hong Kong grid infrastructure" />
  </>;
}
