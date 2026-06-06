import React from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BatteryCharging,
  Bolt,
  Building2,
  CheckCircle2,
  CircleDollarSign,
  CloudLightning,
  Factory,
  Gauge,
  Leaf,
  Network,
  RadioTower,
  ShieldCheck,
  TrendingDown,
  Wind,
  Zap,
} from "lucide-react";

export function cx(...values) {
  return values.filter(Boolean).join(" ");
}

export function StatusBadge({ severity = "stable", children }) {
  return (
    <span className={cx("status-badge", `status-badge--${severity}`)}>
      <span className="status-badge__dot" />
      {children}
    </span>
  );
}

export function SectionTitle({ eyebrow, title, note, action }) {
  return (
    <div className="section-title">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2>{title}</h2>
        {note ? <p className="section-title__note">{note}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function StatCard({
  label,
  value,
  unit,
  icon: Icon = Activity,
  tone = "default",
  footnote,
  onClick,
}) {
  const Element = onClick ? "button" : "div";
  return (
    <Element className={cx("stat-card", `stat-card--${tone}`, onClick && "stat-card--clickable")} onClick={onClick}>
      <div className="stat-card__top">
        <span>{label}</span>
        <Icon size={17} />
      </div>
      <div className="stat-card__value">
        <strong>{value}</strong>
        {unit ? <small>{unit}</small> : null}
      </div>
      {footnote ? <p>{footnote}</p> : null}
    </Element>
  );
}

export function MiniFrequencyTrace({ values, tone = "good", height = 72 }) {
  const width = 260;
  const minY = Math.min(...values) - 0.08;
  const maxY = Math.max(...values) + 0.08;
  const path = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = 8 + ((maxY - value) / (maxY - minY || 1)) * (height - 16);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg className={cx("mini-trace", `mini-trace--${tone}`)} viewBox={`0 0 ${width} ${height}`} role="img">
      <path d={path} />
    </svg>
  );
}

export function DetailFrequencyChart({ before, after }) {
  const width = 780;
  const height = 310;
  const left = 54;
  const right = 20;
  const top = 25;
  const bottom = 36;
  const minY = 49.0;
  const maxY = 50.1;
  const y = (value) => top + ((maxY - value) * (height - top - bottom)) / (maxY - minY);
  const path = (values) =>
    values
      .map((value, index) => {
        const x = left + (index * (width - left - right)) / (values.length - 1);
        return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y(value).toFixed(1)}`;
      })
      .join(" ");

  return (
    <div className="detail-chart">
      <div className="detail-chart__heading">
        <div>
          <p className="eyebrow">Frequency trajectory</p>
          <h3>Validated response compared with the unmitigated case</h3>
        </div>
        <div className="chart-legend">
          <span><i className="legend-line legend-line--baseline" />Without action</span>
          <span><i className="legend-line legend-line--optimized" />Tiangou AI</span>
          <span><i className="legend-line legend-line--threshold" />Configured threshold</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="detail-chart__svg">
        {[50, 49.75, 49.5, 49.25].map((value) => (
          <g key={value}>
            <line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="grid-line" />
            <text x="5" y={y(value) + 4} className="axis-label">{value.toFixed(2)}</text>
          </g>
        ))}
        <line x1={left} x2={width - right} y1={y(49.5)} y2={y(49.5)} className="threshold-line" />
        <path d={path(before)} className="detail-path detail-path--before" />
        <path d={path(after)} className="detail-path detail-path--after" />
        {["Now", "+2", "+4", "+6", "+8", "+10", "+12", "+14 min"].map((label, index) => (
          <text
            key={label}
            x={left + (index * (width - left - right)) / 7}
            y={height - 9}
            textAnchor={index === 0 ? "start" : index === 7 ? "end" : "middle"}
            className="axis-label"
          >
            {label}
          </text>
        ))}
      </svg>
    </div>
  );
}

export function GridMap({ mode, values, footerLabel }) {
  const before = mode === "before";
  const live = mode === "live";
  const tone = (value) => value >= 100 ? "critical" : value >= 80 ? "warning" : "good";

  const nodes = [
    { label: "NT West", x: 96, y: 112, boxX: 10, boxY: 49, anchorX: 94, anchorY: 91 },
    { label: "NT North", x: 203, y: 64, boxX: 157, boxY: 9, anchorX: 203, anchorY: 48 },
    { label: "NT East", x: 324, y: 121, boxX: 286, boxY: 58, anchorX: 324, anchorY: 98 },
    { label: "Kowloon", x: 231, y: 182, boxX: 260, boxY: 164, anchorX: 260, anchorY: 181 },
    { label: "HK Island", x: 280, y: 257, boxX: 226, boxY: 270, anchorX: 280, anchorY: 270 },
    { label: "Lantau", x: 104, y: 248, boxX: 10, boxY: 260, anchorX: 104, anchorY: 260 },
  ];

  const lines = [
    [96, 112, 203, 64],
    [203, 64, 324, 121],
    [96, 112, 231, 182],
    [324, 121, 231, 182],
    [231, 182, 280, 257],
    [104, 248, 231, 182],
    [104, 248, 96, 112],
  ];

  return (
    <div className={cx("grid-map", before ? "grid-map--before" : live ? "grid-map--live" : "grid-map--after")}>
      <div className="real-map-background" aria-hidden="true">
        <img
          className="real-map-background__wikimedia"
          src="https://upload.wikimedia.org/wikipedia/commons/7/76/Hong_Kong_Base_Map.svg"
          alt=""
        />
      </div>

      <svg viewBox="0 0 420 320" role="img" aria-label={`${mode} Hong Kong grid visualization`}>
        {lines.map(([x1, y1, x2, y2], index) => (
          <line key={index} x1={x1} y1={y1} x2={x2} y2={y2} className="grid-map__line" />
        ))}

        {nodes.map((node, index) => {
          const value = Number(values[index] ?? 0);
          const nodeTone = tone(value);
          return (
            <g key={node.label} className={`node-label node-label--${nodeTone}`}>
              <line x1={node.x} y1={node.y} x2={node.anchorX} y2={node.anchorY} className="node-label__leader" />
              <circle cx={node.x} cy={node.y} r="11" className="grid-map__node" />
              <circle cx={node.x} cy={node.y} r="4" className="grid-map__core" />
              <rect x={node.boxX} y={node.boxY} width="112" height="42" rx="7" className="node-label__box" />
              <text x={node.boxX + 9} y={node.boxY + 16} className="grid-map__label">{node.label}</text>
              <text x={node.boxX + 9} y={node.boxY + 34} className="grid-map__value">{value.toFixed(0)}%</text>
            </g>
          );
        })}
      </svg>

      <div className="grid-map__footer">
        <span><RadioTower size={15} />Hong Kong base map · Wikimedia Commons</span>
        <span>{footerLabel || (before ? "Overload risk visible" : live ? "Stable operation" : "Optimal dispatch active")}</span>
      </div>
    </div>
  );
}

export function ExploreCard({ icon: Icon, title, description, to, navigate, tag }) {
  return (
    <button className="explore-card" onClick={() => navigate(to)}>
      <div className="explore-card__icon"><Icon size={19} /></div>
      <div>
        <div className="explore-card__title-row">
          <h3>{title}</h3>
          {tag ? <small>{tag}</small> : null}
        </div>
        <p>{description}</p>
      </div>
      <ArrowRight className="explore-card__arrow" size={18} />
    </button>
  );
}

export function ResourceIcon({ type }) {
  const icons = {
    synchronous: Factory,
    inverter: Wind,
    import: Network,
    battery: BatteryCharging,
    flexible: Bolt,
    demand: Building2,
    savings: CircleDollarSign,
    emissions: Leaf,
    risk: AlertTriangle,
    frequency: Activity,
    inertia: Gauge,
    power: Zap,
    weather: CloudLightning,
    security: ShieldCheck,
  };
  const Icon = icons[type] || Zap;
  return <Icon size={17} />;
}

export function ValueBar({ label, value, max, unit, tone = "good", icon }) {
  return (
    <div className="value-bar">
      <div className="value-bar__top">
        <span>{icon}{label}</span>
        <strong>{value.toLocaleString()} <small>{unit}</small></strong>
      </div>
      <div className="progress"><span className={`progress__fill progress__fill--${tone}`} style={{ width: `${Math.min((value / max) * 100, 100)}%` }} /></div>
    </div>
  );
}

export const iconSet = {
  Activity,
  AlertTriangle,
  BatteryCharging,
  Bolt,
  Building2,
  CheckCircle2,
  CircleDollarSign,
  CloudLightning,
  Factory,
  Gauge,
  Leaf,
  Network,
  ShieldCheck,
  TrendingDown,
  Wind,
  Zap,
};


export function LiveTelemetryChart({
  frequencyValues,
  inertiaValues,
  demandValues = [],
  productionValues = [],
  predictionValues = [],
  predictionHorizonSec = 20,
  demandCurrent,
  productionCurrent,
  threshold = 49.5,
}) {
  const width = 1320;
  const height = 610;
  const left = 82;
  const right = 88;
  const upperTop = 30;
  const upperBottom = 260;
  const lowerTop = 338;
  const lowerBottom = 568;
  const nowX = left + (width - left - right) * 0.79;
  const pastWidth = nowX - left;
  const fullWidth = width - left - right;
  const futureWidth = width - right - nowX;
  const minFrequency = 49.45;
  const maxFrequency = 50.08;
  const minInertia = 1.8;
  const maxInertia = 2.65;
  const allEnergy = [...demandValues, ...productionValues];
  const maxEnergy = Math.max(...allEnergy, 1) + 95;
  const minEnergy = Math.min(...allEnergy, maxEnergy) - 95;

  const xPast = (index, length) => left + (index * pastWidth) / Math.max(length - 1, 1);
  const xEnergy = (index, length) => left + (index * fullWidth) / Math.max(length - 1, 1);
  const xFuture = (index, length) => nowX + (index * futureWidth) / Math.max(length - 1, 1);
  const yFrequency = (value) => upperTop + ((maxFrequency - value) * (upperBottom - upperTop)) / (maxFrequency - minFrequency);
  const yInertia = (value) => upperTop + ((maxInertia - value) * (upperBottom - upperTop)) / (maxInertia - minInertia);
  const yEnergy = (value) => lowerTop + ((maxEnergy - value) * (lowerBottom - lowerTop)) / Math.max(maxEnergy - minEnergy, 1);
  const path = (values, x, y) => values.map((value, index) => `${index === 0 ? "M" : "L"} ${x(index, values.length).toFixed(1)} ${y(value).toFixed(1)}`).join(" ");
  const pastTicks = ["−60 s", "−45 s", "−30 s", "−15 s", "Now"];
  const energyTicks = ["−60 s", "−45 s", "−30 s", "−15 s", "Now"];
  const futureTicks = ["+5", "+10", "+15", `+${predictionHorizonSec} s`];

  return (
    <div className="live-chart live-chart--compact">
      <div className="live-chart__heading">
        <div><p className="eyebrow">Live telemetry and PINN forecast</p><h3>Frequency, inertia and energy balance</h3></div>
        <div className="chart-legend chart-legend--compact">
          <span><i className="legend-line legend-line--actual" />Observed frequency</span>
          <span><i className="legend-line legend-line--ai-forecast" />PINN forecast</span>
          <span><i className="legend-line legend-line--inertia" />Inertia</span>
          <span><i className="legend-line legend-line--demand" />Demand</span>
          <span><i className="legend-line legend-line--production" />Production</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="live-chart__svg live-chart__svg--compact" role="img" aria-label="Live frequency, inertia, demand, production and PINN forecast">
        <rect x={left} y={upperTop} width={fullWidth} height={upperBottom - upperTop} className="plot-panel" />
        <rect x={left} y={lowerTop} width={fullWidth} height={lowerBottom - lowerTop} className="plot-panel" />
        <rect x={nowX} y={upperTop} width={futureWidth} height={upperBottom - upperTop} className="forecast-zone" />
        {[50.00, 49.90, 49.80, 49.70, 49.60, 49.50].map((value) => (
          <g key={`frequency-${value}`}>
            <line x1={left} x2={width - right} y1={yFrequency(value)} y2={yFrequency(value)} className="grid-line" />
            <text x={left - 15} y={yFrequency(value) + 5} textAnchor="end" className="axis-label axis-label--compact">{value.toFixed(2)}</text>
          </g>
        ))}
        {[2.0, 2.2, 2.4, 2.6].map((value) => (
          <text key={`inertia-${value}`} x={width - right + 15} y={yInertia(value) + 5} className="axis-label axis-label--compact">{value.toFixed(1)}</text>
        ))}
        {[minEnergy, (minEnergy + maxEnergy) / 2, maxEnergy].map((value) => (
          <g key={`energy-${value}`}>
            <line x1={left} x2={width - right} y1={yEnergy(value)} y2={yEnergy(value)} className="grid-line" />
            <text x={left - 15} y={yEnergy(value) + 5} textAnchor="end" className="axis-label axis-label--compact">{Math.round(value).toLocaleString()}</text>
          </g>
        ))}
        {pastTicks.map((label, index) => {
          const tickX = left + (index * pastWidth) / (pastTicks.length - 1);
          return (
            <g key={`upper-${label}`}>
              <line x1={tickX} x2={tickX} y1={upperTop} y2={upperBottom} className="grid-line grid-line--vertical" />
              <text x={tickX} y={upperBottom + 22} textAnchor="middle" className="axis-label axis-label--compact">{label}</text>
            </g>
          );
        })}
        {energyTicks.map((label, index) => {
          const tickX = left + (index * fullWidth) / (energyTicks.length - 1);
          return (
            <g key={`lower-${label}`}>
              <line x1={tickX} x2={tickX} y1={lowerTop} y2={lowerBottom} className="grid-line grid-line--vertical" />
              <text x={tickX} y={height - 14} textAnchor="middle" className="axis-label axis-label--compact">{label}</text>
            </g>
          );
        })}
        {futureTicks.map((label, index) => {
          const tickX = nowX + ((index + 1) * futureWidth) / futureTicks.length;
          return (
            <g key={label}>
              <line x1={tickX} x2={tickX} y1={upperTop} y2={upperBottom} className="grid-line grid-line--vertical forecast-grid" />
              <text x={tickX} y={upperBottom + 22} textAnchor="middle" className="axis-label axis-label--future">{label}</text>
            </g>
          );
        })}
        <line x1={left} x2={width - right} y1={yFrequency(threshold)} y2={yFrequency(threshold)} className="threshold-line" />
        <text x={width - right - 5} y={yFrequency(threshold) - 9} textAnchor="end" className="threshold-label threshold-label--compact">49.50 Hz threshold</text>
        <path d={path(frequencyValues, xPast, yFrequency)} className="detail-path detail-path--actual live-path" />
        <path d={path(inertiaValues, xPast, yInertia)} className="detail-path detail-path--inertia live-path" />
        <path d={path(predictionValues, xFuture, yFrequency)} className="detail-path detail-path--ai-forecast live-path" />
        <line x1={nowX} x2={nowX} y1={upperTop} y2={upperBottom} className="now-line" />
        <text x={nowX + 7} y={upperTop + 16} className="forecast-zone__label forecast-zone__label--compact">PINN +20 s</text>
        <path d={path(demandValues, xEnergy, yEnergy)} className="detail-path detail-path--demand energy-path" />
        <path d={path(productionValues, xEnergy, yEnergy)} className="detail-path detail-path--production energy-path" />
        <text x="18" y={(upperTop + upperBottom) / 2} transform={`rotate(-90 18 ${(upperTop + upperBottom) / 2})`} textAnchor="middle" className="axis-title axis-title--compact">Frequency (Hz)</text>
        <text x={width - 18} y={(upperTop + upperBottom) / 2} transform={`rotate(90 ${width - 18} ${(upperTop + upperBottom) / 2})`} textAnchor="middle" className="axis-title axis-title--compact">Inertia (s)</text>
        <text x="18" y={(lowerTop + lowerBottom) / 2} transform={`rotate(-90 18 ${(lowerTop + lowerBottom) / 2})`} textAnchor="middle" className="axis-title axis-title--compact">Power (MW)</text>
        <text x={left} y={lowerTop - 16} className="energy-label energy-label--compact">Demand {Number(demandCurrent ?? demandValues.at(-1) ?? 0).toLocaleString()} MW · Production {Number(productionCurrent ?? productionValues.at(-1) ?? 0).toLocaleString()} MW</text>
      </svg>
    </div>
  );
}



export function ComparisonFrequencyChart({
  before,
  after,
  beforePrediction = [],
  afterPrediction = [],
  beforeCurrent,
  afterCurrent,
  progress,
  decisionIndex = 0,
  decisionTaken = false,
  predictionHorizonSec = 20,
}) {
  const width = 1050;
  const height = 310;
  const left = 74;
  const right = 38;
  const top = 24;
  const bottom = 46;
  const nowX = left + (width - left - right) * 0.78;
  const pastWidth = nowX - left;
  const futureWidth = width - right - nowX;
  const minY = 49.0;
  const maxY = 50.08;
  const threshold = 49.5;
  const xPast = (index, length) => left + (index * pastWidth) / Math.max(length - 1, 1);
  const xFuture = (index, length) => nowX + (index * futureWidth) / Math.max(length - 1, 1);
  const y = (value) => top + ((maxY - value) * (height - top - bottom)) / (maxY - minY);
  const path = (values, x) => values.map((value, index) => `${index === 0 ? "M" : "L"} ${x(index, values.length).toFixed(1)} ${y(value).toFixed(1)}`).join(" ");
  const markerX = xPast(Math.min(Math.max(decisionIndex, 0), Math.max(after.length - 1, 0)), Math.max(after.length, 1));
  const pastTicks = ["−90 s", "−60 s", "−30 s", "Now"];
  const futureTicks = ["+5", "+10", "+15", `+${predictionHorizonSec} s`];

  return (
    <div className="live-chart comparison-chart comparison-chart--balanced">
      <div className="live-chart__heading">
        <div><p className="eyebrow">Digital-twin comparison</p><h3>Conventional response versus Tiangou AI</h3></div>
        <div className="chart-legend chart-legend--compact">
          <span><i className="legend-line legend-line--baseline" />Conventional trajectory</span>
          <span><i className="legend-line legend-line--ai" />Tiangou AI trajectory</span>
          <span><i className="legend-line legend-line--baseline-forecast" />Conventional forecast</span>
          <span><i className="legend-line legend-line--ai-forecast" />Tiangou AI forecast</span>
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="comparison-chart__svg--balanced" role="img" aria-label="Frequency comparison with AI decision point and twenty second prediction">
        <rect x={left} y={top} width={width - left - right} height={height - top - bottom} className="plot-panel" />
        <rect x={nowX} y={top} width={futureWidth} height={height - top - bottom} className="forecast-zone" />
        {[50.00, 49.75, 49.50, 49.25, 49.00].map((value) => (
          <g key={value}>
            <line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="grid-line" />
            <text x={left - 14} y={y(value) + 5} textAnchor="end" className="axis-label axis-label--compact">{value.toFixed(2)}</text>
          </g>
        ))}
        {pastTicks.map((label, index) => {
          const tickX = left + (index * pastWidth) / (pastTicks.length - 1);
          return (
            <g key={label}>
              <line x1={tickX} x2={tickX} y1={top} y2={height - bottom} className="grid-line grid-line--vertical" />
              <text x={tickX} y={height - 14} textAnchor="middle" className="axis-label axis-label--compact">{label}</text>
            </g>
          );
        })}
        {futureTicks.map((label, index) => {
          const tickX = nowX + ((index + 1) * futureWidth) / futureTicks.length;
          return (
            <g key={label}>
              <line x1={tickX} x2={tickX} y1={top} y2={height - bottom} className="grid-line grid-line--vertical forecast-grid" />
              <text x={tickX} y={height - 14} textAnchor="middle" className="axis-label axis-label--future">{label}</text>
            </g>
          );
        })}
        <line x1={left} x2={width - right} y1={y(threshold)} y2={y(threshold)} className="threshold-line" />
        <text x={width - right - 5} y={y(threshold) - 9} textAnchor="end" className="threshold-label threshold-label--compact">49.50 Hz threshold</text>
        <path d={path(before, xPast)} className="detail-path detail-path--before live-path" />
        <path d={path(after, xPast)} className="detail-path detail-path--ai live-path" />
        <path d={path(beforePrediction, xFuture)} className="detail-path detail-path--baseline-forecast live-path" />
        <path d={path(afterPrediction, xFuture)} className="detail-path detail-path--ai-forecast live-path" />
        <line x1={nowX} x2={nowX} y1={top} y2={height - bottom} className="now-line" />
        <text x={nowX + 7} y={top + 16} className="forecast-zone__label forecast-zone__label--compact">PINN +20 s</text>
        {decisionTaken ? <g className="ai-decision-marker ai-decision-marker--line-only"><line x1={markerX} x2={markerX} y1={top} y2={height - bottom} /><text x={markerX + 7} y={top + 36}>AI decision</text></g> : null}
        <text x="18" y={(top + height - bottom) / 2} transform={`rotate(-90 18 ${(top + height - bottom) / 2})`} textAnchor="middle" className="axis-title axis-title--compact">Frequency (Hz)</text>
        <text x={width - right} y={top + 15} textAnchor="end" className="simulation-progress-label simulation-progress-label--compact">{progress}%</text>
      </svg>
    </div>
  );
}


export function TopologyComparisonTable({ conventional, ai, liveOnly = false }) {
  const nodes = ["NT West", "NT North", "NT East", "Kowloon", "HK Island", "Lantau"];
  const tone = (value) => value >= 100 ? "critical" : value >= 80 ? "warning" : "good";

  return (
    <div className="topology-comparison-table">
      <table>
        <thead>
          <tr>
            <th>Node</th>
            <th>{liveOnly ? "Loading" : "Conv."}</th>
            {!liveOnly ? <th>AI</th> : null}
            {!liveOnly ? <th>Δ</th> : null}
          </tr>
        </thead>
        <tbody>
          {nodes.map((node, index) => {
            const conv = Number(conventional[index] ?? 0);
            const aiValue = Number(ai[index] ?? conv);
            const delta = aiValue - conv;
            return (
              <tr key={node}>
                <td>{node}</td>
                <td className={`node-value node-value--${tone(conv)}`}>{conv.toFixed(0)}%</td>
                {!liveOnly ? <td className={`node-value node-value--${tone(aiValue)}`}>{aiValue.toFixed(0)}%</td> : null}
                {!liveOnly ? <td className={delta <= 0 ? "delta-good" : "delta-bad"}>{delta > 0 ? "+" : ""}{delta.toFixed(0)} pp</td> : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
