import React from "react";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock3,
  CloudLightning,
  Factory,
  Network,
  Server,
} from "lucide-react";
import { SectionTitle, StatusBadge, cx } from "../components/ui";
import { scenarioOrder } from "../data/scenarios";

const scenarioIcons = {
  generatorTrip: Factory,
  dataCenter: Server,
  importDrop: Network,
  typhoon: CloudLightning,
  stable: CheckCircle2,
};

export default function ScenariosPage({ scenario, scenarios, runScenario, navigate, simulation }) {
  const run = (key) => {
    runScenario(key);
  };

  return (
    <>
      <section className="page-hero page-hero--compact">
        <div>
          <p className="eyebrow">Digital-twin stress testing</p>
          <h1>Scenarios</h1>
          <p>Activate a scenario and compare the unmitigated outcome against the physics-validated response.</p>
        </div>
        <StatusBadge severity={simulation.phase === "live" ? "stable" : scenario.severity}>{simulation.phase === "live" ? "Live monitoring" : `Active: ${scenario.short}`}</StatusBadge>
      </section>

      <section className="scenario-grid">
        {scenarioOrder.map((key) => {
          const item = scenarios[key];
          const Icon = scenarioIcons[key] || Activity;
          return (
            <article key={key} className={cx("scenario-card", scenario.id === key && "scenario-card--active")}>
              <div className="scenario-card__top">
                <div className="scenario-card__icon"><Icon size={19} /></div>
                <StatusBadge severity={item.severity}>{item.severity}</StatusBadge>
              </div>
              <h2>{item.label}</h2>
              <p>{item.description}</p>
              <div className="scenario-card__metrics">
                <span><Clock3 size={14} />Time to breach: <strong>{item.countdown}</strong></span>
                <span><Activity size={14} />Risk score: <strong>{item.before.stabilityRisk}%</strong></span>
              </div>
              <button className="scenario-card__button" onClick={() => run(key)}>
                {scenario.id === key && simulation.phase !== "live" ? "Replay simulation" : "Run simulation"}<ArrowRight size={15} />
              </button>
            </article>
          );
        })}
      </section>
    </>
  );
}
