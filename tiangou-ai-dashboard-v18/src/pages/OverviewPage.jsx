
import React from "react";
import {
  Activity,
  ArrowRight,
  BatteryCharging,
  CircleDollarSign,
  Gauge,
  Leaf,
  Network,
  Pause,
  Play,
  RefreshCcw,
  ShieldCheck,
  Wind,
  Zap,
} from "lucide-react";
import {
  ComparisonFrequencyChart,
  LiveTelemetryChart,
  StatusBadge,
  cx,
} from "../components/ui";

function conditionTone(type, value) {
  if (type === "frequency") return value < 49.5 ? "critical" : value < 49.8 ? "warning" : "good";
  if (type === "inertia") return value < 2.0 ? "critical" : value < 2.2 ? "warning" : "good";
  if (type === "rocof") return Math.abs(value) > 0.3 ? "critical" : Math.abs(value) > 0.15 ? "warning" : "good";
  if (type === "reserve") return value < 250 ? "critical" : value < 310 ? "warning" : "good";
  if (type === "risk") return value > 55 ? "critical" : value > 25 ? "warning" : "good";
  if (type === "co2") return value > 1650 ? "critical" : value > 1400 ? "warning" : "good";
  if (type === "gap") return value > 450 ? "critical" : value > 100 ? "warning" : "good";
  return "good";
}

function LiveMetric({ label, value, unit, icon: Icon, tone = "good" }) {
  return (
    <div className={cx("live-metric live-metric--vertical", `live-metric--${tone}`)}>
      <div className="live-metric__icon-wrap"><Icon size={24} /></div>
      <div className="live-metric__body">
        <span>{label}</span>
        <div className="live-metric__reading"><strong>{value}</strong><small>{unit}</small></div>
      </div>
    </div>
  );
}

function ComparisonMetric({ label, type, conventional, ai, unit, icon: Icon, formatter = (value) => value, aiValidated = false }) {
  const conventionalTone = conditionTone(type, conventional);
  const aiTone = aiValidated ? "good" : conditionTone(type, ai);
  const delta = ai - conventional;
  const isHigherBetter = ["frequency", "inertia", "reserve"].includes(type);
  const deltaGood = isHigherBetter ? delta >= 0 : delta <= 0;

  return (
    <div className="comparison-metric">
      <div className={cx("comparison-metric__icon", `comparison-metric__icon--${aiTone}`)}><Icon size={21} /></div>
      <div className="comparison-metric__content">
        <div className="comparison-metric__heading">
          <h4>{label}</h4>
          <span className={cx("comparison-metric__delta", deltaGood ? "is-good" : "is-bad")}>
            Δ {delta > 0 ? "+" : ""}{formatter(delta)} {unit}
          </span>
        </div>
        <div className="comparison-metric__values">
          <span>Conventional<strong className={`value-tone value-tone--${conventionalTone}`}>{formatter(conventional)} <small>{unit}</small></strong></span>
          <span>Tiangou AI<strong className={`value-tone value-tone--${aiTone}`}>{formatter(ai)} <small>{unit}</small></strong></span>
        </div>
      </div>
    </div>
  );
}

