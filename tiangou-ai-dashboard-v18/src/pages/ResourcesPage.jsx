
import React from "react";
import {
  BatteryCharging,
  Bolt,
  Building2,
  Factory,
  Network,
  Wind,
} from "lucide-react";
import { SectionTitle, StatusBadge, ValueBar } from "../components/ui";
import WeatherClimateSection from "../components/WeatherClimateSection";
import GridInfrastructureMap from "../components/GridInfrastructureMap";

function ResourceMixDonut({ synchronous, nonSynchronous, imports }) {
  const total = synchronous + nonSynchronous + imports;
  const radius = 78;
  const circumference = 2 * Math.PI * radius;

  const categories = [
    {
      id: "synchronous",
      label: "Synchronous generation",
      note: "Rotating assets",
      value: synchronous,
      className: "resource-donut__segment--sync",
    },
    {
      id: "inverter",
      label: "Inverter-based generation",
      note: "Solar, wind and other non-synchronous sources",
      value: nonSynchronous,
      className: "resource-donut__segment--inverter",
    },
    {
      id: "imports",
      label: "Cross-boundary imports",
      note: "Imported electricity",
      value: imports,
      className: "resource-donut__segment--imports",
    },
  ].map((item) => ({
    ...item,
    share: total > 0 ? (item.value / total) * 100 : 0,
  }));

  let cumulativeShare = 0;

  return (
    <section className="panel-card resource-mix-chart-card">
      <SectionTitle
        eyebrow="Generation portfolio"
        title="Contribution to total available supply"
        note="The chart updates automatically with the live portfolio and with the validated scenario response."
      />

      <div className="resource-mix-chart-layout">
        <div className="resource-donut-wrap" aria-label="Resource mix donut chart">
          <svg className="resource-donut" viewBox="0 0 220 220" role="img" aria-label="Resource mix shares">
            <circle className="resource-donut__track" cx="110" cy="110" r={radius} />
            {categories.map((item) => {
              const dash = (item.share / 100) * circumference;
              const offset = -((cumulativeShare / 100) * circumference);
              cumulativeShare += item.share;
              return (
                <circle
                  key={item.id}
                  className={`resource-donut__segment ${item.className}`}
                  cx="110"
                  cy="110"
                  r={radius}
                  strokeDasharray={`${dash} ${circumference - dash}`}
                  strokeDashoffset={offset}
                />
              );
            })}
          </svg>

          <div className="resource-donut__center">
            <small>Total supply</small>
            <strong>{total.toLocaleString()}</strong>
            <span>MW</span>
          </div>
        </div>

        <div className="resource-donut-legend">
          {categories.map((item) => (
            <article className="resource-donut-legend__item" key={item.id}>
              <i className={`resource-donut-legend__marker ${item.className}`} />
              <div>
                <h3>{item.label}</h3>
                <p>{item.note}</p>
              </div>
              <div className="resource-donut-legend__value">
                <strong>{item.value.toLocaleString()} MW</strong>
                <span>{item.share.toFixed(1)}%</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function ResourcesPage({ scenario, simulation }) {
  const b = simulation.phase === "live" ? simulation.live : simulation.after;
  const total = b.synchronous + b.nonSynchronous + b.imports;
  const syncShare = Math.round((b.synchronous / total) * 100);
  const inverterShare = Math.round((b.nonSynchronous / total) * 100);
  const importShare = 100 - syncShare - inverterShare;

  return (
    <>
      <section className="page-hero page-hero--compact">
        <div>
          <p className="eyebrow">Portfolio monitoring</p>
          <h1>Resource mix</h1>
          <p>Track synchronous resources, non-synchronous generation, cross-boundary imports and flexible demand separately.</p>
        </div>
        <StatusBadge severity={simulation.phase === "live" ? "stable" : scenario.severity}>{simulation.phase === "live" ? "Live portfolio" : scenario.label}</StatusBadge>
      </section>

      <section className="resource-summary-grid">
        <article className="large-info-card">
          <SectionTitle eyebrow="Synchronous resources" title="Rotating inertia online" note="Assets physically coupled to the system contribute inherent inertia." />
          <strong className="large-info-card__metric">{b.synchronous.toLocaleString()} <small>MW</small></strong>
          <ValueBar label="Synchronous generation online" value={b.synchronous} max={5000} unit="MW" tone={syncShare < 55 ? "warning" : "good"} icon={<Factory size={16} />} />
          <p>Share of monitored portfolio: <b>{syncShare}%</b></p>
        </article>
        <article className="large-info-card">
          <SectionTitle eyebrow="Non-synchronous resources" title="Inverter-based generation" note="Solar, wind and batteries are tracked separately from inherent rotating inertia." />
          <strong className="large-info-card__metric">{b.nonSynchronous.toLocaleString()} <small>MW</small></strong>
          <ValueBar label="Non-synchronous generation online" value={b.nonSynchronous} max={2600} unit="MW" tone="neutral" icon={<Wind size={16} />} />
          <p>Share of monitored portfolio: <b>{inverterShare}%</b></p>
        </article>
        <article className="large-info-card">
          <SectionTitle eyebrow="Cross-boundary interface" title="Electricity imports" note="The contribution depends on the physical interconnection and operating conditions." />
          <strong className="large-info-card__metric">{b.imports.toLocaleString()} <small>MW</small></strong>
          <ValueBar label="Imported electricity" value={b.imports} max={1200} unit="MW" tone="neutral" icon={<Network size={16} />} />
          <p>Share of monitored portfolio: <b>{importShare}%</b></p>
        </article>
      </section>

      <ResourceMixDonut
        synchronous={b.synchronous}
        nonSynchronous={b.nonSynchronous}
        imports={b.imports}
      />


      <GridInfrastructureMap resourcesOnly title="Resource-location map" />

            <WeatherClimateSection />

      <section className="panel-card">
        <SectionTitle eyebrow="Fast flexibility" title="Resources available to the decision engine" note="These resources can rebalance the grid without treating every asset as a physical inertia source." />
        <div className="flexibility-grid">
          <ValueBar label="Battery flexibility available" value={b.batteryFlex} max={250} unit="MW" tone="good" icon={<BatteryCharging size={16} />} />
          <ValueBar label="Flexible EV-charging demand" value={b.evFlex} max={180} unit="MW" tone="good" icon={<Bolt size={16} />} />
          <ValueBar label="Contracted flexible demand" value={b.flexibleDemand} max={250} unit="MW" tone="good" icon={<Building2 size={16} />} />
          <ValueBar label="Fast-response reserve" value={b.reserves} max={450} unit="MW" tone={b.reserves < 250 ? "warning" : "good"} icon={<Factory size={16} />} />
        </div>
      </section>

      <section className="classification-table">
        <SectionTitle eyebrow="Asset classification" title="Do not treat every MW as equivalent" />
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Resource</th><th>Typical assets</th><th>Physical contribution</th><th>Decision-engine role</th></tr>
            </thead>
            <tbody>
              <tr><td>Synchronous generation</td><td>Gas, hydro, coal, nuclear</td><td>Inherent rotating inertia</td><td>Reserve retention and dispatch</td></tr>
              <tr><td>Inverter-based generation</td><td>Solar PV, most wind farms</td><td>No inherent synchronous inertia by default</td><td>Available clean generation and curtailment avoidance</td></tr>
              <tr><td>Battery storage</td><td>Grid-scale and distributed BESS</td><td>Fast active-power response; capability depends on converter controls</td><td>Fast-frequency support and redispatch</td></tr>
              <tr><td>Flexible demand</td><td>EV charging, selected data-center and industrial loads</td><td>Demand reduction or shifting</td><td>Reversible load management</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
