
import { useCallback, useEffect, useMemo, useState } from "react";

const OPEN_METEO_URL =
  "https://api.open-meteo.com/v1/forecast?latitude=22.3193&longitude=114.1694&current=temperature_2m,relative_humidity_2m,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m,weather_code&hourly=temperature_2m,precipitation_probability,precipitation,cloud_cover,wind_speed_10m,wind_gusts_10m,shortwave_radiation&forecast_days=3&timezone=Asia%2FHong_Kong";
const HKO_WARNINGS_URL =
  "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=en";

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

function riskTone(score) {
  if (score >= 70) return "critical";
  if (score >= 38) return "warning";
  return "good";
}

function buildFallback() {
  const now = new Date();
  const hourly = Array.from({ length: 12 }, (_, index) => {
    const time = new Date(now.getTime() + index * 60 * 60 * 1000);
    const cloud = 38 + Math.round(Math.sin(index / 2) * 14);
    const gust = 23 + Math.round(Math.sin(index / 3) * 8);
    const rainProbability = Math.max(5, 16 + Math.round(Math.cos(index / 2.4) * 10));
    const radiation = Math.max(0, 540 - index * 24 - cloud * 2);
    return {
      time: time.toISOString(),
      cloudCover: cloud,
      windSpeed: Math.max(5, gust - 8),
      windGusts: gust,
      precipitationProbability: rainProbability,
      precipitation: rainProbability > 45 ? 0.8 : 0,
      shortwaveRadiation: radiation,
    };
  });

  return {
    sourceMode: "fallback",
    updatedAt: now.toISOString(),
    current: {
      temperature: 27.4,
      humidity: 73,
      precipitation: 0,
      cloudCover: 42,
      windSpeed: 16,
      windGusts: 28,
      weatherCode: 2,
    },
    hourly,
    hkoWarnings: [],
  };
}

function parseOpenMeteo(data) {
  const current = data.current || {};
  const hourly = data.hourly || {};
  const nowIndex = Math.max(
    0,
    (hourly.time || []).findIndex((time) => new Date(time).getTime() >= Date.now())
  );

  const forecast = (hourly.time || []).slice(nowIndex, nowIndex + 12).map((time, relativeIndex) => {
    const index = nowIndex + relativeIndex;
    return {
      time,
      cloudCover: hourly.cloud_cover?.[index] ?? 0,
      windSpeed: hourly.wind_speed_10m?.[index] ?? 0,
      windGusts: hourly.wind_gusts_10m?.[index] ?? 0,
      precipitationProbability: hourly.precipitation_probability?.[index] ?? 0,
      precipitation: hourly.precipitation?.[index] ?? 0,
      shortwaveRadiation: hourly.shortwave_radiation?.[index] ?? 0,
    };
  });

  return {
    updatedAt: current.time || new Date().toISOString(),
    current: {
      temperature: current.temperature_2m ?? 0,
      humidity: current.relative_humidity_2m ?? 0,
      precipitation: current.precipitation ?? 0,
      cloudCover: current.cloud_cover ?? 0,
      windSpeed: current.wind_speed_10m ?? 0,
      windGusts: current.wind_gusts_10m ?? 0,
      weatherCode: current.weather_code ?? 0,
    },
    hourly: forecast,
  };
}

function parseWarnings(data) {
  return Object.values(data || {})
    .filter((warning) => warning && warning.actionCode !== "CANCEL")
    .map((warning) => ({
      name: warning.name || warning.code || "Weather warning",
      code: warning.code || "HKO",
      issuedAt: warning.issueTime || warning.updateTime || null,
    }));
}

function deriveImpact(weather) {
  const forecast = weather.hourly || [];
  const maximumGust = Math.max(weather.current.windGusts || 0, ...forecast.map((item) => item.windGusts || 0));
  const maximumCloud = Math.max(weather.current.cloudCover || 0, ...forecast.map((item) => item.cloudCover || 0));
  const maximumRainProbability = Math.max(...forecast.map((item) => item.precipitationProbability || 0), 0);
  const minimumRadiation = Math.min(...forecast.map((item) => item.shortwaveRadiation || 0), 9999);

  const windScore = clamp((maximumGust - 28) * 2.2, 0, 100);
  const solarScore = clamp(maximumCloud * 0.58 + maximumRainProbability * 0.36 + (minimumRadiation < 160 ? 16 : 0), 0, 100);
  const severeWarningBonus = weather.hkoWarnings.length ? 22 : 0;
  const gridScore = clamp(Math.max(windScore, solarScore) + severeWarningBonus, 0, 100);

  return {
    windScore: Math.round(windScore),
    solarScore: Math.round(solarScore),
    gridScore: Math.round(gridScore),
    windTone: riskTone(windScore),
    solarTone: riskTone(solarScore),
    gridTone: riskTone(gridScore),
    maximumGust,
    maximumCloud,
    maximumRainProbability,
  };
}

export default function useWeatherClimate() {
  const [weather, setWeather] = useState(buildFallback);
  const [loading, setLoading] = useState(true);
  const [lastError, setLastError] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [meteoResponse, hkoResponse] = await Promise.allSettled([
        fetch(OPEN_METEO_URL),
        fetch(HKO_WARNINGS_URL),
      ]);

      if (meteoResponse.status !== "fulfilled" || !meteoResponse.value.ok) {
        throw new Error("Open-Meteo forecast unavailable");
      }

      const meteoData = await meteoResponse.value.json();
      const parsed = parseOpenMeteo(meteoData);
      let hkoWarnings = [];

      if (hkoResponse.status === "fulfilled" && hkoResponse.value.ok) {
        hkoWarnings = parseWarnings(await hkoResponse.value.json());
      }

      setWeather({
        ...parsed,
        hkoWarnings,
        sourceMode: hkoResponse.status === "fulfilled" && hkoResponse.value.ok ? "live" : "partial",
      });
      setLastError(null);
    } catch (error) {
      setWeather(buildFallback());
      setLastError(error instanceof Error ? error.message : "Weather API unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = window.setInterval(refresh, 10 * 60 * 1000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const impact = useMemo(() => deriveImpact(weather), [weather]);

  return {
    ...weather,
    impact,
    loading,
    lastError,
    refresh,
  };
}