function KpiColumn({ live, before, after, isLive, aiValidated = false }) {
  if (isLive) {
    return (
      <aside className="live-kpi-column" aria-label="Live grid KPIs">
        <div className="live-kpi-column__heading"><p className="eyebrow">Live state</p><h3>Key parameters</h3></div>
        <LiveMetric label="Frequency" value={live.frequency.toFixed(3)} unit="Hz" icon={Activity} tone={conditionTone("frequency", live.frequency)} />
        <LiveMetric label="Equivalent inertia" value={live.inertia.toFixed(3)} unit="s" icon={Gauge} tone={conditionTone("inertia", live.inertia)} />
        <LiveMetric label="RoCoF" value={live.rocof.toFixed(3)} unit="Hz/s" icon={Zap} tone={conditionTone("rocof", live.rocof)} />
        <LiveMetric label="Demand" value={live.demand.toLocaleString()} unit="MW" icon={Network} />
        <LiveMetric label="Production" value={live.production.toLocaleString()} unit="MW" icon={Wind} />
        <LiveMetric label="Fast reserve" value={live.reserves.toLocaleString()} unit="MW" icon={BatteryCharging} tone={conditionTone("reserve", live.reserves)} />
        <LiveMetric label="Stability risk" value={live.stabilityRisk} unit="%" icon={ShieldCheck} tone={conditionTone("risk", live.stabilityRisk)} />
      </aside>
    );
  }

  return (
    <aside className="live-kpi-column comparison-kpi-column" aria-label="Scenario KPI comparison">
      <div className="live-kpi-column__heading"><p className="eyebrow">Simulation</p><h3>Conventional vs Tiangou AI</h3></div>
      <ComparisonMetric aiValidated={aiValidated} label="Frequency" type="frequency" conventional={before.frequency} ai={after.frequency} unit="Hz" icon={Activity} formatter={(value) => Number(value).toFixed(2)} />
      <ComparisonMetric aiValidated={aiValidated} label="Inertia" type="inertia" conventional={before.inertia} ai={after.inertia} unit="s" icon={Gauge} formatter={(value) => Number(value).toFixed(2)} />
      <ComparisonMetric aiValidated={aiValidated} label="RoCoF" type="rocof" conventional={before.rocof} ai={after.rocof} unit="Hz/s" icon={Zap} formatter={(value) => Number(value).toFixed(3)} />
      <ComparisonMetric aiValidated={aiValidated} label="CO₂ output" type="co2" conventional={before.co2Rate} ai={after.co2Rate} unit="t/h" icon={Leaf} formatter={(value) => Math.round(value).toLocaleString()} />
      <ComparisonMetric aiValidated={aiValidated} label="Demand-generation gap" type="gap" conventional={before.gap} ai={after.gap} unit="MW" icon={Network} formatter={(value) => Math.round(value).toLocaleString()} />
      <ComparisonMetric aiValidated={aiValidated} label="Fast reserve" type="reserve" conventional={before.reserves} ai={after.reserves} unit="MW" icon={BatteryCharging} formatter={(value) => Math.round(value).toLocaleString()} />
      <ComparisonMetric aiValidated={aiValidated} label="Stability risk" type="risk" conventional={before.stabilityRisk} ai={after.stabilityRisk} unit="%" icon={ShieldCheck} formatter={(value) => Math.round(value)} />
    </aside>
  );
}

function SimulationControls({ scenarioKey, setScenarioKey, runScenario, simulation, scenarios }) {
  const options = Object.entries(scenarios).filter(([key]) => key !== "stable");
  const label = simulation.phase === "live" ? "Stable live operation" : simulation.phase === "buffering" ? "Stable buffer" : simulation.phase === "running" ? "Scenario running" : simulation.phase === "paused" ? "Paused" : "Validation complete";
  return (
    <section className="simulation-controls overview-simulation-controls">
      <span className={cx("simulation-state", `simulation-state--${simulation.phase}`)}><i />{label}</span>
      <div className="simulation-controls__actions">
        <select value={scenarioKey} onChange={(event) => setScenarioKey(event.target.value)} aria-label="Select scenario">
          {options.map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}
        </select>
        {(simulation.phase === "running" || simulation.phase === "paused" || simulation.phase === "buffering") ? <button className="ghost-btn" onClick={simulation.togglePause}>{simulation.phase === "paused" ? <Play size={16} /> : <Pause size={16} />}{simulation.phase === "paused" ? "Resume" : "Pause"}</button> : null}
        {simulation.phase !== "live" ? <button className="ghost-btn" onClick={simulation.resetLive}><RefreshCcw size={16} />Reset live</button> : null}
        <button className="primary-btn" onClick={() => runScenario(scenarioKey)}><Play size={16} />{simulation.phase === "live" ? "Simulate" : "Replay"}</button>
      </div>
    </section>
  );
}

