
import React, { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import OverviewPage from "./pages/OverviewPage";
import StabilityPage from "./pages/StabilityPage";
import ResourcesPage from "./pages/ResourcesPage";
import ImpactPage from "./pages/ImpactPage";
import ReadinessPage from "./pages/ReadinessPage";
import ActionsPage from "./pages/ActionsPage";
import ScenariosPage from "./pages/ScenariosPage";
import AuditPage from "./pages/AuditPage";
import useLiveSimulation from "./hooks/useLiveSimulation";
import { baseAuditEvents, scenarios } from "./data/scenarios";

const validRoutes = new Set([
  "home",
  "overview",
  "stability",
  "resources",
  "impact",
  "readiness",
  "actions",
  "scenarios",
  "audit",
]);


function readStoredTheme() {
  try {
    return window.localStorage?.getItem("tiangou-theme") || "dark";
  } catch {
    return "dark";
  }
}

function persistTheme(theme) {
  try {
    window.localStorage?.setItem("tiangou-theme", theme);
  } catch {
    // Storage can be unavailable in restrictive browser contexts.
  }
}

function readRoute() {
  const raw = window.location.hash.replace(/^#\/?/, "") || "home";
  return validRoutes.has(raw) ? raw : "overview";
}

export default function App() {
  const [route, setRoute] = useState(readRoute);
  const [theme, setTheme] = useState(readStoredTheme);
  const [scenarioKey, setScenarioKey] = useState("generatorTrip");
  const [decision, setDecision] = useState("pending");
  const [auditEvents, setAuditEvents] = useState(baseAuditEvents);
  const [notifications, setNotifications] = useState([]);
  const scenario = scenarios[scenarioKey];

  const addAuditEvent = useCallback((event) => {
    const time = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setAuditEvents((current) => [{ time, ...event }, ...current]);
  }, []);

  const simulation = useLiveSimulation({
    scenarios,
    selectedScenario: scenario,
    onEvent: addAuditEvent,
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    persistTheme(theme);
  }, [theme]);

  useEffect(() => {
    const onHashChange = () => setRoute(readRoute());
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) window.location.hash = "#/home";
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    setDecision("pending");
  }, [scenarioKey]);

  useEffect(() => {
    if (!simulation.warning) return;
    setNotifications((current) => current.some((item) => item.id === simulation.warning.id)
      ? current
      : [{ ...simulation.warning, dismissed: false, createdAt: new Date().toISOString() }, ...current]);
  }, [simulation.warning]);

  const dismissNotification = useCallback((id, options = {}) => {
    setNotifications((current) => current.map((item) => item.id === id ? { ...item, dismissed: true, popup: false, ...options } : item));
  }, []);

  const navigate = (nextRoute) => {
    window.location.hash = `#/${nextRoute}`;
  };

  const selectScenario = (key) => {
    setScenarioKey(key);
    setDecision("pending");
    simulation.resetLive();
  };

  const runScenario = (key = scenarioKey) => {
    const nextScenario = scenarios[key];
    setScenarioKey(key);
    setDecision("pending");
    simulation.startSimulation(nextScenario);
    navigate("overview");
  };

  const page = useMemo(() => {
    const shared = { scenario, navigate, simulation };
    switch (route) {
      case "home":
        return <HomePage navigate={navigate} />;
      case "stability":
        return <StabilityPage {...shared} />;
      case "resources":
        return <ResourcesPage {...shared} />;
      case "impact":
        return <ImpactPage {...shared} />;
      case "readiness":
        return <ReadinessPage {...shared} />;
      case "actions":
        return (
          <ActionsPage
            {...shared}
            decision={decision}
            setDecision={setDecision}
            addAuditEvent={addAuditEvent}
          />
        );
      case "scenarios":
        return (
          <ScenariosPage
            {...shared}
            scenarios={scenarios}
            setScenarioKey={setScenarioKey}
            runScenario={runScenario}
            addAuditEvent={addAuditEvent}
          />
        );
      case "audit":
        return <AuditPage auditEvents={auditEvents} />;
      case "overview":
      default:
        return (
          <OverviewPage
            {...shared}
            scenarios={scenarios}
            scenarioKey={scenarioKey}
            setScenarioKey={selectScenario}
            runScenario={runScenario}
          />
        );
    }
  }, [route, scenario, scenarioKey, decision, auditEvents, simulation, addAuditEvent]);

  return (
    <Layout
      route={route}
      navigate={navigate}
      scenario={scenario}
      scenarios={scenarios}
      setScenarioKey={selectScenario}
      theme={theme}
      toggleTheme={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
      simulation={simulation}
      notifications={notifications}
      dismissNotification={dismissNotification}
    >
      {page}
    </Layout>
  );
}
