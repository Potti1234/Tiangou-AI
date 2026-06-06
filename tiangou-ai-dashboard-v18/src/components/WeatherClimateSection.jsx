
import React from "react";
import {
  AlertTriangle,
  Cloud,
  CloudRain,
  CloudSun,
  Droplets,
  RefreshCcw,
  SunMedium,
  ThermometerSun,
  Wind,
} from "lucide-react";
import useWeatherClimate from "../hooks/useWeatherClimate";
import { SectionTitle, StatusBadge, cx } from "./ui";

function formatHour(value) {
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function RiskCard({ icon: Icon, label, score, tone, note }) {
  return (
    <article className={cx("weather-risk-card", `weather-risk-card--${tone}`)}>
      <div className="weather-risk-card__icon"><Icon size={25} /></div>
      <div>
        <span>{label}</span>
        <strong>{score}%</strong>
        <small>{note}</small>
      </div>
    </article>
  );
}

export default function WeatherClimateSection() {
  const weather = useWeatherClimate();
  const current = weather.current;
  const impact = weather.impact;
  const sourceLabel =
    weather.sourceMode === "live"
      ? "Live APIs"
      : weather.sourceMode === "partial"
      ? "Forecast live · HKO warnings unavailable"
      : "Fallback demonstrator data";

  return (
    <section className="panel-card weather-climate-section">
      <SectionTitle
        eyebrow="Weather and climate intelligence"
        title="Forecast renewable disruption before it affects stability"
        note="Open-Meteo model conditions and forecast are combined with the official Hong Kong Observatory warning summary. Disruption scores are heuristic demonstrator indicators, not utility operating limits."
        action={
          <button className="ghost-btn weather-refresh" onClick={weather.refresh} disabled={weather.loading}>
            <RefreshCcw size={16} className={weather.loading ? "is-spinning" : ""} />
            Refresh
          </button>
        }
      />

      <div className="weather-status-bar">
        <StatusBadge severity={weather.sourceMode === "fallback" ? "warning" : "stable"}>{sourceLabel}</StatusBadge>
        <span>Updated {new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(new Date(weather.updatedAt))}</span>
        {weather.lastError ? <small>{weather.lastError}</small> : null}
      </div>

      <div className="weather-dashboard-grid">
        <div className="weather-current-panel">
          <div className="weather-current-panel__heading">
            <CloudSun size={28} />
            <div>
              <p className="eyebrow">Current Hong Kong conditions</p>
              <h3>Renewable-generation context</h3>
            </div>
          </div>

          <div className="weather-current-grid">
            <div><ThermometerSun size={20} /><span>Temperature</span><strong>{Number(current.temperature).toFixed(1)}°C</strong></div>
            <div><Droplets size={20} /><span>Humidity</span><strong>{Math.round(current.humidity)}%</strong></div>
            <div><Wind size={20} /><span>Wind speed</span><strong>{Math.round(current.windSpeed)} km/h</strong></div>
            <div><Wind size={20} /><span>Wind gusts</span><strong>{Math.round(current.windGusts)} km/h</strong></div>
            <div><Cloud size={20} /><span>Cloud cover</span><strong>{Math.round(current.cloudCover)}%</strong></div>
            <div><CloudRain size={20} /><span>Precipitation</span><strong>{Number(current.precipitation).toFixed(1)} mm</strong></div>
          </div>
        </div>

        <div className="weather-risk-panel">
          <RiskCard icon={SunMedium} label="Solar disruption risk" score={impact.solarScore} tone={impact.solarTone} note={`Peak cloud cover ${impact.maximumCloud}%`} />
          <RiskCard icon={Wind} label="Wind disruption risk" score={impact.windScore} tone={impact.windTone} note={`Peak gust ${Math.round(impact.maximumGust)} km/h`} />
          <RiskCard icon={AlertTriangle} label="Grid-weather attention" score={impact.gridScore} tone={impact.gridTone} note={`${weather.hkoWarnings.length} active HKO warning${weather.hkoWarnings.length === 1 ? "" : "s"}`} />
        </div>
      </div>

      <div className="weather-forecast-row">
        {weather.hourly.slice(0, 8).map((item) => {
          const tone =
            item.windGusts >= 55 || item.precipitationProbability >= 75
              ? "critical"
              : item.windGusts >= 38 || item.cloudCover >= 75 || item.precipitationProbability >= 45
              ? "warning"
              : "good";

          return (
            <article className={cx("weather-hour-card", `weather-hour-card--${tone}`)} key={item.time}>
              <time>{formatHour(item.time)}</time>
              <CloudSun size={19} />
              <strong>{Math.round(item.windGusts)} <small>km/h gust</small></strong>
              <span>{Math.round(item.cloudCover)}% cloud</span>
              <span>{Math.round(item.precipitationProbability)}% rain</span>
            </article>
          );
        })}
      </div>

      <div className="weather-warning-list">
        <div>
          <p className="eyebrow">Official HKO alerts</p>
          <h3>{weather.hkoWarnings.length ? "Warnings currently in force" : "No active warning returned by HKO"}</h3>
        </div>
        {weather.hkoWarnings.length ? (
          weather.hkoWarnings.map((warning) => (
            <span className="weather-warning-chip" key={`${warning.code}-${warning.issuedAt || ""}`}>
              <AlertTriangle size={15} />{warning.name}
            </span>
          ))
        ) : (
          <span className="weather-warning-chip weather-warning-chip--clear"><CloudSun size={15} />Monitoring active</span>
        )}
      </div>
    </section>
  );
}