function ScenarioEnergyBalance({ before, after }) {
  const width = 1050;
  const height = 310;
  const left = 74;
  const right = 32;
  const top = 24;
  const bottom = 46;
  const values = [...before.demandTrace, ...before.productionTrace, ...after.productionTrace];
  const minY = Math.min(...values) - 65;
  const maxY = Math.max(...values) + 65;
  const x = (index, length) => left + (index * (width - left - right)) / Math.max(length - 1, 1);
  const y = (value) => top + ((maxY - value) * (height - top - bottom)) / Math.max(maxY - minY, 1);
  const path = (series) => series.map((value, index) => `${index === 0 ? "M" : "L"} ${x(index, series.length).toFixed(1)} ${y(value).toFixed(1)}`).join(" ");
  const xTicks = ["−90 s", "−60 s", "−30 s", "Now"];

  return (
    <div className="scenario-energy-chart scenario-energy-chart--balanced">
      <div className="scenario-energy-chart__heading">
        <h3>Shared demand and available production</h3>
        <div className="chart-legend chart-legend--compact">
          <span><i className="legend-line legend-line--demand" />Demand</span>
          <span><i className="legend-line legend-line--baseline" />Conventional production</span>
          <span><i className="legend-line legend-line--production" />Tiangou AI production</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Shared demand and production comparison">
        <rect x={left} y={top} width={width - left - right} height={height - top - bottom} className="plot-panel" />
        {[minY, (minY + maxY) / 2, maxY].map((value) => (
          <g key={value}>
            <line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="grid-line" />
            <text x={left - 14} y={y(value) + 5} textAnchor="end" className="axis-label axis-label--compact">{Math.round(value).toLocaleString()}</text>
          </g>
        ))}
        {xTicks.map((label, index) => {
          const tickX = left + (index * (width - left - right)) / (xTicks.length - 1);
          return (
            <g key={label}>
              <line x1={tickX} x2={tickX} y1={top} y2={height - bottom} className="grid-line grid-line--vertical" />
              <text x={tickX} y={height - 14} textAnchor="middle" className="axis-label axis-label--compact">{label}</text>
            </g>
          );
        })}
        <path d={path(before.demandTrace)} className="detail-path detail-path--demand energy-path" />
        <path d={path(before.productionTrace)} className="detail-path detail-path--before energy-path" />
        <path d={path(after.productionTrace)} className="detail-path detail-path--production energy-path" />
        <text x="18" y={(top + height - bottom) / 2} transform={`rotate(-90 18 ${(top + height - bottom) / 2})`} textAnchor="middle" className="axis-title axis-title--compact">Power (MW)</text>
      </svg>
    </div>
  );
}

const topologyNodes = [
  { label: "NT West", x: 36, y: 74 },
  { label: "NT North", x: 100, y: 36 },
  { label: "NT East", x: 172, y: 73 },
  { label: "Kowloon", x: 115, y: 114 },
  { label: "HK Island", x: 154, y: 165 },
  { label: "Lantau", x: 42, y: 156 },
];

const topologyLinks = [
  [0, 1], [1, 2], [0, 3], [2, 3], [3, 4], [5, 3], [5, 0],
];

