
import React from "react";
import {
  ArrowRight,
  BatteryCharging,
  Bolt,
  Check,
  Clock3,
  Factory,
  Gauge,
  Leaf,
  RotateCcw,
  ShieldCheck,
  TimerReset,
  X,
  Zap,
} from "lucide-react";
import { StatusBadge, cx } from "../components/ui";

function PriorityMetric({ icon: Icon, label, before, after, unit }) {
  return (
    <div className="decision-priority-metric">
      <Icon size={24} />
      <span>{label}</span>
      <strong><b>{before}</b><ArrowRight size={17} /><em>{after}</em><small>{unit}</small></strong>
    </div>
  );
}

function ActionLever({ icon: Icon, label, value, unit = "MW" }) {
  return (
    <div className="decision-action-lever">
      <Icon size={24} />
      <span>{label}</span>
      <strong>{value} <small>{unit}</small></strong>
    </div>
  );
}

export default function ActionsPage({ scenario, simulation, decision, setDecision, addAuditEvent }) {
  const activeScenario = simulation.phase === "live" ? scenario : simulation.activeScenario;
  const action = activeScenario.action;
  const after = simulation.phase === "live" ? activeScenario.after : simulation.after;
  const before = simulation.phase === "live" ? activeScenario.before : simulation.before;

  const decide = (next) => {
    setDecision(next);
    addAuditEvent({
      severity: next === "approved" ? "stable" : next === "rejected" ? "critical" : "warning",
      type: "Operator decision",
      event: next === "approved" ? `Corrective action approved: ${activeScenario.label}` : next === "rejected" ? `Corrective action rejected: ${activeScenario.label}` : `Recommendation reset: ${activeScenario.label}`,
      source: "Human-in-command interface",
    });
  };

  return (
    <>
      <section className="page-hero page-hero--compact">
        <div><p className="eyebrow">Operator decision layer</p><h1>Decision engine</h1></div>
        <StatusBadge severity={decision === "approved" ? "stable" : decision === "rejected" ? "critical" : "warning"}>
          {decision === "approved" ? "Approved" : decision === "rejected" ? "Rejected" : "Approval required"}
        </StatusBadge>
      </section>

      <section className={cx("decision-card decision-card--operator", decision === "approved" && "decision-card--approved", decision === "rejected" && "decision-card--rejected")}>
        <header className="decision-card__heading decision-card__heading--compact">
          <div><p className="eyebrow">Tiangou AI recommendation</p><h2>Approve reversible stabilisation actions.</h2></div>
          <StatusBadge severity="stable">Physics validated</StatusBadge>
        </header>

        <div className="decision-priority-grid">
          <PriorityMetric icon={Gauge} label="Predicted nadir" before={(before.predictedNadir ?? before.nadir).toFixed(2)} after={(after.predictedNadir ?? after.nadir).toFixed(2)} unit="Hz" />
          <PriorityMetric icon={ShieldCheck} label="Stability risk" before={`${before.stabilityRisk}%`} after={`${after.stabilityRisk}%`} unit="" />
          <PriorityMetric icon={Leaf} label="CO₂ output" before={before.co2Rate.toLocaleString()} after={after.co2Rate.toLocaleString()} unit="t/h" />
        </div>

        <div className="decision-action-grid decision-action-grid--operator">
          <ActionLever icon={BatteryCharging} label="Battery discharge" value={`+${action.battery}`} />
          <ActionLever icon={Factory} label="Sync reserve retained" value={`+${action.synchronousReserve}`} />
          <ActionLever icon={Zap} label="Demand response" value={action.demandResponse ? `−${action.demandResponse}` : "0"} />
          <ActionLever icon={Bolt} label="Flexible charging" value={`−${action.evReduction}`} />
        </div>

        <footer className="decision-card__footer decision-card__footer--operator">
          <div className="decision-timing-strip">
            <span><Clock3 size={15} />Warning +{simulation.detectionSecond}s</span>
            <span><Gauge size={15} />Decision +{simulation.decisionSecond}s</span>
            <span><TimerReset size={15} />Actuation +{simulation.actuationSecond}s</span>
            <span><ShieldCheck size={15} />Stable +{simulation.stabilizationSecond}s</span>
          </div>
          <div className="decision-footer-actions">
            <button className="ghost-btn" onClick={() => decide("pending")}><RotateCcw size={16} />Reset</button>
            <button className="danger-btn" onClick={() => decide("rejected")}><X size={16} />Reject</button>
            <button className="primary-btn" onClick={() => decide("approved")}><Check size={16} />Approve action</button>
          </div>
        </footer>
      </section>
    </>
  );
}
