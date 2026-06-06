
import React from "react";
import {
  CircleDollarSign,
  Clock3,
  Gauge,
  Leaf,
  RadioTower,
  ShieldCheck,
  TimerReset,
  TrendingDown,
  Wind,
} from "lucide-react";
import { SectionTitle, StatCard, StatusBadge } from "../components/ui";

export default function ImpactPage({ scenario, simulation }) {
  const liveMode = simulation.phase === "live";
  const before = liveMode ? simulation.live : simulation.before;
  const after = liveMode ? simulation.live : simulation.after;
  const avoided = Math.max(0, before.co2Rate - after.co2Rate);
  const riskReduction = Math.max(0, before.stabilityRisk - after.stabilityRisk);

  return (
    <>
      <section className="page-hero page-hero--compact">
        <div><p className="eyebrow">Outcome monitoring</p><h1>Impact</h1></div>
        <StatusBadge severity={liveMode ? "stable" : scenario.severity}>{liveMode ? "Live baseline" : "Validated response"}</StatusBadge>
      </section>

      <section className="impact-priority-grid">
        <StatCard label="Operational savings" value={liveMode ? "—" : `HK$${Number(after.savings ?? 0).toFixed(2)}`} unit={liveMode ? "" : "M"} icon={CircleDollarSign} tone="good" />
        <StatCard label="CO₂ emissions avoided" value={liveMode ? "—" : avoided.toLocaleString()} unit={liveMode ? "" : "t/h"} icon={Leaf} tone="good" />
        <StatCard label="Stability-risk reduction" value={liveMode ? "—" : `−${riskReduction}`} unit={liveMode ? "" : "pp"} icon={ShieldCheck} tone="good" />
        <StatCard label="Renewable share" value={`${Number(after.renewableShare).toFixed(1)}`} unit="%" icon={Wind} tone="good" />
      </section>

      <section className="panel-card impact-reaction-panel">
        <SectionTitle eyebrow="System reaction" title="Prediction and actuation speed" />
        <div className="impact-reaction-grid">
          <div><RadioTower size={23} /><span>PINN horizon</span><strong>+{simulation.predictionHorizonSec}s</strong></div>
          <div><Clock3 size={23} /><span>Issue detected</span><strong>{liveMode ? "—" : `+${simulation.detectionSecond}s`}</strong></div>
          <div><Gauge size={23} /><span>AI decision</span><strong>{liveMode ? "—" : `+${simulation.decisionSecond}s`}</strong></div>
          <div><TimerReset size={23} /><span>Actuation delay</span><strong>{liveMode ? "—" : `${Math.max(0, simulation.actuationSecond-simulation.decisionSecond)}s`}</strong></div>
          <div><TrendingDown size={23} /><span>Stable envelope</span><strong>{liveMode ? "—" : `+${simulation.stabilizationSecond}s`}</strong></div>
        </div>
      </section>

      <section className="panel-card">
        <SectionTitle eyebrow="Validated comparison" title="Conventional response versus Tiangou AI" />
        <div className="comparison-table-wrap">
          <table className="comparison-table">
            <thead><tr><th>KPI</th><th>Conventional</th><th>Tiangou AI</th><th>Improvement</th></tr></thead>
            <tbody>
              <tr><td>Predicted frequency nadir</td><td>{(before.predictedNadir ?? before.nadir).toFixed(2)} Hz</td><td>{(after.predictedNadir ?? after.nadir).toFixed(2)} Hz</td><td className="good-cell">+{((after.predictedNadir ?? after.nadir)-(before.predictedNadir ?? before.nadir)).toFixed(2)} Hz</td></tr>
              <tr><td>Stability risk</td><td>{before.stabilityRisk}%</td><td>{after.stabilityRisk}%</td><td className="good-cell">−{riskReduction} pp</td></tr>
              <tr><td>Demand-generation gap</td><td>{before.gap} MW</td><td>{after.gap} MW</td><td className="good-cell">−{Math.max(0,before.gap-after.gap)} MW</td></tr>
              <tr><td>CO₂ output</td><td>{before.co2Rate.toLocaleString()} t/h</td><td>{after.co2Rate.toLocaleString()} t/h</td><td className="good-cell">−{avoided.toLocaleString()} t/h</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