function ScenarioGridMap({ title, status, values, mode, mix }) {
  const tone = (value) => value > 100 ? "blackout" : value >= 80 ? "warning" : "good";
  const displayValue = (value) => value > 100 ? "OUTAGE" : `${Math.round(value)}%`;
  const overloads = values.filter((value) => Number(value) > 100);
  const overloadExcess = overloads.reduce((sum, value) => sum + Math.max(0, Number(value) - 100), 0);
  const trippedShare = mode === "conventional" && overloads.length
    ? Math.min(42, 12 + overloads.length * 5 + overloadExcess * 0.18)
    : 0;

  const totalMix = Math.max(1, Number(mix.synchronous || 0) + Number(mix.nonSynchronous || 0) + Number(mix.imports || 0));
  const availableShare = 100 - trippedShare;
  const availableCapacity = Math.round(totalMix * availableShare / 100);
  const trippedCapacity = Math.max(0, Math.round(totalMix - availableCapacity));
  const scale = availableShare / 100;
  const shares = {
    synchronous: (Number(mix.synchronous || 0) / totalMix) * 100 * scale,
    inverter: (Number(mix.nonSynchronous || 0) / totalMix) * 100 * scale,
    imports: (Number(mix.imports || 0) / totalMix) * 100 * scale,
    tripped: trippedShare,
  };

  const nodes = [
    { label: "NT West", x: 52, y: 84, boxX: 6, boxY: 28, anchorX: 47, anchorY: 66 },
    { label: "NT North", x: 130, y: 48, boxX: 91, boxY: 5, anchorX: 130, anchorY: 36 },
    { label: "NT East", x: 210, y: 81, boxX: 180, boxY: 24, anchorX: 211, anchorY: 64 },
    { label: "Kowloon", x: 151, y: 125, boxX: 178, boxY: 107, anchorX: 178, anchorY: 124 },
    { label: "HK Island", x: 195, y: 175, boxX: 167, boxY: 181, anchorX: 195, anchorY: 181 },
    { label: "Lantau", x: 63, y: 166, boxX: 6, boxY: 174, anchorX: 63, anchorY: 174 },
  ];

  const links = [[0,1],[1,2],[0,3],[2,3],[3,4],[5,3],[5,0]];

  return (
    <article className={cx("scenario-grid-map", `scenario-grid-map--${mode}`)}>
      <div className="scenario-grid-map__header">
        <div><p>{title}</p><strong>{status}</strong></div>
        <span>{mode === "conventional" ? "Counterfactual" : "Preventive response"}</span>
      </div>

      <svg viewBox="0 0 270 220" role="img" aria-label={`${title} live topology`}>
        <image
          href="https://commons.wikimedia.org/wiki/Special:FilePath/Hong_Kong_Base_Map.svg"
          x="0"
          y="0"
          width="270"
          height="220"
          preserveAspectRatio="xMidYMid slice"
          className="scenario-grid-map__real-background"
        />

        {nodes.map((node, index) => {
          const currentTone = tone(Number(values[index] ?? 0));
          return currentTone === "blackout" ? (
            <circle key={`blackout-${node.label}`} cx={node.x} cy={node.y} r="8" className="scenario-grid-map__blackout-region" />
          ) : null;
        })}

        {links.map(([from, to], index) => {
          const first = nodes[from];
          const second = nodes[to];
          const lineTone = tone(Math.max(Number(values[from] ?? 0), Number(values[to] ?? 0)));
          return <line key={index} x1={first.x} y1={first.y} x2={second.x} y2={second.y} className={`scenario-grid-map__link scenario-grid-map__link--${lineTone}`} />;
        })}

        {nodes.map((node, index) => {
          const value = Number(values[index] ?? 0);
          const nodeTone = tone(value);
          return (
            <g key={node.label} className={`scenario-grid-map__asset scenario-grid-map__asset--${nodeTone}`}>
              <line x1={node.x} y1={node.y} x2={node.anchorX} y2={node.anchorY} className="scenario-grid-map__leader" />
              <circle cx={node.x} cy={node.y} r="8" className={`scenario-grid-map__node scenario-grid-map__node--${nodeTone}`} />
              <rect x={node.boxX} y={node.boxY} width="82" height="34" rx="6" className="scenario-grid-map__box" />
              <text x={node.boxX + 7} y={node.boxY + 13} className="scenario-grid-map__label">{node.label}</text>
              <text x={node.boxX + 7} y={node.boxY + 27} className={`scenario-grid-map__value scenario-grid-map__value--${nodeTone}`}>{displayValue(value)}</text>
            </g>
          );
        })}
      </svg>

      <div className="scenario-grid-map__mix">
        <div className="scenario-grid-map__mix-heading">
          <span className="scenario-grid-map__mix-title">Available resource mix</span>
          <strong>{availableCapacity.toLocaleString()} MW</strong>
        </div>
        <div className="scenario-grid-map__mix-bar" aria-label={`${title} available resource mix`}>
          <i className="scenario-grid-map__mix-segment scenario-grid-map__mix-segment--sync" style={{ width: `${shares.synchronous}%` }} />
          <i className="scenario-grid-map__mix-segment scenario-grid-map__mix-segment--ibr" style={{ width: `${shares.inverter}%` }} />
          <i className="scenario-grid-map__mix-segment scenario-grid-map__mix-segment--imports" style={{ width: `${shares.imports}%` }} />
          {shares.tripped > 0 ? <i className="scenario-grid-map__mix-segment scenario-grid-map__mix-segment--tripped" style={{ width: `${shares.tripped}%` }} /> : null}
        </div>
        <div className="scenario-grid-map__mix-labels">
          <span>Sync {shares.synchronous.toFixed(0)}%</span>
          <span>IBR {shares.inverter.toFixed(0)}%</span>
          <span>Imports {shares.imports.toFixed(0)}%</span>
          {shares.tripped > 0 ? <span className="scenario-grid-map__mix-label--tripped">Tripped {trippedCapacity.toLocaleString()} MW</span> : <span>Tripped 0 MW</span>}
        </div>
      </div>
    </article>
  );
}

