const API_BASE = (import.meta.env.VITE_TELEMETRY_API_URL || "").replace(/\/$/, "");
const API_MODE = (import.meta.env.VITE_TELEMETRY_MODE || "mock").toLowerCase();
const WS_URL = import.meta.env.VITE_TELEMETRY_WS_URL || "";

export function getTelemetryMode() {
  return API_MODE === "api" && API_BASE ? "database-api" : "mock-fallback";
}

export function isDatabaseConfigured() {
  return getTelemetryMode() === "database-api";
}

function numberOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function arrayOr(value, fallback = []) {
  return Array.isArray(value) ? value.map((item) => Number(item)).filter(Number.isFinite) : fallback;
}

export function normalizeTelemetrySnapshot(payload, fallback) {
  if (!payload || typeof payload !== "object") return fallback;
  const source = payload.telemetry || payload;
  const forecast = payload.forecast || source.forecast || {};

  return {
    ...fallback,
    frequency: numberOr(source.frequency_hz ?? source.frequency, fallback.frequency),
    inertia: numberOr(source.inertia_seconds ?? source.inertia, fallback.inertia),
    criticalInertia: numberOr(source.critical_inertia_seconds ?? source.criticalInertia, fallback.criticalInertia),
    rocof: numberOr(source.rocof_hz_s ?? source.rocof, fallback.rocof),
    co2Rate: numberOr(source.co2_t_h ?? source.co2Rate, fallback.co2Rate),
    gap: numberOr(source.gap_mw ?? source.gap, fallback.gap),
    reserves: numberOr(source.fast_reserve_mw ?? source.reserves, fallback.reserves),
    stabilityRisk: numberOr(source.stability_risk_pct ?? source.stabilityRisk, fallback.stabilityRisk),
    thresholdBreach: numberOr(source.threshold_breach_probability_pct ?? source.thresholdBreach, fallback.thresholdBreach),
    demand: numberOr(source.demand_mw ?? source.demand, fallback.demand),
    production: numberOr(source.production_mw ?? source.production, fallback.production),
    synchronous: numberOr(source.synchronous_mw ?? source.synchronous, fallback.synchronous),
    nonSynchronous: numberOr(source.non_synchronous_mw ?? source.nonSynchronous, fallback.nonSynchronous),
    imports: numberOr(source.imports_mw ?? source.imports, fallback.imports),
    batteryFlex: numberOr(source.battery_flex_mw ?? source.batteryFlex, fallback.batteryFlex),
    evFlex: numberOr(source.ev_flex_mw ?? source.evFlex, fallback.evFlex),
    flexibleDemand: numberOr(source.flexible_demand_mw ?? source.flexibleDemand, fallback.flexibleDemand),
    curtailment: numberOr(source.curtailment_mwh ?? source.curtailment, fallback.curtailment),
    renewableShare: numberOr(source.renewable_share_pct ?? source.renewableShare, fallback.renewableShare),
    overloads: arrayOr(source.zone_loading_pct ?? source.overloads, fallback.overloads),
    frequencyPrediction: arrayOr(forecast.frequency_hz ?? source.frequency_prediction_hz, fallback.frequencyPrediction),
    dataTimestamp: source.timestamp || payload.timestamp || new Date().toISOString(),
    dataSource: "database-api",
  };
}

export async function fetchLatestTelemetry({ signal } = {}) {
  if (!isDatabaseConfigured()) return null;
  const response = await fetch(`${API_BASE}/telemetry/latest?include=forecast,resources,zones`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error(`Telemetry API returned ${response.status}`);
  return response.json();
}

export function connectTelemetrySocket(onSnapshot, onError) {
  if (!WS_URL || typeof WebSocket === "undefined") return undefined;
  const socket = new WebSocket(WS_URL);
  socket.addEventListener("message", (event) => {
    try {
      onSnapshot(JSON.parse(event.data));
    } catch (error) {
      onError?.(error);
    }
  });
  socket.addEventListener("error", (error) => onError?.(error));
  return () => socket.close();
}
