import React from "react";
import {
  ArrowRight,
  CheckCircle2,
  Database,
  GitBranch,
  LockKeyhole,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  UserCheck,
  Zap,
} from "lucide-react";
import { SectionTitle, StatusBadge } from "../components/ui";

const checks = [
  ["Human approval required for material dispatch", "Active", UserCheck],
  ["Physics-based validation before execution", "Passed", ShieldCheck],
  ["Data-quality checks and provenance", "Passed", Database],
  ["Audit trail and model versioning", "Active", GitBranch],
  ["Cybersecurity interface", "Read-only", LockKeyhole],
  ["Manual override", "Available", RotateCcw],
];

export default function ReadinessPage({ scenario }) {
  return (
    <>
      <section className="page-hero page-hero--compact">
        <div>
          <p className="eyebrow">Regulatory and operational readiness</p>
          <h1>Human-in-command architecture</h1>
          <p>Tiangou AI recommends and validates corrective actions. The utility operator retains operational authority.</p>
        </div>
        <StatusBadge severity="stable">Advisory mode</StatusBadge>
      </section>

      <section className="panel-card">
        <SectionTitle eyebrow="Control path" title="Bounded automation by design" note="The initial deployment remains read-only and advisory. Selected reversible actions may be automated later within utility-approved envelopes." />
        <div className="architecture-chain">
          <span><Database size={16} />Telemetry</span><ArrowRight size={17} />
          <span><SlidersHorizontal size={16} />PINN analysis</span><ArrowRight size={17} />
          <span><ShieldCheck size={16} />Physics validation</span><ArrowRight size={17} />
          <span><UserCheck size={16} />Operator approval</span><ArrowRight size={17} />
          <span><Zap size={16} />Utility execution</span>
        </div>
      </section>

      <section className="readiness-grid">
        {checks.map(([label, value, Icon]) => (
          <article className="readiness-card" key={label}>
            <div className="readiness-card__icon"><Icon size={19} /></div>
            <div><h3>{label}</h3><strong><CheckCircle2 size={15} />{value}</strong></div>
          </article>
        ))}
      </section>

      <section className="control-level-grid">
        <article className="control-level-card control-level-card--active">
          <small>Level 1 · MVP</small>
          <h3>Advisory mode</h3>
          <p>AI estimates risk, recommends an action and waits for operator approval before material dispatch changes.</p>
        </article>
        <article className="control-level-card">
          <small>Level 2 · Future deployment</small>
          <h3>Guarded automation</h3>
          <p>Pre-authorised low-risk reversible actions execute automatically within utility-approved operating limits.</p>
        </article>
        <article className="control-level-card">
          <small>Level 3 · Existing protection layer</small>
          <h3>Emergency response</h3>
          <p>Certified protection systems execute deterministic time-critical actions. Tiangou AI does not replace them.</p>
        </article>
      </section>

      <section className="info-card info-card--full">
        <p className="eyebrow">Deployment principle</p>
        <h3>Keep the AI outside the protection boundary</h3>
        <p>
          The first version receives telemetry, produces a traceable recommendation and records operator decisions.
          It should not connect directly to field devices. This protects accountability, cybersecurity and operational
          acceptance while preserving a credible path toward bounded automation.
        </p>
      </section>
    </>
  );
}