function ScenarioTopologyComparison({ before, after }) {
  const conventionalCritical = before.stabilityRisk >= 55 || before.overloads.some((value) => value > 100);
  const aiCritical = after.stabilityRisk >= 55 || after.overloads.some((value) => value > 100);

  return (
    <aside className="scenario-topology-column" aria-label="Live topology comparison">
      <div className="scenario-topology-column__title"><p className="eyebrow">Live topology</p><h3>Grid response</h3></div>
      <ScenarioGridMap
        title="Conventional grid"
        status={conventionalCritical ? "BLACKOUT RISK" : "DEGRADING"}
        values={before.overloads}
        mix={{ synchronous: before.synchronous, nonSynchronous: before.nonSynchronous, imports: before.imports }}
        mode="conventional"
      />
      <ScenarioGridMap
        title="Tiangou AI grid"
        status={aiCritical ? "WATCH" : "STABLE"}
        values={after.overloads}
        mix={{ synchronous: after.synchronous, nonSynchronous: after.nonSynchronous, imports: after.imports }}
        mode="ai"
      />
    </aside>
  );
}

function MainPanel({ isLive, simulation, navigate }) {
  const { live, before, after } = simulation;
  if (isLive) {
    return (
      <section className="live-center-column">
        <LiveTelemetryChart
          frequencyValues={live.frequencyTrace}
          inertiaValues={live.inertiaTrace}
          demandValues={live.demandTrace}
          productionValues={live.productionTrace}
          demandCurrent={live.demand}
          productionCurrent={live.production}
          predictionValues={live.frequencyPrediction}
          predictionHorizonSec={simulation.predictionHorizonSec}
        />
      </section>
    );
  }

  return (
    <section className="simulation-workspace">
      <div className="simulation-plots-column">
        <ComparisonFrequencyChart
          before={before.frequencyTrace}
          after={after.frequencyTrace}
          beforePrediction={before.frequencyPrediction}
          afterPrediction={after.frequencyPrediction}
          beforeCurrent={before.frequency}
          afterCurrent={after.frequency}
          progress={simulation.progress}
          decisionTaken={simulation.decisionTaken}
          decisionIndex={simulation.decisionTraceIndex ?? 0}
          predictionHorizonSec={simulation.predictionHorizonSec}
        />
        <ScenarioEnergyBalance before={before} after={after} />
        <div className="comparison-summary-strip">
          <div><Leaf size={20} /><span>CO₂ avoided</span><strong>{Math.max(0, before.co2Rate - after.co2Rate).toLocaleString()} t/h</strong></div>
          <div><Wind size={20} /><span>Renewable uplift</span><strong>+{Number(after.renewableIncrease ?? 0).toFixed(1)} pp</strong></div>
          <div><CircleDollarSign size={20} /><span>Estimated saving</span><strong>HK${Number(after.savings ?? 0).toFixed(2)}M</strong></div>
          <button onClick={() => navigate("actions")}>Review action <ArrowRight size={15} /></button>
        </div>
      </div>
      <ScenarioTopologyComparison before={before} after={after} />
    </section>
  );
}

export default function OverviewPage({ scenarioKey, scenarios, setScenarioKey, runScenario, navigate, simulation }) {
  const isLive = simulation.phase === "live";
  return (
    <div className="overview-minimal">
      <div className="overview-minimal__header">
        <div><p className="eyebrow">Operator workspace</p><h1>Live grid overview</h1></div>
        <StatusBadge severity={isLive ? "stable" : simulation.activeScenario.severity}>{isLive ? "Nominal" : simulation.phase === "complete" ? "Validated" : "Simulation active"}</StatusBadge>
      </div>
      <SimulationControls scenarioKey={scenarioKey} setScenarioKey={setScenarioKey} runScenario={runScenario} simulation={simulation} scenarios={scenarios} />
      <section className={cx("overview-telemetry-grid", isLive ? "overview-telemetry-grid--live" : "overview-telemetry-grid--simulation")}>
        <KpiColumn live={simulation.live} before={simulation.before} after={simulation.after} isLive={isLive} aiValidated={simulation.phase === "complete" || simulation.progress >= 100} />
        <MainPanel isLive={isLive} simulation={simulation} navigate={navigate} />
      </section>
    </div>
  );
}
