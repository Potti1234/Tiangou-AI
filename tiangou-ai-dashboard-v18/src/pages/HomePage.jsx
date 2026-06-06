
import React from "react";
import {
  Activity,
  ArrowRight,
  BellRing,
  BrainCircuit,
  CircleDollarSign,
  CloudSun,
  Gauge,
  Leaf,
  MapPinned,
  Network,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";

const modules = [
  {
    icon: Activity,
    title: "Live overview",
    text: "Monitor frequency, equivalent inertia, RoCoF, demand, production, reserves and forward frequency prediction in one operator screen.",
    target: "overview",
  },
  {
    icon: Gauge,
    title: "Grid stability",
    text: "Inspect the physical operating envelope, the PINN forecast and the grid-response trajectory during disturbances.",
    target: "stability",
  },
  {
    icon: Network,
    title: "Resource mix",
    text: "Separate synchronous generation, inverter-based generation, imports and flexibility resources. Add weather-driven renewable-risk monitoring.",
    target: "resources",
  },
  {
    icon: Leaf,
    title: "Impact",
    text: "Prioritise operational savings, emissions avoided, stability-risk reduction and renewable utilisation.",
    target: "impact",
  },
  {
    icon: SlidersHorizontal,
    title: "Decision engine",
    text: "Convert the physics-informed forecast into a concise, operator-approved preventive action.",
    target: "actions",
  },
  {
    icon: MapPinned,
    title: "Interactive infrastructure map",
    text: "Explore public grid infrastructure on a responsive MapLibre map with filters for utility owner, voltage and asset class.",
    target: "overview",
  },
];

const workflow = [
  ["01", "Ingest", "Live telemetry and public context"],
  ["02", "Predict", "PINN frequency trajectory"],
  ["03", "Warn", "Operator notification before breach"],
  ["04", "Optimise", "Validated preventive action"],
  ["05", "Approve", "Human-in-command execution"],
];

export default function HomePage({ navigate }) {
  return (
    <div className="home-page">
      <section className="home-hero">
        <div>
          <p className="eyebrow">Hong Kong grid-stability decision support</p>
          <h1>Predict instability.<br />Act before the outage.</h1>
          <p>
            Tiangou AI combines live grid telemetry, physics-informed forecasting and operator-approved preventive dispatch in a single professional interface.
          </p>
          <div className="home-hero__actions">
            <button className="primary-btn" onClick={() => navigate("overview")}>Open live overview <ArrowRight size={17} /></button>
            <button className="ghost-btn" onClick={() => navigate("scenarios")}>Explore scenarios</button>
          </div>
        </div>
        <div className="home-hero__signal">
          <div><BrainCircuit size={34} /><span>PINN forecast</span><strong>+20 s</strong></div>
          <div><BellRing size={34} /><span>Early warning</span><strong>Operator alert</strong></div>
          <div><ShieldCheck size={34} /><span>Control mode</span><strong>Human-in-command</strong></div>
        </div>
      </section>

      <section className="home-workflow">
        {workflow.map(([number, title, text]) => (
          <article key={number}>
            <span>{number}</span>
            <h3>{title}</h3>
            <p>{text}</p>
          </article>
        ))}
      </section>

      <section className="home-section-heading">
        <p className="eyebrow">Platform modules</p>
        <h2>Everything the operator needs, without unnecessary noise.</h2>
      </section>

      <section className="home-module-grid">
        {modules.map(({ icon: Icon, title, text, target }) => (
          <button key={title} className="home-module-card" onClick={() => navigate(target)}>
            <span className="home-module-card__icon"><Icon size={25} /></span>
            <h3>{title}</h3>
            <p>{text}</p>
            <span className="home-module-card__link">Open module <ArrowRight size={15} /></span>
          </button>
        ))}
      </section>

      <section className="home-principles">
        <article><CloudSun size={23} /><div><h3>Context-aware</h3><p>Weather and renewable-disruption intelligence complements the physical grid state.</p></div></article>
        <article><CircleDollarSign size={23} /><div><h3>Value-oriented</h3><p>Economic, environmental and stability outcomes remain visible to the operator.</p></div></article>
        <article><ShieldCheck size={23} /><div><h3>Advisory by design</h3><p>The AI recommends. The operator retains authority over execution.</p></div></article>
      </section>
    </div>
  );
}
